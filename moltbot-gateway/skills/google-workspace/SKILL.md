---
name: google-workspace
description: Google Calendar and Gmail - list events, view calendar, check schedule, show meetings, get appointments, create/update/delete events, read/send emails, check inbox, search emails, recent messages, unread emails, send message, compose email, find messages, email search, reply to email, respond to message, answer email
user-invocable: true
metadata: {"openclaw": {"emoji": "📧"}}
---

<tool_execution_directive>
CRITICAL: When this skill is triggered, you MUST execute the bash commands directly using the bash tool.
DO NOT describe what you would do. DO NOT explain the steps you plan to take.
DO NOT ask for confirmation unless disambiguation is genuinely required (e.g., multiple matching events).
EXECUTE the curl/bash command immediately, parse the API response, and report the result to the user.
You are an agent — act, don't narrate.
</tool_execution_directive>

<skill_description>
# Google Workspace - Calendar & Gmail

🎯 **Comprehensive Google Calendar and Gmail integration using OAuth tokens and direct API calls.**
</skill_description>

<trigger_patterns>
## ⚡ When to Use This Skill

Use this skill when the user asks about:
- **Calendar**: list meetings, view schedule, check calendar, what meetings, create/update/delete events, appointments
- **Gmail**: read emails, check inbox, send email, search messages, mark read/unread
</trigger_patterns>

<environment_variables>
## 🔑 Environment Variables

The OAuth access token is automatically available:
- `$GOOGLE_ACCESS_TOKEN` - OAuth 2.0 bearer token (auto-refreshed by FastAPI backend)
</environment_variables>

<operation name="calendar">
## 📅 GOOGLE CALENDAR API

Base URL: `https://www.googleapis.com/calendar/v3`

### CRITICAL: Date/Time Parsing Instructions

**ALWAYS extract date and time from the user's actual request. NEVER use hardcoded values.**

Parse user input to extract:
- **Date**: "tomorrow", "today", "next Tuesday", "February 15", "in 3 days"
- **Time**: "at 6pm", "at 14:00", "2 PM", "noon", "morning" (default 9am), "afternoon" (default 2pm)
- **Duration**: Default 1 hour if not specified. "30 minute meeting" = 30min, "2 hour call" = 2hr

### 🚨 TIMEZONE HANDLING - CRITICAL RULES

**Rule 1: NEVER convert to UTC. Pass LOCAL time + timeZone to Google Calendar.**
- Google Calendar API accepts local times with a `timeZone` field — it does the UTC conversion for you
- When user says "at 10:00", just use `10:00:00` with `timeZone: $USER_TIMEZONE`
- DO NOT use `date -u` (UTC flag) for event creation. DO NOT append `Z` to times.

**Rule 2: Use `TZ="$USER_TIMEZONE"` ONLY for resolving relative dates ("today", "tomorrow")**
- "today" / "tomorrow" must be relative to the user's timezone, not the server's
- Use `TZ="$USER_TIMEZONE" date -d "tomorrow" +%Y-%m-%d` to get the correct DATE only
- Then combine that date with the user's stated time as-is (no UTC conversion)

**Rule 3: When updating/deleting events, search in the user's timezone context**
- If user says "my meeting tomorrow", search for events on tomorrow in THEIR timezone
- Don't search by UTC date - you'll get the wrong day

### How to calculate event times (NO UTC conversion!)

```bash
# Step 1: Resolve the DATE in user's timezone
EVENT_DATE=$(TZ="$USER_TIMEZONE" date -d "tomorrow" +%Y-%m-%d)

# Step 2: Combine with user's stated time (NO conversion, NO -u flag, NO Z suffix)
EVENT_START="${EVENT_DATE}T14:00:00"   # User said "2pm" → 14:00:00
EVENT_END="${EVENT_DATE}T15:00:00"     # 1 hour later

# Step 3: Pass to Google Calendar with timeZone field — Google handles UTC conversion
# {
#   "start": {"dateTime": "2026-03-27T14:00:00", "timeZone": "America/New_York"},
#   "end": {"dateTime": "2026-03-27T15:00:00", "timeZone": "America/New_York"}
# }
```

Common date patterns:
- Today: `$(TZ="$USER_TIMEZONE" date -d "today" +%Y-%m-%d)`
- Tomorrow: `$(TZ="$USER_TIMEZONE" date -d "tomorrow" +%Y-%m-%d)`
- Next Tuesday: `$(TZ="$USER_TIMEZONE" date -d "next Tuesday" +%Y-%m-%d)`
- In 3 days: `$(TZ="$USER_TIMEZONE" date -d "+3 days" +%Y-%m-%d)`

