import httpx
from typing import Dict, Optional, List
from ..config import settings
import logging

logger = logging.getLogger(__name__)

class MoltbotClient:
    """Client for communicating with Moltbot Gateway"""
    
    def __init__(self):
        self.base_url = settings.MOLTBOT_GATEWAY_URL
        self.timeout = settings.MOLTBOT_TIMEOUT
    
    async def send_message(
        self,
        session_id: str,
        message: str,
        user_credentials: Optional[Dict] = None,
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict:
        """Send message to Moltbot Gateway"""
        
        payload = {
            "session_id": session_id,
            "message": message,
            "credentials": user_credentials or {},
            "history": conversation_history or []
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/execute",
                    json=payload
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Moltbot request failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error calling Moltbot: {e}")
            raise
    
    async def health_check(self) -> bool:
        """Check if Moltbot Gateway is online"""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Moltbot health check failed: {e}")
            return False