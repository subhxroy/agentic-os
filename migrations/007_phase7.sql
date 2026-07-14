-- Phase 7: Large-Scale AgentOS

-- ============================================================
-- KNOWLEDGE GRAPH (Memory Graph)
-- ============================================================
CREATE TABLE kg_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    properties JSONB DEFAULT '{}',
    embedding VECTOR(768),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_kg_entities_org ON kg_entities(org_id);
CREATE INDEX idx_kg_entities_type ON kg_entities(entity_type);
CREATE INDEX idx_kg_entities_name ON kg_entities USING gin(name gin_trgm_ops);

CREATE TABLE kg_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    target_id UUID NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,
    weight NUMERIC(5,4) DEFAULT 1.0,
    properties JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source_id, target_id, relationship_type)
);

CREATE INDEX idx_kg_rels_source ON kg_relationships(source_id);
CREATE INDEX idx_kg_rels_target ON kg_relationships(target_id);
CREATE INDEX idx_kg_rels_type ON kg_relationships(relationship_type);

CREATE TABLE kg_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    entity_count INTEGER DEFAULT 0,
    relationship_count INTEGER DEFAULT 0,
    snapshot_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- AGENT SCHEDULER (Custom task queue)
-- ============================================================
CREATE TABLE scheduler_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    task_type TEXT NOT NULL,
    payload JSONB DEFAULT '{}',
    priority INTEGER DEFAULT 5 CHECK (priority >= 1 AND priority <= 10),
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled', 'retry')),
    max_retries INTEGER DEFAULT 3,
    retry_count INTEGER DEFAULT 0,
    last_error TEXT,
    worker_id TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    scheduled_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_scheduler_status ON scheduler_tasks(status);
CREATE INDEX idx_scheduler_priority ON scheduler_tasks(priority DESC, scheduled_at);
CREATE INDEX idx_scheduler_org ON scheduler_tasks(org_id);
CREATE INDEX idx_scheduler_type ON scheduler_tasks(task_type);

CREATE TABLE scheduler_workers (
    id TEXT PRIMARY KEY,
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'idle' CHECK (status IN ('idle', 'busy', 'offline')),
    current_task_id UUID REFERENCES scheduler_tasks(id),
    max_concurrency INTEGER DEFAULT 5,
    active_count INTEGER DEFAULT 0,
    tasks_completed INTEGER DEFAULT 0,
    last_heartbeat TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- OBSERVABILITY
-- ============================================================
CREATE TABLE observability_traces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id TEXT NOT NULL,
    span_id TEXT NOT NULL,
    parent_span_id TEXT,
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    operation TEXT NOT NULL,
    service TEXT DEFAULT 'agentos',
    duration_ms INTEGER,
    status TEXT DEFAULT 'ok' CHECK (status IN ('ok', 'error', 'timeout')),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_traces_trace_id ON observability_traces(trace_id);
CREATE INDEX idx_traces_org ON observability_traces(org_id);
CREATE INDEX idx_traces_operation ON observability_traces(operation);
CREATE INDEX idx_traces_created ON observability_traces(created_at);
CREATE INDEX idx_traces_status ON observability_traces(status);

CREATE TABLE observability_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    metric_name TEXT NOT NULL,
    metric_value NUMERIC NOT NULL,
    metric_type TEXT CHECK (metric_type IN ('counter', 'gauge', 'histogram')),
    labels JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_metrics_name ON observability_metrics(metric_name);
CREATE INDEX idx_metrics_org ON observability_metrics(org_id);
CREATE INDEX idx_metrics_created ON observability_metrics(created_at);

CREATE TABLE observability_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    trace_id TEXT,
    level TEXT DEFAULT 'info' CHECK (level IN ('debug', 'info', 'warn', 'error', 'fatal')),
    message TEXT NOT NULL,
    source TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_logs_trace ON observability_logs(trace_id);
CREATE INDEX idx_logs_org ON observability_logs(org_id);
CREATE INDEX idx_logs_level ON observability_logs(level);
CREATE INDEX idx_logs_created ON observability_logs(created_at);

-- ============================================================
-- ANOMALY DETECTION
-- ============================================================
CREATE TABLE anomaly_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    condition TEXT NOT NULL CHECK (condition IN ('gt', 'lt', 'eq', 'gte', 'lte')),
    threshold NUMERIC NOT NULL,
    window_minutes INTEGER DEFAULT 5,
    severity TEXT DEFAULT 'warning' CHECK (severity IN ('info', 'warning', 'critical')),
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE anomaly_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id UUID NOT NULL REFERENCES anomaly_rules(id) ON DELETE CASCADE,
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    metric_value NUMERIC,
    threshold NUMERIC,
    severity TEXT,
    message TEXT,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_anomaly_events_org ON anomaly_events(org_id);
CREATE INDEX idx_anomaly_events_unresolved ON anomaly_events(resolved) WHERE NOT resolved;

-- ============================================================
-- THREAT DETECTION
-- ============================================================
CREATE TABLE threat_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    rule_type TEXT NOT NULL CHECK (rule_type IN ('rate_limit', 'ip_block', 'pattern', 'anomaly')),
    config JSONB DEFAULT '{}',
    severity TEXT DEFAULT 'warning' CHECK (severity IN ('info', 'warning', 'critical')),
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE threat_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id UUID REFERENCES threat_rules(id) ON DELETE SET NULL,
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    source_ip TEXT,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    details JSONB DEFAULT '{}',
    severity TEXT DEFAULT 'warning',
    action_taken TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_threat_events_org ON threat_events(org_id);
CREATE INDEX idx_threat_events_created ON threat_events(created_at);

-- ============================================================
-- MULTI-REGION CONFIG
-- ============================================================
CREATE TABLE region_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    region_name TEXT NOT NULL UNIQUE,
    endpoint TEXT NOT NULL,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'draining', 'offline')),
    weight INTEGER DEFAULT 100,
    latency_ms_avg INTEGER DEFAULT 0,
    features JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE region_routing (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    region_name TEXT NOT NULL,
    priority INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(org_id, region_name)
);
