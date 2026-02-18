# Moltbot Architecture Diagrams (Mermaid)

> Paste each mermaid code block individually into Excalidraw's Mermaid import feature.

---

## 1. BASE ARCHITECTURE OVERVIEW — Full System Map

```mermaid
flowchart TB
    subgraph USER_LAYER["USER LAYER"]
        USER["User via SMS"]
        PEPPI["Peppi Platform\nLaravel Backend"]
    end

    subgraph FASTAPI["FASTAPI WRAPPER — Python — :8000"]
        direction TB
        ROUTES["/execute-action\n/session | /credentials | /history"]
        OAUTH["/oauth/google\ninit | callback | token | status"]
        SESSION["Session Manager\nRedis sessions, TTL 1hr"]
        CRED["Credential Manager\nFernet AES-128 encryption"]
        MIDDLEWARE["Rate Limiter + User Lock\nAudit Logger"]
    end

    subgraph GATEWAY["OPENCLAW GATEWAY — Node.js — :18789"]
        direction TB
        SERVER["/execute | /health | /skills"]
        TOKEN_BRIDGE["OAuth Token Bridge\nFetches fresh token per request"]
        CONTEXT["Context Builder\nIdentity + Timezone + Capabilities"]
        CLI["OpenClaw CLI\nGemini 2.5 Flash | per-user session"]
    end

    subgraph AGENT["AI AGENT — Gemini 2.5 Flash"]
        direction TB
        INTENT{"Intent\nTask or Chat?"}
        SKILL["Skill Executor\nReads SKILL.md\nRuns curl + jq via Bash"]
    end

    subgraph SKILLS_FILE["SKILL.MD — google-workspace"]
        direction LR
        CAL["Calendar\nList | Create | Update | Delete"]
        MAIL["Gmail\nSend | Reply | Search | Read"]
    end

    subgraph DATA["DATA STORES"]
        direction LR
        REDIS["Upstash Redis\nSessions | Rate Limits\nLocks | OAuth State"]
        SUPA["Supabase PostgreSQL\nCredentials (encrypted)\nAudit Log"]
    end

    subgraph GOOGLE["GOOGLE APIs"]
        direction LR
        GCAL["Calendar API v3"]
        GMAIL["Gmail API v1"]
        GOAUTH["OAuth 2.0"]
    end

    SEARXNG["SearXNG\nWeb Search"]

    USER -->|"SMS"| PEPPI
    PEPPI -->|"POST /execute-action"| ROUTES
    ROUTES --> SESSION & CRED & MIDDLEWARE
    OAUTH --> CRED
    OAUTH --> GOAUTH
    SESSION --> REDIS
    CRED --> SUPA
    MIDDLEWARE --> REDIS
    MIDDLEWARE --> SUPA

    ROUTES -->|"POST /execute"| SERVER
    SERVER --> TOKEN_BRIDGE --> OAUTH
    SERVER --> CONTEXT --> CLI
    CLI -->|"Spawns"| INTENT
    INTENT -->|"Task"| SKILL
    INTENT -->|"Chat"| CLI
    SKILL --> CAL & MAIL
    SKILL -->|"curl + Bearer token"| GCAL
    SKILL -->|"curl + Bearer token"| GMAIL
    CLI -->|"Web search"| SEARXNG

    %% ── COLORS ──

    %% User — Blue
    style USER fill:#3B82F6,stroke:#1E40AF,color:#FFF,stroke-width:2px
    style PEPPI fill:#60A5FA,stroke:#1E40AF,color:#FFF,stroke-width:2px
    style USER_LAYER fill:#DBEAFE,stroke:#1E40AF,color:#1E40AF,stroke-width:2px

    %% FastAPI — Green
    style FASTAPI fill:#D1FAE5,stroke:#047857,color:#047857,stroke-width:2px
    style ROUTES fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style OAUTH fill:#34D399,stroke:#047857,color:#FFF,stroke-width:2px
    style SESSION fill:#A7F3D0,stroke:#047857,color:#065F46,stroke-width:1px
    style CRED fill:#A7F3D0,stroke:#047857,color:#065F46,stroke-width:1px
    style MIDDLEWARE fill:#A7F3D0,stroke:#047857,color:#065F46,stroke-width:1px

    %% Gateway — Orange
    style GATEWAY fill:#FFF7ED,stroke:#C2410C,color:#C2410C,stroke-width:2px
    style SERVER fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style TOKEN_BRIDGE fill:#FB923C,stroke:#C2410C,color:#FFF,stroke-width:2px
    style CONTEXT fill:#FDBA74,stroke:#C2410C,color:#7C2D12,stroke-width:1px
    style CLI fill:#FED7AA,stroke:#C2410C,color:#7C2D12,stroke-width:1px

    %% Agent — Purple
    style AGENT fill:#F3E8FF,stroke:#7C3AED,color:#7C3AED,stroke-width:2px
    style INTENT fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px
    style SKILL fill:#A78BFA,stroke:#6D28D9,color:#FFF,stroke-width:2px

    %% Skills — Yellow
    style SKILLS_FILE fill:#FEF9C3,stroke:#CA8A04,color:#854D0E,stroke-width:2px
    style CAL fill:#FACC15,stroke:#CA8A04,color:#422006,stroke-width:2px
    style MAIL fill:#FDE047,stroke:#CA8A04,color:#422006,stroke-width:2px

    %% Data — Red/Pink
    style DATA fill:#FFF1F2,stroke:#E11D48,color:#BE123C,stroke-width:2px
    style REDIS fill:#FB7185,stroke:#BE123C,color:#FFF,stroke-width:2px
    style SUPA fill:#F43F5E,stroke:#BE123C,color:#FFF,stroke-width:2px

    %% Google — Teal
    style GOOGLE fill:#CCFBF1,stroke:#0D9488,color:#0F766E,stroke-width:2px
    style GCAL fill:#14B8A6,stroke:#0F766E,color:#FFF,stroke-width:2px
    style GMAIL fill:#2DD4BF,stroke:#0F766E,color:#042F2E,stroke-width:2px
    style GOAUTH fill:#5EEAD4,stroke:#0F766E,color:#042F2E,stroke-width:2px
    style SEARXNG fill:#99F6E4,stroke:#0F766E,color:#042F2E,stroke-width:2px
```

