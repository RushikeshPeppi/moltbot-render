"""
Google OAuth endpoints for Peppi website integration.
Handles OAuth flow, token exchange, and connection status.

All responses follow the standardized DTO format:
- code: HTTP status code
- message: Human-readable message
- data: Response payload
- error: Error type/code
- exception: Exception details
"""

import logging
import secrets
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Query, Depends
from fastapi.responses import RedirectResponse, JSONResponse
import httpx
from ..utils.timezone_utils import now_utc_naive

from ..config import settings
from ..core.credential_manager import CredentialManager
from ..core.database import db
from ..core.redis_client import redis_client
from ..core.auth import require_internal_secret
from ..models import ResponseCode

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/oauth", tags=["OAuth"])

credential_manager = CredentialManager()


def create_response(
    code: int,
    message: str,
    data: dict = None,
    error: str = None,
    exception: str = None
) -> dict:
    """Create standardized response"""
    return {
        "code": code,
        "message": message,
        "data": data,
        "error": error,
        "exception": exception,
        "timestamp": now_utc_naive().isoformat()
    }


def create_error_response(
    code: int,
    message: str,
    error: str,
    exception: str = None
) -> JSONResponse:
    """Create standardized error JSON response"""
    return JSONResponse(
        status_code=code,
        content=create_response(code, message, None, error, exception)
    )


@router.get("/google/init")
async def google_oauth_init(
    user_id: str = Query(..., description="Peppi user ID"),
    redirect_uri: Optional[str] = Query(None, description="Where to redirect after OAuth completes")
):
    """
    Initialize Google OAuth flow.
    
    Your Peppi website calls this endpoint, then redirects the user to the returned URL.
    
    Example:
        GET /api/v1/oauth/google/init?user_id=123&redirect_uri=https://peppi.app/clawdbot/connected
    """
    try:
        if not settings.GOOGLE_CLIENT_ID:
            return create_error_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Google OAuth not configured",
                error="OAUTH_NOT_CONFIGURED",
                exception=None
            )
        
        # Generate state for CSRF protection
        state = secrets.token_urlsafe(32)
        
        # Store state in Redis with 10 minute expiration
        state_data = {
            "user_id": user_id,
            "redirect_uri": redirect_uri or settings.PEPPI_WEBSITE_URL
        }
        
        # Store OAuth state in Redis
        stored = await redis_client.set(
            f"oauth_state:{state}",
            state_data,
            ttl=600  # 10 minutes
        )
        
        if not stored:
            # Fallback: in-memory (not recommended for production)
            logger.warning("Redis unavailable, using in-memory state storage")
        
        # Build authorization URL
        scopes = " ".join(settings.GOOGLE_SCOPES)
        
        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth"
            f"?client_id={settings.GOOGLE_CLIENT_ID}"
            f"&redirect_uri={settings.GOOGLE_REDIRECT_URI}"
            f"&response_type=code"
            f"&scope={scopes}"
            f"&state={state}"
            f"&access_type=offline"
            f"&prompt=consent"
        )
        
        logger.info(f"OAuth init for user {user_id}")
        
        return create_response(
            code=ResponseCode.SUCCESS,
            message="OAuth initialization successful",
            data={
                "authorization_url": auth_url,
                "state": state
            }
        )
    except Exception as e:
        logger.error(f"OAuth init error: {e}")
        return create_error_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Failed to initialize OAuth",
            error="OAUTH_INIT_ERROR",
            exception=str(e)
        )


