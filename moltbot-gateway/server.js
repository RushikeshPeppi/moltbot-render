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

    // Use --session-id to avoid the --to requirement (which expects messaging channels)
    args.push('--session-id', sessionId || 'api-session');

    // Use --local to run the embedded agent directly with shell env vars.
    // This avoids the "gateway closed" errors seen with the background daemon.
    args.push('--local');

    // Pass Google Token if available
    const extraEnv = {};
    if (credentials && credentials.google_access_token) {
      extraEnv.GOOGLE_ACCESS_TOKEN = credentials.google_access_token;
      // Also potentially for specific skills
      extraEnv.GOOGLE_TOKEN = credentials.google_access_token;
    }

    // Set thinking level
    args.push('--thinking', 'medium');

    // Request JSON output
    args.push('--json');

    console.log(`Executing: openclaw ${args.join(' ')}`);

    const openclaw = spawn('openclaw', args, {
      env: {
        ...process.env,
        // OpenClaw often expects GOOGLE_API_KEY for the google provider
        GOOGLE_API_KEY: process.env.GEMINI_API_KEY,
        ...extraEnv
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
        // Try to parse JSON response
        // Note: New version with --json might wrap the response in a different structure
        const result = JSON.parse(stdout);
        resolve({
          response: result.response || result.message || result.text || stdout.trim(),
          action_type: result.action_type || result.tool || result.agent || 'chat',
          details: result.details || result.metadata || result.data || null,
          tokens_used: result.tokens_used || result.usage?.total_tokens || 0
        });
      } catch (e) {
        // If not JSON, return as plain response
        resolve({
          response: stdout.trim() || 'Task completed.',
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

  // Initialize configuration
  try {
    const homeDir = process.env.HOME || '/root'; // Default to /root if HOME not set
    const openClawDir = path.join(homeDir, '.openclaw');
    const agentDir = path.join(openClawDir, 'agents', 'main', 'agent');
    const authProfilePath = path.join(agentDir, 'auth-profiles.json');

    // Ensure directory exists
    if (!fs.existsSync(agentDir)) {
      console.log(`Creating agent directory: ${agentDir}`);
      fs.mkdirSync(agentDir, { recursive: true });
    }

    // Create auth-profiles.json if using Google/Gemini
    if (process.env.GEMINI_API_KEY) {
      console.log('Configuring OpenClaw to use Google/Gemini provider...');
      const authConfig = {
        profiles: [
          {
            id: "google-gemini",
            provider: "google",
            apiKey: process.env.GEMINI_API_KEY
          }
        ],
        default: "google-gemini"
      };

      fs.writeFileSync(authProfilePath, JSON.stringify(authConfig, null, 2));
      console.log(`✓ Created auth-profiles.json at ${authProfilePath}`);
    } else {
      console.warn('⚠ GEMINI_API_KEY not set. Skipping auth profile creation.');
    }
  } catch (err) {
    console.error('Error initializing OpenClaw configuration:', err);
  }

  // Check if openclaw is available
  exec('openclaw --version', (error, stdout, stderr) => {
    if (error) {
      console.error('OpenClaw not found. Please ensure openclaw is installed.');
      console.error('Run: npm install -g openclaw@latest');
      return;
    }

    console.log(`OpenClaw version: ${stdout.trim()}`);

    // Verify environment variables
    if (!process.env.GEMINI_API_KEY) {
      console.warn('WARNING: GEMINI_API_KEY not set. OpenClaw may not work correctly.');
    } else {
      console.log('✓ GEMINI_API_KEY is configured');
    }

    // Check if BRAVE_API_KEY is set (optional for enhanced web search)
    if (process.env.BRAVE_API_KEY) {
      console.log('✓ BRAVE_API_KEY is configured (enhanced web search enabled)');
    } else {
      console.log('ℹ BRAVE_API_KEY not set (using built-in web search)');
    }

    console.log('OpenClaw Gateway is ready!');
    console.log('- web_search tool: enabled by default');
    console.log('- Model: auto-detected from GOOGLE_API_KEY');
    console.log('- Mode: local execution (--local flag)');

    isReady = true;
  });
}

// Initialize
app.listen(PORT, '0.0.0.0', () => {
  console.log(`OpenClaw Gateway listening on port ${PORT}`);
  console.log(`Health check: http://localhost:${PORT}/health`);
  console.log(`Execute endpoint: http://localhost:${PORT}/execute`);
  startOpenClaw();
});