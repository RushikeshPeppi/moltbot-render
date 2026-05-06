/**
 * Structured per-call logging. Single JSON line per /execute completion — easy to grep
 * and `jq` on Render's log viewer.
 *
 * Metrics to watch:
 *   - p50 / p95 wall time (`ms`)
 *   - cache hit ratio (`hit`) — should be >0.85 on warm calls
 *   - iterations per call (`iter`) — target avg <2.5
 *   - tool error rate — `tools[].ok = false` ratio
 *   - cost per call (compute downstream from cr/cw5/cw1h/in/out — Sonnet 4.6 pricing)
 */

export interface CallMeta {
  sessionId: string;
  userId: string;
  iterations: number;
  elapsedMs: number;
  usage: {
    input: number;
    output: number;
    cacheRead: number;
    cacheWrite5m: number;
    cacheWrite1h: number;
  };
  actionType: string;
  toolCalls: Array<{ name: string; durationMs: number; ok: boolean }>;
  requestId: string;
  /** Anthropic-side request id (`_request_id` on the SDK response, last iteration). Useful for support tickets. */
  anthropicRequestId?: string | null;
}

export function logCall(c: CallMeta): void {
  // Cache hit ratio: fraction of total *input* tokens that came from cache.
  // Total input = input (uncached) + cache_creation_5m + cache_creation_1h + cache_read
  // (Anthropic docs explicitly note these three counters do not overlap.)
  const totalInput = c.usage.input + c.usage.cacheRead + c.usage.cacheWrite5m + c.usage.cacheWrite1h;
  const hit = totalInput > 0 ? c.usage.cacheRead / totalInput : 0;
  console.log(
    JSON.stringify({
      ts: new Date().toISOString(),
      evt: "agent_call",
      session: c.sessionId,
      user: c.userId,
      req: c.requestId,
      anth_req: c.anthropicRequestId ?? null,
      iter: c.iterations,
      ms: Math.round(c.elapsedMs),
      action: c.actionType,
      in: c.usage.input,
      out: c.usage.output,
      cr: c.usage.cacheRead,
      cw5: c.usage.cacheWrite5m,
      cw1h: c.usage.cacheWrite1h,
      hit: Number(hit.toFixed(2)),
      tools: c.toolCalls.map((t) => ({
        n: t.name,
        ms: Math.round(t.durationMs),
        ok: t.ok,
      })),
    }),
  );
}

export function logError(reqId: string, msg: string, err: unknown): void {
  console.error(
    JSON.stringify({
      ts: new Date().toISOString(),
      evt: "error",
      req: reqId,
      msg,
      err: err instanceof Error ? { name: err.name, message: err.message } : String(err),
    }),
  );
}
