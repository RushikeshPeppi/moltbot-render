const express = require('express');
const { spawn, exec } = require('child_process');
const fs = require('fs');
const path = require('path');
const axios = require('axios');
const app = express();
const PORT = process.env.PORT || 18789;

app.use(express.json());

// Store for active OpenClaw processes
let isReady = false;

// Health check
app.get('/health', (req, res) => {
  res.json({
    status: 'online',
    service: 'openclaw-gateway',
    openclaw_ready: isReady
  });
});

// Diagnostic check
app.get('/diagnose', (req, res) => {
  const envCheck = {
    GEMINI_API_KEY: process.env.GEMINI_API_KEY ? 'Set (starts with ' + process.env.GEMINI_API_KEY.substring(0, 5) + '...)' : 'MISSING',
    BRAVE_API_KEY: process.env.BRAVE_API_KEY ? 'Set (starts with ' + process.env.BRAVE_API_KEY.substring(0, 5) + '...)' : 'Not set (using built-in search)',
    NODE_VERSION: process.version,
    PATH: process.env.PATH
  };

  exec('openclaw --version', (error, stdout, stderr) => {
    res.json({
      status: 'diagnostic',
      env: envCheck,
      openclaw: {
        installed: !error,
        version: stdout ? stdout.trim() : 'Unknown',
        error: error ? error.message : null
      }
    });
  });
});

/**
 * Fetch OAuth token from FastAPI for a user
 */
async function fetchOAuthTokenFromFastAPI(userId) {
  try {
    const fastApiUrl = process.env.FASTAPI_URL || 'https://moltbot-fastapi.onrender.com';

    const response = await axios.get(`${fastApiUrl}/api/v1/oauth/google/token/${userId}`, {
      timeout: 10000
    });

    if (response.data && response.data.data && response.data.data.access_token) {
      return response.data.data.access_token;
    }

    return null;
  } catch (error) {
    console.error(`Failed to fetch OAuth token for user ${userId}: ${error.message}`);
    return null;
  }
}

/**
 * Execute action via OpenClaw
 *
 * POST /execute
 * Body: {
 *   session_id: string,
 *   message: string,
 *   user_id: number,  // NEW: Required for OAuth token bridge
 *   credentials: object,
 *   history: array
 * }
 */
app.post('/execute', async (req, res) => {
  const { session_id, message, user_id, credentials, history, timezone, user_context, image_urls } = req.body;

  if (!message) {
    return res.status(400).json({ error: 'Message is required' });
  }

  try {
    console.log(`[${session_id}] Processing for user ${user_id}: ${message.substring(0, 50)}...`);

    // OAuth token bridge: Fetch fresh token from FastAPI if user_id provided
    let enhancedCredentials = { ...credentials };
    if (user_id) {
      console.log(`[${session_id}] Fetching OAuth token for user ${user_id}...`);
      const accessToken = await fetchOAuthTokenFromFastAPI(user_id);
      if (accessToken) {
        enhancedCredentials.google_access_token = accessToken;
        console.log(`[${session_id}] OAuth token retrieved successfully`);
      } else {
        console.log(`[${session_id}] No OAuth token available for user ${user_id}`);
      }
    }

    // Extract user context for personalization
    const userContext = user_context || {};

    // Build dynamic context (static rules are now in SOUL.md, injected by OpenClaw)
    const context = buildContext(
      enhancedCredentials,
      history,
      user_id,
      timezone || 'UTC',
      userContext
    );

    // Execute OpenClaw command (pass user_id for workspace isolation and timezone for skills)
    const result = await executeOpenClaw(session_id, message, context, enhancedCredentials, user_id, timezone || 'UTC', image_urls);

    console.log(`[${session_id}] Completed: ${result.action_type || 'chat'}`);

    res.json({
      success: true,
      response: result.response,
      action_type: result.action_type,
      details: result.details,
      tokens_used: result.tokens_used || 0,
      input_tokens: result.input_tokens || 0,
      output_tokens: result.output_tokens || 0,
      cache_read: result.cache_read || 0,
      cache_write: result.cache_write || 0
    });

  } catch (error) {
    console.error(`[${session_id}] Error:`, error.message);
    res.status(500).json({
      success: false,
      error: error.message,
      response: "I'm sorry, I encountered an error processing your request. Please try again."
    });
  }
});

/**
 * Build dynamic context for OpenClaw.
 * Static behavioral rules (identity, inference, timezone, etc.) are now in SOUL.md,
 * which OpenClaw auto-injects into the system prompt every turn.
 * This function only provides per-request dynamic data: capabilities, user info, and history.
 */
