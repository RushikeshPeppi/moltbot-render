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

COST WARNING: The "tavily" source costs real money per call. You MUST use the default results unless they are COMPLETE GARBAGE with ZERO useful information. Average or mediocre results are FINE — use them. If you get website links like cricbuzz.com, espncricinfo.com, iplt20.com for cricket, or any recognizable relevant website for the topic — those are GOOD results, use them directly. Do NOT retry with tavily just because you think you could get "better" results. Only use source="tavily" when every single result is a totally unrelated generic homepage (like getting "Best Buy" or "Merriam-Webster dictionary" when someone asked about restaurants). If results have ANY connection to the query topic, use them as-is.`,
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
    if (ctx.tavilyApiKey) {
      console.log(`[web_search] AI requested Tavily for: "${input.query}"`);
      const tavilyResults = await fetchTavilyResults(input.query, ctx.tavilyApiKey);
      if (tavilyResults && tavilyResults.length > 0) {
        return formatResults(tavilyResults);
      }
      console.warn(`[web_search] Tavily failed/empty, falling back to SearXNG`);
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
    if (ctx.tavilyApiKey) {
      console.log(`[web_search] SearXNG returned 0 results, auto-falling back to Tavily`);
      const tavilyResults = await fetchTavilyResults(input.query, ctx.tavilyApiKey);
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
