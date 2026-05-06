# Peppi gateway eval harness

Twenty scenarios that exercise simple, medium, hard, edge, and image flows
against the deployed gateway. Run before/after every prompt or tool change to
verify direction.

## Run

```bash
cd moltbot-gateway

# Read-only tiers, against prod gateway:
GATEWAY_URL=https://openclaw-gateway-dg3y.onrender.com \
EVAL_USER_ID=<a-user-id-with-google-oauth-set-up> \
EVAL_TIMEZONE=Asia/Kolkata \
EVAL_TIERS=simple,medium,edge \
EVAL_INCLUDE_WRITE=0 \
npx tsx tests/eval/run.ts

# All tiers including writes (creates real reminders/events on EVAL_USER_ID):
EVAL_TIERS=simple,medium,hard,edge npx tsx tests/eval/run.ts
```

## What it measures

Per scenario:
- **expected_tool_calls** — every named tool must appear in the response's
  `_meta.tool_calls` (subset, order-insensitive).
- **must_contain** / **must_not_contain** — case-insensitive regex on the SMS
  reply text.
- **max_iterations** — fail if the agent loop ran more iterations than allowed.
- **max_wall_ms** — fail if wall time exceeded the budget.

Aggregate:
- pass-rate by tier
- avg iterations per call
- avg wall time per call

## Tier definitions

- **simple** — single tool, happy path. Pass-rate target: 100%.
- **medium** — 2-step chains, one list+one act. Target: ≥85%.
- **hard** — enumeration, time-relative, cross-tool with side effects. Target: ≥60%.
- **edge** — bare-hour ambiguity, timezone, identity tests. Target: 100%.
- **image** — MMS attachments. Currently skipped — populate `image_urls` with
  a real Twilio URL to enable.

## Important caveats

1. **Side effects are real.** Write scenarios (`side_effect: "write"`) create
   reminders, calendar events, and emails on the `EVAL_USER_ID` account. Use a
   dedicated test user. Set `EVAL_INCLUDE_WRITE=0` to skip them.

2. **Scoring is on the agent's *decisions*, not on Google API state.** We
   verify the model called the right tools and returned a sensible reply. We
   do NOT poll Calendar/Gmail to confirm the side effect persisted. That's
   intentional — for prompt iteration, the model's choices are the signal.

3. **Image scenarios need a real URL.** Twilio image URLs expire ~2h after
   send. If running image tests, capture a fresh URL and substitute it in
   `scenarios.json` for the `__REPLACE_WITH_TEST_IMAGE_URL__` placeholder.

4. **Don't run from CI yet.** No mocking layer — every run hits live
   Anthropic, SearXNG, Google APIs, and FastAPI. Run manually before deploys.

## Adding scenarios

Append to `scenarios.json`. Each scenario must have:
- `id` (unique, kebab-case)
- `tier` and `side_effect`
- `user_message` (what the SMS user types)
- `expected_tool_calls` (array of tool names)
- `must_contain` (regex on reply)
- `max_iterations` and `max_wall_ms`

Optional: `must_not_contain`, `image_urls`, `skip_reason`.
