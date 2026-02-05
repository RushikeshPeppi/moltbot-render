# Deployment & Testing Guide

Complete guide for deploying Moltbot-Render to production and testing all MVP features.

---

## Pre-Deployment Checklist

### 1. Environment Variables Setup

Complete [ENVIRONMENT_SETUP.md](ENVIRONMENT_SETUP.md) first. Ensure all variables are set:

**OpenClaw Gateway:**
- [x] `GEMINI_API_KEY`
- [x] `GOOGLE_API_KEY`
- [x] `BRAVE_API_KEY` (optional but recommended)

**FastAPI Wrapper:**
- [x] `SUPABASE_URL`
- [x] `SUPABASE_KEY`
- [x] `UPSTASH_REDIS_URL`
- [x] `UPSTASH_REDIS_TOKEN`
- [x] `GOOGLE_CLIENT_ID`
- [x] `GOOGLE_CLIENT_SECRET`
- [x] `GOOGLE_REDIRECT_URI`

### 2. Database Setup

Run migrations on Supabase:

```sql
-- Run migrations/002_supabase_tables.sql in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS tbl_clawdbot_credentials (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    service VARCHAR(50) NOT NULL,
    encrypted_credentials TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    UNIQUE(user_id, service)
);

CREATE TABLE IF NOT EXISTS tbl_clawdbot_audit_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    session_id VARCHAR(50),
    action_type VARCHAR(50) NOT NULL,
    request_summary TEXT,
    response_summary TEXT,
    status VARCHAR(20) NOT NULL,
    error_message TEXT,
    tokens_used INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_credentials_user ON tbl_clawdbot_credentials(user_id);
CREATE INDEX idx_audit_user ON tbl_clawdbot_audit_log(user_id);
CREATE INDEX idx_audit_created ON tbl_clawdbot_audit_log(created_at);
```

### 3. Google Cloud Setup

Enable required APIs in Google Cloud Console:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project
3. Go to "APIs & Services" → "Library"
4. Enable these APIs:
   - **Gmail API**
   - **Google Calendar API**

### 4. Code Deployment

Push your code to GitHub (or your Git provider):

```bash
cd e:/Peppi/moltbot-render
git add .
git commit -m "Fix OpenClaw configuration and add comprehensive setup"
git push origin main
```

---

## Deployment to Render

### Method 1: Automatic (via render.yaml)

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click "New" → "Blueprint"
3. Connect your GitHub repository
4. Render will automatically detect [render.yaml](render.yaml)
5. Review services (2 services will be created)
6. Click "Apply"

### Method 2: Manual

If automatic deployment fails:

#### Deploy OpenClaw Gateway:
1. Click "New" → "Web Service"
2. Connect repository
3. Settings:
   - **Name:** `openclaw-gateway`
   - **Root Directory:** `moltbot-gateway`
   - **Build Command:** `npm install && npm install -g openclaw@latest`
   - **Start Command:** `npm start`
   - **Plan:** Starter ($7/month) or Pro ($25/month)
   - **Region:** Oregon (US-West)
4. Add environment variables (see ENVIRONMENT_SETUP.md)
5. Click "Create Web Service"

#### Deploy FastAPI Wrapper:
1. Click "New" → "Web Service"
2. Connect repository
3. Settings:
   - **Name:** `moltbot-fastapi`
   - **Root Directory:** `fastapi-wrapper`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Plan:** Starter or Pro
   - **Region:** Oregon (US-West)
4. Add environment variables
5. Click "Create Web Service"

---

## Post-Deployment Verification

### 1. Check Service Health

Wait 5-10 minutes for services to start, then test:

#### OpenClaw Gateway Health
```bash
curl https://openclaw-gateway-dg3y.onrender.com/health
```

**Expected:**
```json
{
  "status": "online",
  "service": "openclaw-gateway",
  "openclaw_ready": true
}
```

**If `openclaw_ready: false`:**
- Check logs in Render dashboard
- Look for "OpenClaw not found" or "GEMINI_API_KEY not set"

#### FastAPI Health
```bash
curl https://moltbot-fastapi.onrender.com/health
```

**Expected:**
```json
{
  "code": 200,
  "message": "Service health check completed",
  "data": {
    "status": "healthy",
    "openclaw_gateway": "online",
    "redis": true,
    "supabase": true,
    "active_sessions": 0
  }
}
```

**If any service shows offline/false:**
- Check environment variables
- Check service logs
- Verify database/Redis credentials

### 2. Check Diagnostics

```bash
curl https://openclaw-gateway-dg3y.onrender.com/diagnose
```

**Look for:**
```json
{
  "status": "diagnostic",
  "env": {
    "GEMINI_API_KEY": "Set (starts with AIza...)",
    "BRAVE_API_KEY": "Set (starts with BSA...)",
    "NODE_VERSION": "v22.x.x",
    ...
  },
  "openclaw": {
    "installed": true,
    "version": "2026.2.x",
    "error": null
  }
}
```

