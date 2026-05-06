/**
 * In-memory session store.
 *
 * Holds per-user conversation history (the `messages` array we feed to Claude).
 * Replaces OpenClaw's session.jsonl-on-disk model.
 *
 * Single-instance Render deploy: in-memory is fine. If we scale to multi-instance,
 * swap for Postgres (Neon serverless) — same interface, ~30 LOC delta.
 *
 * Eviction:
 *   - idle TTL: 30 min since last touch → drop
 *   - hard cap: 10,000 sessions → drop oldest first (insertion-order LRU)
 */

import type Anthropic from "@anthropic-ai/sdk";

export interface Session {
  history: Anthropic.MessageParam[];
  lastTouched: number;
}

const MAX_SESSIONS = 10_000;
const IDLE_TTL_MS = 30 * 60 * 1000; // 30 min

const sessions = new Map<string, Session>();

export function getSession(peerId: string): Session {
  let s = sessions.get(peerId);
  if (!s) {
    s = { history: [], lastTouched: Date.now() };
    sessions.set(peerId, s);
  } else {
    s.lastTouched = Date.now();
    // Move to end of insertion order — naive LRU on Map.
    sessions.delete(peerId);
    sessions.set(peerId, s);
  }
  evictIfNeeded();
  return s;
}

export function setSessionHistory(peerId: string, history: Anthropic.MessageParam[]): void {
  const s = getSession(peerId);
  s.history = history;
  s.lastTouched = Date.now();
}

export function clearSession(peerId: string): void {
  sessions.delete(peerId);
}

export function sessionCount(): number {
  return sessions.size;
}

function evictIfNeeded(): void {
  const now = Date.now();
  // Evict idle sessions.
  for (const [k, v] of sessions) {
    if (now - v.lastTouched > IDLE_TTL_MS) sessions.delete(k);
  }
  // Hard cap (after idle eviction, if still over).
  while (sessions.size > MAX_SESSIONS) {
    const oldest = sessions.keys().next().value;
    if (!oldest) break;
    sessions.delete(oldest);
  }
}
