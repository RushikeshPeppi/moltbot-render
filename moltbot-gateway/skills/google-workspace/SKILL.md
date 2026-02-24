---
name: google-workspace
description: Google Calendar and Gmail - list events, view calendar, check schedule, show meetings, get appointments, create/update/delete events, read/send emails, check inbox, search emails, recent messages, unread emails, send message, compose email, find messages, email search, reply to email, respond to message, answer email
user-invocable: true
metadata: {"openclaw": {"emoji": "📧"}}
---

# Google Workspace - Calendar & Gmail

🎯 **Comprehensive Google Calendar and Gmail integration using OAuth tokens and direct API calls.**

## ⚡ When to Use This Skill

Use this skill when the user asks about:
- **Calendar**: list meetings, view schedule, check calendar, what meetings, create/update/delete events, appointments
- **Gmail**: read emails, check inbox, send email, search messages, mark read/unread

## 🔑 Environment Variables

The OAuth access token is automatically available:
- `$GOOGLE_ACCESS_TOKEN` - OAuth 2.0 bearer token (auto-refreshed by FastAPI backend)

## 📅 GOOGLE CALENDAR API

Base URL: `https://www.googleapis.com/calendar/v3`

### CRITICAL: Date/Time Parsing Instructions

**ALWAYS extract date and time from the user's actual request. NEVER use hardcoded values.**

Parse user input to extract:
- **Date**: "tomorrow", "today", "next Tuesday", "February 15", "in 3 days"
- **Time**: "at 6pm", "at 14:00", "2 PM", "noon", "morning" (default 9am), "afternoon" (default 2pm)
- **Duration**: Default 1 hour if not specified. "30 minute meeting" = 30min, "2 hour call" = 2hr

### 🚨 TIMEZONE HANDLING - CRITICAL RULES

**Rule 1: User speaks in their LOCAL timezone ($USER_TIMEZONE), NOT UTC**
- When user says "tomorrow at 2pm", they mean 2pm in THEIR timezone
- You MUST convert this to UTC for the Calendar API
- Use `TZ="$USER_TIMEZONE"` when parsing user input

**Rule 2: "Tomorrow" depends on when the user is speaking**
- If conversation happens at 11:30 PM on Monday night:
  - "Tomorrow" = Tuesday (the next calendar day from their perspective)
  - "Today" = Monday (even though it might be early Tuesday UTC)
- Always calculate relative dates from the user's current time in THEIR timezone

**Rule 3: When updating/deleting events, search in the user's timezone context**
- If user says "my meeting tomorrow", search for events on tomorrow in THEIR timezone
- Don't search by UTC date - you'll get the wrong day

Calculate dates dynamically using `date` command WITH timezone context:

```bash
# CORRECT: Use user's timezone for date calculations
TZ="$USER_TIMEZONE" date -d "tomorrow 14:00"  # → User's tomorrow at 2pm
TZ="$USER_TIMEZONE" date -u -d "tomorrow 14:00" +%Y-%m-%dT%H:%M:%SZ  # → Convert to UTC for API

# WRONG: Using UTC for user-facing dates
date -u -d "tomorrow 14:00"  # ❌ This is tomorrow UTC, not user's tomorrow!
```

Common date patterns (ALWAYS use `TZ="$USER_TIMEZONE"`):
- Today: `$(TZ="$USER_TIMEZONE" date -u -d "today" +%Y-%m-%dT00:00:00Z)`
- Tomorrow: `$(TZ="$USER_TIMEZONE" date -u -d "tomorrow" +%Y-%m-%dT00:00:00Z)`
- Tomorrow at 2pm: `$(TZ="$USER_TIMEZONE" date -u -d "tomorrow 14:00" +%Y-%m-%dT%H:%M:%SZ)`
- Next Tuesday at 6pm: `$(TZ="$USER_TIMEZONE" date -u -d "next Tuesday 18:00" +%Y-%m-%dT%H:%M:%SZ)`
- In 3 days: `$(TZ="$USER_TIMEZONE" date -u -d "+3 days" +%Y-%m-%dT00:00:00Z)`

Time conversion rules:
- "6pm" → 18:00
- "2 PM" → 14:00
- "noon" → 12:00
- "midnight" → 00:00
- No time specified → default to 9:00 for morning, 14:00 for afternoon

### 🎯 Example: Handling "tomorrow at 2pm" correctly

