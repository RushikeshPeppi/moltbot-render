from pydantic_settings import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    """Application settings for Render"""
    
    # API Settings
    APP_NAME: str = "Moltbot Wrapper API"
    API_VERSION: str = "v1"
    DEBUG: bool = False
    
    # Moltbot Gateway (will be internal Render service)
    MOLTBOT_GATEWAY_URL: str = os.getenv("MOLTBOT_GATEWAY_URL", "http://moltbot-gateway:18789")
    MOLTBOT_TIMEOUT: int = 60
    
    # Session Management (using Render disk)
    SESSION_DIR: str = "/data/sessions/active"
    SESSION_ARCHIVE_DIR: str = "/data/sessions/archived"
    SESSION_TTL: int = 3600
    SESSION_CLEANUP_INTERVAL: int = 300
    
    # Credentials (using Render disk)
    CREDENTIALS_DIR: str = "/data/credentials"
    ENCRYPTION_KEY: str
    
    # Security
    API_SECRET_KEY: str
    ALLOWED_ORIGINS: list = ["*"]
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "/data/logs"
    
    # Render specific
    PORT: int = int(os.getenv("PORT", "8000"))
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()

# Create directories on startup
for directory in [
    settings.SESSION_DIR,
    settings.SESSION_ARCHIVE_DIR,
    settings.CREDENTIALS_DIR,
    settings.LOG_DIR
]:
    os.makedirs(directory, exist_ok=True)