**MANDATORY: You MUST normalize ALL user time inputs to `HH:MM` 24-hour format BEFORE using them in bash variables.** Never pass raw user input directly. The `TIME_PART` variable must ALWAYS match the pattern `[0-9]{2}:[0-9]{2}`.

Time normalization table (input → output for `TIME_PART`):
- "6pm" / "6 PM" / "6:00pm" / "6:00 p.m." → `18:00`
- "2 PM" / "2pm" / "2:00 PM" → `14:00`
- "10:00" / "at 10" / "10 AM" → `10:00`
- "0700" / "0700hrs" / "0700 hours" → `07:00` (split 4-digit military: first 2 = hours, last 2 = minutes)
- "730" → `07:30` (split 3-digit: first 1 = hour, last 2 = minutes)
- "1430" → `14:30` (split 4-digit)
- "7.30" / "7:30" → `07:30` (replace dot with colon, pad hour)
- "7" / "at 7" / "7 o'clock" → `07:00` (AM) or `19:00` (PM) — see disambiguation below
- "noon" / "midday" → `12:00`
- "midnight" → `00:00`
- "quarter past 2" → `14:15`, "half past 3" → `15:30`, "quarter to 5" → `16:45`
- No time specified → default to `09:00` for morning, `14:00` for afternoon

**Ambiguous hour disambiguation (when user says just a number like "7" or "at 8"):**
- Hours 1-6 without AM/PM → assume **PM** (13:00-18:00). Nobody schedules meetings at 3 AM.
- Hours 7-11 without AM/PM → assume **AM** (07:00-11:00). Morning meetings are common.
- Hour 12 without AM/PM → `12:00` (noon)
- If context says "evening"/"tonight"/"dinner" → always PM
- If context says "morning"/"breakfast"/"wake up" → always AM

### 🎯 Example: Handling "tomorrow at 2pm" correctly

```bash
# User is in America/New_York, they say "create a meeting tomorrow at 2pm"

# CORRECT approach — pass local time, let Google convert:
EVENT_DATE=$(TZ="$USER_TIMEZONE" date -d "tomorrow" +%Y-%m-%d)
EVENT_START="${EVENT_DATE}T14:00:00"
# → "2026-03-27T14:00:00" with timeZone: "America/New_York"
# → Google Calendar shows 2:00 PM Eastern ✅

# WRONG approach — converting to UTC yourself (error-prone!):
# date -u -d "tomorrow 14:00" +%Y-%m-%dT%H:%M:%SZ
# → "2026-03-27T14:00:00Z" = 10:00 AM Eastern ❌ WRONG!
```

### Handling API Response Dates (ISO 8601 with Timezone Offsets)

When using dates FROM Google Calendar API responses (e.g., to calculate "30 minutes before a meeting" for reminders, or to compare event times):

**Problem:** API returns times like `2026-02-26T17:30:00+05:30`. The `+HH:MM` offset format can cause "invalid date" errors on some systems.

**Safe approach — convert via epoch seconds:**

```bash
# API returns: EVENT_TIME="2026-02-26T17:30:00+05:30"
EVENT_TIME="<FROM_API_RESPONSE>"

# Convert to epoch (handles timezone offsets reliably)
# Try direct parsing first, fall back to stripping the colon from offset
EVENT_EPOCH=$(date -d "$EVENT_TIME" +%s 2>/dev/null || date -d "$(echo $EVENT_TIME | sed 's/+\([0-9][0-9]\):\([0-9][0-9]\)$/+\1\2/')" +%s)

# Calculate 30 minutes before (1800 seconds)
BEFORE_EPOCH=$((EVENT_EPOCH - 1800))

# Convert back to ISO 8601 UTC
BEFORE_TIME=$(date -u -d "@$BEFORE_EPOCH" +%Y-%m-%dT%H:%M:%SZ)

# Convert to user's local time for display
LOCAL_DISPLAY=$(TZ="$USER_TIMEZONE" date -d "@$EVENT_EPOCH" '+%I:%M %p on %b %d')
```

**Use this pattern whenever you need to do arithmetic on API-returned dates (e.g., setting reminders before meetings, comparing times).**

### List Events (Today/Tomorrow/This Week/Range)

When user asks: "What meetings do I have today?" or "What's on my schedule tomorrow?" or "what meetings do I have this week?"

**YOU MUST execute the curl command and parse the JSON response. DO NOT just describe what to do - ACTUALLY RUN THE COMMAND.**

