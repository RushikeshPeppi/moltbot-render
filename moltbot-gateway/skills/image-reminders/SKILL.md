---
name: image-reminders
description: Image-based reminders — set reminder from image, remind me about this picture, save this image as reminder, remind with photo, screenshot reminder, image note reminder, remember this image, remind me about what's in this photo, remind me to pay this bill, payment reminder from receipt. Do NOT use for text-only reminders without images, listing existing reminders, or cancelling reminders.
user-invocable: true
metadata: {"openclaw": {"emoji": "📸⏰"}}
---

<tool_execution_directive>
CRITICAL: When this skill is triggered with an image context, you MUST execute the bash commands directly using the bash tool.
Follow the One-Turn PVE pattern: DESCRIBE what you see in the image, then EXECUTE the reminder creation, then CONFIRM — all in one response.

**ORDER OF OPERATIONS (mandatory):**
1. FIRST `exec` call this turn: run the `<pre_operation_setup>` block below. It exports `$FASTAPI_URL`, `$MOLTBOT_USER_ID`, `$USER_TIMEZONE` for the rest of the turn.
2. THEN run the operation the user asked for. All operations below assume step 1 has completed.

You are an agent — act, don't narrate.
</tool_execution_directive>

<skill_description>
# Image-Aware Reminders — Set Reminders with Image Context

🎯 **Handles reminder creation when the user's message includes attached images (from Twilio MMS). Uses Sonnet 4.6 vision to extract context from images for smart reminder creation.**

This skill extends the reminders skill specifically for scenarios where images accompany reminder requests.
Images arrive as Twilio media URLs appended to the message context as `[Attached Images]\nImage 1: <url>`.
</skill_description>

<trigger_patterns>
## ⚡ When to Use This Skill

Use this skill when the user's message includes `[Attached Images]` AND involves reminders:
- **Reminder from image content**: "Remind me about this" + 📸 (shopping list, recipe, task board)
- **Reminder with image as note**: "Set a reminder for this" + 📸
- **Reminder from schedule image**: "Remind me of these times" + 📸 (schedule/timetable)
- **Reminder from receipt/bill**: "Remind me to pay this" + 📸 (bill/invoice)
- **Reminder from event poster**: "Remind me about this event" + 📸 (poster/flyer)
- **Contextual reminders**: "Don't let me forget about this" + 📸

**DO NOT use this skill when:**
- No `[Attached Images]` section exists in the message (use reminders skill instead)
- User wants to list, update, or cancel existing reminders (use reminders skill)
- User is just chatting about a photo without requesting a reminder
</trigger_patterns>

<environment_variables>
## 🔑 Environment Variables

After you run the per-turn context block below, these are guaranteed to be set:
- `$FASTAPI_URL` — The Moltbot FastAPI backend URL
- `$MOLTBOT_USER_ID` — The current user's ID from Peppi
- `$USER_TIMEZONE` — The user's timezone (e.g., `Asia/Kolkata`, `America/New_York`)

Don't assume these are pre-populated — the gateway may run in persistent-daemon (HTTP) mode, where per-request values only reach skills via the context broker. The preamble below works in BOTH transports.
</environment_variables>

<pre_operation_setup>
## ⚡ PER-TURN CONTEXT (run this FIRST, before any other bash in this turn)

**MANDATORY:** As your first `exec` call in every turn that uses this skill, run this block. It resolves per-request values from the gateway's loopback broker and `export`s them for the rest of the turn.

The agent MUST substitute `<SESSION_KEY_FROM_CONTEXT>` with the value on the `SessionKey:` line in the system context above. If `$OPENCLAW_SESSION_KEY` is already set in env (legacy spawn path), that wins and no substitution is needed.

```bash
# ── PER-TURN CONTEXT ───────────────────────────────────────────────────
SESSION_KEY="${OPENCLAW_SESSION_KEY:-<SESSION_KEY_FROM_CONTEXT>}"
BROKER_URL="${INTERNAL_BROKER_URL:-http://127.0.0.1:8788}"

CTX=$(curl -sf --max-time 5 "${BROKER_URL}/internal/context/${SESSION_KEY}" 2>/dev/null || echo "")
if [ -n "$CTX" ]; then
  _UID=$(echo "$CTX" | jq -r '.user_id // empty')
  _TZ=$(echo  "$CTX" | jq -r '.user_timezone // empty')
  _API=$(echo "$CTX" | jq -r '.fastapi_url // empty')
  [ -n "$_UID" ] && export MOLTBOT_USER_ID="$_UID"
  [ -n "$_TZ"  ] && export USER_TIMEZONE="$_TZ"
  [ -n "$_API" ] && export FASTAPI_URL="$_API"
fi

if [ -z "$FASTAPI_URL" ] || [ -z "$MOLTBOT_USER_ID" ]; then
  echo "⚠️ Couldn't resolve reminder context. Please try again."
  exit 1
fi
# ───────────────────────────────────────────────────────────────────────
```

