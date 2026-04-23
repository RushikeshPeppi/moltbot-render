"""
Reminder API Router.

Provides endpoints for creating, delivering, listing, and cancelling reminders.
Integrates with QStash for scheduling and Peppi for SMS delivery.

Production hardening (April 2026):
- QStash webhook signature verification is ENABLED
- Reminder deduplication prevents the same reminder from being created twice
- Delivery errors are classified as permanent vs transient:
    - Permanent (404, 403, 400): auto-fail + cancel QStash schedule
    - Transient (5xx, timeout): retry up to max_retries
- Playground users (usr_* IDs) skip Peppi SMS and use Redis push instead
- Dead-letter guard: if retry_count exceeds threshold, auto-cancel
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from ..utils.timezone_utils import now_utc_naive

from fastapi import APIRouter, Request, HTTPException
from qstash import Receiver

from ..models import (
    BaseResponse,
    CreateReminderRequest,
    ReminderData,
    ReminderListData,
    CancelReminderRequest,
    UpdateReminderRequest,
    DeliverReminderPayload,
    success_response,
    error_response,
    ResponseCode,
)
from ..core.database import db
from ..core.redis_client import redis_client
from ..services.qstash_service import qstash_service
from ..services.peppi_client import peppi_client
from ..utils.timezone_utils import local_to_utc, recurrence_to_cron
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Reminders"])

# Dead-letter threshold — if a reminder has already retried this many times,
# don't even attempt delivery anymore.
DEAD_LETTER_RETRY_THRESHOLD = 5

# HTTP status codes that indicate permanent, non-retryable failures.
PERMANENT_HTTP_ERRORS = {400, 401, 403, 404, 410, 422}

# Maximum time window (minutes) for duplicate reminder detection.
DEDUP_WINDOW_MINUTES = 5


# ==================== Helpers ====================

def _is_playground_user(user_id: str) -> bool:
    """Playground users have 'usr_' prefixed IDs. They don't exist in Peppi's system."""
    return user_id.startswith("usr_")


def _is_permanent_sms_error(exc: Exception) -> bool:
    """
    Determine whether an SMS delivery error is permanent (never retry) or transient.
    Permanent errors: user_not_found (404), forbidden (403), bad request (400), etc.
    Transient errors: server error (5xx), timeout, network errors.
    """
    import httpx
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in PERMANENT_HTTP_ERRORS
    # Network errors, timeouts → transient
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
        return False
    # Unknown error → treat as transient to be safe
    return False


async def _cancel_qstash_for_reminder(reminder: dict, reminder_id: int) -> None:
    """Cancel any QStash message or schedule for a reminder."""
    if not qstash_service.is_configured:
        return
    try:
        qstash_schedule_id = reminder.get("qstash_schedule_id")
        qstash_message_id = reminder.get("qstash_message_id")
        if qstash_schedule_id:
            qstash_service.cancel_schedule(qstash_schedule_id)
            logger.info(f"Cancelled QStash schedule {qstash_schedule_id} for reminder {reminder_id}")
        elif qstash_message_id:
            qstash_service.cancel_message(qstash_message_id)
            logger.info(f"Cancelled QStash message {qstash_message_id} for reminder {reminder_id}")
    except Exception as e:
        logger.warning(f"Could not cancel QStash job for reminder {reminder_id}: {e}")


async def _mark_permanently_failed(reminder: dict, reminder_id: int, reason: str) -> None:
    """Mark a reminder as permanently failed and cancel its QStash schedule."""
    await db.update_reminder(reminder_id, {
        "status": "failed",
        "retry_count": reminder.get("retry_count", 0),
    })
    await _cancel_qstash_for_reminder(reminder, reminder_id)
    logger.error(
        f"Reminder {reminder_id} PERMANENTLY FAILED: {reason}. "
        f"QStash schedule cancelled."
    )


def _verify_qstash_signature(raw_body: bytes, signature: str) -> bool:
    """
    Verify the QStash webhook signature using current + next signing keys.
    Returns True if valid, False otherwise.

    SECURITY: in production, refuse to serve the /deliver endpoint if the
    signing keys aren't configured — skipping the check would let anyone
    POST a forged reminder payload (spam SMS + pollute audit log).
    In dev/staging, allow-through with a loud warning so local QStash stubs
    can still exercise the code path.
    """
    current_key = settings.QSTASH_CURRENT_SIGNING_KEY
    next_key = settings.QSTASH_NEXT_SIGNING_KEY

    if not current_key or not next_key:
        env = (settings.ENV or "production").lower()
        if env == "production":
            logger.error(
                "QStash signing keys not configured in production — "
                "rejecting webhook (would be a forgery attack surface otherwise)."
            )
            return False
        logger.warning(
            "QStash signing keys not configured (ENV=%s) — skipping verification. "
            "This is only acceptable in dev/staging.",
            env,
        )
        return True

    try:
        receiver = Receiver(
            current_signing_key=current_key,
            next_signing_key=next_key,
        )
        deliver_url = f"{settings.MOLTBOT_PUBLIC_URL}/api/v1/reminders/deliver"
        receiver.verify(
            body=raw_body.decode("utf-8"),
            signature=signature,
            url=deliver_url,
        )
        return True
    except Exception as e:
        logger.error(f"QStash signature verification failed: {e}")
        return False


# ==================== Create ====================

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
        if trigger_at_unix <= int(now_utc_naive().timestamp()):
            return error_response(
                message="Reminder time must be in the future",
                error="invalid_trigger_time",
                code=ResponseCode.BAD_REQUEST,
            )

        # 2. Deduplication — check for an existing pending reminder with similar
        #    trigger time for the same user, created within the last 2 minutes.
        #    This prevents the gateway's empty-payload retries from creating duplicates.
        try:
            existing_reminders = await db.get_user_reminders(request.user_id, status='pending')
            dedup_cutoff = now_utc_naive() - timedelta(minutes=2)

            for existing in existing_reminders:
                existing_trigger = existing.get("trigger_at", "")
                existing_created = existing.get("created_at", "")

                try:
                    existing_trigger_dt = datetime.fromisoformat(
                        existing_trigger.replace('Z', '+00:00')
                    ).replace(tzinfo=None)
                    existing_created_dt = datetime.fromisoformat(
                        existing_created.replace('Z', '+00:00')
                    ).replace(tzinfo=None)
                except (ValueError, AttributeError):
                    continue

                # Same user, similar time (within DEDUP_WINDOW_MINUTES), recently created
                time_diff = abs((existing_trigger_dt - trigger_at_utc.replace(tzinfo=None)).total_seconds())
                if time_diff <= DEDUP_WINDOW_MINUTES * 60 and existing_created_dt >= dedup_cutoff:
                    logger.info(
                        f"Dedup: Reminder for user {request.user_id} at "
                        f"~{trigger_at_utc.isoformat()} already exists "
                        f"(existing reminder {existing.get('id')}). Returning existing."
                    )
                    return success_response(
                        message="Reminder already exists (deduplicated)",
                        data=ReminderData(
                            id=existing.get("id"),
                            user_id=request.user_id,
                            message=existing.get("message", ""),
                            trigger_at=existing_trigger,
                            user_timezone=existing.get("user_timezone", ""),
                            recurrence=existing.get("recurrence", "none"),
                            status="pending",
                            created_at=existing_created,
                        ),
                        code=ResponseCode.SUCCESS,
                    )
        except Exception as dedup_err:
            # Dedup is a best-effort optimization — don't block creation if it fails
            logger.warning(f"Dedup check failed (non-blocking): {dedup_err}")

        # 3. Save reminder to Supabase
        reminder_data = {
            "user_id": request.user_id,
            "message": request.message,
            "trigger_at": trigger_at_utc.isoformat(),
            "user_timezone": request.user_timezone,
            "recurrence": request.recurrence,
            "recurrence_rule": request.recurrence_rule,
            "status": "pending",
            "max_retries": 3,  # Explicit — not NULL
        }

        reminder = await db.create_reminder(reminder_data)
        if not reminder:
            return error_response(
                message="Failed to save reminder to database",
                error="db_error",
                code=ResponseCode.INTERNAL_ERROR,
            )

        reminder_id = reminder["id"]

        # 4. Schedule via QStash
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


# ==================== Deliver ====================

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
    1. Verify QStash signature
    2. Parse the reminder payload
    3. Dead-letter check (skip if too many retries)
    4. Route delivery: Peppi SMS (production) or Redis push (playground)
    5. Update status
    """
    try:
        # 0. Read raw body FIRST (needed for signature verification)
        raw_body = await request.body()
        signature = request.headers.get("upstash-signature", "")

        # 1. Verify QStash signature. Return 401 on failure so monitoring
        # catches forgery attempts — the previous 200 was invisible in logs.
        if not _verify_qstash_signature(raw_body, signature):
            logger.error("QStash signature verification failed — rejecting request")
            from fastapi.responses import JSONResponse as _JR
            return _JR(
                status_code=401,
                content={"status": "rejected", "reason": "invalid_signature"},
            )

        # 2. Parse payload
        import json
        body = json.loads(raw_body)
        payload = DeliverReminderPayload(**body)

        logger.info(
            f"Delivering reminder {payload.reminder_id} to user {payload.user_id}"
        )

        # 3. Fetch reminder from DB
        reminder = await db.get_reminder(payload.reminder_id)
        if not reminder:
            logger.warning(f"Reminder {payload.reminder_id} not found in database")
            return {"status": "skipped", "reason": "reminder_not_found"}

        if reminder.get("status") in ("cancelled", "failed"):
            logger.info(
                f"Reminder {payload.reminder_id} status is "
                f"'{reminder.get('status')}' — skipping delivery"
            )
            return {"status": "skipped", "reason": reminder.get("status")}

        if reminder.get("status") == "delivered" and reminder.get("recurrence") == "none":
            logger.info(f"One-time reminder {payload.reminder_id} already delivered — skipping")
            return {"status": "skipped", "reason": "already_delivered"}

        # 4. Dead-letter guard — prevent zombie retries
        retry_count = reminder.get("retry_count", 0) or 0
        if retry_count >= DEAD_LETTER_RETRY_THRESHOLD:
            logger.error(
                f"Reminder {payload.reminder_id} exceeded dead-letter threshold "
                f"({retry_count} retries). Auto-cancelling."
            )
            await _mark_permanently_failed(
                reminder, payload.reminder_id,
                f"Exceeded {DEAD_LETTER_RETRY_THRESHOLD} retry threshold"
            )
            return {"status": "dead_lettered", "reason": "exceeded_retry_threshold"}

        # 5. Route delivery based on user type
        if _is_playground_user(payload.user_id):
            # Playground users — deliver via Redis push (no Peppi SMS)
            delivery_result = await _deliver_to_playground(payload, reminder)
        else:
            # Production users — deliver via Peppi SMS
            delivery_result = await _deliver_via_peppi_sms(payload, reminder)

        return delivery_result

    except Exception as e:
        logger.error(f"Error in deliver_reminder: {e}")
        # Return 200 to prevent QStash from retrying on parse errors
        return {"status": "error", "reason": str(e)}