```bash
# For TODAY's events (resolve "today" in user's timezone, not server UTC)
TODAY_START_EPOCH=$(TZ="$USER_TIMEZONE" date -d "today 00:00:00" +%s)
TODAY_END_EPOCH=$(TZ="$USER_TIMEZONE" date -d "today 23:59:59" +%s)
TODAY_START=$(date -u -d "@${TODAY_START_EPOCH}" +%Y-%m-%dT%H:%M:%SZ)
TODAY_END=$(date -u -d "@${TODAY_END_EPOCH}" +%Y-%m-%dT%H:%M:%SZ)

RESPONSE=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=${TODAY_START}&timeMax=${TODAY_END}&singleEvents=true&orderBy=startTime")

echo "$RESPONSE" | jq -r '.items[] | "\(.summary) at \(.start.dateTime // .start.date)"'

# For THIS WEEK's events (next 7 days from user's today)
WEEK_END_EPOCH=$(TZ="$USER_TIMEZONE" date -d "+7 days 23:59:59" +%s)
WEEK_END=$(date -u -d "@${WEEK_END_EPOCH}" +%Y-%m-%dT%H:%M:%SZ)

RESPONSE=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=${TODAY_START}&timeMax=${WEEK_END}&singleEvents=true&orderBy=startTime")

echo "$RESPONSE" | jq -r '.items[] | "\(.summary) at \(.start.dateTime // .start.date)"'

# For TOMORROW's events
TOMORROW_START_EPOCH=$(TZ="$USER_TIMEZONE" date -d "tomorrow 00:00:00" +%s)
TOMORROW_END_EPOCH=$(TZ="$USER_TIMEZONE" date -d "tomorrow 23:59:59" +%s)
TOMORROW_START=$(date -u -d "@${TOMORROW_START_EPOCH}" +%Y-%m-%dT%H:%M:%SZ)
TOMORROW_END=$(date -u -d "@${TOMORROW_END_EPOCH}" +%Y-%m-%dT%H:%M:%SZ)

RESPONSE=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=${TOMORROW_START}&timeMax=${TOMORROW_END}&singleEvents=true&orderBy=startTime")

echo "$RESPONSE" | jq -r '.items[] | "\(.summary) at \(.start.dateTime // .start.date)"'
```

**The response will be a list of events with their names and times. Present this to the user in a friendly format.**

### List Next N Events

When user asks: "What are my next 5 meetings?" or "Show upcoming appointments"

**PARSE the number N from user's request.** Default to 10 if not specified.

```bash
# Extract N from user request (e.g., "next 5 meetings" → N=5)
N=<USER_REQUESTED_COUNT>

# Use user's current time as starting point
NOW_EPOCH=$(TZ="$USER_TIMEZONE" date +%s)
NOW_UTC=$(date -u -d "@${NOW_EPOCH}" +%Y-%m-%dT%H:%M:%SZ)

curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?maxResults=${N}&singleEvents=true&orderBy=startTime&timeMin=${NOW_UTC}"
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
TIME_PART="<EXTRACTED_TIME>"  # e.g., "18:00", "14:00" (24-hour format)
DURATION_MINUTES=<EXTRACTED_OR_DEFAULT_60>
ATTENDEE_EMAIL="<EXTRACTED_OR_ASK_USER>"

# Step 1: Resolve the date in user's timezone (handles "today", "tomorrow", etc.)
EVENT_DATE=$(TZ="$USER_TIMEZONE" date -d "${DATE_PART}" +%Y-%m-%d)

# Step 2: Build LOCAL datetime strings (NO UTC conversion, NO -u flag, NO Z suffix!)
EVENT_START="${EVENT_DATE}T${TIME_PART}:00"

# Step 3: Calculate end time by adding duration
END_HOUR=$(( ${TIME_PART%%:*} + DURATION_MINUTES / 60 ))
END_MIN=$(( ${TIME_PART##*:} + DURATION_MINUTES % 60 ))
if [ $END_MIN -ge 60 ]; then END_HOUR=$((END_HOUR + 1)); END_MIN=$((END_MIN - 60)); fi
# Handle midnight rollover (e.g., 23:30 + 90min = 01:00 next day)
if [ $END_HOUR -ge 24 ]; then
  END_HOUR=$((END_HOUR - 24))
  EVENT_DATE_END=$(TZ="$USER_TIMEZONE" date -d "${EVENT_DATE} + 1 day" +%Y-%m-%d)
else
  EVENT_DATE_END="${EVENT_DATE}"
fi
EVENT_END="${EVENT_DATE_END}T$(printf '%02d:%02d' $END_HOUR $END_MIN):00"

# Step 4: Build JSON payload — Google Calendar handles timezone conversion!
# ALWAYS include conferenceData to auto-generate Google Meet link
REQUEST_ID=$(cat /proc/sys/kernel/random/uuid 2>/dev/null || echo "meet-$(date +%s)-$RANDOM")

JSON_PAYLOAD=$(jq -n \
  --arg title "$MEETING_TITLE" \
  --arg desc "${DESCRIPTION:-}" \
  --arg start "$EVENT_START" \
  --arg end "$EVENT_END" \
  --arg tz "$USER_TIMEZONE" \
  --arg reqid "$REQUEST_ID" \
  '{
    summary: $title,
    description: $desc,
    start: {dateTime: $start, timeZone: $tz},
    end: {dateTime: $end, timeZone: $tz},
    conferenceData: {
      createRequest: {
        requestId: $reqid,
        conferenceSolutionKey: {type: "hangoutsMeet"}
      }
    }
  }')

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
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?conferenceDataVersion=1")

# Extract event details and Meet link from response
EVENT_ID=$(echo "$RESPONSE" | jq -r '.id')
EVENT_LINK=$(echo "$RESPONSE" | jq -r '.htmlLink')
MEET_LINK=$(echo "$RESPONSE" | jq -r '.conferenceData.entryPoints[]? | select(.entryPointType=="video") | .uri' 2>/dev/null)

# IMPORTANT: Always confirm success with details AND meeting link
if [ -n "$MEET_LINK" ] && [ "$MEET_LINK" != "null" ]; then
  echo "✅ Calendar event '${MEETING_TITLE}' created for ${EVENT_START}"
  echo "📹 Google Meet link: ${MEET_LINK}"
else
  echo "✅ Calendar event '${MEETING_TITLE}' created for ${EVENT_START}"
  echo "📅 Calendar link: ${EVENT_LINK}"
fi
```

