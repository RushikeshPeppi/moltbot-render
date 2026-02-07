# Google Workspace Skill

**Production-grade OpenClaw skill** for Google Calendar and Gmail integration via direct API calls with dynamic parameter extraction.

## Features

### Google Calendar
- ✅ List today's/tomorrow's/this week's events
- ✅ Search events by keyword
- ✅ Get next N upcoming events
- ✅ Create new calendar events
- ✅ Update existing events
- ✅ Delete events
- ✅ Get specific event details

### Gmail
- ✅ List recent messages
- ✅ Search by sender, subject, keywords
- ✅ Filter unread/important/starred messages
- ✅ Get full message content
- ✅ Send emails
- ✅ Mark as read/unread
- ✅ Star/unstar messages
- ✅ Delete messages

## Requirements

- OAuth 2.0 access token (automatically provided via `$GOOGLE_ACCESS_TOKEN`)
- curl (available in all Unix-like environments)
- jq for JSON parsing (optional, for cleaner output)

## Usage

The skill is automatically available to the OpenClaw agent. The agent will use it when users ask about:
- Calendar: "What meetings do I have today?", "Schedule a meeting", etc.
- Gmail: "Show me my emails", "Send an email to John", etc.

## API Reference

- Google Calendar API v3: https://developers.google.com/workspace/calendar/api/v3/reference
- Gmail API v1: https://developers.google.com/gmail/api/reference/rest

## Author

Custom skill for Moltbot-Render project
