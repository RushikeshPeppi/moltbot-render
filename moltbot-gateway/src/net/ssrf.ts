/**
 * SSRF guard — shared by every server-side fetch of a caller/model-influenced URL
 * (the Gmail image-attach path in tools/gmail.ts and image_handle in tools/image.ts).
 *
 * Both fetch a URL that originates outside our trust boundary, so both MUST refuse
 * URLs whose host resolves to a non-public address (cloud metadata 169.254.169.254,
 * loopback, RFC1918, CGNAT, ULA, link-local) and re-validate EVERY redirect hop —
 * a public URL that 302s to an internal one is the classic bypass.
 *
 * Residual: DNS-rebinding between the validation lookup and the actual fetch is not
 * closed here (would require IP-pinned connects + manual SNI); the practical vectors
 * — direct internal URL, redirect-to-internal, cloud metadata — are all blocked.
 */

import { lookup } from "node:dns/promises";
import net from "node:net";

const MAX_REDIRECTS = 3;

/**
 * Classify an IP literal as non-public (loopback / private / link-local / ULA /
 * unspecified / CGNAT). Anything we can't parse is treated as unsafe.
 */
export function isNonPublicAddress(ip: string): boolean {
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
    if (lc.startsWith("fc") || lc.startsWith("fd")) return true; // ULA fc00::/7
    if (/^fe[89ab]/.test(lc)) return true; // link-local fe80::/10
    // Any IPv6 that EMBEDS an IPv4 (mapped ::ffff:0:0/96, IPv4-compatible ::/96,
    // NAT64 64:ff9b::/96, 6to4 2002::/16) must be classified by that inner IPv4.
    // Critical: new URL() normalizes ::ffff:127.0.0.1 to the hex ::ffff:7f00:1, so
    // a dotted-decimal-only match is an SSRF bypass to loopback/metadata/RFC1918.
    // Unparseable IPv6 → treat as unsafe.
    const bytes = ipv6ToBytes(ip);
    if (!bytes) return true;
    const inner = embeddedIPv4(bytes);
    if (inner) return isNonPublicAddress(inner);
    return false; // genuine global-unicast IPv6
  }
  return true; // unrecognized format → reject
}

/** Expand an IPv6 literal to its 16 bytes, or null if unparseable / scoped. */
function ipv6ToBytes(ip: string): number[] | null {
  let s = ip.toLowerCase();
  if (s.includes("%")) return null; // scoped (zone id) — not a routable public host
  // Convert a trailing dotted-IPv4 tail (e.g. ::ffff:1.2.3.4) to two hextets.
  const tail = s.match(/(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})$/);
  if (tail) {
    const q = tail[1].split(".").map(Number);
    if (q.some((n) => n > 255)) return null;
    const hx = `${((q[0] << 8) | q[1]).toString(16)}:${((q[2] << 8) | q[3]).toString(16)}`;
    s = s.slice(0, s.length - tail[1].length) + hx;
  }
  const halves = s.split("::");
  if (halves.length > 2) return null;
  const head = halves[0] ? halves[0].split(":") : [];
  const tailGroups = halves.length === 2 ? (halves[1] ? halves[1].split(":") : []) : null;
  let groups: string[];
  if (tailGroups === null) {
    groups = head;
  } else {
    const missing = 8 - head.length - tailGroups.length;
    if (missing < 1) return null;
    groups = [...head, ...Array(missing).fill("0"), ...tailGroups];
  }
  if (groups.length !== 8) return null;
  const bytes: number[] = [];
  for (const g of groups) {
    if (!/^[0-9a-f]{1,4}$/.test(g)) return null;
    const v = parseInt(g, 16);
    bytes.push((v >> 8) & 0xff, v & 0xff);
  }
  return bytes;
}

/** If the 16-byte IPv6 embeds an IPv4 (mapped / compatible / NAT64 / 6to4),
 *  return it dotted; else null. */
function embeddedIPv4(b: number[]): string | null {
  const v4 = (i: number) => `${b[i]}.${b[i + 1]}.${b[i + 2]}.${b[i + 3]}`;
  const zero = (lo: number, hi: number) => b.slice(lo, hi).every((x) => x === 0);
  if (zero(0, 10) && b[10] === 0xff && b[11] === 0xff) return v4(12); // ::ffff:0:0/96 mapped
  if (b[0] === 0x00 && b[1] === 0x64 && b[2] === 0xff && b[3] === 0x9b && zero(4, 12)) return v4(12); // 64:ff9b::/96 NAT64
  if (zero(0, 12) && !zero(12, 16)) return v4(12); // ::/96 IPv4-compatible (:: and ::1 handled above)
  if (b[0] === 0x20 && b[1] === 0x02) return v4(2); // 2002::/16 6to4
  return null;
}

/**
 * SSRF guard: require https and reject any URL whose host resolves to a
 * non-public address. Run on the initial URL AND every redirect Location.
 */
export async function assertSafePublicUrl(raw: string): Promise<void> {
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

/**
 * Fetch a URL with redirects handled manually so each hop is re-validated through
 * assertSafePublicUrl. Works for GET (attachment fetch) and HEAD (image_handle probe).
 */
export async function fetchSafely(
  startUrl: string,
  opts?: { method?: string; timeoutMs?: number },
): Promise<Response> {
  const method = opts?.method ?? "GET";
  const timeoutMs = opts?.timeoutMs ?? 15_000;
  let url = startUrl;
  for (let hop = 0; hop <= MAX_REDIRECTS; hop++) {
    await assertSafePublicUrl(url);
    const resp = await fetch(url, { method, redirect: "manual", signal: AbortSignal.timeout(timeoutMs) });
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
