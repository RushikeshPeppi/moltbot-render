/**
 * web_search — SearXNG primary + Tavily fallback, AI-decided.
 *
 * Default call uses SearXNG (free, Bing-powered). If the AI judges the results
 * are garbage (generic homepages, no real data), it calls again with
 * source="tavily" to get quality results. The AI decides — no heuristics.
 *
 * Fallback chain within SearXNG:
 *   1. Pinned engines (bing, bing news, startpage, brave)
 *   2. Default engine set (no pin)
 */

import type Anthropic from "@anthropic-ai/sdk";
import type { ToolContext } from "./index.js";

export const WEB_SEARCH_TOOL: Anthropic.Tool = {
  name: "web_search",
  description:
    `Search the web. Returns up to 3 ranked results with title, URL, and snippet.

Use for: sports scores, news, weather, current events, business hours, near-me queries, flight/hotel prices, and any topic where your training cutoff is insufficient.

For 'near me' queries, append the user's city if available.

COST WARNING — source="tavily" costs real money. Only retry with tavily when results are truly useless. Here is how to judge:

USEFUL (do NOT retry): Result snippets contain specific data related to the query — scores, names, prices, dates, article text, stats. Example: searching "IPL scores" and getting cricbuzz.com with "SRH 235/4, PBKS 202/7" in the snippet. USE THESE.

USELESS (retry with tavily): Result snippets are just generic website taglines with zero query-specific data. Example: searching "flights Mumbai to Delhi June 10" and getting "Google Flights - Find Cheap Flights Worldwide" or "Expedia - Book Your Ticket". These are just homepages — no Mumbai, no Delhi, no prices, no dates. RETRY with tavily.

The test is simple: do the snippets mention anything specific from the user's query? If yes → use them. If every snippet is just a site's marketing tagline → retry tavily.`,
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
      source: {
        type: "string",
        enum: ["auto", "tavily"],
        description:
          "Search source. Default 'auto' uses SearXNG (free). Use 'tavily' only as a retry when auto returned poor/generic results.",
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
  input: { query: string; time_range?: string; source?: string },
  ctx: ToolContext,
): Promise<string> {
  // If the AI explicitly requested Tavily, try it — but fall back to SearXNG
  // if Tavily fails (rate limit, error, etc). Something is better than nothing.
  if (input.source === "tavily") {
    if (ctx.tavilyApiKeys.length > 0) {
      console.log(`[web_search] AI requested Tavily for: "${input.query}"`);
      const tavilyResults = await fetchTavilyWithRotation(input.query, ctx.tavilyApiKeys);
      if (tavilyResults && tavilyResults.length > 0) {
        return formatResults(tavilyResults);
      }
      console.warn(`[web_search] Tavily failed/empty (all keys), falling back to SearXNG`);
    }
    // Tavily failed or not configured — run SearXNG so we return something.
  }

  // Default path: SearXNG.
  const baseUrl = `${ctx.searxngUrl}/search`;
  const q = encodeURIComponent(input.query);

  let results: SearXNGResult[] = [];

  if (input.time_range) {
    // Bing general CANNOT do time_range (SearXNG limitation — depends on JS).
    // Fire two parallel calls and merge:
    //   1. Bing general WITHOUT time_range → web results (scores, pages, etc.)
    //   2. Bing news WITH time_range → fresh time-filtered news articles
    const [webResults, newsResults] = await Promise.all([
      fetchSearxngResults(`${baseUrl}?q=${q}&format=json&safesearch=1&engines=bing`),
      fetchSearxngResults(`${baseUrl}?q=${q}&format=json&safesearch=1&engines=bing+news&time_range=${input.time_range}`),
    ]);
    results = [...(newsResults ?? []), ...(webResults ?? [])];
  } else {
    // No time_range — single call with all engines.
    const primaryUrl = `${baseUrl}?q=${q}&format=json&safesearch=1&engines=bing,bing+news,startpage,brave`;
    const primary = await fetchSearxngResults(primaryUrl);
    if (primary === null) {
      results = [];
    } else {
      results = primary;
    }
  }

  // Fallback: retry without engine pin or time_range.
  if (results.length === 0) {
    const fallbackUrl = `${baseUrl}?q=${q}&format=json&safesearch=1`;
    const fallback = await fetchSearxngResults(fallbackUrl);
    if (fallback && fallback.length > 0) {
      results = fallback;
    }
  }

  if (results.length === 0) {
    // If Tavily is available, auto-fallback on zero results.
    if (ctx.tavilyApiKeys.length > 0) {
      console.log(`[web_search] SearXNG returned 0 results, auto-falling back to Tavily`);
      const tavilyResults = await fetchTavilyWithRotation(input.query, ctx.tavilyApiKeys);
      if (tavilyResults && tavilyResults.length > 0) {
        return formatResults(tavilyResults);
      }
    }
    return "No results — try rephrasing or being more specific.";
  }

  return formatResults(results);
}

function formatResults(results: SearXNGResult[]): string {
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

/**
 * Round-robin counter for Tavily key rotation.
 * Persists across requests for even key distribution.
 */
let tavilyKeyIndex = 0;

/**
 * Try Tavily with key rotation. Starts from current round-robin position.
 * If a key returns 429/402 (quota exceeded), tries the next key.
 * Returns results from first successful key, or null if all keys fail.
 */
async function fetchTavilyWithRotation(
  query: string,
  keys: string[],
): Promise<TavilyResult[] | null> {
  const startIdx = tavilyKeyIndex;
  for (let i = 0; i < keys.length; i++) {
    const idx = (startIdx + i) % keys.length;
    const key = keys[idx];
    const keyLabel = `key${idx + 1}/${keys.length}`;

    const result = await fetchTavilyResults(query, key, keyLabel);

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
): Promise<TavilyResult[] | null | "quota"> {
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