@router.get("/google/callback")
async def google_oauth_callback(
    code: str = Query(None, description="Authorization code from Google"),
    state: str = Query(None, description="State parameter for CSRF verification"),
    error: Optional[str] = Query(None, description="Error from Google if any")
):
    """
    Handle OAuth callback from Google.
    
    This endpoint is called by Google after user authorizes.
    It exchanges the code for tokens and stores them in the database.
    """
    # Default redirect for errors
    default_redirect = settings.PEPPI_WEBSITE_URL or "https://peppi.app"
    
    # Handle Google errors
    if error:
        logger.error(f"OAuth error from Google: {error}")
        return RedirectResponse(
            url=f"{default_redirect}/clawdbot/oauth?status=error&error=GOOGLE_DENIED"
        )
    
    # Validate required parameters
    if not code or not state:
        logger.error("Missing code or state parameter")
        return RedirectResponse(
            url=f"{default_redirect}/clawdbot/oauth?status=error&error=INVALID_REQUEST"
        )
    
    try:
        # Get state data from Redis
        state_data = await redis_client.get(f"oauth_state:{state}")
        
        if not state_data:
            logger.error(f"Invalid or expired state: {state}")
            return RedirectResponse(
                url=f"{default_redirect}/clawdbot/oauth?status=error&error=INVALID_STATE"
            )
        
        # Delete state (one-time use)
        await redis_client.delete(f"oauth_state:{state}")

        # Extract user_id
        user_id = str(state_data.get("user_id", ""))
        if not user_id:
            logger.error(f"Missing user_id in state data: {state_data}")
            return RedirectResponse(
                url=f"{default_redirect}/clawdbot/oauth?status=error&error=INVALID_USER_ID"
            )

        redirect_uri = state_data.get("redirect_uri", default_redirect)
        
        # Exchange code for tokens with retry logic
        tokens = None
        last_error = None
        
        for attempt in range(1, 4):  # Max 3 attempts
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.post(
                        "https://oauth2.googleapis.com/token",
                        data={
                            "client_id": settings.GOOGLE_CLIENT_ID,
                            "client_secret": settings.GOOGLE_CLIENT_SECRET,
                            "code": code,
                            "grant_type": "authorization_code",
                            "redirect_uri": settings.GOOGLE_REDIRECT_URI
                        }
                    )
                    
                    if response.status_code == 200:
                        tokens = response.json()
                        break
                    else:
                        last_error = response.text
                        logger.warning(f"Token exchange attempt {attempt} failed: {last_error}")
                        
            except httpx.TimeoutException as e:
                last_error = str(e)
                logger.warning(f"Token exchange timeout on attempt {attempt}")
            except Exception as e:
                last_error = str(e)
                logger.error(f"Token exchange error on attempt {attempt}: {e}")
                break  # Don't retry unexpected errors
        
        if not tokens:
            logger.error(f"Token exchange failed after retries: {last_error}")
            return RedirectResponse(
                url=f"{redirect_uri}/clawdbot/oauth?status=error&error=TOKEN_EXCHANGE_FAILED"
            )
        
        # Store tokens
        try:
            # Log the actual scopes received from Google (for debugging)
            received_scope = tokens.get('scope', '')
            logger.info(f"OAuth token received for user {user_id} with scopes: {received_scope}")

            stored = await credential_manager.store_google_tokens(
                user_id=user_id,
                access_token=tokens['access_token'],
                refresh_token=tokens.get('refresh_token', ''),
                expires_in=tokens.get('expires_in', 3600),
                token_type=tokens.get('token_type', 'Bearer'),
                scope=received_scope
            )

            if not stored:
                logger.error(f"Failed to store tokens for user {user_id}")
                return RedirectResponse(
                    url=f"{redirect_uri}/clawdbot/oauth?status=error&error=TOKEN_STORAGE_FAILED"
                )
        except Exception as e:
            logger.error(f"Exception storing tokens for user {user_id}: {e}")
            return RedirectResponse(
                url=f"{redirect_uri}/clawdbot/oauth?status=error&error=TOKEN_STORAGE_ERROR&details={str(e)[:100]}"
            )

        # Fetch Google profile info and upsert user
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                profile_resp = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {tokens['access_token']}"}
                )
                if profile_resp.status_code == 200:
                    profile = profile_resp.json()
                    user_name = profile.get("name", f"User {user_id}")
                    user_email = profile.get("email")
                else:
                    user_name = state_data.get("user_name", f"User {user_id}")
                    user_email = None
        except Exception as e:
            logger.warning(f"Failed to fetch Google profile for user {user_id}: {e}")
            user_name = state_data.get("user_name", f"User {user_id}")
            user_email = None

        # Upsert user into tbl_clawdbot_users
        try:
            await db.upsert_user(
                user_id=user_id,
                name=user_name,
                email=user_email,
                google_connected=True
            )
        except Exception as e:
            logger.warning(f"Failed to upsert user {user_id}: {e}")

        # Log the action (non-critical, don't fail if this fails)
        try:
            await db.log_action(
                user_id=user_id,
                session_id="oauth_flow",
                action_type="google_oauth_connect",
                request_summary="User connected Google account",
                status="success"
            )
        except Exception as e:
            logger.warning(f"Failed to log OAuth action for user {user_id}: {e}")

        logger.info(f"OAuth completed for user {user_id}")

        # Redirect to success page
        # Only append /clawdbot/oauth for the Peppi website (base domain with no path)
        # For custom redirect_uris (like playground's /oauth-callback), use as-is
        base_url = redirect_uri
        if redirect_uri == default_redirect and not any(
            p in redirect_uri for p in ["/oauth-callback", "/callback"]
        ):
            base_url = f"{redirect_uri}/clawdbot/oauth"

        separator = "&" if "?" in base_url else "?"
        return RedirectResponse(
            url=f"{base_url}{separator}status=success&service=google&user_id={user_id}"
        )
        
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        return RedirectResponse(
            url=f"{default_redirect}/clawdbot/oauth?status=error&error=CALLBACK_ERROR"
        )


