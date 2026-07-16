/**
 * web_search — Tavily only.
 *
 * SearXNG (self-hosted) was RETIRED 2026-07-16 by owner decision. Why, in short:
 * measured over 7 days of gateway logs, the whole product does ~9 web_search tool
 * calls/week (~39/month) — against a Tavily quota of 1,000 credits/key/month. Even
 * routing 100% of searches to Tavily uses ~4% of ONE key. For that ~30 searches/month
 * SearXNG cost us: a Docker service, a CASA scan target (unfixable scanner false
 * positives — a search proxy echoes the open internet), an open search-proxy abuse
 * vector (its limiter had to stay OFF or it blocked our own gateway), and the
 * engine-blocking fragility documented in CLAUDE.md. See CASA/moltbot/FINDINGS.md
 * F-P5-8 + the vault decision note (2026-07-16).
 *
 * NOTE for future sessions: a Tavily-primary change was tried and reverted on
 * 2026-07-07 — but on "premature optimization" + the self-hosted principle, NOT on
 * evidence. Both reasons expired: we now have the usage numbers, and CASA made
 * SearXNG a net liability. Do NOT silently revert this back to SearXNG; CLAUDE.md
 * invariant #1 was updated to match.
 *
 * Tavily is now the ONLY backend => single point of failure. Mitigations:
 *   - search_depth "basic" = 1 API credit/query (advanced = 2). ~75x headroom.
 *   - Key rotation retained (works with 1..N keys), so adding capacity is config-only.
 *   - Auth is sent BOTH ways (Bearer header + legacy body api_key) — see below.
 *   - If Tavily ever dies, SearXNG is restorable from git history (pre-retirement).
 */

import type Anthropic from "@anthropic-ai/sdk";
import type { ToolContext } from "./index.js";

export const WEB_SEARCH_TOOL: Anthropic.Tool = {
  name: "web_search",
  description:
    `Search the web. Returns up to 3 ranked results with title, URL, and snippet.

Use for: sports scores, news, weather, current events, business hours, near-me queries, flight/hotel prices, and any topic where your training cutoff is insufficient.

For 'near me' queries, append the user's city if available.`,
  input_schema: {
    type: "object",
    additionalProperties: false,
    required: ["query"],
    properties: {
      query: {
        type: "string",
        description: "Concise search query. For near-me queries include the city.",
      },
      time_range: {
        type: "string",
        enum: ["day", "week", "month", "year"],
        description:
          "Optional time filter. Use 'day' for breaking news, 'week' for recent recap, 'month' for trends. Omit for general queries.",
      },
    },
  },
};

interface TavilyResult {
  title?: string;
  url?: string;
  content?: string;
}

interface TavilyResponse {
  results?: TavilyResult[];
}

export async function execute(
  input: { query: string; time_range?: string },
  ctx: ToolContext,
): Promise<string> {
  // Fail loudly-but-gracefully: with Tavily as the only backend, a missing key means
  // no search at all. Say so rather than returning an empty result set that the model
  // would read as "the web has nothing on this".
  if (ctx.tavilyApiKeys.length === 0) {
    console.error("[web_search] no Tavily API key configured — search unavailable");
    return "Search is temporarily unavailable. Tell the user you couldn't search right now.";
  }

  // Log the query LENGTH, never the text (CASA 6.5.1 — a search query is user content
  // and can carry PII/message context; it must not sit in Render's log viewer).
  console.log(
    `[web_search] Tavily query (${input.query.length} chars)` +
      (input.time_range ? ` time_range=${input.time_range}` : ""),
  );

  const results = await fetchTavilyWithRotation(input.query, ctx.tavilyApiKeys, input.time_range);
  if (!results || results.length === 0) {
    return "No results — try rephrasing or being more specific.";
  }
  return formatResults(results);
}

function formatResults(results: TavilyResult[]): string {
  const seenDomains = new Set<string>();
  const lines: string[] = [];
  for (const r of results) {
    if (!r.url) continue;
    const domain = safeDomain(r.url);
    if (seenDomains.has(domain)) continue;
    seenDomains.add(domain);
    const title = (r.title ?? "(no title)").slice(0, 120);
    const snippet = (r.content ?? "").replace(/\s+/g, " ").trim().slice(0, 250);
    lines.push(`${lines.length + 1}. ${title}\n   ${r.url}\n   ${snippet}`);
    if (lines.length >= 3) break;
  }
  return lines.join("\n\n");
}

/**
 * Round-robin counter for Tavily key rotation.
 * Persists across requests for even key distribution.
 */
let tavilyKeyIndex = 0;

/**
 * Try Tavily with key rotation. Starts from current round-robin position.
 * If a key returns 429/402 (quota exceeded), tries the next key.
 * Returns results from first successful key, or null if all keys fail.
 * Works with a single key (the normal case) — the loop simply runs once.
 */
async function fetchTavilyWithRotation(
  query: string,
  keys: string[],
  timeRange?: string,
): Promise<TavilyResult[] | null> {
  const startIdx = tavilyKeyIndex;
  for (let i = 0; i < keys.length; i++) {
    const idx = (startIdx + i) % keys.length;
    const key = keys[idx];
    const keyLabel = `key${idx + 1}/${keys.length}`;

    const result = await fetchTavilyResults(query, key, keyLabel, timeRange);

    if (result === "quota") {
      // This key is exhausted — try the next one.
      console.warn(`[web_search] Tavily ${keyLabel} quota exceeded, rotating`);
      continue;
    }

    // Advance round-robin for next call (even on success).
    tavilyKeyIndex = (idx + 1) % keys.length;

    if (result && result.length > 0) {
      return result;
    }
    // Empty results from this key — still try next.
  }
  return null;
}

async function fetchTavilyResults(
  query: string,
  apiKey: string,
  keyLabel: string = "key",
  timeRange?: string,
): Promise<TavilyResult[] | null | "quota"> {
  try {
    const body: Record<string, unknown> = {
      // Tavily's CURRENT docs authenticate via the `Authorization: Bearer` header and
      // say the key is "not in the request body" — but the legacy body `api_key` is
      // still accepted and is what this integration has always used (verified live
      // 2026-07-16). We send BOTH: Tavily is now our ONLY search backend, so a
      // deprecation of either auth method must not be able to take search out.
      api_key: apiKey,
      query,
      search_depth: "basic", // 1 API credit ("advanced" costs 2)
      max_results: 5,
      include_answer: false,
    };
    // Tavily supports time_range with exactly our enum values (day|week|month|year).
    if (timeRange) body.time_range = timeRange;

    const resp = await fetch("https://api.tavily.com/search", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(10_000),
    });
    if (!resp.ok) {
      // 429 = rate limit, 402 = payment required (quota exceeded)
      if (resp.status === 429 || resp.status === 402) {
        return "quota";
      }
      console.warn(`[web_search] Tavily ${keyLabel} returned ${resp.status}`);
      return null;
    }
    const json = (await resp.json()) as TavilyResponse;
    console.log(`[web_search] Tavily ${keyLabel} returned ${json.results?.length ?? 0} results`);
    return json.results ?? [];
  } catch (err) {
    console.warn(`[web_search] Tavily ${keyLabel} fetch failed: ${(err as Error).message}`);
    return null;
  }
}

function safeDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