---

## 2. SCENARIO: Simple Chat — No Task, Just Conversation

```mermaid
flowchart TB
    USER["User sends SMS\n'Hey, what can you do?'"]
    PEPPI["Peppi Platform"]
    FASTAPI["FastAPI Wrapper\n/execute-action"]
    REDIS["Upstash Redis"]
    SUPA["Supabase DB"]
    GATEWAY["OpenClaw Gateway\n/execute"]
    AGENT{"AI Agent\nIntent: Task or Chat?"}
    NO_SKILL["No Skill Needed\nNo task keywords detected\nJust a conversational question"]
    RESPONSE["Agent generates response\n'I can help you manage your\ncalendar, send emails, search\nthe web, and have conversations!'"]
    SAVE["Save to session + audit log"]
    REPLY["User receives SMS reply"]

    USER -->|"1. SMS message"| PEPPI
    PEPPI -->|"2. POST /execute-action\nuser_id, message, timezone"| FASTAPI
    FASTAPI -->|"3. Acquire lock\nGet session\nCheck rate limit"| REDIS
    FASTAPI -->|"4. Log action\nstatus: pending"| SUPA
    FASTAPI -->|"5. POST /execute\nsession_id, message, history"| GATEWAY
    GATEWAY -->|"6. Fetch OAuth token"| FASTAPI
    GATEWAY -->|"7. Build context\nIdentity + Timezone + Capabilities"| AGENT
    AGENT -->|"8. No action keywords\nInformational query"| NO_SKILL
    NO_SKILL -->|"9. Generate chat response\naction_type: chat"| RESPONSE
    RESPONSE -->|"10. Return JSON to Gateway"| GATEWAY
    GATEWAY -->|"11. Forward response"| FASTAPI
    FASTAPI -->|"12. Save assistant msg\nto session history"| SAVE
    SAVE -->|"13. Update audit log\nstatus: success\nRelease lock"| REDIS
    SAVE -->|"13. Update audit log"| SUPA
    FASTAPI -->|"14. Return response"| PEPPI
    PEPPI -->|"15. Deliver SMS"| REPLY

    style USER fill:#3B82F6,stroke:#1E40AF,color:#FFF,stroke-width:2px
    style PEPPI fill:#60A5FA,stroke:#1E40AF,color:#FFF,stroke-width:2px
    style FASTAPI fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style REDIS fill:#FB7185,stroke:#BE123C,color:#FFF,stroke-width:2px
    style SUPA fill:#F43F5E,stroke:#BE123C,color:#FFF,stroke-width:2px
    style GATEWAY fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style AGENT fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px
    style NO_SKILL fill:#C4B5FD,stroke:#6D28D9,color:#4C1D95,stroke-width:2px
    style RESPONSE fill:#A7F3D0,stroke:#047857,color:#065F46,stroke-width:2px
    style SAVE fill:#FDBA74,stroke:#C2410C,color:#7C2D12,stroke-width:2px
    style REPLY fill:#3B82F6,stroke:#1E40AF,color:#FFF,stroke-width:2px
```

---

## 3. SCENARIO: Create Calendar Event

