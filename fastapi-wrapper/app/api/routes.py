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

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging
import traceback

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
            "timestamp": datetime.utcnow().isoformat()
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
            "timestamp": datetime.utcnow().isoformat()
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

@router.post("/execute-action")
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
    lock_acquired = False
    
    try:
        # 1. Acquire user lock to prevent concurrent processing
        lock_acquired = await session_manager.acquire_user_lock(user_id)
        if not lock_acquired:
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
                google_token = await credential_manager.get_valid_google_token(int(user_id))
                if google_token:
                    user_credentials = {"google_access_token": google_token}
            except ValueError:
                pass  # user_id is not a valid int, skip Google token

        # 3b. Get user context (bot name, preferences, etc.)
        user_context = await session_manager.get_user_context(session_id, user_id)
        logger.debug(f"Retrieved user context for {user_id}: {user_context}")
        
        # 4. Log action start
        log_id = await db.log_action(
            user_id=int(user_id) if user_id.isdigit() else 0,
            session_id=session_id,
            action_type="execute_action",
            request_summary=request.message[:200],
            status="pending"
        )
        
        # 5. Add user message to history
        await session_manager.add_message(session_id, user_id, "user", request.message)
        
        # 6. Call OpenClaw with retry logic
        try:
            # Pass user_id for OAuth token bridge in OpenClaw gateway
            user_id_int = int(user_id) if str(user_id).isdigit() else None

            openclaw_response = await openclaw_client.send_message(
                session_id=session_id,
                message=request.message,
                user_id=user_id_int,  # Pass user_id for OAuth token bridge
                timezone=request.timezone,  # Pass user's timezone
                user_credentials=user_credentials,
                conversation_history=session_data.get('conversation_history', []),
                user_context=user_context  # Pass user-specific context
            )
        except OpenClawClientError as e:
            # OpenClaw call failed after retries
            logger.error(f"OpenClaw call failed: {e.message} (type: {e.error_type})")
            
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
        
        # 7. Add assistant response to history
        assistant_message = openclaw_response.get('response', 'Action completed')
        await session_manager.add_message(session_id, user_id, "assistant", assistant_message)
        
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
                response_summary=assistant_message[:200],
                tokens_used=openclaw_response.get('tokens_used', 0)
            )
        
        # 10. Return success response
        return {
            "code": ResponseCode.SUCCESS,
            "message": "Action executed successfully",
            "data": {
                "session_id": session_id,
                "response": assistant_message,
                "action_performed": openclaw_response.get('action_type'),
                "details": openclaw_response.get('details')
            },
            "error": None,
            "exception": None,
            "timestamp": datetime.utcnow().isoformat()
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
        # Always release lock if acquired
        if lock_acquired:
            await session_manager.release_user_lock(user_id)


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
            "timestamp": datetime.utcnow().isoformat()
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
                "timestamp": datetime.utcnow().isoformat()
            }
        
        await session_manager.delete_session(session_id, user_id)
        
        return {
            "code": ResponseCode.SUCCESS,
            "message": "Session cleared successfully",
            "data": {"cleared": True, "session_id": session_id},
            "error": None,
            "exception": None,
            "timestamp": datetime.utcnow().isoformat()
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
            "timestamp": datetime.utcnow().isoformat()
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
            user_id=int(request.user_id) if request.user_id.isdigit() else 0,
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
                "timestamp": datetime.utcnow().isoformat()
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
        user_id_int = int(user_id) if user_id.isdigit() else 0
        success = await credential_manager.delete_credentials(user_id_int, service)
        
        if success:
            return {
                "code": ResponseCode.SUCCESS,
                "message": "Credentials deleted successfully",
                "data": {"deleted": True, "service": service},
                "error": None,
                "exception": None,
                "timestamp": datetime.utcnow().isoformat()
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
        user_id_int = int(user_id) if user_id.isdigit() else 0
        all_creds = await credential_manager.get_all_credentials(user_id_int)
        
        # Check Google OAuth separately
        google_status = await credential_manager.get_google_connection_status(user_id_int)
        
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
            "timestamp": datetime.utcnow().isoformat()
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
        user_id_int = int(user_id) if user_id.isdigit() else 0
        actions = await db.get_user_action_history(user_id_int, limit, offset)
        
        # Convert datetime objects to strings
        for action in actions:
            if 'created_at' in action and action['created_at']:
                action['created_at'] = action['created_at'].isoformat()
        
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
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting action history: {e}")
        return create_error_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Failed to get action history",
            error="HISTORY_GET_ERROR",
            exception=str(e)
        )