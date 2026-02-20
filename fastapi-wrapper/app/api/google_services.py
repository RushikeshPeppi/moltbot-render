"""
Google Calendar and Gmail API endpoints.
Provides direct access to Google services using stored OAuth tokens.
"""

import logging
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Query, Body
from pydantic import BaseModel, EmailStr

from ..services.google_calendar import GoogleCalendarService
from ..services.gmail import GmailService
from ..models import ResponseCode

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/google", tags=["Google Services"])

# Initialize services
calendar_service = GoogleCalendarService()
gmail_service = GmailService()


def create_response(code: int, message: str, data=None, error=None, exception=None):
    """Create standardized response"""
    return {
        "code": code,
        "message": message,
        "data": data,
        "error": error,
        "exception": exception,
        "timestamp": datetime.utcnow().isoformat()
    }


# ==================== Calendar Endpoints ====================

class CreateEventRequest(BaseModel):
    user_id: str
    summary: str
    start_time: datetime
    end_time: datetime
    description: Optional[str] = None
    location: Optional[str] = None
    attendees: Optional[List[EmailStr]] = None


class UpdateEventRequest(BaseModel):
    user_id: str
    event_id: str
    summary: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    description: Optional[str] = None
    location: Optional[str] = None


@router.get("/calendar/events")
async def list_calendar_events(
    user_id: str = Query(..., description="User ID"),
    max_results: int = Query(10, description="Maximum number of events to return"),
    days: int = Query(7, description="Number of days to look ahead")
):
    """
    List upcoming calendar events for a user.

    Returns events from now until the specified number of days in the future.
    """
    try:
        time_min = datetime.utcnow()
        time_max = datetime.utcnow()
        time_max = time_max.replace(day=time_max.day + days) if days <= 28 else time_max

        result = await calendar_service.list_events(
            user_id=user_id,
            time_min=time_min,
            time_max=time_max,
            max_results=max_results
        )

        if result['success']:
            return create_response(
                code=ResponseCode.SUCCESS,
                message=f"Retrieved {result['count']} calendar events",
                data=result
            )
        else:
            return create_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to retrieve calendar events",
                error="CALENDAR_ERROR",
                exception=result.get('error')
            )

    except Exception as e:
        logger.error(f"Error listing calendar events: {e}")
        return create_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Error listing calendar events",
            error="CALENDAR_ERROR",
            exception=str(e)
        )


@router.post("/calendar/events")
async def create_calendar_event(request: CreateEventRequest):
    """
    Create a new calendar event.

    Creates an event on the user's primary calendar with the specified details.
    """
    try:
        result = await calendar_service.create_event(
            user_id=request.user_id,
            summary=request.summary,
            start_time=request.start_time,
            end_time=request.end_time,
            description=request.description,
            location=request.location,
            attendees=request.attendees
        )

        if result['success']:
            return create_response(
                code=ResponseCode.SUCCESS,
                message="Calendar event created successfully",
                data=result
            )
        else:
            return create_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to create calendar event",
                error="CALENDAR_ERROR",
                exception=result.get('error')
            )

    except Exception as e:
        logger.error(f"Error creating calendar event: {e}")
        return create_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Error creating calendar event",
            error="CALENDAR_ERROR",
            exception=str(e)
        )


@router.get("/calendar/events/{event_id}")
async def get_calendar_event(
    event_id: str,
    user_id: str = Query(..., description="User ID")
):
    """Get a specific calendar event by ID"""
    try:
        result = await calendar_service.get_event(
            user_id=user_id,
            event_id=event_id
        )

        if result['success']:
            return create_response(
                code=ResponseCode.SUCCESS,
                message="Calendar event retrieved successfully",
                data=result
            )
        else:
            return create_response(
                code=ResponseCode.NOT_FOUND if result.get('error_code') == 404 else ResponseCode.INTERNAL_ERROR,
                message="Failed to retrieve calendar event",
                error="CALENDAR_ERROR",
                exception=result.get('error')
            )

    except Exception as e:
        logger.error(f"Error getting calendar event: {e}")
        return create_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Error getting calendar event",
            error="CALENDAR_ERROR",
            exception=str(e)
        )


