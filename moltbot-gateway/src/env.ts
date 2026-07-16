/**
 * Environment variable validation. Fail-fast at boot if anything required is missing.
 */

import "dotenv/config";

// SEARXNG_URL was removed 2026-07-16 when SearXNG was retired (Tavily is now the only
// search backend — see tools/web_search.ts header + CLAUDE.md invariant #1).
// TAVILY_API_KEYS is deliberately NOT required: a missing key must degrade search to
// "unavailable", not refuse to boot — the gateway still serves reminders/calendar/email.
// validateEnv() warns loudly instead.
const REQUIRED = ["ANTHROPIC_API_KEY", "FASTAPI_URL"] as const;

export const env = {
  ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY ?? "",
  FASTAPI_URL: (process.env.FASTAPI_URL ?? "").replace(/\/$/, ""),
  PORT: parseInt(process.env.PORT ?? "10000", 10),
  HELICONE_PROXY: process.env.HELICONE_PROXY === "true",
  HELICONE_KEY: process.env.HELICONE_KEY ?? "",
  // Comma-separated list of Tavily keys for rotation. Falls back to single TAVILY_API_KEY.
  TAVILY_API_KEYS: (process.env.TAVILY_API_KEYS || process.env.TAVILY_API_KEY || "")
    .split(",")
    .map((k) => k.trim())
    .filter(Boolean),
  // Shared service-to-service secret (must match moltbot-fastapi + Peppi Laravel).
  // Guards POST /execute and is sent on the FastAPI token-bridge fetch.
  INTERNAL_SERVICE_KEY: process.env.INTERNAL_SERVICE_KEY ?? "",
  NODE_ENV: process.env.NODE_ENV ?? "production",
} as const;

export function validateEnv(): void {
  const missing = REQUIRED.filter((k) => !process.env[k]);
  if (missing.length > 0) {
    console.error(`[env] missing required env vars: ${missing.join(", ")}`);
    process.exit(1);
  }
  if (env.HELICONE_PROXY && !env.HELICONE_KEY) {
    console.error("[env] HELICONE_PROXY=true but HELICONE_KEY is empty");
    process.exit(1);
  }
  // Tavily is the ONLY search backend since SearXNG was retired — no key means the
  // web_search tool is dead. Not fatal (other tools still work), but must be loud.
  if (env.TAVILY_API_KEYS.length === 0) {
    console.error("[env] TAVILY_API_KEYS/TAVILY_API_KEY is empty — web_search is DISABLED");
  }
  console.log(
    `[env] ANTHROPIC_API_KEY=${env.ANTHROPIC_API_KEY ? "set" : "MISSING"}, ` +
      `FASTAPI_URL=${env.FASTAPI_URL}, PORT=${env.PORT}, ` +
      `HELICONE=${env.HELICONE_PROXY ? "on" : "off"}, TAVILY_KEYS=${env.TAVILY_API_KEYS.length}`,
  );
}
