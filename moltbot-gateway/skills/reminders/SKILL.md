---
name: reminders
description: Reminders and scheduled notifications - remind me, set reminder, create reminder, remind tomorrow, remind at, set alarm, notify me, reminder list, show reminders, my reminders, update reminder, change reminder, modify reminder, cancel reminder, delete reminder, stop reminder, remove reminder, recurring reminder, daily reminder, weekly reminder, monthly reminder, every day, every week, every monday, remind me to, don't let me forget, alert me, schedule reminder
user-invocable: true
metadata: {"openclaw": {"emoji": "⏰"}}
---

# Reminders — Set, List, Update & Cancel via Moltbot API

🎯 **Manages reminders by calling the Moltbot FastAPI backend. Supports one-time and recurring reminders (daily, weekly, monthly). Can update existing reminders.**

## ⚡ When to Use This Skill

Use this skill when the user asks about:
- **Setting reminders**: "remind me", "set a reminder", "remind me tomorrow at 2pm to buy milk", "notify me at 6pm", "don't let me forget"
- **Listing reminders**: "show my reminders", "what reminders do I have", "list my reminders"
- **Updating reminders**: "change reminder to 10am", "update my daily reminder", "modify the reminder time", "change that reminder to 3pm"
- **Cancelling reminders**: "cancel my reminder", "delete reminder", "stop the reminder", "remove reminder"
- **Recurring reminders**: "remind me every day at 9am", "set a daily reminder", "weekly reminder every Monday"

## 🔑 Environment Variables

The following are automatically available:
- `$FASTAPI_URL` — The Moltbot FastAPI backend URL (e.g., `https://moltbot-fastapi.onrender.com`)
- `$MOLTBOT_USER_ID` — The current user's ID from Peppi
- `$USER_TIMEZONE` — The user's timezone (e.g., `Asia/Kolkata`, `America/New_York`)

## 📝 CREATE A REMINDER

### CRITICAL: Parameter Extraction Instructions

**ALWAYS extract ALL details from the user's actual request. NEVER use hardcoded values.**

Parse user input to extract:
- **Message**: What to remind about
  - "remind me to buy milk" → message = "buy milk"
  - "remind me about the meeting" → message = "the meeting"
  - "don't let me forget to call John" → message = "call John"
- **Date**: When to remind
  - "tomorrow" → calculate tomorrow's date
  - "today" → today's date
  - "next Monday" → calculate next Monday date
  - "February 20" → parse as 2026-02-20
  - "in 2 hours" → current time + 2 hours
  - "in 30 minutes" → current time + 30 minutes
- **Time**: What time to fire (convert ALL formats to HH:MM 24-hour for the date command)
  - "at 2pm" / "2 PM" / "2:00pm" / "2:00 p.m." → 14:00
  - "9 AM" / "9am" / "9 a.m." / "9:00 AM" → 09:00
  - "18:00" / "6:00 PM" → 18:00
  - "0700" / "0700hrs" / "0700 hours" → 07:00 (military without colon)
  - "7" / "at 7" / "7 o'clock" → 07:00 (assume AM if no context, PM if afternoon context)
  - "7.30" / "7:30" / "730" → 07:30 (dot notation, colon, or no separator)
  - "noon" / "12" / "midday" → 12:00
  - "midnight" → 00:00
  - "morning" → 09:00, "afternoon" → 14:00, "evening" → 18:00, "night" → 21:00
  - "quarter past 7" → 07:15, "half past 3" → 15:30, "quarter to 5" → 16:45
  - "in 30 minutes" / "in half an hour" → current time + 30 min
  - "in 2 hours" / "in an hour" → current time + N hours
  - Not specified → default to 09:00 (morning)
- **Recurrence**: How often
  - "every day" / "daily" → recurrence = "daily"
  - "Monday to Friday" / "Mon-Fri" / "weekdays" → recurrence = "weekdays"
  - "every week" / "weekly" / "every Monday" → recurrence = "weekly"
  - "every month" / "monthly" → recurrence = "monthly"
  - Not specified → recurrence = "none" (one-time)

### IMPORTANT: Timezone Handling

**The user speaks in their local time. Send the time in LOCAL format — the backend API converts to UTC automatically.**

The user's timezone is `$USER_TIMEZONE` (e.g., "Asia/Kolkata", "America/New_York").

