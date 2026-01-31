import os
import time
from datetime import datetime
import asyncio
from ..config import settings
import logging

logger = logging.getLogger(__name__)

class SessionCleanup:
    """Background task to clean up old sessions"""
    
    def __init__(self):
        self.session_dir = settings.SESSION_DIR
        self.archive_dir = settings.SESSION_ARCHIVE_DIR
        self.interval = settings.SESSION_CLEANUP_INTERVAL
        self.running = False
    
    async def start(self):
        """Start cleanup task"""
        self.running = True
        while self.running:
            await self.cleanup()
            await asyncio.sleep(self.interval)
    
    async def cleanup(self):
        """Clean up expired sessions"""
        try:
            now = datetime.utcnow()
            cleaned = 0
            
            for filename in os.listdir(self.session_dir):
                if not filename.endswith('.json'):
                    continue
                
                filepath = os.path.join(self.session_dir, filename)
                
                # Check file age
                file_age = time.time() - os.path.getmtime(filepath)
                
                if file_age > settings.SESSION_TTL:
                    # Archive old session
                    archive_path = os.path.join(
                        self.archive_dir,
                        f"{filename.replace('.json', '')}_{int(time.time())}.json"
                    )
                    os.rename(filepath, archive_path)
                    cleaned += 1
            
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} expired sessions")
        
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def stop(self):
        """Stop cleanup task"""
        self.running = False