After this runs successfully, every operation below uses `$FASTAPI_URL` / `$MOLTBOT_USER_ID` / `$USER_TIMEZONE` as before.
</pre_operation_setup>

<image_context>
## 📸 How Images Arrive

When the user sends an image via SMS/MMS, the image URLs are appended to your message context:

```
[Attached Images]
Image 1: https://api.twilio.com/2010-04-01/Accounts/.../Media/...
```

**Key facts about Twilio image URLs:**
- URLs are publicly accessible for ~2 hours (sufficient for real-time processing)
- Supported formats: JPEG, PNG, GIF
- You (Claude Sonnet 4.6) can see and read these images natively via vision
- Extract text, dates, times, items, prices — anything visible in the image
</image_context>

<operation name="validate_image_url">
## 🔍 VALIDATE IMAGE URL (Run This First — Always)

**Before processing ANY image, verify the URL is accessible.**

```bash
IMAGE_URL="<EXTRACTED_FROM_ATTACHED_IMAGES>"

# Check if URL is accessible (HEAD request, follow redirects)
HTTP_STATUS=$(curl -sI -o /dev/null -w "%{http_code}" -L "$IMAGE_URL")

if [ "$HTTP_STATUS" != "200" ]; then
  echo "⚠️ I couldn't access the image (HTTP $HTTP_STATUS). The link may have expired — Twilio URLs are valid for about 2 hours. Could you resend the image?"
  exit 0
fi
```

**Run this validation BEFORE every image operation. If it fails, stop and tell the user.**
</operation>

<operation name="reminder_from_image">
## 📸⏰ CREATE REMINDER FROM IMAGE CONTENT

When user says: "Remind me about this" + 📸 or "Set a reminder for this" + 📸

### One-Turn PVE Pattern

1. **DESCRIBE**: "I can see a shopping list with 8 items: milk, eggs, bread, butter, cheese, tomatoes, onions, rice."
2. **EXECUTE**: Create the reminder with extracted content.
3. **CONFIRM**: "✅ Reminder set: 'Buy: milk, eggs, bread, butter, cheese, tomatoes, onions, rice' for tomorrow at 10:00 AM"

**If user did NOT specify WHEN to remind, you MUST ASK:**
"I can see [brief description]. When would you like to be reminded about this?"
DO NOT default to a random time — always confirm with the user.

### How to Extract Content

Using your vision, extract the most useful, actionable information:
- **Shopping list** → "Buy: milk, eggs, bread, butter, cheese"
- **Bill/invoice** → "Pay electricity bill - ₹2,500 due March 15"
- **Event poster** → "Tech Meetup at Convention Center - March 20 at 6 PM"
- **Whiteboard** → "Sprint goals: finish API, deploy v2, write tests"
- **Prescription** → "Refill prescription for Amoxicillin"
- **Screenshot of message** → key actionable info from the screenshot

### SMS Length Enforcement

Reminders are delivered via SMS. The reminder message MUST be under 160 characters.
If your extracted content is longer, summarize it to fit. Prioritize the most important details.

### Execution

