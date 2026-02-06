# Google Workspace - Calendar & Gmail

🎯 **Comprehensive Google Calendar and Gmail integration using OAuth tokens and direct API calls.**

## ⚡ When to Use This Skill

Use this skill when the user asks about:
- **Calendar**: meetings, appointments, schedule, calendar events, today's meetings, tomorrow's schedule, next week's calendar
- **Gmail**: emails, messages, inbox, unread emails, important emails, send email, compose message

## 🔑 Environment Variables

The OAuth access token is automatically available:
- `$GOOGLE_ACCESS_TOKEN` - OAuth 2.0 bearer token (auto-refreshed)

## 📅 GOOGLE CALENDAR API

All endpoints use: `https://www.googleapis.com/calendar/v3`

### List Today's Events

When user asks: "What meetings do I have today?" or "What's on my schedule today?"

```bash
# Calculate today's date range dynamically
TODAY_START=$(date -u +%Y-%m-%dT00:00:00Z)
TODAY_END=$(date -u +%Y-%m-%dT23:59:59Z)

curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=${TODAY_START}&timeMax=${TODAY_END}&singleEvents=true&orderBy=startTime"
```

### List Tomorrow's Events

When user asks: "What meetings do I have tomorrow?" or "What's my schedule tomorrow?"

```bash
# Calculate tomorrow's date range dynamically
TOMORROW_START=$(date -u -d '+1 day' +%Y-%m-%dT00:00:00Z)
TOMORROW_END=$(date -u -d '+1 day' +%Y-%m-%dT23:59:59Z)

curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=${TOMORROW_START}&timeMax=${TOMORROW_END}&singleEvents=true&orderBy=startTime"
```

### List This Week's Events

When user asks: "What meetings do I have this week?" or "What's my schedule this week?"

```bash
# Calculate this week's date range (Monday to Sunday)
WEEK_START=$(date -u -d 'monday this week' +%Y-%m-%dT00:00:00Z)
WEEK_END=$(date -u -d 'sunday this week' +%Y-%m-%dT23:59:59Z)

curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=${WEEK_START}&timeMax=${WEEK_END}&singleEvents=true&orderBy=startTime"
```

### List Next N Events

When user asks: "What are my next 5 meetings?" or "Show me upcoming appointments"

```bash
curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?maxResults=5&singleEvents=true&orderBy=startTime&timeMin=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

### Search Events by Keyword

When user asks: "Do I have any meetings with John?" or "Find meetings about project X"

```bash
QUERY="John"  # or "project X"

curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?q=${QUERY}&singleEvents=true&orderBy=startTime"
```

### Get Specific Event Details

When you have an event ID and need full details:

```bash
EVENT_ID="eventid123"

curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events/${EVENT_ID}"
```

### Create New Event

When user says: "Schedule a meeting with John tomorrow at 2 PM" or "Create a calendar event"

```bash
# Calculate event time dynamically based on user's request
# Example: tomorrow at 2 PM
EVENT_START=$(date -u -d 'tomorrow 14:00' +%Y-%m-%dT%H:%M:%SZ)
EVENT_END=$(date -u -d 'tomorrow 15:00' +%Y-%m-%dT%H:%M:%SZ)

curl -s -X POST \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"summary\": \"Meeting with John\",
    \"description\": \"Discuss project updates\",
    \"start\": {
      \"dateTime\": \"${EVENT_START}\",
      \"timeZone\": \"UTC\"
    },
    \"end\": {
      \"dateTime\": \"${EVENT_END}\",
      \"timeZone\": \"UTC\"
    },
    \"attendees\": [
      {\"email\": \"john@example.com\"}
    ],
    \"reminders\": {
      \"useDefault\": false,
      \"overrides\": [
        {\"method\": \"email\", \"minutes\": 30},
        {\"method\": \"popup\", \"minutes\": 10}
      ]
    }
  }" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events"
```

### Update Event

When user says: "Change my 2 PM meeting to 3 PM" or "Update the meeting description"

```bash
EVENT_ID="eventid123"  # Get this from listing events first

# Calculate new time dynamically
NEW_START=$(date -u -d 'today 15:00' +%Y-%m-%dT%H:%M:%SZ)
NEW_END=$(date -u -d 'today 16:00' +%Y-%m-%dT%H:%M:%SZ)

curl -s -X PUT \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"summary\": \"Updated Meeting Title\",
    \"start\": {
      \"dateTime\": \"${NEW_START}\",
      \"timeZone\": \"UTC\"
    },
    \"end\": {
      \"dateTime\": \"${NEW_END}\",
      \"timeZone\": \"UTC\"
    }
  }" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events/${EVENT_ID}"
```

### Delete Event

When user says: "Cancel my meeting with John" or "Delete the 2 PM appointment"

```bash
EVENT_ID="eventid123"

curl -s -X DELETE \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events/${EVENT_ID}"
```

## 📧 GMAIL API

All endpoints use: `https://gmail.googleapis.com/gmail/v1`

