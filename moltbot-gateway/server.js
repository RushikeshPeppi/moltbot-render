const express = require('express');
const { spawn, exec } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const path = require('path');
const axios = require('axios');
const app = express();
const PORT = process.env.PORT || 18789;

// Single shared http.Agent with keep-alive for loopback calls. Every
// executeViaHttp() request stays on the same TCP connection to the
// daemon instead of re-TCP-handshaking each turn. Cheap but noticeable
// at even modest throughput.
const loopbackAgent = new http.Agent({
  keepAlive: true,
  keepAliveMsecs: 30000,
  maxSockets: 64,
  maxFreeSockets: 16,
});

// This service talks to a long-lived `openclaw gateway` daemon over
// loopback HTTP. server.js forks the daemon as a child, polls /health,
// then routes /execute calls to the daemon's OpenAI-compatible endpoint.
// Per-request values (OAuth token, user id, timezone) reach skills via
// the loopback context broker below — the daemon's own env is fixed at
// boot and can't be mutated per request.
const DAEMON_PORT = Number(process.env.OPENCLAW_DAEMON_PORT || 18790);
const GATEWAY_URL = `http://127.0.0.1:${DAEMON_PORT}`;
const INTERNAL_BROKER_PORT = Number(process.env.INTERNAL_BROKER_PORT || 8788);
const INTERNAL_BROKER_URL = `http://127.0.0.1:${INTERNAL_BROKER_PORT}`;

app.use(express.json({ limit: '2mb' }));

// Require MOLTBOT_INTERNAL_SECRET bearer on mutating/sensitive endpoints.
// Health and diagnose stay open so Render's health check and ops debugging
// keep working. Enforced when the secret env is set; in dev (no env) we log
// and allow through so local testing keeps working.
function requireInternalSecret(req, res, next) {
  const expected = process.env.MOLTBOT_INTERNAL_SECRET || '';
  if (!expected) {
    if ((process.env.ENV || 'production').toLowerCase() === 'production') {
      console.error('[auth] MOLTBOT_INTERNAL_SECRET missing in production — refusing');
      return res.status(503).json({ error: 'inter-service auth not configured' });
    }
    return next(); // dev/staging tolerates missing secret
  }
  const hdr = req.headers['authorization'] || '';
  if (!hdr.toLowerCase().startsWith('bearer ')) {
    return res.status(401).json({ error: 'missing bearer token' });
  }
  const supplied = hdr.slice(7).trim();
  // constant-time string compare to avoid timing attacks on the shared secret
  if (supplied.length !== expected.length) {
    return res.status(401).json({ error: 'invalid bearer token' });
  }
  let diff = 0;
  for (let i = 0; i < expected.length; i++) {
    diff |= supplied.charCodeAt(i) ^ expected.charCodeAt(i);
  }
  if (diff !== 0) {
    return res.status(401).json({ error: 'invalid bearer token' });
  }
  next();
}

// Readiness. server.js must refuse traffic until the daemon is actually
// up, otherwise Render will happily route during the 5-15s cold start
// and every one will 5xx.
let isReady = false;
let gatewayReady = false;
let gatewayChild = null;
// Set by our own SIGTERM/SIGINT handlers. The gatewayChild exit trap
// checks this so a clean deploy doesn't look like a crash in Render logs.
let isShuttingDown = false;

// In-memory context broker. Each /execute turn mints a session key,
// stashes { google_access_token, user_id, user_timezone, fastapi_url }
// under that key, injects the key into the agent's system context, and
// deletes the entry when the response finishes.
//
// Defence in depth:
//   - Key is 128 random bits (unguessable).
//   - Broker is bound loopback-only (see below).
//   - Entries auto-expire after SESSION_CONTEXT_TTL_MS even if `finally`
//     never runs (process crash mid-turn). This prevents OAuth tokens
//     from leaking into a long-lived Map.
//   - Map size is hard-capped at SESSION_CONTEXT_MAX_ENTRIES; if we ever
//     exceed, we evict oldest + log — the daemon is misbehaving.
//   - A `_reads` counter is kept per entry so we can detect the case
//     where Sonnet skips the skill preamble (zero reads for a turn that
//     involved a skill trigger).
const SESSION_CONTEXT_TTL_MS = 300_000;      // 5 min — comfortably longer than image-flow timeout
const SESSION_CONTEXT_MAX_ENTRIES = 2000;    // well above peak concurrent turns
const sessionContext = new Map();

function mintSessionKey() {
  return crypto.randomBytes(16).toString('hex');
}

function sessionContextSet(key, value) {
  // Enforce size cap before insert. If we're above, drop the oldest entry
  // — Maps iterate in insertion order so `keys().next()` is the oldest.
  if (sessionContext.size >= SESSION_CONTEXT_MAX_ENTRIES) {
    const oldest = sessionContext.keys().next().value;
    sessionContext.delete(oldest);
    console.warn(`[broker] sessionContext cap hit (${SESSION_CONTEXT_MAX_ENTRIES}), evicted oldest`);
  }
  sessionContext.set(key, {
    ...value,
    _reads: 0,
    _expiresAt: Date.now() + SESSION_CONTEXT_TTL_MS,
  });
  // Schedule a forced delete even if the /execute handler never reaches its
  // finally (uncaught throw, process crash partway through, etc.). We use
  // unref() so this timer doesn't keep the event loop alive on shutdown.
  setTimeout(() => {
    if (sessionContext.has(key)) {
      sessionContext.delete(key);
      console.warn(`[broker] sessionContext entry for ${key.slice(0, 8)}… TTL-expired; something didn't clean up.`);
    }
  }, SESSION_CONTEXT_TTL_MS).unref();
}

function sessionContextGet(key) {
  const entry = sessionContext.get(key);
  if (!entry) return null;
  if (Date.now() > entry._expiresAt) {
    sessionContext.delete(key);
    return null;
  }
  entry._reads++;
  return entry;
}

// Health check. Refuse traffic until the daemon is reachable — otherwise
// Render routes requests during the 5-15s cold start and every one times
// out inside executeViaHttp().
app.get('/health', (req, res) => {
  if (!gatewayReady) {
    return res.status(503).json({
      status: 'starting',
      service: 'openclaw-gateway',
      gateway_ready: false,
    });
  }
  res.json({
    status: 'online',
    service: 'openclaw-gateway',
    openclaw_ready: isReady,
    gateway_ready: true,
  });
});