### 3. Check Available Skills

```bash
curl https://openclaw-gateway-dg3y.onrender.com/skills
```

**Expected:**
```json
{
  "skills": [
    {
      "name": "caldav-calendar",
      "description": "Manage calendar events",
      "actions": ["create", "read", "update", "delete"]
    },
    {
      "name": "gmail",
      "description": "Read and send emails",
      "actions": ["read", "send", "draft", "search"]
    },
    ...
  ]
}
```

---

## Testing MVP Features

### Prerequisites

1. Services are healthy
2. User has completed Google OAuth flow
3. You have a test user_id

### Test 1: Web Search

**Request:**
```bash
curl -X POST https://moltbot-fastapi.onrender.com/api/v1/execute-action \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "123",
    "message": "Search for latest AI news"
  }'
```

**Expected Response:**
```json
{
  "code": 200,
  "message": "Action executed successfully",
  "data": {
    "session_id": "sess_xxxxx",
    "response": "I found the latest AI news...",
    "action_performed": "web_search",
    "details": {...}
  }
}
```

**What to check:**
- Response contains search results
- `action_performed` is "web_search" or similar
- No errors in logs

---

### Test 2: Google OAuth Flow

**Step 1: Initialize OAuth**
```bash
curl "https://moltbot-fastapi.onrender.com/api/v1/oauth/google/init?user_id=123"
```

**Expected:** JSON with `auth_url`

**Step 2: Visit auth_url in browser**
- User will be redirected to Google
- User grants permissions
- User is redirected back with success message

**Step 3: Check OAuth status**
```bash
curl https://moltbot-fastapi.onrender.com/api/v1/oauth/google/status/123
```

**Expected:**
```json
{
  "code": 200,
  "data": {
    "connected": true,
    "user_id": "123",
    "expires_at": "2026-02-06T12:00:00Z",
    "needs_refresh": false
  }
}
```

---

### Test 3: Calendar - Read Events

**Request:**
```bash
curl -X POST https://moltbot-fastapi.onrender.com/api/v1/execute-action \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "123",
    "message": "What is on my calendar today?"
  }'
```

**Expected Response:**
```json
{
  "code": 200,
  "data": {
    "response": "You have 2 events today: 1) Meeting at 10am...",
    "action_performed": "calendar_read"
  }
}
```

---

### Test 4: Calendar - Create Event

**Request:**
```bash
curl -X POST https://moltbot-fastapi.onrender.com/api/v1/execute-action \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "123",
    "message": "Schedule a meeting tomorrow at 2pm with John about project update"
  }'
```

**Expected Response:**
```json
{
  "code": 200,
  "data": {
    "response": "I have scheduled a meeting for February 6, 2026 at 2:00 PM...",
    "action_performed": "calendar_create"
  }
}
```

**Verify:** Check user's Google Calendar for new event

---

### Test 5: Gmail - Read Emails

**Request:**
```bash
curl -X POST https://moltbot-fastapi.onrender.com/api/v1/execute-action \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "123",
    "message": "Check my emails from today"
  }'
```

**Expected Response:**
```json
{
  "code": 200,
  "data": {
    "response": "You have 5 emails from today. The most recent is from...",
    "action_performed": "gmail_read"
  }
}
```

---

### Test 6: Gmail - Send Email

**Request:**
```bash
curl -X POST https://moltbot-fastapi.onrender.com/api/v1/execute-action \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "123",
    "message": "Send an email to john@example.com saying: Hi John, just checking in!"
  }'
```

**Expected Response:**
```json
{
  "code": 200,
  "data": {
    "response": "I have sent the email to john@example.com",
    "action_performed": "gmail_send"
  }
}
```

**Verify:** Check sent emails in Gmail

---

### Test 7: Reminders/Tasks

**Request:**
```bash
curl -X POST https://moltbot-fastapi.onrender.com/api/v1/execute-action \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "123",
    "message": "Remind me to call Sarah at 5pm today"
  }'
```

**Expected Response:**
```json
{
  "code": 200,
  "data": {
    "response": "I will remind you to call Sarah at 5:00 PM today",
    "action_performed": "reminder_create"
  }
}
```

---

### Test 8: Memory - Save Information

**Request:**
```bash
curl -X POST https://moltbot-fastapi.onrender.com/api/v1/execute-action \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "123",
    "message": "Remember that my favorite color is blue"
  }'
```

**Expected Response:**
```json
{
  "code": 200,
  "data": {
    "response": "I will remember that your favorite color is blue",
    "action_performed": "memory_store"
  }
}
```

---

### Test 9: Memory - Recall Information

