# Execute Action Endpoint Guide

## Endpoint

```
POST https://moltbot-fastapi.onrender.com/api/v1/execute-action
```

## Method

`POST` with `Content-Type: application/json`

## Request Body

| Field      | Type   | Required | Description                                      |
|------------|--------|----------|--------------------------------------------------|
| `user_id`  | string | ✅       | Peppi user ID (e.g. `"usr_7b980496"`)            |
| `message`  | string | ✅       | The user's message                               |
| `timezone` | string | ✅       | IANA timezone (e.g. `"America/New_York"`)         |
| `context`  | string | ❌       | Full behavioral rules + conversation history XML  |

## Example Body

```json
{
  "user_id": "usr_7b980496",
  "message": "Can you check my mailbox",
  "timezone": "America/New_York",
  "context": "<rules>\n<primary_identity>\nYou are Lava. Never break character...\n</primary_identity>\n\n<critical_instructions>\nTHE RECENT CONVERSATION ABOVE IS YOUR PRIMARY SOURCE OF TRUTH.\n...\n</critical_instructions>\n\n<messaging_constraints>\nHARD RULE: Keep all responses under 200 tokens...\n</messaging_constraints>\n</rules>\n\n<recent_conversation>\nYour most recent conversation with Marvin Johnson:\nmessage from Marvin Johnson at Feb 28, 2026 at 11:08 PM - i'm just here to get to know you\nmessage from you Lava at Feb 28, 2026 at 11:08 PM - That's cool, I'm down for that...\n</recent_conversation>\n\n<identity>\nName: Lava\nAge: 40\nDOB: 1986-02-28\n...\n</identity>\n\n<persona>\nYOUR MISSION\nYour goal is to build a meaningful relationship...\n</persona>\n\n<user_context>\nName: Marvin Johnson\nAge: 45\nGender: Male\nLocation: New York, New York\n...\n</user_context>\n\n<today_activities>\n...\n</today_activities>\n\n<yesterday_activities>\n...\n</yesterday_activities>\n\n<past_routines>\n...\n</past_routines>\n\n<backstory>\n...\n</backstory>\n\n<memory_note>\nThe recent conversation history above contains our real previous exchanges.\n</memory_note>"
}
```

> **Note:** The `context` field is a single string. All newlines inside it must be escaped as `\n` in JSON. PHP's `json_encode()` and JavaScript's `JSON.stringify()` do this automatically — you do NOT need to manually escape anything.

## Full Context Structure (what goes inside `context`)

The context string is built by Peppi's Laravel backend and contains these XML-tagged sections concatenated together:

```
<rules>           → Personality, tone, messaging constraints, hard limits
<recent_conversation> → Last 25 messages between the user and the bot
<identity>        → Bot's name, age, DOB, gender, location, personality
<persona>         → Full behavioral instructions, relationship guide, texting style
<user_context>    → User's name, age, location, interests, weather, time
<today_activities> → Bot's simulated daily routine (today)
<yesterday_activities> → Bot's simulated daily routine (yesterday)
<past_routines>   → Previous days' routines
<backstory>       → Bot's life story in chunks
<historical_activities> → Older routine context
<memory_note>     → Instructions to treat conversation as real
```

## How to Call from Laravel

```php
use Illuminate\Support\Facades\Http;

$response = Http::timeout(120)->post(
    'https://moltbot-fastapi.onrender.com/api/v1/execute-action',
    [
        'user_id'  => $user->peppi_user_id,       // e.g. "usr_7b980496"
        'message'  => $incomingMessage,             // e.g. "Can you check my mailbox"
        'timezone' => $user->timezone,              // e.g. "America/New_York"
        'context'  => $this->buildContext($user),   // Full XML string built by Peppi
    ]
);

$data = $response->json();

// Response structure:
// $data['code']    → 200 on success
// $data['data']['response']  → The AI's reply text
// $data['data']['action_performed'] → e.g. "gmail_check", "chat"
// $data['data']['tokens_used'] → Token count
```

> **Important:** Laravel's `Http::post()` calls `json_encode()` internally, which automatically escapes all newlines and special characters in the context string. No manual escaping needed.

## Response Example

```json
{
  "code": 200,
  "message": "Action executed successfully",
  "data": {
    "session_id": "sess_abc123",
    "response": "lemme check real quick 📬",
    "action_performed": "gmail_check",
    "tokens_used": 4521,
    "reminder_trigger_at": null
  },
  "error": null,
  "exception": null,
  "timestamp": "2026-03-06T09:42:00Z"
}
```
