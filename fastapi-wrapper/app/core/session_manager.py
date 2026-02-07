"""
Redis-backed Session Manager for multi-tenant session isolation.
Replaces file-based storage with Upstash Redis for production scalability.
"""

import json
import uuid
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from .redis_client import redis_client
from ..config import settings

logger = logging.getLogger(__name__)


class SessionManager:
    """Upstash Redis-backed session manager with multi-tenant isolation"""
    
    def __init__(self):
        self.redis = redis_client
        self.ttl = settings.SESSION_TTL
        self.max_history = settings.MAX_CONVERSATION_HISTORY
    
    async def create_session(self, user_id: str) -> str:
        """Create new session for user. Returns existing active session if one exists."""
        
        # Check for existing active session
        existing = await self.get_active_session_for_user(user_id)
        if existing:
            logger.info(f"Reusing existing session for user {user_id}: {existing}")
            # Refresh TTL
            await self.redis.refresh_session_ttl(user_id, existing)
            return existing
        
        # Create new session
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        
        session_data = {
            "session_id": session_id,
            "user_id": str(user_id),
            "created_at": datetime.utcnow().isoformat(),
            "last_activity": datetime.utcnow().isoformat(),
            "conversation_history": [],
            "context": {
                "pending_action": None,
                "last_action": None,
                "user_timezone": "UTC"
            },
            "user_context": {
                "bot_name": None,  # Custom name given by user to the bot
                "user_name": None,  # User's real name
                "preferences": None,  # User-specific preferences/notes
                "relationship": "assistant"  # Default relationship type
            },
            "metadata": {
                "message_count": 0,
                "total_tokens": 0
            }
        }
        
        success = await self.redis.set_session(user_id, session_id, session_data, self.ttl)
        
        if success:
            logger.info(f"Created session: {session_id} for user: {user_id}")
            return session_id
        else:
            logger.error(f"Failed to create session for user: {user_id}")
            raise Exception("Failed to create session")
    
    async def get_session(self, session_id: str, user_id: str = None) -> Optional[Dict[str, Any]]:
        """Retrieve session data"""
        if not user_id:
            # Extract user_id from session_id pattern if stored
            logger.warning("user_id not provided, session lookup may fail")
            return None
        
        data = await self.redis.get_session(user_id, session_id)
        
        if data:
            # Refresh TTL on access (sliding expiration)
            await self.redis.refresh_session_ttl(user_id, session_id)
        
        return data
    
    async def get_active_session_for_user(self, user_id: str) -> Optional[str]:
        """Get the most recent active session for a user"""
        sessions = await self.redis.get_user_sessions(user_id)
        
        if not sessions:
            return None
        
        # Return the first (most recent) session
        # Sessions are stored as "session:{user_id}:{session_id}"
        for key in sessions:
            parts = key.split(":")
            if len(parts) >= 3:
                return parts[2]  # session_id
        
        return None
    
    async def update_session(self, session_id: str, user_id: str, data: Dict[str, Any]) -> bool:
        """Update session data"""
        # Update timestamps
        data['last_activity'] = datetime.utcnow().isoformat()
        
        return await self.redis.set_session(user_id, session_id, data, self.ttl)
    
    async def delete_session(self, session_id: str, user_id: str) -> bool:
        """Delete a session"""
        return await self.redis.delete_session(user_id, session_id)
    
    async def add_message(
        self, 
        session_id: str, 
        user_id: str,
        role: str, 
        content: str,
        metadata: Dict[str, Any] = None
    ) -> bool:
        """Add message to conversation history with automatic truncation"""
        session_data = await self.get_session(session_id, user_id)
        
        if not session_data:
            logger.error(f"Session not found: {session_id}")
            return False
        
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if metadata:
            message["metadata"] = metadata
        
        # Add to history
        session_data['conversation_history'].append(message)
        
        # Truncate if exceeds max history
        if len(session_data['conversation_history']) > self.max_history:
            # Keep the last N messages, but preserve system messages
            history = session_data['conversation_history']
            system_messages = [m for m in history if m.get('role') == 'system']
            other_messages = [m for m in history if m.get('role') != 'system']
            
            # Keep system messages + last N other messages
            keep_count = self.max_history - len(system_messages)
            session_data['conversation_history'] = system_messages + other_messages[-keep_count:]
            
            logger.debug(f"Truncated conversation history to {len(session_data['conversation_history'])} messages")
        
        # Update metadata
        session_data['metadata']['message_count'] = len(session_data['conversation_history'])
        
        return await self.update_session(session_id, user_id, session_data)
    
    async def get_conversation_history(
        self, 
        session_id: str, 
        user_id: str,
        limit: int = None
    ) -> List[Dict[str, Any]]:
        """Get conversation history for a session"""
        session_data = await self.get_session(session_id, user_id)
        
        if not session_data:
            return []
        
        history = session_data.get('conversation_history', [])
        
        if limit:
            return history[-limit:]
        
        return history
    
    async def update_context(
        self,
        session_id: str,
        user_id: str,
        context_updates: Dict[str, Any]
    ) -> bool:
        """Update session context (pending_action, last_action, etc.)"""
        session_data = await self.get_session(session_id, user_id)

        if not session_data:
            return False

        session_data['context'].update(context_updates)

        return await self.update_session(session_id, user_id, session_data)

    async def update_user_context(
        self,
        session_id: str,
        user_id: str,
        user_context_updates: Dict[str, Any]
    ) -> bool:
        """
        Update user-specific context (bot name, user name, preferences).
        Example: {"bot_name": "Molly", "user_name": "John", "preferences": "loves tech news"}
        """
        session_data = await self.get_session(session_id, user_id)

        if not session_data:
            return False

        # Ensure user_context exists
        if 'user_context' not in session_data:
            session_data['user_context'] = {
                "bot_name": None,
                "user_name": None,
                "preferences": None,
                "relationship": "assistant"
            }

        session_data['user_context'].update(user_context_updates)

        logger.info(f"Updated user context for {user_id}: {user_context_updates}")

        return await self.update_session(session_id, user_id, session_data)

    async def get_user_context(self, session_id: str, user_id: str) -> Dict[str, Any]:
        """Get user-specific context (bot name, user name, preferences)"""
        session_data = await self.get_session(session_id, user_id)

        if not session_data:
            return {}

        return session_data.get('user_context', {})

    async def get_active_sessions_count(self) -> int:
        """Count active sessions across all users"""
        return await self.redis.get_active_sessions_count()
    
    async def acquire_user_lock(self, user_id: str, timeout: int = 30) -> bool:
        """
        Acquire a lock for user to prevent concurrent request processing.
        This ensures a user's requests are processed one at a time.
        """
        return await self.redis.acquire_lock(user_id, timeout)
    
    async def release_user_lock(self, user_id: str) -> bool:
        """Release user lock after request processing"""
        return await self.redis.release_lock(user_id)
    
    async def health_check(self) -> bool:
        """Check if session manager is healthy (Redis connected)"""
        return await self.redis.health_check()