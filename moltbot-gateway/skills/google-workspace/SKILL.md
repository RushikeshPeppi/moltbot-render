---
name: google-workspace
description: Google Calendar and Gmail - list events, view calendar, check schedule, show meetings, get appointments, create/update/delete events, read/send emails, check inbox, search emails, recent messages, unread emails, send message, compose email, find messages, email search, reply to email, respond to message, answer email
user-invocable: true
metadata: {"openclaw": {"emoji": "📧"}}
---

# Google Workspace — Calendar + Gmail
Token: `$GOOGLE_ACCESS_TOKEN` | TZ: `$USER_TIMEZONE`

**CREATE/LIST calendar and SEND/LIST email**: Use `<calendar_protocol>` and `<gmail_protocol>` from agent context — they have inline templates.
This file covers UPDATE, DELETE, and complex Gmail operations.

---

## TIMEZONE RULES (CRITICAL — applies to all operations)
- **CREATE/UPDATE events**: pass LOCAL time + `timeZone` field. Never convert to UTC yourself.
  `EVENT_DATE=$(TZ="$USER_TIMEZONE" date -d "tomorrow" +%Y-%m-%d)` then `"${EVENT_DATE}T14:00:00"` with `timeZone: $USER_TIMEZONE`
- **LIST queries** (timeMin/timeMax): need UTC. Use epoch approach:
  `EPOCH=$(TZ="$USER_TIMEZONE" date -d "today 00:00:00" +%s)` → `date -u -d "@${EPOCH}" +%Y-%m-%dT%H:%M:%SZ`
- **Time ambiguity**: 1-6 no AM/PM → PM; 7-11 → AM; 12 → noon
- **API date arithmetic**: strip offset colon: `date -d "$(echo $T | sed 's/+\([0-9][0-9]\):\([0-9][0-9]\)$/+\1\2/')" +%s`

---

## CALENDAR

### LIST EVENTS
```bash
# Today / tomorrow / this week — adjust START/END_EPOCH
START_EPOCH=$(TZ="$USER_TIMEZONE" date -d "today 00:00:00" +%s)
END_EPOCH=$(TZ="$USER_TIMEZONE" date -d "today 23:59:59" +%s)
TIME_MIN=$(date -u -d "@${START_EPOCH}" +%Y-%m-%dT%H:%M:%SZ)
TIME_MAX=$(date -u -d "@${END_EPOCH}" +%Y-%m-%dT%H:%M:%SZ)
curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=${TIME_MIN}&timeMax=${TIME_MAX}&singleEvents=true&orderBy=startTime" \
  | jq -r '.items[] | "📅 \(.summary) at \(.start.dateTime // .start.date)"'
# Next N events: use &maxResults=N&timeMin=NOW_UTC (no timeMax)
# Search by keyword: add &q=KEYWORD
```