**CRITICAL: DO NOT use `-u` flag or `Z` suffix when computing trigger_at for specific times!**
The backend receives the local time + user_timezone and converts to UTC correctly. If you send UTC (with Z), the backend treats it as already-converted and the reminder fires at the WRONG time.

**For SPECIFIC times** (user says "at 7am", "at 2pm", etc.):
```bash
# Get the DATE in user's timezone, then combine with the TIME the user specified
# DO NOT use -u flag! DO NOT add Z suffix! Send as LOCAL time.

# Example: Tomorrow at 2pm
TARGET_DATE=$(TZ="$USER_TIMEZONE" date -d "tomorrow" +%Y-%m-%d)
TRIGGER_AT="${TARGET_DATE}T14:00:00"

# Example: Today at 6pm
TARGET_DATE=$(TZ="$USER_TIMEZONE" date -d "today" +%Y-%m-%d)
TRIGGER_AT="${TARGET_DATE}T18:00:00"

# Example: Next Monday at 9am
TARGET_DATE=$(TZ="$USER_TIMEZONE" date -d "next Monday" +%Y-%m-%d)
TRIGGER_AT="${TARGET_DATE}T09:00:00"
```

**For RELATIVE times** (user says "in 5 minutes", "in 2 hours"):
```bash
# Relative times: compute in user's timezone too (no -u, no Z)
TRIGGER_AT=$(TZ="$USER_TIMEZONE" date -d "+2 hours" +%Y-%m-%dT%H:%M:%S)
TRIGGER_AT=$(TZ="$USER_TIMEZONE" date -d "+30 minutes" +%Y-%m-%dT%H:%M:%S)
```

**WHY this approach?** The backend's `local_to_utc()` function:
- If it sees NO timezone marker → treats as user's local time → converts to UTC ✓
- If it sees Z or +00:00 → treats as already UTC → NO conversion (can be WRONG if you forgot TZ)

### Create One-Time Reminder

When user says: "Remind me tomorrow at 2pm to buy milk" or "Set a reminder for 6pm to call John"

**YOU MUST execute the curl command and parse the JSON response. DO NOT just describe what to do - ACTUALLY RUN THE COMMAND.**

```bash
# PARSE all values from user's actual request - DO NOT use these placeholder values!
REMINDER_MESSAGE="<EXTRACTED_FROM_USER_REQUEST>"
DATE_PART="<EXTRACTED_DATE>"  # e.g., "tomorrow", "next Monday", "2026-02-20"
TIME_PART="<EXTRACTED_TIME>"  # e.g., "14:00", "09:00", "18:00" (24-hour format)

# Build trigger_at in LOCAL time (NO -u flag, NO Z suffix!)
# The backend API will convert from user's timezone to UTC
TARGET_DATE=$(TZ="$USER_TIMEZONE" date -d "${DATE_PART}" +%Y-%m-%d)
TRIGGER_AT="${TARGET_DATE}T${TIME_PART}:00"

# For relative times like "in 5 minutes", "in 2 hours":
# TRIGGER_AT=$(TZ="$USER_TIMEZONE" date -d "+5 minutes" +%Y-%m-%dT%H:%M:%S)

# Call the Moltbot FastAPI to create the reminder
RESPONSE=$(curl -s -X POST \
  "${FASTAPI_URL}/api/v1/reminders/create" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"${MOLTBOT_USER_ID}\",
    \"message\": \"${REMINDER_MESSAGE}\",
    \"trigger_at\": \"${TRIGGER_AT}\",
    \"user_timezone\": \"${USER_TIMEZONE}\",
    \"recurrence\": \"none\"
  }")

echo "$RESPONSE"

# IMPORTANT: Always confirm success to user
echo "✅ Reminder set for ${DATE_PART} at ${TIME_PART}: ${REMINDER_MESSAGE}"
```

### Create Recurring Reminder

When user says: "Remind me every day at 9am to take medicine" or "Set a weekly reminder for Monday at 10am" or "Remind me Mon-Fri at 7am to exercise"

