---
name: image-workspace
description: Image-based Google Calendar and Gmail actions — send image via email, create event from screenshot, email screenshot, attach image to email, forward image, describe meeting screenshot, image attachment email, share photo via gmail, event from image, schedule from screenshot. Do NOT use for text-only emails, calendar events without images, general photo discussion, or web searches.
user-invocable: true
metadata: {"openclaw": {"emoji": "📸"}}
---

# Image Workspace — Gmail + Calendar with Images
Use when: `[Attached Images]` present + workspace action. Takes priority over calendar/gmail protocols.
Env: `$GOOGLE_ACCESS_TOKEN`, `$USER_TIMEZONE`, `$MOLTBOT_USER_ID`, `$FASTAPI_URL`

**ALWAYS**: validate URL → describe image → execute → confirm. NEVER hallucinate content.

## VALIDATE URL (run before every image operation — Twilio URLs expire in ~2 hours)
```bash
IMAGE_URL="<from [Attached Images] in message>"
HTTP=$(curl -sI -o /dev/null -w "%{http_code}" -L "$IMAGE_URL")
[ "$HTTP" != "200" ] && echo "⚠️ Image expired (HTTP $HTTP). Could you resend it?" && exit 0
CONTENT_TYPE=$(curl -sI -L "$IMAGE_URL" | grep -i 'content-type' | tail -1 | awk '{print $2}' | tr -d '\r')
[ -z "$CONTENT_TYPE" ] && CONTENT_TYPE="image/jpeg"
```

## SEND IMAGE VIA EMAIL
Ask for recipient email if only a name given. Build a MIME multipart message with the image inline.
```bash
# After validation, download and encode:
IMAGE_BASE64=$(curl -sL "$IMAGE_URL" | base64 | tr -d '\n')
[ -z "$IMAGE_BASE64" ] && echo "⚠️ Failed to download image. Could you resend it?" && exit 0

BOUNDARY="boundary_$(date +%s)_peppi"
# Build MIME — use printf to avoid issues with variable expansion in heredoc
MIME_MSG=$(printf 'From: me\nTo: %s\nSubject: %s\nMIME-Version: 1.0\nContent-Type: multipart/mixed; boundary="%s"\n\n--%s\nContent-Type: text/html; charset=utf-8\n\n<html><body><p>%s</p><img src="cid:attached_image" style="max-width:600px;"></body></html>\n--%s\nContent-Type: %s\nContent-Transfer-Encoding: base64\nContent-Disposition: inline; filename="image.jpg"\nContent-ID: <attached_image>\n\n%s\n--%s--' \
  "$RECIPIENT_EMAIL" "${SUBJECT:-Photo shared via Peppi}" "$BOUNDARY" "$BOUNDARY" \
  "${USER_MESSAGE:-Here's an image:}" "$BOUNDARY" "$CONTENT_TYPE" "$IMAGE_BASE64" "$BOUNDARY")
ENCODED=$(printf '%s' "$MIME_MSG" | base64 | tr '+/' '-_' | tr -d '=\n')

RESP=$(curl -s -X POST "https://gmail.googleapis.com/gmail/v1/users/me/messages/send" \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d "{\"raw\": \"${ENCODED}\"}")
ERR=$(echo "$RESP" | jq -r '.error.message // empty')
[ -n "$ERR" ] && echo "❌ Failed: $ERR" || echo "✅ Image sent to ${RECIPIENT_EMAIL}"
```

## CREATE CALENDAR EVENT FROM IMAGE
Use the CREATE template from `<calendar_protocol>` in agent context.
- Extract TITLE, DATE_PART, TIME_PART, DURATION_MIN, LOCATION using vision
- ASK if date or time is unclear — never guess from blurry text
- Add location: `JSON=$(echo "$JSON" | jq --arg l "$LOCATION" '. + {location:$l}')`
- Same `?conferenceDataVersion=1` flag for Meet link

## DESCRIBE IMAGE + EMAIL (compound action)
1. Describe image in 1-2 sentences using vision
2. Use that description as `USER_MESSAGE` in the SEND IMAGE VIA EMAIL template above
3. Confirm: "✅ Image described and sent to ${RECIPIENT_EMAIL}"

## COMPLEX FLOWS (compound multi-skill operations)

1. **"This receipt + email it to accounting AND remind me to file it for taxes"**
   - Validate URL → vision: extract VENDOR/AMOUNT/DATE → MIME email to accountant with image inline + body "Receipt: $VENDOR — $AMOUNT on $DATE" → POST `/reminders/create` next April 1 09:00 message "File receipt: $VENDOR $AMOUNT".

2. **"This whiteboard + email my team with a description of what's on it"**
   - Validate URL → vision: describe content in detail (action items, decisions, diagrams) → MIME email with `USER_MESSAGE`=description + image inline. Recipients: ask user if not given.

3. **"This event poster + add to calendar AND email Sarah the Meet link"**
   - Validate URL → vision: extract TITLE/DATE/TIME/LOCATION → calendar create with `conferenceDataVersion=1` + location → extract MEET from response → send Gmail to sarah subject "$TITLE on $DATE" body including MEET link.

4. **"This screenshot of an email + reply to that email saying X"**
   - Validate URL → vision: extract sender name + subject from screenshot → Gmail search `q=from:$SENDER_EMAIL_OR_NAME` to find original message → reply on threadId with body=user's X. Caveat user if vision-read sender is uncertain.

5. **"This menu + remind me to order at 7pm AND email my partner what I'm getting"**
   - Validate URL → vision: extract DISH user mentions → POST `/reminders/create` today 19:00 message "Order: $DISH" → MIME email to partner with image + body "Thinking of $DISH for dinner".