```mermaid
flowchart TB
    USER["User sends SMS\n'Schedule meeting with Sarah\ntomorrow at 3pm'"]
    PEPPI["Peppi Platform"]
    FASTAPI["FastAPI Wrapper\n/execute-action"]
    REDIS["Upstash Redis"]
    SUPA["Supabase DB"]
    GATEWAY["OpenClaw Gateway\n/execute"]
    TOKEN["OAuth Token Bridge\nDecrypt from Supabase\nRefresh if expired"]
    AGENT{"AI Agent\nIntent: Task or Chat?"}
    SKILL["google-workspace Skill\nAction: CREATE EVENT"]
    PARSE["Parameter Extraction\nTitle: Meeting with Sarah\nDate: tomorrow\nTime: 3pm\nDuration: 1 hour"]
    TZ["Timezone Conversion\n3:00 PM EST\n= 20:00 UTC\nStart: 2026-02-18T20:00:00Z\nEnd: 2026-02-18T21:00:00Z"]
    CURL["curl -X POST\nAuthorization: Bearer token\ncalendar/v3/calendars/primary/events"]
    GCAL["Google Calendar API v3"]
    RESULT["Event Created\nID: evt_abc123\nMeeting with Sarah"]
    SAVE["Save to session + audit log\nlast_action: calendar_create"]
    REPLY["User receives SMS\n'Meeting scheduled for\ntomorrow at 3:00 PM EST'"]

    USER -->|"1. SMS message"| PEPPI
    PEPPI -->|"2. POST /execute-action\nuser_id, message, timezone"| FASTAPI
    FASTAPI -->|"3. Lock + Session + Rate limit"| REDIS
    FASTAPI -->|"4. Log action pending"| SUPA
    FASTAPI -->|"5. POST /execute"| GATEWAY
    GATEWAY -->|"6. GET /oauth/google/token"| TOKEN
    TOKEN -->|"7. Fetch encrypted creds"| SUPA
    TOKEN -->|"8. Return fresh access_token"| GATEWAY
    GATEWAY -->|"9. Build context\nIdentity + TZ + Capabilities"| AGENT
    AGENT -->|"10. 'Schedule meeting'\n= Calendar task"| SKILL
    SKILL -->|"11. Extract params\nfrom user message"| PARSE
    PARSE -->|"12. Convert user TZ to UTC"| TZ
    TZ -->|"13. Build JSON + curl POST"| CURL
    CURL -->|"14. Create event request"| GCAL
    GCAL -->|"15. Event created\nevt_abc123"| RESULT
    RESULT -->|"16. Return to Agent"| GATEWAY
    GATEWAY -->|"17. Forward response"| FASTAPI
    FASTAPI -->|"18. Save + Update audit"| SAVE
    SAVE --> REDIS
    SAVE --> SUPA
    FASTAPI -->|"19. Return response"| PEPPI
    PEPPI -->|"20. Deliver SMS"| REPLY

    style USER fill:#3B82F6,stroke:#1E40AF,color:#FFF,stroke-width:2px
    style PEPPI fill:#60A5FA,stroke:#1E40AF,color:#FFF,stroke-width:2px
    style FASTAPI fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style REDIS fill:#FB7185,stroke:#BE123C,color:#FFF,stroke-width:2px
    style SUPA fill:#F43F5E,stroke:#BE123C,color:#FFF,stroke-width:2px
    style GATEWAY fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style TOKEN fill:#FB923C,stroke:#C2410C,color:#FFF,stroke-width:2px
    style AGENT fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px
    style SKILL fill:#A78BFA,stroke:#6D28D9,color:#FFF,stroke-width:2px
    style PARSE fill:#C4B5FD,stroke:#6D28D9,color:#4C1D95,stroke-width:2px
    style TZ fill:#FACC15,stroke:#CA8A04,color:#422006,stroke-width:2px
    style CURL fill:#FDE047,stroke:#CA8A04,color:#422006,stroke-width:2px
    style GCAL fill:#14B8A6,stroke:#0F766E,color:#FFF,stroke-width:2px
    style RESULT fill:#A7F3D0,stroke:#047857,color:#065F46,stroke-width:2px
    style SAVE fill:#FDBA74,stroke:#C2410C,color:#7C2D12,stroke-width:2px
    style REPLY fill:#3B82F6,stroke:#1E40AF,color:#FFF,stroke-width:2px
```

---

## 4. SCENARIO: Query Calendar Events — "What's on my schedule today?"

```mermaid
flowchart TB
    USER["User sends SMS\n'What meetings do I have today?'"]
    PEPPI["Peppi Platform"]
    FASTAPI["FastAPI Wrapper\n/execute-action"]
    REDIS["Upstash Redis"]
    SUPA["Supabase DB"]
    GATEWAY["OpenClaw Gateway\n/execute"]
    AGENT{"AI Agent\nIntent: Task or Chat?"}
    SKILL["google-workspace Skill\nAction: LIST EVENTS"]
    TZ["Date Calculation in Bash\nUser TZ: America/New_York\ntoday 00:00 EST = 05:00 UTC\ntoday 23:59 EST = 04:59 UTC+1"]
    CURL["curl GET\nAuthorization: Bearer token\n/events?timeMin=...&timeMax=...\n&orderBy=startTime"]
    GCAL["Google Calendar API v3"]
    EVENTS["3 Events Returned\n1. Team Standup — 9 AM\n2. Client Call — 1 PM\n3. 1:1 with Manager — 3 PM"]
    FORMAT["Parse with jq\nConvert UTC back to EST\nFormat readable list"]
    SAVE["Save to session + audit log"]
    REPLY["User receives SMS\nwith today's schedule"]

    USER -->|"1. SMS message"| PEPPI
    PEPPI -->|"2. POST /execute-action"| FASTAPI
    FASTAPI -->|"3. Lock + Session + Rate limit"| REDIS
    FASTAPI -->|"4. Log action pending"| SUPA
    FASTAPI -->|"5. POST /execute + fetch token"| GATEWAY
    GATEWAY -->|"6. Build context + spawn agent"| AGENT
    AGENT -->|"7. 'What meetings'\n= Calendar query"| SKILL
    SKILL -->|"8. Calculate today's\ntime window in UTC"| TZ
    TZ -->|"9. Build GET request"| CURL
    CURL -->|"10. Fetch events"| GCAL
    GCAL -->|"11. Return event list"| EVENTS
    EVENTS -->|"12. Convert UTC to user TZ"| FORMAT
    FORMAT -->|"13. Return formatted list"| GATEWAY
    GATEWAY -->|"14. Forward response"| FASTAPI
    FASTAPI -->|"15. Save + audit"| SAVE
    SAVE --> REDIS
    SAVE --> SUPA
    FASTAPI -->|"16. Return response"| PEPPI
    PEPPI -->|"17. Deliver SMS"| REPLY

    style USER fill:#3B82F6,stroke:#1E40AF,color:#FFF,stroke-width:2px
    style PEPPI fill:#60A5FA,stroke:#1E40AF,color:#FFF,stroke-width:2px
    style FASTAPI fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style REDIS fill:#FB7185,stroke:#BE123C,color:#FFF,stroke-width:2px
    style SUPA fill:#F43F5E,stroke:#BE123C,color:#FFF,stroke-width:2px
    style GATEWAY fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style AGENT fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px
    style SKILL fill:#A78BFA,stroke:#6D28D9,color:#FFF,stroke-width:2px
    style TZ fill:#FACC15,stroke:#CA8A04,color:#422006,stroke-width:2px
    style CURL fill:#FDE047,stroke:#CA8A04,color:#422006,stroke-width:2px
    style GCAL fill:#14B8A6,stroke:#0F766E,color:#FFF,stroke-width:2px
    style EVENTS fill:#2DD4BF,stroke:#0F766E,color:#042F2E,stroke-width:2px
    style FORMAT fill:#C4B5FD,stroke:#6D28D9,color:#4C1D95,stroke-width:2px
    style SAVE fill:#FDBA74,stroke:#C2410C,color:#7C2D12,stroke-width:2px
    style REPLY fill:#3B82F6,stroke:#1E40AF,color:#FFF,stroke-width:2px
```