```bash
# PARSE from user's actual request
REMINDER_MESSAGE="<EXTRACTED_FROM_USER_REQUEST>"
DATE_PART="<EXTRACTED_DATE_OR_TODAY>"
TIME_PART="<EXTRACTED_TIME>"  # 24-hour format: "07:00", "14:00", "09:00"
RECURRENCE="<daily|weekdays|weekly|monthly>"  # Use "weekdays" for Mon-Fri

# Build trigger_at in LOCAL time (NO -u flag, NO Z suffix!)
# The backend API will convert from user's timezone to UTC and build the CRON
TARGET_DATE=$(TZ="$USER_TIMEZONE" date -d "${DATE_PART}" +%Y-%m-%d)
TRIGGER_AT="${TARGET_DATE}T${TIME_PART}:00"

# Call the API with recurrence
RESPONSE=$(curl -s -X POST \
  "${FASTAPI_URL}/api/v1/reminders/create" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"${MOLTBOT_USER_ID}\",
    \"message\": \"${REMINDER_MESSAGE}\",
    \"trigger_at\": \"${TRIGGER_AT}\",
    \"user_timezone\": \"${USER_TIMEZONE}\",
    \"recurrence\": \"${RECURRENCE}\"
  }")

echo "$RESPONSE"

# Confirm to user
echo "✅ ${RECURRENCE^} reminder set: ${REMINDER_MESSAGE} at ${TIME_PART}"
```

### Auto-Set Reminders from Calendar Events

When user says: "remind me for my meetings" or "set reminders for all my events" or "remind me before my meetings" or "check my calendar and remind me for meets whenever I have"

