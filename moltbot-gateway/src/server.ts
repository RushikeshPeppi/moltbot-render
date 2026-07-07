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

import express, { Request, Response } from "express";
import { randomUUID } from "node:crypto";
import { env, validateEnv } from "./env.js";
import { runAgentLoop } from "./agent.js";
import { getSession, setSessionHistory, sessionCount } from "./session.js";
import { fetchGoogleToken } from "./oauth.js";
import { requireServiceAuth } from "./auth.js";
import { logError } from "./observability.js";

validateEnv();

const app = express();
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
    city: body.user_context?.city,
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