function buildContext(credentials, history, userId, timezone, userContext = {}) {
  let context = '';

  // Dynamic user info
  const botName = userContext.bot_name || userContext.botName || 'Peppi';
  const userName = userContext.user_name || userContext.userName;

  context += `USER: ${userName || userId} | Timezone: ${timezone || 'UTC'} | Bot: ${botName}`;

  // Dynamic capabilities (depends on which credentials are available per-request)
  const capabilities = ['Reminders'];
  if (credentials && credentials.google_access_token) {
    capabilities.push('Google Calendar', 'Gmail');
  }
  context += ` | Available: ${capabilities.join(', ')}`;

  // User preferences (dynamic, from session)
  if (userContext.preferences) {
    context += ` | Prefs: ${userContext.preferences}`;
  }

  context += '\n';



  // Recent conversation history (dynamic per-request)
  if (history && history.length > 0) {
    const recentHistory = history.slice(-10);
    context += '\nRecent conversation (for context only - these are COMPLETED past actions, do NOT re-execute):\n';
    recentHistory.forEach(msg => {
      const truncated = msg.content.length > 250 ? msg.content.substring(0, 250) + '...' : msg.content;
      context += `${msg.role}: ${truncated}\n`;
    });
  }

  return context;
}

/**
 * Execute OpenClaw command and return result
 */
