# Moltbot API — Peppi Integration Guide

> **Hey Hemang 👋** — This is the only doc you need. One endpoint, one payload structure, every scenario.

---

## Endpoint

```
POST https://moltbot-fastapi.onrender.com/api/v1/execute-action
Content-Type: application/json
```

---

## Payload — Always Send All 5 Fields

Your Laravel backend should always build the **same payload shape**. Every request has the same 5 fields — some are `null` or `0` depending on whether the user sent an image or not.

```json
{
  "user_id": "",
  "message": "",
  "timezone": "",
  "image_urls": null,
  "num_media": 0
}
```

| Field | Type | Always Send? | How Peppi Sets It |
|-------|------|:------------:|-------------------|
| `user_id` | string | ✅ Always | Peppi user ID from your DB. Must exist in `tbl_clawdbot_users`. |
| `message` | string | ✅ Always | The raw SMS text from Twilio `Body` param. Pass as-is, don't modify. |
| `timezone` | string | ✅ Always | User's IANA timezone from your DB (e.g., `"Asia/Kolkata"`). **Not** `"IST"` or `"+05:30"`. |
| `image_urls` | string[] \| null | ✅ Always | If Twilio `NumMedia > 0`, collect the `MediaUrl` values into an array. Otherwise `null`. |
| `num_media` | int | ✅ Always | Twilio's `NumMedia` value. `0` when no images. |

> [!IMPORTANT]
> **Fields you should NOT send** (we handle these internally):
> - ~~`credentials`~~ — We auto-fetch and auto-refresh Google OAuth tokens from our DB.
> - ~~`history`~~ — We have our own history tracking. Sending chat history wastes tokens ($$$) and adds no value.
> - ~~`phone_number`~~ — Reserved for future use, not consumed.

---

## Peppi Backend Logic (Pseudocode)

This is roughly what your Laravel controller should do:

```php
// In your Twilio webhook handler
public function handleSms(Request $request)
{
    $user = User::findByPhone($request->From);

    // Build payload — always the same shape
    $payload = [
        'user_id'    => (string) $user->id,
        'message'    => $request->Body,
        'timezone'   => $user->timezone ?? 'Asia/Kolkata',
        'image_urls' => $request->NumMedia > 0
                        ? collect(range(0, $request->NumMedia - 1))
                            ->map(fn($i) => $request->input("MediaUrl{$i}"))
                            ->toArray()
                        : null,
        'num_media'  => (int) ($request->NumMedia ?? 0),
    ];

    // POST to Moltbot
    $response = Http::timeout(200)
        ->post('https://moltbot-fastapi.onrender.com/api/v1/execute-action', $payload);

    // Send AI response back as SMS
    $smsReply = $response->json('data.response') ?? 'Something went wrong. Please try again.';

    return response()->twilio($smsReply);
}
```

---

## Response — What You Get Back

