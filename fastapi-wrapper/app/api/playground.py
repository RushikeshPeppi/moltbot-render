"""
Playground-specific endpoints for PM testing environment.
Provides user listing and account creation for the playground UI.
"""

import logging
import secrets
from typing import Optional
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from datetime import datetime

from ..core.database import db
from ..core.redis_client import redis_client
from ..config import settings
from ..models import ResponseCode

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/playground", tags=["Playground"])


def create_response(code, message, data=None, error=None, exception=None):
    return {
        "code": code,
        "message": message,
        "data": data,
        "error": error,
        "exception": exception,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/users")
async def list_playground_users():
    """
    Get list of all users from tbl_clawdbot_users.
    These are populated when users complete OAuth or are created via the playground.
    """
    try:
        users = await db.get_all_users()

        # Convert user_id to string for frontend consistency
        formatted = [
            {
                "user_id": str(u["user_id"]),
                "name": u["name"],
                "email": u.get("email"),
                "google_connected": u.get("google_connected", False),
                "timezone": u.get("timezone", "UTC"),
            }
            for u in users
        ]

        return create_response(
            code=ResponseCode.SUCCESS,
            message=f"Found {len(formatted)} users",
            data={"users": formatted},
        )

    except Exception as e:
        logger.error(f"Error listing playground users: {e}")
        return JSONResponse(
            status_code=500,
            content=create_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to list users",
                error="PLAYGROUND_USERS_ERROR",
                exception=str(e),
            ),
        )


class CreatePlaygroundUserRequest(BaseModel):
    name: str = Field(..., description="Display name for the new user")
    redirect_uri: Optional[str] = Field(None, description="Where to redirect after OAuth")
    timezone: Optional[str] = Field("UTC", description="User's timezone (IANA format)")


@router.post("/create-user")
async def create_playground_user(request: CreatePlaygroundUserRequest):
    """
    Create a new playground user and optionally initiate OAuth.

    1. Gets next sequential user_id from tbl_clawdbot_users
    2. Inserts user into tbl_clawdbot_users
    3. Returns user_id and OAuth authorization URL if Google OAuth is configured
    """
    try:
        # Generate alphanumeric user_id
        new_user_id = await db.generate_user_id()

        # Insert user into tbl_clawdbot_users
        user = await db.upsert_user(
            user_id=new_user_id,
            name=request.name,
            google_connected=False,
            timezone=request.timezone or "UTC"
        )

        if not user:
            return JSONResponse(
                status_code=500,
                content=create_response(
                    code=ResponseCode.INTERNAL_ERROR,
                    message="Failed to create user in database",
                    error="USER_CREATE_FAILED",
                ),
            )

        # Build OAuth URL if configured
        auth_url = None
        if settings.GOOGLE_CLIENT_ID:
            state = secrets.token_urlsafe(32)

            # Store OAuth state with user name for profile fallback
            state_data = {
                "user_id": new_user_id,
                "user_name": request.name,
                "redirect_uri": request.redirect_uri or settings.PEPPI_WEBSITE_URL or "",
            }
            await redis_client.set(f"oauth_state:{state}", state_data, ttl=600)

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

        return create_response(
            code=ResponseCode.CREATED,
            message="Playground user created",
            data={
                "user_id": new_user_id,
                "name": request.name,
                "timezone": request.timezone or "UTC",
                "auth_url": auth_url,
            },
        )

    except Exception as e:
        logger.error(f"Error creating playground user: {e}")
        return JSONResponse(
            status_code=500,
            content=create_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to create user",
                error="PLAYGROUND_CREATE_ERROR",
                exception=str(e),
            ),
        )


class UpdateTimezoneRequest(BaseModel):
    timezone: str = Field(..., description="IANA timezone (e.g. 'America/New_York')")


@router.patch("/users/{user_id}/timezone")
async def update_user_timezone(user_id: str, request: UpdateTimezoneRequest):
    """Update a user's timezone setting from the playground Settings panel."""
    try:
        success = await db.update_user_timezone(user_id, request.timezone)

        if not success:
            return JSONResponse(
                status_code=500,
                content=create_response(
                    code=ResponseCode.INTERNAL_ERROR,
                    message="Failed to update timezone",
                    error="TIMEZONE_UPDATE_FAILED",
                ),
            )

        return create_response(
            code=ResponseCode.SUCCESS,
            message="Timezone updated",
            data={"user_id": user_id, "timezone": request.timezone},
        )
    except Exception as e:
        logger.error(f"Error updating timezone for user {user_id}: {e}")
        return JSONResponse(
            status_code=500,
            content=create_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to update timezone",
                error="TIMEZONE_UPDATE_ERROR",
                exception=str(e),
            ),
        )


@router.get("/messages/{user_id}")
async def get_playground_messages(user_id: str):
    """
    Poll for pending playground messages for a user.

    The frontend calls this every 5 seconds. When a reminder fires (QStash → /reminders/deliver),
    the delivery handler pushes a message to Redis. This endpoint pops and returns them all,
    clearing the queue so each message is shown exactly once.

    Returns:
        {"messages": [{"type": "reminder_delivery", "message": "...", "timestamp": "..."}]}
    """
    try:
        messages = await redis_client.pop_playground_messages(user_id)
        return create_response(
            code=ResponseCode.SUCCESS,
            message=f"Found {len(messages)} message(s)",
            data={"messages": messages},
        )
    except Exception as e:
        logger.error(f"Error fetching playground messages for user {user_id}: {e}")
        return JSONResponse(
            status_code=500,
            content=create_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to fetch messages",
                error="PLAYGROUND_MESSAGES_ERROR",
                exception=str(e),
            ),
        )