```bash
IMAGE_URL="<EXTRACTED_FROM_ATTACHED_IMAGES>"

# Step 1: Validate image URL
HTTP_STATUS=$(curl -sI -o /dev/null -w "%{http_code}" -L "$IMAGE_URL")
if [ "$HTTP_STATUS" != "200" ]; then
  echo "⚠️ I couldn't access the image. The link may have expired. Could you resend it?"
  exit 0
fi

# Step 2: Extract content from image using your vision
# Keep it concise — under 160 characters for SMS delivery
REMINDER_MESSAGE="<YOUR_EXTRACTED_CONTENT_FROM_IMAGE>"

# Enforce 160 character limit for SMS
# If your extracted content is over 160 chars, summarize the key points
# Example: Instead of listing 15 items, list the top 8 with "..." at the end

# Step 3: Parse time from user's text (if provided)
# "Remind me about this tomorrow at 2pm" → DATE_PART="tomorrow", TIME_PART="14:00"
# "Remind me about this in 2 hours" → use relative time
# "Remind me about this" (no time) → ASK the user

DATE_PART="<EXTRACTED_DATE>"
TIME_PART="<EXTRACTED_TIME>"

# Step 4: Build trigger_at in LOCAL time (NO -u, NO Z — backend converts to UTC)
TARGET_DATE=$(TZ="$USER_TIMEZONE" date -d "${DATE_PART}" +%Y-%m-%d)
TRIGGER_AT="${TARGET_DATE}T${TIME_PART}:00"

# For relative times like "in 2 hours":
# TRIGGER_AT=$(TZ="$USER_TIMEZONE" date -d "+2 hours" +%Y-%m-%dT%H:%M:%S)

# Step 5: Check for duplicate reminders (prevent accidental duplicates)
EXISTING=$(curl -s "${FASTAPI_URL}/api/v1/reminders/list/${MOLTBOT_USER_ID}?status=pending")
DUPLICATE=$(echo "$EXISTING" | jq -r --arg msg "$REMINDER_MESSAGE" '.data.reminders[]? | select(.message | ascii_downcase | contains($msg | ascii_downcase)) | .id' 2>/dev/null | head -1)

if [ -n "$DUPLICATE" ] && [ "$DUPLICATE" != "null" ]; then
  echo "📝 You already have a similar reminder set. Creating another one anyway..."
fi

# Step 6: Create the reminder via API
JSON_PAYLOAD=$(jq -n \
  --arg uid "$MOLTBOT_USER_ID" \
  --arg msg "$REMINDER_MESSAGE" \
  --arg trigger "$TRIGGER_AT" \
  --arg tz "$USER_TIMEZONE" \
  --arg recur "none" \
  '{user_id: $uid, message: $msg, trigger_at: $trigger, user_timezone: $tz, recurrence: $recur}')

RESPONSE=$(curl -s -X POST \
  "${FASTAPI_URL}/api/v1/reminders/create" \
  -H "Content-Type: application/json" \
  -d "$JSON_PAYLOAD")

REMINDER_ID=$(echo "$RESPONSE" | jq -r '.data.id // empty')
ERROR_MSG=$(echo "$RESPONSE" | jq -r '.error // empty')

if [ -n "$ERROR_MSG" ]; then
  echo "❌ Failed to set reminder: $(echo "$RESPONSE" | jq -r '.message')"
elif [ -n "$REMINDER_ID" ]; then
  echo "✅ Reminder set: '${REMINDER_MESSAGE}' for ${DATE_PART} at ${TIME_PART}"
  echo "If the details aren't right, just tell me and I'll update it."
else
  echo "$RESPONSE"
fi
```
</operation>

<operation name="reminder_from_schedule_image">
## 📅📸 CREATE MULTIPLE REMINDERS FROM SCHEDULE IMAGE

When user says: "Remind me of these times" + 📸 (image of a class schedule, meeting agenda, weekly plan)

### One-Turn PVE Pattern

1. **DESCRIBE**: "I can see a class schedule with 3 entries: Math on Monday at 9 AM, Physics on Monday at 2 PM, Chemistry on Tuesday at 10 AM."
2. **EXECUTE**: Create a reminder for each entry, one at a time.
3. **CONFIRM**: "✅ Created 3 reminders from the schedule."

### How to Create Multiple Reminders

Extract each schedule entry from the image, then create them ONE AT A TIME using individual curl calls. Do NOT use bash arrays or loops — execute each curl command separately so you can handle errors per-entry.