```json
{
  "code": 200,
  "message": "Action executed successfully",
  "data": {
    "session_id": "sess_abc123",
    "response": "✅ Meeting scheduled for tomorrow at 3:00 PM",
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

**What to use:**
- `data.response` → **Send this as the SMS reply to the user**
- `code` → `200` = success, anything else = error
- `error` → Non-null means something broke

Everything else (`tokens_used`, `session_id`, etc.) is for your internal logging/dashboard — not needed for the SMS flow.

---

## Every Scenario — Full Payloads

### 1. Simple Chat / Question

```json
{
  "user_id": "123",
  "message": "What's the weather like today?",
  "timezone": "Asia/Kolkata",
  "image_urls": null,
  "num_media": 0
}
```

---

### 2. Create Calendar Event

```json
{
  "user_id": "123",
  "message": "Schedule a meeting with the design team tomorrow at 3pm",
  "timezone": "Asia/Kolkata",
  "image_urls": null,
  "num_media": 0
}
```

---

### 3. Create Event with Google Meet + Attendee

```json
{
  "user_id": "123",
  "message": "Set up a meeting with raj@example.com tomorrow at 2pm with Google Meet",
  "timezone": "Asia/Kolkata",
  "image_urls": null,
  "num_media": 0
}
```

---

### 4. One-Time Reminder

```json
{
  "user_id": "123",
  "message": "Remind me to call the dentist tomorrow at 9am",
  "timezone": "Asia/Kolkata",
  "image_urls": null,
  "num_media": 0
}
```

---

### 5. Recurring Reminder

```json
{
  "user_id": "123",
  "message": "Remind me to take medicine every day at 8am",
  "timezone": "Asia/Kolkata",
  "image_urls": null,
  "num_media": 0
}
```

---

### 6. Send Email

```json
{
  "user_id": "123",
  "message": "Send an email to boss@company.com saying I'll be late today",
  "timezone": "Asia/Kolkata",
  "image_urls": null,
  "num_media": 0
}
```

---

### 7. Check Inbox

```json
{
  "user_id": "123",
  "message": "Check my inbox for unread emails",
  "timezone": "Asia/Kolkata",
  "image_urls": null,
  "num_media": 0
}
```

---

### 8. List Calendar / Reminders

```json
{
  "user_id": "123",
  "message": "What's on my calendar today?",
  "timezone": "Asia/Kolkata",
  "image_urls": null,
  "num_media": 0
}
```

---

### 9. Update / Reschedule

```json
{
  "user_id": "123",
  "message": "Move my 3pm meeting to 5pm",
  "timezone": "Asia/Kolkata",
  "image_urls": null,
  "num_media": 0
}
```

---

### 10. Cancel / Delete

```json
{
  "user_id": "123",
  "message": "Cancel my meeting tomorrow",
  "timezone": "Asia/Kolkata",
  "image_urls": null,
  "num_media": 0
}
```

---

### 11. Image → Calendar Event (1 image MMS)

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

### 12. Image → Reminder (1 image MMS)

User sends a photo of a bill:

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

### 13. Image → Email (1 image MMS)

User sends a photo and asks to forward it:

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

### 14. Multiple Images (2+ image MMS)

```json
{
  "user_id": "123",
  "message": "Add all these events to my calendar",
  "timezone": "Asia/Kolkata",
  "image_urls": [
    "https://api.twilio.com/2010-04-01/Accounts/ACxxx/Messages/MMxxx/Media/ME001",
    "https://api.twilio.com/2010-04-01/Accounts/ACxxx/Messages/MMxxx/Media/ME002"
  ],
  "num_media": 2
}
```

---

### 15. Image-Only (No Text, Just Photo)

User sends only a photo with no text — Twilio sends empty `Body`:

```json
{
  "user_id": "123",
  "message": "",
  "timezone": "Asia/Kolkata",
  "image_urls": [
    "https://api.twilio.com/2010-04-01/Accounts/ACxxx/Messages/MMxxx/Media/MExxxyyy"
  ],
  "num_media": 1
}
```

The agent will describe the image and ask: "I can see [description]. What would you like me to do with this?"

---

## Time & Date — All Formats Work

The user can write time/date in any format — the AI handles normalization. You don't need to parse it.

| User writes | AI understands |
|-------------|---------------|
| "3pm" / "3 PM" / "3:00pm" | 15:00 |
| "15:00" / "1500" / "1500hrs" | 15:00 |
| "3" / "at 3" / "3 o'clock" | 15:00 (PM for 1-6, AM for 7-11) |
| "3.30" / "3:30" / "330" | 15:30 |
| "half past 3" / "quarter to 5" | 15:30 / 16:45 |
| "noon" / "midnight" | 12:00 / 00:00 |
| "tomorrow" / "Monday" / "next week" | Resolved in user's timezone |
| "March 25" / "25th" / "in 2 days" | Resolved correctly |

---

## Error Responses

All errors follow the same response shape. Check `code` and `error`:

### User Not Found

```json
{
  "code": 404,
  "message": "User '999' not found. Please register the user first.",
  "data": null,
  "error": "USER_NOT_FOUND",
  "exception": null,
  "timestamp": "2026-04-21T12:00:00"
}
```

### Concurrent Request (User Locked)

```json
{
  "code": 503,
  "message": "Request already in progress for this user, please wait",
  "data": null,
  "error": "USER_LOCKED",
  "exception": null,
  "timestamp": "2026-04-21T12:00:00"
}
```

We allow only 1 request per user at a time. If the user double-taps, show them "Still processing your previous request..."

### Agent Error

```json
{
  "code": 500,
  "message": "Agent returned an empty response. Please try again.",
  "data": null,
  "error": "EMPTY_RESPONSE",
  "exception": "OpenClaw returned empty payloads after 2 attempts",
  "timestamp": "2026-04-21T12:00:00"
}
```

Safe to retry once.

---

## Integration Checklist for Hemang

- [ ] Always send all 5 fields (`user_id`, `message`, `timezone`, `image_urls`, `num_media`)
- [ ] Set `image_urls` to `null` (not `[]`) when there are no images
- [ ] Set `num_media` to `0` (not `null`) when there are no images
- [ ] Use IANA timezone from user profile (`"Asia/Kolkata"`, not `"IST"`)
- [ ] Set HTTP timeout to **≥ 200 seconds** (complex tasks can take 30-60s)
- [ ] Extract `data.response` from the response and send as SMS reply
- [ ] Handle `503` → tell user "processing previous request, please wait"
- [ ] Handle `404` → user needs to be created in `tbl_clawdbot_users` first
- [ ] Handle `500` → retry once, then tell user "something went wrong, try again"
- [ ] Don't send `credentials`, `history`, or `phone_number` fields
