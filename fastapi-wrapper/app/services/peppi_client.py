"""
Peppi Outbound SMS Client.
Calls the Peppi Laravel API to proactively send SMS to a user via Twilio.

This is used by the reminder delivery endpoint to send reminder SMS messages.
The Peppi endpoint handles looking up the user's phone number and sending via Twilio.
"""
import httpx
import logging
from typing import Optional, Dict, Any

from ..config import settings

logger = logging.getLogger(__name__)


class PeppiClient:
    """Client for Peppi's outbound SMS API"""

    @property
    def is_configured(self) -> bool:
        """Check if Peppi outbound SMS is configured."""
        return bool(settings.PEPPI_OUTBOUND_URL and settings.PEPPI_OUTBOUND_API_KEY)

    async def send_sms(
        self,
        user_id: str,
        message: str,
        source: str = "moltbot-reminder",
        priority: str = "normal",
    ) -> Dict[str, Any]:
        """
        Send an outbound SMS to a user via Peppi's API.
        
        Args:
            user_id: Peppi's internal user ID
            message: SMS text to send
            source: Identifies the caller (e.g., "moltbot-reminder")
            priority: "normal" or "high"
            
        Returns:
            Response dict with status, message_id, twilio_sid, delivered_at
            
        Raises:
            httpx.HTTPStatusError: If the API returns an error status
            Exception: If the request fails
        """
        if not self.is_configured:
            logger.warning("Peppi outbound SMS not configured — skipping SMS delivery")
            return {
                "status": "skipped",
                "message": "Peppi outbound SMS not configured",
            }

        url = f"{settings.PEPPI_OUTBOUND_URL}/api/v1/outbound/send-message"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    json={
                        "user_id": user_id,
                        "message": message,
                        "source": source,
                        "priority": priority,
                    },
                    headers={
                        "Authorization": f"Bearer {settings.PEPPI_OUTBOUND_API_KEY}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                result = response.json()

                logger.info(
                    f"SMS sent to user {user_id} via Peppi: "
                    f"status={result.get('status')}, "
                    f"twilio_sid={result.get('twilio_sid')}"
                )
                return result

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Peppi SMS API error for user {user_id}: "
                f"status={e.response.status_code}, body={e.response.text}"
            )
            raise
        except Exception as e:
            logger.error(f"Failed to send SMS to user {user_id}: {e}")
            raise


# Singleton instance
peppi_client = PeppiClient()
