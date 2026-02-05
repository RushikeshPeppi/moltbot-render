"""
Supabase-backed Credential Manager with OAuth token support.
Handles encrypted storage and automatic token refresh.
"""

import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import httpx
from .database import db
from ..config import settings

logger = logging.getLogger(__name__)


class CredentialManager:
    """Supabase-backed encrypted credential storage with OAuth support"""
    
    def __init__(self):
        self.db = db
    
    async def store_credentials(
        self, 
        user_id: int, 
        service: str, 
        credentials: Dict[str, Any],
        expires_at: datetime = None
    ) -> bool:
        """Store encrypted service credentials"""
        return await self.db.store_credentials(user_id, service, credentials, expires_at)
    
    async def get_credentials(self, user_id: int, service: str) -> Optional[Dict[str, Any]]:
        """Retrieve and decrypt credentials"""
        return await self.db.get_credentials(user_id, service)
    
    async def delete_credentials(self, user_id: int, service: str) -> bool:
        """Delete service credentials"""
        return await self.db.delete_credentials(user_id, service)
    
    async def get_all_credentials(self, user_id: int) -> Dict[str, Dict[str, Any]]:
        """Get all credentials for a user"""
        return await self.db.get_all_credentials(user_id)
    
    async def check_credentials_exist(self, user_id: int, service: str) -> bool:
        """Check if credentials exist for a service"""
        return await self.db.check_credentials_exist(user_id, service)
    
    # ==================== OAuth Token Management ====================
    
    async def store_google_tokens(
        self,
        user_id: int,
        access_token: str,
        refresh_token: str,
        expires_in: int,
        token_type: str = "Bearer",
        scope: str = ""
    ) -> bool:
        """Store Google OAuth tokens"""
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        credentials = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": token_type,
            "scope": scope,
            "expires_in": expires_in
        }
        
        return await self.store_credentials(user_id, "google_oauth", credentials, expires_at)
    
    async def get_valid_google_token(self, user_id: int) -> Optional[str]:
        """
        Get a valid Google access token, refreshing if necessary.
        Returns None if no credentials or refresh fails.
        """
        creds = await self.get_credentials(user_id, "google_oauth")
        
        if not creds:
            logger.warning(f"No Google credentials for user {user_id}")
            return None
        
        # Check if token is expired (with 5 minute buffer)
        expires_at = creds.get('expires_at')
        if expires_at:
            try:
                exp_time = datetime.fromisoformat(expires_at)
                # Remove timezone info if present to compare with utcnow()
                if exp_time.tzinfo is not None:
                    exp_time = exp_time.replace(tzinfo=None)
                if datetime.utcnow() > exp_time - timedelta(minutes=5):
                    # Token expired or about to expire, refresh it
                    logger.info(f"Refreshing expired token for user {user_id}")
                    new_token = await self.refresh_google_token(user_id, creds['refresh_token'])
                    if new_token:
                        return new_token
                    else:
                        logger.error(f"Failed to refresh token for user {user_id}")
                        return None
            except (ValueError, KeyError) as e:
                logger.error(f"Error parsing token expiry: {e}")
        
        return creds.get('access_token')
    
    async def refresh_google_token(self, user_id: int, refresh_token: str) -> Optional[str]:
        """Refresh Google access token using refresh token"""
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            logger.error("Google OAuth not configured")
            return None
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": settings.GOOGLE_CLIENT_ID,
                        "client_secret": settings.GOOGLE_CLIENT_SECRET,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token"
                    }
                )
                
                if response.status_code != 200:
                    logger.error(f"Token refresh failed: {response.text}")
                    return None
                
                data = response.json()
                
                # Store new tokens
                await self.store_google_tokens(
                    user_id=user_id,
                    access_token=data['access_token'],
                    refresh_token=refresh_token,  # Refresh token doesn't change
                    expires_in=data.get('expires_in', 3600),
                    token_type=data.get('token_type', 'Bearer'),
                    scope=data.get('scope', '')
                )
                
                logger.info(f"Token refreshed for user {user_id}")
                return data['access_token']
                
        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            return None
    
    async def revoke_google_token(self, user_id: int) -> bool:
        """Revoke Google OAuth tokens"""
        creds = await self.get_credentials(user_id, "google_oauth")
        
        if not creds:
            return True  # Already revoked
        
        try:
            # Revoke at Google
            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": creds.get('access_token')}
                )
            
            # Delete from database
            await self.delete_credentials(user_id, "google_oauth")
            logger.info(f"Revoked Google tokens for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error revoking token: {e}")
            return False
    
    async def get_google_connection_status(self, user_id: int) -> Dict[str, Any]:
        """Get Google OAuth connection status for a user"""
        creds = await self.get_credentials(user_id, "google_oauth")
        
        if not creds:
            return {
                "connected": False,
                "service": "google",
                "scopes": []
            }
        
        # Check if token is valid
        token = await self.get_valid_google_token(user_id)
        
        return {
            "connected": token is not None,
            "service": "google",
            "scopes": creds.get('scope', '').split(' ') if creds.get('scope') else [],
            "expires_at": creds.get('expires_at')
        }