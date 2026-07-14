"""
Fail-CLOSED rate limiting for the publicly-reachable / auth-adjacent routes (P2-4, CASA 1.1.1).

WHY NOT slowapi (which is already in requirements.txt, unused):
slowapi's storage backends speak the RESP protocol (`redis://`). Our Redis is Upstash over
its REST API (`upstash-redis`), and we hold no RESP URL — so slowapi would silently fall back
to per-process in-memory counters. On Render that means the limit is per-instance and resets
on every deploy/restart: a limiter that looks enforced in code review and isn't. We use the
Redis we actually have. (slowapi stays in requirements only because removing it is a separate
change; it is deliberately not wired.)

FAIL-CLOSED, and it costs us nothing to be:
`check()` DENIES when Redis is unreachable. Standing rule — a security control whose
dependency is missing must deny, not wave traffic through. The two fail-OPEN limiters in this
codebase's history (QStash signature verify P1-5, Redis limits P3-6) are exactly why. And on
the routes below the cost of failing closed is zero: the OAuth callback already REQUIRES Redis
to look up its `state`, so a Redis outage breaks that flow regardless — denying is not a new
failure mode, it is the same one, stated honestly.

Scope note (deliberate, not an oversight): /reminders/deliver is NOT rate-limited here. It is
already cryptographically authenticated by its QStash HMAC signature (fail-closed since
Phase 3), so a limiter adds no security — while failing closed on it WOULD convert a Redis
blip into silently-dropped user reminders. Documented in PROGRESS §2 4.5 for the critic.
"""

import logging
import time
from typing import Optional

from fastapi import HTTPException, Request, status

from .redis_client import redis_client

logger = logging.getLogger(__name__)


def _client_ip(request: Request) -> str:
    """
    Caller identity for the limit bucket. MUST be a value the client cannot forge, or the
    limiter is worthless — a client that controls its own bucket key just rotates it and gets
    infinite buckets.

    Our services sit behind Cloudflare (confirmed live: responses carry `cf-ray` /
    `server: cloudflare`). `CF-Connecting-IP` is set BY Cloudflare to the real connecting
    client and OVERWRITES any client-supplied copy — so it is trustworthy end-to-end.

    Why NOT `X-Forwarded-For[0]` (the previous, wrong choice): Cloudflare APPENDS the real IP
    to any client-sent XFF, so the LEFTMOST entry is attacker-controlled. Keying on it let an
    attacker send a fresh `X-Forwarded-For:` per request and evade every limit. That was a
    real bypass, caught by the Phase-4 critic.

    Fallbacks, in order: CF-Connecting-IP → True-Client-IP (Cloudflare Enterprise alias) →
    socket peer. We deliberately do NOT trust raw XFF. Residual: a request reaching the
    origin DIRECTLY (via the *.onrender.com host, bypassing Cloudflare) could spoof
    CF-Connecting-IP — but the limiter is defense-in-depth (admin also has API_SECRET_KEY;
    the callback also has the single-use CSPRNG state), and the direct-origin path is a
    separate hardening item, not a limiter bypass we can close from here.
    """
    cf_ip = request.headers.get("cf-connecting-ip") or request.headers.get("true-client-ip")
    if cf_ip:
        cf_ip = cf_ip.strip()
        if cf_ip:
            return cf_ip
    return request.client.host if request.client else "unknown"


async def enforce_rate_limit(
    request: Request,
    bucket: str,
    limit: int,
    window_seconds: int,
    identity: Optional[str] = None,
) -> None:
    """
    Fixed-window counter. Raises 429 when over the limit, 503 when Redis is unavailable.

    Fixed-window (not sliding) is intentional: it costs ONE round-trip, and its known
    weakness — up to 2x the limit across a window boundary — is irrelevant at these limits.
    We are stopping enumeration and abuse, not metering billing.
    """
    ident = identity or _client_ip(request)
    window = int(time.time()) // window_seconds
    key = f"ratelimit:{bucket}:{ident}:{window}"

    if not redis_client.is_connected:
        logger.error(
            "Rate limiter FAILING CLOSED for bucket=%s — Redis unavailable. "
            "Denying rather than serving unlimited.", bucket
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiter unavailable",
        )

    try:
        count = redis_client._redis.incr(key)
        if count == 1:
            # First hit in this window — set the TTL so the key self-expires.
            redis_client._redis.expire(key, window_seconds)
    except Exception as e:
        logger.error("Rate limiter FAILING CLOSED for bucket=%s — Redis error: %s", bucket, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiter unavailable",
        )

    if count > limit:
        logger.warning(
            "Rate limit exceeded: bucket=%s identity=%s count=%s limit=%s",
            bucket, ident, count, limit,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
            headers={"Retry-After": str(window_seconds)},
        )


# ── Route-specific dependencies ───────────────────────────────────────────────
#
# Limits are generous enough that no legitimate caller can hit them, and tight enough to
# make enumeration/brute-force pointless.

async def limit_oauth_callback(request: Request) -> None:
    """
    Public (Google redirects the user's BROWSER here) — the one route an anonymous attacker
    can hit that consumes Redis lookups and does crypto work. 30/min per IP: a real user
    completes this once per connect; 30 is ~2 orders of magnitude of headroom, while
    brute-forcing a 256-bit CSPRNG `state` at 30/min is hopeless (as it already was).
    """
    await enforce_rate_limit(request, "oauth_callback", limit=30, window_seconds=60)


async def limit_oauth_init(request: Request) -> None:
    """Service-key gated (Phase 1), but it mints Redis state + hits Google. 60/min per IP."""
    await enforce_rate_limit(request, "oauth_init", limit=60, window_seconds=60)


async def limit_admin(request: Request) -> None:
    """
    Admin bearer-token gate (CASA 1.1.1 — brute-force resistance on an authN endpoint).
    Deliberately tight: 20/min per IP. Real admin usage is a handful of calls; a credential
    brute-force needs millions.
    """
    await enforce_rate_limit(request, "admin", limit=20, window_seconds=60)