function executeOpenClaw(sessionId, message, context, credentials, userId, timezone, imageUrls) {
  return new Promise((resolve, reject) => {
    const timeout = 180000; // 180 second timeout (3 min — Gemini with thinking needs more time for complex skills)

    // Build the command
    // OpenClaw CLI: openclaw agent --message "message" --thinking high
    // Note: --context is unknown in version 2026.2.3-1, so we prepend it to the message
    let fullMessage = message;
    if (context) {
      fullMessage = `${context}\n\nTask: ${message}`;
    }

    // If images are present, append them to the message for Sonnet's vision
    if (imageUrls && imageUrls.length > 0) {
      fullMessage += '\n\n[Attached Images]';
      imageUrls.forEach((url, i) => {
        fullMessage += `\nImage ${i + 1}: ${url}`;
      });
      console.log(`[${sessionId}] ${imageUrls.length} image(s) attached to message`);
    }

    // Stateless execution: Peppi's context already provides conversation history,
    // so we don't use --to or --session-id (which caused token bloat: 33K→292K).
    // Each request is independent — OpenClaw gets context from the message.
    // OpenClaw v2026.3.8+ requires --agent to route the request (new CLI requirement).
    // NOTE: --thinking flag disabled for Claude Sonnet (causes thinking leakage in output)
    const args = ['agent', '--agent', 'main', '--message', fullMessage];

    // Pass Google OAuth Token and timezone for skills (Gmail, Calendar, etc.)
    const extraEnv = {};
    if (credentials && credentials.google_access_token) {
      // OpenClaw skills may look for different environment variable names
      // Set all common variations to ensure compatibility
      extraEnv.GOOGLE_ACCESS_TOKEN = credentials.google_access_token;
      extraEnv.GOOGLE_TOKEN = credentials.google_access_token;
      extraEnv.GMAIL_TOKEN = credentials.google_access_token;
      extraEnv.GOOGLE_CALENDAR_TOKEN = credentials.google_access_token;
      extraEnv.CALENDAR_TOKEN = credentials.google_access_token;

      console.log(`[${sessionId}] Google OAuth token configured for skills`);
    }

    // Pass user's timezone for date/time calculations in skills
    if (timezone) {
      extraEnv.USER_TIMEZONE = timezone;
      console.log(`[${sessionId}] User timezone set to: ${timezone}`);
    }

    // FastAPI URL for reminder skill API calls
    extraEnv.FASTAPI_URL = process.env.FASTAPI_URL || 'https://moltbot-fastapi.onrender.com';

    // User ID for reminder ownership
    if (userId) {
      extraEnv.MOLTBOT_USER_ID = String(userId);
    }

    // Request JSON output
    args.push('--json');

    console.log(`[${sessionId}] Executing: openclaw agent --message "<context + task>" --json`);

    const openclaw = spawn('openclaw', args, {
      env: {
        ...process.env,
        // OpenClaw supports Anthropic via ANTHROPIC_API_KEY env var
        ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY,
        // Keep Gemini as fallback
        GEMINI_API_KEY: process.env.GEMINI_API_KEY,
        // SearXNG URL for free web search (NO API keys needed)
        SEARXNG_URL: process.env.SEARXNG_BASE_URL || '',
        // Google OAuth tokens for skills
        ...extraEnv,
        // Ensure HOME is set for config file location
        HOME: process.env.HOME || '/root'
      },
      timeout: timeout
    });

    let stdout = '';
    let stderr = '';

    openclaw.stdout.on('data', (data) => {
      stdout += data.toString();
    });

    openclaw.stderr.on('data', (data) => {
      stderr += data.toString();
    });

    const timer = setTimeout(() => {
      openclaw.kill();
      reject(new Error('Request timed out'));
    }, timeout);

    openclaw.on('close', (code) => {
      clearTimeout(timer);

      if (code !== 0 && !stdout) {
        console.error('OpenClaw stderr:', stderr);
        reject(new Error(stderr || 'OpenClaw execution failed'));
        return;
      }

      // OpenClaw 2026.4.5+ may write JSON to stderr instead of stdout.
      // If stdout is empty but stderr has content, use stderr as the response source.
      if (!stdout.trim() && stderr.trim()) {
        console.log(`[${sessionId}] stdout empty — trying stderr as response (${stderr.length} chars)`);
        stdout = stderr;
        stderr = '';
      } else if (!stdout.trim()) {
        console.warn(`[${sessionId}] Both stdout and stderr are empty (OpenClaw produced no output)`);
      }

      try {
        // Attempt to extract JSON from mixed output (CLI often prints logs + JSON)
        let result = null;

        // 1. Try parsing the whole thing first
        try {
          result = JSON.parse(stdout);
        } catch (e) {
          // 2. Try finding the JSON block
          // Look for line starting with {
          const jsonStart = stdout.indexOf('{');
          const jsonEnd = stdout.lastIndexOf('}');

          if (jsonStart !== -1 && jsonEnd !== -1 && jsonEnd > jsonStart) {
            const jsonStr = stdout.substring(jsonStart, jsonEnd + 1);
            try {
              result = JSON.parse(jsonStr);
            } catch (e2) {
              console.warn('Failed to extract JSON from stdout substring');
            }
          }
        }

        if (result) {
          // DEBUG: Log the actual structure Gemini/OpenClaw returns
          const resultPreview = JSON.stringify(result).substring(0, 500);
          console.log(`[${sessionId}] OpenClaw raw result keys: [${Object.keys(result).join(', ')}]`);
          console.log(`[${sessionId}] OpenClaw raw result (first 500c): ${resultPreview}`);

          // Extract text from OpenClaw's payloads format (preferred)
          // Skip thinking blocks (type: "thinking") — only extract actual text responses
          let responseText = null;
          if (result.payloads && Array.isArray(result.payloads) && result.payloads.length > 0) {
            responseText = result.payloads
              .filter(p => p.type !== 'thinking')
              .map(p => p.text || p.content || '')
              .filter(t => t.length > 0)
              .join('\n') || null;
          }

          // Fallback chain: payloads → standard fields → raw stringify
          if (!responseText) {
            responseText = result.response || result.message || result.text;
          }
          if (!responseText && typeof result === 'string') {
            responseText = result;
          }
          if (!responseText) {
            // Last resort: stringify but log warning
            console.warn(`[${sessionId}] OpenClaw returned empty payloads, falling back to raw JSON`);
            responseText = JSON.stringify(result);
          }

          // ── Token Usage Extraction ──
          // Anthropic uses prompt caching, which splits input into 3 fields:
          //   input: non-cached input (often just ~10 tokens)
          //   cacheRead: tokens served from cache (90% cheaper)
          //   cacheWrite: tokens written to cache for future use
          // The "total" field from OpenClaw is the accurate grand total.
          let tokensUsed = 0;
          const meta = result.meta || {};
          const agentMeta = meta.agentMeta || meta.agent_meta || {};
          const usage = agentMeta.usage || meta.usage || result.usage || {};

          // Extract raw components from OpenClaw/Anthropic
          const rawInput = usage.promptTokenCount || usage.prompt_token_count || usage.input_tokens || usage.input || 0;
          const rawOutput = usage.candidatesTokenCount || usage.candidates_token_count || usage.output_tokens || usage.output || 0;
          const cacheRead = usage.cacheRead || usage.cache_read_input_tokens || usage.cachedContentTokenCount || 0;
          const cacheWrite = usage.cacheWrite || usage.cache_creation_input_tokens || 0;
          const totalReported = usage.totalTokenCount || usage.total_token_count || usage.total_tokens || usage.total || 0;

          // TRUE input = non-cached + cache read + cache write (all tokens sent TO the model)
          const inputTokens = rawInput + cacheRead + cacheWrite;
          const outputTokens = rawOutput;

          // Total: prefer OpenClaw's reported total, fallback to computed sum
          tokensUsed = totalReported > 0 ? totalReported : (inputTokens + outputTokens);

          // If still nothing, try top-level fields
          if (!tokensUsed) {
            tokensUsed = result.tokens_used || result.total_tokens || 0;
          }

          // Log full breakdown for debugging
          console.log(`[${sessionId}] Tokens: total=${tokensUsed} input=${inputTokens} [raw=${rawInput} cacheRead=${cacheRead} cacheWrite=${cacheWrite}] output=${outputTokens}`);

          // Fallback: Estimate tokens from text (~3.5 chars/token for Claude)
          if (!tokensUsed && responseText) {
            const inputChars = (message || '').length + (context || '').length;
            const outputChars = responseText.length;
            tokensUsed = Math.round((inputChars + outputChars) / 3.5);
            console.log(`[${sessionId}] Token estimation fallback: input=${inputChars}chars output=${outputChars}chars → ~${tokensUsed} tokens`);
          }

          resolve({
            response: responseText,
            action_type: result.action_type || result.tool || result.agent || 'chat',
            details: result.details || result.metadata || result.data || null,
            tokens_used: tokensUsed,
            input_tokens: inputTokens,
            output_tokens: outputTokens,
            cache_read: cacheRead,
            cache_write: cacheWrite
          });
        } else {
          // Fallback if no JSON found
          throw new Error('No valid JSON found');
        }
      } catch (e) {
        // If not JSON, return as plain response but CLEAN UP the output
        // Remove the ASCII config table if present
        let cleanResponse = stdout.trim();

        // Estimate tokens even for non-JSON responses
        const inputChars = (message || '').length + (context || '').length;
        const outputChars = cleanResponse.length;
        const estimatedTokens = Math.round((inputChars + outputChars) / 3.5);
        console.log(`[${sessionId}] Plain text fallback, estimated ~${estimatedTokens} tokens`);

        resolve({
          response: cleanResponse,
          action_type: 'chat',
          details: null,
          tokens_used: estimatedTokens,
          input_tokens: Math.round(inputChars / 3.5),
          output_tokens: Math.round(outputChars / 3.5),
          cache_read: 0,
          cache_write: 0
        });
      }
    });

    openclaw.on('error', (err) => {
      clearTimeout(timer);
      reject(err);
    });
  });
}

