-- Add detailed token tracking columns to audit log
-- These columns support the token usage breakdown (input/output/cache)
-- that was added to the application code but missing from the schema.

ALTER TABLE tbl_clawdbot_audit_log
  ADD COLUMN IF NOT EXISTS input_tokens INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS output_tokens INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cache_read INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cache_write INTEGER DEFAULT 0;
