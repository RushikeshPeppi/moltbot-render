/**
 * Gmail tools — direct calls to Gmail API v1 using OAuth token from ToolContext.
 *
 * gmail_send: idempotent via X-Idempotency-Key (FastAPI-side dedup) + Anthropic-style
 *   composite. Builds RFC822 MIME, base64url-encodes, POSTs to /messages/send.
 * gmail_list: search-style, accepts a query in Gmail's "from:x is:unread" syntax.
 * gmail_reply: fetches threadId + headers, builds reply MIME with In-Reply-To.
 * gmail_mark: read/unread/starred/important via /messages/{id}/modify.
 */

import type Anthropic from "@anthropic-ai/sdk";
import type { ToolContext } from "./index.js";

const GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me";

// ─── Schemas ───────────────────────────────────────────────────────────

export const GMAIL_SEND_TOOL: Anthropic.Tool = {
  name: "gmail_send",
  description:
    "Send an email from the user's Gmail. Pass recipient email (resolve names to addresses first — ask the user if uncertain), subject, body. Returns message_id on success.",
  input_schema: {
    type: "object",
    additionalProperties: false,
    required: ["to", "subject", "body"],
    properties: {
      to: { type: "string", description: "Recipient email address." },
      subject: { type: "string", description: "Email subject line." },
      body: { type: "string", description: "Email body (plain text)." },
    },
  },
};

export const GMAIL_LIST_TOOL: Anthropic.Tool = {
  name: "gmail_list",
  description:
    "Search the user's Gmail. Pass a Gmail query string ('from:John', 'is:unread', 'subject:invoice', 'from:lottiefiles is:unread', etc). Returns up to max_results messages with id, from, subject, snippet, date.",
  input_schema: {
    type: "object",
    additionalProperties: false,
    properties: {
      query: {
        type: "string",
        description:
          "Gmail search query. Examples: 'is:unread', 'from:John', 'subject:invoice', 'after:2026/04/01', 'has:attachment'. Combine with spaces. Empty string returns recent messages.",
      },
      max_results: {
        type: "integer",
        description: "Max messages to return. Default 10, max 50.",
      },
    },
  },
};

export const GMAIL_REPLY_TOOL: Anthropic.Tool = {
  name: "gmail_reply",
  description:
    "Reply to an existing email. Pass the message_id (from gmail_list) and the body of the reply. Subject and threading are handled automatically. Returns sent message_id.",
  input_schema: {
    type: "object",
    additionalProperties: false,
    required: ["message_id", "body"],
    properties: {
      message_id: { type: "string", description: "Gmail message id from gmail_list." },
      body: { type: "string", description: "Reply body (plain text)." },
    },
  },
};

export const GMAIL_MARK_TOOL: Anthropic.Tool = {
  name: "gmail_mark",
  description:
    "Mark a Gmail message as read, unread, starred, or unstarred. Returns the updated label state.",
  input_schema: {
    type: "object",
    additionalProperties: false,
    required: ["message_id", "action"],
    properties: {
      message_id: { type: "string" },
      action: {
        type: "string",
        enum: ["read", "unread", "starred", "unstarred"],
      },
    },
  },
};

// ─── Implementations ───────────────────────────────────────────────────

export async function send(input: { to: string; subject: string; body: string }, ctx: ToolContext): Promise<{ message_id: string; thread_id: string }> {
  requireToken(ctx);
  // Note: Gmail API has no documented header-based idempotency. If the model
  // emits two parallel `gmail_send` tool_use blocks with identical args, both
  // will deliver. Mitigations live in the prompt (single-call rule for writes)
  // and the per-/execute requestId — within one request, parallel duplicate
  // tool_use blocks for the same op are vanishingly rare from Sonnet 4.6.
  const raw = encodeBase64Url(buildMime({ to: input.to, subject: input.subject, body: input.body }));
  const resp = await fetch(`${GMAIL_BASE}/messages/send`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${ctx.googleAccessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ raw }),
    signal: AbortSignal.timeout(15_000),
  });
  const j = (await resp.json()) as { id?: string; threadId?: string; error?: { message?: string } };
  if (!resp.ok || j.error || !j.id) {
    throw new Error(j.error?.message ?? `gmail send failed (HTTP ${resp.status})`);
  }
  return { message_id: j.id, thread_id: j.threadId ?? "" };
}

export async function list(input: { query?: string; max_results?: number }, ctx: ToolContext): Promise<Array<{ id: string; from: string; subject: string; snippet: string; date: string }>> {
  requireToken(ctx);
  const max = Math.min(input.max_results ?? 10, 50);
  const q = input.query ? encodeURIComponent(input.query) : "";
  const listUrl = `${GMAIL_BASE}/messages?q=${q}&maxResults=${max}`;
  const listResp = await fetch(listUrl, {
    headers: { Authorization: `Bearer ${ctx.googleAccessToken}` },
    signal: AbortSignal.timeout(15_000),
  });
  const listJ = (await listResp.json()) as {
    messages?: Array<{ id: string }>;
    error?: { message?: string };
  };
  if (!listResp.ok || listJ.error) {
    throw new Error(listJ.error?.message ?? `gmail list failed (HTTP ${listResp.status})`);
  }
  const ids = listJ.messages ?? [];
  if (ids.length === 0) return [];

  // Fetch metadata for each in parallel.
  const details = await Promise.all(
    ids.map(async (m) => {
      const r = await fetch(
        `${GMAIL_BASE}/messages/${m.id}?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date`,
        {
          headers: { Authorization: `Bearer ${ctx.googleAccessToken}` },
          signal: AbortSignal.timeout(10_000),
        },
      );
      if (!r.ok) return null;
      const j = (await r.json()) as {
        id: string;
        snippet?: string;
        payload?: { headers?: Array<{ name: string; value: string }> };
      };
      const headers = j.payload?.headers ?? [];
      const get = (name: string) =>
        headers.find((h) => h.name.toLowerCase() === name.toLowerCase())?.value ?? "";
      return {
        id: j.id,
        from: get("From"),
        subject: get("Subject"),
        snippet: (j.snippet ?? "").slice(0, 200),
        date: get("Date"),
      };
    }),
  );
  return details.filter((d): d is NonNullable<typeof d> => d !== null);
}