**Request:**
```bash
curl -X POST https://moltbot-fastapi.onrender.com/api/v1/execute-action \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "123",
    "message": "What is my favorite color?"
  }'
```

**Expected Response:**
```json
{
  "code": 200,
  "data": {
    "response": "Your favorite color is blue",
    "action_performed": "memory_recall"
  }
}
```

---

### Test 10: Task Management

**Request:**
```bash
curl -X POST https://moltbot-fastapi.onrender.com/api/v1/execute-action \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "123",
    "message": "Add task: Buy groceries tomorrow"
  }'
```

**Expected Response:**
```json
{
  "code": 200,
  "data": {
    "response": "I have added the task: Buy groceries tomorrow",
    "action_performed": "task_create"
  }
}
```

---

## Troubleshooting

### Issue: OpenClaw not ready

**Symptoms:**
```json
{"openclaw_ready": false}
```

**Check:**
1. Render logs for OpenClaw Gateway
2. Look for installation errors
3. Verify `GEMINI_API_KEY` is set

**Solution:**
- Redeploy with correct environment variables
- Check build logs for npm install errors

---

### Issue: Skills not working

**Symptoms:**
- Agent responds but doesn't use skills
- Generic chat responses instead of actions

**Check:**
1. OpenClaw config file created at `/root/.openclaw/openclaw.json`
2. Skills are enabled in config
3. Required environment variables set

**Solution:**
- Check Render logs for config creation
- Manually verify config file via Render shell
- Ensure `HOME` environment variable is set

---

### Issue: Google OAuth not working

**Symptoms:**
- OAuth flow fails
- "Redirect URI mismatch" error

**Check:**
1. `GOOGLE_REDIRECT_URI` matches Google Cloud Console
2. Gmail API and Calendar API are enabled
3. OAuth consent screen is configured

**Solution:**
- Update redirect URI in Google Cloud Console
- Enable APIs
- Publish OAuth app (not in test mode)

---

### Issue: Web search returns poor results

**Symptoms:**
- Search works but results are generic
- No specific/recent information

**Check:**
1. `BRAVE_API_KEY` is set
2. Brave API has available quota

**Solution:**
- Set Brave API key
- Check usage at Brave dashboard
- Upgrade plan if needed

---

### Issue: Calendar/Gmail token expired

**Symptoms:**
- Works initially but fails after 1 hour
- "Invalid credentials" error

**Check:**
1. Token refresh logic in credential_manager.py
2. Refresh token is stored
3. Token expiration time

**Solution:**
- User needs to re-authenticate
- Check if refresh token was saved
- Verify OAuth scopes include "offline" access

---

## Monitoring & Maintenance

### Daily Checks

1. **Health endpoints** - Ensure all services are online
2. **Error rate** - Check Render logs for errors
3. **API quotas** - Monitor Google AI, Brave Search usage

### Weekly Tasks

1. **Review audit logs** - Check Supabase for unusual activity
2. **Check active sessions** - Monitor Redis memory usage
3. **Update dependencies** - Check for OpenClaw updates

### Monthly Tasks

1. **Rotate API keys** - For security
2. **Review costs** - Render, Google Cloud, Brave, Upstash
3. **Backup database** - Export Supabase data

---

## Performance Optimization

### Reduce Latency

1. Use Render paid plan (better performance)
2. Keep services in same region (Oregon)
3. Optimize conversation history (limit to 20 messages)

### Reduce Costs

1. Use Brave free tier (2000 req/month)
2. Optimize session TTL (reduce from 1 hour to 30 min)
3. Clean up old sessions regularly

### Scale for Production

1. Upgrade to Render Pro plan
2. Add Redis persistence (Upstash Pro)
3. Enable Supabase connection pooling
4. Add rate limiting per user

---

## Support & Resources

- **OpenClaw Issues:** https://github.com/openclaw/openclaw/issues
- **Render Support:** https://render.com/docs/support
- **Google Cloud Status:** https://status.cloud.google.com/
- **Project Issues:** Check logs first, then contact support

---

## Next Steps

After successful deployment and testing:

1. **Integrate with Peppi** - Configure Peppi Laravel to call FastAPI
2. **Add more skills** - Explore ClawHub for additional capabilities
3. **Improve prompts** - Optimize system prompts for better responses
4. **Add monitoring** - Set up Sentry or similar for error tracking
5. **User onboarding** - Create flow for users to connect Google accounts

---

## Success Criteria

Your deployment is successful when:

- [x] Health checks return 200 OK
- [x] Web search works and returns relevant results
- [x] Users can connect Google accounts via OAuth
- [x] Calendar read/write works
- [x] Gmail read/send works
- [x] Reminders/tasks work
- [x] Memory persists across sessions
- [x] No errors in Render logs
- [x] All MVP features tested and working

**Congratulations! Your Moltbot is live!** 🎉
