"""
OAuth redirect_uri allow-listing (CASA 3.2.2 / 5.1.2 — open-redirect prevention).

The post-callback redirect_uri is caller-supplied: Peppi Laravel and the playground
pass it into /oauth/google/init and /playground/create-user, it is stored in the
Redis `oauth_state` blob, and the public /oauth/google/callback 302s the user to it.
Left unchecked that is an open-redirect + phishing primitive on our own OAuth callback
host — exactly the behavior a Google restricted-scope reviewer flags.

We pin the set of origins we are willing to 302 a user back to and match on the
EXACT scheme+host[:port] origin — never a substring (a substring match on "peppi.ai"
would pass "evil-peppi.ai" and "https://evil.com/peppi.ai"). This defeats
`//evil.com`, `https:evil.com`, `https://peppi.ai.evil.com`, and `javascript:`/`data:`.
"""

import logging
from typing import Optional
from urllib.parse import urlsplit

from ..config import settings

logger = logging.getLogger(__name__)


def _origin(url: str) -> Optional[str]:
    """Return the exact 'scheme://host[:port]' origin of an absolute http(s) URL,
    or None if it has no usable scheme+host — e.g. 'javascript:alert(1)',
    protocol-relative '//evil.com', 'https:evil.com', or ''."""
    if not url:
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    # Require an explicit http(s) scheme AND a network location. urlsplit maps
    # '//evil.com' → scheme='' (rejected) and 'javascript:x' → netloc='' (rejected).
    if parts.scheme not in ("https", "http") or not parts.netloc:
        return None
    # Host is case-insensitive (RFC 3986 §6.2.2.1); urlsplit already lowercases the
    # scheme. Lowercase netloc so a canonical-but-uppercase host (e.g. 'Peppi.ai')
    # matches. Cannot weaken the check: any off-allowlist host stays off-allowlist,
    # and userinfo tricks ('peppi.ai@evil.com') keep the '@evil.com' in the netloc.
    return f"{parts.scheme}://{parts.netloc.lower()}"


def _build_allowlist() -> frozenset:
    """Compute the allow-listed origins once at import.

    `OAUTH_ALLOWED_REDIRECT_ORIGINS` (comma-separated exact origins — scheme://host,
    NO path; a path-bearing entry can never match an origin and is silently inert)
    overrides the default set entirely when present.

    ⚠ THE ENV VAR IS NOT THE WHOLE ALLOW-LIST. The origin of `PEPPI_WEBSITE_URL` is
    added **unconditionally**, on both the env-override and default paths, so an
    environment-specific website value is never accidentally rejected. The effective
    allow-list is therefore:
        (OAUTH_ALLOWED_REDIRECT_ORIGINS  OR  the built-in default set)
        ∪ { origin(PEPPI_WEBSITE_URL) }
    That union is an implicit trust channel: changing PEPPI_WEBSITE_URL silently adds a
    redirect origin. Keep it pointed at a live, owned origin, and state the union (not
    just the env var) whenever this control is described in CASA evidence.

    The committed default is PRODUCTION origins ONLY. Any non-prod origin (e.g. a
    staging host used for pre-prod OAuth testing) is supplied per-environment via
    `OAUTH_ALLOWED_REDIRECT_ORIGINS` — never hard-coded here — so the repo default can
    never ship a non-prod / localhost redirect target into a CASA-scanned build
    (CWE-601). NOTE: because the env var REPLACES this set, an env override must list
    the full set of origins it wants allowed (all prod origins + any staging host),
    not just the extra one.
    """
    raw = (settings.OAUTH_ALLOWED_REDIRECT_ORIGINS or "").strip()
    if raw:
        origins = {
            o.strip().rstrip("/")
            for o in raw.split(",")
            if o.strip()
        }
    else:
        origins = {
            # LIVE product origins.
            "https://peppi.ai",
            "https://www.peppi.ai",
            # Legacy company-owned domain. Currently has NO A record (verified 2026-07-16)
            # so nothing can actually land here; retained because we own + renew the domain
            # (no takeover risk) and it may be revived. NOT the safe-default any more —
            # see config.PEPPI_WEBSITE_URL.
            "https://peppi.app",
            "https://www.peppi.app",
            # REMOVED 2026-07-16: "https://peppi-playground.onrender.com".
            # Two reasons. (1) SECURITY: the playground Render service is SUSPENDED
            # (`x-render-routing: suspend-by-user`). Suspension reserves the slug, but if the
            # service is ever DELETED, Render returns `peppi-playground.onrender.com` to a
            # SHARED namespace — anyone could then claim it and would own an allow-listed
            # OAuth redirect origin, i.e. a live open-redirect on our callback. A *.onrender.com
            # slug is not a domain we own; it cannot be trusted like peppi.ai/peppi.app.
            # (2) It is a TEST UI — it does not belong in a production redirect allow-list.
            # If the playground is ever revived, supply its origin via
            # OAUTH_ALLOWED_REDIRECT_ORIGINS for that environment instead of hard-coding it.
        }

    site_origin = _origin(settings.PEPPI_WEBSITE_URL or "")
    if site_origin:
        origins.add(site_origin)

    return frozenset(origins)


ALLOWED_REDIRECT_ORIGINS = _build_allowlist()

# Public alias for callers that need the parsed origin (e.g. for safe logging
# of a rejected redirect_uri without echoing the full attacker-supplied URL).
origin_of = _origin


def is_allowed_redirect(url: str) -> bool:
    """True only if `url` is an absolute http(s) URL whose exact origin is allow-listed."""
    origin = _origin(url)
    return origin is not None and origin in ALLOWED_REDIRECT_ORIGINS


def safe_redirect_base(url: str, default: str) -> str:
    """Return `url` if its origin is allow-listed, else the safe `default`.

    Used at the callback as defense-in-depth: the entry points reject off-allowlist
    values up front, so a rejected value here means a stale/tampered state blob —
    fail closed to the default rather than honor it.
    """
    if is_allowed_redirect(url):
        return url
    logger.warning("Rejected off-allowlist OAuth redirect_uri; falling back to safe default")
    return default
