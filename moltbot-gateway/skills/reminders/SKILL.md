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
- **Time**: What time to fire
  - "at 2pm" → 14:00
  - "at 9 AM" → 09:00
  - "at 18:00" → 18:00
  - "noon" → 12:00
  - Not specified → default to 09:00 (morning)
- **Recurrence**: How often
  - "every day" / "daily" → recurrence = "daily"
  - "every week" / "weekly" / "every Monday" → recurrence = "weekly"
  - "every month" / "monthly" → recurrence = "monthly"
  - Not specified → recurrence = "none" (one-time)

### IMPORTANT: Timezone Handling

**The user speaks in their local time. The API expects UTC.**

The user's timezone is `$USER_TIMEZONE` (e.g., "Asia/Kolkata" = UTC+5:30).

You MUST convert the user's local time to UTC before calling the API:
- User says "2pm" in Asia/Kolkata → 2:00 PM IST = 8:30 AM UTC → `trigger_at = "2026-02-19T08:30:00Z"`
- User says "9am" in America/New_York → 9:00 AM EST = 2:00 PM UTC → `trigger_at = "2026-02-19T14:00:00Z"`

Use the `date` command to calculate UTC times:

```bash
# Convert user's local time to UTC ISO 8601
# Example: Tomorrow at 2pm in user's timezone
TRIGGER_AT=$(TZ="$USER_TIMEZONE" date -u -d "tomorrow 14:00" +%Y-%m-%dT%H:%M:%SZ)

# Example: Today at 6pm in user's timezone
TRIGGER_AT=$(TZ="$USER_TIMEZONE" date -u -d "today 18:00" +%Y-%m-%dT%H:%M:%SZ)

# Example: Next Monday at 9am in user's timezone
TRIGGER_AT=$(TZ="$USER_TIMEZONE" date -u -d "next Monday 09:00" +%Y-%m-%dT%H:%M:%SZ)

# Example: In 2 hours from now
TRIGGER_AT=$(date -u -d "+2 hours" +%Y-%m-%dT%H:%M:%SZ)

# Example: In 30 minutes from now
TRIGGER_AT=$(date -u -d "+30 minutes" +%Y-%m-%dT%H:%M:%SZ)
```

### Create One-Time Reminder

When user says: "Remind me tomorrow at 2pm to buy milk" or "Set a reminder for 6pm to call John"

**YOU MUST execute the curl command and parse the JSON response. DO NOT just describe what to do - ACTUALLY RUN THE COMMAND.**

```bash
# PARSE all values from user's actual request - DO NOT use these placeholder values!
REMINDER_MESSAGE="<EXTRACTED_FROM_USER_REQUEST>"
DATE_PART="<EXTRACTED_DATE>"  # e.g., "tomorrow", "next Monday", "2026-02-20"
TIME_PART="<EXTRACTED_TIME>"  # e.g., "14:00", "09:00", "18:00"

# Calculate UTC trigger time from user's local time
TRIGGER_AT=$(TZ="$USER_TIMEZONE" date -u -d "${DATE_PART} ${TIME_PART}" +%Y-%m-%dT%H:%M:%SZ)

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

When user says: "Remind me every day at 9am to take medicine" or "Set a weekly reminder for Monday at 10am"

```bash
# PARSE from user's actual request
REMINDER_MESSAGE="<EXTRACTED_FROM_USER_REQUEST>"
DATE_PART="<EXTRACTED_DATE_OR_TODAY>"
TIME_PART="<EXTRACTED_TIME>"
RECURRENCE="<daily|weekly|monthly>"

# Calculate the first trigger time in UTC
TRIGGER_AT=$(TZ="$USER_TIMEZONE" date -u -d "${DATE_PART} ${TIME_PART}" +%Y-%m-%dT%H:%M:%SZ)

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
  # CRITICAL: Convert user's local time to UTC
  # When user says "change to 11am", they mean 11am in THEIR timezone (not UTC)
  TRIGGER_AT=$(TZ="$USER_TIMEZONE" date -u -d "${DATE_PART} ${NEW_TIME}" +%Y-%m-%dT%H:%M:%SZ)
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
2. **TIMEZONE CONVERSION IS MANDATORY** — When user says "10am", they mean 10am in $USER_TIMEZONE (NOT UTC). YOU MUST run: `TRIGGER_AT=$(TZ="$USER_TIMEZONE" date -u -d "tomorrow 10:00" +%Y-%m-%dT%H:%M:%SZ)` to convert to UTC. DO NOT skip this step or you will schedule reminders at the wrong time!
3. **USE UPDATE ENDPOINT for changes** — When user wants to change a reminder time/message, use `/api/v1/reminders/update` instead of cancelling and recreating
4. **USE SMART SEARCH for updates/cancels** — When user says "change my claude billing reminder" or "cancel my daily reminder", use the smart search + disambiguation approach (search by keywords, time, or recurrence, handle 0/1/multiple matches). This works across sessions and time, unlike relying on conversation history.
5. **ALWAYS confirm actions** — Tell the user what was set, when, and the recurrence (in THEIR timezone). DO NOT show technical IDs to users.
6. **ASK for missing information** — If the user doesn't specify a time, ask: "What time should I remind you?"
7. **PARSE natural language** — Understand "tomorrow", "next week", "in 2 hours", "every Monday"
8. **DISPLAY times in user's timezone** — When showing reminders, convert UTC back to local time for readability
9. **FORMAT responses** in a user-friendly way with emojis and clear structure
10. **EXECUTE the bash commands** — DO NOT just describe or acknowledge the commands - ACTUALLY RUN THEM
