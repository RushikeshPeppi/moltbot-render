-- ============================================
-- Migrate user_id columns from INTEGER to VARCHAR(50)
-- for alphanumeric user ID support.
-- Run this in Supabase SQL Editor.
-- ============================================

-- 1. tbl_clawdbot_users
ALTER TABLE tbl_clawdbot_users
    ALTER COLUMN user_id TYPE VARCHAR(50) USING user_id::VARCHAR(50);

-- 2. tbl_clawdbot_credentials
ALTER TABLE tbl_clawdbot_credentials
    ALTER COLUMN user_id TYPE VARCHAR(50) USING user_id::VARCHAR(50);

-- 3. tbl_clawdbot_audit_log
ALTER TABLE tbl_clawdbot_audit_log
    ALTER COLUMN user_id TYPE VARCHAR(50) USING user_id::VARCHAR(50);

-- 4. tbl_clawdbot_reminders (if exists)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'tbl_clawdbot_reminders'
    ) THEN
        EXECUTE 'ALTER TABLE tbl_clawdbot_reminders ALTER COLUMN user_id TYPE VARCHAR(50) USING user_id::VARCHAR(50)';
    END IF;
END $$;

-- ============================================
-- Verify
-- ============================================
-- SELECT column_name, data_type FROM information_schema.columns
-- WHERE table_name LIKE 'tbl_clawdbot%' AND column_name = 'user_id';
