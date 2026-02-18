# Reminders Skill

**OpenClaw skill** for setting, listing, and cancelling reminders via the Moltbot FastAPI backend.

## Features

### One-Time Reminders
- ✅ Set reminders for specific date/time
- ✅ Natural language parsing ("tomorrow at 2pm", "in 30 minutes")
- ✅ Automatic timezone conversion (user's local → UTC)

### Recurring Reminders
- ✅ Daily reminders ("every day at 9am")
- ✅ Weekly reminders ("every Monday at 10am")
- ✅ Monthly reminders ("on the 15th at noon")

### Management
- ✅ List all reminders for a user
- ✅ Filter by status (pending, delivered, cancelled)
- ✅ Cancel any reminder

## How It Works

1. User says "Remind me tomorrow at 2pm to buy milk"
2. AI agent activates this skill
3. Skill calls `POST $FASTAPI_URL/api/v1/reminders/create`
4. FastAPI saves to Supabase and schedules via QStash
5. QStash fires a webhook when time arrives
6. FastAPI receives webhook and calls Peppi to send SMS
7. User gets: "⏰ Reminder: Buy milk!"

## Requirements

- `$FASTAPI_URL` — Moltbot FastAPI backend URL (auto-set)
- `$MOLTBOT_USER_ID` — Current user's ID (auto-set)
- `$USER_TIMEZONE` — User's timezone (auto-set)
- curl and jq available on the system

## Author

Custom skill for Moltbot-Render project