```bash
# User is in Asia/Kolkata (UTC+5:30), it's Monday 11:30 PM
# They say "create a meeting tomorrow at 2pm"

# CORRECT approach:
TZ="$USER_TIMEZONE" date -u -d "tomorrow 14:00" +%Y-%m-%dT%H:%M:%SZ
# → Output: 2026-02-25T08:30:00Z (Tuesday 2pm IST = Tuesday 8:30am UTC)

# WRONG approach:
date -u -d "tomorrow 14:00" +%Y-%m-%dT%H:%M:%SZ
# → Output: 2026-02-25T14:00:00Z (Tuesday 2pm UTC, which is 7:30pm IST - WRONG!)
```

### List Events (Today/Tomorrow/This Week/Range)

When user asks: "What meetings do I have today?" or "What's on my schedule tomorrow?" or "what meetings do I have this week?"

**YOU MUST execute the curl command and parse the JSON response. DO NOT just describe what to do - ACTUALLY RUN THE COMMAND.**

```bash
# For TODAY's events
RESPONSE=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=$(date -u +%Y-%m-%dT00:00:00Z)&timeMax=$(date -u +%Y-%m-%dT23:59:59Z)&singleEvents=true&orderBy=startTime")

echo "$RESPONSE" | jq -r '.items[] | "\(.summary) at \(.start.dateTime // .start.date)"'

# For THIS WEEK's events (next 7 days)
RESPONSE=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=$(date -u +%Y-%m-%dT00:00:00Z)&timeMax=$(date -u -d '+7 days' +%Y-%m-%dT23:59:59Z)&singleEvents=true&orderBy=startTime")

echo "$RESPONSE" | jq -r '.items[] | "\(.summary) at \(.start.dateTime // .start.date)"'

# For TOMORROW's events
RESPONSE=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=$(date -u -d '+1 day' +%Y-%m-%dT00:00:00Z)&timeMax=$(date -u -d '+1 day' +%Y-%m-%dT23:59:59Z)&singleEvents=true&orderBy=startTime")

echo "$RESPONSE" | jq -r '.items[] | "\(.summary) at \(.start.dateTime // .start.date)"'
```

**The response will be a list of events with their names and times. Present this to the user in a friendly format.**

### List Next N Events

When user asks: "What are my next 5 meetings?" or "Show upcoming appointments"

**PARSE the number N from user's request.** Default to 10 if not specified.

```bash
# Extract N from user request (e.g., "next 5 meetings" → N=5)
N=<USER_REQUESTED_COUNT>

curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?maxResults=${N}&singleEvents=true&orderBy=startTime&timeMin=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

### Search Events by Keyword

When user asks: "Do I have any meetings with Marvin?" or "Find meetings about project X"

**EXTRACT the search keyword from user's request.**
- "meetings with Marvin" → QUERY="Marvin"
- "meetings about project X" → QUERY="project X"
- "standup meetings" → QUERY="standup"

```bash
# Extract keyword from user's actual request
QUERY="<USER_SEARCH_TERM>"

curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?q=${QUERY}&singleEvents=true&orderBy=startTime"
```

### Create New Event

When user says: "Schedule a meeting with Marvin tomorrow at 6 PM" or "Create event for project review next Tuesday at 2pm"

**CRITICAL: Extract ALL parameters dynamically from user's request:**

1. **Meeting title/summary**: Parse from context
   - "meeting with Marvin" → summary = "Meeting with Marvin"
   - "project review" → summary = "Project review"
   - "standup call" → summary = "Standup call"
   - Default format: Capitalize first letter of each word

2. **Date**: Extract from user's request
   - "tomorrow" → calculate tomorrow's date
   - "next Tuesday" → calculate next Tuesday's date
   - "February 15" → parse as 2026-02-15
   - "in 3 days" → add 3 days to current date

3. **Time**: Extract from user's request
   - "at 6pm" → 18:00
   - "at 2 PM" → 14:00
   - "at 14:00" → 14:00
   - No time specified → default 14:00 (2 PM)

4. **Duration**: Extract or default to 1 hour
   - "30 minute meeting" → 30 minutes
   - "2 hour call" → 120 minutes
   - Not specified → 60 minutes (1 hour)

5. **Attendees**: Extract names/emails from request
   - "with Marvin" → ask user for Marvin's email OR use name only
   - "with john@example.com" → use email directly
   - Multiple attendees: "with Marvin and Sarah" → parse both names

6. **Description**: Optional, infer from context or leave empty

```bash
# PARSE all values from user's actual request - DO NOT use these placeholder values!
MEETING_TITLE="<EXTRACTED_FROM_USER_REQUEST>"
DATE_PART="<EXTRACTED_DATE>"  # e.g., "tomorrow", "next Tuesday", "2026-02-15"
TIME_PART="<EXTRACTED_TIME>"  # e.g., "18:00", "14:00"
DURATION_MINUTES=<EXTRACTED_OR_DEFAULT_60>
ATTENDEE_EMAIL="<EXTRACTED_OR_ASK_USER>"

