/**
 * Core agent loop — direct Anthropic SDK, replaces OpenClaw subprocess.
 *
 * Pattern: Anthropic cookbook customer-service agent + Cline's anthropic.ts
 * provider, adapted for SMS-shaped webhook flow.
 *
 * Key design choices (all backed by research in PEPPI_DEEP_RESEARCH.md /
 * PEPPI_SDK_MIGRATION_RESEARCH.md):
 *
 *   1. Manual tool loop (`while (iter < MAX)`) — not toolRunner. SDK's toolRunner
 *      has open issue #922 (defaultHeaders dropped on follow-up) and we want
 *      explicit control over cache_control and parallel execution.
 *
 *   2. stop_reason switch handles all 6 values (end_turn, tool_use, max_tokens,
 *      refusal, stop_sequence, pause_turn). end_turn / tool_use are the hot path.
 *
 *   3. Parallel tool execution via Promise.all — Sonnet 4.6 emits parallel
 *      tool_use blocks for independent reads. Errors from any one tool become
 *      a tool_result with is_error: true so Claude can self-correct.
 *
 *   4. Cache control breakpoints (max 4 allowed, we use 2):
 *        bp1 (1h TTL) on system text — Anthropic's prefix walker is tools →
 *          system → messages, so this single breakpoint caches the entire
 *          (tools + system) prefix. agent.md only changes on deploy.
 *        bp2 (5m TTL) on last STABLE assistant turn — caches the conversation
 *          history up through the prior assistant reply. Resets each time the
 *          user sends a new message (current user turn stays uncached).
 *      Dynamic content (oauth, timestamps, image URLs) lives in the FRESH user
 *      message, AFTER all breakpoints — never busts cache.
 *
 *   5. MAX_TOOL_ITERATIONS = 6 — hard cap to prevent runaway loops. Real SMS
 *      compound flows top out at 3-4 iterations.
 *
 *   6. timeout: 90s — fails fast inside Render's 120s shutdown grace.
 *
 *   7. thinking off — Sonnet 4.6 with extended thinking on simple tasks is
 *      net-negative per Anthropic's own data.
 */

import Anthropic from "@anthropic-ai/sdk";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { TOOLS, dispatchTool, type ToolContext } from "./tools/index.js";
import type { Session } from "./session.js";
import { logCall } from "./observability.js";
import { env } from "./env.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

// ─── Client ────────────────────────────────────────────────────────────

const client = new Anthropic({
  apiKey: env.ANTHROPIC_API_KEY,
  // Built-in retry: 2 retries on connection errors / 408 / 409 / 429 / >=500.
  maxRetries: 2,
  // Default 10min — way too long for SMS. Tighten so we fail fast.
  timeout: 90 * 1000,
  // Optional Helicone proxy (free tier, observability)
  ...(env.HELICONE_PROXY
    ? {
        baseURL: "https://anthropic.helicone.ai",
        defaultHeaders: { "Helicone-Auth": `Bearer ${env.HELICONE_KEY}` },
      }
    : {}),
});

// ─── Constants ─────────────────────────────────────────────────────────

// Sonnet 4.6 — current generation as of 2026-05. The aliased ID auto-points at
// the latest dated build. Verified against @anthropic-ai/sdk Model type union.
const MODEL = "claude-sonnet-4-6";
const MAX_TOKENS = 1024;
const MAX_TOOL_ITERATIONS = 6;
const HISTORY_TURNS_KEPT = 20; // last 10 user/assistant pairs

// Tools that have side effects (creates / updates / sends). Within a single
// agent run, if the model emits two tool_use blocks with the SAME tool name
// and byte-identical args (a write fingerprint collision), only the first
// runs; the others get a synthetic tool_result telling the model the call
// was deduplicated. Belt-and-suspenders against the duplicate-write seen in
// 2026-05-06 eval (medium-chain-find-and-remind, req bbfccb7a). Reads
// (list / search / handle) are unaffected.
const WRITE_TOOLS = new Set<string>([
  "reminder_create",
  "reminder_update",
  "reminder_cancel",
  "calendar_create",
  "calendar_update",
  "calendar_delete",
  "gmail_send",
  "gmail_reply",
  "gmail_mark",
]);

