# Web Search & Multi-Tenant Memory Solutions

## 🔍 Problem 1: Built-in web_search Didn't Work

**Issue:** Earlier test showed: "web_search tool requires Brave API key"

The built-in `web_search` only works with Anthropic/Claude API. Since you're using **Google Gemini**, it's not available.

---

## ✅ Solution: ClawHub Web Search Skills

### **Option 1: exa-web-search-free** (RECOMMENDED)
**From awesome-openclaw-skills repository**

- **What:** Free AI search via Exa API
- **Cost:** FREE tier available
- **Installation:**
  ```bash
  npx clawhub@latest install exa-web-search-free
  ```
- **Pros:**
  - ✅ Free tier
  - ✅ AI-optimized search results
  - ✅ Good quality results
- **Cons:**
  - ⚠️ Requires Exa API key (but free tier is generous)

**Setup:**
1. Get free API key: https://exa.ai
2. Install skill: `npx clawhub@latest install exa-web-search-free`
3. Configure API key in OpenClaw

---

### **Option 2: Brave Search API**
**Official OpenClaw recommendation**

- **Free tier:** 2,000 requests/month
- **Installation:** Configure via OpenClaw settings
- **API key:** Get from https://api-dashboard.search.brave.com
- **Pros:**
  - ✅ 2,000 free searches/month
  - ✅ Independent index (privacy-focused)
  - ✅ Well-documented
  - ✅ Officially recommended

**Setup in server.js:**
```javascript
// Add to environment variables
extraEnv.BRAVE_API_KEY = process.env.BRAVE_API_KEY;
```

**Add to render.yaml:**
```yaml
- key: BRAVE_API_KEY
  sync: false  # Set in Render dashboard
```

---

### **Option 3: Tavily MCP**
**AI-optimized for agents**

- **Free tier:** 1,000 requests/month
- **Best for:** Deep research, RAG applications
- **Installation:**
  ```bash
  npx @tavily/mcp-server
  ```
- **Pros:**
  - ✅ Specifically designed for AI agents
  - ✅ Automatic content extraction
  - ✅ Good for research queries
- **Cons:**
  - ⚠️ Only 1,000 requests/month (less than Brave)

---

### **Option 4: DuckDuckGo (UNLIMITED FREE)**
**Best for unlimited searches**

- **Cost:** FREE, UNLIMITED
- **Quality:** Good for general queries
- **Installation:** Via OneSearch MCP
  ```bash
  # OneSearch MCP supports multiple backends including DuckDuckGo
  ```
- **Pros:**
  - ✅ FREE
  - ✅ UNLIMITED
  - ✅ No API key needed
  - ✅ Privacy-focused
- **Cons:**
  - ⚠️ Results quality not as good as Exa/Brave

---

### **🎯 RECOMMENDATION:**

For your use case, I recommend **Brave Search API**:

**Why?**
1. ✅ 2,000 free searches/month (enough for MVP)
2. ✅ Officially supported by OpenClaw
3. ✅ Easy setup (just add API key)
4. ✅ Good quality results
5. ✅ No skill installation needed (built-in support)

**Backup:** Use DuckDuckGo for unlimited searches if you exceed Brave's limit.

---

## 👥 Problem 2: Multi-Tenant Memory

**Critical Requirement:** Each user needs isolated memory (User A can't see User B's memories)

---

## ✅ Solution: OpenClaw Has Built-in Multi-Tenant Support!

**Good news:** OpenClaw natively supports multi-tenant isolation through **sessions**!

### **How OpenClaw Handles Multi-Tenant:**

1. **Session Isolation:**
   - Each user gets a unique `session_id`
   - User A's session is completely separate from User B's
   - No cross-talk unless explicitly enabled

2. **Per-User Context:**
   - Each session has its own conversation history
   - Memory is tied to `session_id`
   - Agent tracks which user is making the request

3. **DM Scope Isolation:**
   - `dmScope` parameter isolates per channel peer
   - Each WhatsApp user gets their own isolated context
   - Memory stays separate for each user

**From the docs:**
> "OpenClaw handles per-user isolation through dmScope, which isolates sessions per channel peer, so each user who DMs the bot gets their own isolated conversation context."

---

## 🧠 Memory Skills - Multi-Tenant Analysis

### **Option 1: Built-in memory_search + memory_get** (RECOMMENDED)
**Native OpenClaw tools**

- **Multi-tenant:** ✅ **YES** - Uses session isolation
- **How it works:**
  - Memory is stored per `session_id`
  - Each user automatically gets their own session
  - No configuration needed
- **Pros:**
  - ✅ Built-in (no installation)
  - ✅ Native multi-tenant support
  - ✅ Session-based isolation
  - ✅ Zero configuration
- **Cons:**
  - ⚠️ May not persist across server restarts (check implementation)

**Usage:**
```javascript
// In your server.js when calling OpenClaw
const sessionId = `user_${user_id}`;  // Unique per user
args.push('--session-id', sessionId);
```

OpenClaw automatically isolates memory per session!

---