@router.get("/google/status/{user_id}")
async def google_oauth_status(user_id: str):
    """
    Check if a user has connected their Google account.
    
    Your Peppi website can call this to show connection status.
    """
    try:
        status = await credential_manager.get_google_connection_status(user_id)
        
        return create_response(
            code=ResponseCode.SUCCESS,
            message="Google OAuth status retrieved",
            data={
                "connected": status['connected'],
                "service": status['service'],
                "scopes": status['scopes'],
                "expires_at": status.get('expires_at')
            }
        )
    except Exception as e:
        logger.error(f"OAuth status error: {e}")
        return create_error_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Failed to get OAuth status",
            error="OAUTH_STATUS_ERROR",
            exception=str(e)
        )


@router.delete(
    "/google/disconnect/{user_id}",
    dependencies=[Depends(require_internal_secret)],
)
async def google_oauth_disconnect(user_id: str):
    """
    Disconnect (revoke) a user's Google connection. **Internal only** —
    requires Authorization: Bearer <MOLTBOT_INTERNAL_SECRET>.

    Revokes tokens at Google and deletes them from the database.
    """
    try:
        success = await credential_manager.revoke_google_token(user_id)
        
        if success:
            # Log the action
            await db.log_action(
                user_id=user_id,
                session_id="oauth_flow",
                action_type="google_oauth_disconnect",
                request_summary="User disconnected Google account",
                status="success"
            )
            
            return create_response(
                code=ResponseCode.SUCCESS,
                message="Google account disconnected successfully",
                data={"disconnected": True}
            )
        else:
            return create_error_response(
                code=ResponseCode.NOT_FOUND,
                message="No Google account connected",
                error="NOT_CONNECTED",
                exception=None
            )
    except Exception as e:
        logger.error(f"Error disconnecting Google: {e}")
        return create_error_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Failed to disconnect Google account",
            error="OAUTH_DISCONNECT_ERROR",
            exception=str(e)
        )


@router.post(
    "/google/refresh/{user_id}",
    dependencies=[Depends(require_internal_secret)],
)
async def google_oauth_refresh(user_id: str):
    """
    Manually refresh a user's Google access token. **Internal only** —
    requires Authorization: Bearer <MOLTBOT_INTERNAL_SECRET>.

    Normally tokens are refreshed automatically.
    """
    try:
        token = await credential_manager.get_valid_google_token(user_id)

        if token:
            return create_response(
                code=ResponseCode.SUCCESS,
                message="Token refreshed successfully",
                data={"refreshed": True}
            )
        else:
            return create_error_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to refresh token",
                error="TOKEN_REFRESH_FAILED",
                exception=None
            )
    except Exception as e:
        logger.error(f"Error refreshing token: {e}")
        return create_error_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Failed to refresh token",
            error="TOKEN_REFRESH_ERROR",
            exception=str(e)
        )


@router.get(
    "/google/token/{user_id}",
    dependencies=[Depends(require_internal_secret)],
)
async def google_oauth_get_token(user_id: str):
    """
    Get a valid Google access token for a user. **Internal only** — requires
    Authorization: Bearer <MOLTBOT_INTERNAL_SECRET>.

    Called by the OpenClaw Gateway to bridge OAuth tokens to bash skills.
    The token auto-refreshes if expired.
    """
    try:
        # Get valid token (auto-refreshes if expired)
        token = await credential_manager.get_valid_google_token(user_id)

        if token:
            return create_response(
                code=ResponseCode.SUCCESS,
                message="OAuth token retrieved successfully",
                data={
                    "access_token": token,
                    "token_type": "Bearer"
                }
            )
        else:
            return create_error_response(
                code=ResponseCode.NOT_FOUND,
                message="No Google account connected for this user",
                error="NOT_CONNECTED",
                exception=None
            )
    except Exception as e:
        logger.error(f"Error getting OAuth token for user {user_id}: {e}")
        return create_error_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Failed to get OAuth token",
            error="TOKEN_RETRIEVAL_ERROR",
            exception=str(e)
        )