# Calculate start time dynamically
EVENT_START=$(date -u -d "${DATE_PART} ${TIME_PART}" +%Y-%m-%dT%H:%M:%SZ)

# Calculate end time (start + duration)
EVENT_END=$(date -u -d "${DATE_PART} ${TIME_PART} + ${DURATION_MINUTES} minutes" +%Y-%m-%dT%H:%M:%SZ)

# Build JSON payload dynamically
JSON_PAYLOAD=$(cat <<EOF
{
  "summary": "${MEETING_TITLE}",
  "description": "<OPTIONAL_FROM_CONTEXT>",
  "start": {
    "dateTime": "${EVENT_START}",
    "timeZone": "UTC"
  },
  "end": {
    "dateTime": "${EVENT_END}",
    "timeZone": "UTC"
  }
}
EOF
)

# Add attendees ONLY if email is provided or extracted
# If user says "meeting with Marvin" without email, you can either:
# 1. Ask user: "What's Marvin's email address?"
# 2. Create event without attendees and let user add later
# DO NOT use fake/example emails like "john@example.com"

if [ -n "$ATTENDEE_EMAIL" ]; then
  JSON_PAYLOAD=$(echo "$JSON_PAYLOAD" | jq --arg email "$ATTENDEE_EMAIL" '. + {attendees: [{email: $email}]}')
fi

RESPONSE=$(curl -s -X POST \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$JSON_PAYLOAD" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events")

# CRITICAL: Extract the event ID from the response for future updates/deletes
EVENT_ID=$(echo "$RESPONSE" | jq -r '.id')
EVENT_LINK=$(echo "$RESPONSE" | jq -r '.htmlLink')

# IMPORTANT: Always confirm success AND include the event ID in your response
# This allows you to update or delete the event later when the user asks
echo "✅ Calendar event '${MEETING_TITLE}' created successfully for ${EVENT_START}"
echo "Event ID: ${EVENT_ID}"
```

### Update Event

When user says: "Change my 2 PM meeting to 3 PM" or "Update the Marvin meeting to tomorrow" or "Change the time to 9PM"

**CRITICAL: Updating is complex and error-prone. Use the full flow below to ensure success.**

**SMART EVENT ID EXTRACTION:**
- **If user just created an event** and says "change the time" → Look in YOUR OWN recent responses for "Event ID: xyz" and use that directly (skip search)
- **If user mentions event by name/time** → Search for it using the Calendar API
- **ALWAYS check your recent conversation history FIRST** before searching

**Steps:**
1. **Get the EVENT_ID** (from recent conversation history OR search)
2. **Parse what to update** from user's request
3. **Fetch the current event** to preserve all fields
4. **Build the update payload** with ONLY the fields that changed
5. **Update the event** and confirm success

```bash
# SMART Step 1: Try to find EVENT_ID in recent conversation first
# If you recently created an event and said "Event ID: abc123xyz", use that!
# Check your last 3-5 messages for "Event ID: <id>" pattern

# If EVENT_ID not found in history, search for the event:
# Extract search criteria from user's request
SEARCH_QUERY="<KEYWORD_FROM_REQUEST>"  # e.g., "Marvin" or "Testing Peppi"

# Search for the event
SEARCH_RESPONSE=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?q=${SEARCH_QUERY}&singleEvents=true&orderBy=startTime")

# Check if any events found
EVENT_COUNT=$(echo "$SEARCH_RESPONSE" | jq '.items | length')
if [ "$EVENT_COUNT" -eq 0 ]; then
  echo "❌ No events found matching '${SEARCH_QUERY}'"
  exit 1
fi

# Step 2: Show user what was found and extract EVENT_ID from the first match
echo "Found ${EVENT_COUNT} matching event(s):"
echo "$SEARCH_RESPONSE" | jq -r '.items[0] | "- \(.summary) at \(.start.dateTime // .start.date)"'

EVENT_ID=$(echo "$SEARCH_RESPONSE" | jq -r '.items[0].id')

# Step 3: Fetch the full current event to preserve all fields
CURRENT_EVENT=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events/${EVENT_ID}")

