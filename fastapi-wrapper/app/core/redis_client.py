"""
Upstash Redis Client for session management and rate limiting.
Uses HTTP-based Upstash Redis which works well with serverless/Render.
"""

import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from upstash_redis import Redis
from ..config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Upstash Redis client wrapper for session and rate limit management"""
    
    _instance: Optional["RedisClient"] = None
    _redis: Optional[Redis] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._redis is None and settings.UPSTASH_REDIS_URL:
            try:
                self._redis = Redis(
                    url=settings.UPSTASH_REDIS_URL,
                    token=settings.UPSTASH_REDIS_TOKEN
                )
                logger.info("Upstash Redis client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Redis: {e}")
                self._redis = None
    
    @property
    def is_connected(self) -> bool:
        """Check if Redis is connected"""
        return self._redis is not None
    
    # ==================== Session Operations ====================
    
    async def set_session(
        self, 
        user_id: str, 
        session_id: str, 
        data: Dict[str, Any],
        ttl: int = None
    ) -> bool:
        """Store session data with TTL"""
        if not self._redis:
            logger.warning("Redis not connected, skipping session storage")
            return False
        
        try:
            key = f"session:{user_id}:{session_id}"
            ttl = ttl or settings.SESSION_TTL
            
            # Add metadata
            data["_stored_at"] = datetime.utcnow().isoformat()
            data["_expires_at"] = (datetime.utcnow() + timedelta(seconds=ttl)).isoformat()
            
            self._redis.setex(key, ttl, json.dumps(data))
            logger.debug(f"Session stored: {key}")
            return True
        except Exception as e:
            logger.error(f"Error storing session: {e}")
            return False
    
    async def get_session(self, user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve session data"""
        if not self._redis:
            return None
        
        try:
            key = f"session:{user_id}:{session_id}"
            data = self._redis.get(key)
            
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Error retrieving session: {e}")
            return None
    
    async def get_user_sessions(self, user_id: str) -> list:
        """Get all sessions for a user"""
        if not self._redis:
            return []
        
        try:
            pattern = f"session:{user_id}:*"
            keys = self._redis.keys(pattern)
            return keys or []
        except Exception as e:
            logger.error(f"Error getting user sessions: {e}")
            return []
    
    async def delete_session(self, user_id: str, session_id: str) -> bool:
        """Delete a session"""
        if not self._redis:
            return False
        
        try:
            key = f"session:{user_id}:{session_id}"
            self._redis.delete(key)
            logger.debug(f"Session deleted: {key}")
            return True
        except Exception as e:
            logger.error(f"Error deleting session: {e}")
            return False
    
    async def refresh_session_ttl(self, user_id: str, session_id: str, ttl: int = None) -> bool:
        """Refresh session TTL (sliding expiration)"""
        if not self._redis:
            return False
        
        try:
            key = f"session:{user_id}:{session_id}"
            ttl = ttl or settings.SESSION_TTL
            self._redis.expire(key, ttl)
            return True
        except Exception as e:
            logger.error(f"Error refreshing session TTL: {e}")
            return False
    
    # ==================== Generic Operations ====================

    async def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """Store arbitrary key-value with optional TTL"""
        if not self._redis:
            logger.warning("Redis not connected, skipping storage")
            return False

        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)

            if ttl:
                self._redis.setex(key, ttl, value)
            else:
                self._redis.set(key, value)

            logger.debug(f"Key stored: {key}")
            return True
        except Exception as e:
            logger.error(f"Error storing key: {e}")
            return False

    async def get(self, key: str) -> Optional[Any]:
        """Retrieve value by key"""
        if not self._redis:
            return None

        try:
            data = self._redis.get(key)
            if data:
                try:
                    return json.loads(data)
                except:
                    return data
            return None
        except Exception as e:
            logger.error(f"Error retrieving key: {e}")
            return None

    async def delete(self, key: str) -> bool:
        """Delete a key"""
        if not self._redis:
            logger.warning("Redis not connected, skipping deletion")
            return False

        try:
            self._redis.delete(key)
            logger.debug(f"Key deleted: {key}")
            return True
        except Exception as e:
            logger.error(f"Error deleting key: {e}")
            return False

    # ==================== Rate Limiting ====================

    async def check_rate_limit(self, user_id: str, daily_limit: int = None) -> Dict[str, Any]:
        """
        Check and increment rate limit for user.
        Returns: {"allowed": bool, "remaining": int, "reset_at": str}
        """
        if not self._redis:
            # If Redis is down, allow request but log warning
            logger.warning("Redis not connected, allowing request without rate limit")
            return {"allowed": True, "remaining": -1, "reset_at": None}
        
        try:
            daily_limit = daily_limit or settings.FREE_TIER_DAILY_LIMIT
            today = datetime.utcnow().strftime("%Y-%m-%d")
            key = f"rate_limit:{user_id}:{today}"
            
            # Get current count
            current = self._redis.get(key)
            current_count = int(current) if current else 0
            
            if current_count >= daily_limit:
                # Calculate reset time (midnight UTC)
                tomorrow = datetime.utcnow().replace(
                    hour=0, minute=0, second=0, microsecond=0
                ) + timedelta(days=1)
                
                return {
                    "allowed": False,
                    "remaining": 0,
                    "reset_at": tomorrow.isoformat()
                }
            
            # Increment count
            new_count = self._redis.incr(key)
            
            # Set expiry if first request of the day
            if new_count == 1:
                # Expire at midnight + 1 hour buffer
                seconds_until_midnight = (
                    (datetime.utcnow().replace(hour=23, minute=59, second=59) - datetime.utcnow()).seconds + 3600
                )
                self._redis.expire(key, seconds_until_midnight)
            
            return {
                "allowed": True,
                "remaining": daily_limit - new_count,
                "reset_at": None
            }
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return {"allowed": True, "remaining": -1, "reset_at": None}
    
    async def get_rate_limit_status(self, user_id: str, daily_limit: int = None) -> Dict[str, Any]:
        """Get current rate limit status without incrementing"""
        if not self._redis:
            return {"used": 0, "limit": daily_limit or settings.FREE_TIER_DAILY_LIMIT, "remaining": -1}
        
        try:
            daily_limit = daily_limit or settings.FREE_TIER_DAILY_LIMIT
            today = datetime.utcnow().strftime("%Y-%m-%d")
            key = f"rate_limit:{user_id}:{today}"
            
            current = self._redis.get(key)
            current_count = int(current) if current else 0
            
            return {
                "used": current_count,
                "limit": daily_limit,
                "remaining": max(0, daily_limit - current_count)
            }
        except Exception as e:
            logger.error(f"Error getting rate limit status: {e}")
            return {"used": 0, "limit": daily_limit, "remaining": daily_limit}
    
    # ==================== Request Locking ====================
    
    async def acquire_lock(self, user_id: str, lock_timeout: int = 30) -> bool:
        """
        Acquire a lock for user to prevent concurrent request processing.
        Returns True if lock acquired, False if already locked.
        """
        if not self._redis:
            return True  # Allow if Redis is down
        
        try:
            key = f"lock:{user_id}"
            # SET NX (only if not exists) with expiry
            result = self._redis.set(key, "locked", ex=lock_timeout, nx=True)
            return result is not None
        except Exception as e:
            logger.error(f"Error acquiring lock: {e}")
            return True
    
    async def release_lock(self, user_id: str) -> bool:
        """Release user lock"""
        if not self._redis:
            return True
        
        try:
            key = f"lock:{user_id}"
            self._redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"Error releasing lock: {e}")
            return False
    
    # ==================== Utility ====================
    
    async def health_check(self) -> bool:
        """Check Redis connectivity"""
        if not self._redis:
            return False
        
        try:
            self._redis.ping()
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False
    
    async def get_active_sessions_count(self) -> int:
        """Count all active sessions"""
        if not self._redis:
            return 0
        
        try:
            keys = self._redis.keys("session:*")
            return len(keys) if keys else 0
        except Exception as e:
            logger.error(f"Error counting sessions: {e}")
            return 0


# Singleton instance
redis_client = RedisClient()
