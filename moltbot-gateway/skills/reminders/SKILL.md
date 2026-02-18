---
name: reminders
description: Reminders and scheduled notifications - remind me, set reminder, create reminder, remind tomorrow, remind at, set alarm, notify me, reminder list, show reminders, my reminders, cancel reminder, delete reminder, stop reminder, remove reminder, recurring reminder, daily reminder, weekly reminder, monthly reminder, every day, every week, every monday, remind me to, don't let me forget, alert me, schedule reminder
user-invocable: true
metadata: {"openclaw": {"emoji": "⏰"}}
---

# Reminders — Set, List & Cancel via Moltbot API

🎯 **Manages reminders by calling the Moltbot FastAPI backend. Supports one-time and recurring reminders (daily, weekly, monthly).**

## ⚡ When to Use This Skill

Use this skill when the user asks about:
- **Setting reminders**: "remind me", "set a reminder", "remind me tomorrow at 2pm to buy milk", "notify me at 6pm", "don't let me forget"
- **Listing reminders**: "show my reminders", "what reminders do I have", "list my reminders"
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

## ❌ CANCEL A REMINDER

When user says: "Cancel my reminder" or "Delete reminder #1" or "Stop the daily medicine reminder"

**Steps:**
1. **First list reminders** to find the correct one (if user doesn't provide ID)
2. **Confirm with user** which reminder to cancel
3. **Call cancel API**

```bash
# Extract or find the REMINDER_ID
REMINDER_ID=<FROM_LIST_OR_USER_REQUEST>

# Cancel the reminder
RESPONSE=$(curl -s -X POST \
  "${FASTAPI_URL}/api/v1/reminders/cancel" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"${MOLTBOT_USER_ID}\",
    \"reminder_id\": ${REMINDER_ID}
  }")

echo "$RESPONSE"

# Confirm to user
echo "✅ Reminder #${REMINDER_ID} cancelled successfully"
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
2. **ALWAYS convert to UTC** — Use $USER_TIMEZONE to convert local times to UTC for the API
3. **ALWAYS confirm actions** — Tell the user what was set, when, and the recurrence
4. **ASK for missing information** — If the user doesn't specify a time, ask: "What time should I remind you?"
5. **PARSE natural language** — Understand "tomorrow", "next week", "in 2 hours", "every Monday"
6. **DISPLAY times in user's timezone** — When showing reminders, convert UTC back to local
7. **LIST before cancelling** — If user says "cancel my reminder" without an ID, list reminders first
8. **FORMAT responses** in a user-friendly way with emojis and clear structure