---

## 5. SCENARIO: Send a New Email

```mermaid
flowchart TB
    USER["User sends SMS\n'Send email to john@example.com\nabout the project update'"]
    PEPPI["Peppi Platform"]
    FASTAPI["FastAPI Wrapper\n/execute-action"]
    REDIS["Upstash Redis"]
    SUPA["Supabase DB"]
    GATEWAY["OpenClaw Gateway\n/execute"]
    AGENT{"AI Agent\nIntent: Task or Chat?"}
    SKILL["google-workspace Skill\nAction: SEND EMAIL"]
    PARSE["Parameter Extraction\nTo: john@example.com\nSubject: Project Update (inferred)\nBody: We're on track for Friday"]
    BUILD["Build RFC 2822 Email\nFrom: me\nTo: john@example.com\nSubject: Project Update\nBody: message content"]
    ENCODE["Base64url Encode\n1. Base64 encode email\n2. Replace + with -\n3. Replace / with _\n4. Remove = padding"]
    CURL["curl -X POST\nAuthorization: Bearer token\n/users/me/messages/send\nBody: raw encoded email"]
    GMAIL["Google Gmail API v1"]
    RESULT["Email Sent\nMessage ID: msg_18e3f\nLabel: SENT"]
    SAVE["Save to session + audit log\nlast_action: email_send"]
    REPLY["User receives SMS\n'Email sent to john@example.com\nwith subject Project Update'"]

    USER -->|"1. SMS message"| PEPPI
    PEPPI -->|"2. POST /execute-action"| FASTAPI
    FASTAPI -->|"3. Lock + Session + Rate limit"| REDIS
    FASTAPI -->|"4. Log action pending"| SUPA
    FASTAPI -->|"5. POST /execute + fetch token"| GATEWAY
    GATEWAY -->|"6. Build context + spawn agent"| AGENT
    AGENT -->|"7. 'Send email'\n= Gmail task"| SKILL
    SKILL -->|"8. Extract to, subject, body"| PARSE
    PARSE -->|"9. Compose RFC 2822 format"| BUILD
    BUILD -->|"10. Encode for Gmail API"| ENCODE
    ENCODE -->|"11. POST to Gmail"| CURL
    CURL -->|"12. Send request"| GMAIL
    GMAIL -->|"13. Email delivered\nmsg_18e3f"| RESULT
    RESULT -->|"14. Return to Agent"| GATEWAY
    GATEWAY -->|"15. Forward response"| FASTAPI
    FASTAPI -->|"16. Save + audit"| SAVE
    SAVE --> REDIS
    SAVE --> SUPA
    FASTAPI -->|"17. Return response"| PEPPI
    PEPPI -->|"18. Deliver SMS"| REPLY

    style USER fill:#3B82F6,stroke:#1E40AF,color:#FFF,stroke-width:2px
    style PEPPI fill:#60A5FA,stroke:#1E40AF,color:#FFF,stroke-width:2px
    style FASTAPI fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style REDIS fill:#FB7185,stroke:#BE123C,color:#FFF,stroke-width:2px
    style SUPA fill:#F43F5E,stroke:#BE123C,color:#FFF,stroke-width:2px
    style GATEWAY fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style AGENT fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px
    style SKILL fill:#A78BFA,stroke:#6D28D9,color:#FFF,stroke-width:2px
    style PARSE fill:#C4B5FD,stroke:#6D28D9,color:#4C1D95,stroke-width:2px
    style BUILD fill:#FACC15,stroke:#CA8A04,color:#422006,stroke-width:2px
    style ENCODE fill:#FDE047,stroke:#CA8A04,color:#422006,stroke-width:2px
    style CURL fill:#FDBA74,stroke:#C2410C,color:#7C2D12,stroke-width:2px
    style GMAIL fill:#2DD4BF,stroke:#0F766E,color:#042F2E,stroke-width:2px
    style RESULT fill:#A7F3D0,stroke:#047857,color:#065F46,stroke-width:2px
    style SAVE fill:#FDBA74,stroke:#C2410C,color:#7C2D12,stroke-width:2px
    style REPLY fill:#3B82F6,stroke:#1E40AF,color:#FFF,stroke-width:2px
```

---

## 6. SCENARIO: Reply to an Email (Threaded)