function writeFingerprint(name: string, input: unknown): string {
  // Stable JSON: deterministic key order via Object.keys().sort() — guarantees
  // {a:1,b:2} and {b:2,a:1} hash the same.
  const stable = (v: unknown): unknown => {
    if (v === null || typeof v !== "object") return v;
    if (Array.isArray(v)) return v.map(stable);
    const out: Record<string, unknown> = {};
    for (const k of Object.keys(v as Record<string, unknown>).sort()) {
      out[k] = stable((v as Record<string, unknown>)[k]);
    }
    return out;
  };
  return `${name}:${JSON.stringify(stable(input))}`;
}

// Extended thinking, gated. Per Anthropic, thinking improves multi-step planning
// noticeably but adds output-rate-billed tokens. We only enable it on the FIRST
// iteration of a compound turn (detected heuristically), then let the loop run
// non-thinking. Budget is intentionally small — Sonnet 4.6 plans well in under
// 1024 thinking tokens for the kinds of compound flows Peppi sees.
const THINKING_BUDGET_TOKENS = 1024;
// max_tokens must exceed budget_tokens; 2048 leaves ~1024 for the visible reply.
const MAX_TOKENS_WITH_THINKING = 2048;
// Triggers that indicate a multi-step / multi-tool intent. Calibrated to
// over-trigger slightly — false positives cost ~$0.015 each, false negatives
// cost a wrong action.
const COMPOUND_TRIGGER_RE =
  /\b(and then|then |after |before my |everyone|all of |each |every (?:weekday|day|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|reply to|cancel .* and|move my|find .* and|email .* and|forward |something came up)\b/i;
const LONG_MESSAGE_THRESHOLD = 120;

function shouldEnableThinking(userText: string): boolean {
  if (!userText) return false;
  if (userText.length > LONG_MESSAGE_THRESHOLD) return true;
  return COMPOUND_TRIGGER_RE.test(userText);
}

function buildContextAnchor(ctx: ToolContext): string {
  // Compose a single-line anchor with current local time + city. ~30 tokens,
  // sits in the fresh user turn, never enters the cached prefix.
  // Format example: "[now: 2026-05-06 17:30 Asia/Kolkata; city: Pune]"
  const tz = ctx.timezone || "UTC";
  let local = "";
  try {
    const fmt = new Intl.DateTimeFormat("en-CA", {
      timeZone: tz,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      weekday: "short",
      hour12: false,
    });
    const parts = fmt.formatToParts(new Date()).reduce<Record<string, string>>((acc, p) => {
      if (p.type !== "literal") acc[p.type] = p.value;
      return acc;
    }, {});
    local = `${parts.year}-${parts.month}-${parts.day} ${parts.weekday} ${parts.hour}:${parts.minute}`;
  } catch {
    local = new Date().toISOString();
  }
  const cityPart = ctx.city ? `; city: ${ctx.city}` : "";
  return `[now: ${local} ${tz}${cityPart}]`;
}

// Load agent.md once at import-time. ESM top-level await is fine in Node 22.
const AGENT_MD = await readFile(join(__dirname, "..", "prompts", "agent.md"), "utf-8");

// ─── Types ─────────────────────────────────────────────────────────────

export interface AgentInput {
  sessionId: string;
  userId: string;
  userText: string;
  imageUrls?: string[];
  ctx: ToolContext;
}

export interface AgentOutput {
  reply: string;
  actionType: string;
  tokens: {
    total: number;
    input: number;
    output: number;
    cacheRead: number;
    cacheWrite5m: number;
    cacheWrite1h: number;
  };
  iterations: number;
  toolCalls: Array<{ name: string; durationMs: number; ok: boolean }>;
  reminderTriggerAt?: string;
}

// ─── Main loop ─────────────────────────────────────────────────────────

export async function runAgentLoop(input: AgentInput, session: Session): Promise<AgentOutput> {
  const t0 = performance.now();

  const messages: Anthropic.MessageParam[] = [...session.history];

  // Build the user message: optional context-anchor line + text + optional images.
  const userContent: Anthropic.ContentBlockParam[] = [];

  // Anchor line — Sonnet's training cutoff is Aug 2025 and the system prompt
  // is cached (so we can't put a date there without busting cache). Without
  // this anchor, "tomorrow"/"tonight"/"next Monday" resolve to whatever the
  // model thinks today is, which is wrong by ~9+ months. The anchor goes in
  // the FRESH user message, AFTER all cache breakpoints, so it never busts
  // cache and the model has hard ground for relative dates.
  // Bug observed 2026-05-06 (req e125aa9e): "tomorrow at 4pm" replied as
  // "July 16" instead of "May 7".
  const anchor = buildContextAnchor(input.ctx);
  if (anchor) {
    userContent.push({ type: "text", text: anchor });
  }

  if (input.imageUrls?.length) {
    for (const url of input.imageUrls) {
      userContent.push({
        type: "image",
        source: { type: "url", url },
      });
    }
  }
  if (input.userText) {
    userContent.push({ type: "text", text: input.userText });
  }
  if (userContent.length === 0 || (userContent.length === 1 && anchor)) {
    userContent.push({
      type: "text",
      text: "[empty message — describe the conversation context if any, otherwise ask the user what they need]",
    });
  }
  messages.push({ role: "user", content: userContent });

  // Loop state
  let iter = 0;
  let actionType = "chat";
  let reminderTriggerAt: string | undefined;
  let anthropicRequestId: string | null | undefined;
  const toolCalls: AgentOutput["toolCalls"] = [];
  const usage = { input: 0, output: 0, cacheRead: 0, cacheWrite5m: 0, cacheWrite1h: 0 };

  // Decide once, up front, whether this turn warrants extended thinking.
  // Only applied to iter 1 — subsequent iterations operate on tool_result feedback,
  // which doesn't need re-planning.
  const useThinking = shouldEnableThinking(input.userText);

  // Fingerprints of write tool calls already executed in this run. If the
  // model emits a second write with identical args (parallel or across iters),
  // we skip the actual dispatch and surface a "duplicate skipped" tool_result.
  const writeFingerprintsExecuted = new Set<string>();

  while (iter < MAX_TOOL_ITERATIONS) {
    iter++;

    // Thinking only on iter 1 of compound turns. iter 2+ operates on tool_results
    // and doesn't benefit from re-planning. Note: max_tokens must exceed
    // thinking budget, so we bump it for the thinking iteration.
    const thinkingThisIter = useThinking && iter === 1;
    const resp: Anthropic.Message = await client.messages.create({
      model: MODEL,
      max_tokens: thinkingThisIter ? MAX_TOKENS_WITH_THINKING : MAX_TOKENS,
      ...(thinkingThisIter
        ? { thinking: { type: "enabled" as const, budget_tokens: THINKING_BUDGET_TOKENS } }
        : {}),
      // bp1 (1h TTL): caches the entire (tools + system) prefix.
      system: [
        {
          type: "text",
          text: AGENT_MD,
          cache_control: { type: "ephemeral", ttl: "1h" },
        },
      ],
      tools: TOOLS,
      // bp2 (5m TTL): cache_control on last stable assistant turn (applied inline).
      messages: applyHistoryBreakpoint(messages),
    });

    // Capture Anthropic's request_id for support tickets / log cross-ref.
    // The SDK exposes it as `_request_id` on the response object.
    anthropicRequestId = (resp as unknown as { _request_id?: string | null })._request_id ?? anthropicRequestId;

    // Accumulate usage
    usage.input += resp.usage.input_tokens ?? 0;
    usage.output += resp.usage.output_tokens ?? 0;
    usage.cacheRead += resp.usage.cache_read_input_tokens ?? 0;
    // SDK exposes cache creation as either a flat cache_creation_input_tokens (older shape)
    // or a structured cache_creation: {ephemeral_5m_input_tokens, ephemeral_1h_input_tokens}.
    const cc = (resp.usage as unknown as { cache_creation?: { ephemeral_5m_input_tokens?: number; ephemeral_1h_input_tokens?: number } }).cache_creation;
    if (cc) {
      usage.cacheWrite5m += cc.ephemeral_5m_input_tokens ?? 0;
      usage.cacheWrite1h += cc.ephemeral_1h_input_tokens ?? 0;
    } else {
      usage.cacheWrite5m += resp.usage.cache_creation_input_tokens ?? 0;
    }

    // ─── stop_reason dispatch ────────────────────────────────────────
    if (resp.stop_reason === "end_turn") {
      const text = extractText(resp).trim();
      messages.push({ role: "assistant", content: resp.content });
      session.history = trimHistory(messages);
      logCall({
        sessionId: input.sessionId,
        userId: input.userId,
        iterations: iter,
        elapsedMs: performance.now() - t0,
        usage,
        actionType,
        toolCalls,
        requestId: input.ctx.requestId,
        anthropicRequestId,
      });
      return {
        reply: text || "(no reply)",
        actionType,
        tokens: tokenTotal(usage),
        iterations: iter,
        toolCalls,
        reminderTriggerAt,
      };
    }

    if (resp.stop_reason === "tool_use") {
      const toolUses = resp.content.filter(
        (b): b is Anthropic.ToolUseBlock => b.type === "tool_use",
      );
      // Persist the assistant turn (with all blocks including text + tool_use) BEFORE the tool_result.
      messages.push({ role: "assistant", content: resp.content });

      const results = await Promise.all(
        toolUses.map(async (tu) => {
          const tStart = performance.now();

          // Defensive write dedup: if this is a write and we've already run a
          // write with byte-identical args in this run, skip the actual call.
          // Surface a synthetic tool_result so the model knows it was a dupe
          // and can stop re-emitting.
          if (WRITE_TOOLS.has(tu.name)) {
            const fp = writeFingerprint(tu.name, tu.input);
            if (writeFingerprintsExecuted.has(fp)) {
              toolCalls.push({ name: tu.name, durationMs: 0, ok: true });
              return {
                type: "tool_result" as const,
                tool_use_id: tu.id,
                content:
                  `Duplicate write skipped — ${tu.name} with identical args was already executed in this turn. ` +
                  `The first call is the authoritative one; do not retry. Continue with the rest of your plan or reply to the user.`,
              };
            }
            writeFingerprintsExecuted.add(fp);
          }

          try {
            const out = await dispatchTool(tu.name, tu.input, input.ctx);
            // Track action_type + reminder_trigger_at for the response envelope.
            actionType = inferActionType(tu.name, actionType);
            if (tu.name === "reminder_create" && out && typeof out === "object" && "trigger_at" in out) {
              reminderTriggerAt = (out as { trigger_at: string }).trigger_at;
            }
            toolCalls.push({ name: tu.name, durationMs: performance.now() - tStart, ok: true });
            return {
              type: "tool_result" as const,
              tool_use_id: tu.id,
              content: stringifyToolOutput(out),
            };
          } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            toolCalls.push({ name: tu.name, durationMs: performance.now() - tStart, ok: false });
            // CRITICAL: never throw out of dispatcher — return error as tool_result so
            // Claude can self-correct (per Anthropic's writing-tools-for-agents guidance).
            return {
              type: "tool_result" as const,
              tool_use_id: tu.id,
              content: `Error: ${msg}`,
              is_error: true as const,
            };
          }
        }),
      );

      messages.push({ role: "user", content: results });
      continue;
    }

    if (resp.stop_reason === "max_tokens") {
      const partial = extractText(resp).trim();
      session.history = trimHistory([...messages, { role: "assistant", content: resp.content }]);
      return {
        reply: partial || "I hit a length limit — try rephrasing if the answer feels cut off.",
        actionType,
        tokens: tokenTotal(usage),
        iterations: iter,
        toolCalls,
        reminderTriggerAt,
      };
    }

    if (resp.stop_reason === "refusal") {
      session.history = trimHistory([...messages, { role: "assistant", content: resp.content }]);
      return {
        reply: "I can't help with that one — try a different request.",
        actionType: "refused",
        tokens: tokenTotal(usage),
        iterations: iter,
        toolCalls,
      };
    }

    // pause_turn / stop_sequence — unexpected for our config. Bail.
    throw new Error(`Unexpected stop_reason: ${resp.stop_reason}`);
  }

  // Hit MAX_TOOL_ITERATIONS — return whatever text we have.
  throw new Error(`Agent loop exceeded ${MAX_TOOL_ITERATIONS} iterations without end_turn`);
}

