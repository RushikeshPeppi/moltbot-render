---
name: image-workspace
description: Image-based Google Calendar and Gmail actions — send image via email, create event from screenshot, email screenshot, attach image to email, forward image, describe meeting screenshot, image attachment email, share photo via gmail, event from image, schedule from screenshot. Do NOT use for text-only emails, calendar events without images, general photo discussion, or web searches.
user-invocable: true
metadata: {"openclaw": {"emoji": "📸"}}
---

<tool_execution_directive>
CRITICAL: When this skill is triggered with an image context, you MUST execute the bash commands directly using the bash tool.
Follow the One-Turn PVE pattern: DESCRIBE what you see, then EXECUTE the action, then CONFIRM — all in one response.

**ORDER OF OPERATIONS (mandatory):**
1. FIRST `exec` call this turn: run the `<pre_operation_setup>` block below. It exports `$GOOGLE_ACCESS_TOKEN`, `$USER_TIMEZONE`, `$MOLTBOT_USER_ID`, `$FASTAPI_URL` for the rest of the turn.
2. THEN run the operation the user asked for. All operations below assume step 1 has completed.

You are an agent — act, don't narrate.
</tool_execution_directive>

<skill_description>
# Image-Aware Google Workspace — Calendar & Gmail with Images

🎯 **Handles Google Calendar and Gmail actions when the user's message includes attached images (from Twilio MMS).**

This skill extends the google-workspace skill specifically for scenarios where images are present in the user's request.
Images arrive as Twilio media URLs appended to the message context as `[Attached Images]\nImage 1: <url>`.
</skill_description>

<trigger_patterns>
## ⚡ When to Use This Skill

Use this skill when the user's message includes `[Attached Images]` AND involves:
- **Gmail + Image**: "send this to John", "email this to Sarah", "forward this image", "share this photo via email"
- **Calendar + Image**: "schedule this", "create event from this", "add this to my calendar" (image of a poster/schedule/invite)
- **Image description + Action**: "what's in this image? send it to...", "describe this and email it to..."

**DO NOT use this skill when:**
- No `[Attached Images]` section exists in the message (use google-workspace instead)
- User is just chatting about photos without requesting an action
- User wants to search the web or ask general questions
</trigger_patterns>

<environment_variables>
## 🔑 Environment Variables

After you run the per-turn context block below, these are guaranteed to be set:
- `$GOOGLE_ACCESS_TOKEN` — OAuth 2.0 bearer token (auto-refreshed by FastAPI backend)
- `$USER_TIMEZONE` — The user's timezone (e.g., `Asia/Kolkata`, `America/New_York`)
- `$MOLTBOT_USER_ID` — The current user's ID from Peppi
- `$FASTAPI_URL` — The Moltbot FastAPI backend URL

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
  _TOK=$(echo "$CTX" | jq -r '.google_access_token // empty')
  _UID=$(echo "$CTX" | jq -r '.user_id // empty')
  _TZ=$(echo  "$CTX" | jq -r '.user_timezone // empty')
  _API=$(echo "$CTX" | jq -r '.fastapi_url // empty')
  [ -n "$_TOK" ] && export GOOGLE_ACCESS_TOKEN="$_TOK"
  [ -n "$_UID" ] && export MOLTBOT_USER_ID="$_UID"
  [ -n "$_TZ"  ] && export USER_TIMEZONE="$_TZ"
  [ -n "$_API" ] && export FASTAPI_URL="$_API"
fi

if [ -z "$GOOGLE_ACCESS_TOKEN" ]; then
  echo "⚠️ Couldn't resolve Google OAuth token — your Google connection may need to be refreshed in Settings."
  exit 1
