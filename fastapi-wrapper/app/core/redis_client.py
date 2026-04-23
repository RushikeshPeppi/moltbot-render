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
from ..utils.timezone_utils import now_utc_naive

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
            data["_stored_at"] = now_utc_naive().isoformat()
            data["_expires_at"] = (now_utc_naive() + timedelta(seconds=ttl)).isoformat()
            
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
            today = now_utc_naive().strftime("%Y-%m-%d")
            key = f"rate_limit:{user_id}:{today}"
            
            # Get current count
            current = self._redis.get(key)
            current_count = int(current) if current else 0
            
            if current_count >= daily_limit:
                # Calculate reset time (midnight UTC)
                tomorrow = now_utc_naive().replace(
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
                    (now_utc_naive().replace(hour=23, minute=59, second=59) - now_utc_naive()).seconds + 3600
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
            today = now_utc_naive().strftime("%Y-%m-%d")
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
    #
    # Ownership-token Redlock pattern (per Redis docs):
    #   - acquire: SET key <token> NX EX <ttl>  — token is an unguessable UUID
    #   - release: Lua script that DELs only if stored value == our token
    # Without the ownership check, a lock that times out mid-turn could be
    # released by the original holder after another request has grabbed the
    # same key — classic double-release bug.
    #
    # TTL default bumped to 320s because image-flow agent turns can take up
    # to 260s (260s gateway + 60s buffer for FastAPI framing + network).
    # Callers can refresh TTL mid-turn via extend_lock().

    # Lua for atomic, owner-checked release. Run via Redis's EVAL command.
    _RELEASE_LUA = (
        "if redis.call('get', KEYS[1]) == ARGV[1] then "
        "return redis.call('del', KEYS[1]) "
        "else return 0 end"
    )
    # Lua for atomic, owner-checked TTL extension.
    _EXTEND_LUA = (
        "if redis.call('get', KEYS[1]) == ARGV[1] then "
        "return redis.call('expire', KEYS[1], ARGV[2]) "
        "else return 0 end"
    )

    async def acquire_lock(
        self, user_id: str, lock_timeout: int = 320
    ) -> Optional[str]:
        """
        Acquire a per-user lock. Returns the unique ownership token on
        success, or None if the lock is already held. Callers MUST pass the
        same token back to release_lock() — a blind DEL could release some
        other request's lock if this one expired mid-turn.

        Return type changed from bool to Optional[str] (breaking). Old
        callers that didn't thread a token around were buggy anyway.
        """
        if not self._redis:
            # Redis down: sentinel token so release is a no-op. Preserves
            # the prior "allow through when Redis is down" behaviour.
            return "redis-down-sentinel"

        try:
            key = f"lock:{user_id}"
            import uuid
            token = uuid.uuid4().hex
            result = self._redis.set(key, token, ex=lock_timeout, nx=True)
            return token if result else None
        except Exception as e:
            logger.error(f"Error acquiring lock for {user_id}: {e}")
            return None  # Fail-closed on unexpected errors.

    async def release_lock(self, user_id: str, token: str) -> bool:
        """
        Release the lock iff the stored value matches our token. Passing
        the wrong token is a no-op.
        """
        if not self._redis:
            return True
        if token == "redis-down-sentinel":
            return True

        try:
            key = f"lock:{user_id}"
            # upstash-redis exposes the EVAL primitive directly so we can
            # run the Redlock-release Lua script atomically on the server.
            result = self._redis.execute("EVAL", self._RELEASE_LUA, 1, key, token)
            if result == 0:
                logger.warning(
                    f"release_lock: token mismatch or key expired for {user_id}; "
                    f"skipping DEL to protect a subsequent holder."
                )
            return True
        except Exception as e:
            logger.error(f"Error releasing lock for {user_id}: {e}")
            return False

    async def extend_lock(
        self, user_id: str, token: str, lock_timeout: int = 320
    ) -> bool:
        """
        Refresh TTL on a lock we still own. Use during long agent turns
        to keep the lock alive past the original acquire TTL.
        """
        if not self._redis:
            return True
        if token == "redis-down-sentinel":
            return True

        try:
            key = f"lock:{user_id}"
            result = self._redis.execute(
                "EVAL", self._EXTEND_LUA, 1, key, token, str(lock_timeout)
            )
            return result == 1
        except Exception as e:
            logger.error(f"Error extending lock for {user_id}: {e}")
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

    # ==================== Playground Messages ====================

    async def push_playground_message(self, user_id: str, message: Dict[str, Any]) -> bool:
        """
        Push a playground message (e.g. reminder delivery) to a Redis list.
        The playground frontend polls this and shows the message in the chat window.
        TTL: 1 hour so unread messages don't accumulate forever.
        """
        if not self._redis:
            logger.warning("Redis not connected, skipping playground message push")
            return False

        try:
            key = f"playground_msg:{user_id}"
            self._redis.rpush(key, json.dumps(message))
            # Set/refresh TTL to 1 hour so stale messages are auto-cleaned
            self._redis.expire(key, 3600)
            logger.info(f"Pushed playground message for user {user_id}: {message.get('type')}")
            return True
        except Exception as e:
            logger.error(f"Error pushing playground message: {e}")
            return False

    async def pop_playground_messages(self, user_id: str) -> list:
        """
        Atomically read all pending playground messages for a user and clear the list.
        Returns a list of message dicts. Returns [] if none or Redis unavailable.
        """
        if not self._redis:
            return []

        try:
            key = f"playground_msg:{user_id}"
            # Get all items
            raw_messages = self._redis.lrange(key, 0, -1)
            if not raw_messages:
                return []
            # Clear the list
            self._redis.delete(key)
            return [json.loads(m) for m in raw_messages]
        except Exception as e:
            logger.error(f"Error popping playground messages: {e}")
            return []


# Singleton instance
redis_client = RedisClient()
