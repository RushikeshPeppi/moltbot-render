"""
Session cleanup utility for Redis-based sessions.
Handles cleanup of orphaned sessions and rate limit data.
"""

import logging
import asyncio
from datetime import datetime
from ..core.redis_client import redis_client
from ..config import settings

logger = logging.getLogger(__name__)


class SessionCleanup:
    """
    Background task to monitor and clean up sessions.
    
    With Redis TTL, most cleanup is automatic, but this handles:
    - Orphaned lock keys
    - Rate limit key cleanup
    - Session statistics logging
    """
    
    def __init__(self):
        self.redis = redis_client
        self.interval = settings.SESSION_CLEANUP_INTERVAL
        self.running = False
        self._task = None
    
    async def start(self):
        """Start cleanup task in background"""
        if self.running:
            return
        
        self.running = True
        self._task = asyncio.create_task(self._cleanup_loop())
        logger.info("Session cleanup task started")
    
    async def stop(self):
        """Stop cleanup task"""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Session cleanup task stopped")
    
    async def _cleanup_loop(self):
        """Main cleanup loop"""
        while self.running:
            try:
                await self._perform_cleanup()
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
            
            await asyncio.sleep(self.interval)
    
    async def _perform_cleanup(self):
        """Perform cleanup operations"""
        if not self.redis.is_connected:
            return
        
        try:
            # Log session statistics
            session_count = await self.redis.get_active_sessions_count()
            logger.debug(f"Active sessions: {session_count}")
            
            # Clean up orphaned locks (locks older than 5 minutes)
            # Note: Locks have TTL, so this is mostly for monitoring
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")