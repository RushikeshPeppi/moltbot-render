"""
Two-user RLS isolation test — Phase 6 · 1.6b (CASA 3.1.4).

THE GATE: do NOT set RLS_SCOPED_JWT=true in production until this passes against live
Supabase. It is the only thing that distinguishes "RLS is enforced" from "RLS policies
exist" — and this project has already been burned once by treating the presence of a
policy as proof of enforcement (the Supabase console shows "1 RLS policy" on
tbl_clawdbot_credentials while service_role bypasses it entirely).

WHAT IT PROVES
  1. A scoped JWT for user A can read/write A's own credential row.
  2. A scoped JWT for user A CANNOT read user B's row  <-- the actual control.
  3. A scoped JWT for user A CANNOT overwrite B's row  (WITH CHECK, not just USING).
  4. Fail-closed: flag on + missing secret => raises, never silently degrades to
     service_role.
  5. service_role still sees both rows (proving the test rows really exist and that we
     are observing RLS filtering, not an empty table / a broken query).

Point 5 matters: without it, a query that returns nothing because it is simply BROKEN
looks identical to RLS working perfectly. That false-green is exactly what this file is
guarding against.

RUN (never against prod data; use a scratch project or accept the test rows are created
and deleted under clearly-marked ids):
    export SUPABASE_URL=... SUPABASE_KEY=<service_role> \
           SUPABASE_ANON_KEY=... SUPABASE_JWT_SECRET=... \
           ENCRYPTION_KEY=<fernet key> RLS_SCOPED_JWT=true
    pytest tests/test_rls_isolation.py -v
"""

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not all(
        os.getenv(k)
        for k in ("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_ANON_KEY", "SUPABASE_JWT_SECRET")
    ),
    reason="live Supabase creds + JWT secret + anon key required (see module docstring)",
)

USER_A = f"rlstest_a_{uuid.uuid4().hex[:8]}"
USER_B = f"rlstest_b_{uuid.uuid4().hex[:8]}"
SERVICE = "google_oauth"


@pytest.fixture
async def db():
    from app.core.database import Database

    d = Database()
    await d.initialize()
    yield d
    # Teardown with the service_role client so cleanup cannot itself be blocked by RLS.
    for uid in (USER_A, USER_B):
        try:
            d._client.table("tbl_clawdbot_credentials").delete().eq("user_id", uid).execute()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_scoped_jwt_isolates_users(db):
    """A cannot read B's credential row. This is the control."""
    await db.store_credentials(USER_A, SERVICE, {"access_token": "A-token"})
    await db.store_credentials(USER_B, SERVICE, {"access_token": "B-token"})

    a = await db.get_credentials(USER_A, SERVICE)
    assert a is not None, "user A must see its OWN row"
    assert a.get("access_token") == "A-token"

    # Sanity: both rows genuinely exist (service_role bypasses RLS). Without this, a
    # broken query returning None would masquerade as perfect isolation.
    both = db._client.table("tbl_clawdbot_credentials").select("user_id").in_(
        "user_id", [USER_A, USER_B]
    ).execute()
    assert len({r["user_id"] for r in both.data}) == 2, "both test rows must exist"

    # The assertion that matters: A's scoped client must NOT see B's row.
    leaked = db._scoped(USER_A).table("tbl_clawdbot_credentials").select("user_id").eq(
        "user_id", USER_B
    ).execute()
    assert leaked.data == [], f"RLS LEAK: user A read user B's row -> {leaked.data}"


@pytest.mark.asyncio
async def test_scoped_jwt_cannot_write_another_user(db):
    """WITH CHECK: A must not be able to create/overwrite a row owned by B."""
    await db.store_credentials(USER_B, SERVICE, {"access_token": "B-token"})
    with pytest.raises(Exception):
        db._scoped(USER_A).table("tbl_clawdbot_credentials").upsert(
            {"user_id": USER_B, "service": SERVICE, "encrypted_credentials": "x"}
        ).execute()


@pytest.mark.asyncio
async def test_fails_closed_without_secret(db, monkeypatch):
    """Flag ON + secret MISSING must RAISE, never fall back to service_role."""
    from app.config import settings

    monkeypatch.setattr(settings, "RLS_SCOPED_JWT", True)
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", "")
    with pytest.raises(RuntimeError, match="SUPABASE_JWT_SECRET"):
        db._scoped(USER_A)

    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", "secret")
    monkeypatch.setattr(settings, "SUPABASE_ANON_KEY", "")
    with pytest.raises(RuntimeError, match="SUPABASE_ANON_KEY"):
        db._scoped(USER_A)


@pytest.mark.asyncio
async def test_flag_off_is_byte_identical(db, monkeypatch):
    """With the flag OFF, _scoped() must return the plain service_role client."""
    from app.config import settings

    monkeypatch.setattr(settings, "RLS_SCOPED_JWT", False)
    assert db._scoped(USER_A) is db._client
