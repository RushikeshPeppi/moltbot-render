# Moltbot API — Peppi Integration Guide

> **Base URL:** `https://moltbot-fastapi.onrender.com`  
> **Endpoint:** `POST /api/v1/execute-action`  
> **Content-Type:** `application/json`

---

## The Only Endpoint You Need

```
POST https://moltbot-fastapi.onrender.com/api/v1/execute-action
```

Everything goes through this single endpoint — calendar, email, reminders, image processing, chat. The AI agent figures out what to do based on the message.

---

## Request Format

```json
{
  "user_id": "string",
  "message": "string",
  "timezone": "string",
  "image_urls": ["string"] | null,
  "num_media": 0
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_id` | string | ✅ | Peppi user ID. Must exist in `tbl_clawdbot_users`. |
| `message` | string | ✅ | User's SMS text, exactly as received from Twilio. Don't modify it. |
| `timezone` | string | ✅ | IANA timezone — e.g., `"Asia/Kolkata"`, `"America/New_York"`. **Not** `"IST"` or `"+05:30"`. |
| `image_urls` | string[] | ❌ | Twilio media URLs when user sends MMS. Omit or pass `null` for text-only. |
| `num_media` | int | ❌ | Number of Twilio media attachments. Defaults to `0`. |

> [!IMPORTANT]
> - **Do NOT send `credentials`** — we auto-fetch and auto-refresh Google OAuth tokens from our DB.
> - **Do NOT send `history`** — we have our own history tracking. Sending chat history overloads the agent with unnecessary context and increases token cost.
> - **Do NOT send `phone_number`** — reserved for future use, currently unused.

---

## Response Format

```json
{
  "code": 200,
  "message": "Action executed successfully",
  "data": {
    "session_id": "sess_abc123",
    "response": "✅ Meeting 'Team Standup' scheduled for tomorrow at 3:00 PM. Meet link: https://meet.google.com/abc-defg-hij",
    "action_performed": "chat",
    "tokens_used": 1523,
    "input_tokens": 1200,
    "output_tokens": 323,
    "cache_read": 800,
    "cache_write": 200,
    "reminder_trigger_at": null
  },
  "error": null,
  "exception": null,
  "timestamp": "2026-04-21T12:00:00"
}
```

### What to use from the response

| Field | What to do with it |
|-------|-------------------|
| `data.response` | **Send this back to user as SMS.** This is the AI's reply. |
| `data.tokens_used` | Log for cost tracking (optional). |
| `data.reminder_trigger_at` | ISO timestamp if a reminder was just created (optional, for UI countdown). |
| `code` | HTTP-style status code. `200` = success. |
| `error` | Non-null if something went wrong. |

**TL;DR:** Send 3 fields in → get `data.response` out → send it as SMS.

---

## All Request Examples

### 1. Simple Chat / Question

```json
{
  "user_id": "123",
  "message": "What's the weather like today?",
  "timezone": "Asia/Kolkata"
}
```

---

### 2. Create Calendar Event

```json
{
  "user_id": "123",
  "message": "Schedule a meeting with the design team tomorrow at 3pm",
  "timezone": "Asia/Kolkata"
}
```

---

### 3. Create Event with Google Meet

```json
{
  "user_id": "123",
  "message": "Set up a meeting with raj@example.com tomorrow at 2pm with Google Meet",
  "timezone": "Asia/Kolkata"
}
```

---

### 4. One-Time Reminder

```json
{
  "user_id": "123",
  "message": "Remind me to call the dentist tomorrow at 9am",
  "timezone": "Asia/Kolkata"
}
```

---

### 5. Recurring Reminder

```json
{
  "user_id": "123",
  "message": "Remind me to take medicine every day at 8am",
  "timezone": "Asia/Kolkata"
}
```

---

### 6. Send Email

```json
{
  "user_id": "123",
  "message": "Send an email to boss@company.com saying I'll be late today",
  "timezone": "Asia/Kolkata"
}
```

---

### 7. Check Inbox

```json
{
  "user_id": "123",
  "message": "Check my inbox for unread emails",
  "timezone": "Asia/Kolkata"
}
```

---

### 8. Image → Calendar Event (MMS)

User sends a photo of an event poster + text:

```json
{
  "user_id": "123",
  "message": "Add this to my calendar",
  "timezone": "Asia/Kolkata",
  "image_urls": [
    "https://api.twilio.com/2010-04-01/Accounts/ACxxx/Messages/MMxxx/Media/MExxxyyy"
  ],
  "num_media": 1
}
```

---

### 9. Image → Reminder (MMS)

User sends a photo of a bill + text:

```json
{
  "user_id": "123",
  "message": "Remind me to pay this bill",
  "timezone": "Asia/Kolkata",
  "image_urls": [
    "https://api.twilio.com/2010-04-01/Accounts/ACxxx/Messages/MMxxx/Media/MExxxyyy"
  ],
  "num_media": 1
}
```

