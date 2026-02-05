# Quick Start Guide - Moltbot with OpenClaw Built-in Search

## 🚀 Deployment in 3 Steps

### Step 1: Set Required Environment Variables (5 minutes)

In **Render Dashboard** → **openclaw-gateway** service → **Environment**:

**REQUIRED:**
```bash
GEMINI_API_KEY=AIzaSy...  # Get from: https://makersuite.google.com/app/apikey
GOOGLE_API_KEY=AIzaSy...  # Same value as above
```

**That's it!** No Brave API needed - using OpenClaw's built-in web search.

### Step 2: Deploy (2 minutes)

```bash
git add .
git commit -m "Use OpenClaw built-in search"
git push origin main
```

Render will auto-deploy.

### Step 3: Verify (3 minutes)

Wait 5-10 minutes, then test:

```bash
# Check health
curl https://openclaw-gateway-dg3y.onrender.com/health

# Should show: openclaw_ready: true
```

## ✅ What's Configured

All MVP features work with **OpenClaw built-in search**:

- ✅ **Web Search** - Native OpenClaw search (no external API needed)
- ✅ **Gmail** - Via Google OAuth
- ✅ **Calendar** - Via Google OAuth
- ✅ **Reminders** - Built-in
- ✅ **Memory** - Persistent context
- ✅ **Tasks** - Task management

## 📋 Test Web Search

```bash
curl -X POST https://moltbot-fastapi.onrender.com/api/v1/execute-action \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test123", "message": "Search for OpenClaw AI agent"}'
```

**Expected:** Search results from OpenClaw's built-in search.

## 📖 Full Documentation

- **[IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md)** - Complete changes summary
- **[ENVIRONMENT_SETUP.md](ENVIRONMENT_SETUP.md)** - All environment variables
- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - Full deployment & testing

## 🎯 Key Changes

1. **Removed Brave API dependency** - Using OpenClaw built-in search
2. **Simplified configuration** - Only GEMINI_API_KEY required
3. **Native search** - OpenClaw handles web search internally

## 🔧 Configuration Summary

**server.js** now creates:
```json
{
  "skills": {
    "entries": {
      "web_search": {
        "enabled": true,
        "config": {
          "provider": "builtin",
          "maxResults": 5
        }
      }
    }
  }
}
```

**No external search API required!**

## ✨ Ready to Go!

Your Moltbot is configured to use OpenClaw's native search capabilities. Deploy and test! 🚀