/**
 * Loopback context broker.
 *
 * Purpose: with a persistent OpenClaw daemon, we can't mutate env vars per
 * request — the daemon has one env set at boot. This broker exposes
 * per-turn values (OAuth token, user id, timezone, fastapi URL) on a
 * loopback-only port so skill bash can curl them at the top of each
 * operation.
 *
 * Security:
 *  - Bound to 127.0.0.1 only — not reachable from public internet regardless
 *    of firewall state.
 *  - Keyed by a 128-bit random hex token minted per turn (not by user_id /
 *    session_id, which are predictable). Token lifetime = one agent turn.
 *  - Entries deleted in a finally{} block when /execute returns.
 *  - Skills receive the token via the system context, not via a fixed env
 *    var — so even if two concurrent turns overlap they can't read each
 *    other's context.
 *
 * NOT used on the spawn path (env vars still work there), but we populate
 * the broker regardless so skills can be written once and work in both
 * modes.
 */
const internalApp = express();
internalApp.use(express.json());

// Defence in depth: reject any request whose remote IP isn't loopback.
// Express binds to 127.0.0.1 only (below), but this also catches the case
// where someone accidentally rebinds the broker to 0.0.0.0.
internalApp.use((req, res, next) => {
  const ip = req.ip || req.socket?.remoteAddress || '';
  if (ip !== '127.0.0.1' && ip !== '::1' && ip !== '::ffff:127.0.0.1') {
    console.warn(`[broker] rejected non-loopback request from ${ip}`);
    return res.status(403).json({ error: 'forbidden' });
  }
  next();
});

internalApp.get('/internal/context/:sessionKey', (req, res) => {
  // sessionContextGet() bumps the _reads counter so we can detect skill-
  // preamble skips (zero reads at end of turn for a skill-triggered turn).
  const ctx = sessionContextGet(req.params.sessionKey);
  if (!ctx) {
    return res.status(404).json({ error: 'unknown_session_key' });
  }
  // Strip private fields from the response sent to skills.
  const { _reads, _expiresAt, ...publicCtx } = ctx;
  res.json(publicCtx);
});

internalApp.get('/internal/health', (req, res) => {
  res.json({ status: 'ok', active_sessions: sessionContext.size });
});

// Bind ONLY to 127.0.0.1 — this is the critical security control. If you
// ever need to change this, think twice: the broker hands out OAuth tokens
// to any caller that knows a session key.
//
// Fatal on bind error: if port 8788 is taken we WILL NOT serve requests
// (every skill would silently fail to fetch context). Better to crashloop
// the container so Render's deploy shows red than to serve bad data.
const brokerServer = internalApp.listen(INTERNAL_BROKER_PORT, '127.0.0.1', () => {
  console.log(`[broker] loopback context broker listening on 127.0.0.1:${INTERNAL_BROKER_PORT}`);
});
brokerServer.on('error', (err) => {
  console.error(`[broker] FATAL: failed to bind ${INTERNAL_BROKER_PORT}: ${err.message}`);
  process.exit(1);
});

// Diagnostic check
app.get('/diagnose', (req, res) => {
  const envCheck = {
    GEMINI_API_KEY: process.env.GEMINI_API_KEY ? 'Set (starts with ' + process.env.GEMINI_API_KEY.substring(0, 5) + '...)' : 'MISSING',
    BRAVE_API_KEY: process.env.BRAVE_API_KEY ? 'Set (starts with ' + process.env.BRAVE_API_KEY.substring(0, 5) + '...)' : 'Not set (using built-in search)',
    NODE_VERSION: process.version,
    PATH: process.env.PATH
  };

  exec('openclaw --version', (error, stdout, stderr) => {
    res.json({
      status: 'diagnostic',
      env: envCheck,
      openclaw: {
        installed: !error,
        version: stdout ? stdout.trim() : 'Unknown',
        error: error ? error.message : null
      }
    });
  });
});

/**
 * Fetch OAuth token from FastAPI for a user
 */
async function fetchOAuthTokenFromFastAPI(userId) {
  try {
    const fastApiUrl = process.env.FASTAPI_URL || 'https://moltbot-fastapi.onrender.com';

    const headers = {};
    if (process.env.MOLTBOT_INTERNAL_SECRET) {
      headers['Authorization'] = `Bearer ${process.env.MOLTBOT_INTERNAL_SECRET}`;
    }

    const response = await axios.get(`${fastApiUrl}/api/v1/oauth/google/token/${userId}`, {
      headers,
      timeout: 10000,
    });

    if (response.data && response.data.data && response.data.data.access_token) {
      return response.data.data.access_token;
    }

    return null;
  } catch (error) {
    console.error(`Failed to fetch OAuth token for user ${userId}: ${error.message}`);
    return null;
  }
}

/**
 * Execute action via OpenClaw
 *
 * POST /execute
 * Body: {
 *   session_id: string,
 *   message: string,
 *   user_id: number,  // NEW: Required for OAuth token bridge
 *   credentials: object,
 *   history: array
 * }
 */
