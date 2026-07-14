"""
SQLite schema migration — all 49 tables from Phases 0-7.
Translated from PostgreSQL to SQLite. Run on startup before server starts.
"""

SCHEMA_SQL = """
-- ============================================================
-- PHASE 0: Core tables
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    goal TEXT,
    state TEXT DEFAULT 'active',
    metadata TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    tool_calls TEXT,
    tool_results TEXT,
    token_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id, created_at);

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    memory_type TEXT NOT NULL DEFAULT 'key_value',
    key TEXT NOT NULL,
    content TEXT NOT NULL,
    importance REAL DEFAULT 0.5,
    access_count INTEGER DEFAULT 0,
    last_accessed_at TEXT DEFAULT (datetime('now')),
    embedding TEXT,
    metadata TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, key)
);
CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id, memory_type);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    title TEXT,
    source_type TEXT NOT NULL,
    source_url TEXT,
    file_path TEXT,
    file_hash TEXT,
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    chunk_count INTEGER DEFAULT 0,
    token_count INTEGER DEFAULT 0,
    kb_id TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id, status);
CREATE INDEX IF NOT EXISTS idx_documents_kb ON documents(kb_id);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    embedding TEXT,
    metadata TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);

-- ============================================================
-- PHASE 2: Organizations + multi-tenancy
-- ============================================================

CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_id TEXT NOT NULL REFERENCES users(id),
    settings TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS org_members (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member',
    joined_at TEXT DEFAULT (datetime('now')),
    UNIQUE(org_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_org_members_user ON org_members(user_id);
CREATE INDEX IF NOT EXISTS idx_org_members_org ON org_members(org_id);

CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id TEXT REFERENCES organizations(id) ON DELETE CASCADE,
    key_hash TEXT NOT NULL,
    name TEXT,
    scopes TEXT DEFAULT '["read", "write"]',
    expires_at TEXT,
    last_used_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    app_id TEXT,
    rate_limit INTEGER DEFAULT 1000
);
CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);

CREATE TABLE IF NOT EXISTS rate_limits (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    endpoint TEXT NOT NULL,
    window_start TEXT DEFAULT (datetime('now')),
    request_count INTEGER DEFAULT 1,
    UNIQUE(user_id, endpoint, window_start)
);

-- ============================================================
-- PHASE 3: Team Collaboration
-- ============================================================

CREATE TABLE IF NOT EXISTS invitations (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    invited_by TEXT NOT NULL REFERENCES users(id),
    token TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'pending',
    expires_at TEXT DEFAULT (datetime('now', '+7 days')),
    created_at TEXT DEFAULT (datetime('now')),
    accepted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_invitations_org ON invitations(org_id, status);
CREATE INDEX IF NOT EXISTS idx_invitations_email ON invitations(email, status);
CREATE INDEX IF NOT EXISTS idx_invitations_token ON invitations(token);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    org_id TEXT REFERENCES organizations(id) ON DELETE SET NULL,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    details TEXT DEFAULT '{}',
    ip_address TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_log_org ON audit_log(org_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action, created_at);

CREATE TABLE IF NOT EXISTS knowledge_bases (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    visibility TEXT DEFAULT 'org',
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_kb_org ON knowledge_bases(org_id);

CREATE TABLE IF NOT EXISTS agent_templates (
    id TEXT PRIMARY KEY,
    org_id TEXT REFERENCES organizations(id) ON DELETE SET NULL,
    created_by TEXT NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    description TEXT,
    system_prompt TEXT,
    tools TEXT DEFAULT '[]',
    model_config TEXT DEFAULT '{}',
    tags TEXT DEFAULT '[]',
    visibility TEXT DEFAULT 'private',
    fork_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_templates_org ON agent_templates(org_id);

CREATE TABLE IF NOT EXISTS template_forks (
    id TEXT PRIMARY KEY,
    original_id TEXT NOT NULL REFERENCES agent_templates(id) ON DELETE CASCADE,
    forked_id TEXT NOT NULL REFERENCES agent_templates(id) ON DELETE CASCADE,
    forked_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS comments (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id),
    parent_id TEXT REFERENCES comments(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    comment_type TEXT DEFAULT 'comment',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_comments_session ON comments(session_id, created_at);

CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    message_id INTEGER REFERENCES conversations(id) ON DELETE SET NULL,
    user_id TEXT NOT NULL REFERENCES users(id),
    rating INTEGER NOT NULL,
    comment TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(session_id, message_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_feedback_session ON feedback(session_id);

-- ============================================================
-- PHASE 4: Enterprise SaaS
-- ============================================================

CREATE TABLE IF NOT EXISTS org_settings (
    id TEXT PRIMARY KEY,
    org_id TEXT UNIQUE NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    ip_allowlist TEXT DEFAULT '[]',
    mfa_required INTEGER DEFAULT 0,
    session_duration_hours INTEGER DEFAULT 24,
    max_sessions_per_user INTEGER DEFAULT 10,
    conversation_retention_days INTEGER DEFAULT 90,
    audit_retention_days INTEGER DEFAULT 365,
    auto_delete_expired INTEGER DEFAULT 0,
    data_classification TEXT DEFAULT 'internal',
    dpa_agreed INTEGER DEFAULT 0,
    soc2_enabled INTEGER DEFAULT 0,
    sso_provider TEXT,
    sso_config TEXT DEFAULT '{}',
    scim_enabled INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS gdpr_requests (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    request_type TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    file_path TEXT,
    completed_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_gdpr_requests_user ON gdpr_requests(user_id, status);

CREATE TABLE IF NOT EXISTS session_policies (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    rules TEXT NOT NULL DEFAULT '{}',
    priority INTEGER DEFAULT 0,
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_session_policies_org ON session_policies(org_id, enabled);

CREATE TABLE IF NOT EXISTS compliance_snapshots (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    snapshot_date TEXT NOT NULL,
    total_users INTEGER DEFAULT 0,
    active_users_30d INTEGER DEFAULT 0,
    total_sessions INTEGER DEFAULT 0,
    total_knowledge_docs INTEGER DEFAULT 0,
    audit_log_count INTEGER DEFAULT 0,
    gdpr_requests_pending INTEGER DEFAULT 0,
    mfa_enabled_pct REAL DEFAULT 0,
    data_classification TEXT DEFAULT 'internal',
    issues TEXT DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(org_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS rate_limit_configs (
    id TEXT PRIMARY KEY,
    org_id TEXT UNIQUE NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    requests_per_minute INTEGER DEFAULT 60,
    requests_per_hour INTEGER DEFAULT 1000,
    requests_per_day INTEGER DEFAULT 10000,
    tokens_per_day INTEGER DEFAULT 1000000,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS export_log (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    org_id TEXT REFERENCES organizations(id),
    export_type TEXT NOT NULL,
    format TEXT DEFAULT 'json',
    record_count INTEGER DEFAULT 0,
    file_path TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- ============================================================
-- PHASE 5: Developer Ecosystem
-- ============================================================

CREATE TABLE IF NOT EXISTS apps (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id TEXT REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    redirect_uris TEXT DEFAULT '[]',
    scopes TEXT DEFAULT '["read","write"]',
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS api_usage (
    id TEXT PRIMARY KEY,
    api_key_id TEXT REFERENCES api_keys(id) ON DELETE SET NULL,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id TEXT REFERENCES organizations(id) ON DELETE CASCADE,
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL,
    status_code INTEGER,
    response_time_ms INTEGER,
    tokens_used INTEGER DEFAULT 0,
    model TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_api_usage_user ON api_usage(user_id);
CREATE INDEX IF NOT EXISTS idx_api_usage_org ON api_usage(org_id);
CREATE INDEX IF NOT EXISTS idx_api_usage_created ON api_usage(created_at);
CREATE INDEX IF NOT EXISTS idx_api_usage_api_key ON api_usage(api_key_id);

CREATE TABLE IF NOT EXISTS plugins (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    description TEXT,
    version TEXT DEFAULT '1.0.0',
    manifest TEXT NOT NULL DEFAULT '{}',
    code_path TEXT,
    status TEXT DEFAULT 'draft',
    installs_count INTEGER DEFAULT 0,
    rating_avg REAL DEFAULT 0.0,
    rating_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS plugin_installs (
    id TEXT PRIMARY KEY,
    plugin_id TEXT NOT NULL REFERENCES plugins(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id TEXT REFERENCES organizations(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'active',
    config TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(plugin_id, user_id)
);

-- ============================================================
-- PHASE 6: Marketplace
-- ============================================================

CREATE TABLE IF NOT EXISTS marketplace_packages (
    id TEXT PRIMARY KEY,
    publisher_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    description TEXT,
    long_description TEXT,
    category TEXT DEFAULT 'general',
    tags TEXT DEFAULT '[]',
    icon_url TEXT,
    screenshot_urls TEXT DEFAULT '[]',
    license TEXT DEFAULT 'MIT',
    status TEXT DEFAULT 'draft',
    review_notes TEXT,
    reviewed_by TEXT REFERENCES users(id),
    reviewed_at TEXT,
    installs_count INTEGER DEFAULT 0,
    rating_avg REAL DEFAULT 0.0,
    rating_count INTEGER DEFAULT 0,
    downloads_total INTEGER DEFAULT 0,
    featured INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_marketplace_category ON marketplace_packages(category);
CREATE INDEX IF NOT EXISTS idx_marketplace_status ON marketplace_packages(status);
CREATE INDEX IF NOT EXISTS idx_marketplace_publisher ON marketplace_packages(publisher_id);

CREATE TABLE IF NOT EXISTS package_versions (
    id TEXT PRIMARY KEY,
    package_id TEXT NOT NULL REFERENCES marketplace_packages(id) ON DELETE CASCADE,
    version TEXT NOT NULL,
    manifest TEXT DEFAULT '{}',
    code_path TEXT,
    changelog TEXT,
    file_size_bytes INTEGER DEFAULT 0,
    checksum TEXT,
    status TEXT DEFAULT 'draft',
    reviewed_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(package_id, version)
);
CREATE INDEX IF NOT EXISTS idx_package_versions_pkg ON package_versions(package_id);

CREATE TABLE IF NOT EXISTS package_reviews (
    id TEXT PRIMARY KEY,
    package_id TEXT NOT NULL REFERENCES marketplace_packages(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL,
    title TEXT,
    content TEXT,
    helpful_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(package_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_package_reviews_pkg ON package_reviews(package_id);

CREATE TABLE IF NOT EXISTS package_downloads (
    id TEXT PRIMARY KEY,
    package_id TEXT NOT NULL REFERENCES marketplace_packages(id) ON DELETE CASCADE,
    version_id TEXT REFERENCES package_versions(id) ON DELETE SET NULL,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    org_id TEXT REFERENCES organizations(id) ON DELETE SET NULL,
    ip_address TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_package_downloads_pkg ON package_downloads(package_id);
CREATE INDEX IF NOT EXISTS idx_package_downloads_created ON package_downloads(created_at);

CREATE TABLE IF NOT EXISTS package_pricing (
    id TEXT PRIMARY KEY,
    package_id TEXT NOT NULL REFERENCES marketplace_packages(id) ON DELETE CASCADE,
    price_type TEXT DEFAULT 'free',
    price_cents INTEGER DEFAULT 0,
    currency TEXT DEFAULT 'USD',
    trial_days INTEGER DEFAULT 0,
    subscription_interval TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS developer_payouts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount_cents INTEGER NOT NULL,
    currency TEXT DEFAULT 'USD',
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    stripe_transfer_id TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_developer_payouts_user ON developer_payouts(user_id);
CREATE INDEX IF NOT EXISTS idx_developer_payouts_status ON developer_payouts(status);

CREATE TABLE IF NOT EXISTS revenue_transactions (
    id TEXT PRIMARY KEY,
    package_id TEXT NOT NULL REFERENCES marketplace_packages(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount_cents INTEGER NOT NULL,
    developer_share_cents INTEGER NOT NULL,
    platform_share_cents INTEGER NOT NULL,
    currency TEXT DEFAULT 'USD',
    transaction_type TEXT,
    stripe_payment_id TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_revenue_transactions_pkg ON revenue_transactions(package_id);
CREATE INDEX IF NOT EXISTS idx_revenue_transactions_user ON revenue_transactions(user_id);

CREATE TABLE IF NOT EXISTS package_scans (
    id TEXT PRIMARY KEY,
    package_id TEXT NOT NULL REFERENCES marketplace_packages(id) ON DELETE CASCADE,
    version_id TEXT REFERENCES package_versions(id) ON DELETE SET NULL,
    scan_type TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    findings TEXT DEFAULT '[]',
    scanned_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_package_scans_pkg ON package_scans(package_id);

-- ============================================================
-- PHASE 7: Large-Scale AgentOS
-- ============================================================

CREATE TABLE IF NOT EXISTS kg_entities (
    id TEXT PRIMARY KEY,
    org_id TEXT REFERENCES organizations(id) ON DELETE CASCADE,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    properties TEXT DEFAULT '{}',
    embedding TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_kg_entities_org ON kg_entities(org_id);
CREATE INDEX IF NOT EXISTS idx_kg_entities_type ON kg_entities(entity_type);

CREATE TABLE IF NOT EXISTS kg_relationships (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    target_id TEXT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    properties TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(source_id, target_id, relationship_type)
);
CREATE INDEX IF NOT EXISTS idx_kg_rels_source ON kg_relationships(source_id);
CREATE INDEX IF NOT EXISTS idx_kg_rels_target ON kg_relationships(target_id);
CREATE INDEX IF NOT EXISTS idx_kg_rels_type ON kg_relationships(relationship_type);

CREATE TABLE IF NOT EXISTS kg_snapshots (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    entity_count INTEGER DEFAULT 0,
    relationship_count INTEGER DEFAULT 0,
    snapshot_data TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scheduler_tasks (
    id TEXT PRIMARY KEY,
    org_id TEXT REFERENCES organizations(id) ON DELETE CASCADE,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    task_type TEXT NOT NULL,
    payload TEXT DEFAULT '{}',
    priority INTEGER DEFAULT 5,
    status TEXT DEFAULT 'pending',
    max_retries INTEGER DEFAULT 3,
    retry_count INTEGER DEFAULT 0,
    last_error TEXT,
    worker_id TEXT,
    started_at TEXT,
    completed_at TEXT,
    scheduled_at TEXT DEFAULT (datetime('now')),
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_scheduler_status ON scheduler_tasks(status);
CREATE INDEX IF NOT EXISTS idx_scheduler_priority ON scheduler_tasks(priority DESC, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_scheduler_org ON scheduler_tasks(org_id);
CREATE INDEX IF NOT EXISTS idx_scheduler_type ON scheduler_tasks(task_type);

CREATE TABLE IF NOT EXISTS scheduler_workers (
    id TEXT PRIMARY KEY,
    org_id TEXT REFERENCES organizations(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'idle',
    current_task_id TEXT REFERENCES scheduler_tasks(id),
    max_concurrency INTEGER DEFAULT 5,
    active_count INTEGER DEFAULT 0,
    tasks_completed INTEGER DEFAULT 0,
    last_heartbeat TEXT DEFAULT (datetime('now')),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS observability_traces (
    id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    span_id TEXT NOT NULL,
    parent_span_id TEXT,
    org_id TEXT REFERENCES organizations(id) ON DELETE CASCADE,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    operation TEXT NOT NULL,
    service TEXT DEFAULT 'agentos',
    duration_ms INTEGER,
    status TEXT DEFAULT 'ok',
    metadata TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_traces_trace_id ON observability_traces(trace_id);
CREATE INDEX IF NOT EXISTS idx_traces_org ON observability_traces(org_id);
CREATE INDEX IF NOT EXISTS idx_traces_operation ON observability_traces(operation);
CREATE INDEX IF NOT EXISTS idx_traces_created ON observability_traces(created_at);
CREATE INDEX IF NOT EXISTS idx_traces_status ON observability_traces(status);

CREATE TABLE IF NOT EXISTS observability_metrics (
    id TEXT PRIMARY KEY,
    org_id TEXT REFERENCES organizations(id) ON DELETE CASCADE,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    metric_type TEXT,
    labels TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON observability_metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_metrics_org ON observability_metrics(org_id);
CREATE INDEX IF NOT EXISTS idx_metrics_created ON observability_metrics(created_at);

CREATE TABLE IF NOT EXISTS observability_logs (
    id TEXT PRIMARY KEY,
    org_id TEXT REFERENCES organizations(id) ON DELETE CASCADE,
    trace_id TEXT,
    level TEXT DEFAULT 'info',
    message TEXT NOT NULL,
    source TEXT,
    metadata TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_logs_trace ON observability_logs(trace_id);
CREATE INDEX IF NOT EXISTS idx_logs_org ON observability_logs(org_id);
CREATE INDEX IF NOT EXISTS idx_logs_level ON observability_logs(level);
CREATE INDEX IF NOT EXISTS idx_logs_created ON observability_logs(created_at);

CREATE TABLE IF NOT EXISTS anomaly_rules (
    id TEXT PRIMARY KEY,
    org_id TEXT REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    condition TEXT NOT NULL,
    threshold REAL NOT NULL,
    window_minutes INTEGER DEFAULT 5,
    severity TEXT DEFAULT 'warning',
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS anomaly_events (
    id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL REFERENCES anomaly_rules(id) ON DELETE CASCADE,
    org_id TEXT REFERENCES organizations(id) ON DELETE CASCADE,
    metric_value REAL,
    threshold REAL,
    severity TEXT,
    message TEXT,
    resolved INTEGER DEFAULT 0,
    resolved_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_anomaly_events_org ON anomaly_events(org_id);

CREATE TABLE IF NOT EXISTS threat_rules (
    id TEXT PRIMARY KEY,
    org_id TEXT REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    rule_type TEXT NOT NULL,
    config TEXT DEFAULT '{}',
    severity TEXT DEFAULT 'warning',
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS threat_events (
    id TEXT PRIMARY KEY,
    rule_id TEXT REFERENCES threat_rules(id) ON DELETE SET NULL,
    org_id TEXT REFERENCES organizations(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    source_ip TEXT,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    details TEXT DEFAULT '{}',
    severity TEXT DEFAULT 'warning',
    action_taken TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_threat_events_org ON threat_events(org_id);
CREATE INDEX IF NOT EXISTS idx_threat_events_created ON threat_events(created_at);

CREATE TABLE IF NOT EXISTS region_configs (
    id TEXT PRIMARY KEY,
    region_name TEXT NOT NULL UNIQUE,
    endpoint TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    weight INTEGER DEFAULT 100,
    latency_ms_avg INTEGER DEFAULT 0,
    features TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS region_routing (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    region_name TEXT NOT NULL,
    priority INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(org_id, region_name)
);

-- ============================================================
-- PHASE 0 ADDITIONS: Brain Notes + Refresh Tokens
-- ============================================================

CREATE TABLE IF NOT EXISTS brain_notes (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id TEXT REFERENCES organizations(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    content TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    links TEXT DEFAULT '[]',
    word_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_brain_notes_user ON brain_notes(user_id);
CREATE INDEX IF NOT EXISTS idx_brain_notes_org ON brain_notes(org_id);
CREATE INDEX IF NOT EXISTS idx_brain_notes_updated ON brain_notes(updated_at);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    revoked INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
"""


def run_migrations(conn):
    """Execute all DDL statements. Idempotent (CREATE IF NOT EXISTS)."""
    cur = conn.cursor()
    for statement in SCHEMA_SQL.split(";"):
        stmt = statement.strip()
        if not stmt:
            continue
        # Remove comment lines
        lines = [line for line in stmt.splitlines() if not line.strip().startswith("--")]
        stmt_clean = "\n".join(lines).strip()
        if stmt_clean:
            try:
                cur.execute(stmt_clean)
            except Exception as e:
                # Skip benign errors (e.g., duplicate index)
                if "already exists" not in str(e).lower():
                    print(f"Migration warning: {e}")
    conn.commit()
    cur.close()