```bash
IMAGE_URL="<EXTRACTED_FROM_ATTACHED_IMAGES>"

# Step 1: Validate image URL
HTTP_STATUS=$(curl -sI -o /dev/null -w "%{http_code}" -L "$IMAGE_URL")
if [ "$HTTP_STATUS" != "200" ]; then
  echo "⚠️ I couldn't access the image. Could you resend it?"
  exit 0
fi

# Step 2: For EACH entry extracted from the schedule image,
# run a separate curl command.

# Example: First entry — "Math class" on Monday at 9 AM
TARGET_DATE_1=$(TZ="$USER_TIMEZONE" date -d "next monday" +%Y-%m-%d)
TRIGGER_AT_1="${TARGET_DATE_1}T09:00:00"

RESPONSE_1=$(curl -s -X POST \
  "${FASTAPI_URL}/api/v1/reminders/create" \
  -H "Content-Type: application/json" \
  -d "$(jq -n \
    --arg uid "$MOLTBOT_USER_ID" \
    --arg msg "Math class" \
    --arg trigger "$TRIGGER_AT_1" \
    --arg tz "$USER_TIMEZONE" \
    --arg recur "weekly" \
    '{user_id: $uid, message: $msg, trigger_at: $trigger, user_timezone: $tz, recurrence: $recur}')")

ERROR_1=$(echo "$RESPONSE_1" | jq -r '.error // empty')
if [ -z "$ERROR_1" ]; then
  echo "✅ Reminder set: Math class — Monday at 9:00 AM (weekly)"
else
  echo "❌ Failed: Math class"
fi

# Example: Second entry — "Physics class" on Monday at 2 PM
TARGET_DATE_2=$(TZ="$USER_TIMEZONE" date -d "next monday" +%Y-%m-%d)
TRIGGER_AT_2="${TARGET_DATE_2}T14:00:00"

RESPONSE_2=$(curl -s -X POST \
  "${FASTAPI_URL}/api/v1/reminders/create" \
  -H "Content-Type: application/json" \
  -d "$(jq -n \
    --arg uid "$MOLTBOT_USER_ID" \
    --arg msg "Physics class" \
    --arg trigger "$TRIGGER_AT_2" \
    --arg tz "$USER_TIMEZONE" \
    --arg recur "weekly" \
    '{user_id: $uid, message: $msg, trigger_at: $trigger, user_timezone: $tz, recurrence: $recur}')")

ERROR_2=$(echo "$RESPONSE_2" | jq -r '.error // empty')
if [ -z "$ERROR_2" ]; then
  echo "✅ Reminder set: Physics class — Monday at 2:00 PM (weekly)"
else
  echo "❌ Failed: Physics class"
fi

# Repeat this pattern for each schedule entry you extract from the image.
# Adapt the message, date, and time for each entry.
# Use "weekly" recurrence for class schedules, "none" for one-time events.
```

**IMPORTANT**: The examples above show the PATTERN. You must extract the ACTUAL entries from the image and create a curl command for each one. The message, date, time, and recurrence should come from what you see in the image.
</operation>

<operation name="reminder_from_bill">
## 💰📸 CREATE PAYMENT REMINDER FROM BILL IMAGE

When user says: "Remind me to pay this" + 📸 (image of a bill, invoice, receipt)

### One-Turn PVE Pattern

1. **DESCRIBE**: "I can see a bill from Maharashtra Electricity Board for ₹2,450 due March 15, 2026."
2. **EXECUTE**: Create a payment reminder for 2 days before the due date at 9 AM.
3. **CONFIRM**: "✅ Payment reminder set: 'Pay Maharashtra Electricity Board — ₹2,450' for March 13 at 9:00 AM. If the amount or date isn't right, tell me and I'll fix it."

**If the due date is not visible**, ask the user instead of guessing:
"I can see a bill from [company] for [amount]. When is it due?"

### Security Rule
**NEVER include sensitive data in the reminder message:**
- ❌ Account numbers, credit card numbers, passwords, SSN
- ✅ Company name, amount, due date