### CREATE EVENT (always include conferenceDataVersion=1 for Meet link)
```bash
EVENT_DATE=$(TZ="$USER_TIMEZONE" date -d "${DATE_PART}" +%Y-%m-%d)
EVENT_START="${EVENT_DATE}T${TIME_PART}:00"
END_HOUR=$(( ${TIME_PART%%:*} + DURATION_MIN / 60 )); END_MIN=$(( ${TIME_PART##*:} + DURATION_MIN % 60 ))
if [ $END_MIN -ge 60 ]; then END_HOUR=$((END_HOUR + 1)); END_MIN=$((END_MIN - 60)); fi
if [ $END_HOUR -ge 24 ]; then END_HOUR=$((END_HOUR - 24)); END_DATE=$(TZ="$USER_TIMEZONE" date -d "${EVENT_DATE} + 1 day" +%Y-%m-%d); else END_DATE="${EVENT_DATE}"; fi
EVENT_END="${END_DATE}T$(printf '%02d:%02d' $END_HOUR $END_MIN):00"
REQ_ID=$(cat /proc/sys/kernel/random/uuid 2>/dev/null || echo "meet-$(date +%s)-$RANDOM")
JSON=$(jq -n --arg t "$TITLE" --arg s "$EVENT_START" --arg e "$EVENT_END" --arg tz "$USER_TIMEZONE" --arg r "$REQ_ID" \
  '{summary:$t,start:{dateTime:$s,timeZone:$tz},end:{dateTime:$e,timeZone:$tz},conferenceData:{createRequest:{requestId:$r,conferenceSolutionKey:{type:"hangoutsMeet"}}}}')
# Add attendee: JSON=$(echo "$JSON" | jq --arg em "$EMAIL" '. + {attendees:[{email:$em}]}')
# Add location: JSON=$(echo "$JSON" | jq --arg l "$LOC" '. + {location:$l}')
RESP=$(curl -s -X POST -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d "$JSON" "https://www.googleapis.com/calendar/v3/calendars/primary/events?conferenceDataVersion=1")
MEET=$(echo "$RESP" | jq -r '.conferenceData.entryPoints[]? | select(.entryPointType=="video") | .uri' 2>/dev/null)
echo "✅ '${TITLE}' created for ${EVENT_START}"
[ -n "$MEET" ] && [ "$MEET" != "null" ] && echo "📹 Meet: ${MEET}"
```

### UPDATE EVENT — search first, fetch full event, PUT
```bash
# Step 1: Search (use time window OR keyword — pick based on what user described)
# Option A — by time (±15 min window):
SEARCH_EPOCH=$(TZ="$USER_TIMEZONE" date -d "${SEARCH_DATE} ${SEARCH_TIME}" +%s)
TIME_MIN=$(date -u -d "@$((SEARCH_EPOCH - 900))" +%Y-%m-%dT%H:%M:%SZ)
TIME_MAX=$(date -u -d "@$((SEARCH_EPOCH + 900))" +%Y-%m-%dT%H:%M:%SZ)
SEARCH_RESP=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=${TIME_MIN}&timeMax=${TIME_MAX}&singleEvents=true&orderBy=startTime")
# Option B — by keyword:
NOW_UTC=$(date -u -d "@$(TZ="$USER_TIMEZONE" date +%s)" +%Y-%m-%dT%H:%M:%SZ)
SEARCH_RESP=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?q=${QUERY}&singleEvents=true&orderBy=startTime&timeMin=${NOW_UTC}")

EVENT_COUNT=$(echo "$SEARCH_RESP" | jq '.items | length')
# 0 → "No matching events found. Be more specific."
# >1 → show list, ask user to clarify: .items[0:5] | .[] | "📅 \(.summary) at \(.start.dateTime)"
# 1 → proceed
EVENT_ID=$(echo "$SEARCH_RESP" | jq -r '.items[0].id')

# Step 2: Fetch full current event (preserves all fields)
CURRENT=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events/${EVENT_ID}")

# Step 3: Build new times (local, no Z)
NEW_DATE_RESOLVED=$(TZ="$USER_TIMEZONE" date -d "${NEW_DATE}" +%Y-%m-%d)
NEW_START="${NEW_DATE_RESOLVED}T${NEW_TIME}:00"
# Preserve duration from current event:
START_EPOCH=$(date -d "$(echo $(echo "$CURRENT" | jq -r '.start.dateTime') | sed 's/+\([0-9][0-9]\):\([0-9][0-9]\)$/+\1\2/')" +%s 2>/dev/null || date -d "$(echo "$CURRENT" | jq -r '.start.dateTime')" +%s)
END_EPOCH=$(date -d "$(echo $(echo "$CURRENT" | jq -r '.end.dateTime') | sed 's/+\([0-9][0-9]\):\([0-9][0-9]\)$/+\1\2/')" +%s 2>/dev/null || date -d "$(echo "$CURRENT" | jq -r '.end.dateTime')" +%s)
DUR_MIN=$(( (END_EPOCH - START_EPOCH) / 60 ))
END_H=$(( ${NEW_TIME%%:*} + DUR_MIN / 60 )); END_M=$(( ${NEW_TIME##*:} + DUR_MIN % 60 ))
if [ $END_M -ge 60 ]; then END_H=$((END_H + 1)); END_M=$((END_M - 60)); fi
if [ $END_H -ge 24 ]; then END_H=$((END_H - 24)); NEW_DATE_END=$(TZ="$USER_TIMEZONE" date -d "${NEW_DATE_RESOLVED} + 1 day" +%Y-%m-%d); else NEW_DATE_END="${NEW_DATE_RESOLVED}"; fi
NEW_END="${NEW_DATE_END}T$(printf '%02d:%02d' $END_H $END_M):00"

# Step 4: PUT (mutate current event to preserve conferenceData, attendees, etc.)
UPDATE=$(echo "$CURRENT" | jq --arg s "$NEW_START" --arg e "$NEW_END" --arg tz "$USER_TIMEZONE" \
  '.start.dateTime=$s | .start.timeZone=$tz | .end.dateTime=$e | .end.timeZone=$tz')
RESP=$(curl -s -X PUT -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d "$UPDATE" "https://www.googleapis.com/calendar/v3/calendars/primary/events/${EVENT_ID}?conferenceDataVersion=1")
MEET=$(echo "$RESP" | jq -r '.conferenceData.entryPoints[]? | select(.entryPointType=="video") | .uri' 2>/dev/null)
echo "✅ Event updated to ${NEW_START}"
[ -n "$MEET" ] && [ "$MEET" != "null" ] && echo "📹 Meet: ${MEET}"
```