### Create Event WITH Google Meet Link

When user says: "Create a meet" or "Create a meeting link" or "Send a meet link to X" or "Schedule meeting with Meet link"

**CRITICAL: When user mentions "meet link", "meet", "Google Meet", "video call", or wants to send a meeting link — you MUST include `conferenceData` to auto-generate a Google Meet link.**

```bash
# PARSE from user's actual request
MEETING_TITLE="<EXTRACTED_FROM_USER_REQUEST>"
DATE_PART="<EXTRACTED_DATE>"
TIME_PART="<EXTRACTED_TIME>"  # 24-hour format, e.g., "14:00"
DURATION_MINUTES=<EXTRACTED_OR_DEFAULT_60>
ATTENDEE_EMAIL="<EXTRACTED_OR_EMPTY>"

# Resolve date in user's timezone, then build LOCAL times (NO UTC, NO -u, NO Z!)
EVENT_DATE=$(TZ="$USER_TIMEZONE" date -d "${DATE_PART}" +%Y-%m-%d)
EVENT_START="${EVENT_DATE}T${TIME_PART}:00"
END_HOUR=$(( ${TIME_PART%%:*} + DURATION_MINUTES / 60 ))
END_MIN=$(( ${TIME_PART##*:} + DURATION_MINUTES % 60 ))
if [ $END_MIN -ge 60 ]; then END_HOUR=$((END_HOUR + 1)); END_MIN=$((END_MIN - 60)); fi
# Handle midnight rollover (e.g., 23:30 + 90min = 01:00 next day)
if [ $END_HOUR -ge 24 ]; then
  END_HOUR=$((END_HOUR - 24))
  EVENT_DATE_END=$(TZ="$USER_TIMEZONE" date -d "${EVENT_DATE} + 1 day" +%Y-%m-%d)
else
  EVENT_DATE_END="${EVENT_DATE}"
fi
EVENT_END="${EVENT_DATE_END}T$(printf '%02d:%02d' $END_HOUR $END_MIN):00"

# Generate a unique request ID for Meet link creation
REQUEST_ID=$(cat /proc/sys/kernel/random/uuid 2>/dev/null || echo "meet-$(date +%s)")

# Build JSON payload safely using jq (handles special chars in titles)
JSON_PAYLOAD=$(jq -n \
  --arg title "$MEETING_TITLE" \
  --arg start "$EVENT_START" \
  --arg end "$EVENT_END" \
  --arg tz "$USER_TIMEZONE" \
  --arg reqid "$REQUEST_ID" \
  '{
    summary: $title,
    start: {dateTime: $start, timeZone: $tz},
    end: {dateTime: $end, timeZone: $tz},
    conferenceData: {
      createRequest: {
        requestId: $reqid,
        conferenceSolutionKey: {type: "hangoutsMeet"}
      }
    }
  }')

# Add attendees if provided
if [ -n "$ATTENDEE_EMAIL" ]; then
  JSON_PAYLOAD=$(echo "$JSON_PAYLOAD" | jq --arg email "$ATTENDEE_EMAIL" '. + {attendees: [{email: $email}]}')
fi

# CRITICAL: Must include ?conferenceDataVersion=1 for Meet link generation
RESPONSE=$(curl -s -X POST \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$JSON_PAYLOAD" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?conferenceDataVersion=1")

# Extract the Google Meet link from the response
MEET_LINK=$(echo "$RESPONSE" | jq -r '.conferenceData.entryPoints[]? | select(.entryPointType=="video") | .uri' 2>/dev/null)
EVENT_LINK=$(echo "$RESPONSE" | jq -r '.htmlLink')

if [ -n "$MEET_LINK" ] && [ "$MEET_LINK" != "null" ]; then
  echo "✅ Meeting created with Google Meet link: ${MEET_LINK}"
else
  echo "✅ Meeting created but Meet link was not generated. Calendar link: ${EVENT_LINK}"
fi
```

