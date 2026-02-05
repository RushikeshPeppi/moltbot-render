#!/bin/bash

# OpenClaw Initialization Script
# This script creates the necessary configuration for OpenClaw to use Google/Gemini

echo "Initializing OpenClaw configuration..."

# Create OpenClaw config directory if it doesn't exist
mkdir -p /opt/render/.openclaw/agents/main/agent

# Create auth-profiles.json with Google provider configuration
cat > /opt/render/.openclaw/agents/main/agent/auth-profiles.json << 'EOF'
{
  "profiles": [
    {
      "id": "google-gemini",
      "provider": "google",
      "apiKey": "$GOOGLE_API_KEY"
    }
  ],
  "default": "google-gemini"
}
EOF

# Replace $GOOGLE_API_KEY with actual value from environment
sed -i "s/\$GOOGLE_API_KEY/$GOOGLE_API_KEY/g" /opt/render/.openclaw/agents/main/agent/auth-profiles.json

echo "✓ Created auth-profiles.json with Google provider"
echo "✓ OpenClaw will use Google/Gemini for all requests"

# Start the Node.js server
exec npm start