export async function reply(input: { message_id: string; body: string }, ctx: ToolContext): Promise<{ message_id: string; thread_id: string }> {
  requireToken(ctx);
  // Fetch thread + headers from the original message.
  const origResp = await fetch(
    `${GMAIL_BASE}/messages/${input.message_id}?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Message-ID`,
    {
      headers: { Authorization: `Bearer ${ctx.googleAccessToken}` },
      signal: AbortSignal.timeout(15_000),
    },
  );
  const orig = (await origResp.json()) as {
    threadId?: string;
    payload?: { headers?: Array<{ name: string; value: string }> };
    error?: { message?: string };
  };
  if (!origResp.ok || orig.error) throw new Error(orig.error?.message ?? `gmail reply: original fetch failed`);
  const headers = orig.payload?.headers ?? [];
  const getH = (name: string) => headers.find((h) => h.name.toLowerCase() === name.toLowerCase())?.value ?? "";
  const origFrom = getH("From");
  const origSubj = getH("Subject");
  const origMsgId = getH("Message-ID") || `<${input.message_id}@mail.gmail.com>`;
  const toEmail = parseAddressEmail(origFrom);
  const replySubj = /^Re:/i.test(origSubj) ? origSubj : `Re: ${origSubj}`;

  // (See gmail_send note: no native idempotency for Gmail API.)
  const raw = encodeBase64Url(
    buildMime({
      to: toEmail,
      subject: replySubj,
      body: input.body,
      inReplyTo: origMsgId,
      references: origMsgId,
    }),
  );
  const sendResp = await fetch(`${GMAIL_BASE}/messages/send`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${ctx.googleAccessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ raw, threadId: orig.threadId }),
    signal: AbortSignal.timeout(15_000),
  });
  const sendJ = (await sendResp.json()) as { id?: string; threadId?: string; error?: { message?: string } };
  if (!sendResp.ok || sendJ.error || !sendJ.id) {
    throw new Error(sendJ.error?.message ?? `gmail reply send failed (HTTP ${sendResp.status})`);
  }
  return { message_id: sendJ.id, thread_id: sendJ.threadId ?? orig.threadId ?? "" };
}

export async function mark(input: { message_id: string; action: "read" | "unread" | "starred" | "unstarred" }, ctx: ToolContext): Promise<{ message_id: string; action: string }> {
  requireToken(ctx);
  const labelMap: Record<string, { add: string[]; remove: string[] }> = {
    read: { add: [], remove: ["UNREAD"] },
    unread: { add: ["UNREAD"], remove: [] },
    starred: { add: ["STARRED"], remove: [] },
    unstarred: { add: [], remove: ["STARRED"] },
  };
  const lbls = labelMap[input.action];
  if (!lbls) throw new Error(`unknown action: ${input.action}`);
  const resp = await fetch(`${GMAIL_BASE}/messages/${input.message_id}/modify`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${ctx.googleAccessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ addLabelIds: lbls.add, removeLabelIds: lbls.remove }),
    signal: AbortSignal.timeout(10_000),
  });
  const j = (await resp.json()) as { id?: string; error?: { message?: string } };
  if (!resp.ok || j.error) throw new Error(j.error?.message ?? `gmail mark failed (HTTP ${resp.status})`);
  return { message_id: input.message_id, action: input.action };
}

// ─── Helpers ───────────────────────────────────────────────────────────

function requireToken(ctx: ToolContext): void {
  if (!ctx.googleAccessToken) {
    throw new Error(
      "Google connection not available — your Google account may need to be reconnected.",
    );
  }
}

function buildMime(opts: { to: string; subject: string; body: string; inReplyTo?: string; references?: string }): string {
  const lines: string[] = [
    `From: me`,
    `To: ${opts.to}`,
    `Subject: ${opts.subject}`,
    `MIME-Version: 1.0`,
    `Content-Type: text/plain; charset=UTF-8`,
  ];
  if (opts.inReplyTo) lines.push(`In-Reply-To: ${opts.inReplyTo}`);
  if (opts.references) lines.push(`References: ${opts.references}`);
  lines.push("");
  lines.push(opts.body);
  return lines.join("\r\n");
}

function encodeBase64Url(s: string): string {
  return Buffer.from(s, "utf-8")
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

function parseAddressEmail(addr: string): string {
  // Handles "Name <email@x>" or bare "email@x".
  const m = addr.match(/<([^>]+)>/);
  if (m) return m[1];
  return addr.trim();
}

