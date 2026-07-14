/**
 * Express server — /execute and /health endpoints.
 *
 * Wire format with FastAPI is preserved exactly from the OpenClaw era so the
 * upstream `moltbot_client.py` doesn't need changes:
 *   POST /execute
 *   body: { session_id, message, user_id, credentials, history, timezone, user_context, image_urls }
 *   resp: {
 *     success, response, action_type,
 *     tokens_used, input_tokens, output_tokens, cache_read, cache_write,
 *     reminder_trigger_at,
 *     _meta: { iterations, tool_calls, request_id }
 *   }
 */

import express, { NextFunction, Request, Response } from "express";
import { randomUUID } from "node:crypto";
import { env, validateEnv } from "./env.js";
import { runAgentLoop } from "./agent.js";
import { getSession, setSessionHistory, sessionCount } from "./session.js";
import { fetchGoogleToken } from "./oauth.js";
import { requireServiceAuth } from "./auth.js";
import { logError } from "./observability.js";
import { securityHeaders } from "./security-headers.js";

validateEnv();

const app = express();

// Stop advertising the framework + version (ZAP [10037], CASA 6.2.1 fingerprinting).
app.disable("x-powered-by");

// Security headers FIRST, so every response carries them — including the 401 from
// requireServiceAuth, the 413 from the body cap, and error responses (CASA 4.1.1/5.1.7).
app.use(securityHeaders);

app.use(express.json({ limit: "5mb" })); // headroom for image-attached payloads

// ─── Health ────────────────────────────────────────────────────────────

app.get("/health", (_req: Request, res: Response) => {
  // Fail the health check (→ Render rolls back the deploy) if the service key is
  // unset: without it, requireServiceAuth 503s every /execute, and we do NOT want
  // a deploy that silently rejects all real traffic to look healthy. Mirrors the
  // FastAPI wrapper's agent_md_ready gate.
  const serviceKeyReady = !!env.INTERNAL_SERVICE_KEY;
  res.status(serviceKeyReady ? 200 : 503).json({
    status: serviceKeyReady ? "online" : "degraded",
    service: "moltbot-gateway",
    version: "2.0.0",
    sessions: sessionCount(),
    env: {
      anthropic: !!env.ANTHROPIC_API_KEY,
      fastapi: !!env.FASTAPI_URL,
      searxng: !!env.SEARXNG_URL,
      helicone: env.HELICONE_PROXY,
      internal_key: serviceKeyReady,
    },
  });
});

// Diagnostic for Render's request log
app.get("/", (_req: Request, res: Response) => {
  res.json({ ok: true, service: "moltbot-gateway-v2-sdk" });
});

// ─── /execute ──────────────────────────────────────────────────────────

interface ExecuteBody {
  session_id?: string;
  message?: string;
  user_id?: string;
  credentials?: { google_access_token?: string };
  history?: unknown[]; // unused — we maintain our own session history
  timezone?: string;
  user_context?: { city?: string; bot_name?: string; user_name?: string };
  image_urls?: string[];
}

// Names and city are end-user-controlled text that lands inside the single-line
// context anchor, so they must not be able to break out of it or forge its
// segments: strip the anchor's own delimiters ([ ] ; and the key separator :)
// and newlines, collapse whitespace, cap length (names: 50, matching Peppi's
// max:50 buddy validation; city gets 80 for "City, Long Country Name" strings).
function sanitizeName(v: unknown, max = 50): string | undefined {
  if (typeof v !== "string") return undefined;
  const clean = v
    .replace(/[[\];:\r\n]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, max)
    // The 50-unit slice can split an emoji's surrogate pair (Laravel's max:50
    // counts an emoji as 1 char, UTF-16 as 2), and JSON can smuggle lone
    // surrogates directly — either way an ill-formed string 400s at the
    // Anthropic API on EVERY call for this user until they rename the buddy.
    // Drop lone surrogate halves (valid pairs are untouched).
    .replace(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/g, "")
    .trim();
  return clean || undefined;
}

