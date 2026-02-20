"""
Gmail API integration service.
Handles email operations using OAuth tokens from credential manager.
"""

import logging
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List, Dict, Any
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..core.credential_manager import CredentialManager

logger = logging.getLogger(__name__)


class GmailService:
    """Service for interacting with Gmail API"""

    def __init__(self):
        self.credential_manager = CredentialManager()
        self.scopes = [
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/gmail.send',
            'https://www.googleapis.com/auth/gmail.modify'
        ]

    async def _get_gmail_service(self, user_id: str):
        """Get authenticated Gmail API service"""
        # Get valid access token
        access_token = await self.credential_manager.get_valid_google_token(user_id)

        if not access_token:
            raise ValueError("No valid Google OAuth token found for user")

        # Create credentials object
        credentials = Credentials(token=access_token)

        # Build Gmail service
        service = build('gmail', 'v1', credentials=credentials)
        return service

    async def list_messages(
        self,
        user_id: str,
        query: Optional[str] = None,
        max_results: int = 10,
        label_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        List Gmail messages.

        Args:
            user_id: User ID
            query: Gmail search query (e.g., "is:unread", "from:user@example.com")
            max_results: Maximum number of messages to return
            label_ids: List of label IDs to filter by (e.g., ['INBOX', 'UNREAD'])

        Returns:
            Dict with messages list and metadata
        """
        try:
            service = await self._get_gmail_service(user_id)

            # Build request parameters
            params = {
                'userId': 'me',
                'maxResults': max_results
            }

            if query:
                params['q'] = query

            if label_ids:
                params['labelIds'] = label_ids

            # List messages
            results = service.users().messages().list(**params).execute()
            messages = results.get('messages', [])

            # Get full message details for each
            detailed_messages = []
            for msg in messages:
                msg_detail = service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='metadata',
                    metadataHeaders=['From', 'To', 'Subject', 'Date']
                ).execute()
                detailed_messages.append(msg_detail)

            logger.info(f"Retrieved {len(detailed_messages)} messages for user {user_id}")

            return {
                'success': True,
                'count': len(detailed_messages),
                'messages': detailed_messages,
                'result_size_estimate': results.get('resultSizeEstimate', 0)
            }

        except HttpError as e:
            logger.error(f"Gmail API error for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_code': e.resp.status if hasattr(e, 'resp') else None
            }
        except Exception as e:
            logger.error(f"Error listing messages for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_message(
        self,
        user_id: str,
        message_id: str,
        format: str = 'full'
    ) -> Dict[str, Any]:
        """
        Get a specific Gmail message by ID.

        Args:
            user_id: User ID
            message_id: Gmail message ID
            format: Message format ('minimal', 'full', 'raw', 'metadata')

        Returns:
            Dict with message details
        """
        try:
            service = await self._get_gmail_service(user_id)

            message = service.users().messages().get(
                userId='me',
                id=message_id,
                format=format
            ).execute()

            logger.info(f"Retrieved message {message_id} for user {user_id}")

            return {
                'success': True,
                'message': message
            }

        except HttpError as e:
            logger.error(f"Gmail API error getting message for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_code': e.resp.status if hasattr(e, 'resp') else None
            }
        except Exception as e:
            logger.error(f"Error getting message for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def send_message(
        self,
        user_id: str,
        to: str,
        subject: str,
        body: str,
        cc: Optional[str] = None,
        bcc: Optional[str] = None,
        html: bool = False
    ) -> Dict[str, Any]:
        """
        Send an email via Gmail.

        Args:
            user_id: User ID
            to: Recipient email address
            subject: Email subject
            body: Email body text
            cc: CC recipients (comma-separated)
            bcc: BCC recipients (comma-separated)
            html: Whether body is HTML (default: False, plain text)

        Returns:
            Dict with sent message details
        """
        try:
            service = await self._get_gmail_service(user_id)

            # Create message
            if html:
                message = MIMEMultipart('alternative')
                message.attach(MIMEText(body, 'html'))
            else:
                message = MIMEText(body)

            message['to'] = to
            message['subject'] = subject

            if cc:
                message['cc'] = cc
            if bcc:
                message['bcc'] = bcc

            # Encode message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

            # Send message
            sent_message = service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()

            logger.info(f"Sent message {sent_message['id']} for user {user_id}")

            return {
                'success': True,
                'message': sent_message,
                'message_id': sent_message['id']
            }

        except HttpError as e:
            logger.error(f"Gmail API error sending message for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_code': e.resp.status if hasattr(e, 'resp') else None
            }
        except Exception as e:
            logger.error(f"Error sending message for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def delete_message(
        self,
        user_id: str,
        message_id: str
    ) -> Dict[str, Any]:
        """
        Delete a Gmail message (move to trash).

        Args:
            user_id: User ID
            message_id: Gmail message ID

        Returns:
            Dict with success status
        """
        try:
            service = await self._get_gmail_service(user_id)

            service.users().messages().trash(
                userId='me',
                id=message_id
            ).execute()

            logger.info(f"Deleted message {message_id} for user {user_id}")

            return {
                'success': True,
                'message_id': message_id
            }

        except HttpError as e:
            logger.error(f"Gmail API error deleting message for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_code': e.resp.status if hasattr(e, 'resp') else None
            }
        except Exception as e:
            logger.error(f"Error deleting message for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def mark_as_read(
        self,
        user_id: str,
        message_id: str
    ) -> Dict[str, Any]:
        """Mark a message as read"""
        try:
            service = await self._get_gmail_service(user_id)

            service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()

            logger.info(f"Marked message {message_id} as read for user {user_id}")

            return {
                'success': True,
                'message_id': message_id
            }

        except HttpError as e:
            logger.error(f"Gmail API error marking message as read for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_code': e.resp.status if hasattr(e, 'resp') else None
            }
        except Exception as e:
            logger.error(f"Error marking message as read for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def search_messages(
        self,
        user_id: str,
        query: str,
        max_results: int = 10
    ) -> Dict[str, Any]:
        """
        Search Gmail messages using Gmail search syntax.

        Args:
            user_id: User ID
            query: Gmail search query (e.g., "from:example@gmail.com subject:meeting")
            max_results: Maximum number of results

        Returns:
            Dict with matching messages
        """
        return await self.list_messages(
            user_id=user_id,
            query=query,
            max_results=max_results
        )
