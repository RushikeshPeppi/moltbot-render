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
from .core.database import db
from .core.redis_client import redis_client

# Setup logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# Also log to file if directory exists
try:
    file_handler = logging.FileHandler(f"{settings.LOG_DIR}/app.log")
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logging.getLogger().addHandler(file_handler)
except Exception:
    pass

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

# Include routes
app.include_router(routes.router, prefix=f"/api/{settings.API_VERSION}")
app.include_router(oauth.router, prefix=f"/api/{settings.API_VERSION}")
app.include_router(google_services.router, prefix=f"/api/{settings.API_VERSION}")
app.include_router(reminders.router, prefix=f"/api/{settings.API_VERSION}")
app.include_router(outbound.router, prefix=f"/api/{settings.API_VERSION}")


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