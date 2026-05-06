/**
 * Eval harness for the Peppi gateway.
 *
 * Usage:
 *   GATEWAY_URL=https://openclaw-gateway-dg3y.onrender.com \
 *   EVAL_USER_ID=<a-user-id-with-google-oauth> \
 *   EVAL_TIMEZONE=Asia/Kolkata \
 *   EVAL_TIERS=simple,medium \
 *   npx tsx tests/eval/run.ts
 *
 * What it does:
 *   - Reads tests/eval/scenarios.json.
 *   - For each scenario in EVAL_TIERS, POSTs to {GATEWAY_URL}/execute with the
 *     scenario's user_message and image_urls.
 *   - Scores: did expected_tool_calls all fire? did reply match must_contain
 *     (and not match must_not_contain)? was iter <= max_iterations? wall <=
 *     max_wall_ms?
 *   - Prints a per-scenario pass/fail line and a summary.
 *
 * Caveats:
 *   - "write" scenarios actually create reminders / calendar events / send
 *     emails on the EVAL_USER_ID account. Only run against a dedicated test
 *     user. Set EVAL_INCLUDE_WRITE=0 to skip them.
 *   - The runner only checks tool DECISIONS (from response._meta.tool_calls)
 *     and reply text — it does not poll Google to verify the side effect
 *     persisted. That's OK for prompt-iteration: the model's tool choices are
 *     what we're optimizing.
 *   - Image scenarios are skipped unless image_urls is filled in.
 */

import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

interface Scenario {
  id: string;
  tier: "simple" | "medium" | "hard" | "edge" | "image";
  side_effect: "read" | "write";
  user_message: string;
  image_urls?: string[];
  expected_tool_calls: string[];
  must_contain?: string;
  must_not_contain?: string;
  max_iterations: number;
  max_wall_ms: number;
  skip_reason?: string;
}

interface ScenariosFile {
  version: number;
  scenarios: Scenario[];
}

interface ExecuteResponse {
  success: boolean;
  response?: string;
  action_type?: string;
  tokens_used?: number;
  cache_read?: number;
  cache_write?: number;
  reminder_trigger_at?: string | null;
  _meta?: {
    iterations: number;
    tool_calls: Array<{ name: string; durationMs: number; ok: boolean }>;
    request_id: string;
  };
  error?: string;
}

interface ScoreResult {
  id: string;
  tier: string;
  pass: boolean;
  failures: string[];
  iter: number;
  wallMs: number;
  toolCalls: string[];
  reply: string;
  cacheRead: number;
}

const GATEWAY_URL = (process.env.GATEWAY_URL ?? "https://openclaw-gateway-dg3y.onrender.com").replace(
  /\/$/,
  "",
);
const EVAL_USER_ID = process.env.EVAL_USER_ID ?? "";
const EVAL_TIMEZONE = process.env.EVAL_TIMEZONE ?? "Asia/Kolkata";
const EVAL_CITY = process.env.EVAL_CITY ?? "";
const EVAL_TIERS = (process.env.EVAL_TIERS ?? "simple,medium,hard,edge")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);
const EVAL_INCLUDE_WRITE = process.env.EVAL_INCLUDE_WRITE !== "0";

if (!EVAL_USER_ID) {
  console.error("EVAL_USER_ID required (a real user id with Google OAuth set up).");
  process.exit(1);
}

