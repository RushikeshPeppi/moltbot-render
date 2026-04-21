"""
Playground-specific endpoints for PM testing environment.
Provides user listing and account creation for the playground UI.
"""

import logging
import csv
import io
import secrets
from typing import Optional
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from datetime import datetime

from ..core.database import db
from ..core.redis_client import redis_client
from ..config import settings
from ..models import ResponseCode

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/playground", tags=["Playground"])


def create_response(code, message, data=None, error=None, exception=None):
    return {
        "code": code,
        "message": message,
        "data": data,
        "error": error,
        "exception": exception,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/users")
async def list_playground_users():
    """
    Get list of all users from tbl_clawdbot_users.
    These are populated when users complete OAuth or are created via the playground.
    """
    try:
        users = await db.get_all_users()

        # Convert user_id to string for frontend consistency
        formatted = [
            {
                "user_id": str(u["user_id"]),
                "name": u["name"],
                "email": u.get("email"),
                "google_connected": u.get("google_connected", False),
                "timezone": u.get("timezone", "UTC"),
            }
            for u in users
        ]

        return create_response(
            code=ResponseCode.SUCCESS,
            message=f"Found {len(formatted)} users",
            data={"users": formatted},
        )

    except Exception as e:
        logger.error(f"Error listing playground users: {e}")
        return JSONResponse(
            status_code=500,
            content=create_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to list users",
                error="PLAYGROUND_USERS_ERROR",
                exception=str(e),
            ),
        )


class CreatePlaygroundUserRequest(BaseModel):
    name: str = Field(..., description="Display name for the new user")
    redirect_uri: Optional[str] = Field(None, description="Where to redirect after OAuth")
    timezone: Optional[str] = Field("UTC", description="User's timezone (IANA format)")


@router.post("/create-user")
async def create_playground_user(request: CreatePlaygroundUserRequest):
    """
    Create a new playground user and optionally initiate OAuth.

    1. Gets next sequential user_id from tbl_clawdbot_users
    2. Inserts user into tbl_clawdbot_users
    3. Returns user_id and OAuth authorization URL if Google OAuth is configured
    """
    try:
        # Generate alphanumeric user_id
        new_user_id = await db.generate_user_id()

        # Insert user into tbl_clawdbot_users
        user = await db.upsert_user(
            user_id=new_user_id,
            name=request.name,
            google_connected=False,
            timezone=request.timezone or "UTC"
        )

        if not user:
            return JSONResponse(
                status_code=500,
                content=create_response(
                    code=ResponseCode.INTERNAL_ERROR,
                    message="Failed to create user in database",
                    error="USER_CREATE_FAILED",
                ),
            )

        # Build OAuth URL if configured
        auth_url = None
        if settings.GOOGLE_CLIENT_ID:
            state = secrets.token_urlsafe(32)

            # Store OAuth state with user name for profile fallback
            state_data = {
                "user_id": new_user_id,
                "user_name": request.name,
                "redirect_uri": request.redirect_uri or settings.PEPPI_WEBSITE_URL or "",
            }
            await redis_client.set(f"oauth_state:{state}", state_data, ttl=600)

            scopes = " ".join(settings.GOOGLE_SCOPES)
            auth_url = (
                f"https://accounts.google.com/o/oauth2/v2/auth"
                f"?client_id={settings.GOOGLE_CLIENT_ID}"
                f"&redirect_uri={settings.GOOGLE_REDIRECT_URI}"
                f"&response_type=code"
                f"&scope={scopes}"
                f"&state={state}"
                f"&access_type=offline"
                f"&prompt=consent"
            )

        return create_response(
            code=ResponseCode.CREATED,
            message="Playground user created",
            data={
                "user_id": new_user_id,
                "name": request.name,
                "timezone": request.timezone or "UTC",
                "auth_url": auth_url,
            },
        )

    except Exception as e:
        logger.error(f"Error creating playground user: {e}")
        return JSONResponse(
            status_code=500,
            content=create_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to create user",
                error="PLAYGROUND_CREATE_ERROR",
                exception=str(e),
            ),
        )


class UpdateTimezoneRequest(BaseModel):
    timezone: str = Field(..., description="IANA timezone (e.g. 'America/New_York')")


@router.patch("/users/{user_id}/timezone")
async def update_user_timezone(user_id: str, request: UpdateTimezoneRequest):
    """Update a user's timezone setting from the playground Settings panel."""
    try:
        success = await db.update_user_timezone(user_id, request.timezone)

        if not success:
            return JSONResponse(
                status_code=500,
                content=create_response(
                    code=ResponseCode.INTERNAL_ERROR,
                    message="Failed to update timezone",
                    error="TIMEZONE_UPDATE_FAILED",
                ),
            )

        return create_response(
            code=ResponseCode.SUCCESS,
            message="Timezone updated",
            data={"user_id": user_id, "timezone": request.timezone},
        )
    except Exception as e:
        logger.error(f"Error updating timezone for user {user_id}: {e}")
        return JSONResponse(
            status_code=500,
            content=create_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to update timezone",
                error="TIMEZONE_UPDATE_ERROR",
                exception=str(e),
            ),
        )


