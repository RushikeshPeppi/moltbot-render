/**
 * Google Calendar tools — direct calls to https://www.googleapis.com/calendar/v3
 * using the OAuth access token attached to ToolContext.
 *
 * Time discipline (per CLAUDE.md):
 *   - For create/update: pass LOCAL time in `dateTime` field + `timeZone` field.
 *     Google does the UTC conversion. NEVER append Z, NEVER use date -u.
 *   - For list: timeMin/timeMax must be UTC RFC3339. We compute these from
 *     the user's local-day boundaries.
 */

import type Anthropic from "@anthropic-ai/sdk";
import { createHash, randomUUID } from "node:crypto";
import type { ToolContext } from "./index.js";

const CAL_BASE = "https://www.googleapis.com/calendar/v3/calendars/primary/events";

// ─── Schemas ───────────────────────────────────────────────────────────

export const CALENDAR_CREATE_TOOL: Anthropic.Tool = {
  name: "calendar_create",
  description:
    "Create a Google Calendar event on the user's primary calendar. Accepts local times — the runtime adds the user's timezone. By default a Google Meet link is generated; pass with_meet=false to skip. Returns event_id, htmlLink, and meet_url (if present).",
  input_schema: {
    type: "object",
    additionalProperties: false,
    required: ["title", "start_local", "end_local"],
    properties: {
      title: { type: "string", description: "Event title (summary)." },
      start_local: {
        type: "string",
        description: "ISO 8601 LOCAL start time (no Z, no offset). e.g. '2026-05-02T14:00:00'.",
      },
      end_local: {
        type: "string",
        description: "ISO 8601 LOCAL end time. e.g. '2026-05-02T14:30:00'.",
      },
      location: { type: "string", description: "Optional location (address or URL)." },
      description: { type: "string", description: "Optional event description." },
      attendees: {
        type: "array",
        items: { type: "string", description: "Email address" },
        description: "Optional list of attendee email addresses.",
      },
      with_meet: {
        type: "boolean",
        description: "Generate a Google Meet link (default true).",
      },
    },
  },
};

export const CALENDAR_LIST_TOOL: Anthropic.Tool = {
  name: "calendar_list",
  description:
    "List upcoming events from the user's primary calendar. By default returns events from now to 7 days out. Specify time_window_local to override (e.g. just today, just tomorrow, this week). Returns array of {id, title, start, end, location, attendees}.",
  input_schema: {
    type: "object",
    additionalProperties: false,
    properties: {
      time_window_local: {
        type: "object",
        additionalProperties: false,
        required: ["start_local", "end_local"],
        properties: {
          start_local: { type: "string", description: "ISO 8601 LOCAL start (no Z)." },
          end_local: { type: "string", description: "ISO 8601 LOCAL end (no Z)." },
        },
      },
      max_results: {
        type: "integer",
        description: "Max events to return. Default 10, max 50.",
      },
    },
  },
};

export const CALENDAR_UPDATE_TOOL: Anthropic.Tool = {
  name: "calendar_update",
  description:
    "Update an existing event by id. Pass only fields that are changing. Preserves attendees and Meet link unless those specific fields are provided.",
  input_schema: {
    type: "object",
    additionalProperties: false,
    required: ["event_id"],
    properties: {
      event_id: { type: "string", description: "Event id from calendar_list or calendar_create." },
      title: { type: "string" },
      start_local: { type: "string", description: "ISO 8601 LOCAL." },
      end_local: { type: "string", description: "ISO 8601 LOCAL." },
      location: { type: "string" },
      description: { type: "string" },
    },
  },
};

export const CALENDAR_DELETE_TOOL: Anthropic.Tool = {
  name: "calendar_delete",
  description:
    "Delete (cancel) a calendar event by id. Irreversible. If the user describes the event without an id, call calendar_list first.",
  input_schema: {
    type: "object",
    additionalProperties: false,
    required: ["event_id"],
    properties: {
      event_id: { type: "string" },
    },
  },
};

// ─── Implementations ───────────────────────────────────────────────────