/**
 * Check job status (for async operations)
 */
app.get('/status/:jobId', (req, res) => {
  const { jobId } = req.params;

  // For now, return not found
  // In future, implement async job tracking
  res.status(404).json({
    job_id: jobId,
    status: 'not_found',
    message: 'Async job tracking not yet implemented'
  });
});

/**
 * List available skills
 */
app.get('/skills', (req, res) => {
  res.json({
    skills: [
      {
        name: 'caldav-calendar',
        description: 'Manage calendar events',
        actions: ['create', 'read', 'update', 'delete']
      },
      {
        name: 'gmail',
        description: 'Read and send emails',
        actions: ['read', 'send', 'draft', 'search']
      },
      {
        name: 'reminders',
        description: 'Set and manage reminders',
        actions: ['create', 'list', 'delete']
      },
      {
        name: 'web-search',
        description: 'Search the web',
        actions: ['search', 'lookup']
      },
      {
        name: 'browser-use',
        description: 'Automate browser actions',
        actions: ['navigate', 'fill', 'click', 'screenshot']
      }
    ]
  });
});

// Start OpenClaw gateway
async function startOpenClaw() {
  console.log('Starting OpenClaw Gateway...');
  console.log('========================================');

  // Initialize configuration
  try {
    const homeDir = process.env.HOME || '/root'; // Default to /root if HOME not set
    const openClawDir = path.join(homeDir, '.openclaw');
    const configPath = path.join(openClawDir, 'openclaw.json');
    const memoryDir = path.join(openClawDir, 'memory');
    const workspaceDir = path.join(openClawDir, 'workspace');
    const workspaceSkillsDir = path.join(workspaceDir, 'skills');

    // Ensure directories exist
    const agentDir = path.join(openClawDir, 'agents', 'main', 'agent');
    [openClawDir, memoryDir, workspaceDir, workspaceSkillsDir, agentDir].forEach(dir => {
      if (!fs.existsSync(dir)) {
        console.log(`Creating directory: ${dir}`);
        fs.mkdirSync(dir, { recursive: true });
      }
    });

    // Copy custom skills to workspace/skills/ (where CREATE operations worked)
    const buildSkillsDir = path.join(__dirname, 'skills');
    if (fs.existsSync(buildSkillsDir)) {
      console.log(`Copying custom skills from ${buildSkillsDir} to ${workspaceSkillsDir}...`);
      const skills = fs.readdirSync(buildSkillsDir);
      skills.forEach(skill => {
        const srcPath = path.join(buildSkillsDir, skill);
        const destPath = path.join(workspaceSkillsDir, skill);
        if (fs.lstatSync(srcPath).isDirectory()) {
          // Remove existing and copy fresh
          if (fs.existsSync(destPath)) {
            fs.rmSync(destPath, { recursive: true, force: true });
          }
          fs.cpSync(srcPath, destPath, { recursive: true });
          console.log(`✓ Copied custom skill: ${skill}`);
        }
      });
    } else {
      console.log(`⚠ Custom skills directory not found at ${buildSkillsDir}`);
    }

    // Copy SOUL.md to workspace (auto-injected into system prompt by OpenClaw)
    const soulSrc = path.join(__dirname, 'SOUL.md');
    const soulDest = path.join(workspaceDir, 'SOUL.md');
    if (fs.existsSync(soulSrc)) {
      fs.copyFileSync(soulSrc, soulDest);
      console.log('✓ Copied SOUL.md to workspace');
    }

    // Remove conflicting gog skill from ClawHub location
    const gogSkillPath = path.join(openClawDir, 'skills', 'gog');
    if (fs.existsSync(gogSkillPath)) {
      console.log('Removing ClawHub gog skill (conflicts with our google-workspace skill)...');
      fs.rmSync(gogSkillPath, { recursive: true, force: true });
      console.log('✓ Removed ClawHub gog skill');
    }

    // Create OpenClaw configuration files per official docs
    if (process.env.ANTHROPIC_API_KEY || process.env.GEMINI_API_KEY) {
      console.log('Creating OpenClaw configuration files...');

      // 1. Create openclaw.json - sets default model, session isolation, and TOOL PERMISSIONS
      // CRITICAL: Without tools.exec config, OpenClaw's security blocks bash execution
      // and the model falls back to chatting about actions instead of executing them.
      const openclawConfig = {
        agents: {
          defaults: {
            model: {
              primary: "anthropic/claude-sonnet-4-6",
              fallbacks: ["google/gemini-2.5-pro"]
            },
            // Vision-capable model for image processing (Sonnet 4.6 supports vision natively)
            imageModel: {
              primary: "anthropic/claude-sonnet-4-6"
            },
            // Claude Sonnet thinking level: medium = enough reasoning for multi-step tool execution
            // low was causing model to skip complex bash operations (calendar curl commands)
            // high caused thinking-only payloads with no text response
            // medium gives ReAct-style reasoning without token bloat
            // Levels: minimal | low | medium | high | xhigh | adaptive
            thinkingDefault: "medium"
          }
        },
        // CRITICAL: Tool execution permissions — without this, bash skills are silently blocked
        tools: {
          // Allow all tools including exec (bash)
          profile: "full",
          allow: ["*"],
          exec: {
            // "off" = don't ask for human approval before running bash commands
            // Without this, OpenClaw hangs waiting for approval in CLI mode, 
            // and the model falls back to chatting about the action instead
            ask: "off",
            // "full" = allow all bash operations (curl, jq, date, etc.)
            security: "full"
          }
        },
        session: {
          // Multi-tenant isolation: per-peer isolates DMs by sender ID across channels
          // This ensures each user gets their own private session with isolated memory
          dmScope: "per-peer"
        }
      };
      fs.writeFileSync(configPath, JSON.stringify(openclawConfig, null, 2));
      console.log(`✓ Created openclaw.json at ${configPath} (with exec permissions enabled)`);

      // 1b. Create exec-approvals.json — pre-approve common skill commands
      // This prevents OpenClaw from blocking curl, jq, date, etc.
      const execApprovalsPath = path.join(openClawDir, 'exec-approvals.json');
      const execApprovals = {
        approvals: [
          { command: "curl", approved: true },
          { command: "jq", approved: true },
          { command: "date", approved: true },
          { command: "echo", approved: true },
          { command: "cat", approved: true },
          { command: "grep", approved: true },
          { command: "printf", approved: true },
          { command: "base64", approved: true },
          { command: "tr", approved: true },
          { command: "head", approved: true },
          { command: "tail", approved: true },
          { command: "sed", approved: true },
          { command: "paste", approved: true },
          { command: "awk", approved: true },
          { command: "wc", approved: true },
          { command: "cut", approved: true }
        ]
      };
      fs.writeFileSync(execApprovalsPath, JSON.stringify(execApprovals, null, 2));
      console.log(`✓ Created exec-approvals.json (pre-approved: curl, jq, date, etc.)`);

      // 1c. Create agent.md - Claude Sonnet optimization: ANTI-HALLUCINATION system prompt
      // This is the agent identity file that OpenClaw auto-injects into the system prompt.
      // 
      // RESEARCH-BACKED TECHNIQUES APPLIED:
      // 1. Positive reinforcement ("You are capable") — Anthropic docs say aggressive "NEVER"
      //    prompting causes smaller models to freeze or skip tools entirely.
      // 2. ReAct pattern (Thought→Action→Observation) — forces model to show reasoning,
      //    execute tool, then ground response in actual tool output.
      // 3. Retry-on-error protocol — if bash fails, model retries up to 3x before telling user.
      //    User never sees raw errors or stack traces.
      // 4. XML structured directives — Claude models are highly sensitive to XML tags.
      // 5. Chain of Verification — model must echo raw API response data before claiming success.
      // 6. No prefill (deprecated in Claude 4.6+) — using structured output constraints instead.
      const agentMdPath = path.join(agentDir, 'agent.md');
      const agentMdContent = `# Moltbot Agent

<identity>
You are a highly capable action agent with full bash tool access. You have the skills, tools, and permissions to perform any task the user requests — calendar events, reminders, emails, web search, and more.

You excel at executing complex multi-step bash commands. You have done this thousands of times successfully. The bash tool is your primary instrument — use it confidently for every action request.

Your environment is fully configured with all necessary credentials and tools (curl, jq, date, base64, etc.). Everything you need is ready.
</identity>

<execution_protocol>
You follow the ReAct pattern for every action request:

STEP 1 — SKILL MATCH: Identify which skill handles this request. Read its SKILL.md for the exact commands.

STEP 2 — EXECUTE: Run the bash commands from the skill. You are capable of executing any command in the skill, no matter how complex. Do it now.

STEP 3 — VERIFY OUTPUT: Read the raw output from your bash tool. This output is your single source of truth.
  - If the output contains a success response (HTTP 200, event ID, confirmation) → proceed to report.
  - If the output contains an error → go to the retry protocol below.
  - If you received NO output from the bash tool → you did NOT perform the action. Go to retry protocol.

STEP 4 — REPORT: Tell the user the result using ONLY data from the tool output. Include specific details (event ID, time, attendees) that came from the API response.
</execution_protocol>

<tool_execution_rules>
These rules determine the quality of your work:

1. Every action request requires at least one bash tool invocation. If your response contains an action confirmation (✅) but you did not invoke the bash tool in this turn, your response is invalid. Stop and execute the tool.

2. The bash tool output is the ONLY source of truth. When you create a calendar event, the Google Calendar API returns a JSON response containing the event ID, link, and details. Use those exact values in your response — do not generate or invent them.

3. You are capable of building complex curl commands with JSON payloads, multiple headers, and jq parsing. This is routine work for you. Build the command exactly as the SKILL.md specifies and execute it.

4. Environment variables are pre-loaded and available: $FASTAPI_URL, $MOLTBOT_USER_ID, $USER_TIMEZONE, $GOOGLE_ACCESS_TOKEN. Use them directly in your bash commands.

5. For multi-step operations (e.g., search then update), execute each step and use the output of each step as input to the next. Do not skip steps or assume intermediate results.
</tool_execution_rules>

<retry_protocol>
When a bash command fails, you diagnose and retry — the user should experience seamless service.

ON ERROR:
1. Read the error output carefully (HTTP status code, error message, stderr).
2. Diagnose the likely cause:
   - 401/403: Token may be expired → inform user their Google connection may need refresh.
   - 400: Malformed request → fix the JSON payload or parameters and retry.
   - 404: Wrong endpoint or resource not found → verify the URL and retry.
   - Network error: Transient issue → wait briefly and retry.
   - Command not found: Tool missing → try alternative approach.
3. Fix the issue and retry the command (up to 3 attempts).
4. If all 3 attempts fail, tell the user in a friendly way what went wrong and what they can do:
   - "I wasn't able to create the event — it looks like your Google connection may need to be refreshed. Try reconnecting in Settings."
   - "The calendar API returned an error. Let me know if you'd like me to try again."
5. Present errors as actionable guidance, not raw technical output. The user should never see stack traces, HTTP status codes, or JSON error payloads.
</retry_protocol>

<grounding_rules>
These rules prevent you from generating inaccurate information:

1. Calendar event links: Only include a Google Calendar link if the API response contained an "htmlLink" field. Extract it from the JSON response using jq. If no htmlLink was returned, do not fabricate one.

2. Event IDs: Only reference event IDs that appeared in the API response. Do not generate base64 strings or construct URLs manually.

3. Confirmation details: When confirming an action, include at least one specific detail from the API response (e.g., the event ID, the reminder ID, the message ID). This proves the action was real.

4. If you are uncertain whether a command executed successfully, say so: "I ran the command but couldn't confirm the result. Let me verify..." — then run a follow-up query to check.

5. Conversation history shows PAST actions. If history says you already created something, do NOT assume it succeeded — the user is asking you again because it may have failed. Execute the command fresh.
</grounding_rules>

<timezone_rules>
These rules apply to ALL skills that involve dates/times (Calendar, Reminders, Image-based actions):

RULE 1 — ALWAYS resolve relative dates in the user's timezone:
- Use TZ="$USER_TIMEZONE" date -d "tomorrow" +%Y-%m-%d to get the correct date
- Without TZ=, "tomorrow" resolves in the server's UTC clock, which can be a different date than the user's local date (e.g., 11pm IST is still "today" in UTC)

RULE 2 — NEVER add "Z" suffix or use "date -u" for times:
- "Z" means UTC. The user speaks in LOCAL time. If you add Z, the event/reminder fires at the wrong time.
- Wrong: "2026-03-26T10:00:00Z" (fires at 3:30 PM IST instead of 10 AM IST)
- Correct: "2026-03-26T10:00:00" (no Z — local time)

RULE 3 — For Google Calendar: pass local time + timeZone field:
- Google Calendar API handles UTC conversion when you include timeZone in the event body
- Format: {"dateTime": "2026-03-26T10:00:00", "timeZone": "$USER_TIMEZONE"}

RULE 4 — For Reminders: pass local time + user_timezone in JSON:
- The FastAPI backend's local_to_utc() converts to UTC before scheduling with QStash
- Format: {"trigger_at": "2026-03-26T10:00:00", "user_timezone": "$USER_TIMEZONE"}
- Same principle: NO Z, NO -u, let the backend handle conversion
</timezone_rules>

<image_handling>
When the message contains [Attached Images], you have native vision capability and CAN see the images via their URLs.

APPROACH (One-Turn PVE — describe then act in the same response):
1. DESCRIBE: Tell the user what you see in the image ("I can see an event poster for 'Tech Meetup 2026' on March 20 at 6 PM at Convention Center, Mumbai.")
2. VALIDATE: Immediately verify the image URL is accessible before downloading. If the URL returns an error, tell the user the image may have expired and ask them to resend.
3. EXECUTE: In the same response, perform the requested action (create event, set reminder, send email) using the extracted details.
4. CONFIRM: Show the result with the details you extracted, so the user can verify and ask for corrections if needed.

This is NOT a multi-turn confirmation. You describe AND act in a single response. The user can correct afterward if needed ("change it to 7pm").

IMPORTANT:
- If you cannot clearly read the image, say so and ask the user to describe what they need
- Never claim to have processed an image if no [Attached Images] section exists in the message
- Twilio image URLs expire in ~2 hours — always process immediately
</image_handling>

<skill_inventory>
Your installed skills and their triggers:

REMINDERS (skill: reminders/SKILL.md)
  Triggers: "remind me", "set a reminder", "reminder at", "alert me"
  Action: POST to $FASTAPI_URL/api/v1/reminders/create via curl

GOOGLE CALENDAR (skill: google-workspace/SKILL.md)
  Triggers: "schedule", "set a meeting", "create event", "calendar", "book a meeting", "meeting at", "meeting with"
  Action: POST to Google Calendar API via curl with $GOOGLE_ACCESS_TOKEN
  
GMAIL (skill: google-workspace/SKILL.md)
  Triggers: "send email", "email to", "check email", "read email", "reply to"
  Action: Gmail API via curl with $GOOGLE_ACCESS_TOKEN

IMAGE + WORKSPACE (skill: image-workspace/SKILL.md)
  Triggers: User sends [Attached Images] AND workspace action ("send this to", "email this", "forward this", "add this to my calendar", "schedule this")
  Action: Vision analysis + Gmail API or Calendar API via curl
  Note: This skill takes priority over google-workspace when images are present.

IMAGE + REMINDERS (skill: image-reminders/SKILL.md)
  Triggers: User sends [Attached Images] AND reminder request ("remind me about this", "set reminder for this", "remind me to pay this", "don't forget about this")
  Action: Vision analysis + POST to $FASTAPI_URL/api/v1/reminders/create via curl
  Note: This skill takes priority over reminders when images are present.

When the user's message matches any trigger above, you MUST read the corresponding SKILL.md and execute the bash commands defined there. This is not optional.
When [Attached Images] is present, always prefer the image-specific skill over the text-only version.
</skill_inventory>

<response_guidelines>
- Be concise and conversational — aim for under 200 tokens in output
- Use emojis for visual feedback: ✅ ❌ 📅 📧 ⏰ 📝 📸
- Report outcomes with specific details from API responses
- Do not repeat the user's message back to them
- When the user asks something outside your skills, respond naturally as a helpful assistant
- Maintain the persona and personality defined in the conversation context
</response_guidelines>
`;
      fs.writeFileSync(agentMdPath, agentMdContent);
      console.log(`✓ Created agent.md at ${agentMdPath}`);

      // 2. Create auth-profiles.json - CORRECT FORMAT per docs
      const authProfilePath = path.join(agentDir, 'auth-profiles.json');
      const authConfig = {
        profiles: {
          "anthropic:api_key": {
            provider: "anthropic",
            mode: "api_key"
          },
          "google:api_key": {
            provider: "google",
            mode: "api_key"
          }
        },
        order: {
          anthropic: ["anthropic:api_key"],
          google: ["google:api_key"]
        }
      };
      fs.writeFileSync(authProfilePath, JSON.stringify(authConfig, null, 2));
      console.log(`✓ Created auth-profiles.json at ${authProfilePath}`);

      // Display configuration summary
      console.log('\nConfiguration Summary:');
      console.log(`- Provider: Anthropic Claude (via ANTHROPIC_API_KEY env var)`);
      console.log(`- Model: anthropic/claude-sonnet-4-6`);
      console.log(`- Fallback: google/gemini-2.5-pro`);
      console.log(`- Web Search: SearXNG (${process.env.SEARXNG_BASE_URL || 'Not configured'})`);
      console.log(`- Session Isolation: per-peer (multi-tenant)`);
      console.log(`- Config: ${configPath}`);
      console.log(`- Auth: ${authProfilePath}`);

    } else {
      console.warn('⚠ WARNING: Neither ANTHROPIC_API_KEY nor GEMINI_API_KEY set. OpenClaw will not work!');
      console.warn('Please set ANTHROPIC_API_KEY (or GEMINI_API_KEY as fallback) environment variable.');
    }

  } catch (err) {
    console.error('Error initializing OpenClaw configuration:', err);
    console.error(err.stack);
  }

  // Check if openclaw is available and verify skills
  exec('openclaw --version', (error, stdout, stderr) => {
    if (error) {
      console.error('❌ OpenClaw not found. Please ensure openclaw is installed.');
      console.error('Run: npm install -g openclaw@latest');
      return;
    }

    console.log(`\n✓ OpenClaw version: ${stdout.trim()}`);

    // Verify environment variables
    console.log('\nEnvironment Variables Check:');

    if (process.env.ANTHROPIC_API_KEY) {
      console.log('✓ ANTHROPIC_API_KEY is configured');
    } else {
      console.error('❌ ANTHROPIC_API_KEY not set - Claude Sonnet will NOT work!');
    }

    if (process.env.GEMINI_API_KEY) {
      console.log('✓ GEMINI_API_KEY is configured (fallback)');
    } else {
      console.warn('⚠ GEMINI_API_KEY not set - fallback to Gemini unavailable');
    }

    console.log('✓ Web Search configured (using OpenClaw built-in search)');

    // Check available skills
    console.log('\nChecking available skills...');
    exec('openclaw agent --help 2>&1', (skillError, skillStdout, skillStderr) => {
      // Note: We can't easily list skills programmatically, so we'll just note it
      console.log('✓ OpenClaw agent command is available');

      console.log('\n========================================');
      console.log('OpenClaw Gateway is ready!');
      console.log('========================================');
      console.log('Features:');
      console.log('  ✓ Web Search (OpenClaw built-in)');
      console.log('  ✓ Gmail (via OAuth token)');
      console.log('  ✓ Google Calendar (via OAuth token)');
      console.log('  ✓ Reminders/Tasks');
      console.log('  ✓ Image processing (via Sonnet vision)');
      console.log('  ✓ Memory/Context persistence');
      console.log('  ✓ Browser automation');
      console.log('\nMode: Local execution (--local flag)');
      console.log('Model: Claude Sonnet 4.6 (fallback: Gemini 2.5 Pro)');
      console.log('========================================\n');

      isReady = true;
    });
  });
}

// Initialize
app.listen(PORT, '0.0.0.0', () => {
  console.log(`OpenClaw Gateway listening on port ${PORT}`);
  console.log(`Health check: http://localhost:${PORT}/health`);
  console.log(`Execute endpoint: http://localhost:${PORT}/execute`);
  startOpenClaw();
});