# Step 4: Parse what the user wants to change
# Extract NEW_DATE and NEW_TIME from user's request
NEW_DATE="<PARSE_FROM_REQUEST>"  # e.g., "tomorrow", "2026-02-24"
NEW_TIME="<PARSE_FROM_REQUEST>"  # e.g., "14:00", "2pm"

# Step 5: Calculate new datetime in UTC
# CRITICAL: User speaks in their local timezone ($USER_TIMEZONE), convert to UTC
NEW_START=$(TZ="$USER_TIMEZONE" date -u -d "${NEW_DATE} ${NEW_TIME}" +%Y-%m-%dT%H:%M:%SZ)

# Calculate duration from current event to preserve it
CURRENT_START=$(echo "$CURRENT_EVENT" | jq -r '.start.dateTime')
CURRENT_END=$(echo "$CURRENT_EVENT" | jq -r '.end.dateTime')
START_EPOCH=$(date -d "$CURRENT_START" +%s)
END_EPOCH=$(date -d "$CURRENT_END" +%s)
DURATION_MINUTES=$(( (END_EPOCH - START_EPOCH) / 60 ))

# Calculate new end time based on original duration
NEW_END=$(date -u -d "$NEW_START + $DURATION_MINUTES minutes" +%Y-%m-%dT%H:%M:%SZ)

# Step 6: Build update payload using jq for safety
UPDATE_PAYLOAD=$(echo "$CURRENT_EVENT" | jq \
  --arg newStart "$NEW_START" \
  --arg newEnd "$NEW_END" \
  '{
    summary: .summary,
    description: .description,
    location: .location,
    attendees: .attendees,
    start: {
      dateTime: $newStart,
      timeZone: "UTC"
    },
    end: {
      dateTime: $newEnd,
      timeZone: "UTC"
    },
    reminders: .reminders
  }')

# Step 7: Update the event
UPDATE_RESPONSE=$(curl -s -X PUT \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$UPDATE_PAYLOAD" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events/${EVENT_ID}")

# Step 8: Check for errors
if echo "$UPDATE_RESPONSE" | jq -e '.error' > /dev/null 2>&1; then
  ERROR_MSG=$(echo "$UPDATE_RESPONSE" | jq -r '.error.message')
  echo "❌ Failed to update event: $ERROR_MSG"
  exit 1
fi

# IMPORTANT: Always confirm success with details
UPDATED_SUMMARY=$(echo "$UPDATE_RESPONSE" | jq -r '.summary')
UPDATED_TIME=$(echo "$UPDATE_RESPONSE" | jq -r '.start.dateTime')
echo "✅ Calendar event '${UPDATED_SUMMARY}' updated successfully to ${UPDATED_TIME}"
```

**Alternative: Simple Time-Only Update**

If you ONLY need to change the time (not date), use this simpler approach:

```bash
# Find today's or tomorrow's events by title
TITLE_SEARCH="<EVENT_TITLE>"
TIME_MIN=$(date -u +%Y-%m-%dT00:00:00Z)
TIME_MAX=$(date -u -d '+2 days' +%Y-%m-%dT23:59:59Z)

EVENTS=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=${TIME_MIN}&timeMax=${TIME_MAX}&q=${TITLE_SEARCH}&singleEvents=true")

EVENT_ID=$(echo "$EVENTS" | jq -r '.items[0].id')
CURRENT_EVENT=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events/${EVENT_ID}")

# Parse new time from user request
NEW_TIME_LOCAL="<USER_TIME>"  # e.g., "15:00" for 3 PM
CURRENT_DATE=$(echo "$CURRENT_EVENT" | jq -r '.start.dateTime' | cut -d'T' -f1)

# Combine current date with new time in user's timezone, then convert to UTC
NEW_START=$(TZ="$USER_TIMEZONE" date -u -d "${CURRENT_DATE} ${NEW_TIME_LOCAL}" +%Y-%m-%dT%H:%M:%SZ)
NEW_END=$(TZ="$USER_TIMEZONE" date -u -d "${CURRENT_DATE} ${NEW_TIME_LOCAL} + 60 minutes" +%Y-%m-%dT%H:%M:%SZ)

# Update with jq
UPDATE_PAYLOAD=$(echo "$CURRENT_EVENT" | jq \
  --arg start "$NEW_START" \
  --arg end "$NEW_END" \
  '.start.dateTime = $start | .end.dateTime = $end')

curl -s -X PUT \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$UPDATE_PAYLOAD" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events/${EVENT_ID}"

