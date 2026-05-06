/**
 * current_time — return the user's current local date/time, structured.
 *
 * Why: Sonnet's training cutoff is Aug 2025; on real production traffic
 * "tomorrow" / "next Monday" / "in 2 hours" all resolve to garbage without an
 * anchor. We already inject a `[now: ...]` line into the fresh user turn,
 * but that line is stale by iteration 2 if a tool took 30s+ in iter 1.
 * This tool is the deterministic, callable source of truth — the model can
 * invoke it any iteration it needs the wall clock.
 *
 * No external calls, no auth, ~1ms latency. Cheap to expose.
 */

import type Anthropic from "@anthropic-ai/sdk";
import type { ToolContext } from "./index.js";

export const CURRENT_TIME_TOOL: Anthropic.Tool = {
  name: "current_time",
  description:
    "Get the current local date and time for the user. Call this BEFORE acting on any relative time reference like 'tomorrow', 'tonight', 'next Monday', 'in 2 hours', 'this evening', or to verify whether a time is in the past or future. Your training-data sense of 'today' is wrong — use this. Returns an object with iso, date, time, weekday, year, month, day, hour, minute, timezone, and a `tomorrow_date` convenience field. No input required.",
  input_schema: {
    type: "object",
    additionalProperties: false,
    properties: {},
  },
};

export interface CurrentTimeResult {
  iso: string;          // e.g. "2026-05-06T17:30:42"
  date: string;         // "2026-05-06"
  time: string;         // "17:30:42"
  weekday: string;      // "Tue"
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
  timezone: string;     // "Asia/Kolkata"
  tomorrow_date: string; // "2026-05-07" — saves the model a calendar-math step
  city?: string;
}

export async function execute(
  _input: Record<string, never>,
  ctx: ToolContext,
): Promise<CurrentTimeResult> {
  const tz = ctx.timezone || "UTC";
  const now = new Date();
  const tomorrow = new Date(now.getTime() + 24 * 60 * 60 * 1000);

  const fmtParts = (d: Date) => {
    const fmt = new Intl.DateTimeFormat("en-CA", {
      timeZone: tz,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      weekday: "short",
      hour12: false,
    });
    return fmt.formatToParts(d).reduce<Record<string, string>>((acc, p) => {
      if (p.type !== "literal") acc[p.type] = p.value;
      return acc;
    }, {});
  };

  const p = fmtParts(now);
  const t = fmtParts(tomorrow);

  // 24:xx → 00:xx normalize (some Intl impls return 24 for midnight).
  const hourNum = parseInt(p.hour, 10) % 24;

  return {
    iso: `${p.year}-${p.month}-${p.day}T${String(hourNum).padStart(2, "0")}:${p.minute}:${p.second}`,
    date: `${p.year}-${p.month}-${p.day}`,
    time: `${String(hourNum).padStart(2, "0")}:${p.minute}:${p.second}`,
    weekday: p.weekday,
    year: parseInt(p.year, 10),
    month: parseInt(p.month, 10),
    day: parseInt(p.day, 10),
    hour: hourNum,
    minute: parseInt(p.minute, 10),
    second: parseInt(p.second, 10),
    timezone: tz,
    tomorrow_date: `${t.year}-${t.month}-${t.day}`,
    city: ctx.city,
  };
}
