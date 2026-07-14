"""
Request-body size cap (CASA 5.1.x — resource exhaustion / memory-exhaustion DoS).

Finding (second audit): `main.py` read `await request.body()` on every POST/PUT/PATCH with
NO size cap, so a single large body could exhaust the dyno's memory. The gateway already
caps at 5 MB (`express.json({limit:"5mb"})`); FastAPI did not — the two tiers disagreed.

Two independent gates, because either alone leaks:
  1. Declared Content-Length > cap → reject without reading a byte.
  2. Actual bytes read > cap       → reject mid-read. This is the one that matters: a
     chunked body carries NO Content-Length (gate 1 is blind to it), and a lying
     Content-Length is just as cheap to send as an honest one.

Fail-closed: a malformed or negative Content-Length is rejected (400), never waved through.

WHY BUFFER-AND-REPLAY, NOT RAISE-FROM-RECEIVE (do not "simplify" this back):
The obvious implementation wraps `receive` and raises a custom exception when the running
byte-count exceeds the cap. It does not work here, and the contract test proves it: the
downstream BaseHTTPMiddleware instances (RequestLoggingMiddleware, IdempotencyMiddleware)
pump `receive` inside an anyio task group, which bundles anything raised there into an
ExceptionGroup. The `except` in this module never matches, and the request 500s instead of
returning 413 — a fail-OPEN cap that looks correct in code review.

So we consume the body HERE, bounded by the cap, and replay the buffered bytes downstream
via a replacement `receive`. Peak memory is bounded by max_bytes (5 MB) — which is precisely
the guarantee the cap exists to make — and no exception ever crosses a task-group boundary.
Buffering costs nothing extra in practice: RequestLoggingMiddleware already called
`await request.body()` on every JSON request, so the body was fully buffered regardless.
"""

import json

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") not in _BODY_METHODS:
            await self.app(scope, receive, send)
            return

        # ── Gate 1: declared size. Reject before reading anything. ──
        content_length = Headers(scope=scope).get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                await self._reject(send, 400, "MALFORMED_CONTENT_LENGTH")
                return
            if declared < 0:
                # Negative Content-Length is nonsense and has been used to defeat naive
                # caps (cf. python-multipart CVE-2026-53540). Fail closed.
                await self._reject(send, 400, "MALFORMED_CONTENT_LENGTH")
                return
            if declared > self.max_bytes:
                await self._reject(send, 413, "REQUEST_BODY_TOO_LARGE")
                return

        # ── Gate 2: actual size. Catches chunked bodies and a lying Content-Length. ──
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()

            if message["type"] == "http.disconnect":
                # Client vanished mid-upload. Hand the disconnect to the app and stop.
                await self.app(scope, _once(message), send)
                return

            chunk = message.get("body", b"")
            if chunk:
                size += len(chunk)
                if size > self.max_bytes:
                    # Stop reading immediately — do not drain the rest of the attacker's
                    # body. Nothing has been sent downstream, so we own the response.
                    await self._reject(send, 413, "REQUEST_BODY_TOO_LARGE")
                    return
                chunks.append(chunk)

            if not message.get("more_body", False):
                break

        body = b"".join(chunks)
        await self.app(scope, _replay(body), send)

    async def _reject(self, send: Send, status: int, error: str) -> None:
        payload = json.dumps({
            "code": status,
            "message": "Request body too large" if status == 413 else "Malformed request",
            "data": None,
            "error": error,
            "exception": None,
        }).encode()
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": payload})


def _replay(body: bytes) -> Receive:
    """A `receive` that hands the buffered body downstream exactly once."""
    sent = False

    async def receive() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return receive


def _once(message: Message) -> Receive:
    """A `receive` that replays a single already-consumed message."""
    sent = False

    async def receive() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return message
        return {"type": "http.disconnect"}

    return receive