echo "✅ Updated to ${NEW_TIME_LOCAL}"
```

### Delete Event

When user says: "Cancel my meeting with Marvin" or "Delete the 2 PM appointment"

**CRITICAL: Always show what you're about to delete before deleting it.**

**Steps:**
1. **Search for the event** using details from user's request
2. **Show the user what you found** (title, time, attendees)
3. **Extract EVENT_ID** from search results
4. **Delete the event** and handle errors
5. **Confirm deletion**

```bash
# Step 1: Search for event based on user's description
# Extract search criteria from user's request
SEARCH_QUERY="<KEYWORD_FROM_REQUEST>"  # e.g., "Marvin" or "Testing Peppi"

# Option A: Search by keyword (works for title, attendee names, etc.)
SEARCH_RESPONSE=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?q=${SEARCH_QUERY}&singleEvents=true&orderBy=startTime&timeMin=$(date -u +%Y-%m-%dT%H:%M:%SZ)")

# Option B: Search by specific date/time if user mentions a time
# If user says "delete the 2 PM meeting", search for events at that time
# TIME_SEARCH_START=$(TZ="$USER_TIMEZONE" date -u -d "today 14:00" +%Y-%m-%dT%H:%M:%SZ)
# TIME_SEARCH_END=$(TZ="$USER_TIMEZONE" date -u -d "today 15:00" +%Y-%m-%dT%H:%M:%SZ)
# SEARCH_RESPONSE=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
#   "https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=${TIME_SEARCH_START}&timeMax=${TIME_SEARCH_END}&singleEvents=true")

# Step 2: Check if any events found
EVENT_COUNT=$(echo "$SEARCH_RESPONSE" | jq '.items | length')
if [ "$EVENT_COUNT" -eq 0 ]; then
  echo "❌ No events found matching '${SEARCH_QUERY}'"
  exit 1
fi

# Step 3: Show what was found
echo "Found ${EVENT_COUNT} matching event(s):"
FOUND_EVENT=$(echo "$SEARCH_RESPONSE" | jq -r '.items[0]')
EVENT_TITLE=$(echo "$FOUND_EVENT" | jq -r '.summary')
EVENT_TIME=$(echo "$FOUND_EVENT" | jq -r '.start.dateTime // .start.date')
EVENT_ATTENDEES=$(echo "$FOUND_EVENT" | jq -r '.attendees[]?.email // empty' | paste -sd ',' -)

echo "📅 Event: $EVENT_TITLE"
echo "🕐 Time: $EVENT_TIME"
[ -n "$EVENT_ATTENDEES" ] && echo "👥 Attendees: $EVENT_ATTENDEES"

# Step 4: Extract EVENT_ID
EVENT_ID=$(echo "$FOUND_EVENT" | jq -r '.id')

if [ -z "$EVENT_ID" ] || [ "$EVENT_ID" = "null" ]; then
  echo "❌ Failed to extract event ID"
  exit 1
fi

