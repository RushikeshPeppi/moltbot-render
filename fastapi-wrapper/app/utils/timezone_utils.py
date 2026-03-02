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

    Uses CRON_TZ= prefix so QStash fires at the correct local time,
    automatically handling DST transitions. The trigger_at is in UTC
    but we convert to local time for the CRON fields.

    Args:
        trigger_at: UTC datetime for when to fire
        recurrence: One of 'daily', 'weekly', 'monthly', 'weekdays'
        timezone: User's IANA timezone (e.g., 'America/New_York')

    Returns:
        CRON expression string with CRON_TZ prefix

    Examples:
        - daily at 9am EST → "CRON_TZ=America/New_York 0 9 * * *"
        - weekly on Monday at 9am IST → "CRON_TZ=Asia/Kolkata 0 9 * * 1"
        - monthly on 15th at 10am IST → "CRON_TZ=Asia/Kolkata 0 10 15 * *"
    """
    # Convert UTC trigger_at to user's local time for CRON fields
    local_dt = utc_to_local(trigger_at, timezone)
    minute = local_dt.minute
    hour = local_dt.hour

    # CRON_TZ prefix tells QStash to interpret the schedule in the user's timezone
    # This automatically handles DST transitions
    tz_prefix = f"CRON_TZ={timezone} "

    if recurrence == "daily":
        return f"{tz_prefix}{minute} {hour} * * *"

    elif recurrence == "weekdays":
        return f"{tz_prefix}{minute} {hour} * * 1-5"

    elif recurrence == "weekly":
        # CRON: 0=Sunday, 1=Monday, ..., 6=Saturday
        # Python: 0=Monday, ..., 6=Sunday
        python_dow = local_dt.weekday()
        cron_dow = (python_dow + 1) % 7
        return f"{tz_prefix}{minute} {hour} * * {cron_dow}"

    elif recurrence == "monthly":
        day = local_dt.day
        return f"{tz_prefix}{minute} {hour} {day} * *"

    else:
        raise ValueError(f"Unsupported recurrence type: {recurrence}")