// ─── Helpers ───────────────────────────────────────────────────────────

function applyHistoryBreakpoint(msgs: Anthropic.MessageParam[]): Anthropic.MessageParam[] {
  // bp3 (5m TTL): cache_control on the last STABLE assistant turn (i.e., the turn
  // BEFORE the current user message). The fresh user turn stays uncached so
  // per-call dynamic content (timestamps, image URLs) never busts cache.
  if (msgs.length < 2) return msgs;
  const out = msgs.map((m) => ({ ...m }));
  const lastStableIdx = out.length - 2;
  const lastStable = out[lastStableIdx];
  if (lastStable.role !== "assistant") return out;

  const content = Array.isArray(lastStable.content)
    ? [...lastStable.content]
    : [{ type: "text" as const, text: lastStable.content }];
  // Add cache_control to the LAST block of the prior assistant turn.
  if (content.length === 0) return out;
  const lastBlock = content[content.length - 1];
  // Spread + add the cache_control field. Block types vary; cast through unknown to bypass strict typing.
  content[content.length - 1] = {
    ...(lastBlock as object),
    cache_control: { type: "ephemeral" },
  } as Anthropic.ContentBlockParam;
  out[lastStableIdx] = { ...lastStable, content };
  return out;
}

function trimHistory(msgs: Anthropic.MessageParam[]): Anthropic.MessageParam[] {
  if (msgs.length <= HISTORY_TURNS_KEPT) return msgs;
  // Naive slice can split a tool_use/tool_result pair: if msgs[start] is a
  // `user` turn whose content is a tool_result, the API rejects the request
  // because there's no preceding `assistant` tool_use turn. Walk forward from
  // the cut point until we land on a fresh user query (string content, or a
  // user turn with NO tool_result blocks). That guarantees the truncated array
  // starts at a "round boundary."
  let start = Math.max(0, msgs.length - HISTORY_TURNS_KEPT);
  while (start < msgs.length) {
    const m = msgs[start];
    if (m.role === "user") {
      const content = m.content;
      if (typeof content === "string") return msgs.slice(start);
      if (Array.isArray(content)) {
        const hasToolResult = content.some(
          (b) => b && typeof b === "object" && "type" in b && (b as { type: string }).type === "tool_result",
        );
        if (!hasToolResult) return msgs.slice(start);
      }
    }
    start++;
  }
  // No safe boundary found in the trim window — keep full history rather than
  // emit a malformed message array. Worst case: this turn pays full price; next
  // turn's history will have shifted and find a boundary.
  return msgs;
}