```mermaid
flowchart TB
    USER["User sends SMS\n'Reply to Sarah's last email\nsaying I'll be there at 10am'"]
    PEPPI["Peppi Platform"]
    FASTAPI["FastAPI Wrapper\n/execute-action"]
    REDIS["Upstash Redis"]
    SUPA["Supabase DB"]
    GATEWAY["OpenClaw Gateway\n/execute"]
    AGENT{"AI Agent\nIntent: Task or Chat?"}
    SKILL["google-workspace Skill\nAction: REPLY TO EMAIL"]

    subgraph GMAIL_OPS["3-Step Gmail Reply Process"]
        direction TB
        SEARCH["Step A: Search for Sarah's emails\ncurl GET /messages?q=from:sarah\nReturns: msg_sarah_99, thread_55"]
        DETAIL["Step B: Get original message details\ncurl GET /messages/msg_sarah_99?format=full\nExtract: From, Subject, Message-Id"]
        BUILD["Step C: Build threaded reply\nTo: sarah@company.com\nSubject: Re: Team Lunch Plans\nIn-Reply-To: orig_msg_id\nReferences: orig_msg_id\nBody: I'll be there at 10am!"]
    end

    GMAIL["Google Gmail API v1"]
    ENCODE["Base64url Encode reply\n+ include threadId: thread_55"]
    RESULT["Reply Sent in Same Thread\nThreading preserved via\nIn-Reply-To + References headers"]
    SAVE["Save to session + audit log\nlast_action: email_reply"]
    REPLY["User receives SMS\n'Replied to Sarah's email\nTeam Lunch Plans'"]

    USER -->|"1. SMS message"| PEPPI
    PEPPI -->|"2. POST /execute-action"| FASTAPI
    FASTAPI -->|"3. Lock + Session + Rate limit"| REDIS
    FASTAPI -->|"4. Log action pending"| SUPA
    FASTAPI -->|"5. POST /execute + fetch token"| GATEWAY
    GATEWAY -->|"6. Build context + spawn agent"| AGENT
    AGENT -->|"7. 'Reply to email'\n= Gmail reply task"| SKILL
    SKILL -->|"8. Start 3-step process"| SEARCH
    SEARCH -->|"9. curl GET to Gmail"| GMAIL
    GMAIL -->|"10. msg_sarah_99 found"| SEARCH
    SEARCH -->|"11. Need full details"| DETAIL
    DETAIL -->|"12. curl GET format=full"| GMAIL
    GMAIL -->|"13. Headers: From, Subject,\nMessage-Id extracted"| DETAIL
    DETAIL -->|"14. Build reply with\nthreading headers"| BUILD
    BUILD -->|"15. Encode + attach threadId"| ENCODE
    ENCODE -->|"16. curl POST /messages/send"| GMAIL
    GMAIL -->|"17. Sent in thread_55"| RESULT
    RESULT -->|"18. Return to Agent"| GATEWAY
    GATEWAY -->|"19. Forward response"| FASTAPI
    FASTAPI -->|"20. Save + audit"| SAVE
    SAVE --> REDIS
    SAVE --> SUPA
    FASTAPI -->|"21. Return response"| PEPPI
    PEPPI -->|"22. Deliver SMS"| REPLY

    style USER fill:#3B82F6,stroke:#1E40AF,color:#FFF,stroke-width:2px
    style PEPPI fill:#60A5FA,stroke:#1E40AF,color:#FFF,stroke-width:2px
    style FASTAPI fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style REDIS fill:#FB7185,stroke:#BE123C,color:#FFF,stroke-width:2px
    style SUPA fill:#F43F5E,stroke:#BE123C,color:#FFF,stroke-width:2px
    style GATEWAY fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style AGENT fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px
    style SKILL fill:#A78BFA,stroke:#6D28D9,color:#FFF,stroke-width:2px
    style GMAIL_OPS fill:#FEF9C3,stroke:#CA8A04,color:#854D0E,stroke-width:2px
    style SEARCH fill:#FACC15,stroke:#CA8A04,color:#422006,stroke-width:2px
    style DETAIL fill:#FDE047,stroke:#CA8A04,color:#422006,stroke-width:2px
    style BUILD fill:#FDE68A,stroke:#CA8A04,color:#422006,stroke-width:2px
    style GMAIL fill:#2DD4BF,stroke:#0F766E,color:#042F2E,stroke-width:2px
    style ENCODE fill:#C4B5FD,stroke:#6D28D9,color:#4C1D95,stroke-width:2px
    style RESULT fill:#A7F3D0,stroke:#047857,color:#065F46,stroke-width:2px
    style SAVE fill:#FDBA74,stroke:#C2410C,color:#7C2D12,stroke-width:2px
    style REPLY fill:#3B82F6,stroke:#1E40AF,color:#FFF,stroke-width:2px
```

---

## 7. SCENARIO: Google OAuth Connection Flow

