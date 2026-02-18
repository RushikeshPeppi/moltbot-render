"""
QStash Service for scheduling and managing reminders.
Handles one-time delayed messages and recurring schedules via Upstash QStash.

One-time reminders use publish_json with not_before (Unix timestamp).
Recurring reminders use schedule.create with CRON expressions.
"""
import logging
from qstash import QStash

from ..config import settings

logger = logging.getLogger(__name__)


class QStashService:
    """Service for scheduling reminders via Upstash QStash"""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        """Lazy-initialize QStash client."""
        if self._client is None and settings.QSTASH_TOKEN:
            self._client = QStash(token=settings.QSTASH_TOKEN)
            logger.info("QStash client initialized")
        return self._client

    @property
    def is_configured(self) -> bool:
        """Check if QStash is configured."""
        return bool(settings.QSTASH_TOKEN)

    def schedule_one_time(
        self,
        reminder_id: int,
        user_id: str,
        message: str,
        trigger_at_unix: int,
    ) -> str:
        """
        Schedule a one-time reminder using QStash publish with not_before.
        
        Args:
            reminder_id: DB reminder ID
            user_id: Peppi user ID
            message: Reminder text
            trigger_at_unix: Unix timestamp for when to fire
            
        Returns:
            QStash message ID
        """
        deliver_url = f"{settings.MOLTBOT_PUBLIC_URL}/api/v1/reminders/deliver"

        try:
            res = self.client.message.publish_json(
                url=deliver_url,
                body={
                    "reminder_id": reminder_id,
                    "user_id": user_id,
                    "message": message,
                },
                not_before=trigger_at_unix,
                retries=3,
            )
            logger.info(
                f"Scheduled one-time reminder {reminder_id} for user {user_id}, "
                f"message_id={res.message_id}"
            )
            return res.message_id
        except Exception as e:
            logger.error(f"Failed to schedule one-time reminder {reminder_id}: {e}")
            raise

    def schedule_recurring(
        self,
        reminder_id: int,
        user_id: str,
        message: str,
        cron_expression: str,
    ) -> str:
        """
        Create a recurring schedule using QStash schedules.
        
        Args:
            reminder_id: DB reminder ID
            user_id: Peppi user ID
            message: Reminder text
            cron_expression: CRON expression (e.g., "30 8 * * *" for daily at 8:30 UTC)
            
        Returns:
            QStash schedule ID
        """
        deliver_url = f"{settings.MOLTBOT_PUBLIC_URL}/api/v1/reminders/deliver"

        try:
            schedule_id = self.client.schedule.create(
                destination=deliver_url,
                cron=cron_expression,
                body={
                    "reminder_id": reminder_id,
                    "user_id": user_id,
                    "message": message,
                },
                retries=3,
            )
            logger.info(
                f"Created recurring schedule for reminder {reminder_id}, "
                f"cron={cron_expression}, schedule_id={schedule_id}"
            )
            return schedule_id
        except Exception as e:
            logger.error(f"Failed to create recurring schedule for reminder {reminder_id}: {e}")
            raise

    def cancel_message(self, message_id: str) -> None:
        """Cancel a pending one-time QStash message."""
        try:
            self.client.message.cancel(message_id)
            logger.info(f"Cancelled QStash message: {message_id}")
        except Exception as e:
            logger.error(f"Failed to cancel QStash message {message_id}: {e}")
            raise

    def cancel_schedule(self, schedule_id: str) -> None:
        """Delete a recurring QStash schedule."""
        try:
            self.client.schedule.delete(schedule_id)
            logger.info(f"Deleted QStash schedule: {schedule_id}")
        except Exception as e:
            logger.error(f"Failed to delete QStash schedule {schedule_id}: {e}")
            raise


# Singleton instance
qstash_service = QStashService()
