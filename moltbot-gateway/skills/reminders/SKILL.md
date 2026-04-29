---
name: reminders
description: Reminders and scheduled notifications - remind me, set reminder, create reminder, remind tomorrow, remind at, set alarm, notify me, reminder list, show reminders, my reminders, update reminder, change reminder, modify reminder, cancel reminder, delete reminder, stop reminder, recurring reminder, daily reminder, weekly reminder, monthly reminder, remind me to, don't let me forget, alert me
user-invocable: true
metadata: {"openclaw": {"emoji": "⏰"}}
---

# Reminders API
Base: `$FASTAPI_URL/api/v1/reminders/` | User: `$MOLTBOT_USER_ID` | TZ: `$USER_TIMEZONE`

**CREATE/RECURRING**: Use `<reminder_protocol>` from agent context — it has the full template.
Critical: message MUST be user's explicit words. Local time only (no -u, no Z). recurrence: none|daily|weekdays|weekly|monthly.

## LIST
```bash
RESP=$(curl -s "${FASTAPI_URL}/api/v1/reminders/list/${MOLTBOT_USER_ID}?status=pending")
echo "$RESP" | jq -r '.data.reminders[] | "⏰ #\(.id): \(.message) — \(.recurrence) at \(.trigger_at)"'
# Display trigger_at in user local time: TZ="$USER_TIMEZONE" date -d "$T" '+%I:%M %p on %b %d'
```

## UPDATE — search first, then POST /update
```bash
# Step 1: List and filter
LIST=$(curl -s "${FASTAPI_URL}/api/v1/reminders/list/${MOLTBOT_USER_ID}?status=pending")
TOTAL=$(echo "$LIST" | jq '.data.total')
[ "$TOTAL" -eq 0 ] && echo "📭 No active reminders." && exit 0

# Filter options (use whichever matches user's description):
# By keyword:    jq -c '.data.reminders[] | select(.message | ascii_downcase | contains("KEYWORD"))'
# By recurrence: jq -c '.data.reminders[] | select(.recurrence == "daily")'
# By time (UTC): jq -c '.data.reminders[] | select(.trigger_at | contains("HH:MM"))'

# 0 matches → show all, ask to clarify
# >1 match  → show matches, ask to clarify
# 1 match   → proceed with REMINDER_ID

# Step 2: Build new trigger_at (local time, no -u, no Z)
TARGET_DATE=$(TZ="$USER_TIMEZONE" date -d "${DATE_PART}" +%Y-%m-%d)
TRIGGER_AT="${TARGET_DATE}T${NEW_TIME}:00"

# Step 3: POST update (include only fields that are changing)
PAYLOAD=$(jq -n --arg uid "$MOLTBOT_USER_ID" --argjson rid $REMINDER_ID \
  '{user_id:$uid,reminder_id:$rid}')
[ -n "$TRIGGER_AT"     ] && PAYLOAD=$(echo "$PAYLOAD" | jq --arg t "$TRIGGER_AT" --arg tz "$USER_TIMEZONE" '. + {trigger_at:$t,user_timezone:$tz}')
[ -n "$NEW_MESSAGE"    ] && PAYLOAD=$(echo "$PAYLOAD" | jq --arg m "$NEW_MESSAGE" '. + {message:$m}')
[ -n "$NEW_RECURRENCE" ] && PAYLOAD=$(echo "$PAYLOAD" | jq --arg r "$NEW_RECURRENCE" '. + {recurrence:$r}')

RESP=$(curl -s -X POST "${FASTAPI_URL}/api/v1/reminders/update" \
  -H "Content-Type: application/json" -d "$PAYLOAD")
echo "$RESP" | jq -r 'if .error then "❌ \(.message)" else "✅ Reminder updated" end'
```

## CANCEL — same search as UPDATE, then POST /cancel
```bash
# Search same as UPDATE Step 1, then:
PAYLOAD=$(jq -n --arg uid "$MOLTBOT_USER_ID" --argjson rid $REMINDER_ID \
  '{user_id:$uid,reminder_id:$rid}')
RESP=$(curl -s -X POST "${FASTAPI_URL}/api/v1/reminders/cancel" \
  -H "Content-Type: application/json" -d "$PAYLOAD")
echo "$RESP" | jq -r 'if .error then "❌ \(.message)" else "✅ Reminder cancelled" end'
```

## CALENDAR AUTO-REMINDERS (set reminders before all upcoming events)
```bash
EVENTS=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=$(date -u +%Y-%m-%dT%H:%M:%SZ)&maxResults=10&singleEvents=true&orderBy=startTime")
# For each event with .start.dateTime:
#   EVENT_EPOCH=$(date -d "$EVENT_TIME" +%s)
#   REMINDER_EPOCH=$((EVENT_EPOCH - 1800))    # 30 min before
#   Skip if REMINDER_EPOCH <= $(date +%s)
#   TRIGGER_AT=$(TZ="$USER_TIMEZONE" date -d "@$REMINDER_EPOCH" +%Y-%m-%dT%H:%M:%S)
#   POST /reminders/create with message "Upcoming: $EVENT_TITLE"
# For all-day events (.start.date only): set reminder at 08:30 on that date
```

## COMPLEX FLOWS (compound multi-skill operations)

1. **"If I have a meeting tomorrow with X, reply 'confirm' to their last email; else remind me at 9am"**
   - List tomorrow events with `q=X`. If 1+ matches: search Gmail `q=from:$X` → fetch threadId → reply with body "Confirming for tomorrow" with `threadId`. If 0 matches: POST `/reminders/create` at tomorrow 09:00.

2. **"Remind me 30min before every meeting today"**
   - List today's events → for each `.start.dateTime`: `EVENT_EPOCH=$(date -d "$T" +%s); R_EPOCH=$((EVENT_EPOCH-1800))` → `TRIGGER_AT=$(TZ=$USER_TIMEZONE date -d "@$R_EPOCH" +%Y-%m-%dT%H:%M:%S)` → POST `/reminders/create` with message "Upcoming: $TITLE". Skip if R_EPOCH ≤ now.

3. **"Cancel my 9am medicine reminder and set it for 10am with same recurrence"**
   - List pending → filter by keyword "medicine" → save `RECURRENCE` → POST `/cancel` → POST `/create` with `TIME_PART="10:00"` and saved recurrence.

4. **"Move all today's reminders to tomorrow same time"**
   - List pending → filter `.trigger_at` starts with today's UTC date → for each: extract HH:MM (UTC), `TARGET=$(TZ=$USER_TIMEZONE date -d "tomorrow" +%Y-%m-%d)`, POST `/update` with new trigger_at preserving original time.

5. **"Remind me to call mom every Sunday at 7pm AND remind me 1hr before"**
   - Two creates back-to-back: weekly at "19:00" + weekly at "18:00", same message "call mom". Confirm both reminder IDs to user.
