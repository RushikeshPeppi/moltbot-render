# SearXNG - Free, self-hosted meta-search engine
FROM searxng/searxng:latest

# Copy custom configuration to fix Render.com deployment issues
# - Disables strict bot detection (incompatible with Render's reverse proxy)
# - Disables failing engines (ahmia, torch)
# - Configures proper server settings
COPY settings.yml /etc/searxng/settings.yml

# SearXNG aggregates results from multiple search engines
# No API keys required
