# Moltbot — End-to-End Audit & Hardening Plan

**Status:** in-progress, live notes as I read
**Branch:** `feat/http-gateway`
**Author:** senior-engineering audit
**Scope:** every file in moltbot-render/, including the HTTP migration just landed on this branch

---

## 0. Reading methodology (so a reviewer can trust this)

- Every file is read top-to-bottom, not grep'd for keywords.
- Observations are captured during the read, not after — so I don't summarize away a real flaw as "minor."
- For every flaw I flag: (a) what it is, (b) why it matters, (c) how bad, (d) concrete fix.
- Severity tiers: **P0** = correctness/security bug that will bite in prod, **P1** = scalability/reliability cliff, **P2** = sharp edge or code-quality debt, **P3** = nit.
- At the end: compared against industry patterns (OAuth brokers, long-lived multi-tenant agent servers, OpenClaw production deployments) with sources.

---

## 1. FastAPI wrapper — `app/core/*`

Read in full: `database.py` (651), `session_manager.py` (248), `credential_manager.py` (284), `redis_client.py` (363).

### 1.1 `redis_client.py`

- **P0 — Lock release without ownership token.** `acquire_lock` sets `SET NX EX 30`; `release_lock` does a blind `DEL`. Classic Redlock pitfall: lock expires mid-agent-turn (agent turns can hit 260s for image flows, lock is 30s), a second request acquires it, then the first request finishes and DELs it — now the second request has no lock but thinks it does, and a third request enters concurrently. Fix: set the lock value to a random token, release via Lua `if get == token then del end`.
- **P1 — `KEYS` on `session:{user_id}:*` and `session:*`.** Used in `get_user_sessions` and `get_active_sessions_count`. Upstash's serverless Redis tolerates KEYS better than self-hosted, but it's still O(total keys); hot tenants and growth will degrade this. Fix: maintain a `user_sessions:{user_id}` sorted set indexed by last activity, and a global `sessions:active` counter (INCR on create, DECR on delete).
- **P1 — `pop_playground_messages` is not atomic.** `lrange 0 -1` then `delete` — a message landed between the two calls is silently dropped. Fix: Redis 7 `LMPOP` or `LPOP count` in a loop; or use a transaction (`MULTI … EXEC`).
- **P2 — `check_rate_limit` is dead code.** Comment says "rate limiting handled by Peppi." Remove or gate behind a setting.
- **P2 — `get()` swallows JSON decode errors with bare `except:`.** Works, but masks bugs. Fix: `except json.JSONDecodeError: return data`.

### 1.2 `session_manager.py`

- **P0 — Session TTL and user-lock TTL are wildly mismatched against real turn durations.** Session TTL is 1h (ok); user-lock TTL is 30s default in `acquire_user_lock`. A single image turn legitimately takes 260s. When the lock expires mid-turn, concurrent requests leak in and the DB / OAuth refresh races begin. Fix: bump lock TTL to max-turn-duration + grace (say 300s), or extend via heartbeat.
- **P0 — Session isolation is user-id-keyed, which is good — but tenancy across agents is weaker.** There is no defensive check that a retrieved session's `user_id` field matches the requested `user_id`. Fix: after `get_session`, assert `data.get('user_id') == user_id`; reject on mismatch.
- **P1 — `add_message` rewrites the entire session blob on every append.** The whole conversation history is one JSON document; every new message ser/deserializes the full doc. For a long session this is O(n²) bandwidth. Fix: use `RPUSH session_msgs:{user_id}:{session_id}` for messages, keep the session doc for metadata only.
- **P2 — `conversation_history` is de facto dead:** routes.py explicitly skips `add_message` and notes "Peppi provides full context." Either delete this code path or document it's reserved for the playground.
- **P2 — `get_active_session_for_user` parses keys from `KEYS` output, picks "the first"; order is undefined.** If a user has two stale sessions, you get an arbitrary one.
- **P2 — System-message preservation in history truncation can compute `keep_count` negative** if the user's history accumulates more system messages than `max_history`.

### 1.3 `credential_manager.py`

- Strongest file in the repo. Cooldown pattern for OAuth refresh (5-min Redis key) is production-quality. Permanent-vs-transient error split is well done.
- **P2 — `fromisoformat` will choke on Zulu-suffixed strings** (`…Z`). Supabase returns `+00:00` so we're fine today, but any schema drift will break silently. Fix: `datetime.fromisoformat(s.replace('Z', '+00:00'))`.
- **P3 — `revoke_google_token` doesn't check Google's response status.** Fire-and-forget. Worth a log line if Google 400s.

### 1.4 `database.py`

- **P1 — `get_all_users()` returns all rows with no pagination.** Called by the playground. Works today; growth breaks it.
- **P1 — `get_user_reminders()` returns all rows with no pagination.** Power users with recurring reminders will eventually trip this.
- **P2 — `get_token_usage(user_id=None)` crosses tenants.** Only safe if every caller is trusted-internal. Pending grep of callers.
- **P2 — `generate_user_id` uses `secrets.token_hex(4)` → 32 bits.** Birthday collision at ~65k users. Bump to `token_hex(8)`.
- **P2 — Every mutation-method uses lazy `await self.initialize()`.** If Supabase creds are missing at startup the service boots "healthy" and fails on first write. Fix: fail fast in lifespan.
- **P3 — `update_action_log` drops empty-string summaries.** Low-severity.

