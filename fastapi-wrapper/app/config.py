from pydantic_settings import BaseSettings
from typing import Optional, List
import os

class Settings(BaseSettings):
    """Application settings for Render with Upstash Redis and Supabase"""
    
    # API Settings
    APP_NAME: str = "Moltbot Wrapper API"
    API_VERSION: str = "v1"
    DEBUG: bool = False
    
    # Moltbot Gateway. HTTPS-only default: the Google access token is sent to the
    # gateway in the request body (core/moltbot_client.py), so a plaintext http://
    # default is a token-disclosure risk if the env var is ever missing (CASA 4.1.1).
    MOLTBOT_GATEWAY_URL: str = os.getenv("MOLTBOT_GATEWAY_URL", "https://openclaw-gateway-dg3y.onrender.com")
    # Must exceed the gateway's longest internal skill timeout (320s post-2026-04-28
    # bump — heavy web-search compounds on cold-cache observed at 262s in prod).
    # Render Pro caps a single HTTP request at 600s, so 360s leaves comfortable
    # margin for FastAPI processing on top of the gateway budget.
    MOLTBOT_TIMEOUT: int = 360
    
    # Upstash Redis
    UPSTASH_REDIS_URL: str = os.getenv("UPSTASH_REDIS_URL", "")
    UPSTASH_REDIS_TOKEN: str = os.getenv("UPSTASH_REDIS_TOKEN", "")
    
    # Session Settings (Redis-based)
    SESSION_TTL: int = 3600  # 1 hour
    SESSION_CLEANUP_INTERVAL: int = 300  # 5 minutes
    MAX_CONVERSATION_HISTORY: int = 50  # Keep last N messages
    
    # Supabase Database
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    
    # Encryption. ENCRYPTION_KEY is the PRIMARY key — everything is encrypted with it.
    # ENCRYPTION_KEYS_OLD is an optional comma-separated list of RETIRED keys kept only
    # so previously-stored tokens still decrypt during a rotation (MultiFernet keyring,
    # core/database.py). Rotation procedure: prepend the old primary to
    # ENCRYPTION_KEYS_OLD, set the new key as ENCRYPTION_KEY, redeploy, re-encrypt, then
    # drop the retired key. Without this, rotating ENCRYPTION_KEY silently makes every
    # stored Google token undecryptable (CASA 6.7.1 / ASVS 6.2.4 crypto agility).
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")
    ENCRYPTION_KEYS_OLD: str = os.getenv("ENCRYPTION_KEYS_OLD", "")
    
    # Google OAuth
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "")
    GOOGLE_SCOPES: List[str] = [
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send"
    ]
    
    # Rate Limiting
    FREE_TIER_DAILY_LIMIT: int = 50
    PREMIUM_TIER_DAILY_LIMIT: int = 500
    
    # Security
    API_SECRET_KEY: str = os.getenv("API_SECRET_KEY", "")
    # Shared service-to-service secret. Trusted internal callers (Peppi Laravel,
    # the gateway) must present it in the X-Moltbot-Key header. Guarded routes
    # fail CLOSED (503) when this is unset — never open. Must be IDENTICAL across
    # moltbot-fastapi, the gateway, and Peppi Laravel.
    INTERNAL_SERVICE_KEY: str = os.getenv("INTERNAL_SERVICE_KEY", "")

    # CORS allow-list (CASA 6.3.1 / P2-1). Was `["*"]` with allow_credentials=True.
    # Every route that touches user data now requires the X-Moltbot-Key service
    # header (Phase 1), which no browser can safely hold — so there is NO legitimate
    # cross-origin browser caller, and the correct default is DENY-ALL (empty list).
    # Comma-separated exact origins if one is ever needed (e.g. a future first-party
    # SPA fronted by a server that injects the key).
    ALLOWED_ORIGINS_RAW: str = os.getenv("ALLOWED_ORIGINS", "")

    @property
    def ALLOWED_ORIGINS(self) -> List[str]:
        """Explicit origin allow-list; empty = no cross-origin browser access."""
        return [o.strip() for o in self.ALLOWED_ORIGINS_RAW.split(",") if o.strip()]

    # Max accepted request body (CASA 5.1.x resource-exhaustion). Matches the
    # gateway's express.json({limit:"5mb"}) so the two tiers agree. Enforced by
    # core/body_limit.py at the ASGI layer — before any handler buffers the body.
    MAX_REQUEST_BODY_BYTES: int = int(os.getenv("MAX_REQUEST_BODY_BYTES", str(5 * 1024 * 1024)))

    # OAuth open-redirect allow-list (CASA 3.2.2). Comma-separated EXACT origins
    # (scheme://host[:port]) we are willing to 302 a user back to after the OAuth
    # callback. When set it REPLACES the built-in Peppi default set in
    # core/redirect_validation.py; empty = use that default. PEPPI_WEBSITE_URL's
    # origin is always trusted regardless.
    OAUTH_ALLOWED_REDIRECT_ORIGINS: str = os.getenv("OAUTH_ALLOWED_REDIRECT_ORIGINS", "")

    # Peppi Website. Default is peppi.ai — the LIVE product origin.
    # Was `https://peppi.app` until 2026-07-16: peppi.app has **no A record** (verified
    # `dig +short peppi.app A` → empty), so every OAuth error/expired-state callback was
    # 307'ing users to a browser DNS error instead of an error page. This value is also
    # the callback's safe-default target (api/oauth.py) AND is auto-trusted into the
    # redirect allow-list (core/redirect_validation.py), so a dead value here breaks the
    # fallback the whole allow-list design rests on. Keep it pointed at a LIVE origin.
    PEPPI_WEBSITE_URL: str = os.getenv("PEPPI_WEBSITE_URL", "https://peppi.ai")
    
    # Upstash QStash (Reminder Scheduling)
    QSTASH_URL: str = os.getenv("QSTASH_URL", "")
    QSTASH_TOKEN: str = os.getenv("QSTASH_TOKEN", "")
    QSTASH_CURRENT_SIGNING_KEY: str = os.getenv("QSTASH_CURRENT_SIGNING_KEY", "")
    QSTASH_NEXT_SIGNING_KEY: str = os.getenv("QSTASH_NEXT_SIGNING_KEY", "")
    
    # Peppi Outbound SMS
    PEPPI_OUTBOUND_URL: str = os.getenv("PEPPI_OUTBOUND_URL", "")
    PEPPI_OUTBOUND_API_KEY: str = os.getenv("PEPPI_OUTBOUND_API_KEY", "")
    
    # Moltbot FastAPI Public URL (for QStash webhook callbacks)
    MOLTBOT_PUBLIC_URL: str = os.getenv("MOLTBOT_PUBLIC_URL", "https://moltbot-fastapi.onrender.com")
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "/tmp/logs"
    
    # Render specific
    PORT: int = int(os.getenv("PORT", "8000"))
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()

# Create log directory
os.makedirs(settings.LOG_DIR, exist_ok=True)
