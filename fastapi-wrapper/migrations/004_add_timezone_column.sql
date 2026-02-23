-- ============================================
-- Add timezone column to tbl_clawdbot_users
-- Run this in Supabase SQL Editor
-- ============================================

ALTER TABLE tbl_clawdbot_users
ADD COLUMN IF NOT EXISTS timezone VARCHAR(50) DEFAULT 'UTC';

-- Backfill existing rows
UPDATE tbl_clawdbot_users SET timezone = 'UTC' WHERE timezone IS NULL;

-- ============================================
-- Verify
-- ============================================
-- SELECT user_id, name, timezone FROM tbl_clawdbot_users;