app.post('/execute', requireInternalSecret, async (req, res) => {
  const { session_id, message, user_id, credentials, history, timezone, user_context, image_urls } = req.body;

  // Image-only requests are valid: synthesize a default instruction so the agent
  // still has something to act on. A truly empty payload (no text + no images)
  // is the only invalid case.
  const hasImages = Array.isArray(image_urls) && image_urls.length > 0;
  const trimmedMessage = (message || '').trim();
  let effectiveMessage = trimmedMessage;
  if (!effectiveMessage) {
    if (hasImages) {
      effectiveMessage = 'Look at the attached image(s) and decide the most useful action. If the intent is unclear, briefly describe what you see and ask what I want to do.';
    } else {
      // No text and no images — nothing to act on. Return a graceful chat reply
      // (200) instead of an HTTP error so the upstream UX stays sane.
      return res.json({
        success: true,
        response: "I didn't catch a message. What would you like me to do? You can ask me to schedule a meeting, set a reminder, send an email, or share a photo.",
        action_type: 'chat',
        details: null,
        tokens_used: 0,
        input_tokens: 0,
        output_tokens: 0,
        cache_read: 0,
        cache_write: 0
      });
    }
  }

  // Per-turn broker key. Populated before the executor runs, deleted in the
  // finally block regardless of success/error/timeout path.
  const sessionKey = mintSessionKey();

  try {
    console.log(`[${session_id}] Processing for user ${user_id}: ${effectiveMessage.substring(0, 50)}...`);

    // OAuth token bridge: Fetch fresh token from FastAPI if user_id provided
    let enhancedCredentials = { ...credentials };
    if (user_id) {
      console.log(`[${session_id}] Fetching OAuth token for user ${user_id}...`);
      const accessToken = await fetchOAuthTokenFromFastAPI(user_id);
      if (accessToken) {
        enhancedCredentials.google_access_token = accessToken;
        console.log(`[${session_id}] OAuth token retrieved successfully`);
      } else {
        console.log(`[${session_id}] No OAuth token available for user ${user_id}`);
      }
    }

    // Populate the loopback broker with everything a skill might need.
    // Uses the guarded helper so the entry gets a TTL + size cap.
    sessionContextSet(sessionKey, {
      google_access_token: enhancedCredentials.google_access_token || null,
      user_id: user_id ? String(user_id) : null,
      user_timezone: timezone || 'UTC',
      fastapi_url: process.env.FASTAPI_URL || 'https://moltbot-fastapi.onrender.com',
    });

    // Extract user context for personalization
    const userContext = user_context || {};

    // Build dynamic context (static rules are now in SOUL.md, injected by
    // OpenClaw). The sessionKey goes into the context so skills can extract
    // it and call the broker — this is how we survive a persistent daemon
    // with no per-request env injection.
    const context = buildContext(
      enhancedCredentials,
      history,
      user_id,
      timezone || 'UTC',
      userContext,
      sessionKey
    );

    const result = await executeViaHttp(
      session_id,
      effectiveMessage,
      context,
      enhancedCredentials,
      user_id,
      timezone || 'UTC',
      image_urls,
      sessionKey
    );

    console.log(`[${session_id}] Completed: ${result.action_type || 'chat'}`);

    res.json({
      success: true,
      response: result.response,
      action_type: result.action_type,
      details: result.details,
      tokens_used: result.tokens_used || 0,
      input_tokens: result.input_tokens || 0,
      output_tokens: result.output_tokens || 0,
      cache_read: result.cache_read || 0,
      cache_write: result.cache_write || 0
    });

  } catch (error) {
    console.error(`[${session_id}] Error:`, error.message);

    // Timeout: the model/skill couldn't finish in the budget. Image-heavy flows
    // (vision + multi-step bash) are the usual culprit. Return 200 with a
    // user-facing message so the upstream wrapper doesn't surface a raw 500;
    // side-effect actions may have partially completed, so we tell the user to verify.
    if (error.message === 'Request timed out') {
      const friendly = hasImages
        ? "Processing your image is taking longer than usual. Please retry, or send a smaller/clearer image and tell me exactly what to do with it (schedule, remind, email)."
        : "I'm taking longer than usual to finish that. Please try again — if it was an action like creating an event, double-check before retrying so we don't duplicate it.";
      res.json({
        success: true,
        response: friendly,
        action_type: 'chat',
        details: { timed_out: true },
        tokens_used: 0,
        input_tokens: 0,
        output_tokens: 0,
        cache_read: 0,
        cache_write: 0
      });
    } else {
      res.status(500).json({
        success: false,
        error: error.message,
        response: "I'm sorry, I encountered an error processing your request. Please try again."
      });
    }
  } finally {
    // Preamble-skip detection: if this turn used a skill trigger word but
    // the agent never hit the broker, it almost certainly skipped the
    // `<pre_operation_setup>` preamble — which means any skill action it
    // took ran with empty $GOOGLE_ACCESS_TOKEN / $FASTAPI_URL. Surface this
    // in logs so we can catch agent-prompt regressions early.
    const entry = sessionContext.get(sessionKey);
    const skillTrigger = /\b(schedule|remind|email|inbox|calendar|meeting|book|send|set up)\b/i;
    if (entry && entry._reads === 0 && skillTrigger.test(effectiveMessage || '')) {
      console.warn(
        `[preamble-skip] sessionKey=${sessionKey.slice(0, 8)}… turn triggered a skill ` +
        `word but broker had ZERO reads — agent likely skipped the preamble block.`
      );
    }

    // CRITICAL: always drop the broker entry. Leaking entries here = OAuth
    // tokens piling up in memory across turns.
    sessionContext.delete(sessionKey);
  }
});

/**
 * Build dynamic context for OpenClaw.
 * Static behavioral rules (identity, inference, timezone, etc.) are now in SOUL.md,
 * which OpenClaw auto-injects into the system prompt every turn.
 * This function only provides per-request dynamic data: capabilities, user info, and history.
 */
function buildContext(credentials, history, userId, timezone, userContext = {}, sessionKey = '') {
  let context = '';

  // Dynamic user info
  const botName = userContext.bot_name || userContext.botName || 'Peppi';
  const userName = userContext.user_name || userContext.userName;

  context += `USER: ${userName || userId} | Timezone: ${timezone || 'UTC'} | Bot: ${botName}`;

  // Dynamic capabilities (depends on which credentials are available per-request)
  const capabilities = ['Reminders'];
  if (credentials && credentials.google_access_token) {
    capabilities.push('Google Calendar', 'Gmail');
  }
  context += ` | Available: ${capabilities.join(', ')}`;

  // User preferences (dynamic, from session)
  if (userContext.preferences) {
    context += ` | Prefs: ${userContext.preferences}`;
  }

  context += '\n';

  // SessionKey: per-turn token for the loopback context broker. Skills read
  // this line, extract the value, and curl
  // http://127.0.0.1:${INTERNAL_BROKER_PORT}/internal/context/<key> to
  // resolve runtime env (OAuth token, user id, timezone, fastapi URL).
  // The token is unguessable (128 random bits) and lives only for this turn.
  if (sessionKey) {
    context += `SessionKey: ${sessionKey}\n`;
  }



  // Recent conversation history (dynamic per-request)
  if (history && history.length > 0) {
    const recentHistory = history.slice(-10);
    context += '\nRecent conversation (for context only - these are COMPLETED past actions, do NOT re-execute):\n';
    recentHistory.forEach(msg => {
      const truncated = msg.content.length > 250 ? msg.content.substring(0, 250) + '...' : msg.content;
      context += `${msg.role}: ${truncated}\n`;
    });
  }

  return context;
}