---

## 2. FastAPI wrapper — `app/api/*`

### 2.1 `oauth.py`

- **P0 — `GET /oauth/google/token/:user_id` hands out OAuth access tokens to any caller.** No auth header, no API key, no IP allow-list. It exists to bridge the gateway's spawn path, but nothing stops a third party who learns a user_id (predictable: 8 hex chars — see §1.4) from calling it and walking away with a Google access token. Impact: full read/write access to the victim's Gmail + Calendar until token expiry. **Must have:** a shared-secret bearer token between gateway and wrapper, or signed headers, or loopback-only + gateway-on-same-host. Any of the three.
- **P2 — OAuth callback's profile fetch silently falls back to `User <id>` if userinfo.profile scope isn't granted.** Looks like a "works" path. Users will see the placeholder name in the UI. Fix: include `openid profile email` in GOOGLE_SCOPES or warn on missing name.
- **P2 — RedirectResponse URLs are built by string concatenation.** No URL-encoding of `user_id` or error codes. If user_id ever contains `&` or `=`, the redirect breaks. Fix: `urllib.parse.urlencode`.
- **P3 — Error codes in redirects are ad-hoc strings** (`GOOGLE_DENIED`, `INVALID_STATE`). Document them in a single enum so the frontend has a stable contract.

### 2.2 `reminders.py`

- **P0 — QStash signature verification falls back to `return True` if keys are missing.** If `QSTASH_CURRENT_SIGNING_KEY` is blank in Render, anyone who can reach the public `/api/v1/reminders/deliver` endpoint can trigger fake reminder deliveries (spam SMS + pollute audit log). Fix: fail closed — if configured, require valid sig; if not configured at all, log error and reject in production.
- **P1 — `_verify_qstash_signature` failure returns 200.** `return {"status": "rejected", "reason": "invalid_signature"}` is a 200 OK. QStash will NOT retry and the event is silently dropped. That's actually the desired behavior for signature failures, but the status code should be 401 so it shows up in logs/monitoring.
- **P1 — Dedup iterates all pending reminders per create.** `get_user_reminders(request.user_id, status='pending')` has no limit. Power users with hundreds of recurring reminders pay O(n) per new reminder. Fix: add a DB index on `(user_id, status, created_at)` and a `limit 50` in the query.
- **P2 — `deliver_reminder` swallows ALL exceptions into 200.** Comment says it's to prevent QStash retry loops, but a parse error and a real DB error look identical from the outside. Fix: split — parse errors → 200 + log; transient DB errors → 500 so QStash retries.
- **P2 — `update_reminder` ownership check uses `str() == str()`.** Correct today, but if `user_id` is ever an int from one side and string from the other, the comparison silently fails-open. Fix: normalize once at entry and keep a single type.
- **P2 — Cancel/update endpoints are `POST` when they should be `DELETE` / `PATCH` per REST.** Minor, but it makes client code assume side-effect semantics.

### 2.3 `google_services.py`

- **Dead-ish code in prod.** These endpoints (calendar + gmail wrappers) exist, but skills bypass them and hit Google's REST API directly with `curl` from bash. If nothing else in the repo calls them either, this is ~515 lines the service pays to load for no benefit. Before deleting, grep: likely used by the playground or a future direct-API path. Either document or delete.
- **P2 — `list_calendar_events` computes `time_max` by mutating `.day` field.** `time_max.replace(day=time_max.day + days)` throws `ValueError` when `day + days` crosses month boundaries, and silently no-ops for `days > 28`. Replace with `time_max + timedelta(days=days)`.
- **P2 — Endpoints return HTTP 200 even when inner `success: False`.** Clients have to re-check the body. Map Google errors → proper HTTP status (404, 403, 500).
- **P3 — Every endpoint has the same try/except shape.** A `@google_endpoint` decorator would remove ~300 lines.

### 2.4 `playground.py`

- **P0 — `/playground/token-usage`, `/playground/token-usage/csv`, `/playground/token-usage/backfill` are unauthenticated.** Anyone on the internet can GET token usage (including `request_summary` and `response_summary`, which contain PII like calendar event titles, attendee emails, and reminder text), and POST the backfill endpoint which writes to the DB. Because `user_id` filter is optional, they can also enumerate all users + all messages with one call. **Data leak + write-capability. Fix today.**
- **P1 — `/playground/users` is unauthenticated.** Leaks every user's name, email, google_connected flag, timezone. Same class of bug.
- **P2 — `/playground/create-user` is unauthenticated.** Anyone can create playground users and kick off OAuth flows with attacker-controlled `redirect_uri` (passed into Google OAuth URL). If the validation in the OAuth callback trusts `state_data["redirect_uri"]` to decide where to send the success redirect (it does — line 304-310 of oauth.py), this could be used for phishing. Fix: (a) gate `/playground/*` behind an admin token or CIDR allow-list, (b) validate `redirect_uri` against a hardcoded allow-list.
- **P2 — Hardcoded Anthropic pricing** in `_estimate_cost_detailed`. Move to settings so rate changes don't require a code push.

