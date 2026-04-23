"""
Supabase-backed Credential Manager with OAuth token support.
Handles encrypted storage, automatic token refresh, and dead-token cleanup.

Key behaviors:
- On `invalid_grant`: auto-revokes credential from DB, updates google_connected flag,
  and sets a Redis cooldown to prevent hammering Google's API.
- On transient errors (network, 5xx): keeps credential, sets short cooldown.
- Cooldown prevents repeated refresh attempts within a 5-minute window.
"""

import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import httpx
from .database import db
from .redis_client import redis_client
from ..config import settings
from ..utils.timezone_utils import now_utc_naive

logger = logging.getLogger(__name__)

# Cooldown duration (seconds) before retrying a failed token refresh
OAUTH_COOLDOWN_TTL = 300  # 5 minutes


class CredentialManager:
    """Supabase-backed encrypted credential storage with OAuth support"""
    
    def __init__(self):
        self.db = db
    
    async def store_credentials(
        self, 
        user_id: str, 
        service: str, 
        credentials: Dict[str, Any],
        expires_at: datetime = None
    ) -> bool:
        """Store encrypted service credentials"""
        return await self.db.store_credentials(user_id, service, credentials, expires_at)
    
    async def get_credentials(self, user_id: str, service: str) -> Optional[Dict[str, Any]]:
        """Retrieve and decrypt credentials"""
        return await self.db.get_credentials(user_id, service)
    
    async def delete_credentials(self, user_id: str, service: str) -> bool:
        """Delete service credentials"""
        return await self.db.delete_credentials(user_id, service)
    
    async def get_all_credentials(self, user_id: str) -> Dict[str, Dict[str, Any]]:
        """Get all credentials for a user"""
        return await self.db.get_all_credentials(user_id)
    
    async def check_credentials_exist(self, user_id: str, service: str) -> bool:
        """Check if credentials exist for a service"""
        return await self.db.check_credentials_exist(user_id, service)
    
    # ==================== OAuth Token Management ====================
    
    async def store_google_tokens(
        self,
        user_id: str,
        access_token: str,
        refresh_token: str,
        expires_in: int,
        token_type: str = "Bearer",
        scope: str = ""
    ) -> bool:
        """Store Google OAuth tokens"""
        expires_at = now_utc_naive() + timedelta(seconds=expires_in)
        
        credentials = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": token_type,
            "scope": scope,
            "expires_in": expires_in
        }
        
        # Clear any existing cooldown since we have fresh tokens
        await self._clear_oauth_cooldown(user_id)
        
        return await self.store_credentials(user_id, "google_oauth", credentials, expires_at)
    
    async def get_valid_google_token(self, user_id: str) -> Optional[str]:
        """
        Get a valid Google access token, refreshing if necessary.
        Returns None if no credentials, refresh fails, or cooldown is active.
        """
        # Check cooldown BEFORE hitting Google's API
        if await self._is_oauth_on_cooldown(user_id):
            logger.debug(f"OAuth cooldown active for user {user_id}, skipping refresh")
            return None

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
                if now_utc_naive() > exp_time - timedelta(minutes=5):
                    # Token expired or about to expire, refresh it
                    logger.info(f"Refreshing expired token for user {user_id}")
                    new_token = await self.refresh_google_token(user_id, creds['refresh_token'])
                    if new_token:
                        return new_token
                    else:
                        # refresh_google_token already handled cleanup/cooldown
                        return None
            except (ValueError, KeyError) as e:
                logger.error(f"Error parsing token expiry: {e}")
        
        return creds.get('access_token')
    
    async def refresh_google_token(self, user_id: str, refresh_token: str) -> Optional[str]:
        """
        Refresh Google access token using refresh token.
        
        On permanent failure (invalid_grant): auto-revokes credentials.
        On transient failure (network/5xx): sets cooldown, keeps credentials.
        """
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
                    error_body = response.text
                    logger.error(f"Token refresh failed: {error_body}")
                    
                    # Parse the error to distinguish permanent vs transient
                    try:
                        error_data = response.json()
                        error_code = error_data.get("error", "")
                    except Exception:
                        error_code = ""
                    
                    # PERMANENT failures — token is dead, clean it up
                    permanent_errors = {"invalid_grant", "invalid_client", "unauthorized_client"}
                    if error_code in permanent_errors:
                        logger.error(
                            f"PERMANENT OAuth failure for user {user_id}: {error_code}. "
                            f"Auto-revoking credentials."
                        )
                        await self.invalidate_google_credentials(user_id)
                    else:
                        # TRANSIENT failure — set cooldown but keep credentials
                        logger.warning(
                            f"Transient OAuth failure for user {user_id}: "
                            f"status={response.status_code}, error={error_code}. "
                            f"Setting {OAUTH_COOLDOWN_TTL}s cooldown."
                        )
                        await self._set_oauth_cooldown(user_id)
                    
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
                
        except httpx.TimeoutException:
            logger.warning(f"Token refresh timed out for user {user_id}, setting cooldown")
            await self._set_oauth_cooldown(user_id)
            return None
        except httpx.ConnectError:
            logger.warning(f"Token refresh connection error for user {user_id}, setting cooldown")
            await self._set_oauth_cooldown(user_id)
            return None
        except Exception as e:
            logger.error(f"Unexpected error refreshing token for user {user_id}: {e}")
            await self._set_oauth_cooldown(user_id)
            return None
    
    async def invalidate_google_credentials(self, user_id: str) -> None:
        """
        Permanently remove dead Google credentials and update user record.
        Called when refresh token is permanently invalid (invalid_grant, revoked, etc.).
        """
        # 1. Delete the credential row
        await self.delete_credentials(user_id, "google_oauth")
        
        # 2. Update user's google_connected flag
        try:
            await self.db.update_google_connected(user_id, False)
        except Exception as e:
            logger.error(f"Failed to update google_connected for user {user_id}: {e}")
        
        # 3. Set cooldown to prevent immediate re-attempts
        await self._set_oauth_cooldown(user_id)
        
        logger.info(f"Invalidated Google credentials for user {user_id}")
    
    async def revoke_google_token(self, user_id: str) -> bool:
        """Revoke Google OAuth tokens (user-initiated disconnect)"""
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
            
            # Delete from database and update user record
            await self.invalidate_google_credentials(user_id)
            logger.info(f"Revoked Google tokens for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error revoking token: {e}")
            return False
    
    async def get_google_connection_status(self, user_id: str) -> Dict[str, Any]:
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
    
    # ==================== Cooldown Helpers ====================
    
    async def _is_oauth_on_cooldown(self, user_id: str) -> bool:
        """Check if OAuth refresh is on cooldown for this user."""
        key = f"oauth_cooldown:{user_id}"
        value = await redis_client.get(key)
        return value is not None
    
    async def _set_oauth_cooldown(self, user_id: str) -> None:
        """Set OAuth cooldown to prevent hammering Google's API."""
        key = f"oauth_cooldown:{user_id}"
        await redis_client.set(key, "1", ttl=OAUTH_COOLDOWN_TTL)
    
    async def _clear_oauth_cooldown(self, user_id: str) -> None:
        """Clear OAuth cooldown (e.g., after successful token storage)."""
        key = f"oauth_cooldown:{user_id}"
        await redis_client.delete(key)