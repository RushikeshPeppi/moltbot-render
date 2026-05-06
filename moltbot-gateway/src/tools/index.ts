/**
 * Tool registry + dispatcher.
 *
 * The TOOLS array is what we send to Anthropic in the messages.create call.
 * The LAST tool gets `cache_control: {ttl: "1h"}` — that breakpoint covers the
 * entire tools array AND the system prompt that follows it.
 *
 * dispatchTool routes a tool_use block from Claude's response to the right
 * implementation. Errors are caught by the agent loop wrapper (src/agent.ts)
 * and returned as `tool_result` with `is_error: true` — the dispatcher itself
 * MAY throw, the loop catches.
 */

import type Anthropic from "@anthropic-ai/sdk";
import * as web from "./web_search.js";
import * as rem from "./reminders.js";
import * as cal from "./calendar.js";
import * as gm from "./gmail.js";
import * as img from "./image.js";
import * as tm from "./time.js";

export interface ToolContext {
  userId: string;
  googleAccessToken?: string;
  timezone: string;
  city?: string;
  fastApiUrl: string;
  searxngUrl: string;
  /**
   * Per-/execute UUID. Used to seed deterministic idempotency keys across
   * tool retries. Same userId + same requestId + same args → same key.
   */
  requestId: string;
}

// Tool definitions. We do NOT add cache_control here — the cache_control on the
// system text block (see agent.ts) covers the entire (tools + system) prefix in
// a single breakpoint, since Anthropic's prefix walker is tools → system → messages.
// Adding a separate breakpoint here would write a redundant `tools-only` cache
// entry that's never re-read in practice.
export const TOOLS: Anthropic.Tool[] = [
  tm.CURRENT_TIME_TOOL,
  web.WEB_SEARCH_TOOL,
  rem.REMINDER_CREATE_TOOL,
  rem.REMINDER_LIST_TOOL,
  rem.REMINDER_CANCEL_TOOL,
  rem.REMINDER_UPDATE_TOOL,
  cal.CALENDAR_CREATE_TOOL,
  cal.CALENDAR_LIST_TOOL,
  cal.CALENDAR_UPDATE_TOOL,
  cal.CALENDAR_DELETE_TOOL,
  gm.GMAIL_SEND_TOOL,
  gm.GMAIL_LIST_TOOL,
  gm.GMAIL_REPLY_TOOL,
  gm.GMAIL_MARK_TOOL,
  img.IMAGE_HANDLE_TOOL,
];

export async function dispatchTool(name: string, input: unknown, ctx: ToolContext): Promise<unknown> {
  const i = input as Record<string, unknown>;
  switch (name) {
    case "current_time":
      return tm.execute(i as Record<string, never>, ctx);

    case "web_search":
      return web.execute(i as { query: string; time_range?: string }, ctx);

    case "reminder_create":
      return rem.create(i as { message: string; trigger_at: string; recurrence: string }, ctx);
    case "reminder_list":
      return rem.list(i, ctx);
    case "reminder_cancel":
      return rem.cancel(i as { reminder_id: number }, ctx);
    case "reminder_update":
      return rem.update(i as { reminder_id: number; message?: string; trigger_at?: string; recurrence?: string }, ctx);

    case "calendar_create":
      return cal.create(
        i as {
          title: string;
          start_local: string;
          end_local: string;
          location?: string;
          description?: string;
          attendees?: string[];
          with_meet?: boolean;
        },
        ctx,
      );
    case "calendar_list":
      return cal.list(
        i as { time_window_local?: { start_local: string; end_local: string }; max_results?: number },
        ctx,
      );
    case "calendar_update":
      return cal.update(
        i as {
          event_id: string;
          title?: string;
          start_local?: string;
          end_local?: string;
          location?: string;
          description?: string;
        },
        ctx,
      );
    case "calendar_delete":
      return cal.delete_(i as { event_id: string }, ctx);

    case "gmail_send":
      return gm.send(i as { to: string; subject: string; body: string }, ctx);
    case "gmail_list":
      return gm.list(i as { query?: string; max_results?: number }, ctx);
    case "gmail_reply":
      return gm.reply(i as { message_id: string; body: string }, ctx);
    case "gmail_mark":
      return gm.mark(
        i as { message_id: string; action: "read" | "unread" | "starred" | "unstarred" },
        ctx,
      );

    case "image_handle":
      return img.handle(i as { image_url: string }, ctx);

    default:
      throw new Error(`Unknown tool: ${name}`);
  }
}