### 2.5 `outbound.py`

- **P0 — If `PEPPI_OUTBOUND_URL` is ever set to this endpoint in production, every reminder SMS silently vanishes into a log table, no user gets the message.** This file is explicitly a stub. It should **refuse** to log SMS when running with `ENV=production` unless a `MOLTBOT_ALLOW_SMS_STUB=true` override is set, so that accidental misconfiguration fails loud.
- **P2 — Always returns 200** (even on DB failure). Defensible ("don't trigger QStash retries"), but the `{"status": "sent", "warning": "..."}` shape is indistinguishable from a successful send to anyone reading the response. Should return 500 so someone notices.

### 2.6 `services/google_calendar.py` and `services/gmail.py`

- **P1 — `create_event` accepts naive `datetime` and blindly attaches `timeZone: UTC`.** If a caller passes `2026-04-23T14:00:00` meaning local time, the event is created for 14:00 UTC. Because Pydantic's `datetime` field accepts both naive and aware, this is a live footgun. Fix: require aware datetimes (reject naive in the Pydantic validator) OR always accept a `timezone` pair alongside the datetime string.
- **P2 — These services rebuild the googleapiclient service per call.** For a busy tenant that's one `build('calendar', 'v3', …)` per request. In the skill path it doesn't matter (skills curl directly), but if the wrapper endpoints get used, this will matter. Cache per-user service objects keyed by token hash.
- **P3 — Gmail `list_messages` fetches full metadata one-by-one** — one API call per message. Gmail supports `batchGet`; ~10× faster.

---

## 3. FastAPI wrapper — migrations + utils + services (pt 2)

### 3.1 `migrations/*.sql`

- **P0 — Row Level Security is commented out.** Migration 002 leaves `ALTER TABLE … ENABLE ROW LEVEL SECURITY` as a suggestion, not applied. The service uses Supabase with (presumably) the service-role key, so server-side access is full-table. If the anon key were ever used or leaked into a client, a third party could read every user's credentials blob + audit log. Server-role-only is a single-point-of-failure design — enable RLS, write per-tenant policies on `user_id = current_setting('request.jwt.claim.sub')` style.
- **P1 — No `tbl_clawdbot_reminders` schema in migrations.** Migration 005 *references* it conditionally but no CREATE. The table must exist on Supabase without a version-controlled definition; onboarding a new environment is not reproducible.
- **P1 — Missing composite indexes.** The `get_user_action_history(user_id, ORDER BY created_at DESC)` query has `idx_audit_user_id` and `idx_audit_created_at` separately. Postgres can bitmap-merge them, but a composite `(user_id, created_at DESC)` is ~2× faster and smaller. Same for `get_user_reminders(user_id, status, trigger_at DESC)`.
- **P2 — `user_id VARCHAR(50)` with no CHECK constraint.** Any length or character accepted. At minimum add `CHECK (length(user_id) BETWEEN 5 AND 50 AND user_id ~ '^[A-Za-z0-9_]+$')`.
- **P2 — Migration 001 is MySQL, 002 is Postgres.** The MySQL file is dead — the project uses Supabase. Delete 001 to avoid onboarding confusion.

### 3.2 `services/peppi_client.py`

- **P2 — Timeout is 30s.** Fine for Twilio latency, but combined with QStash retries and our dead-letter threshold it adds up. 10s is enough for an SMS call; Twilio queues internally.
- **P3 — No retry on 5xx.** `raise_for_status()` bubbles up, reminders.py handles retry accounting but calls the client only once per webhook. A transient 503 costs a whole retry slot.

### 3.3 `services/qstash_service.py`

- Clean wrapper. No issues of note.
- **P3 — `retries=3` hardcoded.** Fine, but should be a config constant shared with `DEAD_LETTER_RETRY_THRESHOLD` in reminders.py so they stay aligned.

### 3.4 `utils/timezone_utils.py`

- Strong file. `CRON_TZ=` prefix for QStash is the right pattern for DST correctness.
- **P2 — `ZoneInfo(timezone)` raises on unknown timezone** — the wrapper swallows it as `ValueError`, but callers (reminders.py) just `return error_response("validation_error")`. The user sees a generic error, not "your timezone string is malformed." Fix: validate timezone at OAuth / account creation and refuse invalid strings up front.
- **P3 — `utc_to_local` is only used within the module.** Could go in a tests-only helper.

### 3.5 `utils/cleanup.py`

- Almost a no-op. Runs every 5 min and only logs the session count.
- **P3 — The comment promises orphaned-lock cleanup but doesn't do it.** Either implement or remove the promise.

### 3.6 `utils/encryption.py`

- One-liner utility, used via `python -m app.utils.encryption` to generate a Fernet key. Fine.

---

## 4. Playground frontend (`playground/src/*`)

### 4.1 `services/api.js`

- Clean fetch wrapper with env-var resolution.
- **P2 — Every request is unauthenticated.** No bearer token, no session cookie. The frontend passes `user_id` as part of the URL / body and the server trusts it blindly. That's the tenancy hole called out in §2.4, visible from the client side too.
- **P2 — `request()` swallows errors.** `try { ... } catch {} return []` pattern in `getPlaygroundUsers`. A network failure looks identical to "no users."

