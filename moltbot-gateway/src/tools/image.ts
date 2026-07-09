/**
 * image_handle — operational tool for "do something with this image" flows that need
 * the image bytes (NOT pure vision questions like "what's in this picture", which
 * Anthropic's API handles natively when image content blocks are passed in messages).
 *
 * Use cases this serves:
 *   - "send this image to john" → validate URL, then gmail_send with the image attached
 *   - "save this to drive" → similar
 *
 * Twilio image URLs expire ~2 hours after MMS receipt. Always HEAD-validate first;
 * 4xx means expired and the user must resend.
 */

import type Anthropic from "@anthropic-ai/sdk";
import type { ToolContext } from "./index.js";
import { fetchSafely } from "../net/ssrf.js";

export const IMAGE_HANDLE_TOOL: Anthropic.Tool = {
  name: "image_handle",
  description:
    "Validate a Twilio MMS image URL is still accessible and return its content-type and approximate size in KB. Use BEFORE attempting to email or otherwise use the bytes of an attached image — Twilio URLs expire ~2 hours after send. Returns {ok, content_type, kb} on success or {ok: false, reason} on expiry/error.",
  input_schema: {
    type: "object",
    additionalProperties: false,
    required: ["image_url"],
    properties: {
      image_url: {
        type: "string",
        description: "The Twilio MMS image URL from the conversation context.",
      },
    },
  },
};

export async function handle(input: { image_url: string }, _ctx: ToolContext): Promise<{
  ok: boolean;
  content_type?: string;
  kb?: number;
  reason?: string;
}> {
  try {
    // SSRF guard: https-only, reject non-public hosts, re-validate every redirect
    // hop (shared with the Gmail attach path — see net/ssrf.ts).
    const resp = await fetchSafely(input.image_url, { method: "HEAD", timeoutMs: 8_000 });
    if (!resp.ok) {
      return {
        ok: false,
        reason:
          resp.status === 404 || resp.status === 410
            ? "image expired (Twilio URLs expire ~2 hours after send) — please resend the image"
            : `image fetch failed (HTTP ${resp.status})`,
      };
    }
    const contentType = resp.headers.get("content-type") ?? "image/jpeg";
    const lenStr = resp.headers.get("content-length");
    const kb = lenStr ? Math.round(parseInt(lenStr, 10) / 1024) : undefined;
    if (!contentType.startsWith("image/")) {
      return { ok: false, reason: `URL is not an image (content-type: ${contentType})` };
    }
    return { ok: true, content_type: contentType, kb };
  } catch (err) {
    return { ok: false, reason: `image fetch error: ${(err as Error).message}` };
  }
}
