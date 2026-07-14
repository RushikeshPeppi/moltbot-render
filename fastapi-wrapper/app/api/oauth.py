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
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse, JSONResponse
import httpx

from ..config import settings
from ..core.service_auth import require_service_auth
from ..core.rate_limit import limit_oauth_callback, limit_oauth_init
from ..core.redirect_validation import is_allowed_redirect, origin_of, safe_redirect_base
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
    """Create standardized response. `exception` sanitized — never raw in prod (P2-5).

    create_error_response() below delegates here, so both OAuth builders are covered
    by this one choke point.
    """
    from ..core.error_sanitizer import client_safe_exception
    return {
        "code": code,
        "message": message,
        "data": data,
        "error": error,
        "exception": client_safe_exception(exception),
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


def build_peppi_redirect(base: str, default_redirect: str, params: dict) -> str:
    """Build the 302 target back to the caller (Peppi website / playground).

    A bare website origin (the safe default) gets the legacy /clawdbot/oauth page
    appended; an explicit callback URL (Peppi's /auth/google/callback, the
    playground's /oauth-callback) is used as-is. None-valued params are omitted —
    in particular `app_state` is only echoed when one was stored for this flow
    (CASA 3.2.2: Peppi validates it against the session nonce on success AND error).
    """
    if base == default_redirect and not any(
        p in base for p in ("/oauth-callback", "/callback")
    ):
        base = f"{base}/clawdbot/oauth"
    query = urlencode({k: v for k, v in params.items() if v is not None})
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{query}"


@router.get(
    "/google/init",
    dependencies=[Depends(require_service_auth), Depends(limit_oauth_init)],
)
async def google_oauth_init(
    user_id: str = Query(..., description="Peppi user ID"),
    redirect_uri: Optional[str] = Query(None, description="Where to redirect after OAuth completes"),
    app_state: Optional[str] = Query(
        None,
        description=(
            "Opaque first-party CSRF nonce minted by the caller (Peppi). Stored "
            "verbatim and echoed back on the post-callback redirect — never sent "
            "to Google, never parsed (CASA 3.2.2)."
        ),
    )
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

        # CASA 3.2.2 — never honor an arbitrary post-callback redirect_uri. Reject
        # anything not on the allow-list up front (None → the safe default below).
        if redirect_uri and not is_allowed_redirect(redirect_uri):
            # Log only the origin (never the full URL) so a misconfigured caller
            # (e.g. Peppi's GOOGLE_REDIRECT_URI left relative) is diagnosable.
            logger.warning(
                f"OAuth init rejected off-allowlist redirect_uri "
                f"(origin={origin_of(redirect_uri)!r}) for user {user_id}"
            )
            return create_error_response(
                code=ResponseCode.BAD_REQUEST,
                message="redirect_uri is not allow-listed",
                error="INVALID_REDIRECT_URI",
                exception=None
            )

        # Generate state for CSRF protection
        state = secrets.token_urlsafe(32)

        # Store state in Redis with 10 minute expiration
        state_data = {
            "user_id": user_id,
            "redirect_uri": redirect_uri or settings.PEPPI_WEBSITE_URL,
            # Opaque Peppi-side CSRF nonce, echoed back verbatim on the final
            # redirect (success and error). Empty string is treated as absent so
            # the echo is omitted entirely rather than sent as `app_state=`.
            "app_state": app_state or None
        }
        
        # Store OAuth state in Redis
        stored = await redis_client.set(
            f"oauth_state:{state}",
            state_data,
            ttl=600  # 10 minutes
        )

        if not stored:
            # Fail closed: without the stored state the callback can only ever
            # end in INVALID_STATE, so sending the user to Google's consent
            # screen would burn a full flow for a guaranteed failure.
            logger.error("OAuth init: failed to store state in Redis")
            return create_error_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to persist OAuth state",
                error="STATE_STORAGE_FAILED",
                exception=None
            )
        
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


# PUBLIC (Google redirects the user's browser here) — the only anonymous-reachable route
# in this router, so it is the one that gets a rate limit (P2-4).
@router.get("/google/callback", dependencies=[Depends(limit_oauth_callback)])
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
    # Resolved as soon as the state blob is loaded; the except handler below uses
    # whatever was resolved by the time of the failure.
    redirect_uri = default_redirect
    app_state = None

    def peppi_redirect(base: str, params: dict) -> RedirectResponse:
        return RedirectResponse(
            url=build_peppi_redirect(base, default_redirect, params)
        )

    async def recover_and_burn_state() -> None:
        """On early-exit paths, recover the stored redirect_uri + app_state from
        the state blob (so Peppi can validate the origin and clear its session
        nonce even on failure — CASA 3.2.2) and burn the state (single-use)."""
        nonlocal redirect_uri, app_state
        if not state:
            return
        try:
            state_data = await redis_client.get(f"oauth_state:{state}")
            if state_data:
                await redis_client.delete(f"oauth_state:{state}")
                redirect_uri = safe_redirect_base(
                    state_data.get("redirect_uri") or default_redirect,
                    default_redirect,
                )
                app_state = state_data.get("app_state")
        except Exception as e:
            logger.error(f"Failed to load state on early-exit path: {e}")

    # Handle Google errors (user declined consent, etc.). Google echoes our
    # `state` on error redirects too — recover the blob so the app_state echo
    # reaches Peppi on the error path as well.
    if error:
        # repr + truncate: `error` is attacker-controlled input on a public
        # endpoint — never interpolate it raw (log-line injection, CWE-117).
        logger.error("OAuth error from Google: %r", (error or "")[:64])
        await recover_and_burn_state()
        return peppi_redirect(redirect_uri, {
            "status": "error",
            "error": "GOOGLE_DENIED",
            "app_state": app_state,
        })

    # Validate required parameters
    if not code or not state:
        logger.error("Missing code or state parameter")
        await recover_and_burn_state()
        return peppi_redirect(redirect_uri, {
            "status": "error",
            "error": "INVALID_REQUEST",
            "app_state": app_state,
        })

    try:
        # Get state data from Redis
        state_data = await redis_client.get(f"oauth_state:{state}")

        if not state_data:
            # Don't print the state value — attacker-controlled on a public
            # endpoint, and main.py deliberately redacts it from query logs.
            logger.error("Invalid or expired OAuth state (not found in Redis)")
            return peppi_redirect(default_redirect, {
                "status": "error",
                "error": "INVALID_STATE",
            })

        # Delete state (one-time use)
        await redis_client.delete(f"oauth_state:{state}")

        # Opaque Peppi CSRF nonce — echoed verbatim on every outcome below.
        app_state = state_data.get("app_state")

        # CASA 3.2.2 — re-validate the stored redirect_uri (defense-in-depth against a
        # stale/tampered state blob); fall back to the safe default if not allow-listed.
        redirect_uri = safe_redirect_base(
            state_data.get("redirect_uri") or default_redirect, default_redirect
        )

        # Extract user_id
        user_id = str(state_data.get("user_id", ""))
        if not user_id:
            # Log keys only — the blob carries app_state (a live CSRF nonce)
            # and the redirect_uri; neither belongs in logs.
            logger.error(f"Missing user_id in state data (keys={list(state_data.keys())})")
            return peppi_redirect(redirect_uri, {
                "status": "error",
                "error": "INVALID_USER_ID",
                "app_state": app_state,
            })

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
            return peppi_redirect(redirect_uri, {
                "status": "error",
                "error": "TOKEN_EXCHANGE_FAILED",
                "app_state": app_state,
            })
        
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
                return peppi_redirect(redirect_uri, {
                    "status": "error",
                    "error": "TOKEN_STORAGE_FAILED",
                    "app_state": app_state,
                })
        except Exception as e:
            logger.error(f"Exception storing tokens for user {user_id}: {e}")
            return peppi_redirect(redirect_uri, {
                "status": "error",
                "error": "TOKEN_STORAGE_ERROR",
                "app_state": app_state,
            })

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

        # Redirect to success page. build_peppi_redirect appends /clawdbot/oauth
        # only for the bare website default; explicit callback URLs (Peppi's
        # /auth/google/callback, playground's /oauth-callback) are used as-is.
        return peppi_redirect(redirect_uri, {
            "status": "success",
            "service": "google",
            "user_id": user_id,
            "app_state": app_state,
        })

    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        return peppi_redirect(redirect_uri, {
            "status": "error",
            "error": "CALLBACK_ERROR",
            "app_state": app_state,
        })


@router.get("/google/status/{user_id}", dependencies=[Depends(require_service_auth)])
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


@router.delete("/google/disconnect/{user_id}", dependencies=[Depends(require_service_auth)])
async def google_oauth_disconnect(user_id: str):
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


@router.post("/google/refresh/{user_id}", dependencies=[Depends(require_service_auth)])
async def google_oauth_refresh(user_id: str):
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


@router.get("/google/token/{user_id}", dependencies=[Depends(require_service_auth)])
async def google_oauth_get_token(user_id: str):
    """
    Get a valid Google access token for a user.

    This endpoint is used by the OpenClaw Gateway to fetch OAuth tokens
    for GOG skill integration. The token is automatically refreshed if expired.

    Used internally for OAuth token bridge between FastAPI and OpenClaw.
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