### **Option 2: agentmemory** (Cloud-based)
**100GB free encrypted cloud storage**

- **Multi-tenant:** ⚠️ **NEEDS VERIFICATION**
- **How to make it multi-tenant:**
  - Store with user-specific namespace
  - Use `user_id` as prefix for all memories
  - Example: `memory.store(key=f"user_{user_id}:preference", value="...")`
- **Pros:**
  - ✅ 100GB free storage
  - ✅ Encrypted
  - ✅ Persistent across restarts
  - ✅ Cloud-based
- **Cons:**
  - ⚠️ Need to ensure proper user isolation in implementation
  - ⚠️ External dependency

**Installation:**
```bash
npx clawhub@latest install agentmemory
```

**Multi-tenant implementation:**
```javascript
// When calling OpenClaw, pass user context
const message = `[User: ${user_id}] ${user_message}`;
// agentmemory should use this context for storage isolation
```

---

### **Option 3: chromadb-memory** (Self-hosted)
**Vector-based memory with embeddings**

- **Multi-tenant:** ⚠️ **NEEDS CONFIGURATION**
- **How to make it multi-tenant:**
  - Create separate ChromaDB collections per user
  - Use `user_id` as collection name
  - Requires custom configuration
- **Pros:**
  - ✅ Self-hosted (full control)
  - ✅ Vector search (semantic memory)
  - ✅ Powerful for RAG
- **Cons:**
  - ⚠️ More complex setup
  - ⚠️ Requires custom multi-tenant implementation
  - ⚠️ Higher resource usage

---

## 🎯 FINAL RECOMMENDATIONS

### **For Web Search:**
Use **Brave Search API**:
```yaml
# Add to render.yaml
- key: BRAVE_API_KEY
  sync: false
```

Get free API key: https://api-dashboard.search.brave.com

**Backup:** Keep DuckDuckGo for unlimited searches

---

### **For Multi-Tenant Memory:**
Use **Built-in memory tools** with **session-based isolation**:

**Implementation in your FastAPI:**
```python
# In your execute-action endpoint
session_id = f"user_{user_id}"  # Unique per user

# Pass to OpenClaw gateway
response = requests.post(
    f"{MOLTBOT_GATEWAY_URL}/execute",
    json={
        "session_id": session_id,  # This ensures memory isolation
        "message": user_message
    }
)
```

**In your server.js:**
```javascript
// Already implemented - verify session_id is per-user
const sessionId = request.session_id || `user_${user_id}`;
args.push('--session-id', sessionId);
```

OpenClaw's native session isolation handles multi-tenant memory automatically!

**Optional:** Add `agentmemory` for persistent cloud storage (but ensure you namespace by user_id)

---

## 📋 Updated Implementation Plan

### **Phase 1: Add Web Search**
```bash
# Option A: Brave Search (Recommended)
# 1. Get API key from https://api-dashboard.search.brave.com
# 2. Add to Render dashboard as BRAVE_API_KEY
# 3. Update render.yaml

# Option B: Exa (Alternative)
npx clawhub@latest install exa-web-search-free
# Get API key from https://exa.ai
```

### **Phase 2: Verify Multi-Tenant Session Isolation**
```javascript
// In server.js - ensure session_id is unique per user
function executeOpenClaw(sessionId, message, context, credentials) {
  // sessionId should be like: "user_123", "user_456", etc.
  args.push('--session-id', sessionId);
  // This ensures each user has isolated memory!
}
```

### **Phase 3: Test Multi-Tenant Memory**
```
User A: "Remember my favorite color is blue"
User B: "Remember my favorite color is red"

User A: "What's my favorite color?"
Expected: "Blue" (not "Red")

User B: "What's my favorite color?"
Expected: "Red" (not "Blue")
```

---

## ✅ Summary

| Feature | Solution | Multi-Tenant? | Free? |
|---------|----------|---------------|-------|
| **Web Search** | Brave Search API | N/A | ✅ 2000/month |
| **Memory** | Built-in memory tools + sessions | ✅ YES | ✅ YES |
| **Backup Search** | DuckDuckGo | N/A | ✅ Unlimited |
| **Cloud Memory** | agentmemory (optional) | ⚠️ With namespacing | ✅ 100GB free |

---

## 🚀 Next Steps

1. ✅ Get Brave Search API key
2. ✅ Add to Render environment variables
3. ✅ Verify session-based isolation in server.js
4. ✅ Test multi-tenant memory with 2 users
5. ✅ Install GOG skill for Calendar/Gmail

**Your multi-tenant architecture is already supported by OpenClaw's native session system!**

---

**Sources:**
- [OpenClaw Web Search Configuration Guide](https://help.apiyi.com/en/openclaw-web-search-configuration-guide-en.html)
- [OpenClaw Multi-Agent Routing](https://docs.openclaw.ai/concepts/multi-agent)
- [OpenClaw Multi-Tenant Architecture](https://zenvanriel.nl/ai-engineer-blog/openclaw-multi-agent-orchestration-guide/)
- [Awesome OpenClaw Skills](https://github.com/VoltAgent/awesome-openclaw-skills)
