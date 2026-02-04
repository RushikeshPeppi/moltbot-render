from pydantic_settings import BaseSettings
from typing import Optional, List
import os

class Settings(BaseSettings):
    """Application settings for Render with Upstash Redis and MySQL"""
    
    # API Settings
    APP_NAME: str = "Moltbot Wrapper API"
    API_VERSION: str = "v1"
    DEBUG: bool = False
    
    # Moltbot Gateway
    MOLTBOT_GATEWAY_URL: str = os.getenv("MOLTBOT_GATEWAY_URL", "http://moltbot-gateway:18789")
    MOLTBOT_TIMEOUT: int = 60
    
    # Upstash Redis
    UPSTASH_REDIS_URL: str = os.getenv("UPSTASH_REDIS_URL", "")
    UPSTASH_REDIS_TOKEN: str = os.getenv("UPSTASH_REDIS_TOKEN", "")
    
    # Session Settings (Redis-based)
    SESSION_TTL: int = 3600  # 1 hour
    SESSION_CLEANUP_INTERVAL: int = 300  # 5 minutes
    MAX_CONVERSATION_HISTORY: int = 50  # Keep last N messages
    
    # MySQL Database
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "dashtech_peppi")
    MYSQL_USERNAME: str = os.getenv("MYSQL_USERNAME", "dashtech_peppi")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_POOL_SIZE: int = 5
    MYSQL_POOL_RECYCLE: int = 3600
    
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
