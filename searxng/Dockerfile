# Peppi SearXNG — overlay on the official image (searxng/searxng:latest).
#
# The base image:
#   - Serves SearXNG with Granian (WSGI), default GRANIAN_HOST=::, GRANIAN_PORT=8080
#   - Runs as root (no USER directive); the entrypoint normalises ownership of
#     /etc/searxng to searxng:searxng (UID 977) at startup
#   - Reads settings.yml from /etc/searxng/settings.yml, with first-time
#     creation from /usr/local/searxng/searx/settings.yml as a template
#   - The upstream entrypoint at /usr/local/searxng/entrypoint.sh ONLY
#     substitutes the placeholder string "ultrasecretkey" when settings.yml is
#     being created from the template — NOT on subsequent restarts. Because we
#     ship our own settings.yml, the upstream substitution never fires; our
#     entrypoint-shim.sh handles it explicitly. See entrypoint-shim.sh for
#     the rationale.
#
# Runtime env vars consumed (configured on the Render service):
#   SEARXNG_SECRET           Flask secret key. Substituted into settings.yml
#                            by the shim. If unset, the shim auto-generates a
#                            random value (matches upstream behaviour).
#   __SEARXNG_SETTINGS_PATH  Path to settings.yml. Default /etc/searxng/settings.yml.
#   GRANIAN_HOST             Listen interface. Default :: (dual-stack).
#   GRANIAN_PORT             Listen port. Default 8080.
#   SEARXNG_PORT             Alias for GRANIAN_PORT.

FROM searxng/searxng:latest

# Container runs as root (matches upstream); --chown=977 sets file ownership
# to searxng:searxng so the upstream entrypoint's setup_ownership() check
# does not need to re-chown at startup.
COPY --chown=977:977 settings.yml      /etc/searxng/settings.yml
COPY --chown=977:977 limiter.toml      /etc/searxng/limiter.toml
COPY --chown=977:977 entrypoint-shim.sh /usr/local/searxng/entrypoint-shim.sh

RUN chmod +x /usr/local/searxng/entrypoint-shim.sh

ENTRYPOINT ["/usr/local/searxng/entrypoint-shim.sh"]