@router.get("/messages/{user_id}")
async def get_playground_messages(user_id: str):
    """
    Poll for pending playground messages for a user.

    The frontend calls this every 5 seconds. When a reminder fires (QStash → /reminders/deliver),
    the delivery handler pushes a message to Redis. This endpoint pops and returns them all,
    clearing the queue so each message is shown exactly once.

    Returns:
        {"messages": [{"type": "reminder_delivery", "message": "...", "timestamp": "..."}]}
    """
    try:
        messages = await redis_client.pop_playground_messages(user_id)
        return create_response(
            code=ResponseCode.SUCCESS,
            message=f"Found {len(messages)} message(s)",
            data={"messages": messages},
        )
    except Exception as e:
        logger.error(f"Error fetching playground messages for user {user_id}: {e}")
        return JSONResponse(
            status_code=500,
            content=create_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to fetch messages",
                error="PLAYGROUND_MESSAGES_ERROR",
                exception=str(e),
            ),
        )


@router.get("/token-usage")
async def get_token_usage(
    user_id: Optional[str] = Query(None, description="Filter by user ID (omit for all users)"),
    date_from: Optional[str] = Query(None, description="Start date ISO format"),
    date_to: Optional[str] = Query(None, description="End date ISO format"),
    action_type: Optional[str] = Query(None, description="Filter by action type"),
    limit: int = Query(500, description="Max rows to return"),
):
    """
    Get token usage data for the PM dashboard.
    Supports filtering by user, date range, and action type.
    Returns per-request token usage + aggregate totals.
    """
    try:
        rows = await db.get_token_usage(
            user_id=user_id,
            date_from=date_from,
            date_to=date_to,
            action_type=action_type,
            limit=limit,
        )

        # Compute aggregates
        total_tokens = sum(r.get("tokens_used", 0) or 0 for r in rows)
        total_messages = len(rows)

        # Get user names for display
        users = await db.get_all_users()
        user_map = {u["user_id"]: u["name"] for u in users}

        # Enrich rows with user names
        for row in rows:
            row["user_name"] = user_map.get(row.get("user_id"), "Unknown")

        return create_response(
            code=ResponseCode.SUCCESS,
            message=f"Found {total_messages} actions with {total_tokens} total tokens",
            data={
                "rows": rows,
                "total_messages": total_messages,
                "total_tokens": total_tokens,
            },
        )

    except Exception as e:
        logger.error(f"Error fetching token usage: {e}")
        return JSONResponse(
            status_code=500,
            content=create_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to fetch token usage",
                error="TOKEN_USAGE_ERROR",
                exception=str(e),
            ),
        )


# Anthropic Claude Sonnet 4.6 pricing (per 1M tokens)
SONNET_INPUT_RATE = 3.00        # $ per 1M non-cached input tokens
SONNET_OUTPUT_RATE = 15.00      # $ per 1M output tokens
SONNET_CACHE_READ_RATE = 0.30   # $ per 1M cache read tokens (90% discount)
SONNET_CACHE_WRITE_RATE = 3.75  # $ per 1M cache write tokens (25% premium)
# Blended rate fallback for rows without detailed breakdown
INPUT_RATIO = 0.15
OUTPUT_RATIO = 0.85
BLENDED_RATE = INPUT_RATIO * SONNET_INPUT_RATE + OUTPUT_RATIO * SONNET_OUTPUT_RATE


def _estimate_cost_detailed(input_tokens: int, output_tokens: int, cache_read: int, cache_write: int) -> float:
    """Calculate actual cost using Anthropic's tiered pricing."""
    # Subtract cache from input to get non-cached input
    non_cached_input = max(0, input_tokens - cache_read - cache_write)
    return (
        (non_cached_input / 1_000_000) * SONNET_INPUT_RATE +
        (cache_read / 1_000_000) * SONNET_CACHE_READ_RATE +
        (cache_write / 1_000_000) * SONNET_CACHE_WRITE_RATE +
        (output_tokens / 1_000_000) * SONNET_OUTPUT_RATE
    )


def _estimate_cost(tokens: int) -> float:
    """Estimate cost using Claude Sonnet 4.6 blended rate (fallback)."""
    return (tokens / 1_000_000) * BLENDED_RATE


