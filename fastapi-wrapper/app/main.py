"""
Main FastAPI application with lifespan management.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from .config import settings
from .api import routes
from .api import oauth
from .api import google_services
from .api import reminders
from .api import outbound
from .api import playground
from .core.database import db
from .core.redis_client import redis_client

# Setup logging — structured format with ISO-8601 dates for Render log viewer
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events"""
    logger.info("Starting Moltbot Wrapper API...")
    
    # Initialize database connection pool
    try:
        await db.initialize()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        # Continue anyway - database might not be configured yet
    
    # Check Redis connection
    if redis_client.is_connected:
        logger.info("Redis connected")
    else:
        logger.warning("Redis not configured - sessions will not persist")
    
    yield
    
    # Cleanup
    logger.info("Shutting down Moltbot Wrapper API...")
    await db.close()


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.API_VERSION,
    description="Multi-tenant Moltbot wrapper API for Peppi SMS platform",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request Payload Logging + JSON Control Char Fix Middleware ──
import json as _json
import time as _time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Fields to redact from logged payloads (case-insensitive partial match)
_SENSITIVE_KEYS = {
    "token", "access_token", "refresh_token", "google_access_token",
    "google_token", "api_key", "api_secret", "secret", "password",
    "credentials", "encryption_key", "authorization", "cookie",
}

_req_logger = logging.getLogger("api.requests")


def _redact_payload(obj, max_str_len=500):
    """
    Deep-copy a parsed JSON payload with sensitive fields redacted
    and long strings truncated, so it's safe to log.
    """
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k.lower() in _SENSITIVE_KEYS:
                out[k] = "***REDACTED***"
            elif k == "history" and isinstance(v, list):
                out[k] = f"[{len(v)} messages]"
            else:
                out[k] = _redact_payload(v, max_str_len)
        return out
    elif isinstance(obj, list):
        if len(obj) > 10:
            return [_redact_payload(obj[0], max_str_len), f"...({len(obj)} items total)"]
        return [_redact_payload(item, max_str_len) for item in obj]
    elif isinstance(obj, str) and len(obj) > max_str_len:
        return obj[:max_str_len] + f"...({len(obj)} chars)"
    return obj


# Paths to skip logging for (health checks, static, docs)
_SKIP_LOG_PATHS = {"/health", "/", "/docs", "/openapi.json", "/redoc", "/favicon.ico"}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Combined middleware that:
    1. Fixes raw control characters in JSON bodies (original JsonControlCharMiddleware)
    2. Logs every request payload (redacted) and response status to stdout
    """
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method
        start = _time.monotonic()

        parsed_body = None

        # Only process JSON bodies for POST/PUT/PATCH
        if method in ("POST", "PUT", "PATCH") and \
           "application/json" in (request.headers.get("content-type") or ""):
            body = await request.body()
            try:
                parsed_body = _json.loads(body.decode("utf-8"), strict=False)
                # Re-serialize to fix control characters (original middleware logic)
                fixed = _json.dumps(parsed_body).encode("utf-8")

                async def receive():
                    return {"type": "http.request", "body": fixed}
                request._receive = receive
            except (_json.JSONDecodeError, UnicodeDecodeError):
                pass  # let FastAPI handle the original error

        # Log the request (skip health checks and docs)
        if path not in _SKIP_LOG_PATHS:
            log_parts = [f"→ {method} {path}"]

            # Add query params if present
            if request.url.query:
                log_parts.append(f"  query: {request.url.query}")

            # Add redacted payload for POST/PUT/PATCH
            if parsed_body is not None:
                safe = _redact_payload(parsed_body)
                log_parts.append(f"  payload: {_json.dumps(safe, indent=2, default=str)}")

            _req_logger.info("\n".join(log_parts))

        # Execute the actual request
        response = await call_next(request)

        # Log the response status and timing
        duration_ms = (_time.monotonic() - start) * 1000
        if path not in _SKIP_LOG_PATHS:
            _req_logger.info(f"← {method} {path} → {response.status_code} ({duration_ms:.0f}ms)")

        return response


app.add_middleware(RequestLoggingMiddleware)


# Include routes
app.include_router(routes.router, prefix=f"/api/{settings.API_VERSION}")
app.include_router(oauth.router, prefix=f"/api/{settings.API_VERSION}")
app.include_router(google_services.router, prefix=f"/api/{settings.API_VERSION}")
app.include_router(reminders.router, prefix=f"/api/{settings.API_VERSION}")
app.include_router(outbound.router, prefix=f"/api/{settings.API_VERSION}")
app.include_router(playground.router, prefix=f"/api/{settings.API_VERSION}")


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API info"""
    return {
        "status": "online",
        "service": settings.APP_NAME,
        "version": settings.API_VERSION,
        "docs": "/docs"
    }


# Health check at root level
@app.get("/health")
async def health_check():
    """Simple health check for Render"""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.API_VERSION
    }