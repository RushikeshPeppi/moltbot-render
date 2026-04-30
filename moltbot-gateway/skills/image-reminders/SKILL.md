---
name: image-reminders
description: Image-based reminders — set reminder from image, remind me about this picture, save this image as reminder, remind with photo, screenshot reminder, image note reminder, remember this image, remind me about what's in this photo, remind me to pay this bill, payment reminder from receipt. Do NOT use for text-only reminders without images, listing existing reminders, or cancelling reminders.
user-invocable: true
metadata: {"openclaw": {"emoji": "📸⏰"}}
---

# Image Reminders
Use when: `[Attached Images]` present + reminder intent. Takes priority over `<reminder_protocol>`.
Env: `$FASTAPI_URL`, `$MOLTBOT_USER_ID`, `$USER_TIMEZONE`

**ALWAYS**: validate URL → describe image → execute → confirm (One-Turn PVE pattern).
**NEVER** hallucinate image content. **NEVER** guess times — ask if not specified.

## VALIDATE URL (run before every image operation)
```bash
IMAGE_URL="<from [Attached Images] in message>"
HTTP=$(curl -sI -o /dev/null -w "%{http_code}" -L "$IMAGE_URL")
[ "$HTTP" != "200" ] && echo "⚠️ Image expired (HTTP $HTTP). Could you resend it?" && exit 0
```

## EXTRACTION TEMPLATES BY IMAGE TYPE
Use these as a starting point for `REMINDER_MESSAGE`. Trim to ≤160 chars.
- **Shopping list** → `"Buy: milk, eggs, bread, butter, cheese"` (top 5–8 items, then "...")
- **Bill / invoice** → `"Pay <payee> — <amount> (due <date>)"` (never include card/account numbers)
- **Event poster** → `"<event title> at <venue> — <date> <time>"`
- **Whiteboard / notes** → `"<topic>: <key bullet 1>, <bullet 2>, …"` (top 3 bullets)
- **Prescription** → `"Take <medicine_name> <dosage>"` (no pharmacy / Rx number)
- **Receipt** → `"Submit expense: <merchant> — <amount> on <date>"`
- **Screenshot of message** → core actionable line, attribution if relevant ("Reply to <person>: <gist>")

## CREATE REMINDER FROM IMAGE
1. **DESCRIBE**: "I can see [content]." (1 sentence using vision)
2. **ASK** if user didn't specify WHEN: "When would you like to be reminded about this?" (never default to random time)
3. **EXECUTE** — message must be ≤160 chars (SMS limit):
```bash
REMINDER_MESSAGE="<extracted content, max 160 chars — summarize if needed>"
# Specific time:  TRIGGER_AT="$(TZ="$USER_TIMEZONE" date -d "${DATE_PART}" +%Y-%m-%d)T${TIME_PART}:00"
# Relative time:  TRIGGER_AT=$(TZ="$USER_TIMEZONE" date -d "+N hours" +%Y-%m-%dT%H:%M:%S)
RESP=$(curl -sS -X POST "$FASTAPI_URL/api/v1/reminders/create" -H "Content-Type: application/json" \
  -d "$(jq -n --arg u "$MOLTBOT_USER_ID" --arg m "$REMINDER_MESSAGE" --arg t "$TRIGGER_AT" \
    --arg tz "$USER_TIMEZONE" --arg r "none" \
    '{user_id:$u,message:$m,trigger_at:$t,user_timezone:$tz,recurrence:$r}')")
ID=$(echo "$RESP" | jq -r '.data.id // empty')
[ -n "$ID" ] && echo "✅ Reminder set: '${REMINDER_MESSAGE}' for ${TRIGGER_AT}" || echo "$RESP"
```
4. **CONFIRM**: "If the details aren't right, just tell me."

