-- ============================================================================
-- 009 — Row Level Security policies for tbl_clawdbot_* (CASA 3.1.4 / P2-6)
--
-- STATUS: SAFE TO APPLY NOW (scaffolding). Run it in the Supabase SQL Editor as
-- the project owner (same as migrations 002/008). Full per-user ENFORCEMENT is
-- Phase 6 (the service_role→scoped-JWT cutover) — but applying this now is safe
-- and is the right thing to do:
--   * service_role (the app's key, BYPASSRLS) keeps working unchanged.
--   * peppi_readonly keeps reading — §3 below adds its preservation policy.
--   * The per-user policies (§2) sit INERT until the app connects with a scoped
--     JWT (Phase 6); until then they only deny any OTHER non-bypass role, which
--     is defense-in-depth, not a regression.
-- Before applying: confirm no consumer OTHER than service_role + peppi_readonly
-- reads these tables (anon/authenticated roles). If one exists, add its policy
-- first — otherwise it would see zero rows once RLS is enabled.
--
-- Why full ENFORCEMENT is still Phase 6 (not this migration):
--   The FastAPI wrapper connects to Supabase with the `service_role` key
--   (SUPABASE_KEY, app/core/database.py), which has BYPASSRLS — it IGNORES every
--   policy below. So these policies do not restrict the APP until the data layer
--   is migrated off service_role. That cutover requires the Phase-6 work:
--     1. Stop using service_role for per-user operations.
--     2. Mint a per-request JWT carrying the internal user_id as a custom claim
--        (these ids are NOT Supabase auth.users ids, so auth.uid() does not
--        apply — policies below key off request.jwt.claims ->> 'user_id').
--     3. Rewrite app/core/database.py to connect as a non-BYPASSRLS role and
--        attach that JWT per request; integration-test against live Supabase.
--
--   This file exists so the policies are defined, reviewed, and ready to apply
--   atomically with that cutover. Applying it EARLY is safe ONLY if you first
--   confirm the peppi_readonly preservation policy (§3) keeps analytics working.
--
-- Note on types: user_id is VARCHAR (migration 005), so all comparisons cast
-- the JWT claim to text.
-- ============================================================================

-- Helper: the authenticated end-user id from the request JWT (NULL if absent).
CREATE OR REPLACE FUNCTION app_current_user_id() RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT NULLIF(
        current_setting('request.jwt.claims', true)::json ->> 'user_id',
        ''
    )
$$;

-- ── 1. Enable + FORCE RLS on the four user-scoped tables ────────────────────
-- FORCE so that even the table owner is subject to policies. service_role still
-- bypasses (BYPASSRLS) — that is the app's current path and is intentional
-- until Phase 4.
ALTER TABLE tbl_clawdbot_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE tbl_clawdbot_credentials FORCE ROW LEVEL SECURITY;
ALTER TABLE tbl_clawdbot_users       ENABLE ROW LEVEL SECURITY;
ALTER TABLE tbl_clawdbot_users       FORCE ROW LEVEL SECURITY;
ALTER TABLE tbl_clawdbot_audit_log   ENABLE ROW LEVEL SECURITY;
ALTER TABLE tbl_clawdbot_audit_log   FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'tbl_clawdbot_reminders'
    ) THEN
        EXECUTE 'ALTER TABLE tbl_clawdbot_reminders ENABLE ROW LEVEL SECURITY';
        EXECUTE 'ALTER TABLE tbl_clawdbot_reminders FORCE ROW LEVEL SECURITY';
    END IF;
END $$;

-- ── 2. Per-user policies (enforced once the wrapper connects with a scoped
--       JWT instead of service_role — Phase 4) ────────────────────────────────
-- Each policy restricts every row operation to rows owned by the JWT's user_id.
DROP POLICY IF EXISTS rls_owner ON tbl_clawdbot_credentials;
CREATE POLICY rls_owner ON tbl_clawdbot_credentials
    USING (user_id = app_current_user_id())
    WITH CHECK (user_id = app_current_user_id());

DROP POLICY IF EXISTS rls_owner ON tbl_clawdbot_users;
CREATE POLICY rls_owner ON tbl_clawdbot_users
    USING (user_id = app_current_user_id())
    WITH CHECK (user_id = app_current_user_id());

DROP POLICY IF EXISTS rls_owner ON tbl_clawdbot_audit_log;
CREATE POLICY rls_owner ON tbl_clawdbot_audit_log
    USING (user_id = app_current_user_id())
    WITH CHECK (user_id = app_current_user_id());

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'tbl_clawdbot_reminders'
    ) THEN
        EXECUTE 'DROP POLICY IF EXISTS rls_owner ON tbl_clawdbot_reminders';
        EXECUTE 'CREATE POLICY rls_owner ON tbl_clawdbot_reminders '
             || 'USING (user_id = app_current_user_id()) '
             || 'WITH CHECK (user_id = app_current_user_id())';
    END IF;
END $$;

-- ── 3. Preserve peppi_readonly analytics access (migration 008) ─────────────
-- peppi_readonly does NOT bypass RLS, so without this it would read zero rows
-- once RLS is enabled. It gets read-only visibility of the same columns it was
-- granted in 008 (it was never granted the encrypted token blob). This keeps
-- Peppi's direct-DB analytics working after the cutover.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'peppi_readonly') THEN
        DROP POLICY IF EXISTS rls_peppi_readonly ON tbl_clawdbot_users;
        EXECUTE 'CREATE POLICY rls_peppi_readonly ON tbl_clawdbot_users '
             || 'FOR SELECT TO peppi_readonly USING (true)';

        DROP POLICY IF EXISTS rls_peppi_readonly ON tbl_clawdbot_audit_log;
        EXECUTE 'CREATE POLICY rls_peppi_readonly ON tbl_clawdbot_audit_log '
             || 'FOR SELECT TO peppi_readonly USING (true)';

        DROP POLICY IF EXISTS rls_peppi_readonly ON tbl_clawdbot_credentials;
        EXECUTE 'CREATE POLICY rls_peppi_readonly ON tbl_clawdbot_credentials '
             || 'FOR SELECT TO peppi_readonly USING (true)';
    END IF;
END $$;

-- ── Verification (run as project owner after applying, at Phase 4) ──────────
--   SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class
--     WHERE relname LIKE 'tbl_clawdbot_%';
--   SET request.jwt.claims = '{"user_id":"usr_abc"}';
--   -- as a scoped (non-BYPASSRLS) role: SELECT should return only usr_abc rows.
-- ============================================================================