@router.get("/token-usage/csv")
async def download_token_usage_csv(
    user_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    action_type: Optional[str] = Query(None),
    limit: int = Query(500),
):
    """Download token usage data as CSV."""
    try:
        rows = await db.get_token_usage(
            user_id=user_id,
            date_from=date_from,
            date_to=date_to,
            action_type=action_type,
            limit=limit,
        )

        users = await db.get_all_users()
        user_map = {u["user_id"]: u["name"] for u in users}

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "ID", "Timestamp", "User ID", "User Name", "Action Type",
            "Request", "Response", "Status", "Tokens Used",
            "Input Tokens", "Output Tokens", "Cache Read", "Cache Write", "Est. Cost ($)",
        ])

        total_tokens = 0
        total_cost = 0.0
        for row in rows:
            tokens = row.get("tokens_used", 0) or 0
            inp = row.get("input_tokens", 0) or 0
            out = row.get("output_tokens", 0) or 0
            cr = row.get("cache_read", 0) or 0
            cw = row.get("cache_write", 0) or 0
            total_tokens += tokens
            # Use detailed cost if we have the breakdown, else blended
            cost = _estimate_cost_detailed(inp, out, cr, cw) if inp or out else _estimate_cost(tokens)
            total_cost += cost
            writer.writerow([
                row.get("id", ""),
                row.get("created_at", ""),
                row.get("user_id", ""),
                user_map.get(row.get("user_id"), "Unknown"),
                row.get("action_type", ""),
                (row.get("request_summary") or "")[:200],
                (row.get("response_summary") or "")[:200],
                row.get("status", ""),
                tokens if tokens else "",
                inp if inp else "",
                out if out else "",
                cr if cr else "",
                cw if cw else "",
                f"{cost:.4f}" if tokens else "",
            ])

        # Summary row
        writer.writerow([])
        writer.writerow([
            "TOTAL", "", "", "", "", "", "",
            f"{len(rows)} messages", total_tokens,
            "", "", "", "",
            f"{total_cost:.4f}",
        ])
        writer.writerow([])
        writer.writerow(["PRICING", f"Claude Sonnet 4.6: Input ${SONNET_INPUT_RATE}/1M, Output ${SONNET_OUTPUT_RATE}/1M, Cache Read ${SONNET_CACHE_READ_RATE}/1M, Cache Write ${SONNET_CACHE_WRITE_RATE}/1M"])
        writer.writerow(["METHOD", "Token estimation: ~3.5 chars/token (Anthropic docs), +/- 10-15% for English text"])

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=token_usage.csv"},
        )

    except Exception as e:
        logger.error(f"Error generating CSV: {e}")
        return JSONResponse(
            status_code=500,
            content=create_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to generate CSV",
                error="CSV_ERROR",
                exception=str(e),
            ),
        )


@router.post("/token-usage/backfill")
async def backfill_token_estimates():
    """
    One-time backfill: Estimate tokens for historical rows that have tokens_used=0.
    Uses stored request_summary + response_summary character lengths (~4 chars/token).
    Note: Summaries are truncated to 500 chars, so estimates are lower bounds.
    """
    try:
        # Get all rows with 0 tokens
        rows = await db.get_token_usage(limit=1000)
        zero_rows = [r for r in rows if not r.get("tokens_used")]

        if not zero_rows:
            return create_response(
                code=ResponseCode.SUCCESS,
                message="No rows to backfill — all rows already have token data",
                data={"updated": 0},
            )

        updated = 0
        for row in zero_rows:
            req_len = len(row.get("request_summary") or "")
            resp_len = len(row.get("response_summary") or "")

            if req_len == 0 and resp_len == 0:
                continue

            # Estimate: chars/4 + overhead for system prompt (~500 tokens)
            # Note: summaries are truncated to 500 chars, so this is a lower bound
            estimated = max(1, round((req_len + resp_len) / 4) + 500)

            success = await db.update_action_log(
                log_id=row["id"],
                status=row.get("status", "success"),
                tokens_used=estimated,
            )
            if success:
                updated += 1

        return create_response(
            code=ResponseCode.SUCCESS,
            message=f"Backfilled {updated} of {len(zero_rows)} rows with token estimates",
            data={
                "total_zero_rows": len(zero_rows),
                "updated": updated,
                "note": "Estimates are lower bounds (summaries truncated to 500 chars). Accuracy: +/- 10-15% for full text.",
            },
        )

    except Exception as e:
        logger.error(f"Error backfilling token estimates: {e}")
        return JSONResponse(
            status_code=500,
            content=create_response(
                code=ResponseCode.INTERNAL_ERROR,
                message="Failed to backfill token estimates",
                error="BACKFILL_ERROR",
                exception=str(e),
            ),
        )