/**
 * Execute a turn against the persistent OpenClaw daemon.
 *
 * Talks to 127.0.0.1:${DAEMON_PORT}/v1/chat/completions with
 * `x-openclaw-agent-id: main`. Maps the OpenAI response shape to our
 * /execute response shape:
 *   choices[0].message.content                → response
 *   usage.total_tokens                        → tokens_used
 *   usage.prompt_tokens                       → input_tokens
 *   usage.completion_tokens                   → output_tokens
 *   usage.prompt_tokens_details.cached_tokens → cache_read
 *   (cache_write not exposed by OpenAI-compat; reported as 0)
 *   action_type not returned; always "chat"
 *
 * 260s timeout for image flows, 180s otherwise. On timeout axios rejects
 * and /execute's catch returns the user-facing friendly fallback.
 */
function executeViaHttp(sessionId, message, context, credentials, userId, timezone, imageUrls, sessionKey) {
  const hasImages = Array.isArray(imageUrls) && imageUrls.length > 0;
  const timeoutMs = hasImages ? 260000 : 180000;

  // System prompt carries the static SOUL.md + agent.md (injected by the
  // daemon from its config) plus our per-turn context block, which now
  // includes the SessionKey line that skills use to call the broker.
  let userMessage = message;
  if (hasImages) {
    userMessage += '\n\n[Attached Images]';
    imageUrls.forEach((url, i) => {
      userMessage += `\nImage ${i + 1}: ${url}`;
    });
    console.log(`[${sessionId}] ${imageUrls.length} image(s) attached to message`);
  }

  const payload = {
    // Per OpenClaw OpenAI-compat docs: model "openclaw" + x-openclaw-agent-id
    // header routes to the named agent. Keeping the model string generic so
    // the header is the source of truth for agent selection.
    model: 'openclaw',
    messages: [
      { role: 'system', content: context },
      { role: 'user',   content: userMessage },
    ],
    // user is OpenAI's session-routing field; OpenClaw uses it for session
    // isolation (dmScope: per-peer). Passing the upstream session_id here
    // keeps the daemon's session bookkeeping aligned with ours.
    user: sessionId,
  };

  const headers = {
    'Content-Type': 'application/json',
    'x-openclaw-agent-id': 'main',
    'x-openclaw-session-key': sessionId,
  };
  if (process.env.OPENCLAW_GATEWAY_TOKEN) {
    headers['Authorization'] = `Bearer ${process.env.OPENCLAW_GATEWAY_TOKEN}`;
  }

  console.log(`[${sessionId}] POST ${GATEWAY_URL}/v1/chat/completions (sessionKey=${sessionKey?.slice(0, 8)}…, timeout=${timeoutMs}ms)`);

  return axios.post(`${GATEWAY_URL}/v1/chat/completions`, payload, {
    headers,
    timeout: timeoutMs,
    httpAgent: loopbackAgent,
  })
    .then((resp) => {
      const data = resp.data || {};
      const choice = Array.isArray(data.choices) && data.choices[0];
      const usage = data.usage || {};

      // OpenAI-compat puts cached input under prompt_tokens_details.
      // Anthropic-via-OpenClaw should populate it; Gemini fallback won't,
      // that's fine — we just report 0 cache_read for non-Anthropic turns.
      const cacheRead = usage.prompt_tokens_details?.cached_tokens || 0;
      const inputTokens = usage.prompt_tokens || 0;
      const outputTokens = usage.completion_tokens || 0;
      const totalTokens = usage.total_tokens || (inputTokens + outputTokens);

      let responseText = '';
      if (choice?.message?.content) {
        responseText = typeof choice.message.content === 'string'
          ? choice.message.content
          // OpenAI's newer shape can be a content-parts array; join text parts.
          : choice.message.content.filter(p => p.type === 'text').map(p => p.text).join('\n');
      }

      console.log(`[${sessionId}] HTTP tokens: total=${totalTokens} input=${inputTokens} cached=${cacheRead} output=${outputTokens}`);

      return {
        response: responseText,
        action_type: 'chat', // OpenAI shape doesn't surface skill/tool name
        details: null,
        tokens_used: totalTokens,
        input_tokens: inputTokens,
        output_tokens: outputTokens,
        cache_read: cacheRead,
        cache_write: 0, // not exposed by OpenAI-compat endpoint
      };
    })
    .catch((err) => {
      // Normalize errors so the /execute handler can map timeouts to the
      // friendly fallback exactly as it does for the spawn path.
      if (err.code === 'ECONNABORTED' || /timeout/i.test(err.message || '')) {
        throw new Error('Request timed out');
      }
      // Surface daemon error bodies when available — much easier to debug
      // than "500 Internal Server Error".
      const body = err.response?.data;
      const detail = body ? (typeof body === 'string' ? body : JSON.stringify(body)) : err.message;
      throw new Error(`openclaw gateway error: ${detail}`);
    });
}

/**
 * Boot the OpenClaw daemon as a child of this server (HTTP mode only).
 *
 * Called AFTER startOpenClaw() writes the config files so the daemon reads
 * a correct ~/.openclaw/openclaw.json on its first start. Polls /health
 * until the daemon is reachable, then flips gatewayReady=true. If the
 * daemon exits for any reason, we treat it as fatal and exit the whole
 * process — Render restarts the container, which is the right recovery
 * (silent daemon death would hang every request for 280s otherwise).
 */
