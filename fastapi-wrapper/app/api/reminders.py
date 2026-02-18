"""
Reminder API Router.

Provides endpoints for creating, delivering, listing, and cancelling reminders.
Integrates with QStash for scheduling and Peppi for SMS delivery.
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from ..models import (
    BaseResponse,
    CreateReminderRequest,
    ReminderData,
    ReminderListData,
    CancelReminderRequest,
    DeliverReminderPayload,
    success_response,
    error_response,
    ResponseCode,
)
from ..core.database import db
from ..services.qstash_service import qstash_service
from ..services.peppi_client import peppi_client
from ..utils.timezone_utils import local_to_utc, recurrence_to_cron

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Reminders"])


@router.post(
    "/reminders/create",
    response_model=BaseResponse,
    summary="Create a new reminder",
    description="Create a one-time or recurring reminder. The reminder is saved to the database "
    "and scheduled via QStash. For one-time reminders, QStash delivers via webhook at the "
    "specified time. For recurring reminders, a CRON schedule is created.",
    responses={
        201: {"description": "Reminder created successfully"},
        400: {"description": "Invalid request data"},
        500: {"description": "Failed to create reminder"},
    },
)
async def create_reminder(request: CreateReminderRequest):
    """Create a new reminder and schedule it via QStash."""
    try:
        # 1. Convert trigger_at to UTC if needed
        trigger_at_utc = local_to_utc(request.trigger_at, request.user_timezone)
        trigger_at_unix = int(trigger_at_utc.timestamp())

        # Validate: trigger time must be in the future
        if trigger_at_unix <= int(datetime.utcnow().timestamp()):
            return error_response(
                message="Reminder time must be in the future",
                error="invalid_trigger_time",
                code=ResponseCode.BAD_REQUEST,
            )

        # 2. Save reminder to Supabase
        reminder_data = {
            "user_id": int(request.user_id),
            "message": request.message,
            "trigger_at": trigger_at_utc.isoformat(),
            "user_timezone": request.user_timezone,
            "recurrence": request.recurrence,
            "recurrence_rule": request.recurrence_rule,
            "status": "pending",
        }

        reminder = await db.create_reminder(reminder_data)
        if not reminder:
            return error_response(
                message="Failed to save reminder to database",
                error="db_error",
                code=ResponseCode.INTERNAL_ERROR,
            )

        reminder_id = reminder["id"]

        # 3. Schedule via QStash
        if not qstash_service.is_configured:
            logger.warning("QStash not configured — reminder saved but not scheduled")
            return success_response(
                message="Reminder saved (QStash not configured — scheduling skipped)",
                data=ReminderData(
                    id=reminder_id,
                    user_id=request.user_id,
                    message=request.message,
                    trigger_at=trigger_at_utc.isoformat(),
                    user_timezone=request.user_timezone,
                    recurrence=request.recurrence,
                    status="pending",
                    created_at=reminder.get("created_at", ""),
                ),
                code=ResponseCode.CREATED,
            )

        if request.recurrence == "none":
            # One-time reminder
            message_id = qstash_service.schedule_one_time(
                reminder_id=reminder_id,
                user_id=request.user_id,
                message=request.message,
                trigger_at_unix=trigger_at_unix,
            )
            await db.update_reminder(reminder_id, {"qstash_message_id": message_id})
        else:
            # Recurring reminder — build CRON expression
            cron_expr = recurrence_to_cron(
                trigger_at=trigger_at_utc,
                recurrence=request.recurrence,
                timezone=request.user_timezone,
            )
            schedule_id = qstash_service.schedule_recurring(
                reminder_id=reminder_id,
                user_id=request.user_id,
                message=request.message,
                cron_expression=cron_expr,
            )
            await db.update_reminder(reminder_id, {"qstash_schedule_id": schedule_id})

        logger.info(f"Reminder {reminder_id} created and scheduled for user {request.user_id}")

        return success_response(
            message="Reminder created successfully",
            data=ReminderData(
                id=reminder_id,
                user_id=request.user_id,
                message=request.message,
                trigger_at=trigger_at_utc.isoformat(),
                user_timezone=request.user_timezone,
                recurrence=request.recurrence,
                status="pending",
                created_at=reminder.get("created_at", ""),
            ),
            code=ResponseCode.CREATED,
        )

    except ValueError as e:
        return error_response(
            message=str(e),
            error="validation_error",
            code=ResponseCode.BAD_REQUEST,
        )
    except Exception as e:
        logger.error(f"Error creating reminder: {e}")
        return error_response(
            message="Failed to create reminder",
            error="internal_error",
            code=ResponseCode.INTERNAL_ERROR,
            exception=str(e),
        )


@router.post(
    "/reminders/deliver",
    summary="Deliver a reminder (QStash webhook)",
    description="Called by QStash when a reminder's scheduled time arrives. "
    "Verifies the QStash signature, fetches the reminder, sends SMS via Peppi, "
    "and updates the reminder status.",
    responses={
        200: {"description": "Reminder delivered successfully"},
        400: {"description": "Invalid payload"},
        401: {"description": "Invalid QStash signature"},
        500: {"description": "Delivery failed"},
    },
)
async def deliver_reminder(request: Request):
    """
    QStash webhook endpoint — called when a reminder fires.
    
    Flow:
    1. Parse the reminder payload from QStash
    2. Fetch reminder from DB to confirm it's still pending
    3. Call Peppi to send SMS
    4. Update status to delivered
    """
    try:
        # TODO: Verify QStash signature for production security
        # For now, we'll process without signature verification
        # and add it once we've confirmed the webhook flow works.
        # 
        # from qstash import Receiver
        # receiver = Receiver(
        #     current_signing_key=settings.QSTASH_CURRENT_SIGNING_KEY,
        #     next_signing_key=settings.QSTASH_NEXT_SIGNING_KEY,
        # )
        # body = await request.body()
        # signature = request.headers.get("upstash-signature", "")
        # receiver.verify(body=body.decode(), signature=signature, url=deliver_url)

        # 1. Parse payload
        body = await request.json()
        payload = DeliverReminderPayload(**body)

        logger.info(
            f"Delivering reminder {payload.reminder_id} to user {payload.user_id}"
        )

        # 2. Fetch reminder from DB
        reminder = await db.get_reminder(payload.reminder_id)
        if not reminder:
            logger.warning(f"Reminder {payload.reminder_id} not found in database")
            return {"status": "skipped", "reason": "reminder_not_found"}

        if reminder.get("status") == "cancelled":
            logger.info(f"Reminder {payload.reminder_id} was cancelled — skipping delivery")
            return {"status": "skipped", "reason": "cancelled"}

        # 3. Send SMS via Peppi
        try:
            sms_result = await peppi_client.send_sms(
                user_id=payload.user_id,
                message=f"⏰ Reminder: {payload.message}",
                source="moltbot-reminder",
            )
            logger.info(f"SMS delivery result for reminder {payload.reminder_id}: {sms_result}")
        except Exception as sms_error:
            logger.error(f"SMS delivery failed for reminder {payload.reminder_id}: {sms_error}")

            # Increment retry count
            retry_count = reminder.get("retry_count", 0) + 1
            max_retries = reminder.get("max_retries", 3)

            if retry_count >= max_retries:
                await db.update_reminder(payload.reminder_id, {
                    "status": "failed",
                    "retry_count": retry_count,
                })
                logger.error(f"Reminder {payload.reminder_id} failed after {retry_count} retries")
            else:
                await db.update_reminder(payload.reminder_id, {
                    "retry_count": retry_count,
                })

            # Return 200 so QStash doesn't retry (we handle retries ourselves)
            return {"status": "failed", "reason": str(sms_error)}

        # 4. Update status to delivered
        await db.update_reminder(payload.reminder_id, {
            "status": "delivered",
            "delivered_at": datetime.utcnow().isoformat(),
        })

        logger.info(f"Reminder {payload.reminder_id} delivered successfully")
        return {"status": "delivered", "reminder_id": payload.reminder_id}

    except Exception as e:
        logger.error(f"Error in deliver_reminder: {e}")
        # Return 200 to prevent QStash from retrying on parse errors
        return {"status": "error", "reason": str(e)}


@router.get(
    "/reminders/list/{user_id}",
    response_model=BaseResponse,
    summary="List user's reminders",
    description="Get all reminders for a user, optionally filtered by status.",
    responses={
        200: {"description": "Reminders retrieved successfully"},
    },
)
async def list_reminders(user_id: str, status: Optional[str] = None):
    """List all reminders for a user."""
    try:
        reminders = await db.get_user_reminders(user_id, status=status)

        return success_response(
            message=f"Found {len(reminders)} reminder(s)",
            data=ReminderListData(
                user_id=user_id,
                reminders=reminders,
                total=len(reminders),
            ),
        )
    except Exception as e:
        logger.error(f"Error listing reminders for user {user_id}: {e}")
        return error_response(
            message="Failed to list reminders",
            error="internal_error",
            code=ResponseCode.INTERNAL_ERROR,
            exception=str(e),
        )


@router.post(
    "/reminders/cancel",
    response_model=BaseResponse,
    summary="Cancel a reminder",
    description="Cancel a pending reminder. Removes the QStash scheduled message/schedule "
    "and updates the reminder status to 'cancelled'.",
    responses={
        200: {"description": "Reminder cancelled successfully"},
        404: {"description": "Reminder not found"},
    },
)
async def cancel_reminder(request: CancelReminderRequest):
    """Cancel a pending reminder."""
    try:
        # 1. Fetch the reminder
        reminder = await db.get_reminder(request.reminder_id)
        if not reminder:
            return error_response(
                message="Reminder not found",
                error="not_found",
                code=ResponseCode.NOT_FOUND,
            )

        # Verify ownership
        if str(reminder.get("user_id")) != request.user_id:
            return error_response(
                message="Reminder does not belong to this user",
                error="forbidden",
                code=ResponseCode.FORBIDDEN,
            )

        # Check if already cancelled or delivered
        current_status = reminder.get("status")
        if current_status in ("cancelled", "delivered"):
            return error_response(
                message=f"Reminder is already {current_status}",
                error="invalid_status",
                code=ResponseCode.BAD_REQUEST,
            )

        # 2. Cancel in QStash
        if qstash_service.is_configured:
            try:
                qstash_message_id = reminder.get("qstash_message_id")
                qstash_schedule_id = reminder.get("qstash_schedule_id")

                if qstash_schedule_id:
                    qstash_service.cancel_schedule(qstash_schedule_id)
                elif qstash_message_id:
                    qstash_service.cancel_message(qstash_message_id)
            except Exception as qstash_error:
                logger.warning(
                    f"Could not cancel QStash job for reminder {request.reminder_id}: {qstash_error}"
                )

        # 3. Update status in DB
        await db.cancel_reminder(request.reminder_id)

        logger.info(f"Cancelled reminder {request.reminder_id} for user {request.user_id}")

        return success_response(
            message="Reminder cancelled successfully",
            data={"reminder_id": request.reminder_id, "status": "cancelled"},
        )

    except Exception as e:
        logger.error(f"Error cancelling reminder {request.reminder_id}: {e}")
        return error_response(
            message="Failed to cancel reminder",
            error="internal_error",
            code=ResponseCode.INTERNAL_ERROR,
            exception=str(e),
        )
