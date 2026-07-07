"""
Service-to-service authentication gate.

Trusted internal callers — Peppi Laravel and the OpenClaw gateway — must present
the shared secret in the `X-Moltbot-Key` header. Everything that touches a user's
Google tokens, mailbox, calendar, credentials, session, or PII is gated by this.

Design (CASA Ch3 3.1.1/3.1.3/3.1.4):
  * FAIL CLOSED. If INTERNAL_SERVICE_KEY is unset on the server, every guarded
    route returns 503 — it must never silently become open (mirrors admin.py's
    fail-closed pattern; the whole reason we're here is a missing trust boundary).
  * Timing-safe comparison via hmac.compare_digest.
  * The end-user identity (`user_id`) is trusted only *because* the caller proved
    it is a trusted service. Peppi/the gateway already authenticated the end user
    upstream (Peppi session / Twilio). This gate establishes "trusted internal
    caller"; the anonymous IDOR (P0-1/P0-2/P1-1/P1-4) is closed because an
    unauthenticated caller can no longer reach these routes at all.

The public OAuth callback (Google → us) and health checks are deliberately NOT
guarded by this — see main.py wiring.
"""

from __future__ import annotations

import hmac
from typing import Optional

from fastapi import Header, HTTPException, status

from ..config import settings


def require_service_auth(
    x_moltbot_key: Optional[str] = Header(default=None, alias="X-Moltbot-Key"),
) -> None:
    """FastAPI dependency. Raises 503 if unconfigured, 401 on bad/missing key."""
    expected = settings.INTERNAL_SERVICE_KEY
    if not expected:
        # Misconfigured deploy — fail closed. Never serve token/mailbox routes
        # just because the secret wasn't provisioned.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="INTERNAL_SERVICE_KEY not configured on server",
        )
    if not hmac.compare_digest(x_moltbot_key or "", expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing service key",
        )
