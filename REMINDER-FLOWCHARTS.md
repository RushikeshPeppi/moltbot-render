# Reminder Feature — Mermaid Flowcharts for Excalidraw

> **How to use:** Copy each mermaid code block (without the triple backticks) and paste into
> [Excalidraw Mermaid Tool](https://excalidraw.com) → Click "+" → "Mermaid" → Paste → Done.
>
> **Paste ONE diagram at a time** into Excalidraw for best results.

---

## DIAGRAM 0 — Prerequisite: Peppi Outbound SMS API

```mermaid
flowchart LR
    subgraph CURRENT["TODAY: Request-Response Only"]
        direction LR
        C1["👤 User sends SMS"]
        C2["📱 Peppi receives"]
        C3["🤖 Moltbot processes"]
        C4["💬 Moltbot responds"]
        C5["📱 Peppi delivers reply"]
        C1 -->|"1"| C2 -->|"2"| C3 -->|"3"| C4 -->|"4"| C5
    end

    subgraph NEEDED["NEEDED: Outbound Push"]
        direction LR
        N1["⏰ Reminder triggers"]
        N2["🤖 Moltbot calls Peppi API — POST /api/v1/outbound/send-message"]
        N3["📱 Peppi sends SMS"]
        N4["👤 User gets reminder — No prior SMS needed!"]
        N1 -->|"1"| N2 -->|"2"| N3 -->|"3"| N4
    end

    subgraph BLOCKER["🚫 BLOCKING DEPENDENCY"]
        B1["Peppi Laravel team MUST expose an outbound SMS endpoint. Without it, NO option works."]
    end

    style CURRENT fill:#E2E8F0,stroke:#64748B,color:#334155,stroke-width:2px
    style C1 fill:#94A3B8,stroke:#475569,color:#FFF,stroke-width:2px
    style C2 fill:#94A3B8,stroke:#475569,color:#FFF,stroke-width:2px
    style C3 fill:#94A3B8,stroke:#475569,color:#FFF,stroke-width:2px
    style C4 fill:#94A3B8,stroke:#475569,color:#FFF,stroke-width:2px
    style C5 fill:#94A3B8,stroke:#475569,color:#FFF,stroke-width:2px

    style NEEDED fill:#D1FAE5,stroke:#059669,color:#065F46,stroke-width:2px
    style N1 fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style N2 fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style N3 fill:#3B82F6,stroke:#1E40AF,color:#FFF,stroke-width:2px
    style N4 fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px

    style BLOCKER fill:#FEE2E2,stroke:#DC2626,color:#991B1B,stroke-width:3px
    style B1 fill:#FECACA,stroke:#EF4444,color:#7F1D1D,stroke-width:2px
```

---

## DIAGRAM A — Upstash QStash Flow ⭐ RECOMMENDED

```mermaid
flowchart TD
    subgraph QSTASH_INFO["💡 What is Upstash QStash?"]
        QI["Serverless HTTP message scheduler by Upstash — same vendor as our Redis. You schedule an HTTP request to hit your endpoint at a future time. QStash handles waiting + retrying. ✅ No background workers ✅ Free: 500 msgs/day ✅ Pro: $1/100K msgs ✅ 99.99% SLA ✅ Built-in retry ✅ Native CRON"]
    end

    subgraph P1["📨 PHASE 1 — User Creates Reminder"]
        A["👤 User SMS: Remind me tomorrow at 2pm to buy milk"]
        B["📱 Peppi Platform — Receives SMS"]
        C["🟢 FastAPI — POST /execute-action"]
        D{"🟣 AI Agent — Detects reminder intent"}
    end

    subgraph P2["💾 PHASE 2 — Store + Schedule"]
        E["🔴 Save to Supabase tbl_clawdbot_reminders — user_id: 123, message: Buy milk, trigger_at: 2026-02-18T14:00, status: pending"]
        F["🟠 Call QStash API — POST qstash.upstash.io/v2/publish — Header: Upstash-Not-Before: timestamp — Dest: /api/v1/reminders/deliver"]
        G["⏳ QStash holds message — No process on OUR side — Zero resource cost while waiting"]
        H["✅ Reply to user: Reminder set for tomorrow at 2:00 PM"]
    end

    subgraph P3["🚀 PHASE 3 — Delivery (hours later)"]
        I["🟠 QStash fires at EXACT scheduled time — POST /api/v1/reminders/deliver — Includes crypto signature"]
        J["🔐 Verify QStash signature — Prevents spoofed calls"]
        K["🟢 Fetch reminder from DB — Confirm still pending"]
        L["📱 Call Peppi SMS API — POST /api/send-message — user_id: 123, msg: Buy milk!"]
        M["🔴 Update DB — status = delivered, delivered_at = NOW()"]
        N["📩 User receives SMS: Reminder: Buy milk!"]
    end

    subgraph RETRY["🔄 If Delivery Fails"]
        R1["❌ Peppi API error or timeout"]
        R2["🟠 QStash auto-retries — 3 attempts, exponential backoff — No code needed!"]
        R3["💀 After max retries: status = failed, retry_count = 3"]
    end

    A -->|"1. SMS"| B
    B -->|"2. Forward"| C
    C -->|"3. To agent"| D
    D -->|"4. Intent matched"| E
    E -->|"5. Stored in DB"| F
    F -->|"6. Scheduled"| G
    E -->|"7. Confirm"| H

    G -->|"8. Time reached"| I
    I -->|"9. Webhook"| J
    J -->|"10. Valid"| K
    K -->|"11. Still pending"| L
    L -->|"12. Sent"| M
    M -->|"13. Done"| N

    L -->|"Error"| R1
    R1 --> R2
    R2 -->|"All failed"| R3

    style QSTASH_INFO fill:#FEF9C3,stroke:#EAB308,color:#854D0E,stroke-width:3px
    style QI fill:#FDE68A,stroke:#CA8A04,color:#422006,stroke-width:2px

    style P1 fill:#DBEAFE,stroke:#2563EB,color:#1E40AF,stroke-width:2px
    style A fill:#3B82F6,stroke:#1D4ED8,color:#FFF,stroke-width:2px
    style B fill:#60A5FA,stroke:#2563EB,color:#FFF,stroke-width:2px
    style C fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style D fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px

    style P2 fill:#D1FAE5,stroke:#059669,color:#065F46,stroke-width:2px
    style E fill:#F43F5E,stroke:#BE123C,color:#FFF,stroke-width:2px
    style F fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style G fill:#FDBA74,stroke:#EA580C,color:#7C2D12,stroke-width:2px
    style H fill:#4ADE80,stroke:#16A34A,color:#052E16,stroke-width:2px

    style P3 fill:#F3E8FF,stroke:#7C3AED,color:#5B21B6,stroke-width:2px
    style I fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style J fill:#FACC15,stroke:#CA8A04,color:#422006,stroke-width:2px
    style K fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style L fill:#3B82F6,stroke:#1D4ED8,color:#FFF,stroke-width:2px
    style M fill:#F43F5E,stroke:#BE123C,color:#FFF,stroke-width:2px
    style N fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px

    style RETRY fill:#FEE2E2,stroke:#EF4444,color:#991B1B,stroke-width:2px
    style R1 fill:#EF4444,stroke:#DC2626,color:#FFF,stroke-width:2px
    style R2 fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style R3 fill:#DC2626,stroke:#991B1B,color:#FFF,stroke-width:2px
```

---

## DIAGRAM A2 — QStash Recurring Reminders

```mermaid
flowchart TD
    subgraph CRON_INFO["💡 QStash CRON Schedules"]
        CI["QStash supports CRON expressions natively. Example: 0 9 * * 1 = Every Monday 9am. QStash calls your endpoint automatically on schedule. No background worker needed!"]
    end

    subgraph SETUP["📅 User Sets Recurring Reminder"]
        U["👤 User SMS: Remind me every Monday at 9am to submit report"]
        AG{"🟣 AI Agent — Recurring intent detected"}
    end

    subgraph SCHEDULE["⚙️ Create QStash Schedule"]
        S1["🔴 Save to Supabase — recurrence: weekly, day: monday, hour: 9"]
        S2["🟠 QStash Schedule API — POST /v2/schedules — Upstash-Cron: 0 9 * * 1 — Dest: /api/v1/reminders/deliver"]
        S3["✅ Reply: Weekly reminder set for Mondays at 9am"]
    end

    subgraph WEEKLY["🔁 Every Monday 9am"]
        W1["🟠 QStash fires automatically"]
        W2["🟢 FastAPI receives, verifies + fetches"]
        W3["📱 Peppi sends SMS: Reminder: Submit weekly report!"]
        W4["📩 User gets SMS Every Monday at 9am"]
    end

    subgraph MANAGE["📋 User Management"]
        M1["User: Show my reminders"]
        M2["🟢 FastAPI queries DB — All active reminders"]
        M3["User: Cancel reminder #3"]
        M4["🟠 Delete QStash schedule + 🔴 Update DB: cancelled"]
    end

    U --> AG
    AG --> S1
    S1 --> S2
    S1 --> S3

    S2 -->|"Runs weekly"| W1
    W1 --> W2
    W2 --> W3
    W3 --> W4

    M1 --> M2
    M3 --> M4

    style CRON_INFO fill:#FEF9C3,stroke:#EAB308,color:#854D0E,stroke-width:3px
    style CI fill:#FDE68A,stroke:#CA8A04,color:#422006,stroke-width:2px

    style SETUP fill:#DBEAFE,stroke:#2563EB,color:#1E40AF,stroke-width:2px
    style U fill:#3B82F6,stroke:#1D4ED8,color:#FFF,stroke-width:2px
    style AG fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px

    style SCHEDULE fill:#D1FAE5,stroke:#059669,color:#065F46,stroke-width:2px
    style S1 fill:#F43F5E,stroke:#BE123C,color:#FFF,stroke-width:2px
    style S2 fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style S3 fill:#4ADE80,stroke:#16A34A,color:#052E16,stroke-width:2px

    style WEEKLY fill:#F3E8FF,stroke:#7C3AED,color:#5B21B6,stroke-width:2px
    style W1 fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style W2 fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style W3 fill:#3B82F6,stroke:#1D4ED8,color:#FFF,stroke-width:2px
    style W4 fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px

    style MANAGE fill:#E0E7FF,stroke:#4F46E5,color:#3730A3,stroke-width:2px
    style M1 fill:#818CF8,stroke:#4F46E5,color:#FFF,stroke-width:2px
    style M2 fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style M3 fill:#FB7185,stroke:#E11D48,color:#FFF,stroke-width:2px
    style M4 fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
```

---

## DIAGRAM B — Render Cron + Supabase Polling (Fallback)

```mermaid
flowchart TD
    subgraph CRON_INFO["💡 What is Render Cron Job?"]
        CI["Scheduled task on Render.com — Runs on a timer like Linux crontab. Every 60 seconds, Render spins up a lightweight Python process. It queries DB for due reminders and delivers them. ✅ Simple ✅ No lock-in ✅ Easy SQL debug ⚠️ $7/month ⚠️ 60s delay"]
    end

    subgraph P1["📨 PHASE 1 — User Creates Reminder"]
        A["👤 User SMS: Remind me tomorrow at 2pm to buy milk"]
        B["📱 Peppi Platform"]
        C["🟢 FastAPI — POST /execute-action"]
        D{"🟣 AI Agent — Reminder intent detected"}
    end

    subgraph P2["💾 PHASE 2 — Store Only"]
        E["🔴 INSERT INTO Supabase tbl_clawdbot_reminders — user_id: 123, message: Buy milk, trigger_at: 2026-02-18T14:00, status: pending"]
        F["✅ Reply to user: Reminder set for tomorrow at 2:00 PM"]
        G["💤 Reminder sits in DB — Nothing else happens — No queue, no scheduler"]
    end

    subgraph P3["⏰ PHASE 3 — Every 60s Cron Cycle"]
        H["🟠 Render spins up worker — python -m app.jobs.reminder_worker — Cold start: 5-15 seconds"]
        I["🔍 Query Supabase: SELECT * FROM reminders WHERE status=pending AND trigger_at<=NOW LIMIT 100"]
        J{"Any reminders due?"}
        K["😴 No reminders due — Worker exits — Minimal compute cost"]
    end

    subgraph P4["🚀 PHASE 4 — Deliver Due Reminders"]
        L["🔁 For each due reminder"]
        M["📱 Call Peppi SMS API — POST /api/send-message — user_id: 123, msg: Buy milk!"]
        N["🔴 UPDATE Supabase — status = delivered, delivered_at = NOW()"]
        O{"🔄 Is it recurring?"}
        P["📅 Calculate next trigger_at — INSERT new row — e.g. daily = +1 day"]
        Q["📩 User receives SMS: Reminder: Buy milk!"]
        R["✅ Worker exits — Next cycle in 60s"]
    end

    subgraph FAIL["❌ If Delivery Fails"]
        F1["Peppi API error"]
        F2["INCREMENT retry_count — Will retry next 60s cycle"]
        F3{"retry_count >= 3?"}
        F4["status = failed — Alert ops team"]
    end

    A -->|"1. SMS"| B
    B -->|"2. Forward"| C
    C -->|"3. To agent"| D
    D -->|"4. Intent"| E
    E -->|"5. Stored"| G
    E -->|"6. Confirm"| F

    H -->|"7. Every 60s"| I
    I -->|"8. Check"| J
    J -->|"No rows"| K
    J -->|"Found!"| L
    L -->|"9. Each one"| M
    M -->|"10. Sent"| N
    N -->|"11. Check"| O
    O -->|"Not recurring"| R
    O -->|"Recurring"| P
    P --> R
    M -->|"12. SMS"| Q

    M -->|"Error"| F1
    F1 --> F2
    F2 --> F3
    F3 -->|"No"| R
    F3 -->|"Yes"| F4

    style CRON_INFO fill:#FEF9C3,stroke:#EAB308,color:#854D0E,stroke-width:3px
    style CI fill:#FDE68A,stroke:#CA8A04,color:#422006,stroke-width:2px

    style P1 fill:#DBEAFE,stroke:#2563EB,color:#1E40AF,stroke-width:2px
    style A fill:#3B82F6,stroke:#1D4ED8,color:#FFF,stroke-width:2px
    style B fill:#60A5FA,stroke:#2563EB,color:#FFF,stroke-width:2px
    style C fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style D fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px

    style P2 fill:#D1FAE5,stroke:#059669,color:#065F46,stroke-width:2px
    style E fill:#F43F5E,stroke:#BE123C,color:#FFF,stroke-width:2px
    style F fill:#4ADE80,stroke:#16A34A,color:#052E16,stroke-width:2px
    style G fill:#CBD5E1,stroke:#64748B,color:#1E293B,stroke-width:2px

    style P3 fill:#FFF7ED,stroke:#EA580C,color:#9A3412,stroke-width:2px
    style H fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style I fill:#FB923C,stroke:#EA580C,color:#FFF,stroke-width:2px
    style J fill:#FDBA74,stroke:#EA580C,color:#7C2D12,stroke-width:2px
    style K fill:#CBD5E1,stroke:#64748B,color:#1E293B,stroke-width:2px

    style P4 fill:#F3E8FF,stroke:#7C3AED,color:#5B21B6,stroke-width:2px
    style L fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px
    style M fill:#3B82F6,stroke:#1D4ED8,color:#FFF,stroke-width:2px
    style N fill:#F43F5E,stroke:#BE123C,color:#FFF,stroke-width:2px
    style O fill:#A78BFA,stroke:#7C3AED,color:#FFF,stroke-width:2px
    style P fill:#FACC15,stroke:#CA8A04,color:#422006,stroke-width:2px
    style Q fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px
    style R fill:#4ADE80,stroke:#16A34A,color:#052E16,stroke-width:2px

    style FAIL fill:#FEE2E2,stroke:#EF4444,color:#991B1B,stroke-width:2px
    style F1 fill:#EF4444,stroke:#DC2626,color:#FFF,stroke-width:2px
    style F2 fill:#F87171,stroke:#EF4444,color:#FFF,stroke-width:2px
    style F3 fill:#FB7185,stroke:#E11D48,color:#FFF,stroke-width:2px
    style F4 fill:#DC2626,stroke:#991B1B,color:#FFF,stroke-width:2px
```

---

## DIAGRAM C — APScheduler Background Worker (Not Recommended)

```mermaid
flowchart TD
    subgraph APS_INFO["💡 What is APScheduler?"]
        AI["Advanced Python Scheduler — Mature library for scheduling jobs in-memory. Keeps pending jobs in RAM and fires at exact times. ✅ Exact-second precision ✅ Battle-tested ⚠️ All jobs in RAM ⚠️ Lost on crash/restart"]
    end

    subgraph WARN["⚠️ CRITICAL: Upstash Limitation"]
        WI["Our Upstash Redis is HTTP-based. It does NOT support pub/sub! Worker CANNOT be notified in real-time of new reminders. Must poll DB periodically. ❌ This makes it basically the same as Option B but MORE complex!"]
    end

    subgraph P1["📨 PHASE 1 — User Creates Reminder"]
        A["👤 User SMS: Remind me at 2pm"]
        B["📱 Peppi Platform"]
        C["🟢 FastAPI"]
        D{"🟣 AI Agent"}
    end

    subgraph P2["💾 PHASE 2 — Store + Notify Problem"]
        E["🔴 Save to Supabase"]
        F{"How to notify worker?"}
        G["❌ Redis pub/sub NOT available! Upstash HTTP limitation"]
        H["😕 Must poll DB instead — Same as Option B"]
        I["✅ Reply to user"]
    end

    subgraph P3["🔧 PHASE 3 — Always-On Worker"]
        J["🟠 Worker starts on deploy — Always running: $7+/month — Loads APScheduler"]
        K["📥 On startup: Load ALL pending reminders from Supabase into memory"]
        L["🔄 Every 30s: Poll DB for new reminders — Add to APScheduler"]
        M["🧠 All jobs in RAM — 1K reminders = OK — 100K = high memory!"]
    end

    subgraph P4["🚀 PHASE 4 — Delivery"]
        N["⚡ APScheduler fires at exact second"]
        O["📱 Call Peppi SMS API"]
        P["🔴 Update DB: delivered"]
        Q{"🔄 Recurring?"}
        R["📅 Re-schedule in APScheduler"]
        S["📩 User gets SMS"]
    end

    subgraph RISKS["💀 Risks"]
        X1["🔥 Worker crash/redeploy: ALL in-memory jobs LOST — Must reload from DB — 10-30s gap"]
        X2["💾 High RAM at scale — No horizontal scaling without distributed locks"]
    end

    A -->|"1"| B -->|"2"| C -->|"3"| D
    D -->|"4"| E
    E -->|"5"| F
    F -->|"Ideal"| G
    G -->|"Fallback"| H
    E -->|"6"| I

    J -->|"7. Boot"| K
    K -->|"8. Loop"| L
    L -->|"9. New found"| M

    M -->|"10. Timer"| N
    N -->|"11"| O
    O -->|"12"| P
    P -->|"13"| Q
    Q -->|"Yes"| R
    Q -->|"No"| S
    R --> S

    J -->|"Crash?"| X1

    style APS_INFO fill:#FEF9C3,stroke:#EAB308,color:#854D0E,stroke-width:3px
    style AI fill:#FDE68A,stroke:#CA8A04,color:#422006,stroke-width:2px

    style WARN fill:#FEE2E2,stroke:#EF4444,color:#991B1B,stroke-width:3px
    style WI fill:#FECACA,stroke:#EF4444,color:#7F1D1D,stroke-width:2px

    style P1 fill:#DBEAFE,stroke:#2563EB,color:#1E40AF,stroke-width:2px
    style A fill:#3B82F6,stroke:#1D4ED8,color:#FFF,stroke-width:2px
    style B fill:#60A5FA,stroke:#2563EB,color:#FFF,stroke-width:2px
    style C fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style D fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px

    style P2 fill:#D1FAE5,stroke:#059669,color:#065F46,stroke-width:2px
    style E fill:#F43F5E,stroke:#BE123C,color:#FFF,stroke-width:2px
    style F fill:#FACC15,stroke:#CA8A04,color:#422006,stroke-width:2px
    style G fill:#EF4444,stroke:#DC2626,color:#FFF,stroke-width:2px
    style H fill:#CBD5E1,stroke:#64748B,color:#1E293B,stroke-width:2px
    style I fill:#4ADE80,stroke:#16A34A,color:#052E16,stroke-width:2px

    style P3 fill:#FFF7ED,stroke:#EA580C,color:#9A3412,stroke-width:2px
    style J fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style K fill:#FB923C,stroke:#EA580C,color:#FFF,stroke-width:2px
    style L fill:#FDBA74,stroke:#EA580C,color:#7C2D12,stroke-width:2px
    style M fill:#FDE047,stroke:#EAB308,color:#422006,stroke-width:2px

    style P4 fill:#F3E8FF,stroke:#7C3AED,color:#5B21B6,stroke-width:2px
    style N fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px
    style O fill:#3B82F6,stroke:#1D4ED8,color:#FFF,stroke-width:2px
    style P fill:#F43F5E,stroke:#BE123C,color:#FFF,stroke-width:2px
    style Q fill:#A78BFA,stroke:#7C3AED,color:#FFF,stroke-width:2px
    style R fill:#FACC15,stroke:#CA8A04,color:#422006,stroke-width:2px
    style S fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px

    style RISKS fill:#FEE2E2,stroke:#EF4444,color:#991B1B,stroke-width:2px
    style X1 fill:#EF4444,stroke:#DC2626,color:#FFF,stroke-width:2px
    style X2 fill:#F43F5E,stroke:#BE123C,color:#FFF,stroke-width:2px
```

---

## DIAGRAM D — Google Calendar Webhooks (Not Recommended)

```mermaid
flowchart TD
    subgraph GCAL_INFO["💡 Google Calendar Push Notifications"]
        GI["Watch a calendar for changes. When event starts, Google POSTs to your endpoint. ⚠️ Best-effort delivery ⚠️ NO guaranteed timing ⚠️ Watches expire 7-30 days ⚠️ Must renew per user ⚠️ Requires domain verification"]
    end

    subgraph RISK["🚫 Why This Is Risky"]
        RI["A reminder system's value is delivering ON TIME. Google says notifications have NO delivery guarantee. Late or missing reminders = users lose trust. Only works for Google users. Clutters their calendar."]
    end

    subgraph P1["📨 PHASE 1 — User Creates Reminder"]
        A["👤 User SMS: Remind me at 2pm to buy milk"]
        B["📱 Peppi Platform"]
        C["🟢 FastAPI"]
        D{"🟣 AI Agent — Reminder intent"}
    end

    subgraph P2["📅 PHASE 2 — Calendar Event + Watch"]
        E["🔵 Create Google Calendar Event — POST /calendars/primary/events — summary: REMINDER: Buy milk — start: 2026-02-18T14:00"]
        F["🟠 Register Watch on calendar — POST /events/watch — type: web_hook — address: /api/v1/webhooks/calendar"]
        G["⏰ Watch expires in 7-30 days — Must renew for EVERY user — N users = N watch channels"]
        H["✅ Reply: Reminder set"]
    end

    subgraph P3["📡 PHASE 3 — Google Notifies (Maybe)"]
        I["🔵 Google sends push — POST /webhooks/calendar — Timing: seconds to MINUTES — Delivery: NOT guaranteed"]
        J["🟢 FastAPI receives: Which user? What changed? Must query Google again"]
        K["🔍 GET /events — Find what changed — Filter: REMINDER: prefix"]
        L{"Is it a reminder?"}
        M["📋 Regular event — Ignore"]
    end

    subgraph P4["🚀 PHASE 4 — Deliver"]
        N["📱 Call Peppi SMS API"]
        O["📩 User gets SMS — Maybe on time, maybe minutes late, maybe NOT AT ALL"]
    end

    subgraph PROBLEMS["❌ Additional Problems"]
        P1X["📅 Calendar clutter"]
        P2X["🔒 Privacy: reminders visible to others"]
        P3X["🚫 No Google account = No reminders"]
        P4X["✅ Domain verification required by Google"]
    end

    A -->|"1"| B -->|"2"| C -->|"3"| D
    D -->|"4"| E
    E -->|"5. Event created"| F
    F -->|"6. Watch active"| G
    E -->|"7"| H

    G -->|"8. Event time"| I
    I -->|"9. Webhook"| J
    J -->|"10. Query"| K
    K -->|"11. Check"| L
    L -->|"Not reminder"| M
    L -->|"REMINDER: prefix"| N
    N -->|"12. SMS"| O

    style GCAL_INFO fill:#FEF9C3,stroke:#EAB308,color:#854D0E,stroke-width:3px
    style GI fill:#FDE68A,stroke:#CA8A04,color:#422006,stroke-width:2px

    style RISK fill:#FEE2E2,stroke:#EF4444,color:#991B1B,stroke-width:3px
    style RI fill:#FECACA,stroke:#EF4444,color:#7F1D1D,stroke-width:2px

    style P1 fill:#DBEAFE,stroke:#2563EB,color:#1E40AF,stroke-width:2px
    style A fill:#3B82F6,stroke:#1D4ED8,color:#FFF,stroke-width:2px
    style B fill:#60A5FA,stroke:#2563EB,color:#FFF,stroke-width:2px
    style C fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style D fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px

    style P2 fill:#D1FAE5,stroke:#059669,color:#065F46,stroke-width:2px
    style E fill:#14B8A6,stroke:#0D9488,color:#FFF,stroke-width:2px
    style F fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style G fill:#FDBA74,stroke:#EA580C,color:#7C2D12,stroke-width:2px
    style H fill:#4ADE80,stroke:#16A34A,color:#052E16,stroke-width:2px

    style P3 fill:#FFF7ED,stroke:#EA580C,color:#9A3412,stroke-width:2px
    style I fill:#14B8A6,stroke:#0D9488,color:#FFF,stroke-width:2px
    style J fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style K fill:#FB923C,stroke:#EA580C,color:#FFF,stroke-width:2px
    style L fill:#A78BFA,stroke:#7C3AED,color:#FFF,stroke-width:2px
    style M fill:#CBD5E1,stroke:#64748B,color:#1E293B,stroke-width:2px

    style P4 fill:#F3E8FF,stroke:#7C3AED,color:#5B21B6,stroke-width:2px
    style N fill:#3B82F6,stroke:#1D4ED8,color:#FFF,stroke-width:2px
    style O fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px

    style PROBLEMS fill:#FEE2E2,stroke:#EF4444,color:#991B1B,stroke-width:2px
    style P1X fill:#EF4444,stroke:#DC2626,color:#FFF,stroke-width:2px
    style P2X fill:#EF4444,stroke:#DC2626,color:#FFF,stroke-width:2px
    style P3X fill:#EF4444,stroke:#DC2626,color:#FFF,stroke-width:2px
    style P4X fill:#EF4444,stroke:#DC2626,color:#FFF,stroke-width:2px
```

---

## DIAGRAM E — Side-by-Side Comparison

```mermaid
flowchart LR
    subgraph A["⭐ OPTION A: QStash"]
        A1["Precision: EXACT time"]
        A2["Cost: $0-5/month"]
        A3["Complexity: LOW"]
        A4["Infra: NONE new"]
        A5["Verdict: RECOMMENDED"]
    end

    subgraph B["🔄 OPTION B: Cron"]
        B1["Precision: Within 60s"]
        B2["Cost: $7/month"]
        B3["Complexity: LOW-MED"]
        B4["Infra: 1 cron job"]
        B5["Verdict: FALLBACK"]
    end

    subgraph C["⚙️ OPTION C: APScheduler"]
        C1["Precision: EXACT time"]
        C2["Cost: $7-21/month"]
        C3["Complexity: MED-HIGH"]
        C4["Infra: 1 worker"]
        C5["Verdict: NOT RECOMMENDED"]
    end

    subgraph D["📅 OPTION D: Calendar"]
        D1["Precision: UNRELIABLE"]
        D2["Cost: $0/month"]
        D3["Complexity: MEDIUM"]
        D4["Infra: NONE new"]
        D5["Verdict: NOT RECOMMENDED"]
    end

    style A fill:#D1FAE5,stroke:#059669,color:#065F46,stroke-width:3px
    style A1 fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style A2 fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style A3 fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style A4 fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style A5 fill:#059669,stroke:#047857,color:#FFF,stroke-width:3px

    style B fill:#DBEAFE,stroke:#2563EB,color:#1E40AF,stroke-width:3px
    style B1 fill:#3B82F6,stroke:#1D4ED8,color:#FFF,stroke-width:2px
    style B2 fill:#3B82F6,stroke:#1D4ED8,color:#FFF,stroke-width:2px
    style B3 fill:#3B82F6,stroke:#1D4ED8,color:#FFF,stroke-width:2px
    style B4 fill:#3B82F6,stroke:#1D4ED8,color:#FFF,stroke-width:2px
    style B5 fill:#2563EB,stroke:#1D4ED8,color:#FFF,stroke-width:3px

    style C fill:#FFF7ED,stroke:#EA580C,color:#9A3412,stroke-width:3px
    style C1 fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style C2 fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style C3 fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style C4 fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style C5 fill:#EA580C,stroke:#C2410C,color:#FFF,stroke-width:3px

    style D fill:#FEE2E2,stroke:#EF4444,color:#991B1B,stroke-width:3px
    style D1 fill:#EF4444,stroke:#DC2626,color:#FFF,stroke-width:2px
    style D2 fill:#EF4444,stroke:#DC2626,color:#FFF,stroke-width:2px
    style D3 fill:#EF4444,stroke:#DC2626,color:#FFF,stroke-width:2px
    style D4 fill:#EF4444,stroke:#DC2626,color:#FFF,stroke-width:2px
    style D5 fill:#DC2626,stroke:#991B1B,color:#FFF,stroke-width:3px
```

---

## DIAGRAM F — Implementation Phases Timeline

```mermaid
flowchart LR
    subgraph W1["📦 Week 1: Foundation"]
        W1A["Create reminders table in Supabase"]
        W1B["Add CRUD endpoints in FastAPI"]
        W1C["Confirm Peppi outbound API"]
        W1D["Update AI agent reminder intent skill"]
    end

    subgraph W2["⚙️ Week 2: Scheduling"]
        W2A["Integrate chosen scheduling engine"]
        W2B["Build delivery endpoint"]
        W2C["Implement retry logic"]
        W2D["Timezone conversion: user local to UTC"]
    end

    subgraph W3["🔁 Week 3: Recurring"]
        W3A["Add recurrence: daily/weekly/monthly"]
        W3B["Next occurrence calculation"]
        W3C["User commands: show/cancel reminders"]
        W3D["Edge cases: DST transitions"]
    end

    subgraph W4["🔍 Week 4: Polish"]
        W4A["Delivery tracking in audit log"]
        W4B["Reminder management: list/cancel all"]
        W4C["Failure alerts: Slack/email to ops"]
        W4D["Load testing multi-tenant"]
    end

    W1 --> W2 --> W3 --> W4

    style W1 fill:#DBEAFE,stroke:#2563EB,color:#1E40AF,stroke-width:3px
    style W1A fill:#3B82F6,stroke:#1D4ED8,color:#FFF,stroke-width:2px
    style W1B fill:#60A5FA,stroke:#2563EB,color:#FFF,stroke-width:2px
    style W1C fill:#93C5FD,stroke:#3B82F6,color:#1E3A5F,stroke-width:2px
    style W1D fill:#BFDBFE,stroke:#60A5FA,color:#1E3A5F,stroke-width:2px

    style W2 fill:#D1FAE5,stroke:#059669,color:#065F46,stroke-width:3px
    style W2A fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style W2B fill:#34D399,stroke:#059669,color:#FFF,stroke-width:2px
    style W2C fill:#6EE7B7,stroke:#10B981,color:#064E3B,stroke-width:2px
    style W2D fill:#A7F3D0,stroke:#34D399,color:#064E3B,stroke-width:2px

    style W3 fill:#F3E8FF,stroke:#7C3AED,color:#5B21B6,stroke-width:3px
    style W3A fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px
    style W3B fill:#A78BFA,stroke:#7C3AED,color:#FFF,stroke-width:2px
    style W3C fill:#C4B5FD,stroke:#8B5CF6,color:#3B0764,stroke-width:2px
    style W3D fill:#DDD6FE,stroke:#A78BFA,color:#3B0764,stroke-width:2px

    style W4 fill:#FFF7ED,stroke:#EA580C,color:#9A3412,stroke-width:3px
    style W4A fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style W4B fill:#FB923C,stroke:#EA580C,color:#FFF,stroke-width:2px
    style W4C fill:#FDBA74,stroke:#F97316,color:#7C2D12,stroke-width:2px
    style W4D fill:#FED7AA,stroke:#FB923C,color:#7C2D12,stroke-width:2px
```

---

## DIAGRAM G — Data Model Overview

```mermaid
flowchart TD
    subgraph TABLE["📊 tbl_clawdbot_reminders"]
        T1["id: BIGSERIAL PK"]
        T2["user_id: INTEGER — owner"]
        T3["message: TEXT — what to remind"]
        T4["trigger_at: TIMESTAMPTZ — when, stored UTC"]
        T5["user_timezone: VARCHAR — original TZ"]
        T6["recurrence: VARCHAR — none/daily/weekly"]
        T7["recurrence_rule: JSONB — complex patterns"]
        T8["status: VARCHAR — pending/delivered/failed"]
        T9["delivered_at: TIMESTAMPTZ"]
        T10["retry_count: INTEGER — attempts"]
        T11["max_retries: INTEGER — default 3"]
    end

    subgraph INDEXES["🔍 Key Indexes"]
        I1["status + trigger_at — Find pending reminders due NOW"]
        I2["user_id + status — Show MY active reminders"]
        I3["trigger_at — Time-based range scans"]
    end

    subgraph LIFECYCLE["🔄 Reminder Lifecycle"]
        L1["⬜ PENDING — Waiting to fire"]
        L2["✅ DELIVERED — SMS sent successfully"]
        L3["❌ FAILED — All retries exhausted"]
        L4["🚫 CANCELLED — User cancelled"]
    end

    L1 -->|"Delivered OK"| L2
    L1 -->|"Max retries hit"| L3
    L1 -->|"User cancels"| L4

    TABLE --- INDEXES
    TABLE --- LIFECYCLE

    style TABLE fill:#DBEAFE,stroke:#2563EB,color:#1E40AF,stroke-width:3px
    style T1 fill:#3B82F6,stroke:#1D4ED8,color:#FFF,stroke-width:2px
    style T2 fill:#3B82F6,stroke:#1D4ED8,color:#FFF,stroke-width:2px
    style T3 fill:#3B82F6,stroke:#1D4ED8,color:#FFF,stroke-width:2px
    style T4 fill:#60A5FA,stroke:#2563EB,color:#FFF,stroke-width:2px
    style T5 fill:#60A5FA,stroke:#2563EB,color:#FFF,stroke-width:2px
    style T6 fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px
    style T7 fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px
    style T8 fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style T9 fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style T10 fill:#EF4444,stroke:#DC2626,color:#FFF,stroke-width:2px
    style T11 fill:#EF4444,stroke:#DC2626,color:#FFF,stroke-width:2px

    style INDEXES fill:#FEF9C3,stroke:#EAB308,color:#854D0E,stroke-width:3px
    style I1 fill:#FACC15,stroke:#CA8A04,color:#422006,stroke-width:2px
    style I2 fill:#FDE047,stroke:#EAB308,color:#422006,stroke-width:2px
    style I3 fill:#FEF08A,stroke:#FACC15,color:#422006,stroke-width:2px

    style LIFECYCLE fill:#F3E8FF,stroke:#7C3AED,color:#5B21B6,stroke-width:3px
    style L1 fill:#CBD5E1,stroke:#64748B,color:#1E293B,stroke-width:2px
    style L2 fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style L3 fill:#EF4444,stroke:#DC2626,color:#FFF,stroke-width:2px
    style L4 fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
```
