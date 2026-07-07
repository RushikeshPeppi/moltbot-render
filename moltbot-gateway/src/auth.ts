/**
 * Service-to-service auth for the gateway.
 *
 * /execute runs the full tool-enabled agent for a user and reaches their Google
 * data — it must never be callable anonymously (CASA Ch1/Ch3, finding P0-3).
 * Only the FastAPI wrapper (which authenticated the user upstream) may call it,
 * proving itself with the shared INTERNAL_SERVICE_KEY in the X-Moltbot-Key header.
 *
 * FAIL CLOSED: if INTERNAL_SERVICE_KEY is unset, every guarded route returns 503.
 * Timing-safe comparison via crypto.timingSafeEqual.
 */

import { timingSafeEqual } from "node:crypto";
import type { NextFunction, Request, Response } from "express";
import { env } from "./env.js";

function safeEqual(a: string, b: string): boolean {
  const ab = Buffer.from(a);
  const bb = Buffer.from(b);
  // timingSafeEqual throws on length mismatch; compare lengths first (constant
  // outcome for our fixed-length secret) then the bytes.
  if (ab.length !== bb.length) return false;
  return timingSafeEqual(ab, bb);
}

export function requireServiceAuth(
  req: Request,
  res: Response,
  next: NextFunction,
): void {
  const expected = env.INTERNAL_SERVICE_KEY;
  if (!expected) {
    res.status(503).json({ success: false, error: "INTERNAL_SERVICE_KEY not configured on server" });
    return;
  }
  const provided = req.header("X-Moltbot-Key") ?? "";
  if (!safeEqual(provided, expected)) {
    res.status(401).json({ success: false, error: "Invalid or missing service key" });
    return;
  }
  next();
}
