"""
Supabase Database Client for credential storage, audit logging, and rate limit persistence.
Uses supabase-py for async operations.
"""

import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from cryptography.fernet import Fernet
from supabase import create_client, Client
from ..config import settings

logger = logging.getLogger(__name__)


class Database:
    """Supabase database client for credential storage and audit logging"""
    
    _instance: Optional["Database"] = None
    _client: Optional[Client] = None
    _cipher: Optional[Fernet] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def initialize(self):
        """Initialize Supabase client and encryption"""
        if self._client is None:
            try:
                if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
                    logger.warning("Supabase credentials not configured")
                    return
                
                # Create client without proxy (Render doesn't need it)
                self._client = create_client(
                    supabase_url=settings.SUPABASE_URL,
                    supabase_key=settings.SUPABASE_KEY
                )
                logger.info("Supabase client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client: {e}")
                raise
        
        if self._cipher is None and settings.ENCRYPTION_KEY:
            try:
                self._cipher = Fernet(settings.ENCRYPTION_KEY.encode())
            except Exception as e:
                logger.error(f"Failed to initialize encryption: {e}")
    
    async def close(self):
        """Close Supabase client (no-op for supabase-py)"""
        self._client = None
        logger.info("Supabase client closed")
    
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
            if not self._client:
                await self.initialize()
                if not self._client:
                    return False
            
            encrypted = self._encrypt(credentials)
            
            # Upsert: insert or update on conflict
            data = {
                "user_id": user_id,
                "service": service,
                "encrypted_credentials": encrypted,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            self._client.table("tbl_clawdbot_credentials").upsert(
                data,
                on_conflict="user_id,service"
            ).execute()
            
            logger.info(f"Stored credentials for user {user_id}, service: {service}")
            return True
        except Exception as e:
            logger.error(f"Error storing credentials: {e}")
            return False
    
    async def get_credentials(self, user_id: int, service: str) -> Optional[Dict[str, Any]]:
        """Retrieve and decrypt credentials"""
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return None
            
            response = self._client.table("tbl_clawdbot_credentials").select(
                "encrypted_credentials, expires_at"
            ).eq("user_id", user_id).eq("service", service).execute()
            
            if not response.data or len(response.data) == 0:
                return None
            
            row = response.data[0]
            creds = self._decrypt(row['encrypted_credentials'])
            creds['expires_at'] = row['expires_at']
            
            return creds
        except Exception as e:
            logger.error(f"Error retrieving credentials: {e}")
            return None
    
    async def delete_credentials(self, user_id: int, service: str) -> bool:
        """Delete credentials for a service"""
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return False
            
            self._client.table("tbl_clawdbot_credentials").delete().eq(
                "user_id", user_id
            ).eq("service", service).execute()
            
            logger.info(f"Deleted credentials for user {user_id}, service: {service}")
            return True
        except Exception as e:
            logger.error(f"Error deleting credentials: {e}")
            return False
    
    async def get_all_credentials(self, user_id: int) -> Dict[str, Dict[str, Any]]:
        """Get all credentials for a user"""
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return {}
            
            response = self._client.table("tbl_clawdbot_credentials").select(
                "service, encrypted_credentials, expires_at"
            ).eq("user_id", user_id).execute()
            
            result = {}
            for row in response.data or []:
                creds = self._decrypt(row['encrypted_credentials'])
                creds['expires_at'] = row['expires_at']
                result[row['service']] = creds
            
            return result
        except Exception as e:
            logger.error(f"Error retrieving all credentials: {e}")
            return {}
    
    async def check_credentials_exist(self, user_id: int, service: str) -> bool:
        """Check if credentials exist for a service"""
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return False
            
            response = self._client.table("tbl_clawdbot_credentials").select(
                "id"
            ).eq("user_id", user_id).eq("service", service).execute()
            
            return len(response.data or []) > 0
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
            if not self._client:
                await self.initialize()
                if not self._client:
                    return None
            
            data = {
                "user_id": user_id,
                "session_id": session_id,
                "action_type": action_type,
                "request_summary": request_summary[:500] if request_summary else None,
                "response_summary": response_summary[:500] if response_summary else None,
                "status": status,
                "tokens_used": tokens_used,
                "error_message": error_message
            }
            
            response = self._client.table("tbl_clawdbot_audit_log").insert(data).execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0].get('id')
            return None
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
            if not self._client:
                await self.initialize()
                if not self._client:
                    return False
            
            data = {"status": status}
            
            if response_summary:
                data["response_summary"] = response_summary[:500]
            if tokens_used is not None:
                data["tokens_used"] = tokens_used
            if error_message:
                data["error_message"] = error_message
            
            self._client.table("tbl_clawdbot_audit_log").update(data).eq("id", log_id).execute()
            
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
            if not self._client:
                await self.initialize()
                if not self._client:
                    return []
            
            response = self._client.table("tbl_clawdbot_audit_log").select(
                "id, session_id, action_type, request_summary, response_summary, status, tokens_used, created_at"
            ).eq("user_id", user_id).order(
                "created_at", desc=True
            ).range(offset, offset + limit - 1).execute()
            
            return response.data or []
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
            if not self._client:
                await self.initialize()
                if not self._client:
                    return False
            
            # Simple query to check connectivity
            response = self._client.table("tbl_clawdbot_credentials").select("id").limit(1).execute()
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False


# Singleton instance
db = Database()
