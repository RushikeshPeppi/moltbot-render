"""
OpenClaw Gateway Client with retry logic and robust error handling.
Implements exponential backoff with maximum 3 retries.
"""

import httpx
import asyncio
from typing import Dict, Optional, List, Any
from ..config import settings
import logging

logger = logging.getLogger(__name__)


class OpenClawClientError(Exception):
    """Custom exception for OpenClaw client errors"""
    def __init__(self, message: str, error_type: str, retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.retryable = retryable


class OpenClawClient:
    """
    Client for communicating with OpenClaw Gateway.
    
    Features:
    - Retry logic with exponential backoff (max 3 retries)
    - Proper error categorization
    - Connection pooling via httpx
    - Timeout handling
    """
    
    MAX_RETRIES = 3
    BASE_DELAY = 1.0  # Initial delay in seconds
    MAX_DELAY = 10.0  # Maximum delay between retries
    
    # Retryable HTTP status codes
    RETRYABLE_STATUS_CODES = {502, 503, 504, 429}
    
    def __init__(self):
        self.base_url = settings.MOLTBOT_GATEWAY_URL
        self.timeout = settings.MOLTBOT_TIMEOUT
    
    async def send_message(
        self,
        session_id: str,
        message: str,
        user_credentials: Optional[Dict] = None,
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Send message to OpenClaw Gateway with retry logic.
        
        Retry conditions:
        - Network errors (connection refused, timeout)
        - Server errors (502, 503, 504)
        - Rate limits (429)
        
        No retry for:
        - Client errors (400, 401, 403, 404)
        - Successful responses
        """
        payload = {
            "session_id": session_id,
            "message": message,
            "credentials": user_credentials or {},
            "history": conversation_history or []
        }
        
        last_exception = None
        
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                logger.info(f"[{session_id}] Attempt {attempt}/{self.MAX_RETRIES}: Sending message")
                
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/execute",
                        json=payload
                    )
                    
                    # Check if response is retryable
                    if response.status_code in self.RETRYABLE_STATUS_CODES:
                        error_msg = f"Server returned {response.status_code}"
                        logger.warning(f"[{session_id}] {error_msg}, retrying...")
                        last_exception = OpenClawClientError(
                            message=error_msg,
                            error_type="SERVER_ERROR",
                            retryable=True
                        )
                        await self._wait_before_retry(attempt)
                        continue
                    
                    # Check for client errors (non-retryable)
                    if 400 <= response.status_code < 500:
                        error_body = response.text
                        logger.error(f"[{session_id}] Client error {response.status_code}: {error_body}")
                        raise OpenClawClientError(
                            message=f"Client error: {response.status_code}",
                            error_type="CLIENT_ERROR",
                            retryable=False
                        )
                    
                    # Successful response
                    response.raise_for_status()
                    result = response.json()
                    
                    logger.info(f"[{session_id}] Success on attempt {attempt}")
                    return result
                    
            except httpx.TimeoutException as e:
                logger.warning(f"[{session_id}] Timeout on attempt {attempt}: {e}")
                last_exception = OpenClawClientError(
                    message="Request timed out",
                    error_type="TIMEOUT",
                    retryable=True
                )
                if attempt < self.MAX_RETRIES:
                    await self._wait_before_retry(attempt)
                    
            except httpx.ConnectError as e:
                logger.warning(f"[{session_id}] Connection error on attempt {attempt}: {e}")
                last_exception = OpenClawClientError(
                    message="Failed to connect to OpenClaw gateway",
                    error_type="CONNECTION_ERROR",
                    retryable=True
                )
                if attempt < self.MAX_RETRIES:
                    await self._wait_before_retry(attempt)
                    
            except httpx.HTTPStatusError as e:
                logger.error(f"[{session_id}] HTTP error on attempt {attempt}: {e}")
                last_exception = OpenClawClientError(
                    message=str(e),
                    error_type="HTTP_ERROR",
                    retryable=False
                )
                break  # Don't retry HTTP errors (already handled above)
                
            except OpenClawClientError:
                raise  # Re-raise our custom errors
                
            except Exception as e:
                logger.error(f"[{session_id}] Unexpected error on attempt {attempt}: {e}")
                last_exception = OpenClawClientError(
                    message=f"Unexpected error: {str(e)}",
                    error_type="UNKNOWN_ERROR",
                    retryable=False
                )
                break  # Don't retry unexpected errors
        
        # All retries exhausted
        logger.error(f"[{session_id}] All {self.MAX_RETRIES} attempts failed")
        if last_exception:
            raise last_exception
        else:
            raise OpenClawClientError(
                message="All retry attempts exhausted",
                error_type="RETRY_EXHAUSTED",
                retryable=False
            )
    
    async def _wait_before_retry(self, attempt: int) -> None:
        """
        Calculate and wait with exponential backoff.
        Delay = min(BASE_DELAY * 2^attempt, MAX_DELAY)
        """
        delay = min(self.BASE_DELAY * (2 ** attempt), self.MAX_DELAY)
        logger.debug(f"Waiting {delay}s before retry attempt {attempt + 1}")
        await asyncio.sleep(delay)
    
    async def health_check(self) -> bool:
        """
        Check if OpenClaw Gateway is online.
        Single attempt, no retry for health checks.
        """
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"OpenClaw health check failed: {e}")
            return False
    
    async def get_skills(self) -> List[Dict[str, Any]]:
        """Get list of available skills from OpenClaw"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.base_url}/skills")
                if response.status_code == 200:
                    return response.json().get('skills', [])
                return []
        except Exception as e:
            logger.warning(f"Failed to get skills: {e}")
            return []


# Backwards compatibility alias
MoltbotClient = OpenClawClient