fi
# ───────────────────────────────────────────────────────────────────────
```

After this runs successfully, every operation below uses `$GOOGLE_ACCESS_TOKEN` / `$USER_TIMEZONE` / etc. as before.
</pre_operation_setup>

<image_context>
## 📸 How Images Arrive

When the user sends an image via SMS/MMS, the image URLs are appended to your message context in this format:

```
[Attached Images]
Image 1: https://api.twilio.com/2010-04-01/Accounts/.../Media/...
```

**Key facts about Twilio image URLs:**
- URLs are publicly accessible for ~2 hours (sufficient for real-time processing)
- Supported formats: JPEG, PNG, GIF
- Maximum 10 images per MMS message (realistically 1-2)
- URLs can be downloaded with `curl -sL <url>` for further processing
- URLs require `-L` flag (follow redirects) — Twilio serves a 302 first
</image_context>

<operation name="validate_image_url">
## 🔍 VALIDATE IMAGE URL (Run This First — Always)

**Before processing ANY image, verify the URL is accessible and returns an actual image.**

```bash
IMAGE_URL="<EXTRACTED_FROM_ATTACHED_IMAGES>"

# Step 1: Check if URL is accessible (HEAD request, follow redirects)
HTTP_STATUS=$(curl -sI -o /dev/null -w "%{http_code}" -L "$IMAGE_URL")

if [ "$HTTP_STATUS" != "200" ]; then
  echo "⚠️ I couldn't access the image (HTTP $HTTP_STATUS). The link may have expired — Twilio image URLs are only valid for about 2 hours. Could you resend the image?"
  exit 0
fi

# Step 2: Verify it's actually an image (not HTML error page, etc.)
CONTENT_TYPE=$(curl -sI -L "$IMAGE_URL" | grep -i 'content-type' | tail -1 | awk '{print $2}' | tr -d '\r')

if ! echo "$CONTENT_TYPE" | grep -qi "image/"; then
  echo "⚠️ The attachment doesn't appear to be an image (detected: ${CONTENT_TYPE:-unknown}). Could you resend it?"
  exit 0
fi

echo "Image validated: ${CONTENT_TYPE}"
```

**Run this validation BEFORE every image operation. If it fails, stop and tell the user.**
</operation>

<operation name="email_with_image">
## 📧 SEND IMAGE VIA GMAIL

When user says: "Send this to John" or "Email this photo to sarah@example.com" or "Forward this to my boss"

### One-Turn PVE Pattern

1. **DESCRIBE**: "I can see your photo. Sending it to sarah@example.com now..."
2. **VALIDATE**: Run URL check (above). If URL is dead, stop and ask user to resend.
3. **EXECUTE**: Download image, build MIME, send via Gmail API.
4. **CONFIRM**: "✅ Image sent to sarah@example.com with subject 'Photo shared via Peppi'"

**CRITICAL: Extract recipient from the user's request. If user says "send this to John" without an email, ASK: "What's John's email address?"**

```bash
IMAGE_URL="<EXTRACTED_FROM_ATTACHED_IMAGES>"

# Step 1: Validate image URL
HTTP_STATUS=$(curl -sI -o /dev/null -w "%{http_code}" -L "$IMAGE_URL")
if [ "$HTTP_STATUS" != "200" ]; then
  echo "⚠️ I couldn't access the image (HTTP $HTTP_STATUS). The link may have expired. Could you resend it?"
  exit 0
fi

# Step 2: Parse recipient from user's request
RECIPIENT_EMAIL="<EXTRACTED_FROM_REQUEST>"
SUBJECT="<EXTRACTED_OR_DEFAULT>"
USER_MESSAGE="<EXTRACTED_MESSAGE_IF_ANY>"

# Step 3: Detect content type
CONTENT_TYPE=$(curl -sI -L "$IMAGE_URL" | grep -i 'content-type' | tail -1 | awk '{print $2}' | tr -d '\r')
if [ -z "$CONTENT_TYPE" ] || ! echo "$CONTENT_TYPE" | grep -qi "image/"; then
  CONTENT_TYPE="image/jpeg"
fi

# Step 4: Download image and base64 encode
IMAGE_BASE64=$(curl -sL "$IMAGE_URL" | base64 | tr -d '\n')

if [ -z "$IMAGE_BASE64" ]; then
  echo "⚠️ Failed to download the image. The link may have expired. Could you resend it?"
  exit 0
fi