```bash
IMAGE_URL="<EXTRACTED_FROM_ATTACHED_IMAGES>"

# Step 1: Validate image URL
HTTP_STATUS=$(curl -sI -o /dev/null -w "%{http_code}" -L "$IMAGE_URL")
if [ "$HTTP_STATUS" != "200" ]; then
  echo "⚠️ I couldn't access the image. Could you resend it?"
  exit 0
fi

# Step 2: Extract bill details from image using your vision
# REQUIRED: Company/payee name, Amount
# OPTIONAL: Due date (if not visible, ASK the user)
# NEVER INCLUDE: Account numbers, card numbers, or other sensitive data
PAYEE="<EXTRACTED_FROM_IMAGE>"
AMOUNT="<EXTRACTED_FROM_IMAGE>"
DUE_DATE="<EXTRACTED_FROM_IMAGE_OR_EMPTY>"

# Step 3: Build reminder message (keep under 160 chars for SMS)
REMINDER_MESSAGE="Pay ${PAYEE} — ${AMOUNT}"
if [ -n "$DUE_DATE" ]; then
  REMINDER_MESSAGE="${REMINDER_MESSAGE} (due ${DUE_DATE})"
fi

# Step 4: Set reminder timing
if [ -n "$DUE_DATE" ]; then
  # Set reminder 2 days before due date at 9 AM local time
  TARGET_DATE=$(TZ="$USER_TIMEZONE" date -d "${DUE_DATE} -2 days" +%Y-%m-%d)
  TRIGGER_AT="${TARGET_DATE}T09:00:00"
else
  # No due date visible — ask user
  echo "I can see a bill from ${PAYEE} for ${AMOUNT}, but I couldn't find the due date."
  echo "When should I remind you to pay this?"
  exit 0
fi

# Step 5: Check for duplicate payment reminders
EXISTING=$(curl -s "${FASTAPI_URL}/api/v1/reminders/list/${MOLTBOT_USER_ID}?status=pending")
DUPLICATE=$(echo "$EXISTING" | jq -r --arg payee "$PAYEE" '.data.reminders[]? | select(.message | ascii_downcase | contains($payee | ascii_downcase)) | .id' 2>/dev/null | head -1)

if [ -n "$DUPLICATE" ] && [ "$DUPLICATE" != "null" ]; then
  echo "📝 You already have a payment reminder for ${PAYEE}. Creating another one anyway..."
fi

# Step 6: Create the reminder
JSON_PAYLOAD=$(jq -n \
  --arg uid "$MOLTBOT_USER_ID" \
  --arg msg "$REMINDER_MESSAGE" \
  --arg trigger "$TRIGGER_AT" \
  --arg tz "$USER_TIMEZONE" \
  --arg recur "none" \
  '{user_id: $uid, message: $msg, trigger_at: $trigger, user_timezone: $tz, recurrence: $recur}')

RESPONSE=$(curl -s -X POST \
  "${FASTAPI_URL}/api/v1/reminders/create" \
  -H "Content-Type: application/json" \
  -d "$JSON_PAYLOAD")

REMINDER_ID=$(echo "$RESPONSE" | jq -r '.data.id // empty')
ERROR_MSG=$(echo "$RESPONSE" | jq -r '.error // empty')

if [ -n "$ERROR_MSG" ]; then
  echo "❌ Failed to set reminder: $(echo "$RESPONSE" | jq -r '.message')"
elif [ -n "$REMINDER_ID" ]; then
  echo "✅ Payment reminder set: '${REMINDER_MESSAGE}' for ${TARGET_DATE} at 9:00 AM"
  echo "If the amount or date isn't right, tell me and I'll fix it."
fi
```
</operation>

<response_formatting>
## 🎯 Response Formatting for Image Reminders

Follow the One-Turn PVE pattern in EVERY response:

1. **DESCRIBE first**: "I can see a [type of content] with [key details]..." (1-2 sentences)
2. **Action + result**: "✅ Reminder set: '[message]' for [date] at [time]"
3. **Correction offer**: "If the details aren't right, just tell me and I'll update it."
4. **Handle failures**: "⚠️ I couldn't access/read the image. Could you resend it?"
5. **Handle missing time**: "I can see [description]. When would you like to be reminded?"
</response_formatting>

<rules priority="critical">
## 🚨 CRITICAL RULES

1. **VALIDATE FIRST** — Always run URL validation before processing. Expired URLs crash the flow.
2. **DESCRIBE THEN ACT** — Tell the user what you see, then create the reminder, all in one response.
3. **IMAGE URLs are in the context** — Look for `[Attached Images]` section in the message.
4. **ASK for time if not specified** — "Remind me about this" without WHEN → ask "When should I remind you?"
5. **KEEP MESSAGES UNDER 160 CHARS** — Reminders are delivered via SMS. Summarize if content is too long.
6. **SEND LOCAL TIME — NOT UTC** — NO `-u` flag, NO `Z` suffix on trigger_at. Backend converts to UTC.
7. **NEVER hallucinate image content** — If you can't clearly see/read something, say so and ask the user.
8. **SECURITY: No sensitive data** — Never include credit card numbers, account numbers, or passwords in reminder messages.
9. **DUPLICATE AWARENESS** — Check for existing similar reminders before creating. Warn user if duplicate found.
10. **ONE CURL PER ENTRY** — For schedule images with multiple entries, create each reminder with a separate curl call. Do not use bash arrays.
11. **EXECUTE the bash commands** — DO NOT just describe or acknowledge — ACTUALLY RUN THEM.
</rules>
