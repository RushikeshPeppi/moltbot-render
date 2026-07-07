/**
 * Google OAuth token bridge.
 *
 * The FastAPI wrapper owns the OAuth flow + token storage (Supabase + refresh logic).
 * For each /execute call, we fetch the current access token from FastAPI and pass it
 * into the tool dispatcher context. Tools that need it (calendar, gmail, image_handle's
 * email-send path) use it directly.
 *
 * Endpoint: GET /api/v1/oauth/google/token/{user_id}
 * Response: { code, message, data: { access_token: "..." } | null, error, ... }
 */

import { env } from "./env.js";
import { serviceKeyHeaders } from "./auth.js";

export async function fetchGoogleToken(userId: string): Promise<string | null> {
  if (!userId) return null;
  try {
    const r = await fetch(
      `${env.FASTAPI_URL}/api/v1/oauth/google/token/${encodeURIComponent(userId)}`,
      {
        signal: AbortSignal.timeout(10_000),
        headers: serviceKeyHeaders(),
      },
    );
    if (!r.ok) {
      console.warn(`[oauth] FastAPI returned ${r.status} for user ${userId}`);
      return null;
    }
    const j = (await r.json()) as { data?: { access_token?: string } };
    return j.data?.access_token ?? null;
  } catch (err) {
    console.warn(`[oauth] fetch failed for user ${userId}:`, (err as Error).message);
    return null;
  }
}