function extractText(resp: Anthropic.Message): string {
  // Sonnet sometimes emits literal <thinking>...</thinking> XML tags inside
  // text blocks, mimicking the structured-thinking style. They MUST NOT reach
  // the SMS user. Strip both closed pairs and dangling open tags. Observed in
  // hard-find-thread-and-reply (req b1d7767a) on 2026-05-06.
  const stripThinking = (t: string): string =>
    t
      .replace(/<thinking>[\s\S]*?<\/thinking>/gi, "")
      .replace(/<thinking>[\s\S]*$/i, "")
      .replace(/^[\s\S]*?<\/thinking>/i, "")
      .trim();
  return resp.content
    .filter((b): b is Anthropic.TextBlock => b.type === "text")
    .map((b) => stripThinking(b.text))
    .filter((t) => t.length > 0)
    .join("\n");
}

function stringifyToolOutput(out: unknown): string {
  if (out === null || out === undefined) return "";
  if (typeof out === "string") return out;
  // For objects/arrays, JSON stringify (compact). Tools that return human-readable
  // strings (web_search) take the string path above.
  return JSON.stringify(out);
}

function inferActionType(toolName: string, current: string): string {
  if (toolName === "web_search") return "web_search";
  if (toolName.startsWith("reminder_")) {
    const op = toolName.split("_")[1] ?? "action";
    return `reminder_${op}`;
  }
  if (toolName.startsWith("calendar_")) {
    const op = toolName.split("_")[1] ?? "action";
    return `calendar_${op}`;
  }
  if (toolName.startsWith("gmail_")) {
    const op = toolName.split("_")[1] ?? "action";
    return `gmail_${op}`;
  }
  if (toolName === "image_handle") return "image_handle";
  return current;
}

function tokenTotal(u: AgentOutput["tokens"] | { input: number; output: number; cacheRead: number; cacheWrite5m: number; cacheWrite1h: number }): AgentOutput["tokens"] {
  return {
    total: u.input + u.output + u.cacheRead + u.cacheWrite5m + u.cacheWrite1h,
    input: u.input,
    output: u.output,
    cacheRead: u.cacheRead,
    cacheWrite5m: u.cacheWrite5m,
    cacheWrite1h: u.cacheWrite1h,
  };
}
