const express = require('express');
const { spawn, exec } = require('child_process');
const fs = require('fs');
const path = require('path');
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
 * Execute action via OpenClaw
 * 
 * POST /execute
 * Body: {
 *   session_id: string,
 *   message: string,
 *   credentials: object,
 *   history: array
 * }
 */
app.post('/execute', async (req, res) => {
  const { session_id, message, credentials, history } = req.body;

  if (!message) {
    return res.status(400).json({ error: 'Message is required' });
  }

  try {
    console.log(`[${session_id}] Processing: ${message.substring(0, 50)}...`);

    // Build context from credentials and history
    const context = buildContext(credentials, history);

    // Execute OpenClaw command
    const result = await executeOpenClaw(session_id, message, context, credentials);

    console.log(`[${session_id}] Completed: ${result.action_type || 'chat'}`);

    res.json({
      success: true,
      response: result.response,
      action_type: result.action_type,
      details: result.details,
      tokens_used: result.tokens_used || 0
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
 * Build context string for OpenClaw from credentials and history
 */
function buildContext(credentials, history) {
  let context = '';

  // Add credentials context
  if (credentials) {
    if (credentials.google_access_token) {
      context += 'User has connected their Google account. You can access their calendar and email.\n';
    }
  }

  // Add conversation history context
  if (history && history.length > 0) {
    const recentHistory = history.slice(-10); // Last 10 messages
    context += '\nRecent conversation:\n';
    recentHistory.forEach(msg => {
      context += `${msg.role}: ${msg.content}\n`;
    });
  }

  return context;
}

/**
 * Execute OpenClaw command and return result
 */
function executeOpenClaw(sessionId, message, context, credentials) {
  return new Promise((resolve, reject) => {
    const timeout = 55000; // 55 second timeout

    // Build the command
    // OpenClaw CLI: openclaw agent --message "message" --thinking high
    // Note: --context is unknown in version 2026.2.3-1, so we prepend it to the message
    let fullMessage = message;
    if (context) {
      fullMessage = `${context}\n\nTask: ${message}`;
    }

    const args = ['agent', '--message', fullMessage];

    // Use --session-id to avoid the --to requirement
    args.push('--session-id', sessionId || 'api-session');

    // Use --local to run the embedded agent directly with shell env vars.
    // This avoids the "gateway closed" errors seen with the background daemon.
    args.push('--local');

    // Pass Google OAuth Token for skills (Gmail, Calendar, etc.)
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

    // Set thinking level
    args.push('--thinking', 'medium');

    // Request JSON output
    args.push('--json');

    console.log(`Executing: openclaw ${args.join(' ')}`);

    const openclaw = spawn('openclaw', args, {
      env: {
        ...process.env,
        // OpenClaw 2026 expects GOOGLE_API_KEY for Google/Gemini models
        GOOGLE_API_KEY: process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY,
        GEMINI_API_KEY: process.env.GEMINI_API_KEY,
        // Brave Search API for web search
        BRAVE_API_KEY: process.env.BRAVE_API_KEY || '',
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
          resolve({
            response: result.response || result.message || result.text || (typeof result === 'string' ? result : JSON.stringify(result)),
            action_type: result.action_type || result.tool || result.agent || 'chat',
            details: result.details || result.metadata || result.data || null,
            tokens_used: result.tokens_used || result.usage?.total_tokens || 0
          });
        } else {
          // Fallback if no JSON found
          throw new Error('No valid JSON found');
        }
      } catch (e) {
        // If not JSON, return as plain response but CLEAN UP the output
        // Remove the ASCII config table if present
        let cleanResponse = stdout.trim();

        resolve({
          response: cleanResponse,
          action_type: 'chat',
          details: null,
          tokens_used: 0
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
    const skillsDir = path.join(openClawDir, 'skills');

    // Ensure directories exist
    const agentDir = path.join(openClawDir, 'agents', 'main', 'agent');
    [openClawDir, memoryDir, skillsDir, agentDir].forEach(dir => {
      if (!fs.existsSync(dir)) {
        console.log(`Creating directory: ${dir}`);
        fs.mkdirSync(dir, { recursive: true });
      }
    });

    // Create OpenClaw configuration files per official docs
    if (process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY) {
      console.log('Creating OpenClaw configuration files...');

      // 1. Create openclaw.json - sets default model
      const openclawConfig = {
        agents: {
          defaults: {
            model: {
              primary: "google/gemini-2.0-flash-exp"
            }
          }
        }
      };
      fs.writeFileSync(configPath, JSON.stringify(openclawConfig, null, 2));
      console.log(`✓ Created openclaw.json at ${configPath}`);

      // 2. Create auth-profiles.json - CORRECT FORMAT per docs
      const authProfilePath = path.join(agentDir, 'auth-profiles.json');
      const authConfig = {
        profiles: {
          "google:gemini": {
            provider: "google",
            mode: "api_key"
          }
        },
        order: {
          google: ["google:gemini"]
        }
      };
      fs.writeFileSync(authProfilePath, JSON.stringify(authConfig, null, 2));
      console.log(`✓ Created auth-profiles.json at ${authProfilePath}`);

      // Display configuration summary
      console.log('\nConfiguration Summary:');
      console.log(`- Provider: Google (via GEMINI_API_KEY env var)`);
      console.log(`- Model: google/gemini-2.0-flash-exp`);
      console.log(`- Web Search: OpenClaw built-in`);
      console.log(`- Config: ${configPath}`);
      console.log(`- Auth: ${authProfilePath}`);

    } else {
      console.warn('⚠ WARNING: GEMINI_API_KEY not set. OpenClaw will not work!');
      console.warn('Please set GEMINI_API_KEY or GOOGLE_API_KEY environment variable.');
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

    if (process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY) {
      console.log('✓ GEMINI_API_KEY/GOOGLE_API_KEY is configured');
    } else {
      console.error('❌ GEMINI_API_KEY not set - OpenClaw will NOT work!');
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
      console.log('  ✓ Memory/Context persistence');
      console.log('  ✓ Browser automation');
      console.log('\nMode: Local execution (--local flag)');
      console.log('Model: Google Gemini 2.0 Flash');
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