# MVP Features Implementation Plan - ClawHub Skills

## 🎯 Your MVP Features
1. ✅ Web search
2. ✅ Calendar scheduling (read/write)
3. ✅ Gmail (read/send)
4. ✅ Reminders
5. ✅ Tasks
6. ✅ Memory/context persistence

---

## 📊 Available Solutions (Skills vs Built-in Tools)

### **Feature 1: Web Search**
**Status:** ✅ **BUILT-IN TOOL** (No skill needed!)

**What it is:**
- OpenClaw has native `web_search` and `web_fetch` tools
- Already available in your deployment (confirmed in earlier test)
- Works with Google Gemini (your current model)

**Configuration:**
- ✅ **ZERO CONFIGURATION** - Already working!
- No API keys needed (uses your Gemini API access)
- Agent can call it automatically when user asks: "Search for X"

**How it works:**
```
User: "What's the weather in Mumbai?"
  ↓
OpenClaw calls: web_search("weather Mumbai today")
  ↓
Returns: "It's 28°C and sunny in Mumbai..."
```

**Installation:** ✅ None needed - already available

---

### **Feature 2 & 3: Calendar + Gmail**
**Solution:** 🎯 **GOG Skill** (Most Popular - 468 installs)

**What it is:**
- Single skill that handles Gmail, Calendar, Drive, Docs, Sheets, Contacts
- CLI tool that OpenClaw calls via `exec` command
- Most widely used Google integration (90% of users)

**Installation Command:**
```bash
npx clawhub@latest install gog
```

**Setup Requirements:**
1. Install gog CLI on Render server
2. Configure OAuth credentials (you already have these!)
3. Run: `gog auth credentials /path/to/client_secret.json`
4. Add account: `gog auth add user@email.com --services gmail,calendar`

**How it works:**
```
User: "What meetings do I have today?"
  ↓
OpenClaw calls: gog calendar events --account user@gmail.com --from 2026-02-06 --to 2026-02-06
  ↓
Returns: "You have 2 meetings: 10am with John, 3pm standup"

User: "Send email to john@example.com saying I'm running late"
  ↓
OpenClaw calls: gog gmail send --to john@example.com --subject "Running late" --body "..."
  ↓
Returns: "Email sent!"
```

**Pros:**
- ✅ Handles both Calendar AND Gmail in one skill
- ✅ Most battle-tested (468 installs)
- ✅ Works with your existing OAuth
- ✅ Community support & documentation

**Status:** 🟡 Needs installation

---

### **Feature 4: Reminders**
**Options Available:**

#### **Option A: apple-reminders** (130 installs)
- **Platform:** macOS only ❌
- **Not suitable for Render/Linux**

#### **Option B: Use Calendar Events as Reminders**
- **Solution:** Use GOG skill's Calendar feature
- **Method:** Create calendar events with notifications
- **Pros:** ✅ Cross-platform, already included in GOG
- **Example:**
  ```
  User: "Remind me to call John at 3pm tomorrow"
    ↓
  OpenClaw calls: gog calendar events create --summary "Call John" --start tomorrow-3pm --remind 15min
  ```

#### **Option C: Custom Reminder Skill**
- **Solution:** Create simple reminder storage in Supabase
- **Pros:** ✅ Custom implementation, persistent across platforms
- **Status:** Would need custom development

**Recommendation:** 🎯 **Option B** - Use GOG Calendar with notifications

---

### **Feature 5: Tasks**
**Options Available:**

#### **Option A: things-mac** (105 installs)
- **Platform:** macOS only ❌
- **Not suitable for Render/Linux**

#### **Option B: clawlist** (Community favorite)
- **Purpose:** "MUST use for any multi-step project, long-running task"
- **Installation:**
  ```bash
  npx clawhub@latest install clawlist
  ```
- **Features:**
  - Multi-step project management
  - Long-running task tracking
  - Infinite monitoring workflows

#### **Option C: Use Google Tasks via GOG**
- **Check if GOG supports Google Tasks API**
- **If not:** Use Calendar events as tasks

#### **Option D: task-status skill**
- **Purpose:** Send short status descriptions for long-running tasks
- **Installation:**
  ```bash
  npx clawhub@latest install task-status
  ```

**Recommendation:** 🎯 **Option B (clawlist)** for task management + **Option D (task-status)** for status updates

---

### **Feature 6: Memory/Context Persistence**
**Options Available:**

#### **Option A: agentmemory** (Most Popular)
- **Features:**
  - End-to-end encrypted cloud memory
  - 100GB free storage
  - Persistent across sessions
- **Installation:**
  ```bash
  npx clawhub@latest install agentmemory
  ```
- **Pros:**
  - ✅ Cloud-based (works on Render)
  - ✅ Large storage
  - ✅ Encrypted

#### **Option B: chromadb-memory**
- **Features:**
  - Long-term memory via ChromaDB
  - Uses local Ollama embeddings
  - Vector search
- **Installation:**
  ```bash
  npx clawhub@latest install chromadb-memory
  ```
- **Pros:**
  - ✅ Self-hosted
  - ✅ Vector search capabilities

#### **Option C: anterior-cingulate-memory**
- **Features:**
  - Conflict detection
  - Error monitoring
- **Specialized use case**

