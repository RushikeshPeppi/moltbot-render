"""
Idempotency middleware — honors `X-Idempotency-Key` on whitelisted POST endpoints.

Why this exists:
  The moltbot-gateway (TypeScript SDK) computes a deterministic SHA-256 key for
  every write tool call from (userId, requestId, op, stable_args) and sends it
  as `X-Idempotency-Key`. Without server-side honoring, that header is just bytes.

What it catches:
  - In-flight retries where the same key arrives twice within the cache TTL
    (e.g., a model emitting parallel duplicate tool_use blocks; future
    gateway-side fetch retry on transient 5xx).

What it does NOT replace:
  - The time-based heuristic dedup inside `reminders.create_reminder` — that
    handles the user-fast-retry case where requestId differs but trigger
    time + message match. Both layers stay; this one is faster and stricter.

Design notes:
  - Whitelist by path. Only writes that the gateway flags with X-Idempotency-Key
    get this treatment — list/get endpoints pass through.
  - Cache only application-success responses (2xx + body has no `error` field).
    Caching app-level errors would silently mask transient problems on retry.
  - Cap cached body size to avoid Redis bloat.
  - Fall back to pass-through if Redis is down. Idempotency is an optimization,
    not a safety property here — the time-based dedup still protects the DB.
"""
from __future__ import annotations

import json
import logging
from typing import Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# POST endpoints that honor the header. Keep narrow — only writes that the
# gateway actually keys (see moltbot-gateway/src/tools/reminders.ts).
IDEMPOTENT_PATHS: Set[str] = {
    "/api/v1/reminders/create",
    "/api/v1/reminders/update",
    "/api/v1/reminders/cancel",
}

# 5 minutes. Long enough to cover a tool-call retry cycle; short enough that a
# legitimate "same reminder, different intent" 6 minutes later still goes through.
CACHE_TTL_SECONDS = 300

# Don't cache responses larger than this — guards Redis from a misbehaving handler.
MAX_CACHE_BYTES = 64 * 1024


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method != "POST" or request.url.path not in IDEMPOTENT_PATHS:
            return await call_next(request)

        key = (request.headers.get("x-idempotency-key") or "").strip()
        if not key:
            return await call_next(request)

        # Lazy import to avoid module-load circularity with the singleton.
        from ..core.redis_client import redis_client

        if not redis_client.is_connected:
            return await call_next(request)

        cache_key = f"idem:{request.url.path}:{key}"

        # Hit path — return the cached response verbatim.
        try:
            cached = await redis_client.get(cache_key)
            if isinstance(cached, dict) and "body" in cached and "status" in cached:
                logger.info(
                    "idempotency hit path=%s key=%s...",
                    request.url.path, key[:8],
                )
                return JSONResponse(content=cached["body"], status_code=cached["status"])
        except Exception as e:
            logger.warning("idempotency cache read failed: %s", e)

        # Miss path — pass through, then capture response for caching.
        response = await call_next(request)

        body_chunks = []
        async for chunk in response.body_iterator:
            body_chunks.append(chunk)
        body_bytes = b"".join(body_chunks)

        # Cache only on HTTP 2xx + app-level success (no error field) + size cap.
        if (
            200 <= response.status_code < 300
            and len(body_bytes) <= MAX_CACHE_BYTES
        ):
            try:
                body_json = json.loads(body_bytes)
                if isinstance(body_json, dict) and not body_json.get("error"):
                    await redis_client.set(
                        cache_key,
                        {"body": body_json, "status": response.status_code},
                        ttl=CACHE_TTL_SECONDS,
                    )
                    logger.debug(
                        "idempotency cached path=%s key=%s...",
                        request.url.path, key[:8],
                    )
            except json.JSONDecodeError:
                # Non-JSON response — don't cache, let it through.
                pass
            except Exception as e:
                logger.warning("idempotency cache write failed: %s", e)

        # Reconstruct response. Drop content-length — framework recomputes it.
        rebuilt_headers = {
            k: v for k, v in response.headers.items()
            if k.lower() != "content-length"
        }
        return Response(
            content=body_bytes,
            status_code=response.status_code,
            headers=rebuilt_headers,
            media_type=response.media_type,
        )