**If user wants to send the Meet link via email**, chain the actions:
1. Create the event with Meet link (above)
2. Extract `$MEET_LINK` from the response
3. Send email using the Gmail Send Email flow with the Meet link in the body

### Update Event

When user says: "Change my 2 PM meeting to 3 PM" or "Update the Marvin meeting to tomorrow" or "Change the time to 9PM"

**CRITICAL: Updating is complex and error-prone. Use the full flow below to ensure success.**

**STRATEGY: Smart Search + Disambiguation + Confirmation**

This approach works for ALL scenarios (scalable, multi-tenant):
- ✅ Immediate update (just created event → use recent Event ID if available)
- ✅ Later update (created hours ago → search by time/title)
- ✅ Multiple events (disambiguate by showing options)
- ✅ Multi-tenant (search scoped to user's calendar automatically)

**Steps:**
1. **Extract search criteria** from user's request (time, title, date)
2. **Search for matching events** using smart time-based or keyword-based search
3. **Handle results**: single match → confirm and proceed, multiple → ask user to clarify
4. **Once EVENT_ID confirmed**, parse updates, fetch current event, build payload, update
5. **Confirm success** with updated details

```bash
# Step 1: Extract search criteria from user's request
# CRITICAL: Parse what the user mentions to build targeted search
# - "my 4pm meeting" → SEARCH_TIME="16:00"
# - "the code review" → SEARCH_QUERY="code review"
# - "meeting with Marvin" → SEARCH_QUERY="Marvin"
# - "tomorrow's standup" → SEARCH_DATE="tomorrow", SEARCH_QUERY="standup"

SEARCH_TIME="<EXTRACTED_TIME_IF_MENTIONED>"  # e.g., "16:00", "14:00" in 24h format
SEARCH_QUERY="<EXTRACTED_KEYWORDS>"  # e.g., "Marvin", "code review"
SEARCH_DATE="<EXTRACTED_DATE_OR_TODAY>"  # e.g., "today", "tomorrow"

# Step 2: Search for events based on criteria
# OPTION A: If user mentioned specific time, search around that time window
if [ -n "$SEARCH_TIME" ]; then
  # Resolve date in user's timezone and build search window
  SEARCH_DATE_RESOLVED=$(TZ="$USER_TIMEZONE" date -d "$SEARCH_DATE" +%Y-%m-%d)
  SEARCH_HOUR=${SEARCH_TIME%%:*}
  SEARCH_MIN=${SEARCH_TIME##*:}
  MIN_HOUR=$SEARCH_HOUR; MIN_MIN=$((SEARCH_MIN - 15))
  if [ $MIN_MIN -lt 0 ]; then MIN_HOUR=$((MIN_HOUR - 1)); MIN_MIN=$((MIN_MIN + 60)); fi
  MAX_HOUR=$SEARCH_HOUR; MAX_MIN=$((SEARCH_MIN + 15))
  if [ $MAX_MIN -ge 60 ]; then MAX_HOUR=$((MAX_HOUR + 1)); MAX_MIN=$((MAX_MIN - 60)); fi

  # Convert search window to UTC for API (search queries need UTC)
  # Two-step epoch approach: parse in user's TZ → format as UTC
  # (TZ= env var is overridden by -u flag, so we can't combine them)
  EPOCH_MIN=$(TZ="$USER_TIMEZONE" date -d "${SEARCH_DATE_RESOLVED} $(printf '%02d:%02d' $MIN_HOUR $MIN_MIN)" +%s)
  TIME_MIN=$(date -u -d "@${EPOCH_MIN}" +%Y-%m-%dT%H:%M:%SZ)
  EPOCH_MAX=$(TZ="$USER_TIMEZONE" date -d "${SEARCH_DATE_RESOLVED} $(printf '%02d:%02d' $MAX_HOUR $MAX_MIN)" +%s)
  TIME_MAX=$(date -u -d "@${EPOCH_MAX}" +%Y-%m-%dT%H:%M:%SZ)

  SEARCH_RESPONSE=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
    "https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=${TIME_MIN}&timeMax=${TIME_MAX}&singleEvents=true&orderBy=startTime")

# OPTION B: If user mentioned keywords (title, attendee), search by query
elif [ -n "$SEARCH_QUERY" ]; then
  SEARCH_RESPONSE=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
    "https://www.googleapis.com/calendar/v3/calendars/primary/events?q=${SEARCH_QUERY}&singleEvents=true&orderBy=startTime&timeMin=$(date -u -d "@$(TZ="$USER_TIMEZONE" date +%s)" +%Y-%m-%dT%H:%M:%SZ)")

# OPTION C: User said "change my meeting" without specifics - search today's upcoming events
else
  NOW_UTC=$(date -u -d "@$(TZ="$USER_TIMEZONE" date +%s)" +%Y-%m-%dT%H:%M:%SZ)
  TODAY_END_EPOCH=$(TZ="$USER_TIMEZONE" date -d "today 23:59:59" +%s)
  TODAY_END_UTC=$(date -u -d "@${TODAY_END_EPOCH}" +%Y-%m-%dT%H:%M:%SZ)
  SEARCH_RESPONSE=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
    "https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=${NOW_UTC}&timeMax=${TODAY_END_UTC}&singleEvents=true&orderBy=startTime&maxResults=10")
fi

# Step 3: Handle search results - disambiguation logic
EVENT_COUNT=$(echo "$SEARCH_RESPONSE" | jq '.items | length')

if [ "$EVENT_COUNT" -eq 0 ]; then
  echo "❌ No matching events found. Can you be more specific? (e.g., time, title, or attendee name)"
  exit 1

elif [ "$EVENT_COUNT" -eq 1 ]; then
  # Single match - show user and confirm
  FOUND_EVENT=$(echo "$SEARCH_RESPONSE" | jq -r '.items[0]')
  EVENT_TITLE=$(echo "$FOUND_EVENT" | jq -r '.summary')
  EVENT_START=$(echo "$FOUND_EVENT" | jq -r '.start.dateTime // .start.date')

  echo "📅 Found: '${EVENT_TITLE}' at ${EVENT_START}"
  echo "Updating this event..."

  EVENT_ID=$(echo "$FOUND_EVENT" | jq -r '.id')

else
  # Multiple matches - show user options and ask to clarify
  echo "Found ${EVENT_COUNT} events that match:"
  echo "$SEARCH_RESPONSE" | jq -r '.items[0:5] | .[] | "📅 \(.summary) at \(.start.dateTime // .start.date)"'

  if [ "$EVENT_COUNT" -gt 5 ]; then
    echo "... and $((EVENT_COUNT - 5)) more"
  fi

  echo ""
  echo "Which one do you want to update? Please be more specific (e.g., 'the code review at 4pm' or 'the first one')"
  exit 1
fi

# If we reach here, EVENT_ID is set and confirmed

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

# Step 5: Calculate new datetime in USER'S LOCAL timezone (NOT UTC!)
# CRITICAL: Do NOT convert to UTC — pass local time + timeZone to Google Calendar
NEW_DATE_RESOLVED=$(TZ="$USER_TIMEZONE" date -d "${NEW_DATE}" +%Y-%m-%d)
NEW_START="${NEW_DATE_RESOLVED}T${NEW_TIME}:00"

# Calculate duration from current event to preserve it
CURRENT_START=$(echo "$CURRENT_EVENT" | jq -r '.start.dateTime')
CURRENT_END=$(echo "$CURRENT_EVENT" | jq -r '.end.dateTime')
START_EPOCH=$(date -d "$CURRENT_START" +%s)
END_EPOCH=$(date -d "$CURRENT_END" +%s)
DURATION_MINUTES=$(( (END_EPOCH - START_EPOCH) / 60 ))

# Calculate new end time based on original duration (local time, no UTC!)
END_HOUR=$(( ${NEW_TIME%%:*} + DURATION_MINUTES / 60 ))
END_MIN=$(( ${NEW_TIME##*:} + DURATION_MINUTES % 60 ))
if [ $END_MIN -ge 60 ]; then END_HOUR=$((END_HOUR + 1)); END_MIN=$((END_MIN - 60)); fi
# Handle midnight rollover
if [ $END_HOUR -ge 24 ]; then
  END_HOUR=$((END_HOUR - 24))
  NEW_DATE_END=$(TZ="$USER_TIMEZONE" date -d "${NEW_DATE_RESOLVED} + 1 day" +%Y-%m-%d)
else
  NEW_DATE_END="${NEW_DATE_RESOLVED}"
fi
NEW_END="${NEW_DATE_END}T$(printf '%02d:%02d' $END_HOUR $END_MIN):00"

# Step 6: Build update payload using jq for safety
# CRITICAL: Use user's timezone, NOT "UTC" — Google handles conversion
# IMPORTANT: Preserve conferenceData so existing Meet links survive the update
UPDATE_PAYLOAD=$(echo "$CURRENT_EVENT" | jq \
  --arg newStart "$NEW_START" \
  --arg newEnd "$NEW_END" \
  --arg tz "$USER_TIMEZONE" \
  '{
    summary: .summary,
    description: .description,
    location: .location,
    attendees: .attendees,
    conferenceData: .conferenceData,
    start: {
      dateTime: $newStart,
      timeZone: $tz
    },
    end: {
      dateTime: $newEnd,
      timeZone: $tz
    },
    reminders: .reminders
  }')

# Step 7: Update the event (conferenceDataVersion=1 preserves Meet link)
UPDATE_RESPONSE=$(curl -s -X PUT \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$UPDATE_PAYLOAD" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events/${EVENT_ID}?conferenceDataVersion=1")

# Step 8: Check for errors
if echo "$UPDATE_RESPONSE" | jq -e '.error' > /dev/null 2>&1; then
  ERROR_MSG=$(echo "$UPDATE_RESPONSE" | jq -r '.error.message')
  echo "❌ Failed to update event: $ERROR_MSG"
  exit 1
fi

# IMPORTANT: Always confirm with details AND Meet link if available
UPDATED_SUMMARY=$(echo "$UPDATE_RESPONSE" | jq -r '.summary')
UPDATED_TIME=$(echo "$UPDATE_RESPONSE" | jq -r '.start.dateTime')
MEET_LINK=$(echo "$UPDATE_RESPONSE" | jq -r '.conferenceData.entryPoints[]? | select(.entryPointType=="video") | .uri' 2>/dev/null)

echo "✅ Calendar event '${UPDATED_SUMMARY}' updated successfully to ${UPDATED_TIME}"
if [ -n "$MEET_LINK" ] && [ "$MEET_LINK" != "null" ]; then
  echo "📹 Google Meet link: ${MEET_LINK}"
fi
```

**Alternative: Simple Time-Only Update**

If you ONLY need to change the time (not date), use this simpler approach:

```bash
# Find today's or tomorrow's events by title
TITLE_SEARCH="<EVENT_TITLE>"
SEARCH_START_EPOCH=$(TZ="$USER_TIMEZONE" date -d "today 00:00:00" +%s)
TIME_MIN=$(date -u -d "@${SEARCH_START_EPOCH}" +%Y-%m-%dT%H:%M:%SZ)
SEARCH_END_EPOCH=$(TZ="$USER_TIMEZONE" date -d "+2 days 23:59:59" +%s)
TIME_MAX=$(date -u -d "@${SEARCH_END_EPOCH}" +%Y-%m-%dT%H:%M:%SZ)

EVENTS=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=${TIME_MIN}&timeMax=${TIME_MAX}&q=${TITLE_SEARCH}&singleEvents=true")

EVENT_ID=$(echo "$EVENTS" | jq -r '.items[0].id')
CURRENT_EVENT=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events/${EVENT_ID}")

# Parse new time from user request
NEW_TIME_LOCAL="<USER_TIME>"  # e.g., "15:00" for 3 PM (24-hour format)
CURRENT_DATE=$(echo "$CURRENT_EVENT" | jq -r '.start.dateTime' | cut -d'T' -f1)

# Combine current date with new LOCAL time (NO UTC conversion, NO -u, NO Z!)
NEW_START="${CURRENT_DATE}T${NEW_TIME_LOCAL}:00"
END_HOUR=$(( ${NEW_TIME_LOCAL%%:*} + 1 ))
# Handle midnight rollover
if [ $END_HOUR -ge 24 ]; then
  END_HOUR=$((END_HOUR - 24))
  END_DATE=$(TZ="$USER_TIMEZONE" date -d "${CURRENT_DATE} + 1 day" +%Y-%m-%d)
else
  END_DATE="${CURRENT_DATE}"
fi
NEW_END="${END_DATE}T$(printf '%02d:%02d' $END_HOUR ${NEW_TIME_LOCAL##*:}):00"

# Update with jq — pass timeZone so Google handles conversion
UPDATE_PAYLOAD=$(echo "$CURRENT_EVENT" | jq \
  --arg start "$NEW_START" \
  --arg end "$NEW_END" \
  --arg tz "$USER_TIMEZONE" \
  '.start.dateTime = $start | .start.timeZone = $tz | .end.dateTime = $end | .end.timeZone = $tz')

curl -s -X PUT \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$UPDATE_PAYLOAD" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events/${EVENT_ID}?conferenceDataVersion=1"

# Extract updated event details including Meet link
UPDATED_RESPONSE=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events/${EVENT_ID}")
MEET_LINK=$(echo "$UPDATED_RESPONSE" | jq -r '.conferenceData.entryPoints[]? | select(.entryPointType=="video") | .uri' 2>/dev/null)
UPDATED_SUMMARY=$(echo "$UPDATED_RESPONSE" | jq -r '.summary')
UPDATED_TIME=$(echo "$UPDATED_RESPONSE" | jq -r '.start.dateTime')
echo "✅ Calendar event '${UPDATED_SUMMARY}' updated to ${UPDATED_TIME}"
if [ -n "$MEET_LINK" ] && [ "$MEET_LINK" != "null" ]; then
  echo "📹 Google Meet link: ${MEET_LINK}"
fi
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
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?q=${SEARCH_QUERY}&singleEvents=true&orderBy=startTime&timeMin=$(date -u -d "@$(TZ="$USER_TIMEZONE" date +%s)" +%Y-%m-%dT%H:%M:%SZ)")

# Option B: Search by specific date/time if user mentions a time
# If user says "delete the 2 PM meeting", search for events at that time
# EPOCH_START=$(TZ="$USER_TIMEZONE" date -d "today 14:00" +%s)
# TIME_SEARCH_START=$(date -u -d "@${EPOCH_START}" +%Y-%m-%dT%H:%M:%SZ)
# EPOCH_END=$(TZ="$USER_TIMEZONE" date -d "today 15:00" +%s)
# TIME_SEARCH_END=$(date -u -d "@${EPOCH_END}" +%Y-%m-%dT%H:%M:%SZ)
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
# Two-step epoch approach: parse in user's TZ → format as UTC
EPOCH_START=$(TZ="$USER_TIMEZONE" date -d "$TARGET_DATE 00:00" +%s)
DAY_START=$(date -u -d "@${EPOCH_START}" +%Y-%m-%dT%H:%M:%SZ)
EPOCH_END=$(TZ="$USER_TIMEZONE" date -d "$TARGET_DATE 23:59" +%s)
DAY_END=$(date -u -d "@${EPOCH_END}" +%Y-%m-%dT%H:%M:%SZ)

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
</operation>

<operation name="gmail">
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
# Use printf + base64 -w 0 for reliable encoding (no line wraps, handles special chars)
ENCODED=$(printf '%s' "$EMAIL_CONTENT" | base64 -w 0 | tr '+/' '-_' | tr -d '=')

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

# Base64url encode (use printf + base64 -w 0 for reliable encoding)
ENCODED=$(printf '%s' "$REPLY_CONTENT" | base64 -w 0 | tr '+/' '-_' | tr -d '=')

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
</operation>

<response_formatting>
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

</response_formatting>

<rules priority="critical">
## 🚨 CRITICAL RULES

1. **NEVER use hardcoded values** - ALWAYS extract from user's actual request
2. **NEVER use example emails** like "john@example.com" in production
3. **ASK user for missing information** rather than making assumptions
4. **PARSE natural language** to extract dates, times, names, emails
5. **CALCULATE dates dynamically** using `date` command
6. **CONFIRM actions** before deleting or modifying events
7. **FORMAT responses** in user-friendly way with emojis/structure
</rules>

<references>

- [Google Calendar API v3](https://developers.google.com/workspace/calendar/api/v3/reference)
- [Gmail API v1](https://developers.google.com/gmail/api/reference/rest)
- [Calendar Events](https://developers.google.com/workspace/calendar/api/v3/reference/events)
- [Gmail Messages](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages)
</references>