async function main(): Promise<void> {
  const file = JSON.parse(
    await readFile(join(__dirname, "scenarios.json"), "utf-8"),
  ) as ScenariosFile;

  const scenarios = file.scenarios.filter((s) => {
    if (!EVAL_TIERS.includes(s.tier)) return false;
    if (!EVAL_INCLUDE_WRITE && s.side_effect === "write") return false;
    if (s.skip_reason && s.image_urls?.some((u) => u.startsWith("__"))) return false;
    return true;
  });

  console.log(
    `[eval] gateway=${GATEWAY_URL} user=${EVAL_USER_ID} tiers=${EVAL_TIERS.join(",")} write=${EVAL_INCLUDE_WRITE} → running ${scenarios.length} of ${file.scenarios.length} scenarios\n`,
  );

  const results: ScoreResult[] = [];
  for (const s of scenarios) {
    const r = await runOne(s);
    results.push(r);
    const status = r.pass ? "PASS" : "FAIL";
    const failNote = r.failures.length ? `  — ${r.failures.join("; ")}` : "";
    console.log(
      `[${status}] ${s.id.padEnd(36)} tier=${s.tier.padEnd(6)} iter=${r.iter} ms=${r.wallMs.toString().padStart(5)} cache_read=${r.cacheRead.toString().padStart(6)} tools=[${r.toolCalls.join(",")}]${failNote}`,
    );
  }

  // Summary
  const total = results.length;
  const passed = results.filter((r) => r.pass).length;
  const byTier: Record<string, { passed: number; total: number }> = {};
  for (const r of results) {
    byTier[r.tier] ??= { passed: 0, total: 0 };
    byTier[r.tier].total++;
    if (r.pass) byTier[r.tier].passed++;
  }
  const avgIter = results.reduce((a, r) => a + r.iter, 0) / Math.max(1, total);
  const avgWall = results.reduce((a, r) => a + r.wallMs, 0) / Math.max(1, total);

  console.log(`\n[summary] ${passed}/${total} pass  avg_iter=${avgIter.toFixed(2)}  avg_wall_ms=${Math.round(avgWall)}`);
  for (const [tier, c] of Object.entries(byTier)) {
    console.log(`  ${tier.padEnd(7)} ${c.passed}/${c.total}`);
  }

  process.exit(passed === total ? 0 : 1);
}

async function runOne(s: Scenario): Promise<ScoreResult> {
  const t0 = performance.now();
  const failures: string[] = [];

  let resp: ExecuteResponse;
  try {
    const httpResp = await fetch(`${GATEWAY_URL}/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: `eval_${s.id}_${Date.now()}`,
        message: s.user_message,
        user_id: EVAL_USER_ID,
        timezone: EVAL_TIMEZONE,
        user_context: EVAL_CITY ? { city: EVAL_CITY } : {},
        image_urls: s.image_urls && !s.image_urls.some((u) => u.startsWith("__")) ? s.image_urls : undefined,
      }),
      signal: AbortSignal.timeout(s.max_wall_ms + 5_000),
    });
    resp = (await httpResp.json()) as ExecuteResponse;
    if (!httpResp.ok) failures.push(`http ${httpResp.status}`);
  } catch (err) {
    const wallMs = Math.round(performance.now() - t0);
    return {
      id: s.id,
      tier: s.tier,
      pass: false,
      failures: [`fetch error: ${(err as Error).message}`],
      iter: 0,
      wallMs,
      toolCalls: [],
      reply: "",
      cacheRead: 0,
    };
  }

  const wallMs = Math.round(performance.now() - t0);
  const meta = resp._meta;
  const iter = meta?.iterations ?? 0;
  const tools = (meta?.tool_calls ?? []).map((t) => t.name);
  const reply = resp.response ?? "";

  // 1. expected_tool_calls — every name in expected must appear (subset, order-insensitive)
  for (const expected of s.expected_tool_calls) {
    if (!tools.includes(expected)) failures.push(`missing tool ${expected}`);
  }

  // 2. must_contain
  if (s.must_contain) {
    if (!new RegExp(s.must_contain, "i").test(reply)) {
      failures.push(`reply missing /${s.must_contain}/i`);
    }
  }

  // 3. must_not_contain
  if (s.must_not_contain) {
    if (new RegExp(s.must_not_contain, "i").test(reply)) {
      failures.push(`reply matches forbidden /${s.must_not_contain}/i`);
    }
  }

  // 4. iteration cap
  if (iter > s.max_iterations) failures.push(`iter ${iter} > ${s.max_iterations}`);

  // 5. wall cap (already enforced by AbortSignal but record overshoot)
  if (wallMs > s.max_wall_ms) failures.push(`wall ${wallMs} > ${s.max_wall_ms}`);

  // 6. success flag
  if (!resp.success) failures.push(`gateway error: ${resp.error ?? "unknown"}`);

  return {
    id: s.id,
    tier: s.tier,
    pass: failures.length === 0,
    failures,
    iter,
    wallMs,
    toolCalls: tools,
    reply: reply.slice(0, 200),
    cacheRead: resp.cache_read ?? 0,
  };
}

main().catch((err) => {
  console.error("[eval] fatal:", err);
  process.exit(2);
});