```mermaid
flowchart TB
    subgraph PHASE1["PHASE 1 — Initiate OAuth"]
        direction TB
        USER_CLICK["User clicks\n'Connect Google Account'\non Peppi Website"]
        INIT["FastAPI: /oauth/google/init\nGenerate CSRF state token\nstate = random UUID"]
        STORE_STATE["Store state in Redis\noauth_state:uuid TTL=600s\nuser_id + redirect_uri"]
        AUTH_URL["Build Google Auth URL\nclient_id + redirect_uri\nscope: calendar + gmail\naccess_type: offline"]
        REDIRECT["Redirect user to\nGoogle Consent Screen"]
    end

    subgraph PHASE2["PHASE 2 — User Consent"]
        direction TB
        CONSENT["Google shows:\n'Moltbot wants access to\nyour Calendar and Gmail.\nAllow?'"]
        ALLOW["User clicks Allow"]
        AUTH_CODE["Google generates\nauthorization code"]
        CALLBACK["Google redirects to\n/oauth/google/callback\n?code=AUTH_CODE&state=csrf"]
    end

    subgraph PHASE3["PHASE 3 — Token Exchange"]
        direction TB
        VALIDATE["FastAPI validates CSRF state\nGET oauth_state from Redis\nDEL after validation"]
        EXCHANGE["POST to oauth2.googleapis.com/token\ncode + client_id + client_secret\ngrant_type: authorization_code"]
        TOKENS["Google returns tokens\naccess_token: ya29.xxx\nrefresh_token: 1//xxx\nexpires_in: 3600"]
    end

    subgraph PHASE4["PHASE 4 — Store Credentials"]
        direction TB
        ENCRYPT["Encrypt with Fernet AES-128\nFernet.encrypt(json.dumps(\naccess_token + refresh_token))"]
        STORE_DB["UPSERT tbl_clawdbot_credentials\nuser_id=123, service=google\nencrypted_credentials, expires_at"]
        SUCCESS["Redirect to Peppi website\nstatus=success\n'Google Account Connected!'"]
    end

    subgraph PHASE5["PHASE 5 — Token Usage (Later)"]
        direction TB
        GW_REQUEST["Gateway needs token\nGET /oauth/google/token/123"]
        FETCH_CREDS["Fetch from Supabase\nDecrypt with Fernet"]
        CHECK{"Token\nexpired?"}
        USE_TOKEN["Return fresh\naccess_token to Gateway"]
        REFRESH["POST to Google\ngrant_type: refresh_token\nGet new access_token\nUpdate Supabase"]
    end

    REDIS["Upstash Redis"]
    SUPA["Supabase DB"]
    GOOGLE["Google OAuth 2.0"]

    USER_CLICK -->|"1. Click connect"| INIT
    INIT -->|"2. Store CSRF state"| STORE_STATE
    STORE_STATE -->|"3."| REDIS
    INIT -->|"4. Build URL"| AUTH_URL
    AUTH_URL -->|"5. Redirect"| REDIRECT
    REDIRECT -->|"6. User sees consent"| CONSENT
    CONSENT --> ALLOW
    ALLOW -->|"7. User approves"| AUTH_CODE
    AUTH_CODE -->|"8. Callback with code"| CALLBACK
    CALLBACK -->|"9. Validate state"| VALIDATE
    VALIDATE -->|"10. Check Redis"| REDIS
    VALIDATE -->|"11. Exchange code"| EXCHANGE
    EXCHANGE -->|"12. POST to Google"| GOOGLE
    GOOGLE -->|"13. Return tokens"| TOKENS
    TOKENS -->|"14. Encrypt tokens"| ENCRYPT
    ENCRYPT -->|"15. Store encrypted"| STORE_DB
    STORE_DB -->|"16."| SUPA
    STORE_DB -->|"17. Redirect success"| SUCCESS

    GW_REQUEST -->|"18. Fetch creds"| FETCH_CREDS
    FETCH_CREDS -->|"19."| SUPA
    FETCH_CREDS -->|"20. Check expiry"| CHECK
    CHECK -->|"Not expired"| USE_TOKEN
    CHECK -->|"Expired"| REFRESH
    REFRESH -->|"21. Refresh token"| GOOGLE
    REFRESH -->|"22. Update DB"| SUPA
    REFRESH -->|"23. Return new token"| USE_TOKEN

    style PHASE1 fill:#DBEAFE,stroke:#1E40AF,color:#1E40AF,stroke-width:2px
    style USER_CLICK fill:#3B82F6,stroke:#1E40AF,color:#FFF,stroke-width:2px
    style INIT fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style STORE_STATE fill:#A7F3D0,stroke:#047857,color:#065F46,stroke-width:2px
    style AUTH_URL fill:#34D399,stroke:#047857,color:#FFF,stroke-width:2px
    style REDIRECT fill:#60A5FA,stroke:#1E40AF,color:#FFF,stroke-width:2px

    style PHASE2 fill:#F3E8FF,stroke:#7C3AED,color:#7C3AED,stroke-width:2px
    style CONSENT fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px
    style ALLOW fill:#A78BFA,stroke:#6D28D9,color:#FFF,stroke-width:2px
    style AUTH_CODE fill:#C4B5FD,stroke:#6D28D9,color:#4C1D95,stroke-width:2px
    style CALLBACK fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px

    style PHASE3 fill:#FFF7ED,stroke:#C2410C,color:#C2410C,stroke-width:2px
    style VALIDATE fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style EXCHANGE fill:#FB923C,stroke:#C2410C,color:#FFF,stroke-width:2px
    style TOKENS fill:#FDBA74,stroke:#C2410C,color:#7C2D12,stroke-width:2px

    style PHASE4 fill:#FEF9C3,stroke:#CA8A04,color:#854D0E,stroke-width:2px
    style ENCRYPT fill:#FACC15,stroke:#CA8A04,color:#422006,stroke-width:2px
    style STORE_DB fill:#FDE047,stroke:#CA8A04,color:#422006,stroke-width:2px
    style SUCCESS fill:#A7F3D0,stroke:#047857,color:#065F46,stroke-width:2px

    style PHASE5 fill:#D1FAE5,stroke:#047857,color:#047857,stroke-width:2px
    style GW_REQUEST fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style FETCH_CREDS fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style CHECK fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px
    style USE_TOKEN fill:#A7F3D0,stroke:#047857,color:#065F46,stroke-width:2px
    style REFRESH fill:#FB7185,stroke:#BE123C,color:#FFF,stroke-width:2px

    style REDIS fill:#FB7185,stroke:#BE123C,color:#FFF,stroke-width:2px
    style SUPA fill:#F43F5E,stroke:#BE123C,color:#FFF,stroke-width:2px
    style GOOGLE fill:#14B8A6,stroke:#0F766E,color:#FFF,stroke-width:2px
```

---

## 8. SCENARIO: Agent Decision Flow — Task vs Chat

