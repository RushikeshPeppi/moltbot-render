/**
 * Reminder tools — talk to FastAPI's /api/v1/reminders/* endpoints.
 *
 * Idempotency: reminder_create computes a deterministic SHA-256 key from
 * (userId, requestId, trigger_at, message-prefix) and sends it as
 * X-Idempotency-Key. FastAPI side dedupes within a 5-minute window.
 *
 * Reads (list) are not idempotency-keyed — they're safe to repeat.
 */

import type Anthropic from "@anthropic-ai/sdk";
import { createHash } from "node:crypto";
import type { ToolContext } from "./index.js";

// ─── Schemas ───────────────────────────────────────────────────────────

export const REMINDER_CREATE_TOOL: Anthropic.Tool = {
  name: "reminder_create",
  description:
    "Create a reminder. Stores in DB and schedules via QStash for SMS delivery. Use 'recurrence':'none' for one-time, or 'daily' / 'weekdays' / 'weekly' / 'monthly'. Returns the reminder_id and trigger_at on success. The user must have explicitly stated what to be reminded about — do not invent the message.",
  input_schema: {
    type: "object",
    additionalProperties: false,
    required: ["message", "trigger_at", "recurrence"],
    properties: {
      message: {
        type: "string",
        description: "What to remind the user about. Must come from the user's words. Max 500 chars.",
      },
      trigger_at: {
        type: "string",
        description:
          "ISO 8601 LOCAL time (no Z, no offset). Example: '2026-05-02T18:00:00'. The backend converts to UTC using the user's timezone.",
      },
      recurrence: {
        type: "string",
        enum: ["none", "daily", "weekdays", "weekly", "monthly"],
        description: "How often to repeat. Use 'none' for one-time reminders.",
      },
    },
  },
};

export const REMINDER_LIST_TOOL: Anthropic.Tool = {
  name: "reminder_list",
  description:
    "List the user's pending reminders. Returns an array of {id, message, trigger_at, recurrence}. Use when the user asks to see, review, or check their reminders.",
  input_schema: {
    type: "object",
    additionalProperties: false,
    properties: {},
  },
};

export const REMINDER_CANCEL_TOOL: Anthropic.Tool = {
  name: "reminder_cancel",
  description:
    "Cancel a pending reminder by id. Pass the reminder_id from a previous reminder_list or reminder_create. If the user describes the reminder ('cancel my 9am water reminder') without an id, call reminder_list first to find the matching id, then cancel.",
  input_schema: {
    type: "object",
    additionalProperties: false,
    required: ["reminder_id"],
    properties: {
      reminder_id: {
        type: "integer",
        description: "Numeric reminder id from reminder_list or reminder_create.",
      },
    },
  },
};

export const REMINDER_UPDATE_TOOL: Anthropic.Tool = {
  name: "reminder_update",
  description:
    "Update an existing reminder's time, message, or recurrence. Pass only the fields that are changing (omit fields the user didn't mention). The backend keeps unchanged fields.",
  input_schema: {
    type: "object",
    additionalProperties: false,
    required: ["reminder_id"],
    properties: {
      reminder_id: { type: "integer", description: "Numeric reminder id." },
      message: { type: "string", description: "New message text. Optional." },
      trigger_at: {
        type: "string",
        description: "New ISO 8601 LOCAL time. Optional.",
      },
      recurrence: {
        type: "string",
        enum: ["none", "daily", "weekdays", "weekly", "monthly"],
        description: "New recurrence. Optional.",
      },
    },
  },
};

// ─── Implementations ───────────────────────────────────────────────────

