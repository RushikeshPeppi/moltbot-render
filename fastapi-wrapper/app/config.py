from pydantic_settings import BaseSettings
from typing import Optional, List
import os

class Settings(BaseSettings):
    """Application settings for Render with Upstash Redis and Supabase"""
    
    # API Settings
    APP_NAME: str = "Moltbot Wrapper API"
    API_VERSION: str = "v1"
    DEBUG: bool = False
    
    # Moltbot Gateway
    MOLTBOT_GATEWAY_URL: str = os.getenv("MOLTBOT_GATEWAY_URL", "http://moltbot-gateway:18789")
    MOLTBOT_TIMEOUT: int = 130  # Must exceed gateway's 120s internal timeout for skill execution
    
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
    
    # Encryption
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")
    
    # Google OAuth
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "")
    GOOGLE_SCOPES: List[str] = [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send"
    ]
    
    # Rate Limiting
    FREE_TIER_DAILY_LIMIT: int = 50
    PREMIUM_TIER_DAILY_LIMIT: int = 500
    
    # Security
    API_SECRET_KEY: str = os.getenv("API_SECRET_KEY", "")
    ALLOWED_ORIGINS: List[str] = ["*"]
    
    # Peppi Website
    PEPPI_WEBSITE_URL: str = os.getenv("PEPPI_WEBSITE_URL", "https://peppi.app")
    
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