app.post("/execute", requireServiceAuth, async (req: Request, res: Response) => {
  const requestId = randomUUID();
  const body = (req.body ?? {}) as ExecuteBody;
  const sessionId = body.session_id ?? "";
  const userId = body.user_id ?? sessionId;

  // Validate.
  const message = (body.message ?? "").trim();
  const imageUrls = Array.isArray(body.image_urls) ? body.image_urls : [];
  if (!message && imageUrls.length === 0) {
    res.json({
      success: true,
      response:
        "I didn't catch a message. What would you like me to do? I can schedule meetings, set reminders, send emails, or work with photos you send me.",
      action_type: "chat",
      tokens_used: 0,
      input_tokens: 0,
      output_tokens: 0,
      cache_read: 0,
      cache_write: 0,
      reminder_trigger_at: null,
      _meta: { iterations: 0, tool_calls: [], request_id: requestId },
    });
    return;
  }

  if (!userId) {
    res.status(400).json({ success: false, error: "user_id required", request_id: requestId });
    return;
  }

  const peerKey = userId; // session per user (matches OpenClaw's per-peer scoping)
  const session = getSession(peerKey);

  // Resolve the Google OAuth token SERVER-SIDE only. A caller-supplied
  // credentials.google_access_token is an injection vector (act as an arbitrary
  // user with a token you bring), so it is deliberately ignored — the token is
  // always fetched from the wrapper for the authenticated user_id (P0-3).
  const googleAccessToken: string | undefined = userId
    ? ((await fetchGoogleToken(userId)) ?? undefined)
    : undefined;

  const ctx = {
    userId,
    googleAccessToken,
    timezone: body.timezone ?? "UTC",
    city: sanitizeName(body.user_context?.city, 80),
    botName: sanitizeName(body.user_context?.bot_name),
    userName: sanitizeName(body.user_context?.user_name),
    fastApiUrl: env.FASTAPI_URL,
    searxngUrl: env.SEARXNG_URL,
    tavilyApiKeys: env.TAVILY_API_KEYS,
    requestId,
  };

  try {
    const result = await runAgentLoop(
      {
        sessionId,
        userId,
        userText: message,
        imageUrls: imageUrls.length > 0 ? imageUrls : undefined,
        ctx,
      },
      session,
    );

    setSessionHistory(peerKey, session.history);

    res.json({
      success: true,
      response: result.reply,
      action_type: result.actionType,
      tokens_used: result.tokens.total,
      input_tokens: result.tokens.input,
      output_tokens: result.tokens.output,
      cache_read: result.tokens.cacheRead,
      // Combined cache_write kept for backward compat with older FastAPI versions.
      // Prefer cache_write_5m / cache_write_1h for accurate billing — the rates
      // differ (5m = 1.25× input, 1h = 2× input).
      cache_write: result.tokens.cacheWrite5m + result.tokens.cacheWrite1h,
      cache_write_5m: result.tokens.cacheWrite5m,
      cache_write_1h: result.tokens.cacheWrite1h,
      reminder_trigger_at: result.reminderTriggerAt ?? null,
      _meta: {
        iterations: result.iterations,
        tool_calls: result.toolCalls,
        request_id: requestId,
      },
    });
  } catch (err) {
    logError(requestId, "agent_loop_failed", err);
    const msg = err instanceof Error ? err.message : "agent error";
    res.status(500).json({
      success: false,
      error: msg,
      request_id: requestId,
    });
  }
});

// ─── Error handler (must be LAST, and must take 4 args to be an error handler) ──
//
// body-parser rejects malformed JSON and >5mb bodies BEFORE any route runs, i.e. before
// requireServiceAuth — so this path is reachable UNAUTHENTICATED and its output is part of
// our public attack surface. Express's built-in handler renders `err.stack` as HTML unless
// NODE_ENV=production. Render happens to set that today (verified live: a malformed body
// returns a bare "Bad Request"), but leaving stack-trace suppression dependent on an
// implicit platform env var is exactly the fail-open pattern this phase exists to remove.
// Own the response: generic JSON, no stack, ever (CASA 6.2.1).
app.use((err: unknown, req: Request, res: Response, _next: NextFunction): void => {
  const e = err as { type?: string; status?: number };
  const requestId = randomUUID();
  logError(requestId, "request_rejected", err); // full detail server-side only

  if (res.headersSent) return;

  if (e?.type === "entity.too.large") {
    res.status(413).json({ success: false, error: "request body too large", request_id: requestId });
    return;
  }
  if (e?.type === "entity.parse.failed" || e?.status === 400) {
    res.status(400).json({ success: false, error: "malformed request body", request_id: requestId });
    return;
  }
  res.status(500).json({ success: false, error: "internal error", request_id: requestId });
});

// ─── Server bootstrap + SIGTERM drain ──────────────────────────────────

const server = app.listen(env.PORT, () => {
  console.log(
    `[server] moltbot-gateway-v2 listening on :${env.PORT} (Anthropic SDK, no OpenClaw)`,
  );
});

// Render sends SIGTERM with a configurable grace (we set maxShutdownDelaySeconds: 120).
// Stop accepting new requests immediately, finish in-flight, then exit.
let draining = false;
function gracefulShutdown(signal: string): void {
  if (draining) return;
  draining = true;
  console.log(`[server] ${signal} received — draining...`);
  server.close((err) => {
    if (err) {
      console.error(`[server] close error:`, err);
      process.exit(1);
    }
    console.log("[server] closed cleanly");
    process.exit(0);
  });
  // Hard stop after 110s if drain stalls (Render Pro grace = 120s, we leave 10s buffer).
  setTimeout(() => {
    console.warn("[server] drain timeout — forcing exit");
    process.exit(1);
  }, 110_000).unref();
}
process.on("SIGTERM", () => gracefulShutdown("SIGTERM"));
process.on("SIGINT", () => gracefulShutdown("SIGINT"));

// Don't crash the whole process on a single unhandled rejection — log and continue.
process.on("unhandledRejection", (reason) => {
  console.error("[server] unhandledRejection:", reason);
});
process.on("uncaughtException", (err) => {
  console.error("[server] uncaughtException:", err);
});