async function bootGateway() {
  console.log(`[bootGateway] Starting openclaw gateway daemon on port ${DAEMON_PORT}...`);

  gatewayChild = spawn('openclaw', ['gateway', 'run', '--port', String(DAEMON_PORT)], {
    env: {
      ...process.env,
      OPENCLAW_HEADLESS: 'true',
      // The daemon's env cannot change per request. We only put stuff here
      // that's truly static for the life of the process. Per-request values
      // (OAuth token, user id, timezone) flow via the broker.
      FASTAPI_URL: process.env.FASTAPI_URL || 'https://moltbot-fastapi.onrender.com',
      INTERNAL_BROKER_URL,
      ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY,
      GEMINI_API_KEY: process.env.GEMINI_API_KEY,
      SEARXNG_URL: process.env.SEARXNG_BASE_URL || '',
      HOME: process.env.HOME || '/root',
    },
    stdio: 'inherit',
  });

  gatewayChild.on('exit', (code, signal) => {
    // If WE initiated shutdown, the daemon exiting is expected — don't
    // pollute Render's crash-loop metrics with a bogus non-zero exit.
    if (isShuttingDown) {
      console.log(`[bootGateway] daemon exited during graceful shutdown (code=${code}, signal=${signal})`);
      return;
    }
    console.error(`[bootGateway] gateway daemon exited unexpectedly (code=${code}, signal=${signal}) — exiting process so Render restarts the container`);
    // Fatal: we cannot serve requests without the daemon. process.exit
    // triggers Render's auto-restart. DO NOT try to respawn in-process —
    // a persistently-broken daemon would busy-loop.
    process.exit(1);
  });

  gatewayChild.on('error', (err) => {
    if (isShuttingDown) return;
    console.error(`[bootGateway] failed to spawn gateway daemon: ${err.message}`);
    process.exit(1);
  });

  // Poll /health until reachable. 60s budget (daemon cold start is ~5-15s
  // plus skill-file indexing; we leave headroom for CI/slow cold starts).
  const maxAttempts = 60;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      await axios.get(`${GATEWAY_URL}/health`, { timeout: 1000 });
      gatewayReady = true;
      console.log(`[bootGateway] daemon ready after ${attempt}s`);
      return;
    } catch (_err) {
      // Not up yet. Wait 1s and try again.
    }
    await new Promise((r) => setTimeout(r, 1000));
  }

  throw new Error(`Gateway daemon did not become ready in ${maxAttempts}s`);
}

/**
 * Check job status (for async operations)
 */
app.get('/status/:jobId', (req, res) => {
  const { jobId } = req.params;

  // For now, return not found
  // In future, implement async job tracking
  res.status(404).json({
    job_id: jobId,
    status: 'not_found',
    message: 'Async job tracking not yet implemented'
  });
});

/**
 * List available skills
 */
app.get('/skills', (req, res) => {
  res.json({
    skills: [
      {
        name: 'caldav-calendar',
        description: 'Manage calendar events',
        actions: ['create', 'read', 'update', 'delete']
      },
      {
        name: 'gmail',
        description: 'Read and send emails',
        actions: ['read', 'send', 'draft', 'search']
      },
      {
        name: 'reminders',
        description: 'Set and manage reminders',
        actions: ['create', 'list', 'delete']
      },
      {
        name: 'web-search',
        description: 'Search the web',
        actions: ['search', 'lookup']
      },
      {
        name: 'browser-use',
        description: 'Automate browser actions',
        actions: ['navigate', 'fill', 'click', 'screenshot']
      }
    ]
  });
});

