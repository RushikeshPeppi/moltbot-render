/**
 * web_search — SearXNG multi-engine search with zero-result fallback.
 *
 * Engine reality (verified 2026-05-19 from Render egress):
 *   bing       works  — primary anchor for general queries
 *   bing news  works  — essential for time-filtered / news queries (bing general returns 0 with time_range)
 *   startpage  dead   — CAPTCHA-blocked from Render IP, suspended 3600s
 *   brave      dead   — 429 rate-limited from Render IP, suspended 600s
 *   duckduckgo / qwant / mojeek / karmasearch — permanently CAPTCHA / access-denied
 *
 * Order matters: SearXNG processes engines left-to-right, so put the most-reliable first.
 */

import type Anthropic from "@anthropic-ai/sdk";
import type { ToolContext } from "./index.js";

export const WEB_SEARCH_TOOL: Anthropic.Tool = {
  name: "web_search",
  description:
    "Search the web via SearXNG. Returns up to 3 ranked results with title, URL, and short snippet. Use for sports scores, news, weather, current events, business hours, near-me queries, and any topic where current data matters and your training cutoff (Aug 2025) is insufficient. For 'near me' queries append the user's city to the query if available; otherwise call without geography. Do not call more than once per turn.",
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

interface SearXNGResult {
  title?: string;
  url?: string;
  content?: string;
}

interface SearXNGResponse {
  results?: SearXNGResult[];
  unresponsive_engines?: Array<[string, string]>;
}

export async function execute(
  input: { query: string; time_range?: string },
  ctx: ToolContext,
): Promise<string> {
  const baseUrl = `${ctx.searxngUrl}/search`;
  const q = encodeURIComponent(input.query);
  const tr = input.time_range ? `&time_range=${input.time_range}` : "";
  // Multi-engine — bing + bing news primary, startpage/brave kept as opportunistic fallbacks.
  const primaryUrl = `${baseUrl}?q=${q}&format=json&safesearch=1&engines=bing,bing+news,startpage,brave${tr}`;

  let results = await fetchResults(primaryUrl);
  if (results === null) {
    return "Web search rate-limited — try again in a moment.";
  }

  // Zero-result fallback: retry without engine pin (uses SearXNG's full default set).
  if (results.length === 0) {
    const fallbackUrl = `${baseUrl}?q=${q}&format=json&safesearch=1${tr}`;
    const fallback = await fetchResults(fallbackUrl);
    if (fallback && fallback.length > 0) {
      results = fallback;
    }
  }

  if (results.length === 0) {
    return "No results — try rephrasing or being more specific.";
  }

  // Deduplicate by parsed-domain, take top 3, render plain text (NO markdown).
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

async function fetchResults(url: string): Promise<SearXNGResult[] | null> {
  try {
    const resp = await fetch(url, {
      headers: {
        Accept: "application/json",
        "User-Agent": "PeppiAgent/2.0 (+https://peppi.app)",
      },
      signal: AbortSignal.timeout(8_000),
    });
    if (!resp.ok) {
      if (resp.status === 429 || resp.status === 403) return null;
      console.warn(`[web_search] non-ok ${resp.status} from SearXNG`);
      return [];
    }
    const json = (await resp.json()) as SearXNGResponse;
    return json.results ?? [];
  } catch (err) {
    console.warn(`[web_search] fetch failed: ${(err as Error).message}`);
    return [];
  }
}

function safeDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
