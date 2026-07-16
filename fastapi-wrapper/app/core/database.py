"""
Supabase Database Client for credential storage, audit logging, and rate limit persistence.
Uses supabase-py for async operations.
"""

import json
import logging
import secrets
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from cryptography.fernet import Fernet, MultiFernet
from supabase import create_client, Client
from ..config import settings

logger = logging.getLogger(__name__)


# ── RLS scoped-JWT support (Phase 6 · 1.6b / CASA 3.1.4) ───────────────────────────
# migrations/009_rls_policies.sql defines: USING (user_id = app_current_user_id()),
# where app_current_user_id() reads  request.jwt.claims ->> 'user_id'.
# Those policies are INERT while we connect with the service_role key, because
# service_role has BYPASSRLS. To make them enforce, PER-USER operations run through a
# client whose Authorization bearer is a short-lived JWT we mint here carrying
# {"role": "authenticated", "user_id": <id>} signed with the project's JWT secret.
#
# WHY NOT EVERYTHING: several operations are legitimately CROSS-user and cannot carry a
# single user's claim. Each is called out at its call site below. Forcing them through a
# scoped JWT would not "improve security" — it would break the feature and tempt someone
# to widen the policy, which is worse than the status quo.
def _mint_scoped_jwt(user_id: str) -> str:
    """Mint a short-lived JWT scoped to one user_id for PostgREST/RLS.

    Fail-CLOSED: raises if the flag is on but the signing secret is absent. A silent
    fallback to service_role would present as "RLS enforced" while enforcing nothing —
    exactly the class of fail-open this codebase has been burned by twice.
    """
    # HS256 against Supabase's LEGACY JWT secret. Verified on the live project 2026-07-16:
    # the JWT Keys page shows "Legacy JWT secret (still used) — used only to verify JWTs",
    # i.e. we sign / Supabase verifies. That is also why the project's anon+service_role
    # keys (themselves HS256 JWTs signed with this secret) still work.
    #
    # ⚠ COUPLING: Supabase is deprecating this secret and nudges you to revoke it. If it is
    # ever revoked while RLS_SCOPED_JWT=true, EVERY per-user credential op breaks — there is
    # no fallback, because the new signing keys are ASYMMETRIC and Supabase holds the private
    # key (they sign Auth-issued user JWTs; we don't use Supabase Auth, our ids are Peppi
    # uuids, so we must self-mint). Response is RLS_SCOPED_JWT=false, then re-architect.
    # See evidence/phase6/1.6b-rls-cutover-runbook.md.
    import jwt as pyjwt  # PyJWT (pinned explicitly in requirements.txt — was only transitive)

    if not settings.SUPABASE_JWT_SECRET:
        raise RuntimeError(
            "RLS_SCOPED_JWT=true but SUPABASE_JWT_SECRET is empty — refusing to fall back "
            "to service_role (that would silently disable RLS while appearing enforced)."
        )
    if not user_id:
        raise ValueError("scoped JWT requires a user_id")

    now = int(time.time())
    claims = {
        # PostgREST derives the Postgres role from this claim. MUST be a non-BYPASSRLS
        # role or the policies are skipped again.
        "role": "authenticated",
        # Read by app_current_user_id() in migration 009.
        "user_id": user_id,
        "iat": now,
        "exp": now + settings.RLS_JWT_TTL_SECONDS,
    }
    return pyjwt.encode(claims, settings.SUPABASE_JWT_SECRET, algorithm="HS256")


