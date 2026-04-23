# Moltbot — OpenClaw HTTP Gateway Migration Plan

**Status:** proposal, pre-implementation
**Owner:** Rushikesh
**Reviewer:** codex
**Last updated:** 2026-04-23

---

## 0. TL;DR

We are migrating the OpenClaw integration from "fork a CLI process per request" to "talk to a long-lived OpenClaw gateway daemon over HTTP". This is the right call for scale, latency, observability, and future skill features — but it has **one hard coupling** (per-request OAuth tokens) that needs deliberate work, and **one operational change** (a second long-lived process inside the Render container).

**Strategy:** branch off `main` into `feat/http-gateway`, stand up parallel staging services on Render pointing at that branch, port the change behind a feature flag, run the existing 193-scenario suite as the safety net, cut over only when staging is green.

**Estimated work:** 3–4 focused engineering days + 1 week soak in staging.

**Risk to prod:** zero — the `main` branch and live services stay untouched until cut-over.

---

## 1. Why we're doing this (recap so codex can audit)̨

Today, [moltbot-gateway/server.js:264](moltbot-gateway/server.js#L264) calls `spawn('openclaw', args, { env: { ...extraEnv } })` for every `/execute` request. Each turn pays:

- ~3–8s Node fork + OpenClaw boot + Anthropic SDK init + skill-file disk reads,
- full process teardown after the response,
- no in-process state (token cache, rate limiter, request coalescing) survives between turns,
- output parsing relies on substring scraping (`stdout.indexOf('{')` at [server.js:311](moltbot-gateway/server.js#L311)), which is brittle to OpenClaw version bumps.

The persistent gateway gives us:

- **One warm process** holding skill schemas, tool registry, model client — boot cost paid once at deploy.
- **A real HTTP contract** (`POST /v1/responses` or `/v1/chat/completions`) with stable OpenAI-compatible JSON instead of a CLI's stdout.
- **A place to add cross-cutting concerns** (in-process LRU caches, circuit breakers, structured logs per session, admission control under load).
- **Cheaper p99** under bursty traffic — no per-request fork tax.

What it does **not** materially improve: Anthropic's server-side prompt cache. We're already at ~99.9% hit rate ([test_results.json](tests/results/test_results.json), scenario L3: `cache_read=163975 / input=164054`). That's an Anthropic-side cache, not OpenClaw's, and switching transports doesn't change it.

---

## 2. Render branch hosting — exactly how we'll do this

### 2.1 What Render actually supports (researched, with sources)

- **One service ↔ one branch.** From [Render Deploys docs](https://render.com/docs/deploys): "As part of creating a service on Render, you link a branch of your GitHub/GitLab/Bitbucket repo." A single service cannot follow multiple branches.
- **For a parallel staging deploy** of a non-`main` branch, you create a **separate service** (paid at the same plan rate). Confirmed in Render community: ["Best Practices for Dev Branch"](https://community.render.com/t/best-practices-for-dev-branch/837).
- **Preview Environments** ([Render Preview Environments docs](https://render.com/docs/preview-environments)) automatically clone the entire blueprint per PR. Important constraints:
  - Requires **Professional plan or higher** (we have Pro ✅).
  - Billed by the second at the same rate as production.
  - Variables marked `sync: false` in `render.yaml` are **NOT** copied — you must re-supply them via env groups or `previewValue`.
  - Disks are not first-class in preview docs; assume not provisioned.
  - Auto-destroyed when the PR merges or closes.

### 2.2 Our chosen approach

We will use **dedicated staging services** for this migration, not Preview Environments, because:

1. We need them to live for ~1 week of soak, not just for an open PR.
2. We need real OAuth / Redis / Supabase secrets injected (`sync: false` in render.yaml — these would NOT auto-copy into a preview).
3. The OpenClaw gateway needs a persistent disk (`/root/.openclaw`, see [moltbot-gateway/render.yaml:13-15](moltbot-gateway/render.yaml#L13-L15)) — preview disks are not guaranteed.
4. We want stable URLs to point the test runner at.

**Concrete services to create on Render:**

| Service name | Branch | Plan | Notes |
|---|---|---|---|
| `moltbot-fastapi-staging` | `feat/http-gateway` | Pro (same as prod) | Same env vars as prod but pointed at the staging gateway |
| `openclaw-gateway-staging` | `feat/http-gateway` | Pro | New disk: `openclaw-data-staging` |
| `peppi-playground-staging` | `feat/http-gateway` | static (free) | optional, for visual smoke tests |

`searxng` is shared — both prod and staging can hit the existing instance.

**Cost impact:** roughly +$50/month for the duration of staging (two Pro web services). Tear them down after cut-over.

### 2.3 Mechanics

```bash
# Create the branch from current main
git checkout -b feat/http-gateway main
git push -u origin feat/http-gateway

# In Render dashboard:
# 1. New > Web Service > pick repo > select branch "feat/http-gateway"
# 2. Name it "openclaw-gateway-staging"
# 3. Copy env vars from prod openclaw-gateway, override OPENCLAW_HTTP_MODE=true
# 4. Repeat for moltbot-fastapi-staging, override MOLTBOT_GATEWAY_URL to staging URL
```

Render will auto-redeploy the staging services on every push to `feat/http-gateway`. Prod (`main`) stays frozen.

---

## 3. OpenClaw HTTP — what we'll actually use

### 3.1 Endpoint choice

The gateway exposes (researched, sources at the end):

| Endpoint | Use case | Verdict |
|---|---|---|
| `POST /v1/chat/completions` | OpenAI-shape, single-shot, easy migration target | ✅ acceptable, simpler |
| `POST /v1/responses` | OpenAI Responses-shape, supports `previous_response_id`, returns `function_call` items, more agentic | ✅ better long-term — picks this up properly |
| `POST /tools/invoke` | Direct tool call | ❌ not needed, agent handles tools |
| WebSocket | Real-time channel multiplex | ❌ overkill for our request/response pattern |

**Decision:** start with `/v1/chat/completions` (smallest delta from current code) for the cut-over, plan a follow-up to switch to `/v1/responses` once the migration is stable and we want session continuity.

### 3.2 Request shape (chat-completions, what we'll send)

```bash
POST http://127.0.0.1:18789/v1/chat/completions
Authorization: Bearer ${OPENCLAW_GATEWAY_TOKEN}
Content-Type: application/json
x-openclaw-agent-id: main

{
  "model": "openclaw",
  "messages": [
    {"role": "system", "content": "<built context — capabilities, history>"},
    {"role": "user",   "content": "<user message + [Attached Images] block>"}
  ]
}
```

Agent selection per [OpenClaw OpenAI HTTP docs](https://docs.openclaw.ai/gateway/openai-http-api): `"model": "openclaw:main"` OR header `x-openclaw-agent-id: main`. We'll use the header — keeps `model` field clean and matches OpenAI conventions.

### 3.3 Response shape (what we'll parse)

OpenAI-compatible:

```json
{
  "id": "chatcmpl-...",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "..."},
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 164054,
    "completion_tokens": 40,
    "total_tokens": 164094,
    "prompt_tokens_details": {
      "cached_tokens": 163975
    }
  }
}
```

Mapping to current `routes.py` fields:

| Current field (gateway → wrapper) | Source in OpenAI shape |
|---|---|
| `response` | `choices[0].message.content` |
| `tokens_used` | `usage.total_tokens` |
| `input_tokens` | `usage.prompt_tokens` |
| `output_tokens` | `usage.completion_tokens` |
| `cache_read` | `usage.prompt_tokens_details.cached_tokens` |
| `cache_write` | ⚠️ **not exposed** in the OpenAI-compat shape — the cache still works, we just lose the metric |
| `action_type` | not returned — default to `"chat"` |

**Loss to accept:** the `cache_write` count. The cache itself still works (Anthropic still writes; we just can't observe the write). I think that's an acceptable trade — we still see hit rate via `cached_tokens / prompt_tokens`.

### 3.4 Auth

`Authorization: Bearer <token>`. The token is generated by `openclaw onboard` (`ogt_…` prefix) or set via `gateway.auth.mode` config. Since the gateway runs **inside the same container** as `server.js`, traffic is loopback-only (`127.0.0.1`) — Render's firewall doesn't expose port 18789 to the public internet. Per [OpenClaw security docs](https://docs.openclaw.ai/gateway/security), loopback can be configured to bypass auth. **We will still set a token** — defence in depth, and it costs nothing.

### 3.5 The OAuth env-var problem (the hard one)

Today every Google skill uses `$GOOGLE_ACCESS_TOKEN` set by the spawn's per-request `env`. With a persistent gateway, the env is fixed at gateway boot — we cannot mutate it per HTTP request.

Confirmed via [OpenResponses HTTP docs](https://docs.openclaw.ai/gateway/openresponses-http-api): the only per-request context handles are `user`, `x-openclaw-session-key`, `x-openclaw-account-id`, `x-openclaw-message-channel`. **No per-request env var injection.**

**Affected skills (audited):**

- [moltbot-gateway/skills/google-workspace/SKILL.md](moltbot-gateway/skills/google-workspace/SKILL.md) — 50+ uses of `$GOOGLE_ACCESS_TOKEN`
- [moltbot-gateway/skills/image-workspace/SKILL.md](moltbot-gateway/skills/image-workspace/SKILL.md) — 8 uses
- [moltbot-gateway/skills/reminders/SKILL.md](moltbot-gateway/skills/reminders/SKILL.md) — uses `$FASTAPI_URL`, `$MOLTBOT_USER_ID`, `$USER_TIMEZONE` (these are fine — they're per-deploy/per-user-static)
- [moltbot-gateway/skills/image-reminders/SKILL.md](moltbot-gateway/skills/image-reminders/SKILL.md) — same pattern as reminders

`$GOOGLE_ACCESS_TOKEN` is the only env var that varies per request. `$MOLTBOT_USER_ID`, `$USER_TIMEZONE` also vary — they're currently injected via spawn env. Same problem.

**Solution: add a loopback-only token broker endpoint inside `server.js`.**

Add `GET http://127.0.0.1:8788/internal/context/:session_id` returning:

```json
{
  "google_access_token": "ya29....",
  "user_id": "usr_84e773f8",
  "user_timezone": "Asia/Kolkata",
  "fastapi_url": "https://moltbot-fastapi.onrender.com"
}
```

`server.js` stores per-request context in an in-memory map keyed by `session_id` (or by a fresh UUID per turn) for the duration of the request. The map entry is deleted when the response finishes.

**Skill changes required** — change every `$GOOGLE_ACCESS_TOKEN` to:

```bash
CTX=$(curl -s "http://127.0.0.1:8788/internal/context/${OPENCLAW_SESSION_ID}")
GOOGLE_ACCESS_TOKEN=$(echo "$CTX" | jq -r '.google_access_token')
```

`$OPENCLAW_SESSION_ID` is set as a real (gateway-startup) env var to a sentinel and then overridden via the `user` field of the chat-completions request — OpenClaw exposes `user` to skills via its session context. **Verification needed in Phase 0** — see open questions.

If `user` propagation doesn't work, fallback: pass the session_id inside a hidden line at the top of the user message (`__SESSION_ID__: abc123`) and have skills extract it. Uglier but bulletproof.

**Scope of skill rewrite:**

- 4 skill files
- ~60 `$GOOGLE_ACCESS_TOKEN` occurrences (mostly `Authorization: Bearer $GOOGLE_ACCESS_TOKEN`)
- ~10 `$MOLTBOT_USER_ID` and `$USER_TIMEZONE` occurrences
- Estimated 2 hours per skill including tests = 1 day total

**Important property:** this skill change is **independent of the HTTP migration**. We can ship it on the spawn path first (skills fetch context via HTTP, but server.js still spawns), test that all 193 scenarios still pass, then swap the transport. That's the de-risking trick — the two changes are decoupled even though they look entangled.

---

## 4. The 5 hard problems and exact solutions

| # | Problem | Solution | Risk if we skip |
|---|---|---|---|
| 1 | Per-request OAuth env vars | Loopback context broker (§3.5) | Skills fail to authenticate, 100% Google action failure |
| 2 | Two long-lived processes inside one Render container | `server.js` spawns `openclaw gateway run` as child at startup, polls `/health`, treats child exit as fatal (`process.exit(1)` → Render restarts) | Gateway dies silently, requests hang for 280s timeout |
| 3 | Response shape change | New parser for OpenAI shape; fallback to old parser behind feature flag | Empty responses, EMPTY_RESPONSE 500s |
| 4 | Lost `cache_write` metric | Document the loss, show `cached_tokens` as the hit-rate signal in any future dashboards | Telemetry gap, no functional impact |
| 5 | Per-request cancellation | None — gateway has no documented cancel endpoint. Accept that wrapper-side timeout means the gateway keeps working but client sees fallback. | Memory bloat under bursty traffic with abandoned clients |

---

## 5. Code-level change list (file by file)

### 5.1 New / modified files

| File | Change | Estimated LOC |
|---|---|---|
| `moltbot-gateway/server.js` | Add `bootGateway()`, `executeViaHttp()`, context broker endpoint | +180 / -10 |
| `moltbot-gateway/skills/google-workspace/SKILL.md` | Replace env reads with HTTP context fetch | ~50 line edits |
| `moltbot-gateway/skills/image-workspace/SKILL.md` | Same | ~10 line edits |
| `moltbot-gateway/skills/reminders/SKILL.md` | Same | ~15 line edits |
| `moltbot-gateway/skills/image-reminders/SKILL.md` | Same | ~12 line edits |
| `moltbot-gateway/render.yaml` (root [render.yaml](render.yaml)) | Add `OPENCLAW_HTTP_MODE` env, `OPENCLAW_GATEWAY_TOKEN` (sync:false) | +6 |
| `moltbot-gateway/package.json` | No change (axios already there) | 0 |
| `fastapi-wrapper/app/core/moltbot_client.py` | No change — still POSTs to gateway's `/execute` | 0 |
| `fastapi-wrapper/app/api/routes.py` | No change — gateway translates response shape internally | 0 |
| `tests/run_tests.py` | Add a `--target staging` flag pointing to the staging FastAPI URL | +10 |

### 5.2 server.js — the meat

```javascript
// New: boot the gateway as a child of this process
let gatewayChild = null;
let gatewayReady = false;

async function bootGateway() {
  if (process.env.OPENCLAW_HTTP_MODE !== 'true') return;

  console.log('[bootGateway] Starting openclaw gateway daemon...');
  gatewayChild = spawn('openclaw', ['gateway', 'run', '--port', '18789'], {
    env: {
      ...process.env,
      OPENCLAW_HEADLESS: 'true',
      // Set fixed env that's truly cross-request:
      FASTAPI_URL: process.env.FASTAPI_URL,
      // Static skill helpers (NOT user-specific)
      INTERNAL_CONTEXT_URL: 'http://127.0.0.1:8788/internal/context',
    },
    stdio: 'inherit',
  });

  gatewayChild.on('exit', (code) => {
    console.error(`[bootGateway] gateway exited (code ${code}) — restarting service`);
    process.exit(1); // Render restarts the whole container
  });

  // Poll /health
  for (let i = 0; i < 60; i++) {
    try {
      await axios.get('http://127.0.0.1:18789/health', { timeout: 1000 });
      gatewayReady = true;
      console.log('[bootGateway] gateway is ready');
      return;
    } catch (e) { /* not yet */ }
    await new Promise(r => setTimeout(r, 1000));
  }
  throw new Error('Gateway failed to become ready in 60s');
}

// In-memory per-request context (for the loopback broker)
const sessionContext = new Map();

app.get('/internal/context/:sessionId', (req, res) => {
  // Loopback only — defence in depth
  if (req.ip !== '127.0.0.1' && req.ip !== '::1' && req.ip !== '::ffff:127.0.0.1') {
    return res.status(403).json({ error: 'forbidden' });
  }
  const ctx = sessionContext.get(req.params.sessionId);
  if (!ctx) return res.status(404).json({ error: 'unknown session' });
  res.json(ctx);
});

// New executor — talks to the daemon
async function executeViaHttp(sessionId, message, context, credentials, userId, timezone, imageUrls) {
  // Stash per-request context for skill bash to retrieve
  sessionContext.set(sessionId, {
    google_access_token: credentials?.google_access_token || null,
    user_id: userId,
    user_timezone: timezone,
    fastapi_url: process.env.FASTAPI_URL,
  });

  try {
    let userMessage = message;
    if (imageUrls?.length) {
      userMessage += '\n\n[Attached Images]\n' +
        imageUrls.map((u, i) => `Image ${i+1}: ${u}`).join('\n');
    }

    const resp = await axios.post(
      'http://127.0.0.1:18789/v1/chat/completions',
      {
        model: 'openclaw',
        messages: [
          { role: 'system', content: context },
          { role: 'user',   content: userMessage },
        ],
        user: sessionId, // OpenClaw exposes this to skills as $OPENCLAW_USER
      },
      {
        headers: {
          'Authorization': `Bearer ${process.env.OPENCLAW_GATEWAY_TOKEN}`,
          'x-openclaw-agent-id': 'main',
          'x-openclaw-session-key': sessionId,
        },
        timeout: imageUrls?.length ? 260000 : 180000,
      }
    );

    const choice = resp.data.choices?.[0];
    const usage  = resp.data.usage || {};
    return {
      response: choice?.message?.content || '',
      action_type: 'chat',
      details: null,
      tokens_used:   usage.total_tokens || 0,
      input_tokens:  usage.prompt_tokens || 0,
      output_tokens: usage.completion_tokens || 0,
      cache_read:    usage.prompt_tokens_details?.cached_tokens || 0,
      cache_write:   0, // not exposed by OpenAI-compat
    };
  } finally {
    sessionContext.delete(sessionId);
  }
}

// Existing /execute handler picks executor based on flag
const executor = process.env.OPENCLAW_HTTP_MODE === 'true' ? executeViaHttp : executeOpenClaw;
const result = await executor(session_id, effectiveMessage, context, enhancedCredentials, user_id, timezone || 'UTC', image_urls);
```

### 5.3 Skill change pattern (one-time)

Every skill block that currently reads:

```bash
curl -s -H "Authorization: Bearer $GOOGLE_ACCESS_TOKEN" ...
```

Becomes (one block at the top of each skill operation):

```bash
# Resolve per-request context (set by gateway loopback broker)
CTX=$(curl -s "${INTERNAL_CONTEXT_URL}/${OPENCLAW_USER}")
GOOGLE_ACCESS_TOKEN=$(echo "$CTX" | jq -r '.google_access_token')
MOLTBOT_USER_ID=$(echo "$CTX" | jq -r '.user_id')
USER_TIMEZONE=$(echo "$CTX" | jq -r '.user_timezone')
FASTAPI_URL=$(echo "$CTX" | jq -r '.fastapi_url')
```

Then existing `$GOOGLE_ACCESS_TOKEN` references work unchanged.

`$OPENCLAW_USER` is set by OpenClaw based on the `user` field in the request (verified per [OpenResponses docs](https://docs.openclaw.ai/gateway/openresponses-http-api): `"user": stable session routing`). **Phase 0 must verify** this is exposed to skill bash.

---

## 6. Phased rollout (the actual sequence)

### Phase 0 — Local spike (½ day, no code in repo)

Goal: kill the two unknowns before touching production code.

- [ ] Install `openclaw@2026.3.8` locally, run `openclaw gateway run --port 18789`.
- [ ] `curl` it with `/v1/chat/completions`, agent header `main`, confirm response shape matches §3.3.
- [ ] Write a throwaway skill that reads `$OPENCLAW_USER` and curls a local http server. Confirm the `user` field round-trips into skill bash.
- [ ] If `user` doesn't propagate → fall back to embedding `__SESSION_ID__: <id>` in the user message (skills extract via `grep`). Document which path won.

**Ship gate for Phase 1:** both unknowns answered in writing.

### Phase 1 — Branch + staging stand-up (½ day)

- [ ] `git checkout -b feat/http-gateway main`
- [ ] Push branch.
- [ ] Render dashboard: create `openclaw-gateway-staging` and `moltbot-fastapi-staging` services pointing at `feat/http-gateway`. Copy all `sync:false` env vars from prod.
- [ ] Verify staging deploys cleanly with **zero code changes** (sanity check that the new services boot the same code as prod).
- [ ] Run the 193-scenario suite against staging URLs to establish a baseline. Should match the 187/193 we have on prod.

**Ship gate for Phase 2:** staging matches prod baseline exactly.

### Phase 2 — Skill OAuth refactor (1 day)

Done **on `feat/http-gateway` branch, still using the spawn path** — completely independent of HTTP migration.

- [ ] Add the loopback context broker endpoint to `server.js`.
- [ ] Modify `executeOpenClaw()` to populate `sessionContext` map AND continue to set spawn env (belt and suspenders during this phase).
- [ ] Rewrite all 4 skills to read context via HTTP.
- [ ] Push, let staging redeploy.
- [ ] Run 193-scenario suite against staging. **Must still be 187/193.**

**Ship gate for Phase 3:** skill refactor is invisible to the test suite.

### Phase 3 — HTTP executor behind a flag (1 day)

- [ ] Implement `bootGateway()` and `executeViaHttp()` in `server.js`.
- [ ] Add `OPENCLAW_HTTP_MODE` env var to staging only.
- [ ] Push, let staging redeploy. Confirm `bootGateway()` log line on startup.
- [ ] Run 193-scenario suite against staging.
- [ ] Investigate any deltas vs the spawn-path baseline. Common expected deltas: `cache_write` field is now 0 (acceptable), `action_type` is always "chat" (acceptable — wrapper already accepts it).

**Ship gate for Phase 4:** staging green, p50/p95 latency tracked.

### Phase 4 — Soak (3–5 days)

- [ ] Manually exercise the staging playground for several days.
- [ ] Watch staging Render logs for: gateway crashes, OOMs, OAuth failures, response empties.
- [ ] Run the suite daily.

**Ship gate for cut-over:** zero regressions for 3+ days.

### Phase 5 — Cut-over (½ day)

- [ ] Merge `feat/http-gateway` into `main`.
- [ ] **Do not** flip `OPENCLAW_HTTP_MODE=true` on prod yet. Prod redeploys with the new code but still on spawn (flag default is false).
- [ ] Run 193-scenario suite against prod. Must still be 187/193 baseline (spawn path unchanged).
- [ ] Flip `OPENCLAW_HTTP_MODE=true` on prod. Watch first 30 minutes of logs.
- [ ] Run the suite again. Confirm parity with staging.

**Rollback:** flip `OPENCLAW_HTTP_MODE=false` and restart. Spawn path is preserved in the merged code for one full week before deletion.

### Phase 6 — Cleanup (1 day, the week after)

- [ ] Delete spawn path from `server.js`.
- [ ] Delete staging services from Render.
- [ ] Update `API_USAGE.md` with new architecture.
- [ ] Optionally migrate from `/v1/chat/completions` to `/v1/responses` for proper session continuity.

---

## 7. Test strategy

Our 193-scenario suite ([tests/scenarios.py](tests/scenarios.py), [tests/run_tests.py](tests/run_tests.py)) is the safety net. Two things to add:

### 7.1 `--target` flag on the runner

```python
# tests/run_tests.py
parser.add_argument("--target", default="prod",
                    choices=["prod", "staging"],
                    help="Which deployment to test against")
TARGETS = {
    "prod":    "https://moltbot-fastapi.onrender.com/api/v1",
    "staging": "https://moltbot-fastapi-staging.onrender.com/api/v1",
}
```

This lets us run staging and prod independently and compare `test_results.json` files.

### 7.2 Baseline diff

After each phase, save `test_results.json` as `test_results.<phase>.json` and diff against the previous baseline. Anything that changes from `pass` → `fail` is an immediate stop-the-line.

### 7.3 What the suite catches vs misses

**Catches:** functional regressions in skills (calendar, gmail, reminders), timeout regressions, response-shape parsing bugs, OAuth failures.

**Misses:** memory leaks (need to watch Render metrics), p99 latency under load (need separate load test), gateway crash recovery (need manual chaos test — `kill -9` the gateway child and confirm Render restarts the service).

For Phase 4 soak, plan a 10-minute load test with `hey` or `wrk` against staging to surface anything the suite misses.

---

## 8. Risks I have not solved + open questions

These need answers before / during Phase 0:

1. **Does OpenClaw expose the `user` field to skill bash as `$OPENCLAW_USER`?** Documented as a session-routing input but not as a skill-visible env var. **Verify in Phase 0.** If no → use the message-embedded session ID fallback.

2. **Does `openclaw gateway run` write its admin token to `~/.openclaw/openclaw.json` on first start, or does it require `openclaw onboard` first?** If onboard is required, the Render build command needs `npm install -g openclaw && openclaw onboard --headless`. This may need a deploy hook.

3. **Does the gateway respect the existing `~/.openclaw/openclaw.json` config (model selection, exec permissions) we already write at startup?** Should — the config path is the same — but worth verifying that `bootGateway()` doesn't race with the config-writing code.

4. **What happens to the 5-min Anthropic prompt cache when multiple users hit the gateway concurrently?** The cache is keyed by exact prompt prefix. SOUL.md + agent.md + skills are identical across users → cache hits. The per-user context block diverges → that part is uncached. This should be fine, but if cache hit rate drops in staging vs prod, we need to investigate — perhaps reorder the system prompt so the per-user bit is at the end.

5. **Render Pro CPU/RAM limits with two long-lived Node processes inside one container.** Pro plan gives ~2 GB RAM. OpenClaw gateway + Express + skill child processes — could push it. Watch memory in Phase 4. If we hit the wall: bump to a higher plan, or split into two services (which we've already rejected for cost reasons but is the fallback).

6. **Cold start.** The gateway needs ~5–15s to boot. Render's `healthCheckPath: /health` is on `server.js`'s health, not the gateway. We need `server.js` to **NOT report healthy** until `gatewayReady === true`, otherwise Render may route traffic before the gateway is up. Edit:

   ```javascript
   app.get('/health', (req, res) => {
     if (process.env.OPENCLAW_HTTP_MODE === 'true' && !gatewayReady) {
       return res.status(503).json({ status: 'starting' });
     }
     res.json({ status: 'online', service: 'openclaw-gateway', openclaw_ready: isReady });
   });
   ```

---

## 9. Honest assurances

What I can guarantee:

- The spawn path stays in the code through Phase 5 — at any point pre-cleanup, flipping `OPENCLAW_HTTP_MODE=false` reverts to current behavior with no rollback work.
- `main` branch is untouched until Phase 5 — staging risk is fully isolated.
- The 193-scenario suite is run at every phase boundary — any regression blocks the next phase.

What I cannot guarantee:

- That every one of 193 scenarios still passes after the HTTP cut-over without **some** investigation. Realistic expectation: 1–3 scenarios will reveal subtle differences (e.g., `cache_write` becomes 0, an empty assistant message handled differently). Each will need ~30 min to triage.
- That there are no OpenClaw HTTP behaviors not covered in the public docs. We will discover edge cases. That's what staging soak is for.

What you should not let me hand-wave:

- Any phase showing a regression is a STOP. We don't roll forward "to see if it gets better." We diagnose first.
- The skill OAuth refactor (Phase 2) **must** pass the suite cleanly on the spawn path before we even attempt Phase 3. If it doesn't, the HTTP migration is paused and we fix the skill change first — they're decoupled and that's the whole point.

---

## 10. Cost summary

| Item | One-time | Recurring |
|---|---|---|
| 2 staging Render Pro web services | $0 | ~$50/month for ~2 weeks → ~$25 total |
| Engineering time | 3–4 days | — |
| Anthropic tokens for running suite ~5 times in staging | ~$5–10 | — |
| **Total** | **~$35** | **$0 after cut-over** |

---

## 11. What changes for codex review

When this lands, codex will see:

- A new branch `feat/http-gateway` and a PR diff.
- One large `server.js` change (the executor + bootstrap + broker).
- 4 skill diffs (mechanical search-and-replace pattern).
- One `render.yaml` env-var addition.
- `tests/run_tests.py` `--target` flag.
- This file (`HTTP_MIGRATION_PLAN.md`) as the design doc.

Things codex should specifically check:
- That `sessionContext.delete(sessionId)` is in a `finally` block — leaks here = OAuth tokens stuck in memory.
- That the `/internal/context/` endpoint enforces loopback IP — leaks here = OAuth tokens exfiltratable.
- That the gateway child process exit triggers `process.exit(1)` — silent gateway death = 280s hangs.
- That the health check refuses traffic until `gatewayReady === true`.
- That every skill change preserves the existing `Authorization: Bearer $GOOGLE_ACCESS_TOKEN` semantics — easy to typo a curl flag.

---

## 12. Sources

OpenClaw HTTP gateway:
- [OpenClaw OpenAI HTTP API docs](https://docs.openclaw.ai/gateway/openai-http-api)
- [OpenClaw OpenResponses HTTP API docs](https://docs.openclaw.ai/gateway/openresponses-http-api)
- [OpenClaw tools/invoke HTTP API docs](https://docs.openclaw.ai/gateway/tools-invoke-http-api)
- [OpenClaw security & auth docs](https://docs.openclaw.ai/gateway/security)
- [OpenClaw agent CLI docs](https://docs.openclaw.ai/cli/agent)
- [OpenClaw npm package](https://www.npmjs.com/package/openclaw)
- [Meta Intelligence: Gateway setup, start/stop, remote mode](https://www.meta-intelligence.tech/en/insight-openclaw-gateway)
- [DextraLabs: How to run OpenClaw (terminal, daemon, TUI, cloud)](https://dextralabs.com/blog/how-to-run-openclaw/)

Render branch deploys & preview environments:
- [Render Deploys docs](https://render.com/docs/deploys)
- [Render Preview Environments docs](https://render.com/docs/preview-environments)
- [Render Service Previews docs](https://render.com/docs/service-previews)
- [Render community: best practices for dev branch](https://community.render.com/t/best-practices-for-dev-branch/837)
- [Render community: separate staging vs production](https://community.render.com/t/whats-the-best-practice-for-have-a-separate-staging-and-production-environment/338)

Repo cross-references:
- [moltbot-gateway/server.js](moltbot-gateway/server.js)
- [moltbot-gateway/render.yaml](moltbot-gateway/render.yaml)
- [moltbot-gateway/package.json](moltbot-gateway/package.json)
- [moltbot-gateway/skills/google-workspace/SKILL.md](moltbot-gateway/skills/google-workspace/SKILL.md)
- [moltbot-gateway/skills/image-workspace/SKILL.md](moltbot-gateway/skills/image-workspace/SKILL.md)
- [moltbot-gateway/skills/reminders/SKILL.md](moltbot-gateway/skills/reminders/SKILL.md)
- [moltbot-gateway/skills/image-reminders/SKILL.md](moltbot-gateway/skills/image-reminders/SKILL.md)
- [fastapi-wrapper/app/api/routes.py](fastapi-wrapper/app/api/routes.py)
- [fastapi-wrapper/app/core/moltbot_client.py](fastapi-wrapper/app/core/moltbot_client.py)
- [fastapi-wrapper/app/config.py](fastapi-wrapper/app/config.py)
- [tests/scenarios.py](tests/scenarios.py)
- [tests/run_tests.py](tests/run_tests.py)
- [tests/results/test_results.json](tests/results/test_results.json) — 187/193 baseline
- [render.yaml](render.yaml) — root blueprint