### DELETE EVENT
```bash
# Search same as UPDATE (Option A or B), extract EVENT_ID, then:
DELETE_RESP=$(curl -s -w "\n%{http_code}" -X DELETE \
  -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events/${EVENT_ID}")
HTTP_CODE=$(echo "$DELETE_RESP" | tail -1)
[ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ] && echo "✅ Event deleted" || echo "❌ Delete failed (HTTP $HTTP_CODE)"
```

---

## GMAIL

### LIST / SEARCH
Map user phrasing → Gmail query (`q=` URL-encoded):
- "recent" / "inbox" → empty filter, `maxResults=10`
- "unread" → `is:unread`
- "important" → `is:important`
- "starred" → `is:starred`
- "with attachments" → `has:attachment`
- "from John" / "from john@x" → `from:John` (Gmail also matches display names)
- "to Sarah" → `to:sarah@...`
- "about <topic>" → `subject:<topic>` OR plain `<topic>` (Gmail full-text)
- "today" → `after:$(TZ="$USER_TIMEZONE" date -d "today 00:00:00" +%s)`
- "this week" → `after:$(TZ="$USER_TIMEZONE" date -d "monday 00:00:00" +%s)` (or `7d` for last-7-days)
- "last N emails" → empty filter, `maxResults=N`
- Combine with space: `from:john is:unread after:1717200000`

```bash
curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages?q=${FILTER}&maxResults=10" | jq -r '.messages[].id'
# Get full message:    GET /users/me/messages/${ID}?format=full
# Headers + snippet:   GET /users/me/messages/${ID}?format=metadata
# Body of plain-text part (handles single-part and multipart, decodes base64url):
#   curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" "$URL?format=full" \
#     | jq -r '(.payload.parts[]? | select(.mimeType=="text/plain") | .body.data) // .payload.body.data // empty' \
#     | tr '_-' '/+' | base64 -d 2>/dev/null
```

### SEND EMAIL
```bash
# Ask for email address if user only gave a name
EMAIL_CONTENT="From: me
To: ${TO}
Subject: ${SUBJECT}

${BODY}"
ENCODED=$(printf '%s' "$EMAIL_CONTENT" | base64 -w 0 | tr '+/' '-_' | tr -d '=')
curl -s -X POST -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d "{\"raw\": \"$ENCODED\"}" "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
echo "✅ Email sent to ${TO}"
```

