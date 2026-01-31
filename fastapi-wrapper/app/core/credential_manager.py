import json
import os
from typing import Optional, Dict
from cryptography.fernet import Fernet
import aiofiles
from ..config import settings
import logging

logger = logging.getLogger(__name__)

class CredentialManager:
    """Encrypted credential storage"""
    
    def __init__(self):
        self.credentials_dir = settings.CREDENTIALS_DIR
        self.cipher = Fernet(settings.ENCRYPTION_KEY.encode())
    
    async def store_credentials(self, user_id: str, service: str, credentials: Dict) -> bool:
        """Store encrypted service credentials"""
        try:
            cred_file = os.path.join(self.credentials_dir, f"user_{user_id}.json")
            
            # Load existing credentials
            user_creds = {}
            if os.path.exists(cred_file):
                async with aiofiles.open(cred_file, 'r') as f:
                    content = await f.read()
                    user_creds = json.loads(content)
            
            # Encrypt new credentials
            encrypted = self.cipher.encrypt(json.dumps(credentials).encode())
            user_creds[service] = encrypted.decode()
            
            # Save
            async with aiofiles.open(cred_file, 'w') as f:
                await f.write(json.dumps(user_creds, indent=2))
            
            logger.info(f"Stored credentials for user {user_id}, service: {service}")
            return True
        except Exception as e:
            logger.error(f"Error storing credentials: {e}")
            return False
    
    async def get_credentials(self, user_id: str, service: str) -> Optional[Dict]:
        """Retrieve and decrypt credentials"""
        try:
            cred_file = os.path.join(self.credentials_dir, f"user_{user_id}.json")
            
            if not os.path.exists(cred_file):
                return None
            
            async with aiofiles.open(cred_file, 'r') as f:
                content = await f.read()
                user_creds = json.loads(content)
            
            if service not in user_creds:
                return None
            
            # Decrypt
            decrypted = self.cipher.decrypt(user_creds[service].encode())
            return json.loads(decrypted.decode())
        except Exception as e:
            logger.error(f"Error retrieving credentials: {e}")
            return None
    
    async def delete_credentials(self, user_id: str, service: str) -> bool:
        """Delete service credentials"""
        try:
            cred_file = os.path.join(self.credentials_dir, f"user_{user_id}.json")
            
            if not os.path.exists(cred_file):
                return False
            
            async with aiofiles.open(cred_file, 'r') as f:
                content = await f.read()
                user_creds = json.loads(content)
            
            if service in user_creds:
                del user_creds[service]
                
                async with aiofiles.open(cred_file, 'w') as f:
                    await f.write(json.dumps(user_creds, indent=2))
            
            return True
        except Exception as e:
            logger.error(f"Error deleting credentials: {e}")
            return False