"""
Inter-service bearer-secret auth.

Every request from Peppi → wrapper, wrapper → gateway, and gateway → wrapper's
/oauth/google/token endpoint must carry:
    Authorization: Bearer <MOLTBOT_INTERNAL_SECRET>

In ENV=production this is enforced. In ENV=staging or ENV=dev a missing secret
is tolerated so engineers can run the stack locally without the shared env var,
but a present-but-wrong secret still fails. This gives us fail-safe behaviour
without requiring every developer to set the env.
"""
import hmac
import logging
from typing import Optional

from fastapi import Header, HTTPException, status

from ..config import settings

logger = logging.getLogger(__name__)


def _expected() -> str:
    return settings.MOLTBOT_INTERNAL_SECRET or ""


def _compare(supplied: str, expected: str) -> bool:
    # Constant-time comparison to avoid timing side-channels.
    return hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))


async def require_internal_secret(
    authorization: Optional[str] = Header(default=None),
) -> None:
    """
    FastAPI dependency: require Authorization: Bearer <MOLTBOT_INTERNAL_SECRET>.

    Semantics by environment:
      - production:            secret must be set AND request must match.
      - staging/dev/anything:  if secret is not configured, allow through (so
                               local dev works); if secret IS configured, the
                               request must match (no fail-open on wrong value).
    """
    expected = _expected()
    env = (settings.ENV or "production").lower()

    if not expected:
        if env == "production":
            # Refuse to serve production requests without a configured secret —
            # that would mean *every* caller is trusted, which is never right.
            logger.error(
                "MOLTBOT_INTERNAL_SECRET is not configured in production. "
                "Refusing to serve authenticated endpoints."
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="inter-service auth not configured",
            )
        # dev/staging without a secret: allow through, but log once per request
        # so it's visible in CI output.
        logger.debug("MOLTBOT_INTERNAL_SECRET not set; skipping auth check (ENV=%s)", env)
        return

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    supplied = authorization.split(" ", 1)[1].strip()
    if not _compare(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