### 4.2 `context/AuthContext.jsx`

- **P0 — No real authentication.** "Login" just writes `{user_id, name}` to `localStorage`. Anyone who types another user's `user_id` at the login prompt becomes that user for the rest of the session, with full access to their Google tokens, reminders, and audit log. This is the headline tenant-isolation hole. A playground for PMs may not need corporate SSO, but it needs *something* — even a shared passphrase + scoped to that user, or a signed cookie from an OAuth login. Today it is effectively a public PII viewer.
- **P2 — localStorage user includes `timezone: Intl.DateTimeFormat().resolvedOptions().timeZone`.** If the user's machine TZ changes (travelling) the playground silently uses stale TZ. Not terrible, but not what SettingsModal probably expects. Refresh TZ on login.

### 4.3 `components/ChatInterface.jsx`

- **P1 — Polls `/playground/messages/:user_id` every 5 seconds forever** whenever the tab is open. Zero polling back-off. For 100 tabs = 20 req/s to FastAPI just for empty-reply polls. Switch to SSE or WebSocket, or at minimum back off when the page is hidden (`document.visibilityState === 'hidden'`).
- **P2 — `user.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone` fallback chain.** Fine, but means TZ sent to backend can vary per tab. Inconsistency risk during travel or if two tabs are open.
- **P3 — `isReminderDelivery: log.action_type === 'reminder_delivery'` — identifier is a hardcoded string shared with the backend.** At least move to a shared `constants.js`.

### 4.4 `tests/generate_report.py`

- Clean HTML generation with proper `escape()`. No XSS.
- **P3 — `datetime.utcnow()` is deprecated in 3.12+** (use `datetime.now(timezone.utc)`). Everywhere in the repo, actually — this is a repo-wide 3.12 upgrade issue.

### 4.5 SearXNG

- **P1 — `secret_key: "replace_this_with_a_random_secret_key_for_production"` committed in `searxng/settings.yml`.** If Render doesn't override via env var, the key is the string `replace_this…`. Need to verify the deployed instance; if it's the literal default, fix now.
- **P3 — `limiter: false` relies on Render's rate limiting, which doesn't exist on this plan.** Put SearXNG behind a small budget or it'll get crawled.

---

## 5. Gateway & skills (recap — already audited during migration)

