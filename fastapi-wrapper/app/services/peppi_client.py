"""
Peppi Outbound SMS Client.
Calls the Peppi Laravel API to proactively send SMS to a user via Twilio.

This is used by the reminder delivery endpoint to send reminder SMS messages.
The Peppi endpoint handles looking up the user's phone number and sending via Twilio.
"""
import asyncio
import httpx
import logging
from typing import Optional, Dict, Any

from ..config import settings
from ..core.database import db

logger = logging.getLogger(__name__)

# peppi.ai sits behind Cloudflare + an origin openresty reverse-proxy (host-level,
# not in either app repo). That proxy INTERMITTENTLY returns these statuses BEFORE
# the request reaches Laravel/Twilio (confirmed: ~2 of 7 recent sends 415'd with an
# openresty body while the rest succeeded; off-cycle probes never fail). Because the
# request never reached the app, no SMS was sent — so retrying is safe (no duplicate).
PROXY_RETRY_STATUSES = {415, 502, 503, 504}
MAX_SEND_ATTEMPTS = 3
RETRY_BACKOFF_S = 1.5


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

        url = settings.PEPPI_OUTBOUND_URL
        payload = {
            "user_id": user_id,
            "message": message,
            "source": source,
            "priority": priority,
        }
        headers = {
            "Authorization": f"Bearer {settings.PEPPI_OUTBOUND_API_KEY}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(1, MAX_SEND_ATTEMPTS + 1):
                # Connection/timeout errors — the request may not have landed; retry.
                try:
                    response = await client.post(url, json=payload, headers=headers)
                except httpx.TransportError as conn_err:
                    if attempt < MAX_SEND_ATTEMPTS:
                        logger.warning(
                            f"Peppi outbound transport error for user {user_id} "
                            f"(attempt {attempt}/{MAX_SEND_ATTEMPTS}): {conn_err} — retrying"
                        )
                        await asyncio.sleep(RETRY_BACKOFF_S * attempt)
                        continue
                    logger.error(f"Failed to send SMS to user {user_id}: {conn_err}")
                    raise

                # Intermittent origin-proxy rejection (openresty 415/5xx) — the request
                # never reached Laravel/Twilio, so no SMS was sent. Retry a good backend.
                if response.status_code in PROXY_RETRY_STATUSES and attempt < MAX_SEND_ATTEMPTS:
                    logger.warning(
                        f"Peppi outbound proxy error {response.status_code} for user "
                        f"{user_id} (attempt {attempt}/{MAX_SEND_ATTEMPTS}, "
                        f"server={response.headers.get('server')}) — retrying"
                    )
                    await asyncio.sleep(RETRY_BACKOFF_S * attempt)
                    continue

                # Final attempt, or a non-retryable status: raise on error, else parse.
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as e:
                    logger.error(
                        f"Peppi SMS API error for user {user_id}: "
                        f"status={e.response.status_code}, body={e.response.text}"
                    )
                    raise

                result = response.json()
                logger.info(
                    f"SMS sent to user {user_id} via Peppi: "
                    f"status={result.get('status')}, twilio_sid={result.get('twilio_sid')}"
                    + (f" (after {attempt} attempts)" if attempt > 1 else "")
                )

                # Log to sms_log table regardless of which endpoint handled it
                try:
                    await db.log_outbound_sms(
                        user_id=user_id,
                        message=message,
                        source=source,
                        priority=priority,
                    )
                except Exception as log_err:
                    logger.warning(f"Failed to log outbound SMS for user {user_id}: {log_err}")

                return result


# Singleton instance
peppi_client = PeppiClient()
