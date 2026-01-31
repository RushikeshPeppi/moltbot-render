from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime

class ExecuteActionRequest(BaseModel):
    """Request to execute an action via Moltbot"""
    user_id: str = Field(..., description="User ID from your system")
    message: str = Field(..., description="User's action request")
    phone_number: Optional[str] = Field(None, description="User's phone number")
    credentials: Optional[Dict] = Field(None, description="User service credentials")

class ExecuteActionResponse(BaseModel):
    """Response from action execution"""
    success: bool
    message: str
    session_id: str
    action_performed: Optional[str] = None
    details: Optional[Dict] = None

class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    moltbot_gateway: str
    active_sessions: int
    timestamp: str

class StoreCredentialsRequest(BaseModel):
    """Store user credentials"""
    user_id: str
    service: str
    credentials: Dict

class CredentialsResponse(BaseModel):
    """Credentials operation response"""
    success: bool
    message: str