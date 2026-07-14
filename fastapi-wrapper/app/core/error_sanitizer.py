"""
Client-facing exception sanitizer (CASA 6.2.1 — no debug/stack detail in production).

Finding P2-5: handlers pass `exception=str(e)` into the response builders, which copy it
straight into the JSON body — handing an attacker raw exception text (driver errors, table
names, Supabase/Google API internals, occasionally a value from the record itself).

ROOT-CAUSE PLACEMENT — read before "simplifying" this away:
There are ~30 `exception=str(e)` call sites but only SIX response builders, and every leak
flows through one of them. Sanitizing at the builders (not the call sites) means a NEW
handler written next year that does `exception=str(e)` still cannot leak — the control does
not depend on the next developer remembering it. Patching 30 call sites would have left the
33rd one open. Builders: models.error_response, routes.create_error_response,
oauth.create_response, oauth.create_error_response, google_services.create_response,
playground.create_response.

The exception text is NOT discarded — callers already `logger.error(...)` it server-side,
where it belongs. Only the client-facing copy is suppressed.
"""

import logging

from ..config import settings

logger = logging.getLogger(__name__)


def client_safe_exception(exception: object) -> str | None:
    """
    Return what the CLIENT may see in the `exception` field of a response body.

    Production (DEBUG=false, the only mode Render runs): always None.
    Local dev (DEBUG=true): pass the text through, so debugging still works.

    The response SHAPE is unchanged — `exception` stays a nullable field that is already
    None on every success path, so no caller (Peppi Laravel, the gateway, the playground)
    sees a new or missing key.
    """
    if exception is None:
        return None
    if settings.DEBUG:
        return str(exception)
    return None
