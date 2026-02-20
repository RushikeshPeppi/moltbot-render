"""
Outbound SMS Stub Router.

Provides a dummy POST /outbound/send-message endpoint that mirrors the
Peppi Laravel API payload structure. Logs every delivery attempt to
tbl_clawdbot_sms_log in Supabase so we can verify reminder timing.

When Peppi's real endpoint is ready, just swap PEPPI_OUTBOUND_URL
to point to their server — zero code changes needed.
"""
import uuid
import logging
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional

from ..core.database import db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Outbound SMS"])


class SendMessageRequest(BaseModel):
    """Mirrors the exact payload peppi_client.py sends."""
    user_id: str = Field(..., description="Peppi user ID (alphanumeric)")
    message: str = Field(..., description="SMS message body")
    source: str = Field(default="unknown", description="Caller origin, e.g. moltbot-reminder")
    priority: str = Field(default="normal", description="normal or high")


@router.post(
    "/outbound/send-message",
    summary="Stub: receive outbound SMS (Peppi stand-in)",
    description=(
        "Logs the SMS payload to tbl_clawdbot_sms_log for verification. "
        "Returns a response mimicking Peppi's real API."
    ),
    responses={
        200: {"description": "Message logged successfully"},
    },
)
async def send_message_stub(request: SendMessageRequest):
    """
    Stand-in for Peppi's outbound SMS endpoint.
    Logs the payload to Supabase and returns a mock success response.
    """
    message_id = str(uuid.uuid4())
    received_at = datetime.utcnow().isoformat()

    try:
        await db.log_outbound_sms(
            user_id=request.user_id,
            message=request.message,
            source=request.source,
            priority=request.priority,
        )
        logger.info(
            f"[SMS STUB] Logged message for user {request.user_id}: "
            f"{request.message[:60]}... (source={request.source})"
        )
    except Exception as e:
        logger.error(f"[SMS STUB] Failed to log SMS: {e}")
        # Still return success so QStash doesn't retry
        return {
            "status": "sent",
            "message_id": message_id,
            "delivered_at": received_at,
            "warning": "Failed to persist to SMS log",
        }

    return {
        "status": "sent",
        "message_id": message_id,
        "twilio_sid": f"SM_stub_{message_id[:8]}",
        "delivered_at": received_at,
    }
