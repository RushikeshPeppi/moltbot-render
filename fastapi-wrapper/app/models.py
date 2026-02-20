"""
Pydantic models for API request/response with standardized DTO format.
All responses follow the structure: Code, Message, Data, Error, Exception
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any, Generic, TypeVar
from datetime import datetime
from enum import IntEnum

# Generic type for response data
T = TypeVar('T')


class ResponseCode(IntEnum):
    """Standard response codes"""
    SUCCESS = 200
    CREATED = 201
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    UNPROCESSABLE = 422
    TOO_MANY_REQUESTS = 429
    INTERNAL_ERROR = 500
    SERVICE_UNAVAILABLE = 503
    GATEWAY_TIMEOUT = 504


# ==================== Base Response DTO ====================

class BaseResponse(BaseModel):
    """
    Standard response format for all API endpoints.
    This DTO structure is consistent across all responses.
    """
    code: int = Field(..., description="HTTP status code")
    message: str = Field(..., description="Human-readable message")
    data: Optional[Any] = Field(None, description="Response payload")
    error: Optional[str] = Field(None, description="Error type/code if any")
    exception: Optional[str] = Field(None, description="Exception details for debugging")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    class Config:
        json_schema_extra = {
            "example": {
                "code": 200,
                "message": "Action executed successfully",
                "data": {"session_id": "sess_abc123", "response": "Meeting scheduled"},
                "error": None,
                "exception": None,
                "timestamp": "2026-02-05T00:50:00Z"
            }
        }


# ==================== Execute Action ====================

class ExecuteActionRequest(BaseModel):
    """Request to execute an action via OpenClaw"""
    user_id: str = Field(..., description="User ID from Peppi system")
    message: str = Field(..., description="User's SMS message/action request")
    timezone: str = Field(..., description="User's timezone (e.g., 'Asia/Kolkata', 'America/New_York')")
    phone_number: Optional[str] = Field(None, description="User's phone number")
    credentials: Optional[Dict[str, Any]] = Field(None, description="User service credentials")

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "123",
                "message": "Schedule a meeting tomorrow at 3pm",
                "timezone": "Asia/Kolkata",
                "phone_number": "+1234567890",
                "credentials": None
            }
        }


class ExecuteActionData(BaseModel):
    """Data payload for execute action response"""
    session_id: str = Field(..., description="Session ID for conversation tracking")
    response: str = Field(..., description="AI response message")
    action_performed: Optional[str] = Field(None, description="Type of action executed")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional action details")


class ExecuteActionResponse(BaseResponse):
    """Response from action execution"""
    data: Optional[ExecuteActionData] = None


# ==================== Health Check ====================

class HealthData(BaseModel):
    """Health check data payload"""
    status: str = Field(..., description="Overall health status")
    openclaw_gateway: str = Field(..., description="OpenClaw gateway status")
    redis: bool = Field(..., description="Redis connection status")
    supabase: bool = Field(..., description="Supabase connection status")
    active_sessions: int = Field(..., description="Number of active sessions")


class HealthResponse(BaseResponse):
    """Health check response"""
    data: Optional[HealthData] = None


# ==================== Session Management ====================

class SessionData(BaseModel):
    """Session information data"""
    session_id: str
    user_id: str
    created_at: str
    last_activity: str
    message_count: int


class SessionResponse(BaseResponse):
    """Session info response"""
    data: Optional[SessionData] = None


class ConversationData(BaseModel):
    """Conversation history data"""
    session_id: str
    messages: List[Dict[str, Any]]
    total_messages: int


class ConversationResponse(BaseResponse):
    """Conversation history response"""
    data: Optional[ConversationData] = None


# ==================== Credentials ====================

class StoreCredentialsRequest(BaseModel):
    """Store user credentials request"""
    user_id: str
    service: str
    credentials: Dict[str, Any]


class CredentialsStatusData(BaseModel):
    """Credentials status data"""
    user_id: str
    services: Dict[str, bool]


class CredentialsResponse(BaseResponse):
    """Credentials operation response"""
    data: Optional[CredentialsStatusData] = None


# ==================== Action History ====================

class ActionHistoryData(BaseModel):
    """Action history data"""
    user_id: str
    actions: List[Dict[str, Any]]
    total: int


class ActionHistoryResponse(BaseResponse):
    """Action history response"""
    data: Optional[ActionHistoryData] = None


# ==================== OAuth ====================

class OAuthInitData(BaseModel):
    """OAuth initialization data"""
    authorization_url: str
    state: str


class OAuthInitResponse(BaseResponse):
    """OAuth init response"""
    data: Optional[OAuthInitData] = None


class OAuthStatusData(BaseModel):
    """OAuth status data"""
    connected: bool
    service: str
    scopes: List[str]
    expires_at: Optional[str] = None


class OAuthStatusResponse(BaseResponse):
    """OAuth status response"""
    data: Optional[OAuthStatusData] = None


# ==================== Reminders ====================

class CreateReminderRequest(BaseModel):
    """Request to create a new reminder"""
    user_id: str = Field(..., description="User ID from Peppi system")
    message: str = Field(..., description="What to remind the user about")
    trigger_at: str = Field(..., description="ISO 8601 datetime for when to fire (UTC)")
    user_timezone: str = Field(..., description="User's timezone (e.g., 'Asia/Kolkata')")
    recurrence: str = Field(default="none", description="none, daily, weekly, monthly")
    recurrence_rule: Optional[Dict[str, Any]] = Field(
        None, description="Complex recurrence rules (day_of_week, etc.)"
    )

    @field_validator("recurrence", mode="before")
    @classmethod
    def normalize_recurrence(cls, v):
        """Normalize empty/whitespace recurrence to 'none' to satisfy DB check constraint."""
        if not v or (isinstance(v, str) and not v.strip()):
            return "none"
        v = v.strip().lower()
        allowed = {"none", "daily", "weekly", "monthly"}
        if v not in allowed:
            return "none"
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "123",
                "message": "Buy milk on your way home",
                "trigger_at": "2026-02-19T08:30:00Z",
                "user_timezone": "Asia/Kolkata",
                "recurrence": "none",
                "recurrence_rule": None
            }
        }


class ReminderData(BaseModel):
    """Reminder data in responses"""
    id: int
    user_id: str
    message: str
    trigger_at: str
    user_timezone: str
    recurrence: str
    status: str
    created_at: str
    qstash_message_id: Optional[str] = None
    qstash_schedule_id: Optional[str] = None


class ReminderListData(BaseModel):
    """Reminder list data"""
    user_id: str
    reminders: List[Dict[str, Any]]
    total: int


class CancelReminderRequest(BaseModel):
    """Request to cancel a reminder"""
    user_id: str = Field(..., description="User ID from Peppi system")
    reminder_id: int = Field(..., description="Reminder ID to cancel")


class DeliverReminderPayload(BaseModel):
    """Payload received from QStash when a reminder fires"""
    reminder_id: int
    user_id: str
    message: str


# ==================== Helper Functions ====================

def success_response(
    message: str,
    data: Any = None,
    code: int = ResponseCode.SUCCESS
) -> BaseResponse:
    """Create a success response"""
    return BaseResponse(
        code=code,
        message=message,
        data=data,
        error=None,
        exception=None
    )


def error_response(
    message: str,
    error: str,
    code: int = ResponseCode.INTERNAL_ERROR,
    exception: str = None
) -> BaseResponse:
    """Create an error response"""
    return BaseResponse(
        code=code,
        message=message,
        data=None,
        error=error,
        exception=exception
    )