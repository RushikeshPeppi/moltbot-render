# Image-Aware Google Workspace Skill

Extends the `google-workspace` skill with image handling capabilities for Peppi SMS users.

## What This Skill Does

Handles scenarios where users send images alongside Google Workspace action requests via SMS (Twilio MMS):

- **Email with image**: "Send this photo to sarah@example.com"
- **Describe and email**: "What's in this picture? Forward it to John"
- **Calendar from image**: "Add this event to my calendar" (image of a poster/invite)

## How Images Arrive

Twilio MMS images are passed as public URLs appended to the message:
```
[Attached Images]
Image 1: https://api.twilio.com/2010-04-01/...
```

## Requirements

- Claude Sonnet 4.6 (vision-capable model) for image understanding
- `$GOOGLE_ACCESS_TOKEN` for Gmail/Calendar API calls
- Twilio image URLs are valid for ~2 hours

## Operations

| Operation | Trigger | Actions |
|-----------|---------|---------|
| `validate_image_url` | Always runs first | HEAD request → check HTTP 200 + content-type is image |
| `email_with_image` | "Send this to John" + 📸 | Describe → Download image → MIME encode → Gmail send |
| `describe_and_email` | "What's this? Email it to..." + 📸 | Vision describe → Compose → Gmail send |
| `calendar_from_image` | "Add this to my calendar" + 📸 | Describe → Extract event details → Calendar create → Offer correction |

## Pattern: One-Turn PVE

All operations follow the **describe-then-act** pattern: the agent tells the user what it sees in the image, performs the action, and offers correction — all in one SMS response.