## BILL / PAYMENT REMINDER
Extract from image: PAYEE, AMOUNT, DUE_DATE (if visible).
- **Never** include account/card numbers in message.
- Message: `"Pay ${PAYEE} — ${AMOUNT}"` or `"Pay ${PAYEE} — ${AMOUNT} (due ${DUE_DATE})"` (≤160 chars)
- If DUE_DATE visible: `TRIGGER_AT` = 2 days before at 09:00 local time
  ```bash
  TARGET_DATE=$(TZ="$USER_TIMEZONE" date -d "${DUE_DATE} -2 days" +%Y-%m-%d)
  TRIGGER_AT="${TARGET_DATE}T09:00:00"
  ```
- If DUE_DATE missing: ask "When is this due?" instead of guessing

## SCHEDULE IMAGE (multiple reminders from timetable/class schedule)
- One `curl` call PER entry — never use bash arrays or loops over curl
- recurrence: `weekly` for recurring classes, `none` for one-time events
- Confirm each: "✅ Reminder: [title] — [day] at [time] ([recurrence])"
- Example per-entry pattern:
```bash
TARGET_DATE=$(TZ="$USER_TIMEZONE" date -d "next monday" +%Y-%m-%d)
RESP=$(curl -s -X POST "$FASTAPI_URL/api/v1/reminders/create" -H "Content-Type: application/json" \
  -d "$(jq -n --arg u "$MOLTBOT_USER_ID" --arg m "CLASS_TITLE" --arg t "${TARGET_DATE}T09:00:00" \
    --arg tz "$USER_TIMEZONE" --arg r "weekly" \
    '{user_id:$u,message:$m,trigger_at:$t,user_timezone:$tz,recurrence:$r}')")
echo "$RESP" | jq -r 'if .data.id then "✅ Reminder set" else "❌ \(.message)" end'
```

## DUPLICATE CHECK (optional, for ambiguous repeats like "remind me to pay this again")
```bash
EXISTING=$(curl -s "$FASTAPI_URL/api/v1/reminders/list/$MOLTBOT_USER_ID?status=pending")
DUP=$(echo "$EXISTING" | jq -r --arg m "$REMINDER_MESSAGE" \
  '.data.reminders[]? | select(.message | ascii_downcase | contains($m | ascii_downcase)) | .id' | head -1)
[ -n "$DUP" ] && [ "$DUP" != "null" ] && echo "📝 Note: similar reminder #$DUP already exists. Creating new one anyway."
```

For LIST/CANCEL/UPDATE: use reminders/SKILL.md.

## COMPLEX FLOWS (compound multi-skill operations)

1. **"This bill + remind me 2 days before AND email it to my wife"**
   - Validate URL → extract PAYEE/AMOUNT/DUE_DATE → POST `/reminders/create` (DUE-2 days at 09:00) → use image-workspace MIME flow to email wife with image inline + body "Bill: $PAYEE — $AMOUNT due $DUE_DATE". Confirm both actions.

2. **"This shopping list + remind me when I'm at the store at 6pm"**
   - Validate URL → vision: extract items → REMINDER_MESSAGE="Buy: $items" (≤160 chars, summarize if longer) → TRIGGER_AT today 18:00 (or whatever time user says) → POST `/reminders/create`.

3. **"This timetable + create reminders AND calendar events for each class"**
   - Validate URL → vision: extract each row's title/day/time → for each: POST `/reminders/create` (recurrence=weekly) AND calendar create with `recurrence:["RRULE:FREQ=WEEKLY"]`. Confirm count of both: "✅ Set 5 reminders + 5 weekly events."

4. **"This prescription + remind me daily at 9pm to take it AND email my doctor a photo"**
   - Validate URL → extract MED_NAME → POST `/reminders/create` recurrence=daily at 21:00 message "Take $MED_NAME" → use image-workspace MIME flow to email doctor with image + body "Just confirming this is the prescription".

5. **"This event poster + add to calendar AND remind me 1 day before"**
   - Validate URL → vision: extract TITLE/DATE/TIME/LOCATION → calendar create (use `<calendar_protocol>` with location) → POST `/reminders/create` at (DATE - 1 day) 09:00 message "Tomorrow: $TITLE at $LOCATION".