#### **Option D: Built-in memory_search + memory_get**
- **Status:** ✅ Already available as built-in tools
- **Check:** Verify if persistent or session-only

**Recommendation:** 🎯 **Option A (agentmemory)** for production + Use built-in memory tools

---

## 🔧 Implementation Plan

### **Phase 1: Install Core Skills (Day 1)**

1. **GOG Skill** (Calendar + Gmail)
   ```bash
   # On Render server
   cd /opt/render/project/src/moltbot-gateway
   npx clawhub@latest install gog
   ```

2. **Configure GOG OAuth**
   ```bash
   # Upload Google OAuth credentials
   gog auth credentials /path/to/client_secret.json

   # Add user account (use service account email)
   gog auth add moltbot@yourservice.com --services gmail,calendar,drive
   ```

3. **Test GOG**
   ```bash
   # Test calendar
   gog calendar events --account moltbot@yourservice.com

   # Test Gmail
   gog gmail messages list --account moltbot@yourservice.com --max 5
   ```

### **Phase 2: Install Task & Memory Skills (Day 2)**

1. **clawlist** (Task Management)
   ```bash
   npx clawhub@latest install clawlist
   ```

2. **agentmemory** (Persistent Memory)
   ```bash
   npx clawhub@latest install agentmemory
   ```

3. **task-status** (Task Status Updates)
   ```bash
   npx clawhub@latest install task-status
   ```

### **Phase 3: Verify Built-in Tools (Day 2)**

1. **Confirm web_search works**
   - Test: "Search for latest AI news"
   - Already verified in earlier tests ✅

2. **Confirm memory tools work**
   - Test: "Remember that John's birthday is March 15"
   - Test: "What did I tell you about John?"

### **Phase 4: Integration Testing (Day 3)**

Test conversational scenarios:

1. **Calendar Test:**
   ```
   User: "What do I have scheduled for today?"
   Expected: GOG skill fetches calendar events
   ```

2. **Gmail Test:**
   ```
   User: "Send an email to john@example.com"
   Expected: GOG skill composes and sends email
   ```

3. **Task Test:**
   ```
   User: "Add a task to follow up with client tomorrow"
   Expected: clawlist creates task
   ```

4. **Memory Test:**
   ```
   User: "Remember that my favorite color is blue"
   Expected: agentmemory stores this
   ```

5. **Web Search Test:**
   ```
   User: "What's the latest news on AI?"
   Expected: Built-in web_search tool fetches results
   ```

---

## 📦 Final Skill List for Installation

| Feature | Solution | Installation Command | Priority |
|---------|----------|---------------------|----------|
| **Web Search** | Built-in `web_search` | ✅ Already available | P0 |
| **Calendar** | GOG skill | `npx clawhub@latest install gog` | P0 |
| **Gmail** | GOG skill | ✅ Same as Calendar | P0 |
| **Reminders** | GOG Calendar + notifications | ✅ Included in GOG | P1 |
| **Tasks** | clawlist | `npx clawhub@latest install clawlist` | P1 |
| **Memory** | agentmemory | `npx clawhub@latest install agentmemory` | P1 |
| **Task Status** | task-status | `npx clawhub@latest install task-status` | P2 |

---

## 🚀 Deployment Steps for Render

### **Update Render Build Command:**

```yaml
# render.yaml - openclaw-gateway service
buildCommand: |
  npm install &&
  npm install -g openclaw@latest &&
  npm install -g clawhub@latest &&
  clawhub install gog &&
  clawhub install clawlist &&
  clawhub install agentmemory &&
  clawhub install task-status
```

### **Add Environment Variables:**

```yaml
# For GOG authentication
- key: GOG_GOOGLE_CREDENTIALS_PATH
  sync: false
- key: GOG_ACCOUNT_EMAIL
  value: moltbot@yourservice.com
```

### **Configure OAuth Tokens:**

Since you already have OAuth tokens in Supabase, create a script to:
1. Fetch tokens from Supabase
2. Configure gog with those tokens
3. Run at startup

---

## ✅ Benefits of This Approach

1. ✅ **Battle-tested:** Using skills with 130-468 installs each
2. ✅ **Conversational:** Users ask in natural language
3. ✅ **Dynamic:** OpenClaw chooses which skill to use
4. ✅ **Scalable:** Easy to add more skills later
5. ✅ **Community support:** Well-documented solutions
6. ✅ **Zero custom code:** No need for custom integrations

---

## 🎯 What Users Can Now Do

**Natural Language Commands:**
- "What meetings do I have today?"
- "Send an email to john@example.com"
- "Search for latest AI news"
- "Remind me to call Sarah at 3pm"
- "Add a task to review the proposal"
- "Remember that John prefers morning meetings"

**OpenClaw handles everything dynamically!**

---

## 📚 Sources

- [GOG Skill - 468 installs](https://skills.sh/openclaw/openclaw/gog)
- [ClawHub Skills Registry](https://clawhub.ai/)
- [Awesome OpenClaw Skills](https://github.com/VoltAgent/awesome-openclaw-skills)
- [OpenClaw Web Search Guide](https://help.apiyi.com/en/openclaw-web-search-configuration-guide-en.html)
- [OpenClaw Skills Installation Guide 2026](https://gist.github.com/ashio-git/ab99c4b808b25adaad156fb53349d81b)

---

**Ready to implement? Let's start with Phase 1!**
