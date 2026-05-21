-- ============================================
-- Peppi read-only Postgres role for direct DB validation.
--
-- Run this in the Supabase SQL Editor as the project owner.
-- Replace <STRONG_PASSWORD> below with a generated secret BEFORE running,
-- and share the connection string with the Peppi team out-of-band
-- (1Password / Bitwarden — NEVER paste into the integration guide doc).
--
-- After running, Peppi can connect to:
--   postgres://peppi_readonly:<password>@<pooler-host>:6543/postgres?sslmode=require
-- and SELECT from the four tables below. They cannot INSERT/UPDATE/DELETE
-- anything, and they cannot read the encrypted_credentials blob.
-- ============================================

-- 1. Create the role (idempotent — skip if it already exists).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'peppi_readonly') THEN
        CREATE ROLE peppi_readonly LOGIN PASSWORD '<STRONG_PASSWORD>';
    END IF;
END $$;

-- 2. Schema access. CONNECT is granted to PUBLIC by default on Supabase;
--    we just need USAGE on the schema so the role can resolve table names.
GRANT USAGE ON SCHEMA public TO peppi_readonly;

-- 3. Per-table SELECT grants. tbl_clawdbot_credentials is column-restricted
--    so the role CANNOT read the Fernet-encrypted token blob.
GRANT SELECT ON tbl_clawdbot_users         TO peppi_readonly;
GRANT SELECT ON tbl_clawdbot_audit_log     TO peppi_readonly;

GRANT SELECT (user_id, service, expires_at, created_at, updated_at)
    ON tbl_clawdbot_credentials
    TO peppi_readonly;

-- tbl_clawdbot_reminders may not exist on every deployment — guard the grant.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'tbl_clawdbot_reminders'
    ) THEN
        EXECUTE 'GRANT SELECT ON tbl_clawdbot_reminders TO peppi_readonly';
    END IF;
END $$;

-- 4. Explicitly REVOKE any write permissions inherited from PUBLIC defaults.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE
    ON tbl_clawdbot_users,
       tbl_clawdbot_credentials,
       tbl_clawdbot_audit_log
    FROM peppi_readonly;

-- 5. Future-proofing: any NEW tables created in the public schema by the
--    Supabase project owner will NOT be auto-granted to peppi_readonly.
--    If a new table needs to be readable by Peppi, add an explicit GRANT
--    in a follow-up migration.

-- ============================================
-- Verification queries — run as the project owner to confirm.
-- ============================================
-- 1. Does the role exist with login?
--    SELECT rolname, rolcanlogin FROM pg_roles WHERE rolname = 'peppi_readonly';
--
-- 2. What can it SELECT?
--    SELECT table_name, column_name, privilege_type
--    FROM information_schema.column_privileges
--    WHERE grantee = 'peppi_readonly'
--    ORDER BY table_name, column_name;
--
-- 3. Smoke test — switch into the role and try a read + a write:
--    SET ROLE peppi_readonly;
--    SELECT count(*) FROM tbl_clawdbot_users;                  -- should succeed
--    SELECT encrypted_credentials FROM tbl_clawdbot_credentials LIMIT 1;
--                                                              -- should ERROR (column denied)
--    DELETE FROM tbl_clawdbot_users WHERE user_id = 'x';       -- should ERROR (permission denied)
--    RESET ROLE;
