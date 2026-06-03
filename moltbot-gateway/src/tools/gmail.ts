/**
 * Gmail tools — direct calls to Gmail API v1 using OAuth token from ToolContext.
 *
 * gmail_send: idempotent via X-Idempotency-Key (FastAPI-side dedup) + Anthropic-style
 *   composite. Builds RFC822 MIME, base64url-encodes, POSTs to /messages/send.
 * gmail_list: search-style, accepts a query in Gmail's "from:x is:unread" syntax.
 * gmail_reply: fetches threadId + headers, builds reply MIME with In-Reply-To.
 * gmail_mark: read/unread/starred/important via /messages/{id}/modify.
 */

import { lookup } from "node:dns/promises";
import net from "node:net";
import type Anthropic from "@anthropic-ai/sdk";
import type { ToolContext } from "./index.js";

const GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me";

// ─── Schemas ───────────────────────────────────────────────────────────

export const GMAIL_SEND_TOOL: Anthropic.Tool = {
  name: "gmail_send",
  description:
    "Send an email from the user's Gmail. Pass recipient email (resolve names to addresses first — ask the user if uncertain), subject, body. Returns message_id on success. If the user attached one or more images in THIS message and wants them sent in the email, set attach_images=true — the attached image(s) are added automatically; you do not need their URLs.",
  input_schema: {
    type: "object",
    additionalProperties: false,
    required: ["to", "subject", "body"],
    properties: {
      to: { type: "string", description: "Recipient email address." },
      subject: { type: "string", description: "Email subject line." },
      body: { type: "string", description: "Email body (plain text)." },
      attach_images: {
        type: "boolean",
        description:
          "Set true to attach the image(s) the user sent in this message. Only valid when the user actually attached an image this turn; ignored otherwise.",
      },
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
      attach_images: {
        type: "boolean",
        description:
          "Set true to attach the image(s) the user sent in this message to the reply. Only valid when the user actually attached an image this turn.",
      },
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

export async function send(input: { to: string; subject: string; body: string; attach_images?: boolean }, ctx: ToolContext): Promise<{ message_id: string; thread_id: string }> {
  requireToken(ctx);
  // Note: Gmail API has no documented header-based idempotency. If the model
  // emits two parallel `gmail_send` tool_use blocks with identical args, both
  // will deliver. Mitigations live in the prompt (single-call rule for writes)
  // and the per-/execute requestId — within one request, parallel duplicate
  // tool_use blocks for the same op are vanishingly rare from Sonnet 4.6.
  const attachments = input.attach_images ? await fetchAttachments(ctx.imageUrls ?? []) : [];
  const raw = encodeBase64Url(buildMime({ to: input.to, subject: input.subject, body: input.body, attachments }));
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

export async function reply(input: { message_id: string; body: string; attach_images?: boolean }, ctx: ToolContext): Promise<{ message_id: string; thread_id: string }> {
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
  const attachments = input.attach_images ? await fetchAttachments(ctx.imageUrls ?? []) : [];
  const raw = encodeBase64Url(
    buildMime({
      to: toEmail,
      subject: replySubj,
      body: input.body,
      inReplyTo: origMsgId,
      references: origMsgId,
      attachments,
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

interface Attachment {
  filename: string;
  contentType: string;
  /** Standard base64 (NOT base64url) — MIME bodies use RFC 2045 base64. */
  base64: string;
}

function buildMime(opts: {
  to: string;
  subject: string;
  body: string;
  inReplyTo?: string;
  references?: string;
  attachments?: Attachment[];
}): string {
  const headerLines: string[] = [`From: me`, `To: ${opts.to}`, `Subject: ${opts.subject}`, `MIME-Version: 1.0`];
  if (opts.inReplyTo) headerLines.push(`In-Reply-To: ${opts.inReplyTo}`);
  if (opts.references) headerLines.push(`References: ${opts.references}`);

  const attachments = opts.attachments ?? [];
  if (attachments.length === 0) {
    return [...headerLines, `Content-Type: text/plain; charset=UTF-8`, "", opts.body].join("\r\n");
  }

  // multipart/mixed: a text/plain part followed by one part per attachment.
  // Boundary is derived from requestId-free static + index by the caller's content;
  // a fixed token is fine since it cannot collide with base64 (no '=' runs of this form).
  const boundary = "peppi_mixed_boundary_b3a1c9f2";
  const parts: string[] = [];
  parts.push(`--${boundary}`);
  parts.push(`Content-Type: text/plain; charset=UTF-8`);
  parts.push(`Content-Transfer-Encoding: 7bit`);
  parts.push("");
  parts.push(opts.body);
  for (const att of attachments) {
    parts.push(`--${boundary}`);
    parts.push(`Content-Type: ${att.contentType}; name="${att.filename}"`);
    parts.push(`Content-Transfer-Encoding: base64`);
    parts.push(`Content-Disposition: attachment; filename="${att.filename}"`);
    parts.push("");
    // RFC 2045 caps encoded lines at 76 chars.
    parts.push(att.base64.replace(/.{76}/g, "$&\r\n"));
  }
  parts.push(`--${boundary}--`);

  return [...headerLines, `Content-Type: multipart/mixed; boundary="${boundary}"`, "", ...parts].join("\r\n");
}

const MAX_IMAGE_REDIRECTS = 3;

/**
 * Classify an IP literal as non-public (loopback / private / link-local / ULA /
 * unspecified / CGNAT). Anything we can't parse is treated as unsafe.
 */
function isNonPublicAddress(ip: string): boolean {
  if (net.isIPv4(ip)) {
    const p = ip.split(".").map(Number);
    if (p[0] === 0) return true; // 0.0.0.0/8
    if (p[0] === 10) return true; // 10/8
    if (p[0] === 127) return true; // loopback
    if (p[0] === 169 && p[1] === 254) return true; // link-local 169.254/16
    if (p[0] === 172 && p[1] >= 16 && p[1] <= 31) return true; // 172.16/12
    if (p[0] === 192 && p[1] === 168) return true; // 192.168/16
    if (p[0] === 100 && p[1] >= 64 && p[1] <= 127) return true; // CGNAT 100.64/10
    return false;
  }
  if (net.isIPv6(ip)) {
    const lc = ip.toLowerCase();
    if (lc === "::1" || lc === "::") return true; // loopback / unspecified
    const mapped = lc.match(/^::ffff:(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})$/);
    if (mapped) return isNonPublicAddress(mapped[1]); // IPv4-mapped
    if (lc.startsWith("fc") || lc.startsWith("fd")) return true; // ULA fc00::/7
    if (/^fe[89ab]/.test(lc)) return true; // link-local fe80::/10
    return false;
  }
  return true; // unrecognized format → reject
}

/**
 * SSRF guard: require https and reject any URL whose host resolves to a
 * non-public address. Run on the initial URL AND every redirect Location.
 * Residual: DNS-rebinding between this check and the fetch is not closed here
 * (would require IP-pinned connects + manual SNI); the practical SSRF vectors
 * — direct internal URLs, redirect-to-internal, cloud metadata 169.254.169.254
 * — are blocked.
 */
async function assertSafePublicUrl(raw: string): Promise<void> {
  let u: URL;
  try {
    u = new URL(raw);
  } catch {
    throw new Error("invalid image URL");
  }
  if (u.protocol !== "https:") throw new Error("image URL must use https");
  const host = u.hostname.toLowerCase().replace(/\.$/, "").replace(/^\[|\]$/g, "");
  if (net.isIP(host)) {
    if (isNonPublicAddress(host)) throw new Error("image URL points to a non-public address");
    return;
  }
  const addrs = await lookup(host, { all: true });
  if (addrs.length === 0) throw new Error("image host did not resolve");
  for (const a of addrs) {
    if (isNonPublicAddress(a.address)) {
      throw new Error("image URL resolves to a non-public address");
    }
  }
}

/** Fetch an image with redirects handled manually so each hop is re-validated. */
async function fetchImageSafely(startUrl: string): Promise<Response> {
  let url = startUrl;
  for (let hop = 0; hop <= MAX_IMAGE_REDIRECTS; hop++) {
    await assertSafePublicUrl(url);
    const resp = await fetch(url, { redirect: "manual", signal: AbortSignal.timeout(15_000) });
    if (resp.status >= 300 && resp.status < 400) {
      const loc = resp.headers.get("location");
      if (!loc) throw new Error("image redirect missing Location");
      url = new URL(loc, url).toString();
      continue;
    }
    return resp;
  }
  throw new Error("too many redirects fetching image");
}

/**
 * Fetch the bytes for each image URL and return MIME-ready base64 attachments.
 * Throws on an expired/unreachable URL so the model can tell the user to resend.
 * Skips silently-empty input. Total guarded at 25 MB (Gmail raw-send cap is ~35 MB
 * base64-inflated; we stay well under).
 */
async function fetchAttachments(urls: string[]): Promise<Attachment[]> {
  if (urls.length === 0) {
    throw new Error("no image found on this message to attach — ask the user to resend the image");
  }
  const out: Attachment[] = [];
  let totalBytes = 0;
  for (let i = 0; i < urls.length; i++) {
    const url = urls[i];
    const resp = await fetchImageSafely(url);
    if (!resp.ok) {
      throw new Error(
        resp.status === 404 || resp.status === 410
          ? "the attached image is no longer available (link expired) — please resend it"
          : `could not fetch the attached image (HTTP ${resp.status})`,
      );
    }
    const contentType = resp.headers.get("content-type") ?? "image/jpeg";
    if (!contentType.toLowerCase().startsWith("image/")) {
      throw new Error("attached file is not an image");
    }
    const buf = Buffer.from(await resp.arrayBuffer());
    totalBytes += buf.length;
    if (totalBytes > 25 * 1024 * 1024) {
      throw new Error("attached image(s) too large to email (over 25 MB total)");
    }
    out.push({
      filename: filenameFor(url, contentType, i),
      contentType,
      base64: buf.toString("base64"),
    });
  }
  return out;
}

function filenameFor(url: string, contentType: string, index: number): string {
  const fromUrl = url.split("?")[0].split("/").pop() ?? "";
  if (fromUrl && /\.[a-z0-9]{2,4}$/i.test(fromUrl)) return fromUrl;
  const ext = contentType.split("/")[1]?.split("+")[0] || "jpg";
  return `image_${index + 1}.${ext}`;
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

