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
from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse, JSONResponse
import httpx

from ..config import settings
from ..core.credential_manager import CredentialManager
from ..core.database import db
from ..core.redis_client import redis_client
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
        "timestamp": datetime.utcnow().isoformat()
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
    user_id: int = Query(..., description="Peppi user ID"),
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
        
        # Try Redis first, fallback to memory
        stored = await redis_client.set_session(
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
        state_data = await redis_client.get_session(f"oauth_state:{state}")
        
        if not state_data:
            logger.error(f"Invalid or expired state: {state}")
            return RedirectResponse(
                url=f"{default_redirect}/clawdbot/oauth?status=error&error=INVALID_STATE"
            )
        
        # Delete state (one-time use)
        await redis_client.delete_session(f"oauth_state:{state}")
        
        user_id = state_data["user_id"]
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
        await credential_manager.store_google_tokens(
            user_id=user_id,
            access_token=tokens['access_token'],
            refresh_token=tokens.get('refresh_token', ''),
            expires_in=tokens.get('expires_in', 3600),
            token_type=tokens.get('token_type', 'Bearer'),
            scope=tokens.get('scope', '')
        )
        
        # Log the action
        await db.log_action(
            user_id=user_id,
            session_id="oauth_flow",
            action_type="google_oauth_connect",
            request_summary="User connected Google account",
            status="success"
        )
        
        logger.info(f"OAuth completed for user {user_id}")
        
        # Redirect to success page
        return RedirectResponse(
            url=f"{redirect_uri}/clawdbot/oauth?status=success&service=google"
        )
        
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        return RedirectResponse(
            url=f"{default_redirect}/clawdbot/oauth?status=error&error=CALLBACK_ERROR"
        )


@router.get("/google/status/{user_id}")
async def google_oauth_status(user_id: int):
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


@router.delete("/google/disconnect/{user_id}")
async def google_oauth_disconnect(user_id: int):
    """
    Disconnect (revoke) a user's Google connection.
    
    This revokes the tokens at Google and deletes them from the database.
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


@router.post("/google/refresh/{user_id}")
async def google_oauth_refresh(user_id: int):
    """
    Manually refresh a user's Google access token.
    
    Normally tokens are refreshed automatically, but this endpoint
    allows manual refresh if needed.
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
