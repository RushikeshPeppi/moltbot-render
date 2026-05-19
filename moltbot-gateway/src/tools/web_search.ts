/**
 * web_search — SearXNG multi-engine search with Tavily API fallback.
 *
 * Engine reality (verified 2026-05-19 from Render egress):
 *   bing       works  — primary anchor for general queries
 *   bing news  works  — essential for time-filtered / news queries (bing general returns 0 with time_range)
 *   startpage  dead   — CAPTCHA-blocked from Render IP, suspended 3600s
 *   brave      dead   — 429 rate-limited from Render IP, suspended 600s
 *   duckduckgo / qwant / mojeek / karmasearch — permanently CAPTCHA / access-denied
 *
 * Fallback chain:
 *   1. SearXNG with pinned engines (bing, bing news, startpage, brave)
 *   2. SearXNG with default engine set (no pin)
 *   3. Tavily API (legitimate API — never blocks, 1000 free/month)
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
  const baseUrl = `${ctx.searxngUrl}/search`;
  const q = encodeURIComponent(input.query);
  const tr = input.time_range ? `&time_range=${input.time_range}` : "";
  // Multi-engine — bing + bing news primary, startpage/brave kept as opportunistic fallbacks.
  const primaryUrl = `${baseUrl}?q=${q}&format=json&safesearch=1&engines=bing,bing+news,startpage,brave${tr}`;

  let results = await fetchSearxngResults(primaryUrl);
  if (results === null) {
    // SearXNG returned 429/403 — skip to Tavily directly.
    results = [];
  }

  // Fallback 1: retry without engine pin (uses SearXNG's full default set).
  if (results.length === 0) {
    const fallbackUrl = `${baseUrl}?q=${q}&format=json&safesearch=1${tr}`;
    const fallback = await fetchSearxngResults(fallbackUrl);
    if (fallback && fallback.length > 0) {
      results = fallback;
    }
  }

  // Fallback 2: Tavily API (legitimate API, never blocks).
  if (results.length === 0 && ctx.tavilyApiKey) {
    console.log(`[web_search] SearXNG returned 0 results, falling back to Tavily`);
    const tavilyResults = await fetchTavilyResults(input.query, ctx.tavilyApiKey);
    if (tavilyResults && tavilyResults.length > 0) {
      // Normalize Tavily results to match SearXNG shape.
      results = tavilyResults.map((r) => ({
        title: r.title,
        url: r.url,
        content: r.content,
      }));
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

async function fetchSearxngResults(url: string): Promise<SearXNGResult[] | null> {
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
    console.warn(`[web_search] SearXNG fetch failed: ${(err as Error).message}`);
    return [];
  }
}

async function fetchTavilyResults(
  query: string,
  apiKey: string,
): Promise<TavilyResult[] | null> {
  try {
    const resp = await fetch("https://api.tavily.com/search", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        api_key: apiKey,
        query,
        search_depth: "basic",
        max_results: 5,
        include_answer: false,
      }),
      signal: AbortSignal.timeout(10_000),
    });
    if (!resp.ok) {
      console.warn(`[web_search] Tavily returned ${resp.status}`);
      return null;
    }
    const json = (await resp.json()) as TavilyResponse;
    return json.results ?? [];
  } catch (err) {
    console.warn(`[web_search] Tavily fetch failed: ${(err as Error).message}`);
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