```mermaid
flowchart TB
    START["User Message Arrives"]

    subgraph FASTAPI["FastAPI Wrapper Processing"]
        LOCK["Acquire User Lock"]
        SESSION["Get or Create Session"]
        HISTORY["Add to Conversation History"]
        LOG_START["Log Action Start"]
    end

    subgraph GATEWAY["OpenClaw Gateway Processing"]
        FETCH_TOKEN["Fetch Fresh OAuth Token"]
        BUILD_CTX["Build Rich Context: Identity + Timezone + Capabilities"]
        SPAWN["Spawn OpenClaw CLI — Gemini 2.5 Flash"]
    end

    subgraph AGENT["AI Agent Decision Engine"]
        ANALYZE["Analyze User Message + Context + History"]
        DECISION{{"Intent Classification: Task or Chat?"}}

        subgraph CHAT_PATH["CHAT PATH — No Skill Needed"]
            CHAT_RESPONSE["Generate Conversational Response"]
        end

        subgraph TASK_PATH["TASK PATH — Skill Invocation"]
            CLASSIFY{{"Which Google Service?"}}

            subgraph CAL_OPS["Calendar Operations"]
                CAL_Q{{"Calendar Action?"}}
                CAL_LIST["LIST — GET /calendars/primary/events"]
                CAL_CREATE["CREATE — POST /calendars/primary/events"]
                CAL_UPDATE["UPDATE — PUT /events/id"]
                CAL_DELETE["DELETE — DELETE /events/id"]
            end

            subgraph MAIL_OPS["Gmail Operations"]
                MAIL_Q{{"Gmail Action?"}}
                MAIL_LIST["LIST/SEARCH — GET /messages?q=..."]
                MAIL_READ["READ — GET /messages/id?format=full"]
                MAIL_SEND["SEND — POST /messages/send"]
                MAIL_REPLY["REPLY — Search + Thread + POST /messages/send"]
            end
        end
    end

    subgraph RESPONSE["Response Pipeline"]
        FORMAT["Format Response for SMS"]
        SAVE_HIST["Save to Session History"]
        LOG_END["Update Audit Log"]
        RELEASE["Release User Lock"]
        RETURN["Return to Peppi Platform"]
    end

    START --> LOCK --> SESSION --> HISTORY --> LOG_START
    LOG_START --> FETCH_TOKEN --> BUILD_CTX --> SPAWN
    SPAWN --> ANALYZE --> DECISION

    DECISION -->|"Greetings, questions, no action keywords"| CHAT_RESPONSE

    DECISION -->|"Action keywords detected"| CLASSIFY

    CLASSIFY -->|"Calendar: schedule, meeting, event"| CAL_Q
    CLASSIFY -->|"Gmail: email, send, reply, inbox"| MAIL_Q

    CAL_Q -->|"list/show/what"| CAL_LIST
    CAL_Q -->|"create/schedule/add"| CAL_CREATE
    CAL_Q -->|"update/change/move"| CAL_UPDATE
    CAL_Q -->|"delete/cancel/remove"| CAL_DELETE

    MAIL_Q -->|"list/search/show"| MAIL_LIST
    MAIL_Q -->|"read/open/details"| MAIL_READ
    MAIL_Q -->|"send/compose/write"| MAIL_SEND
    MAIL_Q -->|"reply/respond"| MAIL_REPLY

    CHAT_RESPONSE --> FORMAT
    CAL_LIST --> FORMAT
    CAL_CREATE --> FORMAT
    CAL_UPDATE --> FORMAT
    CAL_DELETE --> FORMAT
    MAIL_LIST --> FORMAT
    MAIL_READ --> FORMAT
    MAIL_SEND --> FORMAT
    MAIL_REPLY --> FORMAT

    FORMAT --> SAVE_HIST --> LOG_END --> RELEASE --> RETURN

    %% ── COLORS ──

    style START fill:#3B82F6,stroke:#1E40AF,color:#FFF,stroke-width:2px

    %% FastAPI — Green
    style FASTAPI fill:#D1FAE5,stroke:#047857,color:#047857,stroke-width:2px
    style LOCK fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style SESSION fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style HISTORY fill:#A7F3D0,stroke:#047857,color:#065F46,stroke-width:1px
    style LOG_START fill:#A7F3D0,stroke:#047857,color:#065F46,stroke-width:1px

    %% Gateway — Orange
    style GATEWAY fill:#FFF7ED,stroke:#C2410C,color:#C2410C,stroke-width:2px
    style FETCH_TOKEN fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style BUILD_CTX fill:#FB923C,stroke:#C2410C,color:#FFF,stroke-width:2px
    style SPAWN fill:#FDBA74,stroke:#C2410C,color:#7C2D12,stroke-width:1px

    %% Agent — Purple
    style AGENT fill:#F3E8FF,stroke:#7C3AED,color:#7C3AED,stroke-width:2px
    style ANALYZE fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px
    style DECISION fill:#A78BFA,stroke:#6D28D9,color:#FFF,stroke-width:2px

    %% Chat Path — Light Purple
    style CHAT_PATH fill:#EDE9FE,stroke:#7C3AED,color:#6D28D9,stroke-width:1px
    style CHAT_RESPONSE fill:#C4B5FD,stroke:#6D28D9,color:#4C1D95,stroke-width:2px

    %% Task Path — Yellow
    style TASK_PATH fill:#FEF9C3,stroke:#CA8A04,color:#854D0E,stroke-width:2px
    style CLASSIFY fill:#FACC15,stroke:#CA8A04,color:#422006,stroke-width:2px

    %% Calendar — Teal
    style CAL_OPS fill:#CCFBF1,stroke:#0D9488,color:#0F766E,stroke-width:2px
    style CAL_Q fill:#14B8A6,stroke:#0F766E,color:#FFF,stroke-width:2px
    style CAL_LIST fill:#2DD4BF,stroke:#0F766E,color:#042F2E,stroke-width:1px
    style CAL_CREATE fill:#2DD4BF,stroke:#0F766E,color:#042F2E,stroke-width:1px
    style CAL_UPDATE fill:#2DD4BF,stroke:#0F766E,color:#042F2E,stroke-width:1px
    style CAL_DELETE fill:#2DD4BF,stroke:#0F766E,color:#042F2E,stroke-width:1px

    %% Gmail — Blue
    style MAIL_OPS fill:#DBEAFE,stroke:#1E40AF,color:#1E40AF,stroke-width:2px
    style MAIL_Q fill:#3B82F6,stroke:#1E40AF,color:#FFF,stroke-width:2px
    style MAIL_LIST fill:#60A5FA,stroke:#1E40AF,color:#FFF,stroke-width:1px
    style MAIL_READ fill:#60A5FA,stroke:#1E40AF,color:#FFF,stroke-width:1px
    style MAIL_SEND fill:#60A5FA,stroke:#1E40AF,color:#FFF,stroke-width:1px
    style MAIL_REPLY fill:#60A5FA,stroke:#1E40AF,color:#FFF,stroke-width:1px

    %% Response — Red/Pink
    style RESPONSE fill:#FFF1F2,stroke:#E11D48,color:#BE123C,stroke-width:2px
    style FORMAT fill:#FB7185,stroke:#BE123C,color:#FFF,stroke-width:2px
    style SAVE_HIST fill:#FB7185,stroke:#BE123C,color:#FFF,stroke-width:1px
    style LOG_END fill:#F43F5E,stroke:#BE123C,color:#FFF,stroke-width:1px
    style RELEASE fill:#F43F5E,stroke:#BE123C,color:#FFF,stroke-width:1px
    style RETURN fill:#F43F5E,stroke:#BE123C,color:#FFF,stroke-width:2px
```