---

### 10. Image → Email (MMS)

User sends a photo + asks to email it:

```json
{
  "user_id": "123",
  "message": "Send this to marketing@company.com",
  "timezone": "Asia/Kolkata",
  "image_urls": [
    "https://api.twilio.com/2010-04-01/Accounts/ACxxx/Messages/MMxxx/Media/MExxxyyy"
  ],
  "num_media": 1
}
```

---

### 11. Multiple Images (MMS)

```json
{
  "user_id": "123",
  "message": "Add all these events to my calendar",
  "timezone": "Asia/Kolkata",
  "image_urls": [
    "https://api.twilio.com/.../Media/ME001",
    "https://api.twilio.com/.../Media/ME002"
  ],
  "num_media": 2
}
```

---

### 12. List / Search

```json
{"user_id": "123", "message": "What's on my calendar today?", "timezone": "Asia/Kolkata"}
{"user_id": "123", "message": "What meetings do I have this week?", "timezone": "Asia/Kolkata"}
{"user_id": "123", "message": "Show my reminders", "timezone": "Asia/Kolkata"}
```

---

### 13. Update / Cancel

```json
{"user_id": "123", "message": "Move my 3pm meeting to 5pm", "timezone": "Asia/Kolkata"}
{"user_id": "123", "message": "Cancel my meeting tomorrow", "timezone": "Asia/Kolkata"}
{"user_id": "123", "message": "Cancel my dentist reminder", "timezone": "Asia/Kolkata"}
```

---

### 14. All Time Formats That Work

The user can say time in any format — the agent normalizes it:

| User says | Agent interprets |
|-----------|-----------------|
| "3pm" / "3 PM" / "3:00pm" | 15:00 |
| "15:00" / "1500" / "1500hrs" | 15:00 |
| "3" / "at 3" / "3 o'clock" | 15:00 (PM for 1-6, AM for 7-11) |
| "3.30" / "3:30" / "330" | 15:30 |
| "half past 3" | 15:30 |
| "quarter to 5" | 16:45 |
| "noon" / "midday" | 12:00 |
| "midnight" | 00:00 |
| "morning" | 09:00 |
| "evening" | 18:00 |

### 15. All Date Formats That Work

| User says | Agent interprets |
|-----------|-----------------|
| "tomorrow" | Next day in user's timezone |
| "Monday" / "next Monday" | Next upcoming Monday |
| "March 25" / "25th March" | 2026-03-25 |
| "25th" (no month) | Next upcoming 25th |
| "in 2 days" | Today + 2 |
| "in 30 minutes" | Now + 30 min |
| "next week" | Next Monday |

---

## Error Responses

### User Not Found (404)

```json
{
  "code": 404,
  "message": "User '999' not found. Please register the user first.",
  "error": "USER_NOT_FOUND"
}
```

**Fix:** User must exist in `tbl_clawdbot_users` before calling execute-action.

### Request Already In Progress (503)

```json
{
  "code": 503,
  "message": "Request already in progress for this user, please wait",
  "error": "USER_LOCKED"
}
```

**Fix:** We enforce one request per user at a time. Wait for the previous request to finish (~5-60s). Don't retry immediately.

### Agent Empty Response (500)

```json
{
  "code": 500,
  "message": "Agent returned an empty response. Please try again.",
  "error": "EMPTY_RESPONSE"
}
```

**Fix:** Safe to retry. Rare — happens when AI model returns incomplete output.

### Google OAuth Expired

No error code — the agent handles this gracefully and tells the user in plain language:

> "I wasn't able to access your calendar — your Google connection may need to be refreshed."

We auto-refresh tokens. If the refresh token itself is dead (user changed password / revoked access), we auto-cleanup and the user needs to re-connect via OAuth.

---

## Integration Checklist

- [ ] Send `user_id`, `message`, `timezone` in every request
- [ ] Use IANA timezone strings (`"Asia/Kolkata"`, NOT `"IST"`)
- [ ] Pass Twilio media URLs in `image_urls` for MMS messages
- [ ] Set HTTP client timeout to **≥ 200 seconds** (complex tasks take 30-60s)
- [ ] Don't send `credentials`, `history`, or `phone_number`
- [ ] Handle `503` by showing "processing, please wait" to user
- [ ] Use `data.response` as the SMS reply text
- [ ] Ensure user exists in DB before first request

---

## Quick Copy-Paste

**Text-only:**
```json
{"user_id": "USER_ID", "message": "USER_SMS_TEXT", "timezone": "Asia/Kolkata"}
```

**With image:**
```json
{"user_id": "USER_ID", "message": "USER_SMS_TEXT", "timezone": "Asia/Kolkata", "image_urls": ["TWILIO_MEDIA_URL"], "num_media": 1}
```

**Extract SMS reply:**
```
response.data.response → send as SMS
```
