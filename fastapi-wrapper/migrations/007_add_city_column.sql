-- ============================================
-- Add city column to tbl_clawdbot_users
-- Run this in Supabase SQL Editor
--
-- Purpose: power the web-search skill's "near me" handling. The gateway
-- reads userContext.city and exports it as $USER_CITY into OpenClaw, so
-- queries like "best restaurants near me" can be rewritten with a city
-- before hitting SearXNG. NULL is allowed because existing users don't
-- have a city yet — the playground UI prompts them on next login.
-- ============================================

ALTER TABLE tbl_clawdbot_users
ADD COLUMN IF NOT EXISTS city VARCHAR(100) NULL;

-- Existing rows stay NULL on purpose. The playground frontend triggers
-- a one-time prompt for users whose city is NULL the next time they log in.

-- ============================================
-- Verify
-- ============================================
-- SELECT user_id, name, timezone, city FROM tbl_clawdbot_users ORDER BY name;
