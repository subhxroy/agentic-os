-- Phase 4: Enterprise SaaS schema

-- ============================================================
-- ORG SETTINGS (security policies, retention, IP allowlist)
-- ============================================================
CREATE TABLE IF NOT EXISTS org_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID UNIQUE NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    -- Security policies
    ip_allowlist JSONB DEFAULT '[]',        -- list of CIDR ranges
    mfa_required BOOLEAN DEFAULT false,
    session_duration_hours INTEGER DEFAULT 24,
    max_sessions_per_user INTEGER DEFAULT 10,
    -- Data retention
    conversation_retention_days INTEGER DEFAULT 90,
    audit_retention_days INTEGER DEFAULT 365,
    auto_delete_expired BOOLEAN DEFAULT false,
    -- Compliance
    data_classification TEXT DEFAULT 'internal',  -- public, internal, confidential, restricted
    dpa_agreed BOOLEAN DEFAULT false,
    soc2_enabled BOOLEAN DEFAULT false,
    -- SSO (future)
    sso_provider TEXT,         -- okta, azure_ad, google, custom
    sso_config JSONB DEFAULT '{}',
    scim_enabled BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- GDPR REQUESTS (data export/deletion)
-- ============================================================
CREATE TABLE IF NOT EXISTS gdpr_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    request_type TEXT NOT NULL,  -- export, deletion, rectification
    status TEXT DEFAULT 'pending',  -- pending, processing, completed, failed
    file_path TEXT,                -- for exports: path to exported ZIP
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_gdpr_requests_user ON gdpr_requests(user_id, status);

-- ============================================================
-- SESSION POLICIES (per-org enforcement)
-- ============================================================
CREATE TABLE IF NOT EXISTS session_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    rules JSONB NOT NULL DEFAULT '{}',  -- {require_mfa: true, max_duration: 3600, ip_restrictions: [...]}
    priority INTEGER DEFAULT 0,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_session_policies_org ON session_policies(org_id, enabled);

-- ============================================================
-- COMPLIANCE SNAPSHOTS (periodic compliance status)
-- ============================================================
CREATE TABLE IF NOT EXISTS compliance_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    total_users INTEGER DEFAULT 0,
    active_users_30d INTEGER DEFAULT 0,
    total_sessions INTEGER DEFAULT 0,
    total_knowledge_docs INTEGER DEFAULT 0,
    audit_log_count INTEGER DEFAULT 0,
    gdpr_requests_pending INTEGER DEFAULT 0,
    mfa_enabled_pct REAL DEFAULT 0,
    data_classification TEXT DEFAULT 'internal',
    issues JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(org_id, snapshot_date)
);

-- ============================================================
-- RATE LIMIT CONFIG (per-org, customizable)
-- ============================================================
CREATE TABLE IF NOT EXISTS rate_limit_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID UNIQUE NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    requests_per_minute INTEGER DEFAULT 60,
    requests_per_hour INTEGER DEFAULT 1000,
    requests_per_day INTEGER DEFAULT 10000,
    tokens_per_day INTEGER DEFAULT 1000000,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- DATA EXPORT LOG (track who exported what)
-- ============================================================
CREATE TABLE IF NOT EXISTS export_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    org_id UUID REFERENCES organizations(id),
    export_type TEXT NOT NULL,  -- gdpr, audit, compliance, admin
    format TEXT DEFAULT 'json',  -- json, csv
    record_count INTEGER DEFAULT 0,
    file_path TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