# Step 5: Delete the event
DELETE_RESPONSE=$(curl -s -w "\n%{http_code}" -X DELETE \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events/${EVENT_ID}")

# Extract HTTP status code (last line)
HTTP_CODE=$(echo "$DELETE_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$DELETE_RESPONSE" | sed '$d')

# Step 6: Check for errors
if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
  echo "✅ Calendar event '${EVENT_TITLE}' deleted successfully"
else
  echo "❌ Failed to delete event (HTTP $HTTP_CODE)"
  if [ -n "$RESPONSE_BODY" ]; then
    ERROR_MSG=$(echo "$RESPONSE_BODY" | jq -r '.error.message // empty')
    [ -n "$ERROR_MSG" ] && echo "Error: $ERROR_MSG"
  fi
  exit 1
fi
```

**Safer Alternative: Delete by Date + Title**

If you know the approximate date and title, use this more targeted approach:

```bash
# Search for events on a specific date with a specific title
TARGET_DATE="<DATE_FROM_REQUEST>"  # e.g., "tomorrow", "2026-02-24"
EVENT_TITLE_SEARCH="<TITLE_FROM_REQUEST>"  # e.g., "Testing Peppi"

# Calculate date range (whole day in user's timezone)
DAY_START=$(TZ="$USER_TIMEZONE" date -u -d "$TARGET_DATE 00:00" +%Y-%m-%dT%H:%M:%SZ)
DAY_END=$(TZ="$USER_TIMEZONE" date -u -d "$TARGET_DATE 23:59" +%Y-%m-%dT%H:%M:%SZ)

# Search for events
EVENTS=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=${DAY_START}&timeMax=${DAY_END}&q=${EVENT_TITLE_SEARCH}&singleEvents=true")

# Extract first matching event
EVENT_ID=$(echo "$EVENTS" | jq -r '.items[0].id')
EVENT_TITLE=$(echo "$EVENTS" | jq -r '.items[0].summary')

if [ -z "$EVENT_ID" ] || [ "$EVENT_ID" = "null" ]; then
  echo "❌ No event found with title '${EVENT_TITLE_SEARCH}' on ${TARGET_DATE}"
  exit 1
fi

echo "Deleting: $EVENT_TITLE"

# Delete
curl -s -X DELETE \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events/${EVENT_ID}"

echo "✅ Event deleted successfully"
```

## 📧 GMAIL API

Base URL: `https://gmail.googleapis.com/gmail/v1`

### IMPORTANT: Timezone Context for Date-Based Gmail Queries

When user asks for emails with date/time filters (e.g., "emails from today", "messages from this week"), use the user's timezone context to calculate the correct date ranges.

**The user's timezone is available via the `$USER_TIMEZONE` environment variable** (e.g., "Asia/Kolkata", "America/New_York").

Date calculation with timezone:
- "Today's emails": Get start of today in user's timezone, convert to UTC for API query
- "This week": Get start of week (Monday 00:00) in user's timezone
- "Last 3 days": Calculate date range based on user's timezone

```bash
# Example: Get today's date range in user's timezone
# If USER_TIMEZONE="Asia/Kolkata" and it's Feb 9, 2026
# Today starts at 2026-02-09 00:00:00 IST = 2026-02-08 18:30:00 UTC

TODAY_START=$(TZ="$USER_TIMEZONE" date -d "today 00:00:00" +%s)
TODAY_END=$(TZ="$USER_TIMEZONE" date -d "today 23:59:59" +%s)

# Gmail API uses "after:" and "before:" with timestamps
QUERY="after:${TODAY_START} before:${TODAY_END}"
```

### List Recent/Unread/Important Messages

When user asks: "Show me my recent emails" or "Any unread messages?" or "Important emails?" or "Emails from today"

**PARSE user's filter criteria:**
- "recent" → no filter, maxResults=10
- "unread" → q=is:unread
- "important" → q=is:important
- "starred" → q=is:starred
- "today" / "from today" → calculate date range using USER_TIMEZONE
- "this week" → calculate week range using USER_TIMEZONE
- "last 3 days" → calculate date range using USER_TIMEZONE
- Custom count: "last 20 emails" → maxResults=20

```bash
# Extract filter from user's request
BASE_QUERY="<FILTER_IF_ANY>"  # e.g., "is:unread" or empty
MAX_RESULTS=<COUNT_OR_DEFAULT_10>

# If user specifies date range, add timezone-aware filtering
DATE_FILTER=""
if [[ "$USER_REQUEST" == *"today"* ]] || [[ "$USER_REQUEST" == *"from today"* ]]; then
  # Calculate today in user's timezone
  TODAY_START=$(TZ="$USER_TIMEZONE" date -d "today 00:00:00" +%s)
  DATE_FILTER="after:${TODAY_START}"
fi

if [[ "$USER_REQUEST" == *"this week"* ]]; then
  # Calculate start of this week (Monday) in user's timezone
  WEEK_START=$(TZ="$USER_TIMEZONE" date -d "monday this week 00:00:00" +%s)
  DATE_FILTER="after:${WEEK_START}"
fi

if [[ "$USER_REQUEST" == *"last 3 days"* ]]; then
  # Calculate 3 days ago in user's timezone
  THREE_DAYS_AGO=$(TZ="$USER_TIMEZONE" date -d "3 days ago 00:00:00" +%s)
  DATE_FILTER="after:${THREE_DAYS_AGO}"
fi

# Combine base query with date filter
FINAL_QUERY="${BASE_QUERY} ${DATE_FILTER}"

curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages?q=${FINAL_QUERY}&maxResults=${MAX_RESULTS}"
```

### Search Messages

When user asks: "Show me emails from Marvin" or "Find messages about project X" or "Emails from John today"

**EXTRACT search criteria from user's request:**
- "from Marvin" → q=from:marvin (or ask for email)
- "from sarah@example.com" → q=from:sarah@example.com
- "about project X" → q=subject:project X
- "with attachment" → q=has:attachment
- "from John today" → q=from:john after:<TODAY_TIMESTAMP>
- "unread from John this week" → q=is:unread from:john after:<WEEK_START_TIMESTAMP>
- Combinations with dates: Always use USER_TIMEZONE for date calculations

```bash
# Build search query from user's actual request
BASE_SEARCH_QUERY="<DYNAMIC_QUERY_FROM_REQUEST>"

# If user includes date/time context, add timezone-aware filtering
DATE_FILTER=""
if [[ "$USER_REQUEST" == *"today"* ]]; then
  TODAY_START=$(TZ="$USER_TIMEZONE" date -d "today 00:00:00" +%s)
  DATE_FILTER="after:${TODAY_START}"
fi

if [[ "$USER_REQUEST" == *"this week"* ]]; then
  WEEK_START=$(TZ="$USER_TIMEZONE" date -d "monday this week 00:00:00" +%s)
  DATE_FILTER="after:${WEEK_START}"
fi

if [[ "$USER_REQUEST" == *"yesterday"* ]]; then
  YESTERDAY_START=$(TZ="$USER_TIMEZONE" date -d "yesterday 00:00:00" +%s)
  YESTERDAY_END=$(TZ="$USER_TIMEZONE" date -d "yesterday 23:59:59" +%s)
  DATE_FILTER="after:${YESTERDAY_START} before:${YESTERDAY_END}"
fi

FINAL_SEARCH_QUERY="${BASE_SEARCH_QUERY} ${DATE_FILTER}"

curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages?q=${FINAL_SEARCH_QUERY}&maxResults=10"
```

### Get Message Details

After listing messages, get full content of a specific message:

```bash
# Extract MESSAGE_ID from previous list results
MESSAGE_ID="<FROM_LIST_RESULTS>"

# Use format=full for complete content, format=metadata for headers only
FORMAT="<full_or_metadata>"

curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages/${MESSAGE_ID}?format=${FORMAT}"
```

### Send Email

When user says: "Send an email to marvin@example.com saying hi" or "Email Sarah about the meeting"

**CRITICAL: Extract ALL email components from user's request:**

1. **Recipient (To)**: Extract email address
   - "to marvin@example.com" → TO="marvin@example.com"
   - "email Marvin" → ask user for Marvin's email address
   - Multiple recipients: "to john@a.com and sarah@b.com" → parse both

2. **Subject**: Extract or ask user
   - "about the meeting" → SUBJECT="About the meeting"
   - "saying hi" → SUBJECT="Hi" (infer simple subject)
   - Not specified → ask user: "What should the subject be?"

3. **Body**: Extract message content
   - User provides body directly → use exactly as given
   - "saying hi" → BODY="Hi,\n\n[user may provide more]"
   - Complex body → ask user for full message

```bash
# PARSE from user's actual request - DO NOT use placeholder values!
TO_EMAIL="<EXTRACTED_EMAIL_ADDRESS>"
SUBJECT="<EXTRACTED_OR_ASK_USER>"
BODY="<EXTRACTED_MESSAGE_BODY>"

# Build RFC 2822 email
EMAIL_CONTENT="From: me
To: ${TO_EMAIL}
Subject: ${SUBJECT}

${BODY}"

# Base64url encode (required by Gmail API)
ENCODED=$(echo -n "$EMAIL_CONTENT" | base64 | tr '+/' '-_' | tr -d '=')

# Send email
curl -s -X POST \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"raw\": \"$ENCODED\"}" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

# IMPORTANT: Always confirm success
echo "✅ Email sent successfully to ${TO_EMAIL}"
```

### Reply to Email

When user says: "Reply to the email from John" or "Reply to the latest email saying thanks"

**CRITICAL: Extract reply details and provide confirmation:**

1. **Identify the original email**:
   - "reply to email from John" → search for latest email from John
   - "reply to latest email" → get most recent email
   - "reply to that email" → use email from context

2. **Extract reply message**:
   - "saying thanks" → REPLY_BODY="Thanks"
   - "tell them I'll check it out" → REPLY_BODY="I'll check it out"
   - User provides full message → use exactly as given

3. **Get original message details** for threading:
   - MESSAGE_ID
   - THREAD_ID (for proper email threading)
   - Original subject (for Re: prefix)
   - Sender email (for To: field)

```bash
# Step 1: Find the original email (search by sender or get latest)
SEARCH_QUERY="<FROM_USER_REQUEST>"  # e.g., "from:john" or empty for latest

# Get the message
RESPONSE=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages?q=${SEARCH_QUERY}&maxResults=1")

MESSAGE_ID=$(echo "$RESPONSE" | jq -r '.messages[0].id')

# Step 2: Get full message details for threading
MESSAGE_DETAILS=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages/${MESSAGE_ID}?format=metadata")

THREAD_ID=$(echo "$MESSAGE_DETAILS" | jq -r '.threadId')
ORIGINAL_FROM=$(echo "$MESSAGE_DETAILS" | jq -r '.payload.headers[] | select(.name=="From") | .value')
ORIGINAL_SUBJECT=$(echo "$MESSAGE_DETAILS" | jq -r '.payload.headers[] | select(.name=="Subject") | .value')

# Extract email from "Name <email@domain.com>" format
TO_EMAIL=$(echo "$ORIGINAL_FROM" | grep -oP '<\K[^>]+' || echo "$ORIGINAL_FROM")

# Add "Re:" prefix if not already present
if [[ "$ORIGINAL_SUBJECT" != Re:* ]]; then
  REPLY_SUBJECT="Re: ${ORIGINAL_SUBJECT}"
else
  REPLY_SUBJECT="${ORIGINAL_SUBJECT}"
fi

# Step 3: Extract reply body from user's request
REPLY_BODY="<EXTRACTED_FROM_USER_REQUEST>"

# Step 4: Build reply email with proper threading
REPLY_CONTENT="From: me
To: ${TO_EMAIL}
Subject: ${REPLY_SUBJECT}
In-Reply-To: ${MESSAGE_ID}
References: ${MESSAGE_ID}

${REPLY_BODY}"

# Base64url encode
ENCODED=$(echo -n "$REPLY_CONTENT" | base64 | tr '+/' '-_' | tr -d '=')

# Step 5: Send reply with threadId for proper threading
curl -s -X POST \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"raw\": \"$ENCODED\", \"threadId\": \"$THREAD_ID\"}" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

# CRITICAL: Always provide confirmation to user
echo "✅ Reply sent successfully to ${TO_EMAIL} in thread '${ORIGINAL_SUBJECT}'"
```

### Mark Message as Read/Unread/Starred

When user says: "Mark this email as read" or "Star the message from John"

**Steps:**
1. **Identify the message** (may need to search first)
2. **Extract MESSAGE_ID**
3. **Determine action**:
   - "mark as read" → removeLabelIds: ["UNREAD"]
   - "mark as unread" → addLabelIds: ["UNREAD"]
   - "star" → addLabelIds: ["STARRED"]
   - "unstar" → removeLabelIds: ["STARRED"]

```bash
MESSAGE_ID="<FROM_SEARCH_OR_CONTEXT>"
ACTION="<add_or_remove>"
LABEL="<UNREAD_or_STARRED>"

curl -s -X POST \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"${ACTION}LabelIds\": [\"${LABEL}\"]}" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages/${MESSAGE_ID}/modify"
```

### Delete Message

When user says: "Delete this email" or "Remove the spam message"

```bash
MESSAGE_ID="<FROM_SEARCH_OR_CONTEXT>"

curl -s -X DELETE \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages/${MESSAGE_ID}"
```

## 🎯 Response Formatting

After executing API calls:

1. **Parse JSON responses** using `jq`:
   ```bash
   # Extract event summaries
   curl ... | jq -r '.items[] | "\(.summary) - \(.start.dateTime)"'

   # Extract email subjects and senders
   curl ... | jq -r '.messages[].id'  # then get details for each
   ```

2. **Format for user readability**:
   - Calendar events: "📅 Meeting with Marvin - Tomorrow at 6:00 PM"
   - Emails: "📧 From: marvin@example.com | Subject: Project Update"

3. **Handle errors gracefully**:
   - 401 Unauthorized → "OAuth token issue (auto-refresh failed)"
   - 403 Forbidden → "Missing permissions for this operation"
   - 404 Not Found → "Event/message not found"
   - 429 Rate Limited → "Too many requests, please wait"

4. **Confirm actions**:
   - After creating event: "✅ Created: Meeting with Marvin on Feb 7 at 6:00 PM"
   - After sending email: "✅ Email sent to marvin@example.com"

## 🚨 CRITICAL RULES

1. **NEVER use hardcoded values** - ALWAYS extract from user's actual request
2. **NEVER use example emails** like "john@example.com" in production
3. **ASK user for missing information** rather than making assumptions
4. **PARSE natural language** to extract dates, times, names, emails
5. **CALCULATE dates dynamically** using `date` command
6. **CONFIRM actions** before deleting or modifying events
7. **FORMAT responses** in user-friendly way with emojis/structure

## 📚 Reference

- [Google Calendar API v3](https://developers.google.com/workspace/calendar/api/v3/reference)
- [Gmail API v1](https://developers.google.com/gmail/api/reference/rest)
- [Calendar Events](https://developers.google.com/workspace/calendar/api/v3/reference/events)
- [Gmail Messages](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages)