**This is a COMPOUND action — you must use BOTH skills:**
1. First, fetch upcoming calendar events (using google-workspace skill's approach)
2. Then, for each future event, create a one-time reminder (default: 30 minutes before)

**YOU MUST execute these commands — do NOT ask "what should I remind you about?" when calendar context is available.**

```bash
# Step 1: Get upcoming events from Google Calendar
EVENTS_JSON=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=$(date -u +%Y-%m-%dT%H:%M:%SZ)&maxResults=10&singleEvents=true&orderBy=startTime")

EVENT_COUNT=$(echo "$EVENTS_JSON" | jq '.items | length')

if [ "$EVENT_COUNT" -eq 0 ]; then
  echo "📭 No upcoming events found on your calendar."
  exit 0
fi

echo "Found ${EVENT_COUNT} upcoming events. Setting reminders..."

# Step 2: For each event, calculate 30 min before and set a reminder
echo "$EVENTS_JSON" | jq -c '.items[]' | while read -r EVENT; do
  EVENT_TITLE=$(echo "$EVENT" | jq -r '.summary')
  EVENT_TIME=$(echo "$EVENT" | jq -r '.start.dateTime // .start.date')

  # Calculate 30 minutes before the event (safe ISO 8601 parsing)
  EVENT_EPOCH=$(date -d "$EVENT_TIME" +%s 2>/dev/null || date -d "$(echo $EVENT_TIME | sed 's/+\([0-9][0-9]\):\([0-9][0-9]\)$/+\1\2/')" +%s)
  REMINDER_EPOCH=$((EVENT_EPOCH - 1800))
  # Output in LOCAL time (no -u, no Z) — backend converts to UTC
  TRIGGER_AT=$(TZ="$USER_TIMEZONE" date -d "@$REMINDER_EPOCH" +%Y-%m-%dT%H:%M:%S)

  # Only set reminder if the reminder time is still in the future
  NOW_EPOCH=$(date +%s)
  if [ "$REMINDER_EPOCH" -gt "$NOW_EPOCH" ]; then
    RESPONSE=$(curl -s -X POST \
      "${FASTAPI_URL}/api/v1/reminders/create" \
      -H "Content-Type: application/json" \
      -d "{
        \"user_id\": \"${MOLTBOT_USER_ID}\",
        \"message\": \"Upcoming: ${EVENT_TITLE}\",
        \"trigger_at\": \"${TRIGGER_AT}\",
        \"user_timezone\": \"${USER_TIMEZONE}\",
        \"recurrence\": \"none\"
      }")

    # Display in user's local time
    LOCAL_TIME=$(TZ="$USER_TIMEZONE" date -d "@$EVENT_EPOCH" '+%I:%M %p on %b %d' 2>/dev/null || echo "$EVENT_TIME")
    echo "✅ Reminder set for '${EVENT_TITLE}' — 30 min before event at ${LOCAL_TIME}"
  else
    echo "⏩ Skipped '${EVENT_TITLE}' — event is too soon or already passed"
  fi
done
```

## 📋 LIST REMINDERS

When user asks: "Show my reminders" or "What reminders do I have?" or "List my reminders"

```bash
# List all reminders for the user
RESPONSE=$(curl -s \
  "${FASTAPI_URL}/api/v1/reminders/list/${MOLTBOT_USER_ID}")

echo "$RESPONSE"
```

To list only pending reminders:

```bash
# List only pending reminders
RESPONSE=$(curl -s \
  "${FASTAPI_URL}/api/v1/reminders/list/${MOLTBOT_USER_ID}?status=pending")

echo "$RESPONSE"
```

**Parse the response and present reminders in a user-friendly format:**
- "📝 Reminder #1: Buy milk — Tomorrow at 2:00 PM (one-time)"
- "📝 Reminder #2: Take medicine — Every day at 9:00 AM (daily)"
- "📝 Reminder #3: Team standup — Every Monday at 10:00 AM (weekly)"

Convert UTC times back to the user's local timezone for display.

## 🔄 UPDATE A REMINDER

When user says: "Change reminder #1 to 3pm" or "Update my daily reminder to 10am" or "Change my claude billing reminder from 10AM to 11AM"

**IMPORTANT: Use the UPDATE endpoint instead of cancelling and recreating!**

**SCALABLE APPROACH: Smart search + disambiguation (works across sessions and time)**

This approach mirrors the calendar event update strategy - it searches for reminders intelligently and handles ambiguity gracefully.

### Step 1: Parse what user wants to change

Extract from the user's actual request:
- **Message keywords**: "claude billing", "medicine", "standup", etc.
- **Time mentioned**: "10am", "2pm", "morning", etc.
- **Recurrence type**: "daily", "weekly", "monthly"
- **What to update**: new time, new message, new recurrence

### Step 2: Search for matching reminders

**YOU MUST execute these commands and parse the JSON response. DO NOT just describe - ACTUALLY RUN THEM.**

```bash
# Step 2A: List all pending reminders for the user
LIST_RESPONSE=$(curl -s \
  "${FASTAPI_URL}/api/v1/reminders/list/${MOLTBOT_USER_ID}?status=pending")

# Step 2B: Parse the reminders array
REMINDERS=$(echo "$LIST_RESPONSE" | jq -c '.data.reminders[]')
REMINDER_COUNT=$(echo "$LIST_RESPONSE" | jq '.data.total')

# Check if user has any reminders
if [ "$REMINDER_COUNT" -eq 0 ]; then
  echo "📭 You don't have any active reminders to update."
  exit 0
fi

# Step 2C: Search for matching reminder based on user's description
# OPTION A: User mentioned keywords (e.g., "claude billing", "medicine")
# Extract keywords from user request - e.g., "change my claude billing reminder"
SEARCH_KEYWORDS="<EXTRACTED_KEYWORDS>"  # e.g., "claude billing", "medicine", "standup"

if [ -n "$SEARCH_KEYWORDS" ]; then
  # Filter reminders by message content (case-insensitive)
  MATCHED_REMINDERS=$(echo "$REMINDERS" | jq -s --arg keywords "${SEARCH_KEYWORDS,,}" \
    '[.[] | select(.message | ascii_downcase | contains($keywords))]')
  MATCH_COUNT=$(echo "$MATCHED_REMINDERS" | jq 'length')

# OPTION B: User mentioned time (e.g., "my 10am reminder")
# Extract time from user request - e.g., "change my 10am reminder"
elif [ -n "<EXTRACTED_TIME>" ]; then
  SEARCH_TIME="<EXTRACTED_TIME>"  # e.g., "10:00", "14:00"
  # Note: Reminders are stored in UTC, so we need to convert search time to UTC range
  SEARCH_TIME_UTC=$(TZ="$USER_TIMEZONE" date -u -d "today ${SEARCH_TIME}" +%H:%M)

  # Filter reminders that trigger around this time (±30 min window)
  MATCHED_REMINDERS=$(echo "$REMINDERS" | jq -s --arg time "$SEARCH_TIME_UTC" \
    '[.[] | select(.trigger_at | match($time))]')
  MATCH_COUNT=$(echo "$MATCHED_REMINDERS" | jq 'length')

# OPTION C: User mentioned recurrence type (e.g., "my daily reminder")
elif [ -n "<EXTRACTED_RECURRENCE>" ]; then
  RECURRENCE_TYPE="<EXTRACTED_RECURRENCE>"  # e.g., "daily", "weekly", "monthly"

  MATCHED_REMINDERS=$(echo "$REMINDERS" | jq -s --arg rec "$RECURRENCE_TYPE" \
    '[.[] | select(.recurrence == $rec)]')
  MATCH_COUNT=$(echo "$MATCHED_REMINDERS" | jq 'length')

# OPTION D: User didn't provide specifics - show all pending reminders
else
  MATCHED_REMINDERS=$(echo "$REMINDERS" | jq -s '.')
  MATCH_COUNT="$REMINDER_COUNT"
fi
```

### Step 3: Handle search results - disambiguation logic

```bash
# Handle different match scenarios
if [ "$MATCH_COUNT" -eq 0 ]; then
  # NO MATCHES - Ask user to be more specific
  echo "❌ I couldn't find a reminder matching that description."
  echo ""
  echo "Your active reminders:"
  echo "$REMINDERS" | jq -r '"📝 #\(.id): \(.message) — \(.recurrence) at \(.trigger_at)"'
  echo ""
  echo "Can you be more specific? (Use reminder message or time)"
  exit 1

elif [ "$MATCH_COUNT" -eq 1 ]; then
  # EXACTLY ONE MATCH - Perfect! Extract details and confirm
  FOUND_REMINDER=$(echo "$MATCHED_REMINDERS" | jq '.[0]')
  REMINDER_ID=$(echo "$FOUND_REMINDER" | jq -r '.id')
  REMINDER_MESSAGE=$(echo "$FOUND_REMINDER" | jq -r '.message')
  REMINDER_TIME=$(echo "$FOUND_REMINDER" | jq -r '.trigger_at')
  REMINDER_RECURRENCE=$(echo "$FOUND_REMINDER" | jq -r '.recurrence')

  # Convert UTC time to user's local timezone for display
  REMINDER_TIME_LOCAL=$(TZ="$USER_TIMEZONE" date -d "$REMINDER_TIME" '+%I:%M %p on %b %d' 2>/dev/null || echo "$REMINDER_TIME")

  echo "📝 Found: '${REMINDER_MESSAGE}' (${REMINDER_RECURRENCE}) scheduled for ${REMINDER_TIME_LOCAL}"
  echo ""
  # Proceed to Step 4 (update)

else
  # MULTIPLE MATCHES - Ask user to disambiguate
  echo "Found ${MATCH_COUNT} reminders that match:"
  echo ""
  echo "$MATCHED_REMINDERS" | jq -r '.[] | "📝 #\(.id): \(.message) — \(.recurrence) at \(.trigger_at)"'
  echo ""
  echo "Which reminder do you want to update? (Tell me the message or ID)"
  exit 1
fi
```

### Step 4: Extract what to update and call API with timezone conversion

```bash
# Parse what user wants to change
NEW_MESSAGE="<EXTRACTED_NEW_MESSAGE_IF_CHANGING>"  # Empty if not changing message
NEW_TIME="<EXTRACTED_NEW_TIME>"  # e.g., "11:00", "14:00"
NEW_RECURRENCE="<EXTRACTED_NEW_RECURRENCE_IF_CHANGING>"  # Empty if not changing recurrence
DATE_PART="<EXTRACTED_DATE_OR_TODAY>"  # e.g., "today", "tomorrow", "next Monday"

# Build the update request payload dynamically
UPDATE_PAYLOAD="{\"user_id\": \"${MOLTBOT_USER_ID}\", \"reminder_id\": ${REMINDER_ID}"

# Add fields only if they're being updated
if [ -n "$NEW_MESSAGE" ]; then
  UPDATE_PAYLOAD="${UPDATE_PAYLOAD}, \"message\": \"${NEW_MESSAGE}\""
fi

if [ -n "$NEW_TIME" ]; then
  # Send LOCAL time (NO -u, NO Z!) — backend converts to UTC
  TARGET_DATE=$(TZ="$USER_TIMEZONE" date -d "${DATE_PART}" +%Y-%m-%d)
  TRIGGER_AT="${TARGET_DATE}T${NEW_TIME}:00"
  UPDATE_PAYLOAD="${UPDATE_PAYLOAD}, \"trigger_at\": \"${TRIGGER_AT}\", \"user_timezone\": \"${USER_TIMEZONE}\""
fi

if [ -n "$NEW_RECURRENCE" ]; then
  UPDATE_PAYLOAD="${UPDATE_PAYLOAD}, \"recurrence\": \"${NEW_RECURRENCE}\""
fi

UPDATE_PAYLOAD="${UPDATE_PAYLOAD}}"

# Call the update API
RESPONSE=$(curl -s -X POST \
  "${FASTAPI_URL}/api/v1/reminders/update" \
  -H "Content-Type: application/json" \
  -d "$UPDATE_PAYLOAD")

echo "$RESPONSE"

# IMPORTANT: Confirm success with clean, user-friendly message in LOCAL time
# DO NOT show reminder ID - users don't care about technical details
if [ -n "$NEW_TIME" ]; then
  NEW_TIME_LOCAL=$(TZ="$USER_TIMEZONE" date -d "${DATE_PART} ${NEW_TIME}" '+%I:%M %p' 2>/dev/null || echo "$NEW_TIME")
  echo "✅ Reminder updated! '${REMINDER_MESSAGE}' is now scheduled for ${NEW_TIME_LOCAL}"
elif [ -n "$NEW_MESSAGE" ]; then
  echo "✅ Reminder message updated to: '${NEW_MESSAGE}'"
elif [ -n "$NEW_RECURRENCE" ]; then
  echo "✅ Reminder recurrence changed to: ${NEW_RECURRENCE}"
else
  echo "✅ Reminder updated successfully"
fi
```

**Optional fields in update request (include only what's changing):**
- `message`: New reminder text (omit if not changing)
- `trigger_at`: New UTC time (omit if not changing time)
- `recurrence`: New recurrence: "none", "daily", "weekly", "monthly" (omit if not changing)
- `user_timezone`: User's timezone (always include if changing time)

**Example: Update only the message**
```bash
RESPONSE=$(curl -s -X POST \
  "${FASTAPI_URL}/api/v1/reminders/update" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"${MOLTBOT_USER_ID}\",
    \"reminder_id\": ${REMINDER_ID},
    \"message\": \"new reminder text\"
  }")
```

## ❌ CANCEL A REMINDER

When user says: "Cancel my reminder" or "Delete reminder #1" or "Stop the daily medicine reminder"

**SCALABLE APPROACH: Use smart search to find the reminder (same as UPDATE)**

### Step 1: Search for the reminder to cancel

```bash
# Step 1A: List all pending reminders
LIST_RESPONSE=$(curl -s \
  "${FASTAPI_URL}/api/v1/reminders/list/${MOLTBOT_USER_ID}?status=pending")

REMINDERS=$(echo "$LIST_RESPONSE" | jq -c '.data.reminders[]')
REMINDER_COUNT=$(echo "$LIST_RESPONSE" | jq '.data.total')

if [ "$REMINDER_COUNT" -eq 0 ]; then
  echo "📭 You don't have any active reminders to cancel."
  exit 0
fi

# Step 1B: Search for matching reminder
# Extract keywords from user request (e.g., "cancel my medicine reminder")
SEARCH_KEYWORDS="<EXTRACTED_KEYWORDS>"  # e.g., "medicine", "standup", "billing"

if [ -n "$SEARCH_KEYWORDS" ]; then
  # Search by message keywords
  MATCHED_REMINDERS=$(echo "$REMINDERS" | jq -s --arg keywords "${SEARCH_KEYWORDS,,}" \
    '[.[] | select(.message | ascii_downcase | contains($keywords))]')
  MATCH_COUNT=$(echo "$MATCHED_REMINDERS" | jq 'length')
else
  # User said "cancel my reminder" without specifics - show all
  MATCHED_REMINDERS=$(echo "$REMINDERS" | jq -s '.')
  MATCH_COUNT="$REMINDER_COUNT"
fi

# Step 1C: Handle search results
if [ "$MATCH_COUNT" -eq 0 ]; then
  echo "❌ No reminders found matching that description."
  echo ""
  echo "Your active reminders:"
  echo "$REMINDERS" | jq -r '"📝 \(.message) — \(.recurrence) at \(.trigger_at)"'
  exit 1

elif [ "$MATCH_COUNT" -eq 1 ]; then
  # Found exactly one - extract details
  FOUND_REMINDER=$(echo "$MATCHED_REMINDERS" | jq '.[0]')
  REMINDER_ID=$(echo "$FOUND_REMINDER" | jq -r '.id')
  REMINDER_MESSAGE=$(echo "$FOUND_REMINDER" | jq -r '.message')

  echo "📝 Found: '${REMINDER_MESSAGE}'"

else
  # Multiple matches - ask user to specify
  echo "Found ${MATCH_COUNT} reminders:"
  echo ""
  echo "$MATCHED_REMINDERS" | jq -r '.[] | "📝 \(.message) — \(.recurrence)"'
  echo ""
  echo "Which one do you want to cancel? (Be more specific)"
  exit 1
fi
```

### Step 2: Cancel the reminder

```bash
# Cancel the reminder
RESPONSE=$(curl -s -X POST \
  "${FASTAPI_URL}/api/v1/reminders/cancel" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"${MOLTBOT_USER_ID}\",
    \"reminder_id\": ${REMINDER_ID}
  }")

echo "$RESPONSE"

# Confirm to user with clean message (no technical IDs)
echo "✅ Reminder cancelled! You won't be reminded about '${REMINDER_MESSAGE}' anymore."
```

## 🎯 Response Formatting

After executing API calls:

1. **Parse JSON responses** using `jq`:
   ```bash
   # Check if reminder was created successfully
   echo "$RESPONSE" | jq -r '.message'
   
   # Get reminder ID from response
   REMINDER_ID=$(echo "$RESPONSE" | jq -r '.data.id')
   
   # List reminders in readable format
   echo "$RESPONSE" | jq -r '.data.reminders[] | "📝 #\(.id): \(.message) — \(.trigger_at) (\(.recurrence))"'
   ```

2. **Format for user readability**:
   - Created: "✅ Reminder set! I'll remind you to buy milk tomorrow at 2:00 PM."
   - Listed: "📝 You have 3 active reminders: ..."
   - Cancelled: "✅ Reminder cancelled. You won't be reminded about buy milk anymore."
   - No reminders: "📭 You don't have any active reminders."

3. **Handle errors gracefully**:
   - Reminder time in the past → "⚠️ That time has already passed. Please set a future time."
   - QStash not configured → "⚠️ Reminder saved but scheduling is not available right now."
   - No reminders found → "📭 You don't have any reminders set."

## 🚨 CRITICAL RULES

1. **NEVER use hardcoded values** — ALWAYS extract from user's actual request
2. **SEND LOCAL TIME — NOT UTC** — When user says "10am", send trigger_at as LOCAL time: `TARGET_DATE=$(TZ="$USER_TIMEZONE" date -d "tomorrow" +%Y-%m-%d) && TRIGGER_AT="${TARGET_DATE}T10:00:00"`. NEVER use `date -u` or add `Z` suffix to trigger_at! The backend API converts local time to UTC automatically using the user_timezone field. If you send Z-suffixed times, the backend treats them as already-UTC and the reminder fires at the WRONG time!
3. **USE UPDATE ENDPOINT for changes** — When user wants to change a reminder time/message, use `/api/v1/reminders/update` instead of cancelling and recreating
4. **USE SMART SEARCH for updates/cancels** — When user says "change my claude billing reminder" or "cancel my daily reminder", use the smart search + disambiguation approach (search by keywords, time, or recurrence, handle 0/1/multiple matches). This works across sessions and time, unlike relying on conversation history.
5. **ALWAYS confirm actions** — Tell the user what was set, when, and the recurrence (in THEIR timezone). DO NOT show technical IDs to users.
6. **ASK for missing information** — If the user doesn't specify a time, ask: "What time should I remind you?"
7. **PARSE natural language** — Understand "tomorrow", "next week", "in 2 hours", "every Monday"
8. **DISPLAY times in user's timezone** — When showing reminders, convert UTC back to local time for readability
9. **FORMAT responses** in a user-friendly way with emojis and clear structure
10. **EXECUTE the bash commands** — DO NOT just describe or acknowledge the commands - ACTUALLY RUN THEM
11. **HANDLE COMPOUND REQUESTS** — When user says "delete X and then create Y" or "cancel my reminder and set a new one", execute each step SEQUENTIALLY:
    - Step A: Complete the first action (e.g., cancel reminder via API, confirm success)
    - Step B: Then execute the second action (e.g., create new reminder via API, confirm success)
    - Report results of BOTH actions to the user
    - If Step A fails, still attempt Step B unless they are dependent
12. **PARSE MILITARY TIME** — "0700" = 07:00, "1430" = 14:30, "2100" = 21:00. Strip leading zeros for display but use HH:MM for the date command
