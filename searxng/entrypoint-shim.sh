#!/bin/sh
# Entrypoint shim for Peppi's SearXNG container.
#
# Why this exists: the upstream container/entrypoint.sh only substitutes the
# placeholder string "ultrasecretkey" when settings.yml is being created from
# its template (i.e. when the file does not yet exist at
# $__SEARXNG_SETTINGS_PATH). Because we ship our own hardened settings.yml via
# Dockerfile COPY, that file always exists at container start, so the upstream
# substitution never runs and the literal "ultrasecretkey" would otherwise
# remain in production. This shim performs the substitution explicitly, every
# start, before delegating to the upstream entrypoint.
#
# Substitution sources, in order of preference:
#   1. SEARXNG_SECRET env var (set on Render — see render.yaml).
#   2. Auto-generated random value (matches upstream behaviour and ensures
#      the placeholder is always replaced even if SEARXNG_SECRET is unset).
#
# The shim is idempotent: if "ultrasecretkey" has already been replaced in
# settings.yml, the sed call is a no-op.

set -eu

SETTINGS_FILE="${__SEARXNG_SETTINGS_PATH:-/etc/searxng/settings.yml}"

if [ -f "$SETTINGS_FILE" ] && grep -q 'ultrasecretkey' "$SETTINGS_FILE"; then
    if [ -n "${SEARXNG_SECRET:-}" ] && [ "$SEARXNG_SECRET" != "ultrasecretkey" ]; then
        SECRET="$SEARXNG_SECRET"
    else
        # Same generator the upstream entrypoint uses for first-time setup.
        SECRET="$(head -c 24 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9')"
    fi

    # In-place edit. Quietly continue on failure (e.g. read-only volume mount)
    # so the container can still boot — searxng will warn at startup if the
    # placeholder secret is in use.
    if ! sed -i "s|ultrasecretkey|${SECRET}|g" "$SETTINGS_FILE" 2>/dev/null; then
        echo "WARN: could not substitute secret_key in $SETTINGS_FILE (file not writable)" >&2
    fi
fi

# Hand off to the upstream entrypoint. Path is fixed by the upstream Dockerfile.
exec /usr/local/searxng/entrypoint.sh "$@"