export async function create(
  input: { message: string; trigger_at: string; recurrence: string },
  ctx: ToolContext,
): Promise<{ reminder_id: number; message: string; trigger_at: string }> {
  const idem = idempotencyKey(ctx, "reminder_create", `${input.trigger_at}|${input.message.slice(0, 100)}`);
  const resp = await fetch(`${ctx.fastApiUrl}/api/v1/reminders/create`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Idempotency-Key": idem,
    },
    body: JSON.stringify({
      user_id: ctx.userId,
      message: input.message,
      trigger_at: input.trigger_at,
      user_timezone: ctx.timezone,
      recurrence: input.recurrence,
    }),
    signal: AbortSignal.timeout(15_000),
  });
  const j = (await resp.json()) as { code?: number; message?: string; data?: { id: number } };
  if (!resp.ok || (j.code && j.code >= 400) || !j.data?.id) {
    throw new Error(j.message ?? `reminder create failed (HTTP ${resp.status})`);
  }
  return { reminder_id: j.data.id, message: input.message, trigger_at: input.trigger_at };
}

export async function list(_input: unknown, ctx: ToolContext): Promise<Array<{ id: number; message: string; trigger_at: string; recurrence: string }>> {
  const resp = await fetch(
    `${ctx.fastApiUrl}/api/v1/reminders/list/${encodeURIComponent(ctx.userId)}?status=pending`,
    { signal: AbortSignal.timeout(10_000) },
  );
  if (!resp.ok) throw new Error(`reminder list failed (HTTP ${resp.status})`);
  const j = (await resp.json()) as { data?: { reminders?: Array<{ id: number; message: string; trigger_at: string; recurrence: string }> } };
  const items = j.data?.reminders ?? [];
  // Return only the fields Claude needs — saves context tokens.
  return items.map((r) => ({
    id: r.id,
    message: r.message,
    trigger_at: r.trigger_at,
    recurrence: r.recurrence,
  }));
}

export async function cancel(input: { reminder_id: number }, ctx: ToolContext): Promise<{ reminder_id: number; status: string }> {
  const idem = idempotencyKey(ctx, "reminder_cancel", String(input.reminder_id));
  const resp = await fetch(`${ctx.fastApiUrl}/api/v1/reminders/cancel`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Idempotency-Key": idem,
    },
    body: JSON.stringify({ user_id: ctx.userId, reminder_id: input.reminder_id }),
    signal: AbortSignal.timeout(10_000),
  });
  const j = (await resp.json()) as { code?: number; message?: string; data?: { status?: string } };
  if (!resp.ok || (j.code && j.code >= 400)) {
    throw new Error(j.message ?? `reminder cancel failed (HTTP ${resp.status})`);
  }
  return { reminder_id: input.reminder_id, status: j.data?.status ?? "cancelled" };
}

export async function update(
  input: { reminder_id: number; message?: string; trigger_at?: string; recurrence?: string },
  ctx: ToolContext,
): Promise<{ reminder_id: number; status: string }> {
  const idem = idempotencyKey(
    ctx,
    "reminder_update",
    `${input.reminder_id}|${input.trigger_at ?? ""}|${input.message?.slice(0, 100) ?? ""}|${input.recurrence ?? ""}`,
  );
  const body: Record<string, unknown> = {
    user_id: ctx.userId,
    reminder_id: input.reminder_id,
  };
  if (input.message !== undefined) body.message = input.message;
  if (input.trigger_at !== undefined) {
    body.trigger_at = input.trigger_at;
    body.user_timezone = ctx.timezone;
  }
  if (input.recurrence !== undefined) body.recurrence = input.recurrence;

  const resp = await fetch(`${ctx.fastApiUrl}/api/v1/reminders/update`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Idempotency-Key": idem,
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(10_000),
  });
  const j = (await resp.json()) as { code?: number; message?: string; data?: { status?: string } };
  if (!resp.ok || (j.code && j.code >= 400)) {
    throw new Error(j.message ?? `reminder update failed (HTTP ${resp.status})`);
  }
  return { reminder_id: input.reminder_id, status: j.data?.status ?? "updated" };
}

// ─── Helpers ───────────────────────────────────────────────────────────

function idempotencyKey(ctx: ToolContext, op: string, payload: string): string {
  return createHash("sha256")
    .update(`${ctx.userId}|${ctx.requestId}|${op}|${payload}`)
    .digest("hex")
    .slice(0, 32);
}
