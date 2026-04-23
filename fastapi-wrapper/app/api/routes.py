"""
Main API routes for OpenClaw Wrapper.
Handles action execution, health checks, and credential management.

All responses follow the standardized DTO format:
- code: HTTP status code
- message: Human-readable message
- data: Response payload
- error: Error type/code
- exception: Exception details

Note: Rate limiting is handled by Peppi (Laravel), not here.
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging
import traceback
from ..utils.timezone_utils import now_utc_naive

from ..models import (
    BaseResponse,
    ResponseCode,
    ExecuteActionRequest,
    ExecuteActionData,
    HealthData,
    SessionData,
    ConversationData,
    CredentialsStatusData,
    ActionHistoryData,
    StoreCredentialsRequest,
    success_response,
    error_response
)
from ..core.session_manager import SessionManager
from ..core.credential_manager import CredentialManager
from ..core.moltbot_client import OpenClawClient, OpenClawClientError
from ..core.database import db
from ..core.redis_client import redis_client
from ..core.auth import require_internal_secret

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize managers
session_manager = SessionManager()
credential_manager = CredentialManager()
openclaw_client = OpenClawClient()


# ==================== Exception Handler ====================

def create_error_response(
    code: int,
    message: str,
    error: str,
    exception: str = None
) -> JSONResponse:
    """Create a standardized error JSON response"""
    return JSONResponse(
        status_code=code,
        content={
            "code": code,
            "message": message,
            "data": None,
            "error": error,
            "exception": exception,
            "timestamp": now_utc_naive().isoformat()
        }
    )


# ==================== Health & Status ====================

@router.get("/health")
async def health_check():
    """
    Health check endpoint with detailed status of all services.
    """
    try:
        # Check all services
        openclaw_ok = await openclaw_client.health_check()
        redis_ok = await redis_client.health_check()
        db_ok = await db.health_check()
        active_sessions = await session_manager.get_active_sessions_count()
        
        all_ok = all([openclaw_ok, redis_ok, db_ok])
        
        return {
            "code": ResponseCode.SUCCESS,
            "message": "Service health check completed",
            "data": {
                "status": "healthy" if all_ok else "degraded",
                "openclaw_gateway": "online" if openclaw_ok else "offline",
                "redis": redis_ok,
                "supabase": db_ok,
                "active_sessions": active_sessions
            },
            "error": None,
            "exception": None,
            "timestamp": now_utc_naive().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return create_error_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Health check failed",
            error="HEALTH_CHECK_ERROR",
            exception=str(e)
        )


# ==================== Action Execution ====================

@router.post(
    "/execute-action",
    dependencies=[Depends(require_internal_secret)],
)
async def execute_action(request: ExecuteActionRequest):
    """
    Execute action via OpenClaw.
    
    This is the main endpoint that Peppi calls to process user SMS messages.
    Rate limiting is handled by Peppi (Laravel) before calling this endpoint.
    
    Flow:
    1. Acquire user lock (prevent concurrent requests)
    2. Create/get session
    3. Get user credentials
    4. Call OpenClaw with retry logic (3 attempts)
    5. Store response
    6. Log action
    7. Release lock
    
    Response format:
    {
        "code": 200,
        "message": "Action executed successfully",
        "data": {
            "session_id": "sess_xxx",
            "response": "AI response",
            "action_performed": "calendar_create",
            "details": {}
        },
        "error": null,
        "exception": null
    }
    """
    user_id = request.user_id
    log_id = None
    lock_token: Optional[str] = None

    # 0a. Pre-validate input shape: must have *something* to act on.
    # Empty text + no images is a no-op — return a friendly chat reply (200)
    # instead of forwarding to the gateway just to get a 400 back.
    has_images = bool(request.image_urls)
    has_text = bool((request.message or "").strip())
    if not has_text and not has_images:
        return {
            "code": ResponseCode.SUCCESS,
            "message": "Action executed successfully",
            "data": {
                "session_id": "",
                "response": "I didn't catch a message. What would you like me to do? I can schedule meetings, set reminders, send emails, or work with photos you send me.",
                "action_performed": "chat",
                "tokens_used": None,
                "input_tokens": None,
                "output_tokens": None,
                "cache_read": None,
                "cache_write": None,
                "reminder_trigger_at": None,
            },
            "error": None,
            "exception": None,
            "timestamp": now_utc_naive().isoformat(),
        }

    try:
        # 0. Validate user_id exists in database
        existing_user = await db.get_user(user_id)
        if not existing_user:
            logger.warning(f"Unknown user_id: {user_id}")
            return create_error_response(
                code=ResponseCode.NOT_FOUND,
                message=f"User '{user_id}' not found. Please register the user first.",
                error="USER_NOT_FOUND",
                exception=None
            )

        # 1. Acquire user lock to prevent concurrent processing. Token is
        # threaded to release so we only ever DEL the lock if we still own
        # it — protects against mid-turn TTL expiry handing the lock to a
        # second request, which our `finally` would otherwise release.
        lock_token = await session_manager.acquire_user_lock(user_id)
        if not lock_token:
            return create_error_response(
                code=ResponseCode.SERVICE_UNAVAILABLE,
                message="Request already in progress for this user, please wait",
                error="USER_LOCKED",
                exception=None
            )
        
        # 2. Create or get session
        session_id = await session_manager.create_session(user_id)
        session_data = await session_manager.get_session(session_id, user_id)
        
        if not session_data:
            return create_error_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to create session",
                error="SESSION_CREATE_FAILED",
                exception=None
            )
        
        # 3. Get user credentials
        user_credentials = request.credentials
        if not user_credentials:
            # Try to get Google OAuth token if available
            try:
                google_token = await credential_manager.get_valid_google_token(user_id)
                if google_token:
                    user_credentials = {"google_access_token": google_token}
            except Exception:
                pass  # skip Google token on error

        # 3b. Get user context (bot name, preferences, etc.)
        user_context = await session_manager.get_user_context(session_id, user_id)
        logger.debug(f"Retrieved user context for {user_id}: {user_context}")
        
        # 4. Log action start (include image count if present)
        img_prefix = f"[{request.num_media} image(s)] " if request.num_media else ""
        log_id = await db.log_action(
            user_id=user_id,
            session_id=session_id,
            action_type="execute_action",
            request_summary=img_prefix + request.message[:2000],
            status="pending"
        )
        
        # Note: We skip saving to Redis conversation_history — Peppi already
        # provides full chat history in context. Redis is only used for session_id mapping.
        
        # 6. Call OpenClaw with retry logic (+ retry on empty payloads)
        MAX_EMPTY_RETRIES = 2
        clean_response = None
        tokens_used = 0
        openclaw_response = None

        for attempt in range(1, MAX_EMPTY_RETRIES + 1):
            try:
                openclaw_response = await openclaw_client.send_message(
                    session_id=session_id,
                    message=request.message,
                    user_id=user_id,
                    timezone=request.timezone,
                    user_credentials=user_credentials,
                    # Peppi sends full context; playground has no context so would use Redis history.
                    # Gateway ignores the history field anyway, so always send empty.
                    conversation_history=[],
                    user_context=user_context,
                    image_urls=request.image_urls
                )
            except OpenClawClientError as e:
                logger.error(f"OpenClaw call failed: {e.message} (type: {e.error_type})")

                # Special-case: gateway-side timeout for image-heavy requests.
                # The gateway already returns a graceful 200 in that path, but if
                # it ever surfaces as a 5xx (e.g., underlying socket reset), we
                # still want to give the user a usable reply rather than HTTP 500.
                msg_lower = (e.message or "").lower()
                is_timeout_like = (
                    e.error_type in ("TIMEOUT", "HTTP_ERROR")
                    and ("timed out" in msg_lower or "timeout" in msg_lower)
                )
                if is_timeout_like:
                    if request.image_urls:
                        friendly = (
                            "Processing your image is taking longer than usual. "
                            "Please retry, or send a smaller/clearer image and tell me "
                            "exactly what to do with it (schedule, remind, email)."
                        )
                    else:
                        friendly = (
                            "I'm taking longer than usual to finish that. Please try again "
                            "— if it was an action like creating an event, double-check before "
                            "retrying so we don't duplicate it."
                        )
                    if log_id:
                        await db.update_action_log(
                            log_id=log_id,
                            status="failed",
                            error_message=f"timeout fallback: {e.message}",
                        )
                    return {
                        "code": ResponseCode.SUCCESS,
                        "message": "Action executed successfully",
                        "data": {
                            "session_id": session_id,
                            "response": friendly,
                            "action_performed": "chat",
                            "tokens_used": None,
                            "input_tokens": None,
                            "output_tokens": None,
                            "cache_read": None,
                            "cache_write": None,
                            "reminder_trigger_at": None,
                        },
                        "error": None,
                        "exception": None,
                        "timestamp": now_utc_naive().isoformat(),
                    }

                if log_id:
                    await db.update_action_log(
                        log_id=log_id,
                        status="failed",
                        error_message=e.message
                    )

                return create_error_response(
                    code=ResponseCode.SERVICE_UNAVAILABLE if e.retryable else ResponseCode.INTERNAL_ERROR,
                    message="Failed to process your request. Please try again.",
                    error=e.error_type,
                    exception=e.message
                )

            # 7. Parse and clean the response
            raw_response = openclaw_response.get('response', 'Action completed')
            tokens_used = openclaw_response.get('tokens_used', 0) or 0
            input_tokens = openclaw_response.get('input_tokens', 0) or 0
            output_tokens = openclaw_response.get('output_tokens', 0) or 0
            cache_read = openclaw_response.get('cache_read', 0) or 0
            cache_write = openclaw_response.get('cache_write', 0) or 0

            try:
                import json
                parsed_response = json.loads(raw_response)

                # Extract text payloads — skip thinking blocks (type: "thinking")
                # Bug: thinking-only payloads have no 'text' key, so payloads[0].get('text','')
                # returns '' and the fallback chain below was never reached.
                payloads = parsed_response.get('payloads', [])
                text_payloads = [p for p in payloads if p.get('type') != 'thinking']

                if text_payloads:
                    clean_response = '\n'.join(
                        p.get('text') or p.get('content') or ''
                        for p in text_payloads
                    ).strip() or None
                else:
                    clean_response = None

                if not clean_response:
                    # Gemini/OpenClaw may return in different formats — try all known fields
                    clean_response = (
                        parsed_response.get('response')
                        or parsed_response.get('message')
                        or parsed_response.get('text')
                        or parsed_response.get('output')
                        or parsed_response.get('content')
                        or None
                    )
                    if clean_response:
                        logger.info(f"[{session_id}] Used fallback field (no text payloads)")
                    else:
                        payload_types = [p.get('type', 'unknown') for p in payloads]
                        logger.warning(
                            f"[{session_id}] No text found in response. "
                            f"Keys: {list(parsed_response.keys())[:10]}, "
                            f"Payload types: {payload_types}, "
                            f"Preview: {raw_response[:300]}"
                        )

                # Extract token usage from meta if gateway didn't provide it
                if not tokens_used:
                    meta = parsed_response.get('meta', {})
                    agent_meta = meta.get('agentMeta', meta.get('agent_meta', {}))
                    usage = agent_meta.get('usage', meta.get('usage', {}))
                    tokens_used = (
                        usage.get('totalTokenCount', 0)
                        or usage.get('total_token_count', 0)
                        or usage.get('total_tokens', 0)
                        or usage.get('total', 0)
                    )

            except (json.JSONDecodeError, AttributeError, KeyError):
                clean_response = raw_response

            # If we got a valid non-empty response, break out of retry loop
            if clean_response and clean_response.strip():
                break

            # --- Smart retry: only retry for chat-like actions ---
            # If the agent performed a side-effect action (gmail, calendar, etc.),
            # retrying would double-execute it. Use a fallback message instead.
            detected_action = (openclaw_response.get('action_type') or '').lower()
            SIDE_EFFECT_ACTIONS = (
                'gmail', 'calendar', 'reminder', 'email', 'send', 'create',
                'delete', 'update', 'schedule', 'compose', 'draft',
            )
            # action_type from OpenClaw defaults to 'chat' even for Gmail/Calendar actions.
            # Also check the user's message to detect side-effect operations.
            message_lower = (request.message or '').lower()
            MESSAGE_SIDE_EFFECT_KEYWORDS = (
                'inbox', 'email', 'mail', 'calendar', 'meet', 'schedule',
                'reminder', 'remind', 'appointment', 'event', 'send', 'compose',
            )
            has_side_effects = (
                any(kw in detected_action for kw in SIDE_EFFECT_ACTIONS)
                or any(kw in message_lower for kw in MESSAGE_SIDE_EFFECT_KEYWORDS)
            )

            if has_side_effects:
                # Action already executed — don't retry (would double-execute).
                # Build a context-aware fallback message.
                if any(kw in message_lower for kw in ('inbox', 'email', 'mail', 'compose', 'send')):
                    clean_response = "I checked your inbox but couldn't format the response properly. Please try asking again."
                elif any(kw in message_lower for kw in ('calendar', 'meet', 'schedule', 'appointment', 'event')):
                    clean_response = "I processed your calendar request. Please check your Google Calendar to confirm."
                elif any(kw in message_lower for kw in ('remind', 'reminder')):
                    clean_response = "Your reminder has been set."
                else:
                    clean_response = "Done! Your request has been processed."
                logger.warning(
                    f"[{session_id}] Empty payloads but side-effect action detected "
                    f"(action_type='{detected_action}', message_keywords matched) — using fallback response"
                )
                break

            # Chat-like action — safe to retry
            if attempt < MAX_EMPTY_RETRIES:
                logger.warning(
                    f"[{session_id}] Empty payloads on attempt {attempt}/{MAX_EMPTY_RETRIES}, retrying..."
                )
            else:
                logger.error(
                    f"[{session_id}] Empty payloads after {MAX_EMPTY_RETRIES} attempts — returning error"
                )

        # If still empty after all retries, return 500 error
        if not clean_response or not clean_response.strip():
            if log_id:
                await db.update_action_log(
                    log_id=log_id,
                    status="failed",
                    error_message="Agent returned empty response (empty payloads)",
                    tokens_used=tokens_used,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_read=cache_read,
                    cache_write=cache_write
                )
            return create_error_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Agent returned an empty response. Please try again.",
                error="EMPTY_RESPONSE",
                exception=f"OpenClaw returned empty payloads after {MAX_EMPTY_RETRIES} attempts"
            )

        # Final fallback: Estimate tokens from character count (~3.5 chars/token for Claude)
        if not tokens_used:
            input_chars = len(request.message or '')
            output_chars = len(clean_response or '')
            # Add ~500 tokens for system prompt/context overhead
            tokens_used = max(1, round((input_chars + output_chars) / 3.5) + 500)
            logger.info(f"Token estimation: input={input_chars}c output={output_chars}c → ~{tokens_used} tokens")

        # Skip saving assistant response to Redis — Peppi manages its own history

        # 8. Update session context
        await session_manager.update_context(session_id, user_id, {
            "last_action": openclaw_response.get('action_type'),
            "pending_action": None
        })

        # 9. Update action log
        if log_id:
            await db.update_action_log(
                log_id=log_id,
                status="success",
                response_summary=clean_response[:2000] if clean_response else "Action completed",
                tokens_used=tokens_used,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read=cache_read,
                cache_write=cache_write
            )

        # 10. If reminder action, fetch the most recently created pending reminder's trigger_at
        # so the playground can show a live countdown timer.
        reminder_trigger_at = None
        action_type_str = (openclaw_response.get('action_type') or '').lower()
        if 'reminder' in action_type_str:
            try:
                pending = await db.get_user_reminders(user_id, status='pending')
                if pending:
                    # reminders are ordered by trigger_at desc, but we want the most recently *created*
                    # The last one inserted will have the largest id
                    latest = max(pending, key=lambda r: r.get('id', 0))
                    reminder_trigger_at = latest.get('trigger_at')
            except Exception as reminder_err:
                logger.warning(f"Could not fetch reminder trigger_at: {reminder_err}")

        # 11. Return clean success response
        return {
            "code": ResponseCode.SUCCESS,
            "message": "Action executed successfully",
            "data": {
                "session_id": session_id,
                "response": clean_response,
                "action_performed": openclaw_response.get('action_type'),
                "tokens_used": tokens_used if tokens_used > 0 else None,
                "input_tokens": input_tokens if input_tokens > 0 else None,
                "output_tokens": output_tokens if output_tokens > 0 else None,
                "cache_read": cache_read if cache_read > 0 else None,
                "cache_write": cache_write if cache_write > 0 else None,
                "reminder_trigger_at": reminder_trigger_at,
            },
            "error": None,
            "exception": None,
            "timestamp": now_utc_naive().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error executing action: {e}\n{traceback.format_exc()}")
        
        # Log failure
        if log_id:
            await db.update_action_log(
                log_id=log_id,
                status="failed",
                error_message=str(e)
            )
        
        return create_error_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="An unexpected error occurred",
            error="UNEXPECTED_ERROR",
            exception=str(e)
        )
    
    finally:
        # Always release the lock if we acquired it. The token ensures we
        # only DEL the key when WE still own it — a mid-turn TTL expiry
        # that handed the lock to another request leaves that request's
        # lock alone.
        if lock_token:
            await session_manager.release_user_lock(user_id, lock_token)


# ==================== Session Management ====================

@router.get("/session/{user_id}")
async def get_user_session(user_id: str):
    """Get current session info for a user."""
    try:
        session_id = await session_manager.get_active_session_for_user(user_id)
        
        if not session_id:
            return create_error_response(
                code=ResponseCode.NOT_FOUND,
                message="No active session found",
                error="SESSION_NOT_FOUND",
                exception=None
            )
        
        session_data = await session_manager.get_session(session_id, user_id)
        
        if not session_data:
            return create_error_response(
                code=ResponseCode.NOT_FOUND,
                message="Session data not found",
                error="SESSION_DATA_NOT_FOUND",
                exception=None
            )
        
        return {
            "code": ResponseCode.SUCCESS,
            "message": "Session retrieved successfully",
            "data": {
                "session_id": session_id,
                "user_id": user_id,
                "created_at": session_data.get('created_at', ''),
                "last_activity": session_data.get('last_activity', ''),
                "message_count": session_data.get('metadata', {}).get('message_count', 0)
            },
            "error": None,
            "exception": None,
            "timestamp": now_utc_naive().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting session: {e}")
        return create_error_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Failed to get session",
            error="SESSION_GET_ERROR",
            exception=str(e)
        )


@router.delete("/session/{user_id}")
async def clear_user_session(user_id: str):
    """Clear/delete a user's session."""
    try:
        session_id = await session_manager.get_active_session_for_user(user_id)
        
        if not session_id:
            return {
                "code": ResponseCode.SUCCESS,
                "message": "No active session to clear",
                "data": {"cleared": False},
                "error": None,
                "exception": None,
                "timestamp": now_utc_naive().isoformat()
            }
        
        await session_manager.delete_session(session_id, user_id)
        
        return {
            "code": ResponseCode.SUCCESS,
            "message": "Session cleared successfully",
            "data": {"cleared": True, "session_id": session_id},
            "error": None,
            "exception": None,
            "timestamp": now_utc_naive().isoformat()
        }
    except Exception as e:
        logger.error(f"Error clearing session: {e}")
        return create_error_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Failed to clear session",
            error="SESSION_CLEAR_ERROR",
            exception=str(e)
        )


