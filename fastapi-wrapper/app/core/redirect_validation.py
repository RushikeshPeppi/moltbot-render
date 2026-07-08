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
    overrides the default set entirely when present. The origin of `PEPPI_WEBSITE_URL`
    is always trusted so an environment-specific website value is never accidentally
    rejected.
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
            "https://peppi.ai",
            "https://www.peppi.ai",
            "https://peppi.app",
            "https://www.peppi.app",
            "https://peppi-playground.onrender.com",
        }

    site_origin = _origin(settings.PEPPI_WEBSITE_URL or "")
    if site_origin:
        origins.add(site_origin)

    return frozenset(origins)


ALLOWED_REDIRECT_ORIGINS = _build_allowlist()


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