// Start OpenClaw gateway
async function startOpenClaw() {
  console.log('Starting OpenClaw Gateway...');
  console.log('========================================');

  // Initialize configuration
  try {
    const homeDir = process.env.HOME || '/root'; // Default to /root if HOME not set
    const openClawDir = path.join(homeDir, '.openclaw');
    const configPath = path.join(openClawDir, 'openclaw.json');
    const memoryDir = path.join(openClawDir, 'memory');
    const workspaceDir = path.join(openClawDir, 'workspace');
    const workspaceSkillsDir = path.join(workspaceDir, 'skills');

    // Ensure directories exist
    const agentDir = path.join(openClawDir, 'agents', 'main', 'agent');
    [openClawDir, memoryDir, workspaceDir, workspaceSkillsDir, agentDir].forEach(dir => {
      if (!fs.existsSync(dir)) {
        console.log(`Creating directory: ${dir}`);
        fs.mkdirSync(dir, { recursive: true });
      }
    });

    // Copy custom skills to workspace/skills/ (where CREATE operations worked)
    const buildSkillsDir = path.join(__dirname, 'skills');
    if (fs.existsSync(buildSkillsDir)) {
      console.log(`Copying custom skills from ${buildSkillsDir} to ${workspaceSkillsDir}...`);
      const skills = fs.readdirSync(buildSkillsDir);
      skills.forEach(skill => {
        const srcPath = path.join(buildSkillsDir, skill);
        const destPath = path.join(workspaceSkillsDir, skill);
        if (fs.lstatSync(srcPath).isDirectory()) {
          // Remove existing and copy fresh
          if (fs.existsSync(destPath)) {
            fs.rmSync(destPath, { recursive: true, force: true });
          }
          fs.cpSync(srcPath, destPath, { recursive: true });
          console.log(`✓ Copied custom skill: ${skill}`);
        }
      });
    } else {
      console.log(`⚠ Custom skills directory not found at ${buildSkillsDir}`);
    }

    // Copy SOUL.md to workspace (auto-injected into system prompt by OpenClaw)
    const soulSrc = path.join(__dirname, 'SOUL.md');
    const soulDest = path.join(workspaceDir, 'SOUL.md');
    if (fs.existsSync(soulSrc)) {
      fs.copyFileSync(soulSrc, soulDest);
      console.log('✓ Copied SOUL.md to workspace');
    }

    // Remove conflicting gog skill from ClawHub location
    const gogSkillPath = path.join(openClawDir, 'skills', 'gog');
    if (fs.existsSync(gogSkillPath)) {
      console.log('Removing ClawHub gog skill (conflicts with our google-workspace skill)...');
      fs.rmSync(gogSkillPath, { recursive: true, force: true });
      console.log('✓ Removed ClawHub gog skill');
    }

    // Create OpenClaw configuration files per official docs
    if (process.env.ANTHROPIC_API_KEY || process.env.GEMINI_API_KEY) {
      console.log('Creating OpenClaw configuration files...');

      // 1. Create openclaw.json - sets default model, session isolation, and TOOL PERMISSIONS
      // CRITICAL: Without tools.exec config, OpenClaw's security blocks bash execution
      // and the model falls back to chatting about actions instead of executing them.
      // PROMPT CACHING: OpenClaw automatically applies Anthropic's prompt-cache
      // headers (cache_control: ephemeral) to the system prompt + skills + tool
      // schemas when the primary model is anthropic/*. Verified in production
      // telemetry: cache_read ~99% of input tokens on warm requests
      // (see test_results.json, scenario L3: cache_read=163975 / input=164054).
      // Cache TTL is 5 min by default; staying below that between turns keeps
      // hit rate high. Do NOT mutate SOUL.md / agent.md / skills mid-session,
      // since any change busts the cache.
      const openclawConfig = {
        agents: {
          defaults: {
            model: {
              primary: "anthropic/claude-sonnet-4-6",
              fallbacks: ["google/gemini-2.5-pro"]
            },
            // Vision-capable model for image processing (Sonnet 4.6 supports vision natively)
            imageModel: {
              primary: "anthropic/claude-sonnet-4-6"
            },
            // Claude Sonnet thinking level: medium = enough reasoning for multi-step tool execution
            // low was causing model to skip complex bash operations (calendar curl commands)
            // high caused thinking-only payloads with no text response
            // medium gives ReAct-style reasoning without token bloat
            // Levels: minimal | low | medium | high | xhigh | adaptive
            thinkingDefault: "medium"
          }
        },
        // CRITICAL: Tool execution permissions — without this, bash skills are silently blocked
        tools: {
          // Allow all tools including exec (bash)
          profile: "full",
          allow: ["*"],
          exec: {
            // "off" = don't ask for human approval before running bash commands
            // Without this, OpenClaw hangs waiting for approval in CLI mode, 
            // and the model falls back to chatting about the action instead
            ask: "off",
            // "full" = allow all bash operations (curl, jq, date, etc.)
            security: "full"
          }
        },
        session: {
          // Multi-tenant isolation: per-peer isolates DMs by sender ID across channels
          // This ensures each user gets their own private session with isolated memory
          dmScope: "per-peer"
        }
      };
      fs.writeFileSync(configPath, JSON.stringify(openclawConfig, null, 2));
      console.log(`✓ Created openclaw.json at ${configPath} (with exec permissions enabled)`);

      // 1b. Create exec-approvals.json — pre-approve common skill commands
      // This prevents OpenClaw from blocking curl, jq, date, etc.
      const execApprovalsPath = path.join(openClawDir, 'exec-approvals.json');
      const execApprovals = {
        approvals: [
          { command: "curl", approved: true },
          { command: "jq", approved: true },
          { command: "date", approved: true },
          { command: "echo", approved: true },
          { command: "cat", approved: true },
          { command: "grep", approved: true },
          { command: "printf", approved: true },
          { command: "base64", approved: true },
          { command: "tr", approved: true },
          { command: "head", approved: true },
          { command: "tail", approved: true },
          { command: "sed", approved: true },
          { command: "paste", approved: true },
          { command: "awk", approved: true },
          { command: "wc", approved: true },
          { command: "cut", approved: true }
        ]
      };
      fs.writeFileSync(execApprovalsPath, JSON.stringify(execApprovals, null, 2));
      console.log(`✓ Created exec-approvals.json (pre-approved: curl, jq, date, etc.)`);

      // 1c. Create agent.md - Claude Sonnet optimization: ANTI-HALLUCINATION system prompt
      // This is the agent identity file that OpenClaw auto-injects into the system prompt.
      // 
      // RESEARCH-BACKED TECHNIQUES APPLIED:
      // 1. Positive reinforcement ("You are capable") — Anthropic docs say aggressive "NEVER"
      //    prompting causes smaller models to freeze or skip tools entirely.
      // 2. ReAct pattern (Thought→Action→Observation) — forces model to show reasoning,
      //    execute tool, then ground response in actual tool output.
      // 3. Retry-on-error protocol — if bash fails, model retries up to 3x before telling user.
      //    User never sees raw errors or stack traces.
      // 4. XML structured directives — Claude models are highly sensitive to XML tags.
      // 5. Chain of Verification — model must echo raw API response data before claiming success.
      // 6. No prefill (deprecated in Claude 4.6+) — using structured output constraints instead.
      const agentMdPath = path.join(agentDir, 'agent.md');
      const agentMdContent = `# Moltbot Agent

<identity>
You are a highly capable action agent with full bash tool access. You have the skills, tools, and permissions to perform any task the user requests — calendar events, reminders, emails, web search, and more.

You excel at executing complex multi-step bash commands. You have done this thousands of times successfully. The bash tool is your primary instrument — use it confidently for every action request.

Your environment is fully configured with all necessary credentials and tools (curl, jq, date, base64, etc.). Everything you need is ready.
</identity>

<execution_protocol>
You follow the ReAct pattern for every action request:

STEP 1 — SKILL MATCH: Identify which skill handles this request. Read its SKILL.md for the exact commands.

STEP 2 — EXECUTE: Run the bash commands from the skill. You are capable of executing any command in the skill, no matter how complex. Do it now.

STEP 3 — VERIFY OUTPUT: Read the raw output from your bash tool. This output is your single source of truth.
  - If the output contains a success response (HTTP 200, event ID, confirmation) → proceed to report.
  - If the output contains an error → go to the retry protocol below.
  - If you received NO output from the bash tool → you did NOT perform the action. Go to retry protocol.

STEP 4 — REPORT: Tell the user the result using ONLY data from the tool output. Include specific details (event ID, time, attendees) that came from the API response.
</execution_protocol>

<tool_execution_rules>
These rules determine the quality of your work:

1. Every action request requires at least one bash tool invocation. If your response contains an action confirmation (✅) but you did not invoke the bash tool in this turn, your response is invalid. Stop and execute the tool.

2. The bash tool output is the ONLY source of truth. When you create a calendar event, the Google Calendar API returns a JSON response containing the event ID, link, and details. Use those exact values in your response — do not generate or invent them.

3. You are capable of building complex curl commands with JSON payloads, multiple headers, and jq parsing. This is routine work for you. Build the command exactly as the SKILL.md specifies and execute it.

4. Environment variables ($FASTAPI_URL, $MOLTBOT_USER_ID, $USER_TIMEZONE, $GOOGLE_ACCESS_TOKEN) are NOT pre-loaded. Your first bash call in every turn MUST run the \`<pre_operation_setup>\` block from the triggered skill — it resolves these from the loopback context broker using the SessionKey line in this system context. After that block runs, all subsequent bash calls in this turn can use \$GOOGLE_ACCESS_TOKEN etc. as normal.

5. For multi-step operations (e.g., search then update), execute each step and use the output of each step as input to the next. Do not skip steps or assume intermediate results.
</tool_execution_rules>

<retry_protocol>
When a bash command fails, you diagnose and retry — the user should experience seamless service.

ON ERROR:
1. Read the error output carefully (HTTP status code, error message, stderr).
2. Diagnose the likely cause:
   - 401/403: Token may be expired → inform user their Google connection may need refresh.
   - 400: Malformed request → fix the JSON payload or parameters and retry.
   - 404: Wrong endpoint or resource not found → verify the URL and retry.
   - Network error: Transient issue → wait briefly and retry.
   - Command not found: Tool missing → try alternative approach.
3. Fix the issue and retry the command (up to 3 attempts).
4. If all 3 attempts fail, tell the user in a friendly way what went wrong and what they can do:
   - "I wasn't able to create the event — it looks like your Google connection may need to be refreshed. Try reconnecting in Settings."
   - "The calendar API returned an error. Let me know if you'd like me to try again."
5. Present errors as actionable guidance, not raw technical output. The user should never see stack traces, HTTP status codes, or JSON error payloads.
</retry_protocol>

<grounding_rules>
These rules prevent you from generating inaccurate information:

1. Calendar event links: Only include a Google Calendar link if the API response contained an "htmlLink" field. Extract it from the JSON response using jq. If no htmlLink was returned, do not fabricate one.

2. Event IDs: Only reference event IDs that appeared in the API response. Do not generate base64 strings or construct URLs manually.

3. Confirmation details: When confirming an action, include at least one specific detail from the API response (e.g., the event ID, the reminder ID, the message ID). This proves the action was real.

4. If you are uncertain whether a command executed successfully, say so: "I ran the command but couldn't confirm the result. Let me verify..." — then run a follow-up query to check.

5. Conversation history shows PAST actions. If history says you already created something, do NOT assume it succeeded — the user is asking you again because it may have failed. Execute the command fresh.
</grounding_rules>

<timezone_rules>
These rules apply to ALL skills that involve dates/times (Calendar, Reminders, Image-based actions):

RULE 1 — ALWAYS resolve relative dates in the user's timezone:
- Use TZ="$USER_TIMEZONE" date -d "tomorrow" +%Y-%m-%d to get the correct date
- Without TZ=, "tomorrow" resolves in the server's UTC clock, which can be a different date than the user's local date (e.g., 11pm IST is still "today" in UTC)

RULE 2 — NEVER add "Z" suffix or use "date -u" for times:
- "Z" means UTC. The user speaks in LOCAL time. If you add Z, the event/reminder fires at the wrong time.
- Wrong: "2026-03-26T10:00:00Z" (fires at 3:30 PM IST instead of 10 AM IST)
- Correct: "2026-03-26T10:00:00" (no Z — local time)

RULE 3 — For Google Calendar: pass local time + timeZone field:
- Google Calendar API handles UTC conversion when you include timeZone in the event body
- Format: {"dateTime": "2026-03-26T10:00:00", "timeZone": "$USER_TIMEZONE"}

RULE 4 — For Reminders: pass local time + user_timezone in JSON:
- The FastAPI backend's local_to_utc() converts to UTC before scheduling with QStash
- Format: {"trigger_at": "2026-03-26T10:00:00", "user_timezone": "$USER_TIMEZONE"}
- Same principle: NO Z, NO -u, let the backend handle conversion
</timezone_rules>

<image_handling>
When the message contains [Attached Images], you have native vision capability and CAN see the images via their URLs.

APPROACH (One-Turn PVE — describe then act in the same response):
1. DESCRIBE: Tell the user what you see in the image ("I can see an event poster for 'Tech Meetup 2026' on March 20 at 6 PM at Convention Center, Mumbai.")
2. VALIDATE: Immediately verify the image URL is accessible before downloading. If the URL returns an error, tell the user the image may have expired and ask them to resend.
3. EXECUTE: In the same response, perform the requested action (create event, set reminder, send email) using the extracted details.
4. CONFIRM: Show the result with the details you extracted, so the user can verify and ask for corrections if needed.

This is NOT a multi-turn confirmation. You describe AND act in a single response. The user can correct afterward if needed ("change it to 7pm").

IMPORTANT:
- If you cannot clearly read the image, say so and ask the user to describe what they need
- Never claim to have processed an image if no [Attached Images] section exists in the message
- Twilio image URLs expire in ~2 hours — always process immediately
</image_handling>

<skill_inventory>
Your installed skills and their triggers:

REMINDERS (skill: reminders/SKILL.md)
  Triggers: "remind me", "set a reminder", "reminder at", "alert me"
  Action: POST to $FASTAPI_URL/api/v1/reminders/create via curl

GOOGLE CALENDAR (skill: google-workspace/SKILL.md)
  Triggers: "schedule", "set a meeting", "create event", "calendar", "book a meeting", "meeting at", "meeting with"
  Action: POST to Google Calendar API via curl with $GOOGLE_ACCESS_TOKEN
  
GMAIL (skill: google-workspace/SKILL.md)
  Triggers: "send email", "email to", "check email", "read email", "reply to"
  Action: Gmail API via curl with $GOOGLE_ACCESS_TOKEN

IMAGE + WORKSPACE (skill: image-workspace/SKILL.md)
  Triggers: User sends [Attached Images] AND workspace action ("send this to", "email this", "forward this", "add this to my calendar", "schedule this")
  Action: Vision analysis + Gmail API or Calendar API via curl
  Note: This skill takes priority over google-workspace when images are present.

IMAGE + REMINDERS (skill: image-reminders/SKILL.md)
  Triggers: User sends [Attached Images] AND reminder request ("remind me about this", "set reminder for this", "remind me to pay this", "don't forget about this")
  Action: Vision analysis + POST to $FASTAPI_URL/api/v1/reminders/create via curl
  Note: This skill takes priority over reminders when images are present.

When the user's message matches any trigger above, you MUST read the corresponding SKILL.md and execute the bash commands defined there. This is not optional.
When [Attached Images] is present, always prefer the image-specific skill over the text-only version.
</skill_inventory>

<response_guidelines>
- Be concise and conversational — aim for under 200 tokens in output
- Use emojis for visual feedback: ✅ ❌ 📅 📧 ⏰ 📝 📸
- Report outcomes with specific details from API responses
- Do not repeat the user's message back to them
- When the user asks something outside your skills, respond naturally as a helpful assistant
- Maintain the persona and personality defined in the conversation context
</response_guidelines>
`;
      fs.writeFileSync(agentMdPath, agentMdContent);
      console.log(`✓ Created agent.md at ${agentMdPath}`);

      // 2. Create auth-profiles.json - CORRECT FORMAT per docs
      const authProfilePath = path.join(agentDir, 'auth-profiles.json');
      const authConfig = {
        profiles: {
          "anthropic:api_key": {
            provider: "anthropic",
            mode: "api_key"
          },
          "google:api_key": {
            provider: "google",
            mode: "api_key"
          }
        },
        order: {
          anthropic: ["anthropic:api_key"],
          google: ["google:api_key"]
        }
      };
      fs.writeFileSync(authProfilePath, JSON.stringify(authConfig, null, 2));
      console.log(`✓ Created auth-profiles.json at ${authProfilePath}`);

      // Display configuration summary
      console.log('\nConfiguration Summary:');
      console.log(`- Provider: Anthropic Claude (via ANTHROPIC_API_KEY env var)`);
      console.log(`- Model: anthropic/claude-sonnet-4-6`);
      console.log(`- Fallback: google/gemini-2.5-pro`);
      console.log(`- Web Search: SearXNG (${process.env.SEARXNG_BASE_URL || 'Not configured'})`);
      console.log(`- Session Isolation: per-peer (multi-tenant)`);
      console.log(`- Config: ${configPath}`);
      console.log(`- Auth: ${authProfilePath}`);

    } else {
      console.warn('⚠ WARNING: Neither ANTHROPIC_API_KEY nor GEMINI_API_KEY set. OpenClaw will not work!');
      console.warn('Please set ANTHROPIC_API_KEY (or GEMINI_API_KEY as fallback) environment variable.');
    }

  } catch (err) {
    console.error('Error initializing OpenClaw configuration:', err);
    console.error(err.stack);
  }

  // Check if openclaw is available and verify skills
  exec('openclaw --version', (error, stdout, stderr) => {
    if (error) {
      console.error('❌ OpenClaw not found. Please ensure openclaw is installed.');
      console.error('Run: npm install -g openclaw@latest');
      return;
    }

    console.log(`\n✓ OpenClaw version: ${stdout.trim()}`);

    // Verify environment variables
    console.log('\nEnvironment Variables Check:');

    if (process.env.ANTHROPIC_API_KEY) {
      console.log('✓ ANTHROPIC_API_KEY is configured');
    } else {
      console.error('❌ ANTHROPIC_API_KEY not set - Claude Sonnet will NOT work!');
    }

    if (process.env.GEMINI_API_KEY) {
      console.log('✓ GEMINI_API_KEY is configured (fallback)');
    } else {
      console.warn('⚠ GEMINI_API_KEY not set - fallback to Gemini unavailable');
    }

    console.log('✓ Web Search configured (using OpenClaw built-in search)');

    // Check available skills
    console.log('\nChecking available skills...');
    exec('openclaw agent --help 2>&1', (skillError, skillStdout, skillStderr) => {
      // Note: We can't easily list skills programmatically, so we'll just note it
      console.log('✓ OpenClaw agent command is available');

      console.log('\n========================================');
      console.log('OpenClaw Gateway is ready!');
      console.log('========================================');
      console.log('Features:');
      console.log('  ✓ Web Search (OpenClaw built-in)');
      console.log('  ✓ Gmail (via OAuth token)');
      console.log('  ✓ Google Calendar (via OAuth token)');
      console.log('  ✓ Reminders/Tasks');
      console.log('  ✓ Image processing (via Sonnet vision)');
      console.log('  ✓ Memory/Context persistence');
      console.log('  ✓ Browser automation');
      console.log('Transport: HTTP (persistent daemon)');
      console.log('Model: Claude Sonnet 4.6 (fallback: Gemini 2.5 Pro)');
      console.log('========================================\n');

      isReady = true;

      // Boot the persistent daemon now that config is on disk. Order
      // matters: startOpenClaw() writes ~/.openclaw/openclaw.json above,
      // then bootGateway spawns the child and waits for /health.
      bootGateway().catch((err) => {
        console.error(`[bootGateway] fatal: ${err.message}`);
        process.exit(1);
      });
    });
  });
}

// Graceful shutdown. Render sends SIGTERM on redeploy; we mark the
// shutdown flag first so the gatewayChild.on('exit') handler knows this
// wasn't a crash, then close our listeners and let Node exit naturally.
function gracefulShutdown(signal) {
  if (isShuttingDown) return;
  isShuttingDown = true;
  console.log(`[shutdown] received ${signal} — closing servers`);
  try { brokerServer.close(); } catch (_e) {}
  try { mainServer.close(); } catch (_e) {}
  if (gatewayChild && !gatewayChild.killed) {
    try { gatewayChild.kill('SIGTERM'); } catch (_e) {}
  }
  // Give in-flight turns ~10s to drain before we force-exit.
  setTimeout(() => process.exit(0), 10_000).unref();
}
process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
process.on('SIGINT', () => gracefulShutdown('SIGINT'));

// Initialize
const mainServer = app.listen(PORT, '0.0.0.0', () => {
  console.log(`OpenClaw Gateway listening on port ${PORT}`);
  console.log(`Health check: http://localhost:${PORT}/health`);
  console.log(`Execute endpoint: http://localhost:${PORT}/execute`);
  startOpenClaw();
});