export async function create(
  input: {
    title: string;
    start_local: string;
    end_local: string;
    location?: string;
    description?: string;
    attendees?: string[];
    with_meet?: boolean;
  },
  ctx: ToolContext,
): Promise<{ event_id: string; htmlLink: string; meet_url?: string }> {
  requireToken(ctx);
  const withMeet = input.with_meet !== false; // default true
  const body: Record<string, unknown> = {
    summary: input.title,
    start: { dateTime: input.start_local, timeZone: ctx.timezone },
    end: { dateTime: input.end_local, timeZone: ctx.timezone },
  };
  if (input.location) body.location = input.location;
  if (input.description) body.description = input.description;
  if (input.attendees?.length) {
    body.attendees = input.attendees.map((email) => ({ email }));
  }
  if (withMeet) {
    body.conferenceData = {
      createRequest: {
        requestId: randomUUID(),
        conferenceSolutionKey: { type: "hangoutsMeet" },
      },
    };
  }
  const url = `${CAL_BASE}${withMeet ? "?conferenceDataVersion=1" : ""}`;
  const idem = idempotencyKey(ctx, "calendar_create", `${input.title}|${input.start_local}`);
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${ctx.googleAccessToken}`,
      "Content-Type": "application/json",
      "X-Goog-Idempotency-Key": idem,
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(15_000),
  });
  const j = (await resp.json()) as {
    id?: string;
    htmlLink?: string;
    conferenceData?: { entryPoints?: Array<{ entryPointType?: string; uri?: string }> };
    error?: { message?: string; code?: number };
  };
  if (!resp.ok || j.error || !j.id) {
    throw new Error(j.error?.message ?? `calendar create failed (HTTP ${resp.status})`);
  }
  const meetUrl = j.conferenceData?.entryPoints?.find((e) => e.entryPointType === "video")?.uri;
  return { event_id: j.id, htmlLink: j.htmlLink ?? "", meet_url: meetUrl };
}

export async function list(
  input: { time_window_local?: { start_local: string; end_local: string }; max_results?: number },
  ctx: ToolContext,
): Promise<Array<{ id: string; title: string; start: string; end: string; location?: string; attendees?: string[] }>> {
  requireToken(ctx);
  const max = Math.min(input.max_results ?? 10, 50);
  let timeMin: string;
  let timeMax: string;
  if (input.time_window_local) {
    timeMin = localToUtc(input.time_window_local.start_local, ctx.timezone);
    timeMax = localToUtc(input.time_window_local.end_local, ctx.timezone);
  } else {
    const now = new Date();
    timeMin = now.toISOString();
    timeMax = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000).toISOString();
  }
  const url = `${CAL_BASE}?timeMin=${encodeURIComponent(timeMin)}&timeMax=${encodeURIComponent(timeMax)}&singleEvents=true&orderBy=startTime&maxResults=${max}`;
  const resp = await fetch(url, {
    headers: { Authorization: `Bearer ${ctx.googleAccessToken}` },
    signal: AbortSignal.timeout(15_000),
  });
  const j = (await resp.json()) as {
    items?: Array<{
      id: string;
      summary?: string;
      start?: { dateTime?: string; date?: string };
      end?: { dateTime?: string; date?: string };
      location?: string;
      attendees?: Array<{ email?: string }>;
      error?: unknown;
    }>;
    error?: { message?: string };
  };
  if (!resp.ok || j.error) throw new Error(j.error?.message ?? `calendar list failed (HTTP ${resp.status})`);
  const items = j.items ?? [];
  return items.map((e) => ({
    id: e.id,
    title: e.summary ?? "(untitled)",
    start: e.start?.dateTime ?? e.start?.date ?? "",
    end: e.end?.dateTime ?? e.end?.date ?? "",
    location: e.location,
    attendees: e.attendees?.map((a) => a.email).filter(Boolean) as string[] | undefined,
  }));
}

export async function update(
  input: {
    event_id: string;
    title?: string;
    start_local?: string;
    end_local?: string;
    location?: string;
    description?: string;
  },
  ctx: ToolContext,
): Promise<{ event_id: string; htmlLink: string }> {
  requireToken(ctx);
  // Use PATCH to update only specified fields without losing attendees / conferenceData.
  const body: Record<string, unknown> = {};
  if (input.title !== undefined) body.summary = input.title;
  if (input.start_local !== undefined) body.start = { dateTime: input.start_local, timeZone: ctx.timezone };
  if (input.end_local !== undefined) body.end = { dateTime: input.end_local, timeZone: ctx.timezone };
  if (input.location !== undefined) body.location = input.location;
  if (input.description !== undefined) body.description = input.description;

  const resp = await fetch(`${CAL_BASE}/${encodeURIComponent(input.event_id)}`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${ctx.googleAccessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(15_000),
  });
  const j = (await resp.json()) as { id?: string; htmlLink?: string; error?: { message?: string } };
  if (!resp.ok || j.error) throw new Error(j.error?.message ?? `calendar update failed (HTTP ${resp.status})`);
  return { event_id: j.id ?? input.event_id, htmlLink: j.htmlLink ?? "" };
}

export async function delete_(input: { event_id: string }, ctx: ToolContext): Promise<{ event_id: string; status: string }> {
  requireToken(ctx);
  const resp = await fetch(`${CAL_BASE}/${encodeURIComponent(input.event_id)}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${ctx.googleAccessToken}` },
    signal: AbortSignal.timeout(15_000),
  });
  if (!resp.ok && resp.status !== 410) {
    // 410 Gone = already deleted, treat as success.
    let msg = `calendar delete failed (HTTP ${resp.status})`;
    try {
      const j = (await resp.json()) as { error?: { message?: string } };
      if (j.error?.message) msg = j.error.message;
    } catch {
      // ignore
    }
    throw new Error(msg);
  }
  return { event_id: input.event_id, status: "deleted" };
}

// ─── Helpers ───────────────────────────────────────────────────────────

function requireToken(ctx: ToolContext): void {
  if (!ctx.googleAccessToken) {
    throw new Error(
      "Google connection not available — your Google account may need to be reconnected.",
    );
  }
}

/**
 * Convert a local-time ISO string + timezone to a UTC RFC3339 string.
 * Used for calendar list timeMin/timeMax.
 *
 * Implementation: parse local date components, construct a Date assuming the
 * timezone's offset, output toISOString().
 *
 * For simplicity we use Intl.DateTimeFormat to compute the timezone offset
 * at the given local time, then adjust.
 */
function localToUtc(localIso: string, timezone: string): string {
  // localIso shape: "2026-05-02T14:00:00" — no Z, no offset.
  const [datePart, timePart] = localIso.split("T");
  if (!datePart || !timePart) {
    // Fallback: trust the input if it's already an ISO with Z.
    return new Date(localIso).toISOString();
  }
  // Construct a Date *as if* the local-iso were UTC, then adjust by the TZ offset.
  const asUtc = new Date(`${datePart}T${timePart}Z`);
  const offsetMin = getTimezoneOffsetMinutes(asUtc, timezone);
  return new Date(asUtc.getTime() - offsetMin * 60_000).toISOString();
}

function getTimezoneOffsetMinutes(at: Date, timezone: string): number {
  // Returns the offset in minutes from UTC for the given timezone at the given instant.
  // Uses Intl to extract the parts.
  try {
    const fmt = new Intl.DateTimeFormat("en-US", {
      timeZone: timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
    const parts = fmt.formatToParts(at).reduce<Record<string, string>>((acc, p) => {
      if (p.type !== "literal") acc[p.type] = p.value;
      return acc;
    }, {});
    const localTime = Date.UTC(
      parseInt(parts.year),
      parseInt(parts.month) - 1,
      parseInt(parts.day),
      parseInt(parts.hour) === 24 ? 0 : parseInt(parts.hour),
      parseInt(parts.minute),
      parseInt(parts.second),
    );
    return Math.round((localTime - at.getTime()) / 60_000);
  } catch {
    return 0;
  }
}

function idempotencyKey(ctx: ToolContext, op: string, payload: string): string {
  return createHash("sha256")
    .update(`${ctx.userId}|${ctx.requestId}|${op}|${payload}`)
    .digest("hex")
    .slice(0, 32);
}