---

## 9. SCENARIO: Data Store Interactions — What Lives Where

```mermaid
flowchart LR
    subgraph APP["Application Layer"]
        FA["FastAPI Wrapper"]
        GW["OpenClaw Gateway"]
        AGENT["AI Agent"]
    end

    subgraph UPSTASH["UPSTASH REDIS — Ephemeral, In-Memory, HTTP-based"]
        direction TB
        S1["SESSION DATA — session:user_id:session_id — TTL 3600s"]
        S3["USER LOCKS — lock:user_id — TTL 30s — Mutex"]
        S4["OAUTH STATE — oauth_state:uuid — TTL 600s — CSRF"]
    end

    subgraph SUPABASE["SUPABASE POSTGRESQL — Persistent, Encrypted"]
        direction TB
        T1["tbl_clawdbot_credentials — Fernet AES-128 encrypted tokens"]
        T2["tbl_clawdbot_audit_log — action_type, status, tokens_used"]
    end

    subgraph DISK["RENDER DISK — 1GB — /root/.openclaw"]
        D1["OpenClaw Agent Memory — per-user session keys"]
    end

    FA -->|"Session CRUD + Lock acquire/release"| S1
    FA -->|"Mutex operations"| S3
    FA -->|"OAuth state storage"| S4
    FA -->|"Store/retrieve encrypted tokens"| T1
    FA -->|"Log all actions, query history"| T2
    GW -->|"Agent memory persistence"| D1
    AGENT -->|"Session-based context recall"| D1

    %% ── COLORS ──

    %% App Layer — Purple
    style APP fill:#F3E8FF,stroke:#7C3AED,color:#7C3AED,stroke-width:2px
    style FA fill:#10B981,stroke:#047857,color:#FFF,stroke-width:2px
    style GW fill:#F97316,stroke:#C2410C,color:#FFF,stroke-width:2px
    style AGENT fill:#8B5CF6,stroke:#6D28D9,color:#FFF,stroke-width:2px

    %% Redis — Red/Pink
    style UPSTASH fill:#FFF1F2,stroke:#E11D48,color:#BE123C,stroke-width:2px
    style S1 fill:#FB7185,stroke:#BE123C,color:#FFF,stroke-width:2px
    style S3 fill:#FB7185,stroke:#BE123C,color:#FFF,stroke-width:2px
    style S4 fill:#FB7185,stroke:#BE123C,color:#FFF,stroke-width:2px

    %% Supabase — Blue
    style SUPABASE fill:#DBEAFE,stroke:#1E40AF,color:#1E40AF,stroke-width:2px
    style T1 fill:#3B82F6,stroke:#1E40AF,color:#FFF,stroke-width:2px
    style T2 fill:#60A5FA,stroke:#1E40AF,color:#FFF,stroke-width:2px

    %% Disk — Teal
    style DISK fill:#CCFBF1,stroke:#0D9488,color:#0F766E,stroke-width:2px
    style D1 fill:#14B8A6,stroke:#0F766E,color:#FFF,stroke-width:2px
```

---

## HOW TO USE IN EXCALIDRAW

1. Go to **excalidraw.com**
2. Click the **hamburger menu** (top-left)
3. Select **"Mermaid to Excalidraw"** (or press the Mermaid icon in the toolbar)
4. **Paste ONE diagram at a time** from the code blocks above
5. Click **"Insert into Canvas"**
6. Arrange and style each diagram on your canvas
7. Repeat for each scenario

Each diagram is self-contained and can be imported independently.
