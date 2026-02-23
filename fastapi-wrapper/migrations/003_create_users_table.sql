-- ============================================
-- ClawdBot Users Table Migration
-- Run this in Supabase SQL Editor
-- ============================================

-- Users table for ClawdBot / Playground
CREATE TABLE IF NOT EXISTS tbl_clawdbot_users (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NULL,
    google_connected BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_users_user_id ON tbl_clawdbot_users(user_id);
CREATE INDEX IF NOT EXISTS idx_users_name ON tbl_clawdbot_users(name);

-- Auto-update updated_at trigger
DROP TRIGGER IF EXISTS update_users_updated_at ON tbl_clawdbot_users;
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON tbl_clawdbot_users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- Verify
-- ============================================
-- SELECT * FROM tbl_clawdbot_users ORDER BY user_id;
