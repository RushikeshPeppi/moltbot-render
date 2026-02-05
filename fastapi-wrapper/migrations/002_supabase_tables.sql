-- ============================================
-- ClawdBot Supabase (PostgreSQL) Migration Script
-- Run this in Supabase SQL Editor
-- ============================================

-- 1. Encrypted user credentials for ClawdBot services
CREATE TABLE IF NOT EXISTS tbl_clawdbot_credentials (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    service VARCHAR(50) NOT NULL,
    encrypted_credentials TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NULL,
    UNIQUE (user_id, service)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_credentials_user_id ON tbl_clawdbot_credentials(user_id);
CREATE INDEX IF NOT EXISTS idx_credentials_service ON tbl_clawdbot_credentials(service);

-- 2. Audit log for all ClawdBot actions
CREATE TABLE IF NOT EXISTS tbl_clawdbot_audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    session_id VARCHAR(100) NOT NULL,
    action_type VARCHAR(50) NOT NULL,
    request_summary TEXT,
    response_summary TEXT,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('success', 'failed', 'pending')),
    error_message TEXT NULL,
    tokens_used INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_audit_user_id ON tbl_clawdbot_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_session_id ON tbl_clawdbot_audit_log(session_id);
CREATE INDEX IF NOT EXISTS idx_audit_action_type ON tbl_clawdbot_audit_log(action_type);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON tbl_clawdbot_audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_status ON tbl_clawdbot_audit_log(status);

-- 3. Function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 4. Trigger for auto-updating updated_at on credentials
DROP TRIGGER IF EXISTS update_credentials_updated_at ON tbl_clawdbot_credentials;
CREATE TRIGGER update_credentials_updated_at
    BEFORE UPDATE ON tbl_clawdbot_credentials
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- Enable Row Level Security (optional but recommended)
-- ============================================
-- ALTER TABLE tbl_clawdbot_credentials ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE tbl_clawdbot_audit_log ENABLE ROW LEVEL SECURITY;

-- ============================================
-- Verify tables were created
-- ============================================
-- SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';
