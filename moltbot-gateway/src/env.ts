/**
 * Environment variable validation. Fail-fast at boot if anything required is missing.
 */

import "dotenv/config";

const REQUIRED = ["ANTHROPIC_API_KEY", "FASTAPI_URL", "SEARXNG_URL"] as const;

export const env = {
  ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY ?? "",
  FASTAPI_URL: (process.env.FASTAPI_URL ?? "").replace(/\/$/, ""),
  SEARXNG_URL: (process.env.SEARXNG_URL ?? "").replace(/\/$/, ""),
  PORT: parseInt(process.env.PORT ?? "10000", 10),
  HELICONE_PROXY: process.env.HELICONE_PROXY === "true",
  HELICONE_KEY: process.env.HELICONE_KEY ?? "",
  TAVILY_API_KEY: process.env.TAVILY_API_KEY ?? "",
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
  console.log(
    `[env] ANTHROPIC_API_KEY=${env.ANTHROPIC_API_KEY ? "set" : "MISSING"}, ` +
      `FASTAPI_URL=${env.FASTAPI_URL}, SEARXNG_URL=${env.SEARXNG_URL}, PORT=${env.PORT}, ` +
      `HELICONE=${env.HELICONE_PROXY ? "on" : "off"}`,
  );
}