The migration added:
- Loopback context broker on `127.0.0.1:8788` (separate Express app, bound-loopback + IP-guard middleware).
- Per-turn 128-bit session key minted by `mintSessionKey()` ([server.js:47](moltbot-gateway/server.js#L47)).
- SessionKey injected into the agent's system prompt; skills extract it and curl the broker.
- Daemon on `127.0.0.1:${OPENCLAW_DAEMON_PORT}` (18790), gatewayReady gate on `/health`.

Additional gateway-level observations from re-reading the committed code:

### 5.1 `server.js`

- **P1 — `sessionContext` Map has no size cap.** If a request lands, mints a key, and then the process crashes before `finally`, the entry leaks until restart. The Map will also grow unbounded if some request path never hits `finally` (unlikely with Express but not impossible). Fix: a second LRU with TTL (say 10 min), or set a `setTimeout` on insert to auto-delete.
- **P1 — No auth on the public `/execute` endpoint.** The wrapper calls it over Render's internal network, which is not actually isolated from the public internet in Render's architecture — Render services are internet-reachable by default. If anyone discovers the gateway's public URL, they can send arbitrary requests, drain Anthropic budget, and forge calls to any user's Google account (since the gateway has OAuth bridge logic and will fetch tokens by `user_id`). **Critical: require a shared `X-Moltbot-Gateway-Auth` bearer.**
- **P2 — The ASCII-table startup banner** still references features removed from the HTTP-mode rewrite. Harmless but confusing.
- **P2 — `/diagnose` returns the first 5 chars of the Gemini key.** That's 20+ bits of entropy; with the same key prefix, an attacker can mount targeted guessing. Log hash, not prefix.
- **P3 — `/skills` returns a hardcoded list** that no one uses. Delete.

### 5.2 Skill preambles

- **P1 — The preamble assumes `$OPENCLAW_USER` / `<SESSION_KEY_FROM_CONTEXT>` will be substituted correctly by the model every turn.** That's a model-reliability bet. Sonnet 4.6 is usually good at this, but a subtle wording drift in agent.md could cause the preamble to skip. Without the preamble, all downstream curl calls get `Authorization: Bearer ` (empty) → HTTP 401 from Google → user sees "Google connection may need refresh." A single-run skip looks like a real token failure. Fix: the gateway could check if the broker received ANY lookup for each request's sessionKey, and if not, surface a 500 with "agent did not fetch context — retry" so we catch this regression.
- **P2 — The preamble curl has `--max-time 5`.** Loopback calls should complete in <50 ms; 5s hides issues. Tighten to 2s.
- **P2 — Skills fail-open if the broker returns empty context** (it `exit 1`s ONLY if `GOOGLE_ACCESS_TOKEN` is empty). For the reminders skill which doesn't need OAuth, a bad/missing broker response leaves `FASTAPI_URL` empty and the subsequent `curl "${FASTAPI_URL}/api/v1/reminders/create"` hits `/api/v1/reminders/create` as a relative URL → different failure mode.

---

## 6. Cross-cutting concerns (worst-to-best)

These aren't about any one file — they're systemic.

### 6.1 Authentication model — the headline weakness

There are **three separate public-facing entry points** that implicitly trust `user_id` from the body or URL without proving the caller is authorized to act as that user:

| Surface | Caller | Trust mechanism | Attacker potential |
|---|---|---|---|
| FastAPI `/api/v1/execute-action` | Peppi (Laravel) | None | Any caller on the internet can spend Anthropic tokens under any user's account, create calendar events, send emails, set reminder SMS to arbitrary phone numbers |
| FastAPI `/api/v1/oauth/google/token/:user_id` | Gateway (server.js) | None | Steal any user's Google access token |
| FastAPI `/api/v1/playground/*` | Playground SPA | None + localStorage | Full PII dump, user impersonation |
| Gateway `/execute` | FastAPI wrapper | None | Spend Anthropic tokens, forge actions |

The trust boundary is "only Peppi + our gateway know these URLs," which is security-by-obscurity. Render assigns URLs like `https://moltbot-fastapi.onrender.com` — they're guessable and indexable.

**Fix (minimum viable):**
1. Generate a shared secret `MOLTBOT_INTERNAL_SECRET`. Both Peppi and the gateway set it in env.
2. Wrap every sensitive FastAPI route in a dependency that requires `Authorization: Bearer $MOLTBOT_INTERNAL_SECRET`.
3. The gateway → FastAPI call already flows through the OAuth token endpoint; add the bearer there too.
4. The gateway's public HTTP surface (`/execute`) should similarly require this bearer from FastAPI.

**Fix (right way):**
- Move `openclaw-gateway-*` to a Render **Private Service** (per docs: "private services aren't reachable via the public internet, but they are reachable by your other Render services on the same private network"). That single change removes the "gateway is internet-facing" attack vector entirely.
- Keep FastAPI as a public web service but require HMAC-signed requests from Peppi with short-lived signatures.
- Playground endpoints move behind Google OAuth login (the same OAuth we already integrate) so only logged-in users can hit them, with RLS on Supabase keyed to the authenticated user's id.

### 6.2 Tenancy — the weakness that compounds

Keyed by `user_id` end-to-end: Redis session keys (`session:{user_id}:*`), Supabase rows (`user_id` column), gateway context broker (session key minted per request). That's good.

What's weak:
- No defensive checks (§1.2). If an upstream bug puts User A's `user_id` in User B's request, nothing catches it.
- `get_token_usage(user_id=None)` returns all tenants (§1.4). Dangerous if any public endpoint forwards `user_id=None`.
- RLS is disabled on Supabase (§3.1). Server-role-only access is a single-point-of-failure.

### 6.3 Concurrency — per-user lock is too short, too simple

- User lock TTL 30s ([session_manager.py:236](fastapi-wrapper/app/core/session_manager.py#L236)), turn duration up to 260s. Two concurrent requests per user are possible during the overlap window.
- Lock release is `DEL` with no ownership check (§1.1). Two requests can hold "the lock" simultaneously.
- Gateway has no user-level lock — the only safety is the FastAPI one. If FastAPI's lock fails, the gateway happily runs two turns per user in parallel. Prompt cache cross-contamination is mostly a non-issue (prefixes diverge), but per-request Google token fetches and DB writes race.

**Fix:** Redlock pattern with UUID ownership token (Redis docs + Python libraries already exist: `redlock-ng`, `pottery`). TTL = max-turn-duration + 60s buffer (say 320s), with mid-turn refresh every 60s.

### 6.4 Error semantics — many 200s that aren't successes

Throughout `reminders.py`, `playground.py`, `google_services.py`, `outbound.py` — errors return `{status: "failed", ...}` with HTTP 200. Comment justifies this as "don't trigger QStash retries." But:
- Monitoring/log aggregation can't distinguish success from failure by HTTP status.
- Clients trip over this — the playground JS has to `res.code === 200 && res.data?.response` checks scattered everywhere.

**Fix:** Use proper HTTP status codes (201 for create, 400 for bad input, 401 for auth, 5xx for real failures), AND include a stable `error.code` string for machine consumption. For QStash: it distinguishes "successfully processed" from "retry" via the HTTP status — 2xx = done, 5xx = retry. We can still return 200 from `/reminders/deliver` (so QStash doesn't retry parse errors) but use 500 for transient DB errors we want to retry.

### 6.5 Observability — structured logs exist, but no metrics

- Good: structured logging with session_id prefix.
- Missing: no request-level metrics emitted (no StatsD / Prometheus / Render metric stream).
- Missing: no alerting on key rates — `cache_read / prompt_tokens` ratio, `EMPTY_RESPONSE` count, `USER_LOCKED` count, `invalid_grant` cleanup rate.
- The test suite (193 scenarios) is great correctness validation but isn't wired into CI to block bad pushes.

**Fix:** Log a one-line structured metric per turn (`event=turn_complete session=… user=… cache_ratio=0.99 tokens=164094 duration_ms=10430`). Pipe to Render's log stream or out to Grafana Cloud. On every PR, run the 193 suite against the staging service and fail the merge if pass count drops.

### 6.6 Singletons + lifespan

The repo uses module-level singletons (`db`, `redis_client`, `qstash_service`, `peppi_client`, `session_manager`, `credential_manager`). Each file instantiates one with `= ClassName()` at import. Lazy initialization guards against missing env vars but also means the service boots without verifying DB connectivity.

Per industry guidance: ["Lifespan objects should be read-only … Anything shared across requests must have concurrency guards built in"](https://medium.com/@dynamicy/fastapi-starlette-lifecycle-guide-startup-order-pitfalls-best-practices-and-a-production-ready-53e29dcb9249). Our pattern is common but suboptimal.

**Fix:** Move singletons into `app.state` in the `lifespan` context manager, fail-fast on init errors. No functional change, cleaner ownership.

### 6.7 Time handling — mostly solid, one weak spot

- `timezone_utils.py` handles naive vs aware, uses `CRON_TZ=` for QStash. Good.
- Dedup in `reminders.py` parses via `.replace(tzinfo=None)` and compares naive datetimes. Fragile against schema changes but works today.
- `services/google_calendar.py` treats all incoming datetimes as UTC (§2.6) — wrong for naive inputs.
- `datetime.utcnow()` deprecated in 3.12+; repo-wide uses it ~50 times. One day this will warn, then break.

### 6.8 Prompt caching posture

From the Anthropic research: **cache entries become available after the first response begins — not available for concurrent parallel requests**. Meaning: 10 simultaneous users hitting the gateway each pay full input-token price for the first turn. After that, subsequent requests within 5 min hit cache.

For our traffic profile (SMS-triggered, bursty), that's fine. For scaling up or CLI/API usage with parallel tenants, we'd want to either warm the cache periodically OR recognize the first-request-of-a-5min-window tax.

Also: per multi-tenant cache research, "caching prefixes that mix tenants creates a security risk where tenant A's data could leak into tenant B's prompt via a shared key." Our system prompt structure (SOUL.md + agent.md + skills) is identical across tenants — safe to share. The divergence point is the per-turn context line (`USER: xxx | Timezone: … | SessionKey: …`). That's AFTER the shared-cached prefix, so cross-tenant leakage is not possible via the cache itself. ✅

### 6.9 Skill reliability under HTTP mode

The biggest fragility introduced by the migration is the "agent must run the preamble first" contract. If Sonnet skips or malforms the preamble:
- `GOOGLE_ACCESS_TOKEN` empty → Google API returns 401 → user sees a cryptic "your connection may need refresh."
- `FASTAPI_URL` empty → relative-URL curl → cryptic failure.
- `MOLTBOT_USER_ID` empty → reminder created for user `""` → DB FK violation (if FK exists) or silent tenant bleed.

**Fix:** Detect preamble skip at the gateway. After each `/execute` turn, check if `sessionContext` was ever read for that key (add a `_reads` counter on the Map). If zero reads happened but the turn involved a skill trigger ("schedule", "remind", "email"), surface an `EMPTY_PREAMBLE` error and retry.

---

## 7. Industry-pattern comparison

### 7.1 OpenClaw multi-tenant projects in the wild

Several production open-source projects address the same problem:

- **[nextlevelbuilder/goclaw](https://github.com/nextlevelbuilder/goclaw)** — Go rewrite with "multi-tenant isolation, 5-layer security, native concurrency." Key pattern: multi-tenant PostgreSQL with per-tenant schemas.
- **[jomafilms/openclaw-multitenant](https://github.com/jomafilms/openclaw-multitenant)** — Platform layer on top of OpenClaw with "container isolation, encrypted vault, team sharing." Pattern: per-user Docker container, so OAuth tokens never leave the tenant's runtime.
- **[aws-samples/sample-openclaw-multi-tenant-platform](https://github.com/aws-samples/sample-openclaw-multi-tenant-platform)** — Amazon EKS with "path-based routing via Gateway API: `claw.example.com/t/<tenant>/`, one domain, one ALB, no wildcard DNS." Pattern: per-tenant URL routing with scale-to-zero per user.
- **[lobu-ai/lobu](https://github.com/lobu-ai/lobu)** — Sandboxing + programmatic API creation, "each channel/DM gets its own isolated runtime, model, tools, credentials, Nix packages." Pattern: runtime isolation per channel.
- **[dataelement/Clawith](https://github.com/dataelement/Clawith)** — "Persistent identity, long-term memory, own workspace per agent. Multi-tenant RBAC with organization-based isolation."

**What they all share that we don't:** per-tenant runtime isolation. OAuth tokens never appear in a shared process's memory. Our loopback-broker approach holds OAuth tokens in a shared `Map` keyed by unguessable session key — safer than env vars but still one bug away from cross-tenant leak.

**Why we probably can't do full container-per-tenant in the short term:** cost. Each tenant container needs Anthropic API access, OpenClaw binary, skills. Render Pro at $25+/month/service means 100 users = $2500/month. Not viable until revenue justifies.

**Pragmatic middle:** we can at least use Render **Private Services** (docs: ["private services aren't reachable via the public internet, but they are reachable by your other Render services on the same private network"](https://render.com/docs/private-services)) for the gateway, eliminating one public attack surface. Cost-neutral.

### 7.2 LangServe / LangChain — per-request OAuth tokens

LangServe's pattern: type-hint a tool argument with `RunnableConfig` — the LLM ignores it (won't try to generate the value), but the runtime injects it at invocation time. [Source](https://github.com/langchain-ai/langserve/discussions/534).

Our broker is the OpenClaw equivalent: we can't add a RunnableConfig arg to skill bash, so we inject via a loopback HTTP call keyed by an unguessable token. Same security model (runtime injection, never in the LLM's prompt), same threat model (single-process compromise = all tokens).

### 7.3 OpenAI-compat cache metrics

OpenAI standardized on `usage.prompt_tokens_details.cached_tokens`. Anthropic's native API exposes **both** `cache_read_input_tokens` and `cache_creation_input_tokens`. OpenClaw's `/v1/chat/completions` passthrough to Anthropic gives us only `cached_tokens` (combined read, no write breakout). That's the loss we accepted. The prompt cache itself still works — we just can't observe write activity.

### 7.4 Redis distributed locks

Industry-standard pattern ([Redis docs](https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/)):
1. SET key token EX ttl NX (atomic, with unique token).
2. Release via Lua script: `if redis.call('GET', KEYS[1]) == ARGV[1] then redis.call('DEL', KEYS[1]) end`.
3. Extend TTL for long tasks: similar Lua script.

Python libraries that implement this: `redlock-ng`, `pottery`, `aioredlock`. Using any of these eliminates our P0 lock bug with <10 LoC change.

---

## 8. Prioritized fix list (what I'd do this sprint)

**This sprint (P0 — do before prod gets more traffic):**

1. **Shared-secret auth on all internal endpoints.** ([§6.1](#61-authentication-model--the-headline-weakness)) One env var (`MOLTBOT_INTERNAL_SECRET`), three dependency decorators. ~30 LoC. Closes four public attack surfaces.
2. **Enable Supabase RLS.** ([§3.1](#31-migrationssql)) Write per-tenant policies keyed to service role. Fallback defence if the service-role key leaks.
3. **Fix `release_lock` ownership check.** ([§1.1](#11-redis_clientpy)) Switch `redis_client.acquire_lock` / `release_lock` to SET-with-token + Lua-script release. ~20 LoC.
4. **Bump user-lock TTL to 320s.** ([§1.2](#12-session_managerpy)) So it survives image-flow turns.
5. **Fail closed on missing QStash signing keys.** ([§2.2](#22-reminderspy)) Raise in lifespan startup if env var blank.
6. **Add defensive user-id match on every session fetch.** ([§1.2](#12-session_managerpy)) Reject cross-tenant.
7. **Move `/playground/*` behind real auth.** ([§2.4](#24-playgroundpy)) At minimum admin-token bearer; properly, Google OAuth login.

**Next sprint (P1 — scalability + correctness cliffs):**

8. **Pagination on `get_all_users`, `get_user_reminders`, audit queries.** ([§1.4](#14-databasepy))
9. **Replace Redis `KEYS` with secondary indexes.** ([§1.1, §1.2](#11-redis_clientpy)) Maintain `user_sessions:{user_id}` sorted set.
10. **Move gateway to Render Private Service.** Eliminates public gateway attack vector.
11. **Move singletons into `lifespan` + `app.state`, fail-fast on init.** ([§6.6](#66-singletons--lifespan))
12. **Replace `datetime.utcnow()` repo-wide with `datetime.now(tz=UTC)`.** Future-proofs for 3.12.
13. **Preamble-skip detection in gateway.** ([§6.9](#69-skill-reliability-under-http-mode)) Per-request broker-read counter.
14. **Composite DB indexes on `(user_id, created_at DESC)`, `(user_id, status, trigger_at)`.**
15. **Polling back-off in playground when `document.visibilityState === 'hidden'`.** ([§4.3](#43-componentschatinterfacejsx))

**Later (P2/P3 — quality + tidy):**

16. Collapse repetitive try/except in Google service endpoints into a decorator.
17. Delete the MySQL migration file 001 (stale).
18. Move hardcoded Anthropic pricing to config.
19. Delete unused `list_messages`-style per-message Gmail fetch loop; use `batchGet`.
20. Tighten 5s broker timeout to 2s.
21. Document which OpenClaw env vars the daemon reads so config drift is visible.

---

## 9. Recommended architecture (end-state, not this week)

```
   Peppi (Laravel)
        │  HMAC-signed POST
        ▼
┌──────────────────────────────────────────────────────┐
│  FastAPI wrapper (public web service)                │
│   — shared-secret bearer auth on /execute-action     │
│   — playground/* behind Google login + RLS           │
│   — lifespan-managed singletons in app.state         │
└──────────────────────────────────────────────────────┘
        │  loopback only
        ▼
┌──────────────────────────────────────────────────────┐
│  openclaw-gateway (Render PRIVATE service)           │
│   — no public URL — reachable only by the wrapper    │
│   — daemon + server.js co-process                    │
│   — context broker on 127.0.0.1:8788 (unchanged)     │
│   — per-turn session key, auto-expiring broker entry │
└──────────────────────────────────────────────────────┘
        │                              │
        │ Anthropic API                │ Supabase
        │ (prompt-cached system)       │ (RLS enabled)
        ▼                              ▼
   ┌──────────┐                 ┌─────────────┐
   │ Claude   │                 │ Postgres    │
   │ Sonnet   │                 │ tbl_*       │
   │ 4.6      │                 │ RLS by user │
   └──────────┘                 └─────────────┘
```

Properties this architecture has that the current one doesn't:
- Gateway not internet-reachable → no DDoS, no token leak via public endpoint.
- Real per-tenant DB isolation even if service-role key leaks.
- Defensive auth on every inter-service hop.
- Same cost (Private Services are free on Pro, unchanged DB layer).

---

## 10. Sources (researched during this audit)

### OpenClaw multi-tenant production patterns
- [Feature Request: Multi-tenant / Multi-agent support on a single gateway — openclaw/openclaw #61123](https://github.com/openclaw/openclaw/issues/61123)
- [GoClaw (Go rewrite with multi-tenant isolation)](https://github.com/nextlevelbuilder/goclaw)
- [jomafilms/openclaw-multitenant](https://github.com/jomafilms/openclaw-multitenant)
- [aws-samples/sample-openclaw-multi-tenant-platform](https://github.com/aws-samples/sample-openclaw-multi-tenant-platform)
- [lobu-ai/lobu — multi-tenant OpenClaw](https://github.com/lobu-ai/lobu)
- [dataelement/Clawith — OpenClaw for Teams](https://github.com/dataelement/Clawith)
- [From Multi-Tier to Multi-Tenant: Trilogy AI deep dive](https://trilogyai.substack.com/p/deep-dive-from-multi-tier-to-multi)
- [OpenClaw security docs](https://docs.openclaw.ai/gateway/security)

### Render private networking
- [Render Private Network docs](https://render.com/docs/private-network)
- [Render Private Services docs](https://render.com/docs/private-services)
- [How Render handles private networking](https://render.com/articles/how-render-handles-private-networking)

### LangChain / LangServe per-request auth
- [LangServe discussion #534 — passing auth token to tools](https://github.com/langchain-ai/langserve/discussions/534)
- [Auth0 blog — Secure LangChain tool calling with FastAPI](https://auth0.com/blog/first-party-tool-calling-python-fastapi-auth0-langchain/)

### Anthropic prompt caching (multi-tenant, concurrency, TTL)
- [Anthropic prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Anthropic Silently Dropped Prompt Cache TTL from 1 Hour to 5 Minutes](https://dev.to/whoffagents/anthropic-silently-dropped-prompt-cache-ttl-from-1-hour-to-5-minutes-16ao)
- [Prompt Caching Guide 2026 — SurePrompts](https://sureprompts.com/blog/prompt-caching-guide-2026)
- [PromptHub: Prompt Caching with OpenAI, Anthropic, Google](https://www.prompthub.us/blog/prompt-caching-with-openai-anthropic-and-google-models)

### Redis distributed locks
- [Redis Distributed Locks docs](https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/)
- [On implementing distributed locks — Abhilash Rejanair](https://www.rejanair.com/blog/on-implementing-distributed-locks)
- [OneUptime: Python Distributed Locks with Redlock (2026-01-25)](https://oneuptime.com/blog/post/2026-01-25-python-distributed-locks-redlock/view)

### FastAPI lifespan + singletons
- [FastAPI/Starlette Lifecycle Guide — Chris Evans](https://medium.com/@dynamicy/fastapi-starlette-lifecycle-guide-startup-order-pitfalls-best-practices-and-a-production-ready-53e29dcb9249)
- [The Concurrency Trap in FastAPI — DataSci Ocean](https://datasciocean.com/en/other/fastapi-race-condition/)
- [Need Advice On How To Properly Use Supabase With FastAPI — supabase discussion #33811](https://github.com/orgs/supabase/discussions/33811)

---

## 11. What I'd want codex to push back on

If this audit gets reviewed, these are the judgment calls I'd want argued:

1. **Should the gateway be a Render Private Service or stay public?** Private = safer but costs migration effort and requires the wrapper to never forward requests from outside Peppi. Public + bearer = cheaper to implement but larger attack surface.
2. **Enable RLS now or later?** Enabling adds complexity to every service-role query (need to set JWT claim or use service-role bypass). Testing surface grows. Worth the safety tradeoff?
3. **Keep the broker pattern or move to something cleaner** (e.g., an Anthropic-native `cache_control` block with per-user context AFTER the cached prefix, and let the model read tokens from the prompt)? The broker is a workaround for OpenClaw not supporting per-request env injection; if OpenClaw adds that upstream, we should remove the broker.
4. **Rewrite skills in Python vs keep in bash?** The OpenClaw bash skills are ~2500 lines across 4 files. Much of the complexity is time-zone arithmetic and JSON parsing in bash. A Python equivalent via direct Anthropic tool-use would be 200 lines and testable. But OpenClaw's whole value prop is bash-in-the-skill; leaving that path means leaving OpenClaw.
5. **Playground auth: Google login vs shared passphrase?** Google is correct but adds onboarding friction (PM testers need accounts). Shared passphrase is ugly but takes 10 minutes. Which is this playground actually for?

---

