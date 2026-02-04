-- ============================================
-- ClawdBot MySQL Migration Script
-- Run this on your dashtech_peppi database
-- ============================================

-- 1. Encrypted user credentials for ClawdBot services
CREATE TABLE IF NOT EXISTS tbl_clawdbot_credentials (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    service VARCHAR(50) NOT NULL,
    encrypted_credentials TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL,
    UNIQUE KEY unique_user_service (user_id, service),
    INDEX idx_user_id (user_id),
    INDEX idx_service (service)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Audit log for all ClawdBot actions
CREATE TABLE IF NOT EXISTS tbl_clawdbot_audit_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    session_id VARCHAR(100) NOT NULL,
    action_type VARCHAR(50) NOT NULL,
    request_summary TEXT,
    response_summary TEXT,
    status ENUM('success', 'failed', 'pending') DEFAULT 'pending',
    error_message TEXT NULL,
    tokens_used INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_session_id (session_id),
    INDEX idx_action_type (action_type),
    INDEX idx_created_at (created_at),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Rate limit tracking is handled by Peppi (Laravel)
-- Table removed - Peppi will enforce rate limits before calling this API

-- ============================================
-- Verify tables were created
-- ============================================
SHOW TABLES LIKE 'tbl_clawdbot%';

-- ============================================
-- Sample queries for testing
-- ============================================

-- Check credentials for a user:
-- SELECT * FROM tbl_clawdbot_credentials WHERE user_id = 123;

-- Get recent audit logs:
-- SELECT * FROM tbl_clawdbot_audit_log ORDER BY created_at DESC LIMIT 20;

-- Check rate limits:
-- SELECT * FROM tbl_clawdbot_rate_limits WHERE user_id = 123;