async def _deliver_to_playground(
    payload: DeliverReminderPayload, reminder: dict
) -> dict:
    """
    Deliver reminder to playground users via Redis push notification.
    Skip Peppi SMS entirely since usr_ IDs don't exist in Peppi's system.
    """
    try:
        await redis_client.push_playground_message(payload.user_id, {
            "type": "reminder_delivery",
            "message": payload.message,
            "reminder_id": payload.reminder_id,
            "timestamp": now_utc_naive().isoformat(),
        })

        # Update status
        if reminder.get("recurrence") == "none":
            await db.update_reminder(payload.reminder_id, {
                "status": "delivered",
                "delivered_at": now_utc_naive().isoformat(),
            })

        # Create audit log
        await _create_delivery_audit_log(payload)

        logger.info(
            f"Reminder {payload.reminder_id} delivered to playground user "
            f"{payload.user_id} via Redis push"
        )
        return {"status": "delivered", "reminder_id": payload.reminder_id, "channel": "playground"}

    except Exception as e:
        logger.error(f"Playground delivery failed for reminder {payload.reminder_id}: {e}")
        return {"status": "failed", "reason": str(e)}


async def _deliver_via_peppi_sms(
    payload: DeliverReminderPayload, reminder: dict
) -> dict:
    """
    Deliver reminder to production users via Peppi SMS.
    Classifies errors as permanent vs transient for proper retry behavior.
    """
    try:
        sms_result = await peppi_client.send_sms(
            user_id=payload.user_id,
            message=f"⏰ Reminder: {payload.message}",
            source="moltbot-reminder",
        )
        logger.info(f"SMS delivery result for reminder {payload.reminder_id}: {sms_result}")
    except Exception as sms_error:
        logger.error(f"SMS delivery failed for reminder {payload.reminder_id}: {sms_error}")

        if _is_permanent_sms_error(sms_error):
            # PERMANENT: user doesn't exist, forbidden, bad request
            # No amount of retrying will fix this — fail immediately
            await _mark_permanently_failed(
                reminder, payload.reminder_id,
                f"Permanent SMS error: {sms_error}"
            )
            return {"status": "permanently_failed", "reason": str(sms_error)}
        else:
            # TRANSIENT: server error, timeout — retry allowed
            retry_count = (reminder.get("retry_count", 0) or 0) + 1
            max_retries = reminder.get("max_retries") or 3

            if retry_count >= max_retries:
                await _mark_permanently_failed(
                    reminder, payload.reminder_id,
                    f"Exhausted {max_retries} retries. Last error: {sms_error}"
                )
                return {"status": "failed", "reason": f"max_retries_exceeded ({max_retries})"}
            else:
                await db.update_reminder(payload.reminder_id, {
                    "retry_count": retry_count,
                })
                logger.warning(
                    f"Reminder {payload.reminder_id} transient failure "
                    f"(retry {retry_count}/{max_retries}): {sms_error}"
                )

            # Return 200 so QStash doesn't add its own retries on top of ours
            return {"status": "retrying", "reason": str(sms_error), "retry_count": retry_count}

    # Check if SMS was actually sent (not just skipped by PeppiClient)
    if sms_result.get("status") == "skipped":
        logger.warning(
            f"Reminder {payload.reminder_id} SMS was skipped: {sms_result.get('message')}"
        )
        await db.update_reminder(payload.reminder_id, {"status": "failed"})
        return {"status": "failed", "reason": sms_result.get("message")}

    # Success — update status
    if reminder.get("recurrence") == "none":
        await db.update_reminder(payload.reminder_id, {
            "status": "delivered",
            "delivered_at": now_utc_naive().isoformat(),
        })

    # Create audit log + push playground notification
    await _create_delivery_audit_log(payload)
    try:
        await redis_client.push_playground_message(payload.user_id, {
            "type": "reminder_delivery",
            "message": payload.message,
            "reminder_id": payload.reminder_id,
            "timestamp": now_utc_naive().isoformat(),
        })
    except Exception as push_error:
        logger.warning(f"Could not push playground message for reminder {payload.reminder_id}: {push_error}")

    logger.info(f"Reminder {payload.reminder_id} delivered successfully via SMS")
    return {"status": "delivered", "reminder_id": payload.reminder_id}


