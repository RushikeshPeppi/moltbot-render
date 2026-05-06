-- Migration: split cache_write into 5m and 1h TTL columns
-- Date: 2026-05-06
-- Reason: billing math correctness. Anthropic charges different rates for
--   ephemeral_5m_input_tokens (1.25× input rate, ~$3.75/MT for Sonnet 4.6)
--   ephemeral_1h_input_tokens (2.00× input rate, ~$6.00/MT for Sonnet 4.6)
-- The legacy `cache_write` column stores the SUM of both, which forces us to
-- assume one rate and undercount the other. This migration adds the per-TTL
-- breakdown sent by the gateway since 2026-05.
--
-- Run this in the Supabase SQL editor for the project that hosts
-- tbl_clawdbot_audit_log.
--
-- Backwards compatibility: the legacy cache_write column is preserved so old
-- code paths still work. New code paths read both columns; any pre-existing
-- row keeps cache_write_5m = cache_write_1h = 0 (best-effort historical cost
-- estimate uses the legacy combined column).

ALTER TABLE tbl_clawdbot_audit_log
  ADD COLUMN IF NOT EXISTS cache_write_5m INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cache_write_1h INTEGER NOT NULL DEFAULT 0;

-- Sanity check: counts of rows by whether they have the new breakdown.
SELECT
  COUNT(*) FILTER (WHERE cache_write_5m > 0 OR cache_write_1h > 0) AS rows_with_breakdown,
  COUNT(*) FILTER (WHERE cache_write_5m = 0 AND cache_write_1h = 0 AND COALESCE(cache_write, 0) > 0) AS legacy_rows_only,
  COUNT(*) AS total
FROM tbl_clawdbot_audit_log;
