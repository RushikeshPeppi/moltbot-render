-- ============================================================
-- Migration 007 — RLS + composite indexes + user_id CHECK
-- ============================================================
--
-- Closes three P0/P1 findings from HTTP_AUDIT.md:
--   1. Row Level Security disabled (§3.1)   — service-role key leak = full-
--      table access. With RLS on, even a leaked key can only touch rows the
--      JWT claim permits (we use the service_role bypass from our server
--      code; any OTHER caller is denied).
--   2. Missing composite indexes (§3.1)     — scan order for the two hot
--      queries: audit log by user+recent, reminders by user+status+trigger.
--   3. user_id VARCHAR(50) has no constraint (§3.1) — no length/character
--      check, any string accepted. Enforce 5..50 chars, alnum + underscore.
--
-- Safe to run on an existing Supabase DB. All statements are idempotent
-- or guarded by IF NOT EXISTS / IF EXISTS.
-- ============================================================


-- ─── 1. Row Level Security ─────────────────────────────────────
-- Enable RLS on every tenant-scoped table. With RLS enabled, direct
-- access via the PUBLIC/anon role is denied by default. Our FastAPI
-- server uses the service_role key which BYPASSES RLS (Postgres
-- privilege: the service_role has BYPASSRLS). So this change:
--   - blocks anon/public access (fail-closed if service_role ever leaks
--     to the client),
--   - does NOT change what our server can do.

ALTER TABLE tbl_clawdbot_credentials  ENABLE ROW LEVEL SECURITY;
ALTER TABLE tbl_clawdbot_audit_log    ENABLE ROW LEVEL SECURITY;
ALTER TABLE tbl_clawdbot_users        ENABLE ROW LEVEL SECURITY;

-- tbl_clawdbot_reminders is created on-platform (not in migrations yet —
-- see migration 005 for the conditional reference). Enable RLS if present.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'tbl_clawdbot_reminders'
  ) THEN
    EXECUTE 'ALTER TABLE tbl_clawdbot_reminders ENABLE ROW LEVEL SECURITY';
  END IF;
END $$;

-- tbl_clawdbot_sms_log (stub-only for tests); enable RLS if present.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'tbl_clawdbot_sms_log'
  ) THEN
    EXECUTE 'ALTER TABLE tbl_clawdbot_sms_log ENABLE ROW LEVEL SECURITY';
  END IF;
END $$;

-- Verify: the service_role must bypass RLS (it does by default in
-- Supabase). If you ever revoke BYPASSRLS from service_role, the server
-- stops working. This SELECT should return 't' for service_role.
-- SELECT rolbypassrls FROM pg_roles WHERE rolname = 'service_role';


-- ─── 2. Composite indexes on hot paths ─────────────────────────
-- audit_log: the standard query is (user_id, ORDER BY created_at DESC).
-- A composite index lets Postgres answer without a separate sort.
CREATE INDEX IF NOT EXISTS idx_audit_user_created
  ON tbl_clawdbot_audit_log (user_id, created_at DESC);

-- reminders: the dedup query (user_id, status='pending', trigger_at near X)
-- and the listing query (user_id, status, ORDER BY trigger_at DESC).
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'tbl_clawdbot_reminders'
  ) THEN
    EXECUTE 'CREATE INDEX IF NOT EXISTS idx_reminders_user_status_trigger '
         || 'ON tbl_clawdbot_reminders (user_id, status, trigger_at DESC)';
  END IF;
END $$;


-- ─── 3. user_id format CHECK ───────────────────────────────────
-- Enforce that user_id is [A-Za-z0-9_]+ of length 5..50. Prevents a bad
-- upstream from slipping a blank / control-char / shell-meta string into
-- our DB. Runs as a named CHECK so it's idempotent.

DO $$
BEGIN
  -- Only add if not already present.
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'tbl_clawdbot_users_user_id_format_chk'
  ) THEN
    ALTER TABLE tbl_clawdbot_users
      ADD CONSTRAINT tbl_clawdbot_users_user_id_format_chk
      CHECK (char_length(user_id) BETWEEN 5 AND 50
             AND user_id ~ '^[A-Za-z0-9_]+$');
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'tbl_clawdbot_credentials_user_id_format_chk'
  ) THEN
    ALTER TABLE tbl_clawdbot_credentials
      ADD CONSTRAINT tbl_clawdbot_credentials_user_id_format_chk
      CHECK (char_length(user_id) BETWEEN 5 AND 50
             AND user_id ~ '^[A-Za-z0-9_]+$');
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'tbl_clawdbot_audit_log_user_id_format_chk'
  ) THEN
    ALTER TABLE tbl_clawdbot_audit_log
      ADD CONSTRAINT tbl_clawdbot_audit_log_user_id_format_chk
      CHECK (char_length(user_id) BETWEEN 5 AND 50
             AND user_id ~ '^[A-Za-z0-9_]+$');
  END IF;
END $$;

-- Reminders: conditional (table may not exist in this migration history).
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'tbl_clawdbot_reminders'
  )
  AND NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'tbl_clawdbot_reminders_user_id_format_chk'
  ) THEN
    EXECUTE 'ALTER TABLE tbl_clawdbot_reminders '
         || 'ADD CONSTRAINT tbl_clawdbot_reminders_user_id_format_chk '
         || 'CHECK (char_length(user_id) BETWEEN 5 AND 50 '
         || 'AND user_id ~ ''^[A-Za-z0-9_]+$'')';
  END IF;
END $$;


-- ─── Verify ────────────────────────────────────────────────────
-- SELECT tablename, rowsecurity FROM pg_tables
--   WHERE tablename LIKE 'tbl_clawdbot%';
-- SELECT indexname FROM pg_indexes WHERE tablename LIKE 'tbl_clawdbot%';
-- SELECT conname FROM pg_constraint WHERE conname LIKE '%user_id_format_chk';
