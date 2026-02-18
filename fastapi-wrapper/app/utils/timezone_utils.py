"""
Timezone conversion utilities for reminders.
Handles local-to-UTC conversions and CRON expression generation.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger(__name__)


def local_to_utc(dt_str: str, timezone: str) -> datetime:
    """
    Convert a local datetime string to UTC datetime.
    
    Args:
        dt_str: ISO 8601 datetime string (may or may not include timezone info)
        timezone: IANA timezone name (e.g., 'Asia/Kolkata', 'America/New_York')
        
    Returns:
        UTC datetime object (timezone-aware)
    """
    try:
        # Parse the datetime string
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        
        # If already has timezone info (e.g., ends with Z or +00:00), just convert
        if dt.tzinfo is not None:
            return dt.astimezone(ZoneInfo("UTC"))
        
        # If naive (no timezone), assume it's in the user's local timezone
        local_tz = ZoneInfo(timezone)
        dt_local = dt.replace(tzinfo=local_tz)
        return dt_local.astimezone(ZoneInfo("UTC"))
        
    except Exception as e:
        logger.error(f"Error converting '{dt_str}' from '{timezone}' to UTC: {e}")
        raise ValueError(f"Invalid datetime or timezone: {e}")


def utc_to_local(dt: datetime, timezone: str) -> datetime:
    """
    Convert a UTC datetime to local timezone for display.
    
    Args:
        dt: UTC datetime object
        timezone: IANA timezone name
        
    Returns:
        Datetime in the user's local timezone
    """
    try:
        local_tz = ZoneInfo(timezone)
        
        # Ensure the datetime is UTC-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
            
        return dt.astimezone(local_tz)
        
    except Exception as e:
        logger.error(f"Error converting UTC to '{timezone}': {e}")
        raise ValueError(f"Invalid timezone: {e}")


def recurrence_to_cron(trigger_at: datetime, recurrence: str, timezone: str) -> str:
    """
    Build a CRON expression from recurrence type and trigger time.
    
    The trigger_at should be in UTC. The CRON expression will fire at that
    UTC time according to the recurrence pattern.
    
    Args:
        trigger_at: UTC datetime for when to fire
        recurrence: One of 'daily', 'weekly', 'monthly'
        timezone: User's timezone (used for weekly/monthly day-of-week calculation)
        
    Returns:
        5-field CRON expression string
        
    Examples:
        - daily at 2pm IST → trigger_at=8:30 UTC → "30 8 * * *"
        - weekly on Monday at 9am IST → trigger_at=3:30 UTC → "30 3 * * 1"
        - monthly on 15th at 10am IST → trigger_at=4:30 UTC → "30 4 15 * *"
    """
    # Use the UTC time components for the CRON expression
    minute = trigger_at.minute
    hour = trigger_at.hour
    
    # Convert trigger_at to local time for day-of-week/day-of-month context
    local_dt = utc_to_local(trigger_at, timezone)
    
    if recurrence == "daily":
        # Fire every day at the same UTC time
        return f"{minute} {hour} * * *"
        
    elif recurrence == "weekly":
        # Fire on the same day of the week (use local day-of-week)
        # CRON: 0=Sunday, 1=Monday, ..., 6=Saturday
        # Python: 0=Monday, ..., 6=Sunday
        python_dow = local_dt.weekday()
        cron_dow = (python_dow + 1) % 7  # Convert Python to CRON day-of-week
        return f"{minute} {hour} * * {cron_dow}"
        
    elif recurrence == "monthly":
        # Fire on the same day of the month
        day = local_dt.day
        return f"{minute} {hour} {day} * *"
        
    else:
        raise ValueError(f"Unsupported recurrence type: {recurrence}")