@router.get("/session/{user_id}/history")
async def get_conversation_history(user_id: str, limit: int = 20):
    """Get conversation history for a user."""
    try:
        session_id = await session_manager.get_active_session_for_user(user_id)
        
        if not session_id:
            return create_error_response(
                code=ResponseCode.NOT_FOUND,
                message="No active session found",
                error="SESSION_NOT_FOUND",
                exception=None
            )
        
        history = await session_manager.get_conversation_history(session_id, user_id, limit)
        
        return {
            "code": ResponseCode.SUCCESS,
            "message": "Conversation history retrieved",
            "data": {
                "session_id": session_id,
                "messages": history,
                "total_messages": len(history)
            },
            "error": None,
            "exception": None,
            "timestamp": now_utc_naive().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        return create_error_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Failed to get conversation history",
            error="HISTORY_GET_ERROR",
            exception=str(e)
        )


# ==================== Credentials ====================

@router.post("/credentials/store")
async def store_credentials(request: StoreCredentialsRequest):
    """Store user service credentials."""
    try:
        success = await credential_manager.store_credentials(
            user_id=request.user_id,
            service=request.service,
            credentials=request.credentials
        )
        
        if success:
            return {
                "code": ResponseCode.SUCCESS,
                "message": "Credentials stored successfully",
                "data": {"stored": True, "service": request.service},
                "error": None,
                "exception": None,
                "timestamp": now_utc_naive().isoformat()
            }
        else:
            return create_error_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to store credentials",
                error="CREDENTIALS_STORE_FAILED",
                exception=None
            )
    except Exception as e:
        logger.error(f"Error storing credentials: {e}")
        return create_error_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Failed to store credentials",
            error="CREDENTIALS_STORE_ERROR",
            exception=str(e)
        )


