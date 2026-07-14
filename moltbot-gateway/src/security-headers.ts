/**
 * Security-response-header middleware for the Express gateway (CASA 4.1.1, 5.1.7, 6.2.1).
 *
 * The gateway is the OTHER half of Phase 4 §4.2. Fixing headers on FastAPI and forgetting
 * Express is the classic miss the phase plan calls out by name — the gateway is a separate
 * public origin (openclaw-gateway-dg3y.onrender.com) and the lab scans it too. Its ZAP
 * baseline was actually WORSE than the wrapper's: 7 WARN vs 5, including the Express
 * `X-Powered-By` version leak.
 *
 * Closes: ZAP [10015] Cache-control · [10021] X-Content-Type-Options · [10035] HSTS ·
 *         [10037] X-Powered-By leak · [10049] Storable/Cacheable · [10063] Permissions-Policy ·
 *         [90004] Cross-Origin-Resource-Policy   (+ Fluid 043/131/132/440)
 *
 * Header VALUES are deliberately identical to the FastAPI wrapper's
 * (fastapi-wrapper/app/core/security_headers.py) — two origins of the same product that
 * disagree on HSTS max-age or CSP is a finding in itself. Keep them in sync.
 *
 * This is a JSON API with no rendered HTML, so `default-src 'none'` is the correct CSP.
 */

import type { NextFunction, Request, Response } from "express";

const PERMISSIONS_POLICY = [
  "accelerometer=()",
  "autoplay=()",
  "camera=()",
  "display-capture=()",
  "encrypted-media=()",
  "fullscreen=()",
  "geolocation=()",
  "gyroscope=()",
  "magnetometer=()",
  "microphone=()",
  "midi=()",
  "payment=()",
  "picture-in-picture=()",
  "usb=()",
  "xr-spatial-tracking=()",
].join(", ");

const CSP = [
  "default-src 'none'",
  "frame-ancestors 'none'",
  "base-uri 'none'",
  "form-action 'none'",
  "object-src 'none'",
].join("; ");

export function securityHeaders(_req: Request, res: Response, next: NextFunction): void {
  res.setHeader("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload");
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.setHeader("X-Frame-Options", "DENY");
  res.setHeader("Referrer-Policy", "strict-origin-when-cross-origin");
  res.setHeader("Cross-Origin-Resource-Policy", "same-origin");
  res.setHeader("Cross-Origin-Opener-Policy", "same-origin");
  res.setHeader("Permissions-Policy", PERMISSIONS_POLICY);
  res.setHeader("Content-Security-Policy", CSP);
  // Agent responses carry the user's mail/calendar content — never cacheable.
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("Pragma", "no-cache");
  next();
}
