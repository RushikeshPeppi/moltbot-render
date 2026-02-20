"""
Google Calendar API integration service.
Handles calendar operations using OAuth tokens from credential manager.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..core.credential_manager import CredentialManager

logger = logging.getLogger(__name__)


class GoogleCalendarService:
    """Service for interacting with Google Calendar API"""

    def __init__(self):
        self.credential_manager = CredentialManager()
        self.scopes = [
            'https://www.googleapis.com/auth/calendar',
            'https://www.googleapis.com/auth/calendar.events'
        ]

    async def _get_calendar_service(self, user_id: str):
        """Get authenticated Calendar API service"""
        # Get valid access token
        access_token = await self.credential_manager.get_valid_google_token(user_id)

        if not access_token:
            raise ValueError("No valid Google OAuth token found for user")

        # Create credentials object
        credentials = Credentials(token=access_token)

        # Build Calendar service
        service = build('calendar', 'v3', credentials=credentials)
        return service

    async def list_events(
        self,
        user_id: str,
        calendar_id: str = 'primary',
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,
        max_results: int = 10
    ) -> Dict[str, Any]:
        """
        List calendar events.

        Args:
            user_id: User ID
            calendar_id: Calendar ID (default: 'primary')
            time_min: Start time for events (default: now)
            time_max: End time for events (default: 7 days from now)
            max_results: Maximum number of events to return

        Returns:
            Dict with events list and metadata
        """
        try:
            service = await self._get_calendar_service(user_id)

            # Default time range: now to 7 days from now
            if not time_min:
                time_min = datetime.utcnow()
            if not time_max:
                time_max = time_min + timedelta(days=7)

            # Call Calendar API
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min.isoformat() + 'Z',
                timeMax=time_max.isoformat() + 'Z',
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])

            logger.info(f"Retrieved {len(events)} events for user {user_id}")

            return {
                'success': True,
                'count': len(events),
                'events': events,
                'calendar_id': calendar_id
            }

        except HttpError as e:
            logger.error(f"Calendar API error for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_code': e.resp.status if hasattr(e, 'resp') else None
            }
        except Exception as e:
            logger.error(f"Error listing events for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def create_event(
        self,
        user_id: str,
        summary: str,
        start_time: datetime,
        end_time: datetime,
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        calendar_id: str = 'primary'
    ) -> Dict[str, Any]:
        """
        Create a new calendar event.

        Args:
            user_id: User ID
            summary: Event title
            start_time: Event start time
            end_time: Event end time
            description: Event description (optional)
            location: Event location (optional)
            attendees: List of attendee emails (optional)
            calendar_id: Calendar ID (default: 'primary')

        Returns:
            Dict with created event details
        """
        try:
            service = await self._get_calendar_service(user_id)

            # Build event object
            event = {
                'summary': summary,
                'start': {
                    'dateTime': start_time.isoformat(),
                    'timeZone': 'UTC',
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': 'UTC',
                },
            }

            if description:
                event['description'] = description

            if location:
                event['location'] = location

            if attendees:
                event['attendees'] = [{'email': email} for email in attendees]

            # Create event
            created_event = service.events().insert(
                calendarId=calendar_id,
                body=event
            ).execute()

            logger.info(f"Created event {created_event['id']} for user {user_id}")

            return {
                'success': True,
                'event': created_event,
                'event_id': created_event['id'],
                'html_link': created_event.get('htmlLink')
            }

        except HttpError as e:
            logger.error(f"Calendar API error creating event for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_code': e.resp.status if hasattr(e, 'resp') else None
            }
        except Exception as e:
            logger.error(f"Error creating event for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_event(
        self,
        user_id: str,
        event_id: str,
        calendar_id: str = 'primary'
    ) -> Dict[str, Any]:
        """Get a specific calendar event by ID"""
        try:
            service = await self._get_calendar_service(user_id)

            event = service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()

            logger.info(f"Retrieved event {event_id} for user {user_id}")

            return {
                'success': True,
                'event': event
            }

        except HttpError as e:
            logger.error(f"Calendar API error getting event for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_code': e.resp.status if hasattr(e, 'resp') else None
            }
        except Exception as e:
            logger.error(f"Error getting event for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def update_event(
        self,
        user_id: str,
        event_id: str,
        summary: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        calendar_id: str = 'primary'
    ) -> Dict[str, Any]:
        """Update an existing calendar event"""
        try:
            service = await self._get_calendar_service(user_id)

            # Get existing event
            event = service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()

            # Update fields
            if summary:
                event['summary'] = summary
            if description is not None:
                event['description'] = description
            if location is not None:
                event['location'] = location
            if start_time:
                event['start'] = {
                    'dateTime': start_time.isoformat(),
                    'timeZone': 'UTC',
                }
            if end_time:
                event['end'] = {
                    'dateTime': end_time.isoformat(),
                    'timeZone': 'UTC',
                }

            # Update event
            updated_event = service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=event
            ).execute()

            logger.info(f"Updated event {event_id} for user {user_id}")

            return {
                'success': True,
                'event': updated_event
            }

        except HttpError as e:
            logger.error(f"Calendar API error updating event for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_code': e.resp.status if hasattr(e, 'resp') else None
            }
        except Exception as e:
            logger.error(f"Error updating event for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def delete_event(
        self,
        user_id: str,
        event_id: str,
        calendar_id: str = 'primary'
    ) -> Dict[str, Any]:
        """Delete a calendar event"""
        try:
            service = await self._get_calendar_service(user_id)

            service.events().delete(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()

            logger.info(f"Deleted event {event_id} for user {user_id}")

            return {
                'success': True,
                'event_id': event_id
            }

        except HttpError as e:
            logger.error(f"Calendar API error deleting event for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_code': e.resp.status if hasattr(e, 'resp') else None
            }
        except Exception as e:
            logger.error(f"Error deleting event for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
