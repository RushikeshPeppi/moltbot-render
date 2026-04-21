# Image-Aware Reminders Skill

Extends the `reminders` skill with image handling capabilities for Peppi SMS users.

## What This Skill Does

Handles scenarios where users send images alongside reminder requests via SMS (Twilio MMS):

- **Reminder from content**: "Remind me about this" + 📸 shopping list → extracts items as reminder
- **Reminder from schedule**: "Remind me of these times" + 📸 timetable → creates multiple reminders
- **Reminder from bill**: "Remind me to pay this" + 📸 invoice → extracts amount + due date

## How Images Arrive

Twilio MMS images are passed as public URLs appended to the message:
```
[Attached Images]
Image 1: https://api.twilio.com/2010-04-01/...
```

## Requirements

- Claude Sonnet 4.6 (vision-capable model) for reading image content
- `$FASTAPI_URL` for reminder API calls
- `$MOLTBOT_USER_ID` for user identification
- `$USER_TIMEZONE` for correct scheduling

## Operations

| Operation | Trigger | Actions |
|-----------|---------|---------|
| `validate_image_url` | Always runs first | HEAD request → check HTTP 200 |
| `reminder_from_image` | "Remind me about this" + 📸 | Describe → Extract content → Check duplicates → Create reminder |
| `reminder_from_schedule_image` | "Remind me of these times" + 📸 | Describe → Extract entries → Create one reminder per entry |
| `reminder_from_bill` | "Remind me to pay this" + 📸 | Describe → Extract bill details → Check duplicates → Create payment reminder |

## Pattern: One-Turn PVE

All operations follow the **describe-then-act** pattern: the agent tells the user what it sees in the image, creates the reminder, and offers correction — all in one SMS response.

## Security

- Never includes sensitive data (card numbers, account numbers, passwords) in reminder messages
- Reminder messages are kept under 160 characters for SMS delivery
- Duplicate detection checks for existing similar reminders before creating

