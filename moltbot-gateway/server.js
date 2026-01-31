const express = require('express');
const { spawn } = require('child_process');
const app = express();
const PORT = process.env.PORT || 18789;

app.use(express.json());

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'online', service: 'moltbot-gateway' });
});

// Start Moltbot gateway
function startMoltbot() {
  console.log('Starting Moltbot Gateway...');

  const moltbot = spawn('moltbot', ['gateway', '--daemon'], {
    env: { ...process.env },
    stdio: 'inherit'
  });

  moltbot.on('error', (err) => {
    console.error('Failed to start Moltbot:', err);
  });

  moltbot.on('exit', (code) => {
    console.log(`Moltbot exited with code ${code}`);
    // Restart after 5 seconds
    setTimeout(startMoltbot, 5000);
  });
}

// Initialize
app.listen(PORT, '0.0.0.0', () => {
  console.log(`Server listening on port ${PORT}`);
  startMoltbot();
});