@router.put("/calendar/events/{event_id}")
async def update_calendar_event(event_id: str, request: UpdateEventRequest):
    """Update an existing calendar event"""
    try:
        result = await calendar_service.update_event(
            user_id=request.user_id,
            event_id=event_id,
            summary=request.summary,
            start_time=request.start_time,
            end_time=request.end_time,
            description=request.description,
            location=request.location
        )

        if result['success']:
            return create_response(
                code=ResponseCode.SUCCESS,
                message="Calendar event updated successfully",
                data=result
            )
        else:
            return create_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to update calendar event",
                error="CALENDAR_ERROR",
                exception=result.get('error')
            )

    except Exception as e:
        logger.error(f"Error updating calendar event: {e}")
        return create_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Error updating calendar event",
            error="CALENDAR_ERROR",
            exception=str(e)
        )


@router.delete("/calendar/events/{event_id}")
async def delete_calendar_event(
    event_id: str,
    user_id: str = Query(..., description="User ID")
):
    """Delete a calendar event"""
    try:
        result = await calendar_service.delete_event(
            user_id=user_id,
            event_id=event_id
        )

        if result['success']:
            return create_response(
                code=ResponseCode.SUCCESS,
                message="Calendar event deleted successfully",
                data=result
            )
        else:
            return create_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to delete calendar event",
                error="CALENDAR_ERROR",
                exception=result.get('error')
            )

    except Exception as e:
        logger.error(f"Error deleting calendar event: {e}")
        return create_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Error deleting calendar event",
            error="CALENDAR_ERROR",
            exception=str(e)
        )


# ==================== Gmail Endpoints ====================

class SendEmailRequest(BaseModel):
    user_id: str
    to: EmailStr
    subject: str
    body: str
    cc: Optional[str] = None
    bcc: Optional[str] = None
    html: bool = False


@router.get("/gmail/messages")
async def list_gmail_messages(
    user_id: str = Query(..., description="User ID"),
    query: Optional[str] = Query(None, description="Gmail search query"),
    max_results: int = Query(10, description="Maximum number of messages"),
    unread_only: bool = Query(False, description="Only show unread messages")
):
    """
    List Gmail messages.

    Supports Gmail search queries like:
    - "is:unread" - Unread messages
    - "from:example@gmail.com" - From specific sender
    - "subject:meeting" - Subject contains "meeting"
    """
    try:
        # Build query
        if unread_only and not query:
            query = "is:unread"
        elif unread_only and query:
            query = f"{query} is:unread"

        result = await gmail_service.list_messages(
            user_id=user_id,
            query=query,
            max_results=max_results
        )

        if result['success']:
            return create_response(
                code=ResponseCode.SUCCESS,
                message=f"Retrieved {result['count']} Gmail messages",
                data=result
            )
        else:
            return create_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to retrieve Gmail messages",
                error="GMAIL_ERROR",
                exception=result.get('error')
            )

    except Exception as e:
        logger.error(f"Error listing Gmail messages: {e}")
        return create_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Error listing Gmail messages",
            error="GMAIL_ERROR",
            exception=str(e)
        )


@router.get("/gmail/messages/{message_id}")
async def get_gmail_message(
    message_id: str,
    user_id: str = Query(..., description="User ID"),
    format: str = Query("full", description="Message format (minimal, full, raw, metadata)")
):
    """Get a specific Gmail message by ID"""
    try:
        result = await gmail_service.get_message(
            user_id=user_id,
            message_id=message_id,
            format=format
        )

        if result['success']:
            return create_response(
                code=ResponseCode.SUCCESS,
                message="Gmail message retrieved successfully",
                data=result
            )
        else:
            return create_response(
                code=ResponseCode.NOT_FOUND if result.get('error_code') == 404 else ResponseCode.INTERNAL_ERROR,
                message="Failed to retrieve Gmail message",
                error="GMAIL_ERROR",
                exception=result.get('error')
            )

    except Exception as e:
        logger.error(f"Error getting Gmail message: {e}")
        return create_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Error getting Gmail message",
            error="GMAIL_ERROR",
            exception=str(e)
        )