### List Recent Messages

When user asks: "Show me my recent emails" or "What are my latest messages?"

```bash
curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=10"
```

### List Unread Messages

When user asks: "Do I have any unread emails?" or "Show me unread messages"

```bash
curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages?q=is:unread&maxResults=10"
```

### List Important/Starred Messages

When user asks: "Any important emails?" or "Show me starred messages"

```bash
curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages?q=is:important&maxResults=10"
```

### Search Messages by Sender

When user asks: "Show me emails from John" or "Any messages from sarah@example.com?"

```bash
SENDER="john@example.com"

curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages?q=from:${SENDER}&maxResults=10"
```

### Search Messages by Subject

When user asks: "Find emails about project X" or "Show me messages with 'invoice' in subject"

```bash
SUBJECT="project X"

curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages?q=subject:${SUBJECT}&maxResults=10"
```

### Get Message Details

After listing messages, get full content of a specific message:

```bash
MESSAGE_ID="msg123abc"

curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages/${MESSAGE_ID}?format=full"
```

### Get Message (Metadata Only - Faster)

For quick preview without full body:

```bash
MESSAGE_ID="msg123abc"

curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages/${MESSAGE_ID}?format=metadata"
```

### Send Email

When user says: "Send an email to john@example.com" or "Compose a message"

**Step 1:** Create RFC 2822 formatted email and base64url encode it:

```bash
# Create email content
EMAIL_CONTENT="From: me
To: john@example.com
Subject: Meeting Follow-up

Hi John,

Thanks for the meeting today. Here are the action items we discussed:
1. Review the proposal
2. Schedule follow-up call

Best regards"

# Base64url encode (replace + with -, / with _, remove =)
ENCODED=$(echo -n "$EMAIL_CONTENT" | base64 | tr '+/' '-_' | tr -d '=')

# Send email
curl -s -X POST \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"raw\": \"$ENCODED\"}" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
```

### Mark Message as Read

When user says: "Mark this email as read"

```bash
MESSAGE_ID="msg123abc"

curl -s -X POST \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"removeLabelIds": ["UNREAD"]}' \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages/${MESSAGE_ID}/modify"
```

### Mark Message as Unread

```bash
MESSAGE_ID="msg123abc"

curl -s -X POST \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"addLabelIds": ["UNREAD"]}' \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages/${MESSAGE_ID}/modify"
```

### Star/Unstar Message

```bash
MESSAGE_ID="msg123abc"

# Star
curl -s -X POST \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"addLabelIds": ["STARRED"]}' \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages/${MESSAGE_ID}/modify"

# Unstar
curl -s -X POST \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"removeLabelIds": ["STARRED"]}' \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages/${MESSAGE_ID}/modify"
```

### Delete Message

When user says: "Delete this email" or "Move to trash"

```bash
MESSAGE_ID="msg123abc"

curl -s -X DELETE \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages/${MESSAGE_ID}"
```

## 🎯 Common Patterns & Best Practices

### Getting Current Date/Time

Always use `session_status` tool to get current date and time before making calendar queries:

```python
# This returns: "Friday, February 6th, 2026 — 5:56 PM (UTC)"
default_api.session_status()
```

Then parse to ISO 8601 format: `2026-02-06T17:56:00Z`

### Date Formatting

- Use ISO 8601 format with UTC timezone: `YYYY-MM-DDTHH:MM:SSZ`
- For all-day events, use date only: `YYYY-MM-DD`
- Always use `timeMin` and `timeMax` for calendar queries to filter results

### Parsing JSON Responses

Calendar and Gmail APIs return JSON. Use `exec` tool with `jq` for parsing:

```bash
# Extract event summaries
curl ... | jq -r '.items[] | .summary'

# Extract email subjects
curl ... | jq -r '.messages[].id'
```

### Error Handling

If API returns error:
- **401 Unauthorized**: OAuth token expired (shouldn't happen - auto-refreshed)
- **403 Forbidden**: Insufficient permissions
- **404 Not Found**: Event/message ID doesn't exist
- **429 Too Many Requests**: Rate limit exceeded (wait and retry)

### User-Friendly Responses

After making API calls:
1. Parse the JSON response
2. Format nicely for the user
3. Include relevant details (time, sender, subject, etc.)
4. If no results, inform user clearly

## 📚 Reference Documentation

- [Google Calendar API v3](https://developers.google.com/workspace/calendar/api/v3/reference)
- [Gmail API v1](https://developers.google.com/gmail/api/reference/rest)
- [Events: list](https://developers.google.com/workspace/calendar/api/v3/reference/events/list)
- [Messages: list](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list)

## 🔧 Implementation Notes

- All API calls use the `exec` tool with curl commands
- OAuth token is automatically available in `$GOOGLE_ACCESS_TOKEN`
- Token is auto-refreshed by the FastAPI backend
- Use `primary` as calendar ID for user's primary calendar
- Use `me` as user ID for Gmail API
- All times should be in UTC unless specified otherwise