### REPLY TO EMAIL
```bash
# Step 1: Get original message
DETAILS=$(curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages/${MSG_ID}?format=metadata")
THREAD_ID=$(echo "$DETAILS" | jq -r '.threadId')
ORIG_FROM=$(echo "$DETAILS" | jq -r '.payload.headers[] | select(.name=="From") | .value')
ORIG_SUBJ=$(echo "$DETAILS" | jq -r '.payload.headers[] | select(.name=="Subject") | .value')
TO_EMAIL=$(echo "$ORIG_FROM" | grep -oP '<\K[^>]+' || echo "$ORIG_FROM")
[[ "$ORIG_SUBJ" == Re:* ]] && REPLY_SUBJ="$ORIG_SUBJ" || REPLY_SUBJ="Re: ${ORIG_SUBJ}"

# Step 2: Send with threadId for proper threading
REPLY_CONTENT="From: me
To: ${TO_EMAIL}
Subject: ${REPLY_SUBJ}
In-Reply-To: ${MSG_ID}
References: ${MSG_ID}

${REPLY_BODY}"
ENCODED=$(printf '%s' "$REPLY_CONTENT" | base64 -w 0 | tr '+/' '-_' | tr -d '=')
curl -s -X POST -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d "{\"raw\": \"$ENCODED\", \"threadId\": \"$THREAD_ID\"}" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
echo "✅ Reply sent to ${TO_EMAIL}"
```

### MARK / LABEL
```bash
# Mark read:   {"removeLabelIds": ["UNREAD"]}
# Mark unread: {"addLabelIds": ["UNREAD"]}
# Star:        {"addLabelIds": ["STARRED"]}
curl -s -X POST -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"ACTION_KEY": ["LABEL"]}' \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages/${MSG_ID}/modify"
```

### DELETE EMAIL
```bash
curl -s -X DELETE -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages/${MSG_ID}"
```

## ERROR CODES
- 401/403: OAuth token issue — inform user Google connection may need refresh
- 400: Malformed payload — fix JSON and retry
- 404: Event/message not found
- 429: Rate limited — wait and retry

## COMPLEX FLOWS (compound multi-skill operations)

1. **"Reply to John's last email saying I'll be at the meeting"**
   - Gmail search `q=from:john maxResults=1` → get message format=metadata → extract `threadId`, `From` (parse email from `Name <email>`), `Subject` → send reply with `In-Reply-To`, `References`, `threadId`. Body = user's words.

2. **"Cancel my 3pm meeting and email each attendee that I'm rescheduling"**
   - Search events around 3pm (±15min window) → fetch full event → save `.attendees[].email` array → DELETE event → loop attendees: send email subject "Meeting cancelled — rescheduling", body "I'll send a new time soon". Confirm both deletion + N emails sent.

3. **"Schedule meeting with Sarah tomorrow 2pm and email her the Meet link"**
   - CREATE event with `attendees:[{email:"sarah@..."}]` + `conferenceDataVersion=1` → extract `MEET` from response → send Gmail to sarah subject "Meeting tomorrow 2pm" body containing `MEET` link. If no email known, ASK first.

4. **"Reschedule my 4pm meeting to 5pm and notify attendees of the change"**
   - Search by time → fetch full event → save attendees + duration → build NEW_START="${DATE}T17:00:00", NEW_END=NEW_START+duration → PUT event preserving conferenceData → send email to each attendee "Rescheduled to 5pm — Meet link unchanged".

5. **"Show me unread emails this week from people I have meetings with"**
   - List this-week events → collect unique attendee emails → for each: Gmail `q="is:unread from:$EMAIL after:$WEEK_EPOCH"` → aggregate results → present grouped by sender.