@router.post("/gmail/send")
async def send_gmail_message(request: SendEmailRequest):
    """
    Send an email via Gmail.

    Sends an email from the authenticated user's Gmail account.
    """
    try:
        result = await gmail_service.send_message(
            user_id=request.user_id,
            to=request.to,
            subject=request.subject,
            body=request.body,
            cc=request.cc,
            bcc=request.bcc,
            html=request.html
        )

        if result['success']:
            return create_response(
                code=ResponseCode.SUCCESS,
                message="Email sent successfully",
                data=result
            )
        else:
            return create_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to send email",
                error="GMAIL_ERROR",
                exception=result.get('error')
            )

    except Exception as e:
        logger.error(f"Error sending email: {e}")
        return create_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Error sending email",
            error="GMAIL_ERROR",
            exception=str(e)
        )


@router.delete("/gmail/messages/{message_id}")
async def delete_gmail_message(
    message_id: str,
    user_id: str = Query(..., description="User ID")
):
    """Delete (trash) a Gmail message"""
    try:
        result = await gmail_service.delete_message(
            user_id=user_id,
            message_id=message_id
        )

        if result['success']:
            return create_response(
                code=ResponseCode.SUCCESS,
                message="Gmail message deleted successfully",
                data=result
            )
        else:
            return create_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to delete Gmail message",
                error="GMAIL_ERROR",
                exception=result.get('error')
            )

    except Exception as e:
        logger.error(f"Error deleting Gmail message: {e}")
        return create_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Error deleting Gmail message",
            error="GMAIL_ERROR",
            exception=str(e)
        )


@router.post("/gmail/messages/{message_id}/mark-read")
async def mark_gmail_message_read(
    message_id: str,
    user_id: str = Query(..., description="User ID")
):
    """Mark a Gmail message as read"""
    try:
        result = await gmail_service.mark_as_read(
            user_id=user_id,
            message_id=message_id
        )

        if result['success']:
            return create_response(
                code=ResponseCode.SUCCESS,
                message="Message marked as read",
                data=result
            )
        else:
            return create_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to mark message as read",
                error="GMAIL_ERROR",
                exception=result.get('error')
            )

    except Exception as e:
        logger.error(f"Error marking message as read: {e}")
        return create_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Error marking message as read",
            error="GMAIL_ERROR",
            exception=str(e)
        )


@router.get("/gmail/search")
async def search_gmail_messages(
    user_id: str = Query(..., description="User ID"),
    query: str = Query(..., description="Gmail search query"),
    max_results: int = Query(10, description="Maximum number of results")
):
    """
    Search Gmail messages using Gmail search syntax.

    Examples:
    - "from:example@gmail.com subject:meeting"
    - "is:unread after:2026/01/01"
    - "has:attachment larger:10M"
    """
    try:
        result = await gmail_service.search_messages(
            user_id=user_id,
            query=query,
            max_results=max_results
        )

        if result['success']:
            return create_response(
                code=ResponseCode.SUCCESS,
                message=f"Found {result['count']} matching messages",
                data=result
            )
        else:
            return create_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to search Gmail messages",
                error="GMAIL_ERROR",
                exception=result.get('error')
            )

    except Exception as e:
        logger.error(f"Error searching Gmail messages: {e}")
        return create_response(
            code=ResponseCode.INTERNAL_ERROR,
            message="Error searching Gmail messages",
            error="GMAIL_ERROR",
            exception=str(e)
        )
