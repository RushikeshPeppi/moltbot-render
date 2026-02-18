# Daemon Mode vs Local Mode — Architecture Evaluation

## Technical Analysis for Moltbot's OpenClaw Execution Strategy

---

## Overview

This document evaluates both execution modes offered by OpenClaw — daemon (persistent process) and local (per-request process) — in the context of Moltbot's multi-tenant architecture. Both modes are valid engineering choices; however, they serve fundamentally different use cases. This analysis outlines why `--local` mode is the appropriate fit for our specific requirements.

---

## How Each Mode Works

| Aspect | Daemon Mode | Local Mode |
|--------|-------------|------------|
| Process lifecycle | Long-running background process | Short-lived process per request |
| Intended use case | Single developer, personal agent | API-driven, stateless execution |
| Session context | One user's context in memory | Isolated per-user session keys |
| Memory model | Shared across all incoming requests | Fresh allocation per request |
| Failure blast radius | All users affected simultaneously | Only the requesting user affected |
| Dashboard | Included (single-user admin panel) | Not included (API-only interface) |
| Cron/Reminders | Included (for the process owner) | Not included (handled externally) |

---

## Evaluation Against Our Requirements

### 1. User Isolation

Moltbot serves multiple users, each with their own Google OAuth credentials. Daemon mode operates as a single process with a single set of environment variables. When two users make requests close together, environment variables like `GOOGLE_ACCESS_TOKEN` can overlap:

- User A's request sets `GOOGLE_ACCESS_TOKEN=token_A`
- User B's request arrives shortly after, overwriting it with `GOOGLE_ACCESS_TOKEN=token_B`
- User A's in-progress request now operates with User B's credentials

This is a known characteristic of single-process architectures, not a flaw in the daemon itself. Daemon mode was simply designed for a different scenario — one user, one token, one machine.

With `--local` mode, each request runs in its own process with its own environment. Credentials never coexist in the same memory space.

### 2. Fault Tolerance

A daemon is a single long-running process. If it encounters an unhandled error, memory leak, or framework-level issue, all users lose service until the process restarts.

During our initial testing with daemon mode, we observed "gateway closed" errors under concurrent load (detailed in the Timeline section below). Recovery required a full restart — approximately 10–15 seconds during which no requests could be served.

With `--local` mode, a failure in one request has no effect on any other request. The next incoming request simply spawns a fresh, healthy process. This pattern is widely used in production systems specifically because it limits the blast radius of failures.

### 3. Concurrent Request Handling

The daemon processes requests sequentially. When one user's request takes 20–30 seconds (common for AI-generated responses), subsequent users queue behind it.

At our expected scale, this sequential processing creates a bottleneck. Running multiple daemon instances to work around this is not straightforward — OpenClaw's daemon shares config directories, session files, and skill installations at `/root/.openclaw`, which introduces contention between instances.

With `--local` mode, Node.js spawns processes concurrently. Ten simultaneous users result in ten parallel processes, each completing independently without blocking the others.

### 4. Dashboard Applicability

The daemon dashboard is a well-designed admin panel — for a single user managing their own agent. It surfaces one agent's configuration, one conversation history, and one set of skills.

For Moltbot, we need visibility into per-user conversations, per-user OAuth connections, per-user session state, and multi-tenant audit trails. These requirements fall outside the dashboard's design scope. We would need to build the same multi-tenant admin tooling regardless of which execution mode we use, so the dashboard does not reduce our development surface.

### 5. Cron & Reminder Applicability

The daemon's built-in cron and reminder features schedule tasks for the daemon's owner — a single user. They have no concept of per-user scheduling, per-user timezone handling, or per-user delivery channels.

Our reminder use case requires:
- Scheduling reminders for individual users across different timezones
- Storing reminders per user in a persistent database
- Delivering reminders via SMS through the Peppi platform

Even if we used daemon mode, we would still need to build the entire multi-tenant scheduling and delivery pipeline ourselves. The built-in cron feature and our requirements simply address different problems.

### 6. Resource Efficiency

A daemon consumes memory and CPU continuously, even during periods of zero traffic. On our Render Pro plan, this represents an ongoing cost for idle capacity.

With `--local` mode, compute resources are consumed only when users are actively making requests. The base Express server is lightweight, and processes spin up and down with demand. This aligns well with our current traffic patterns, which have significant idle periods.

---

## How We Address What Local Mode Doesn't Include

| Requirement | Our Implementation |
|-------------|-------------------|
| Multi-user OAuth tokens | FastAPI Credential Manager — encrypted per-user tokens in Supabase, fresh token fetched per request |
| User isolation | Per-request process spawning — each user gets an isolated OpenClaw process with their own environment variables |
| Session management | Upstash Redis — per-user sessions with `session:{user_id}:{session_id}` keys, auto-expiring TTL |
| Concurrent users | Node.js concurrent child processes — parallel execution with no shared queue |
| Crash recovery | Process-per-request model — next request gets a fresh process, no manual restart needed |
| Audit trail | Supabase audit log — every action logged with user_id, action_type, status, tokens_used |
| Rate limiting | Redis per-user daily counters — 50/day free tier, 500/day premium |
| Skill management | Custom `google-workspace` skill installed at build time, consistent across all requests |

---

## Timeline: How We Arrived at This Decision

This was not a theoretical choice. We initially deployed with daemon mode and evaluated it under real conditions:

1. Deployed OpenClaw in daemon mode on Render
2. Initial requests worked as expected
3. Under concurrent load (5+ simultaneous users), the daemon began returning "gateway closed" errors
4. The daemon would lose its WebSocket connection to the Express server
5. Recovery required a full process restart — 10–15 seconds of downtime affecting all users
6. We introduced retry logic, but the daemon would sometimes enter a degraded state producing inconsistent responses

After several days of investigation and attempted workarounds, we migrated to `--local` mode. The results since switching:

- Zero "gateway closed" errors
- Complete request isolation
- Consistent performance under concurrent load
- Simplified error handling — failed processes don't affect the system

---

## Summary

Both daemon mode and local mode are legitimate approaches for their intended use cases. Daemon mode is well-suited for a single developer running a personal agent on their own machine — and it excels at that. Local mode is better suited for API-driven, multi-tenant platforms where user isolation, fault tolerance, and concurrency are requirements.

For Moltbot, `--local` mode provides:

- **Stronger security** — per-user process isolation prevents credential overlap
- **Better reliability** — no single point of failure, no cascading impact from errors
- **Native concurrency** — parallel request processing without architectural workarounds
- **Full observability** — every request logged independently with per-user attribution
- **Production-grade multi-tenancy** — designed around the reality of serving many users simultaneously

The daemon's dashboard and cron features are valuable in a single-user context, but they don't address our multi-tenant requirements. For features like scheduled reminders, we have a clear path forward using purpose-built tools (Upstash QStash or Render Cron Jobs) that integrate naturally with our existing architecture.

---

*Prepared for internal review — February 2026*