@router.delete("/credentials/{user_id}/{service}")
async def delete_credentials(user_id: str, service: str):
    """Delete user service credentials."""
    try:
        success = await credential_manager.delete_credentials(user_id, service)
        
        if success:
            return {
                "code": ResponseCode.SUCCESS,
                "message": "Credentials deleted successfully",
                "data": {"deleted": True, "service": service},
                "error": None,
                "exception": None,
                "timestamp": now_utc_naive().isoformat()
            }
        else:
            return create_error_response(
                code=ResponseCode.NOT_FOUND,
                message="Credentials not found",
                error="CREDENTIALS_NOT_FOUND",
                exception=None
            )
    except Exception as e:
        logger.error(f"Error deleting credentials: {e}")
        return create_error_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Failed to delete credentials",
            error="CREDENTIALS_DELETE_ERROR",
            exception=str(e)
        )


@router.get("/credentials/{user_id}/status")
async def get_credentials_status(user_id: str):
    """Get status of all credentials for a user."""
    try:
        all_creds = await credential_manager.get_all_credentials(user_id)
        
        # Check Google OAuth separately
        google_status = await credential_manager.get_google_connection_status(user_id)
        
        services = {service: True for service in all_creds.keys()}
        services['google'] = google_status['connected']
        
        return {
            "code": ResponseCode.SUCCESS,
            "message": "Credentials status retrieved",
            "data": {
                "user_id": user_id,
                "services": services
            },
            "error": None,
            "exception": None,
            "timestamp": now_utc_naive().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting credentials status: {e}")
        return create_error_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Failed to get credentials status",
            error="CREDENTIALS_STATUS_ERROR",
            exception=str(e)
        )


# ==================== Action History ====================

@router.get("/history/{user_id}")
async def get_action_history(user_id: str, limit: int = 50, offset: int = 0):
    """Get action history for a user from audit log."""
    try:
        actions = await db.get_user_action_history(user_id, limit, offset)
        
        # Convert datetime objects to strings (Supabase may return strings already)
        for action in actions:
            if 'created_at' in action and action['created_at']:
                if hasattr(action['created_at'], 'isoformat'):
                    action['created_at'] = action['created_at'].isoformat()
                # else: already a string, leave as-is
        
        return {
            "code": ResponseCode.SUCCESS,
            "message": "Action history retrieved",
            "data": {
                "user_id": user_id,
                "actions": actions,
                "total": len(actions)
            },
            "error": None,
            "exception": None,
            "timestamp": now_utc_naive().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting action history: {e}")
        return create_error_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Failed to get action history",
            error="HISTORY_GET_ERROR",
            exception=str(e)
        )