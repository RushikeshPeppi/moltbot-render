from fastapi import APIRouter, HTTPException, BackgroundTasks
from ..models import (
    ExecuteActionRequest,
    ExecuteActionResponse,
    HealthResponse,
    StoreCredentialsRequest,
    CredentialsResponse
)
from ..core.session_manager import SessionManager
from ..core.credential_manager import CredentialManager
from ..core.moltbot_client import MoltbotClient
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize managers
session_manager = SessionManager()
credential_manager = CredentialManager()
moltbot_client = MoltbotClient()

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    moltbot_status = "online" if await moltbot_client.health_check() else "offline"
    active_sessions = await session_manager.get_active_sessions_count()
    
    return HealthResponse(
        status="healthy",
        moltbot_gateway=moltbot_status,
        active_sessions=active_sessions,
        timestamp=datetime.utcnow().isoformat()
    )

@router.post("/execute-action", response_model=ExecuteActionResponse)
async def execute_action(request: ExecuteActionRequest):
    """Execute action via Moltbot"""
    try:
        # Create or get session
        session_id = await session_manager.create_session(request.user_id)
        session_data = await session_manager.get_session(session_id)
        
        if not session_data:
            raise HTTPException(status_code=500, detail="Failed to create session")
        
        # Get user credentials if available
        user_credentials = request.credentials
        if not user_credentials:
            user_credentials = await credential_manager.get_credentials(
                request.user_id,
                "all"  # Or specific service
            )
        
        # Add user message to history
        await session_manager.add_message(session_id, "user", request.message)
        
        # Call Moltbot
        moltbot_response = await moltbot_client.send_message(
            session_id=session_id,
            message=request.message,
            user_credentials=user_credentials,
            conversation_history=session_data.get('conversation_history', [])
        )
        
        # Add assistant response to history
        assistant_message = moltbot_response.get('response', 'Action completed')
        await session_manager.add_message(session_id, "assistant", assistant_message)
        
        # Update session context
        session_data['context']['last_action'] = moltbot_response.get('action_type')
        await session_manager.update_session(session_id, session_data)
        
        return ExecuteActionResponse(
            success=True,
            message=assistant_message,
            session_id=session_id,
            action_performed=moltbot_response.get('action_type'),
            details=moltbot_response.get('details')
        )
    
    except Exception as e:
        logger.error(f"Error executing action: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/credentials/store", response_model=CredentialsResponse)
async def store_credentials(request: StoreCredentialsRequest):
    """Store user service credentials"""
    try:
        success = await credential_manager.store_credentials(
            user_id=request.user_id,
            service=request.service,
            credentials=request.credentials
        )
        
        if success:
            return CredentialsResponse(
                success=True,
                message="Credentials stored successfully"
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to store credentials")
    
    except Exception as e:
        logger.error(f"Error storing credentials: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/credentials/{user_id}/{service}", response_model=CredentialsResponse)
async def delete_credentials(user_id: str, service: str):
    """Delete user service credentials"""
    try:
        success = await credential_manager.delete_credentials(user_id, service)
        
        if success:
            return CredentialsResponse(
                success=True,
                message="Credentials deleted successfully"
            )
        else:
            raise HTTPException(status_code=404, detail="Credentials not found")
    
    except Exception as e:
        logger.error(f"Error deleting credentials: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cleanup")
async def cleanup_sessions(background_tasks: BackgroundTasks):
    """Trigger session cleanup"""
    # This will be handled by background task in main.py
    return {"message": "Cleanup task queued"}