import json
import os
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import aiofiles
from ..config import settings
import logging

logger = logging.getLogger(__name__)

class SessionManager:
    """File-based session manager for Render disk storage"""
    
    def __init__(self):
        self.session_dir = settings.SESSION_DIR
        self.archive_dir = settings.SESSION_ARCHIVE_DIR
        self.ttl = settings.SESSION_TTL
    
    async def create_session(self, user_id: str) -> str:
        """Create new session for user"""
        session_id = f"user_{user_id}_{uuid.uuid4().hex[:8]}"
        
        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat(),
            "last_activity": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(seconds=self.ttl)).isoformat(),
            "conversation_history": [],
            "context": {
                "pending_action": None,
                "last_action": None,
                "user_timezone": "America/New_York"
            }
        }
        
        # Save session file
        session_path = os.path.join(self.session_dir, f"{session_id}.json")
        async with aiofiles.open(session_path, 'w') as f:
            await f.write(json.dumps(session_data, indent=2))
        
        logger.info(f"Created session: {session_id} for user: {user_id}")
        return session_id
    
    async def get_session(self, session_id: str) -> Optional[Dict]:
        """Retrieve session data"""
        session_path = os.path.join(self.session_dir, f"{session_id}.json")
        
        if not os.path.exists(session_path):
            logger.warning(f"Session not found: {session_id}")
            return None
        
        try:
            async with aiofiles.open(session_path, 'r') as f:
                content = await f.read()
                session_data = json.loads(content)
            
            # Check if expired
            expires_at = datetime.fromisoformat(session_data['expires_at'])
            if datetime.utcnow() > expires_at:
                logger.info(f"Session expired: {session_id}")
                await self.delete_session(session_id)
                return None
            
            return session_data
        except Exception as e:
            logger.error(f"Error reading session {session_id}: {e}")
            return None
    
    async def update_session(self, session_id: str, data: Dict) -> bool:
        """Update session data"""
        session_path = os.path.join(self.session_dir, f"{session_id}.json")
        
        try:
            # Update last activity and expiry
            data['last_activity'] = datetime.utcnow().isoformat()
            data['expires_at'] = (datetime.utcnow() + timedelta(seconds=self.ttl)).isoformat()
            
            async with aiofiles.open(session_path, 'w') as f:
                await f.write(json.dumps(data, indent=2))
            
            return True
        except Exception as e:
            logger.error(f"Error updating session {session_id}: {e}")
            return False
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete session and archive it"""
        session_path = os.path.join(self.session_dir, f"{session_id}.json")
        archive_path = os.path.join(self.archive_dir, f"{session_id}_{int(time.time())}.json")
        
        try:
            if os.path.exists(session_path):
                # Move to archive
                os.rename(session_path, archive_path)
                logger.info(f"Archived session: {session_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting session {session_id}: {e}")
            return False
    
    async def add_message(self, session_id: str, role: str, content: str) -> bool:
        """Add message to conversation history"""
        session_data = await self.get_session(session_id)
        if not session_data:
            return False
        
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        session_data['conversation_history'].append(message)
        return await self.update_session(session_id, session_data)
    
    async def get_active_sessions_count(self) -> int:
        """Count active sessions"""
        try:
            files = os.listdir(self.session_dir)
            return len([f for f in files if f.endswith('.json')])
        except Exception as e:
            logger.error(f"Error counting sessions: {e}")
            return 0