class Database:
    """Supabase database client for credential storage and audit logging"""
    
    _instance: Optional["Database"] = None
    _client: Optional[Client] = None
    _cipher: Optional[MultiFernet] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def initialize(self):
        """Initialize Supabase client and encryption"""
        if self._client is None:
            try:
                if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
                    logger.warning("Supabase credentials not configured")
                    return
                
                # Create client without proxy (Render doesn't need it)
                self._client = create_client(
                    supabase_url=settings.SUPABASE_URL,
                    supabase_key=settings.SUPABASE_KEY
                )
                logger.info("Supabase client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client: {e}")
                raise
        
        if self._cipher is None and settings.ENCRYPTION_KEY:
            try:
                # MultiFernet keyring, not a bare Fernet (CASA 6.7.1 / ASVS 6.2.4 —
                # crypto agility). ENCRYPTION_KEY is the PRIMARY: MultiFernet always
                # ENCRYPTS with keys[0] and DECRYPTS by trying each key in order.
                #
                # Why this matters: with a single static Fernet, rotating ENCRYPTION_KEY
                # made every previously-stored Google token undecryptable, and the failure
                # was SILENT — get_credentials() swallows the InvalidToken and returns None
                # (see the `except` below), so every user would have looked "disconnected"
                # with no error anywhere. CASA expects a documented, non-destructive
                # rotation path; this is it.
                #
                # Rotate: ENCRYPTION_KEYS_OLD="<current key>", ENCRYPTION_KEY="<new key>",
                # redeploy (old tokens still decrypt), re-encrypt at rest, then clear
                # ENCRYPTION_KEYS_OLD. Documented in config.py.
                keyring = [Fernet(settings.ENCRYPTION_KEY.encode())]
                for old in settings.ENCRYPTION_KEYS_OLD.split(","):
                    old = old.strip()
                    if old:
                        keyring.append(Fernet(old.encode()))
                self._cipher = MultiFernet(keyring)
                if len(keyring) > 1:
                    logger.info(
                        f"Encryption keyring active: 1 primary + {len(keyring) - 1} "
                        f"retired key(s) for rotation"
                    )
            except Exception as e:
                # Fail closed: leave _cipher as None so _encrypt/_decrypt raise rather
                # than silently storing plaintext.
                logger.error(f"Failed to initialize encryption: {e}")
    
    def _scoped(self, user_id: str) -> Client:
        """Return a client whose DB context is RESTRICTED to `user_id` via RLS.

        When RLS_SCOPED_JWT is off (the default) this returns the ordinary service_role
        client, so behaviour is byte-identical to before the cutover — the flag is the
        only thing that changes the data path.

        When on: `apikey` = anon key (NOT service_role — that would restore a BYPASSRLS
        context and silently defeat the policies), `Authorization` = a per-call JWT
        carrying {"role":"authenticated","user_id":...}. Migration 009's
        `USING (user_id = app_current_user_id())` then does the filtering IN POSTGRES, so
        a bug in our query layer can no longer read another user's row.

        Requires migrations/010_rls_grants.sql (the `authenticated` role needs table
        GRANTs; RLS filters rows, it does not confer privileges).
        """
        if not settings.RLS_SCOPED_JWT:
            return self._client

        if not settings.SUPABASE_ANON_KEY:
            # Fail closed rather than silently using service_role (= no RLS).
            raise RuntimeError(
                "RLS_SCOPED_JWT=true but SUPABASE_ANON_KEY is empty — refusing to send the "
                "service_role key as apikey, which would re-enable BYPASSRLS and make RLS "
                "enforcement a fiction."
            )

        token = _mint_scoped_jwt(user_id)
        client = create_client(
            supabase_url=settings.SUPABASE_URL,
            supabase_key=settings.SUPABASE_ANON_KEY,
        )
        # PostgREST reads the role + custom claims from this bearer.
        client.postgrest.auth(token)
        return client

    async def close(self):
        """Close Supabase client (no-op for supabase-py)"""
        self._client = None
        logger.info("Supabase client closed")
    
    def _encrypt(self, data: Dict[str, Any]) -> str:
        """Encrypt credentials data"""
        if not self._cipher:
            raise ValueError("Encryption key not configured")
        return self._cipher.encrypt(json.dumps(data).encode()).decode()
    
    def _decrypt(self, encrypted: str) -> Dict[str, Any]:
        """Decrypt credentials data"""
        if not self._cipher:
            raise ValueError("Encryption key not configured")
        return json.loads(self._cipher.decrypt(encrypted.encode()).decode())
    
    # ==================== Credential Operations ====================
    
    async def store_credentials(
        self, 
        user_id: str, 
        service: str, 
        credentials: Dict[str, Any],
        expires_at: datetime = None
    ) -> bool:
        """Store encrypted credentials for a user"""
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return False
            
            encrypted = self._encrypt(credentials)
            
            # Upsert: insert or update on conflict
            data = {
                "user_id": user_id,
                "service": service,
                "encrypted_credentials": encrypted,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            self._scoped(user_id).table("tbl_clawdbot_credentials").upsert(
                data,
                on_conflict="user_id,service"
            ).execute()
            
            logger.info(f"Stored credentials for user {user_id}, service: {service}")
            return True
        except Exception as e:
            logger.error(f"Error storing credentials: {e}")
            return False
    
    async def get_credentials(self, user_id: str, service: str) -> Optional[Dict[str, Any]]:
        """Retrieve and decrypt credentials"""
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return None
            
            response = self._scoped(user_id).table("tbl_clawdbot_credentials").select(
                "encrypted_credentials, expires_at"
            ).eq("user_id", user_id).eq("service", service).execute()
            
            if not response.data or len(response.data) == 0:
                return None
            
            row = response.data[0]
            creds = self._decrypt(row['encrypted_credentials'])
            creds['expires_at'] = row['expires_at']
            
            return creds
        except Exception as e:
            logger.error(f"Error retrieving credentials: {e}")
            return None
    
    async def delete_credentials(self, user_id: str, service: str) -> bool:
        """Delete credentials for a service"""
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return False
            
            self._scoped(user_id).table("tbl_clawdbot_credentials").delete().eq(
                "user_id", user_id
            ).eq("service", service).execute()
            
            logger.info(f"Deleted credentials for user {user_id}, service: {service}")
            return True
        except Exception as e:
            logger.error(f"Error deleting credentials: {e}")
            return False
    
    async def get_all_credentials(self, user_id: str) -> Dict[str, Dict[str, Any]]:
        """Get all credentials for a user"""
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return {}
            
            response = self._scoped(user_id).table("tbl_clawdbot_credentials").select(
                "service, encrypted_credentials, expires_at"
            ).eq("user_id", user_id).execute()
            
            result = {}
            for row in response.data or []:
                creds = self._decrypt(row['encrypted_credentials'])
                creds['expires_at'] = row['expires_at']
                result[row['service']] = creds
            
            return result
        except Exception as e:
            logger.error(f"Error retrieving all credentials: {e}")
            return {}
    
    async def check_credentials_exist(self, user_id: str, service: str) -> bool:
        """Check if credentials exist for a service"""
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return False
            
            response = self._scoped(user_id).table("tbl_clawdbot_credentials").select(
                "id"
            ).eq("user_id", user_id).eq("service", service).execute()
            
            return len(response.data or []) > 0
        except Exception as e:
            logger.error(f"Error checking credentials: {e}")
            return False
    
    # ==================== Audit Logging ====================
    
    async def log_action(
        self,
        user_id: str,
        session_id: str,
        action_type: str,
        request_summary: str,
        response_summary: str = None,
        status: str = "pending",
        tokens_used: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read: int = 0,
        cache_write: int = 0,
        cache_write_5m: int = 0,
        cache_write_1h: int = 0,
        error_message: str = None
    ) -> Optional[int]:
        """Log an action to the audit table"""
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return None

            data = {
                "user_id": user_id,
                "session_id": session_id,
                "action_type": action_type,
                "request_summary": request_summary[:500] if request_summary else None,
                "response_summary": response_summary[:500] if response_summary else None,
                "status": status,
                "tokens_used": tokens_used,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read": cache_read,
                "cache_write": cache_write,
                "cache_write_5m": cache_write_5m,
                "cache_write_1h": cache_write_1h,
                "error_message": error_message
            }
            
            response = self._client.table("tbl_clawdbot_audit_log").insert(data).execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0].get('id')
            return None
        except Exception as e:
            logger.error(f"Error logging action: {e}")
            return None
    
    async def update_action_log(
        self,
        log_id: int,
        status: str,
        response_summary: str = None,
        tokens_used: int = None,
        input_tokens: int = None,
        output_tokens: int = None,
        cache_read: int = None,
        cache_write: int = None,
        cache_write_5m: int = None,
        cache_write_1h: int = None,
        error_message: str = None
    ) -> bool:
        """Update an existing audit log entry"""
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return False

            data = {"status": status}

            if response_summary:
                data["response_summary"] = response_summary[:500]
            if tokens_used is not None:
                data["tokens_used"] = tokens_used
            if input_tokens is not None:
                data["input_tokens"] = input_tokens
            if output_tokens is not None:
                data["output_tokens"] = output_tokens
            if cache_read is not None:
                data["cache_read"] = cache_read
            if cache_write is not None:
                data["cache_write"] = cache_write
            if cache_write_5m is not None:
                data["cache_write_5m"] = cache_write_5m
            if cache_write_1h is not None:
                data["cache_write_1h"] = cache_write_1h
            if error_message:
                data["error_message"] = error_message
            
            self._client.table("tbl_clawdbot_audit_log").update(data).eq("id", log_id).execute()
            
            return True
        except Exception as e:
            logger.error(f"Error updating action log: {e}")
            return False
    
    async def get_user_action_history(
        self, 
        user_id: str, 
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get action history for a user"""
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return []
            
            response = self._client.table("tbl_clawdbot_audit_log").select(
                "id, session_id, action_type, request_summary, response_summary, status, tokens_used, input_tokens, output_tokens, cache_read, cache_write, cache_write_5m, cache_write_1h, created_at"
            ).eq("user_id", user_id).order(
                "created_at", desc=True
            ).range(offset, offset + limit - 1).execute()
            
            return response.data or []
        except Exception as e:
            logger.error(f"Error getting action history: {e}")
            return []
    
    # ==================== Token Usage ====================

    async def get_token_usage(
        self,
        user_id: str = None,
        date_from: str = None,
        date_to: str = None,
        action_type: str = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        Get token usage data from audit log with optional filters.
        Supports cross-user queries (user_id=None returns all users).
        """
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return []

            query = self._client.table("tbl_clawdbot_audit_log").select(
                "id, user_id, session_id, action_type, request_summary, response_summary, status, tokens_used, input_tokens, output_tokens, cache_read, cache_write, cache_write_5m, cache_write_1h, created_at"
            )

            if user_id:
                query = query.eq("user_id", user_id)

            if date_from:
                query = query.gte("created_at", date_from)

            if date_to:
                query = query.lte("created_at", date_to)

            if action_type and action_type != "all":
                query = query.eq("action_type", action_type)

            response = query.order("created_at", desc=True).limit(limit).execute()

            return response.data or []
        except Exception as e:
            logger.error(f"Error getting token usage: {e}")
            return []

    # ==================== Rate Limit Functions ====================
    # Note: Rate limiting is handled by Peppi (Laravel), not here.
    # These functions are kept as stubs for potential future use.
    
    async def get_user_tier(self, user_id: str) -> Dict[str, Any]:
        """Get user's tier - Note: Rate limiting handled by Peppi"""
        return {
            "tier": "free",
            "max_daily_requests": settings.FREE_TIER_DAILY_LIMIT,
            "daily_requests": 0
        }
    
    async def increment_daily_usage(self, user_id: str) -> bool:
        """Increment daily usage - Note: Rate limiting handled by Peppi"""
        return True
    
    async def reset_daily_limit(self, user_id: str) -> bool:
        """Reset daily limit - Note: Rate limiting handled by Peppi"""
        return True
    
    # ==================== Reminders ====================
    
    async def create_reminder(self, data: dict) -> dict:
        """
        Insert a new reminder into tbl_clawdbot_reminders.
        
        Args:
            data: Dict with user_id, message, trigger_at, user_timezone, recurrence, etc.
            
        Returns:
            The created reminder row as a dict, or None on failure.
        """
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return None
            
            response = self._client.table("tbl_clawdbot_reminders").insert(data).execute()
            
            if response.data and len(response.data) > 0:
                logger.info(f"Created reminder for user {data.get('user_id')}: {response.data[0].get('id')}")
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Error creating reminder: {e}")
            return None
    
    async def get_reminder(self, reminder_id: int) -> dict:
        """Fetch a single reminder by ID."""
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return None
            
            response = self._client.table("tbl_clawdbot_reminders").select("*").eq(
                "id", reminder_id
            ).execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Error getting reminder {reminder_id}: {e}")
            return None
    
    async def update_reminder(self, reminder_id: int, data: dict) -> bool:
        """
        Update reminder fields (status, qstash_message_id, delivered_at, etc.).
        
        Args:
            reminder_id: ID of the reminder to update
            data: Dict of fields to update
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return False
            
            self._client.table("tbl_clawdbot_reminders").update(data).eq(
                "id", reminder_id
            ).execute()
            
            logger.info(f"Updated reminder {reminder_id}: {list(data.keys())}")
            return True
        except Exception as e:
            logger.error(f"Error updating reminder {reminder_id}: {e}")
            return False
    
    async def get_user_reminders(self, user_id: str, status: str = None) -> list:
        """
        Get all reminders for a user, optionally filtered by status.
        
        Args:
            user_id: Peppi user ID
            status: Optional filter ('pending', 'delivered', 'failed', 'cancelled')
            
        Returns:
            List of reminder dicts, sorted by trigger_at descending
        """
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return []
            
            query = self._client.table("tbl_clawdbot_reminders").select("*").eq(
                "user_id", user_id
            )
            
            if status:
                query = query.eq("status", status)
            
            response = query.order("trigger_at", desc=True).execute()
            
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Error getting reminders for user {user_id}: {e}")
            return []
    
    async def cancel_reminder(self, reminder_id: int) -> bool:
        """Set reminder status to 'cancelled'."""
        return await self.update_reminder(reminder_id, {"status": "cancelled"})
    
    # ==================== Outbound SMS Log ====================
    
    async def log_outbound_sms(
        self,
        user_id: str,
        message: str,
        source: str = "unknown",
        priority: str = "normal",
    ) -> bool:
        """
        Log an outbound SMS delivery to tbl_clawdbot_sms_log.
        Used by the dummy SMS stub endpoint for verifying reminder timing.
        """
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return False
            
            self._client.table("tbl_clawdbot_sms_log").insert({
                "user_id": user_id,
                "message": message,
                "source": source,
                "priority": priority,
            }).execute()
            
            logger.info(f"Logged outbound SMS for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error logging outbound SMS: {e}")
            return False
    
    # ==================== User Management ====================
    
    # Columns selected by user-listing endpoints. Kept as a class attribute so
    # the city/no-city fallback paths (used while migration 007 is pending)
    # stay in sync with each other.
    _USER_SELECT_WITH_CITY = "user_id, name, email, google_connected, timezone, city, created_at"
    _USER_SELECT_FALLBACK = "user_id, name, email, google_connected, timezone, created_at"

    @staticmethod
    def _is_missing_city_column_error(exc: Exception) -> bool:
        """Detect Postgres/PostgREST 'column does not exist' errors for `city`.

        Used to gracefully degrade when migration 007_add_city_column.sql has
        not yet been applied. Once the migration is live this branch is dead
        code but kept as a safety net.
        """
        msg = str(exc).lower()
        return "city" in msg and (
            "does not exist" in msg
            or "could not find the" in msg
            or "42703" in msg  # Postgres undefined_column SQLSTATE
        )

    async def upsert_user(
        self,
        user_id: str,
        name: str,
        email: str = None,
        google_connected: bool = False,
        timezone: str = None,
        city: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Create or update a user in tbl_clawdbot_users.
        Called during OAuth completion and playground user creation.

        `city` is optional and is omitted from the upsert when None so that
        it does not clobber an existing value on follow-up upserts that
        only know name/timezone (e.g. the OAuth completion path).
        """
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return None

            data = {
                "user_id": user_id,
                "name": name,
                "google_connected": google_connected,
                "updated_at": datetime.utcnow().isoformat()
            }
            if email:
                data["email"] = email
            if timezone:
                data["timezone"] = timezone
            if city is not None:
                # Treat empty string as "clear the city" rather than "leave alone".
                data["city"] = city or None

            try:
                response = self._client.table("tbl_clawdbot_users").upsert(
                    data,
                    on_conflict="user_id"
                ).execute()
            except Exception as e:
                # If the city column doesn't exist yet (migration 007 not run),
                # retry without city so user creation still works.
                if "city" in data and self._is_missing_city_column_error(e):
                    logger.warning(
                        "tbl_clawdbot_users.city column missing; retrying upsert "
                        "without city. Run migration 007_add_city_column.sql."
                    )
                    data.pop("city", None)
                    response = self._client.table("tbl_clawdbot_users").upsert(
                        data,
                        on_conflict="user_id"
                    ).execute()
                else:
                    raise

            if response.data and len(response.data) > 0:
                logger.info(f"Upserted user {user_id}: {name}")
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Error upserting user {user_id}: {e}")
            return None

    async def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users from tbl_clawdbot_users, ordered by name."""
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return []

            try:
                response = self._client.table("tbl_clawdbot_users").select(
                    self._USER_SELECT_WITH_CITY
                ).order("name").execute()
            except Exception as e:
                if self._is_missing_city_column_error(e):
                    logger.warning(
                        "tbl_clawdbot_users.city column missing; falling back to "
                        "select without city. Run migration 007_add_city_column.sql."
                    )
                    response = self._client.table("tbl_clawdbot_users").select(
                        self._USER_SELECT_FALLBACK
                    ).order("name").execute()
                else:
                    raise

            return response.data or []
        except Exception as e:
            logger.error(f"Error fetching users: {e}")
            return []

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a single user by user_id."""
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return None

            try:
                response = self._client.table("tbl_clawdbot_users").select(
                    self._USER_SELECT_WITH_CITY
                ).eq("user_id", user_id).execute()
            except Exception as e:
                if self._is_missing_city_column_error(e):
                    response = self._client.table("tbl_clawdbot_users").select(
                        self._USER_SELECT_FALLBACK
                    ).eq("user_id", user_id).execute()
                else:
                    raise

            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Error fetching user {user_id}: {e}")
            return None

    async def generate_user_id(self) -> str:
        """
        Generate a unique alphanumeric user_id (e.g. 'usr_<32 hex>').

        128-bit, was 32-bit (P3-5). `token_hex(4)` is only ~4.3e9 values: guessable by
        brute force, and birthday-colliding at ~65k users. user_id is the identifier every
        route keys off, so a guessable one erodes the whole access-control story.
        Width: 4 + 32 = 36 chars, inside the VARCHAR(50) column (migration 005). Existing
        short ids keep working — this only affects newly-minted ones.
        """
        return f"usr_{secrets.token_hex(16)}"

    async def update_user_timezone(self, user_id: str, timezone: str) -> bool:
        """Update a user's timezone setting."""
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return False

            self._client.table("tbl_clawdbot_users").update({
                "timezone": timezone,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("user_id", user_id).execute()

            logger.info(f"Updated timezone for user {user_id}: {timezone}")
            return True
        except Exception as e:
            logger.error(f"Error updating timezone for user {user_id}: {e}")
            return False

    async def update_user_city(self, user_id: str, city: Optional[str]) -> bool:
        """Update a user's city. Pass None or empty string to clear it."""
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return False

            payload = {
                # Empty string -> NULL so we don't end up with falsy garbage values.
                "city": city or None,
                "updated_at": datetime.utcnow().isoformat(),
            }
            self._client.table("tbl_clawdbot_users").update(payload).eq(
                "user_id", user_id
            ).execute()

            logger.info(f"Updated city for user {user_id}: {city!r}")
            return True
        except Exception as e:
            if self._is_missing_city_column_error(e):
                logger.error(
                    "tbl_clawdbot_users.city column missing — run migration "
                    "007_add_city_column.sql in the Supabase SQL Editor before "
                    "calling this endpoint."
                )
            else:
                logger.error(f"Error updating city for user {user_id}: {e}")
            return False

    async def update_google_connected(self, user_id: str, connected: bool) -> bool:
        """Update a user's google_connected flag (e.g., after OAuth revocation)."""
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return False

            self._client.table("tbl_clawdbot_users").update({
                "google_connected": connected,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("user_id", user_id).execute()

            logger.info(f"Updated google_connected for user {user_id}: {connected}")
            return True
        except Exception as e:
            logger.error(f"Error updating google_connected for user {user_id}: {e}")
            return False

    async def delete_user(self, user_id: str) -> Dict[str, int]:
        """
        Hard-delete a user and all their personal data.

        Removes rows from tbl_clawdbot_users, tbl_clawdbot_credentials,
        and tbl_clawdbot_reminders. Audit log rows are intentionally kept
        (compliance / forensics) — they reference user_id by value, not FK.

        Returns a dict with per-table delete counts. Missing tables are
        treated as zero.
        """
        counts = {"users": 0, "credentials": 0, "reminders": 0}
        if not self._client:
            await self.initialize()
            if not self._client:
                return counts

        try:
            response = self._scoped(user_id).table("tbl_clawdbot_credentials").delete().eq(
                "user_id", user_id
            ).execute()
            counts["credentials"] = len(response.data or [])
        except Exception as e:
            logger.error(f"delete_user: credentials delete failed for {user_id}: {e}")

        try:
            response = self._client.table("tbl_clawdbot_reminders").delete().eq(
                "user_id", user_id
            ).execute()
            counts["reminders"] = len(response.data or [])
        except Exception as e:
            # Table may not exist in older deployments — non-fatal.
            logger.warning(f"delete_user: reminders delete skipped for {user_id}: {e}")

        try:
            response = self._client.table("tbl_clawdbot_users").delete().eq(
                "user_id", user_id
            ).execute()
            counts["users"] = len(response.data or [])
        except Exception as e:
            logger.error(f"delete_user: users delete failed for {user_id}: {e}")

        logger.info(f"Deleted user {user_id}: {counts}")
        return counts

    # ==================== Utility ====================

    async def health_check(self) -> bool:
        """Check database connectivity"""
        try:
            if not self._client:
                await self.initialize()
                if not self._client:
                    return False
            
            # Simple query to check connectivity
            response = self._client.table("tbl_clawdbot_credentials").select("id").limit(1).execute()
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False


# Singleton instance
db = Database()
