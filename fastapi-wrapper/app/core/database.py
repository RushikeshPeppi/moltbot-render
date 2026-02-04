"""
MySQL Database Client for credential storage, audit logging, and rate limit persistence.
Uses aiomysql for async operations.
"""

import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
import aiomysql
from cryptography.fernet import Fernet
from ..config import settings

logger = logging.getLogger(__name__)


class Database:
    """Async MySQL database client with connection pooling"""
    
    _instance: Optional["Database"] = None
    _pool: Optional[aiomysql.Pool] = None
    _cipher: Optional[Fernet] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def initialize(self):
        """Initialize connection pool and encryption"""
        if self._pool is None:
            try:
                self._pool = await aiomysql.create_pool(
                    host=settings.MYSQL_HOST,
                    port=settings.MYSQL_PORT,
                    user=settings.MYSQL_USERNAME,
                    password=settings.MYSQL_PASSWORD,
                    db=settings.MYSQL_DATABASE,
                    minsize=1,
                    maxsize=settings.MYSQL_POOL_SIZE,
                    pool_recycle=settings.MYSQL_POOL_RECYCLE,
                    autocommit=True,
                    charset='utf8mb4'
                )
                logger.info("MySQL connection pool initialized")
            except Exception as e:
                logger.error(f"Failed to initialize MySQL pool: {e}")
                raise
        
        if self._cipher is None and settings.ENCRYPTION_KEY:
            try:
                self._cipher = Fernet(settings.ENCRYPTION_KEY.encode())
            except Exception as e:
                logger.error(f"Failed to initialize encryption: {e}")
    
    async def close(self):
        """Close connection pool"""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None
            logger.info("MySQL connection pool closed")
    
    @asynccontextmanager
    async def get_connection(self):
        """Get a connection from the pool"""
        if not self._pool:
            await self.initialize()
        
        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                yield cursor
    
    def _encrypt(self, data: Dict[str, Any]) -> str:
        """Encrypt credentials data"""
        if not self._cipher:
            raise ValueError("Encryption key not configured")
        return self._cipher.encrypt(json.dumps(data).encode()).decode()
    
    def _decrypt(self, encrypted: str) -> Dict[str, Any]:
        """Decrypt credentials data"""
        if not self._cipher:
            raise ValueError("Encryption key not configured")
        return json.loads(self._cipher.decrypt(encrypted.encode()).decode())
    
    # ==================== Credential Operations ====================
    
    async def store_credentials(
        self, 
        user_id: int, 
        service: str, 
        credentials: Dict[str, Any],
        expires_at: datetime = None
    ) -> bool:
        """Store encrypted credentials for a user"""
        try:
            encrypted = self._encrypt(credentials)
            
            async with self.get_connection() as cursor:
                await cursor.execute("""
                    INSERT INTO tbl_clawdbot_credentials 
                        (user_id, service, encrypted_credentials, expires_at)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        encrypted_credentials = VALUES(encrypted_credentials),
                        expires_at = VALUES(expires_at),
                        updated_at = CURRENT_TIMESTAMP
                """, (user_id, service, encrypted, expires_at))
            
            logger.info(f"Stored credentials for user {user_id}, service: {service}")
            return True
        except Exception as e:
            logger.error(f"Error storing credentials: {e}")
            return False
    
    async def get_credentials(self, user_id: int, service: str) -> Optional[Dict[str, Any]]:
        """Retrieve and decrypt credentials"""
        try:
            async with self.get_connection() as cursor:
                await cursor.execute("""
                    SELECT encrypted_credentials, expires_at 
                    FROM tbl_clawdbot_credentials
                    WHERE user_id = %s AND service = %s
                """, (user_id, service))
                
                row = await cursor.fetchone()
                
                if not row:
                    return None
                
                creds = self._decrypt(row['encrypted_credentials'])
                creds['expires_at'] = row['expires_at'].isoformat() if row['expires_at'] else None
                
                return creds
        except Exception as e:
            logger.error(f"Error retrieving credentials: {e}")
            return None
    
    async def delete_credentials(self, user_id: int, service: str) -> bool:
        """Delete credentials for a service"""
        try:
            async with self.get_connection() as cursor:
                await cursor.execute("""
                    DELETE FROM tbl_clawdbot_credentials
                    WHERE user_id = %s AND service = %s
                """, (user_id, service))
            
            logger.info(f"Deleted credentials for user {user_id}, service: {service}")
            return True
        except Exception as e:
            logger.error(f"Error deleting credentials: {e}")
            return False
    
    async def get_all_credentials(self, user_id: int) -> Dict[str, Dict[str, Any]]:
        """Get all credentials for a user"""
        try:
            async with self.get_connection() as cursor:
                await cursor.execute("""
                    SELECT service, encrypted_credentials, expires_at
                    FROM tbl_clawdbot_credentials
                    WHERE user_id = %s
                """, (user_id,))
                
                rows = await cursor.fetchall()
                
                result = {}
                for row in rows:
                    creds = self._decrypt(row['encrypted_credentials'])
                    creds['expires_at'] = row['expires_at'].isoformat() if row['expires_at'] else None
                    result[row['service']] = creds
                
                return result
        except Exception as e:
            logger.error(f"Error retrieving all credentials: {e}")
            return {}
    
    async def check_credentials_exist(self, user_id: int, service: str) -> bool:
        """Check if credentials exist for a service"""
        try:
            async with self.get_connection() as cursor:
                await cursor.execute("""
                    SELECT 1 FROM tbl_clawdbot_credentials
                    WHERE user_id = %s AND service = %s
                """, (user_id, service))
                
                return await cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking credentials: {e}")
            return False
    
    # ==================== Audit Logging ====================
    
    async def log_action(
        self,
        user_id: int,
        session_id: str,
        action_type: str,
        request_summary: str,
        response_summary: str = None,
        status: str = "pending",
        tokens_used: int = 0,
        error_message: str = None
    ) -> Optional[int]:
        """Log an action to the audit table"""
        try:
            async with self.get_connection() as cursor:
                await cursor.execute("""
                    INSERT INTO tbl_clawdbot_audit_log
                        (user_id, session_id, action_type, request_summary, 
                         response_summary, status, tokens_used, error_message)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    user_id, session_id, action_type, 
                    request_summary[:500] if request_summary else None,  # Truncate
                    response_summary[:500] if response_summary else None,
                    status, tokens_used, error_message
                ))
                
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error logging action: {e}")
            return None
    
    async def update_action_log(
        self,
        log_id: int,
        status: str,
        response_summary: str = None,
        tokens_used: int = None,
        error_message: str = None
    ) -> bool:
        """Update an existing audit log entry"""
        try:
            updates = ["status = %s"]
            params = [status]
            
            if response_summary:
                updates.append("response_summary = %s")
                params.append(response_summary[:500])
            if tokens_used is not None:
                updates.append("tokens_used = %s")
                params.append(tokens_used)
            if error_message:
                updates.append("error_message = %s")
                params.append(error_message)
            
            params.append(log_id)
            
            async with self.get_connection() as cursor:
                await cursor.execute(f"""
                    UPDATE tbl_clawdbot_audit_log
                    SET {', '.join(updates)}
                    WHERE id = %s
                """, tuple(params))
            
            return True
        except Exception as e:
            logger.error(f"Error updating action log: {e}")
            return False
    
    async def get_user_action_history(
        self, 
        user_id: int, 
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get action history for a user"""
        try:
            async with self.get_connection() as cursor:
                await cursor.execute("""
                    SELECT id, session_id, action_type, request_summary, 
                           response_summary, status, tokens_used, created_at
                    FROM tbl_clawdbot_audit_log
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (user_id, limit, offset))
                
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting action history: {e}")
            return []
    
    # ==================== Rate Limit Functions ====================
    # Note: Rate limiting is handled by Peppi (Laravel), not here.
    # These functions are kept as stubs for potential future use.
    
    async def get_user_tier(self, user_id: int) -> Dict[str, Any]:
        """Get user's tier - Note: Rate limiting handled by Peppi"""
        return {
            "tier": "free",
            "max_daily_requests": settings.FREE_TIER_DAILY_LIMIT,
            "daily_requests": 0
        }
    
    async def increment_daily_usage(self, user_id: int) -> bool:
        """Increment daily usage - Note: Rate limiting handled by Peppi"""
        return True
    
    async def reset_daily_limit(self, user_id: int) -> bool:
        """Reset daily limit - Note: Rate limiting handled by Peppi"""
        return True
    
    # ==================== Utility ====================
    
    async def health_check(self) -> bool:
        """Check database connectivity"""
        try:
            async with self.get_connection() as cursor:
                await cursor.execute("SELECT 1")
                return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False


# Singleton instance
db = Database()