# Step 5: Build MIME message with inline image
BOUNDARY="boundary_$(date +%s)_peppi"

MIME_MESSAGE="From: me
To: ${RECIPIENT_EMAIL}
Subject: ${SUBJECT:-Photo shared via Peppi}
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary=\"${BOUNDARY}\"

--${BOUNDARY}
Content-Type: text/html; charset=utf-8

<html><body>
<p>${USER_MESSAGE:-Here's an image shared via Peppi:}</p>
<img src=\"cid:attached_image\" style=\"max-width: 600px; border-radius: 8px;\">
</body></html>
--${BOUNDARY}
Content-Type: ${CONTENT_TYPE}
Content-Transfer-Encoding: base64
Content-Disposition: inline; filename=\"image.jpg\"
Content-ID: <attached_image>

${IMAGE_BASE64}
--${BOUNDARY}--"

# Step 6: Base64url encode the entire MIME message for Gmail API
ENCODED_MESSAGE=$(echo "$MIME_MESSAGE" | base64 | tr '+/' '-_' | tr -d '=\n')

# Step 7: Send via Gmail API
RESPONSE=$(curl -s -X POST \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages/send" \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"raw\": \"${ENCODED_MESSAGE}\"}")

# Step 8: Check for errors
ERROR=$(echo "$RESPONSE" | jq -r '.error.message // empty')
if [ -n "$ERROR" ]; then
  echo "❌ Failed to send email: $ERROR"
  exit 1
fi

MESSAGE_ID=$(echo "$RESPONSE" | jq -r '.id')
echo "✅ Image sent to ${RECIPIENT_EMAIL} with subject '${SUBJECT:-Photo shared via Peppi}'"
```
</operation>

<operation name="describe_and_email">
## 🔍📧 DESCRIBE IMAGE AND EMAIL

When user says: "What's in this picture? Also send it to John" or "Describe this and forward to team"

**This is a COMPOUND action — vision description + email send in one response.**

### One-Turn PVE Pattern

1. **DESCRIBE**: Using your vision, tell the user what you see in detail.
2. **EXECUTE**: Build email with your description as the body + the image inline.
3. **CONFIRM**: "✅ Image described and sent to sarah@example.com"

```bash
IMAGE_URL="<EXTRACTED_FROM_ATTACHED_IMAGES>"

# Step 1: Validate image URL
HTTP_STATUS=$(curl -sI -o /dev/null -w "%{http_code}" -L "$IMAGE_URL")
if [ "$HTTP_STATUS" != "200" ]; then
  echo "⚠️ I couldn't access the image. The link may have expired. Could you resend it?"
  exit 0
fi

# Step 2: You (Claude Sonnet) describe the image via your native vision capability
# Write your description as IMAGE_DESCRIPTION variable
IMAGE_DESCRIPTION="<YOUR_VISION_DESCRIPTION_OF_THE_IMAGE>"

# Step 3: Parse recipient and build email
RECIPIENT_EMAIL="<EXTRACTED_FROM_REQUEST>"
SUBJECT="${USER_SUBJECT:-Image from Peppi}"

# Step 4: Download and encode the image
CONTENT_TYPE=$(curl -sI -L "$IMAGE_URL" | grep -i 'content-type' | tail -1 | awk '{print $2}' | tr -d '\r')
if [ -z "$CONTENT_TYPE" ] || ! echo "$CONTENT_TYPE" | grep -qi "image/"; then
  CONTENT_TYPE="image/jpeg"
fi

IMAGE_BASE64=$(curl -sL "$IMAGE_URL" | base64 | tr -d '\n')

if [ -z "$IMAGE_BASE64" ]; then
  echo "⚠️ Failed to download the image. Could you resend it?"
  exit 0
fi

# Step 5: Build and send MIME message
BOUNDARY="boundary_$(date +%s)_peppi"

MIME_MESSAGE="From: me
To: ${RECIPIENT_EMAIL}
Subject: ${SUBJECT}
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary=\"${BOUNDARY}\"

--${BOUNDARY}
Content-Type: text/html; charset=utf-8

<html><body>
<p>${IMAGE_DESCRIPTION}</p>
<br>
<img src=\"cid:attached_image\" style=\"max-width: 600px; border-radius: 8px;\">
</body></html>
--${BOUNDARY}
Content-Type: ${CONTENT_TYPE}
Content-Transfer-Encoding: base64
Content-Disposition: inline; filename=\"image.jpg\"
Content-ID: <attached_image>

${IMAGE_BASE64}
--${BOUNDARY}--"

ENCODED_MESSAGE=$(echo "$MIME_MESSAGE" | base64 | tr '+/' '-_' | tr -d '=\n')

RESPONSE=$(curl -s -X POST \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages/send" \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"raw\": \"${ENCODED_MESSAGE}\"}")

ERROR=$(echo "$RESPONSE" | jq -r '.error.message // empty')
if [ -n "$ERROR" ]; then
  echo "❌ Failed to send: $ERROR"
  exit 1
fi

echo "✅ Image described and sent to ${RECIPIENT_EMAIL}"
```
</operation>

<operation name="calendar_from_image">
## 📅📸 CREATE CALENDAR EVENT FROM IMAGE

When user says: "Add this to my calendar" or "Schedule this" + 📸 image of a poster, invite, or schedule

### One-Turn PVE Pattern

1. **DESCRIBE**: "I can see an event poster for 'Tech Meetup 2026' on March 20 at 6 PM at Convention Center, Mumbai."
2. **EXECUTE**: Create the calendar event with extracted details.
3. **CONFIRM**: "✅ Calendar event 'Tech Meetup 2026' created for March 20 at 6:00 PM. If any details are wrong, just tell me and I'll fix it."

**If critical details are missing** (date, time), ask the user INSTEAD of guessing:
- Image with no date → "I can see this is about 'Tech Meetup'. When is it?"
- Image with date but no time → "This is on March 15. What time does it start?"
- Image is blurry/unreadable → "I couldn't read the details clearly. Can you tell me the event name, date, and time?"

```bash
IMAGE_URL="<EXTRACTED_FROM_ATTACHED_IMAGES>"

# Step 1: Validate image URL
HTTP_STATUS=$(curl -sI -o /dev/null -w "%{http_code}" -L "$IMAGE_URL")
if [ "$HTTP_STATUS" != "200" ]; then
  echo "⚠️ I couldn't access the image. The link may have expired. Could you resend it?"
  exit 0
fi

# Step 2: Extract event details from the image using your vision
# You MUST have at minimum: title + date + time
# If any are unclear, ASK the user — do not guess
EVENT_TITLE="<EXTRACTED_FROM_IMAGE>"
EVENT_DATE="<EXTRACTED_FROM_IMAGE>"
EVENT_TIME="<EXTRACTED_FROM_IMAGE>"
EVENT_DURATION=<EXTRACTED_OR_DEFAULT_60>
EVENT_LOCATION="<EXTRACTED_FROM_IMAGE>"
EVENT_DESCRIPTION="<EXTRACTED_FROM_IMAGE>"

# Step 3: Build calendar event (local time — NOT UTC)
EVENT_DATE_RESOLVED=$(TZ="$USER_TIMEZONE" date -d "${EVENT_DATE}" +%Y-%m-%d)
EVENT_START="${EVENT_DATE_RESOLVED}T${EVENT_TIME}:00"

END_HOUR=$(( ${EVENT_TIME%%:*} + EVENT_DURATION / 60 ))
END_MIN=$(( ${EVENT_TIME##*:} + EVENT_DURATION % 60 ))
if [ $END_MIN -ge 60 ]; then END_HOUR=$((END_HOUR + 1)); END_MIN=$((END_MIN - 60)); fi
# Handle midnight rollover (e.g., 23:30 + 90min = 01:00 next day)
if [ $END_HOUR -ge 24 ]; then
  END_HOUR=$((END_HOUR - 24))
  EVENT_DATE_END=$(TZ="$USER_TIMEZONE" date -d "${EVENT_DATE_RESOLVED} + 1 day" +%Y-%m-%d)
else
  EVENT_DATE_END="${EVENT_DATE_RESOLVED}"
fi
EVENT_END="${EVENT_DATE_END}T$(printf '%02d:%02d' $END_HOUR $END_MIN):00"

JSON_PAYLOAD=$(jq -n \
  --arg title "$EVENT_TITLE" \
  --arg desc "$EVENT_DESCRIPTION" \
  --arg loc "$EVENT_LOCATION" \
  --arg start "$EVENT_START" \
  --arg end "$EVENT_END" \
  --arg tz "$USER_TIMEZONE" \
  --arg reqid "img-$(date +%s)-$RANDOM" \
  '{
    summary: $title,
    description: $desc,
    location: $loc,
    start: {dateTime: $start, timeZone: $tz},
    end: {dateTime: $end, timeZone: $tz},
    conferenceData: {
      createRequest: {
        requestId: $reqid,
        conferenceSolutionKey: {type: "hangoutsMeet"}
      }
    }
  }')

RESPONSE=$(curl -s -X POST \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$JSON_PAYLOAD" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?conferenceDataVersion=1")

ERROR=$(echo "$RESPONSE" | jq -r '.error.message // empty')
if [ -n "$ERROR" ]; then
  echo "❌ Failed to create event: $ERROR"
  exit 1
fi

CREATED_TITLE=$(echo "$RESPONSE" | jq -r '.summary')
CREATED_START=$(echo "$RESPONSE" | jq -r '.start.dateTime')
MEET_LINK=$(echo "$RESPONSE" | jq -r '.conferenceData.entryPoints[]? | select(.entryPointType=="video") | .uri' 2>/dev/null)
EVENT_LINK=$(echo "$RESPONSE" | jq -r '.htmlLink')

echo "✅ Calendar event '${CREATED_TITLE}' created for ${CREATED_START}"
if [ -n "$EVENT_LOCATION" ]; then
  echo "📍 Location: ${EVENT_LOCATION}"
fi
if [ -n "$MEET_LINK" ] && [ "$MEET_LINK" != "null" ]; then
  echo "📹 Google Meet link: ${MEET_LINK}"
else
  echo "📅 Calendar link: ${EVENT_LINK}"
fi
echo "If any details are wrong, just tell me and I'll fix it."
```
</operation>

<response_formatting>
## 🎯 Response Formatting for Image Actions

Follow the One-Turn PVE pattern in EVERY response:

1. **DESCRIBE first**: "I can see your image — it shows..." (brief, 1 sentence)
2. **Action + result**: "✅ Image sent to sarah@example.com" or "✅ Event created for March 20"
3. **Correction offer**: "If any details are wrong, just tell me and I'll fix it." (for calendar/reminder actions)
4. **Handle failures**: "⚠️ I couldn't access/read the image. Could you resend it?" or "Could you tell me [missing detail]?"
5. **Multi-image**: If multiple images, process the first one and ask about the rest.
</response_formatting>

<rules priority="critical">
## 🚨 CRITICAL RULES

1. **VALIDATE FIRST** — Always run the URL validation before downloading or processing. Expired URLs crash the flow.
2. **DESCRIBE THEN ACT** — Tell the user what you see, then perform the action, all in one response. Never act silently.
3. **IMAGE URLs are in the context** — Look for `[Attached Images]` section in the message.
4. **TWILIO URLs expire in ~2 hours** — Process images immediately, don't defer.
5. **ASK if recipient is ambiguous** — "Send this" without specifying TO WHOM → ask for email.
6. **ASK if event details are unclear** — Don't guess dates or times from blurry text. Ask the user.
7. **NEVER hallucinate image content** — If you can't clearly see/read the image, say so.
8. **DOWNLOAD before embedding** — Always `curl -sL <url>` to download and base64-encode for Gmail attachments.
9. **CHECK download succeeded** — If IMAGE_BASE64 is empty after download, the URL likely expired. Tell the user.
10. **EXECUTE the bash commands** — DO NOT just describe or acknowledge — ACTUALLY RUN THEM.
</rules>