async def _create_delivery_audit_log(payload: DeliverReminderPayload) -> None:
    """Record reminder delivery in audit log for chat history persistence."""
    reminder_delivery_message = f"⏰ Reminder: {payload.message}"
    try:
        await db.log_action(
            user_id=payload.user_id,
            session_id=f"reminder_{payload.reminder_id}",
            action_type="reminder_delivery",
            request_summary="",  # Blank — system-initiated, no user request
            response_summary=reminder_delivery_message,
            status="success",
            tokens_used=0,
        )
        logger.info(f"Audit log created for reminder {payload.reminder_id} delivery")
    except Exception as log_error:
        logger.warning(f"Could not create audit log for reminder {payload.reminder_id}: {log_error}")


# ==================== List ====================

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


# ==================== Cancel ====================

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
        await _cancel_qstash_for_reminder(reminder, request.reminder_id)

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


# ==================== Update ====================

@router.post(
    "/reminders/update",
    response_model=BaseResponse,
    summary="Update an existing reminder",
    description="Update reminder message, time, or recurrence. Cancels old QStash schedule "
    "and creates new one with updated parameters.",
    responses={
        200: {"description": "Reminder updated successfully"},
        404: {"description": "Reminder not found"},
        400: {"description": "Invalid update parameters"},
    },
)
async def update_reminder(request: UpdateReminderRequest):
    """Update an existing reminder (message, time, or recurrence)."""
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

        # Check if already delivered or cancelled
        current_status = reminder.get("status")
        if current_status in ("cancelled", "delivered"):
            return error_response(
                message=f"Cannot update {current_status} reminder",
                error="invalid_status",
                code=ResponseCode.BAD_REQUEST,
            )

        # 2. Prepare updated fields
        update_data = {}

        # Update message if provided
        if request.message:
            update_data["message"] = request.message

        # Update trigger time if provided
        new_trigger_at_unix = None
        if request.trigger_at:
            # Convert to UTC
            trigger_at_utc = local_to_utc(
                request.trigger_at,
                request.user_timezone or reminder.get("user_timezone", "UTC")
            )
            new_trigger_at_unix = int(trigger_at_utc.timestamp())

            # Validate: trigger time must be in the future
            if new_trigger_at_unix <= int(now_utc_naive().timestamp()):
                return error_response(
                    message="New reminder time must be in the future",
                    error="invalid_trigger_time",
                    code=ResponseCode.BAD_REQUEST,
                )

            update_data["trigger_at"] = trigger_at_utc.isoformat()

        # Update recurrence if provided
        if request.recurrence:
            update_data["recurrence"] = request.recurrence

        # Update timezone if provided
        if request.user_timezone:
            update_data["user_timezone"] = request.user_timezone

        # 3. Cancel old QStash schedule
        await _cancel_qstash_for_reminder(reminder, request.reminder_id)
        if reminder.get("qstash_schedule_id"):
            update_data["qstash_schedule_id"] = None
        if reminder.get("qstash_message_id"):
            update_data["qstash_message_id"] = None

        # 4. Create new QStash schedule with updated parameters
        if qstash_service.is_configured:
            updated_message = request.message or reminder.get("message")
            updated_recurrence = request.recurrence or reminder.get("recurrence")
            updated_timezone = request.user_timezone or reminder.get("user_timezone")

            if updated_recurrence == "none":
                # One-time reminder
                trigger_unix = new_trigger_at_unix or int(datetime.fromisoformat(reminder.get("trigger_at")).timestamp())
                message_id = qstash_service.schedule_one_time(
                    reminder_id=request.reminder_id,
                    user_id=request.user_id,
                    message=updated_message,
                    trigger_at_unix=trigger_unix,
                )
                update_data["qstash_message_id"] = message_id
            else:
                # Recurring reminder
                trigger_dt = trigger_at_utc if request.trigger_at else datetime.fromisoformat(reminder.get("trigger_at"))
                cron_expr = recurrence_to_cron(
                    trigger_at=trigger_dt,
                    recurrence=updated_recurrence,
                    timezone=updated_timezone,
                )
                schedule_id = qstash_service.schedule_recurring(
                    reminder_id=request.reminder_id,
                    user_id=request.user_id,
                    message=updated_message,
                    cron_expression=cron_expr,
                )
                update_data["qstash_schedule_id"] = schedule_id

        # 5. Update database
        await db.update_reminder(request.reminder_id, update_data)

        logger.info(f"Updated reminder {request.reminder_id} for user {request.user_id}")

        # 6. Fetch updated reminder and return
        updated_reminder = await db.get_reminder(request.reminder_id)

        return success_response(
            message="Reminder updated successfully",
            data=ReminderData(
                id=request.reminder_id,
                user_id=request.user_id,
                message=updated_reminder.get("message"),
                trigger_at=updated_reminder.get("trigger_at"),
                user_timezone=updated_reminder.get("user_timezone"),
                recurrence=updated_reminder.get("recurrence"),
                status=updated_reminder.get("status"),
                created_at=updated_reminder.get("created_at", ""),
                qstash_message_id=updated_reminder.get("qstash_message_id"),
                qstash_schedule_id=updated_reminder.get("qstash_schedule_id"),
            ),
        )

    except ValueError as e:
        return error_response(
            message=str(e),
            error="validation_error",
            code=ResponseCode.BAD_REQUEST,
        )
    except Exception as e:
        logger.error(f"Error updating reminder {request.reminder_id}: {e}")
        return error_response(
            message="Failed to update reminder",
            error="internal_error",
            code=ResponseCode.INTERNAL_ERROR,
            exception=str(e),
        )
