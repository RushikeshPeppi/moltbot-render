---
name: reminders
description: Reminders and scheduled notifications - remind me, set reminder, create reminder, remind tomorrow, remind at, set alarm, notify me, reminder list, show reminders, my reminders, update reminder, change reminder, modify reminder, cancel reminder, delete reminder, stop reminder, recurring reminder, daily reminder, weekly reminder, monthly reminder, remind me to, don't let me forget, alert me
user-invocable: true
metadata: {"openclaw": {"emoji": "⏰"}}
---

# Reminders API
Base: `$FASTAPI_URL/api/v1/reminders/` | User: `$MOLTBOT_USER_ID` | TZ: `$USER_TIMEZONE`

Critical: message MUST be user's **exact words**. If the user didn't say what to be reminded about, ASK — never invent. Local time only (no `-u`, no `Z`). recurrence: `none|daily|weekdays|weekly|monthly`.

## CREATE — one bash call, fill MESSAGE/DATE_EXPR/TIME_PART then run
```bash
MESSAGE="<exact words from user>"
DATE_EXPR="<tomorrow|today|next Monday|2026-05-01|+5 minutes|+2 hours>"
TIME_PART="<HH:MM in 24h, e.g. 14:00 — leave empty if DATE_EXPR is already relative like '+2 hours'>"
RECURRENCE="none"   # or daily|weekdays|weekly|monthly

# Pick ONE of these two trigger_at lines:
TRIGGER_AT=$(TZ="$USER_TIMEZONE" date -d "${DATE_EXPR}" +%Y-%m-%dT%H:%M:%S)              # relative
TRIGGER_AT="$(TZ="$USER_TIMEZONE" date -d "${DATE_EXPR}" +%Y-%m-%d)T${TIME_PART}:00"     # specific time

RESP=$(curl -sS -X POST "$FASTAPI_URL/api/v1/reminders/create" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg u "$MOLTBOT_USER_ID" --arg m "$MESSAGE" --arg t "$TRIGGER_AT" \
        --arg tz "$USER_TIMEZONE" --arg r "$RECURRENCE" \
        '{user_id:$u,message:$m,trigger_at:$t,user_timezone:$tz,recurrence:$r}')")
ID=$(echo "$RESP" | jq -r '.data.id // empty')
[ -n "$ID" ] && echo "⏰ Reminder #$ID set: $MESSAGE at $TRIGGER_AT" || echo "$RESP"
```
For RECURRING reminders just set `RECURRENCE` to `daily`/`weekdays`/`weekly`/`monthly` — same template, no separate API.

## TIME NORMALIZATION (always convert to `HH:MM` 24-hour BEFORE building trigger_at)
- "2pm" / "2 PM" / "2:00pm" / "2:00 p.m." → `14:00`
- "9am" / "9 a.m." / "9:00 AM" → `09:00`
- "18:00" / "6 PM" → `18:00`
- "0700" / "0700hrs" → `07:00` (4-digit military: split first 2 = hours, last 2 = mins)
- "7.30" / "7:30" → `07:30` (replace dot with colon, zero-pad hour)
- "noon" / "midday" / "12" alone → `12:00`; "midnight" → `00:00`
- "morning" → `09:00`; "afternoon" → `14:00`; "evening" → `18:00`; "night" → `21:00`
- "quarter past 7" → `07:15`; "half past 3" → `15:30`; "quarter to 5" → `16:45`
- "in 30 minutes" / "in 2 hours" → `TRIGGER_AT=$(TZ="$USER_TIMEZONE" date -d "+30 minutes" +%Y-%m-%dT%H:%M:%S)` (skip TIME_PART path)
- **Bare hour with no AM/PM** ("at 7", "8 o'clock"): 1–6 → PM; 7–11 → AM; 12 → noon. Override if context says "tonight"/"evening" (→ PM) or "morning"/"wake" (→ AM).
- If genuinely unclear: ASK ("Did you mean 7 AM or 7 PM?") — do NOT silently pick.

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
