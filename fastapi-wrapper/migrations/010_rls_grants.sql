-- ============================================================================
-- 010 — GRANTs for the `authenticated` role (Phase 6 · 1.6b / CASA 3.1.4)
--
-- WHY THIS EXISTS
-- Migration 009 defined the per-user policies but granted NOTHING. That is not an
-- oversight in 009 — it is the missing half of the cutover, and it must land WITH the
-- app change, not before it.
--
-- The distinction that makes this necessary:
--   * RLS decides WHICH ROWS a role may see.
--   * GRANT decides WHETHER THE ROLE MAY TOUCH THE TABLE AT ALL.
-- They are independent. Without a GRANT, the scoped `authenticated` role does not get
-- "zero rows" — it gets `permission denied for table ...`. So enabling RLS_SCOPED_JWT
-- without this migration does not silently weaken security; it hard-fails every
-- per-user credential operation (i.e. every Google connect / token read).
--
-- ORDER OF OPERATIONS (do not deviate):
--   1. Apply 009 (already done 2026-07-08).
--   2. Apply THIS migration.
--   3. Set SUPABASE_JWT_SECRET + SUPABASE_ANON_KEY on moltbot-fastapi.
--   4. Run tests/test_rls_isolation.py against live Supabase — it must show user A
--      CANNOT read user B's row.
--   5. Only then set RLS_SCOPED_JWT=true.
-- Rollback at any point: RLS_SCOPED_JWT=false. The app returns to the service_role
-- path immediately; nothing here needs reverting (these grants are inert while the app
-- connects as service_role).
--
-- SCOPE: deliberately NARROW. Only the tables carrying the per-user policies from 009,
-- and only the operations the app actually performs on them. `authenticated` gets NO
-- access to anything else, and no DELETE where the app never deletes.
-- ============================================================================

-- ── Credentials: the encrypted Google token blob. The app does upsert/select/delete
--    (store, get, get_all, check_exists, delete, and the account-teardown cascade).
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE tbl_clawdbot_credentials TO authenticated;

-- ── Users: upsert + read of the user's own row.
GRANT SELECT, INSERT, UPDATE ON TABLE tbl_clawdbot_users TO authenticated;

-- ── Audit log: the app inserts action rows and reads a user's own history.
--    No DELETE: the audit log is retained on account teardown by design (data-retention
--    policy) — never grant a scoped user the ability to erase their own audit trail.
GRANT SELECT, INSERT, UPDATE ON TABLE tbl_clawdbot_audit_log TO authenticated;

-- ── Reminders (if present).
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'tbl_clawdbot_reminders'
    ) THEN
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE tbl_clawdbot_reminders TO authenticated';
        -- Sequence access is required for INSERT on a serial/identity PK; without it the
        -- insert fails with "permission denied for sequence".
        EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated';
    END IF;
END $$;

-- Sequences for the audit log's identity column (same reason as above).
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;

-- ── Verification (run as project owner AFTER applying) ──────────────────────
--   -- 1. Grants landed?
--   SELECT grantee, table_name, privilege_type
--     FROM information_schema.role_table_grants
--    WHERE grantee = 'authenticated' AND table_name LIKE 'tbl_clawdbot_%'
--    ORDER BY table_name, privilege_type;
--
--   -- 2. RLS actually filters for a scoped role (the test that matters):
--   SET ROLE authenticated;
--   SET request.jwt.claims = '{"role":"authenticated","user_id":"<USER_A>"}';
--   SELECT user_id FROM tbl_clawdbot_credentials;   -- expect: ONLY <USER_A> rows
--   SET request.jwt.claims = '{"role":"authenticated","user_id":"<USER_B>"}';
--   SELECT user_id FROM tbl_clawdbot_credentials;   -- expect: ONLY <USER_B> rows
--   RESET ROLE;
--
--   -- 3. peppi_readonly analytics still works (009 §3 preservation policy):
--   SET ROLE peppi_readonly;
--   SELECT count(*) FROM tbl_clawdbot_users;        -- expect: > 0, not an error
--   RESET ROLE;
-- ============================================================================
