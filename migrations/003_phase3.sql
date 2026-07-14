-- Phase 3: Team Collaboration schema

-- ============================================================
-- INVITATIONS
-- ============================================================
CREATE TABLE IF NOT EXISTS invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',  -- admin, member
    invited_by UUID NOT NULL REFERENCES users(id),
    token TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'pending',  -- pending, accepted, expired
    expires_at TIMESTAMP DEFAULT (NOW() + INTERVAL '7 days'),
    created_at TIMESTAMP DEFAULT NOW(),
    accepted_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_invitations_org ON invitations(org_id, status);
CREATE INDEX IF NOT EXISTS idx_invitations_email ON invitations(email, status);
CREATE INDEX IF NOT EXISTS idx_invitations_token ON invitations(token);

-- ============================================================
-- AUDIT LOG
-- ============================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,  -- user.login, user.register, session.create, knowledge.upload, agent.chat, org.member_added, etc.
    resource_type TEXT,    -- user, session, knowledge, agent, org
    resource_id TEXT,
    details JSONB DEFAULT '{}',
    ip_address TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_log_org ON audit_log(org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action, created_at DESC);

-- ============================================================
-- SHARED KNOWLEDGE BASES
-- ============================================================
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    visibility TEXT DEFAULT 'org',  -- org, private
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kb_org ON knowledge_bases(org_id);

-- Link documents to knowledge bases
ALTER TABLE documents ADD COLUMN IF NOT EXISTS kb_id UUID REFERENCES knowledge_bases(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_documents_kb ON documents(kb_id);

-- ============================================================
-- AGENT TEMPLATES (save/share/fork)
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE SET NULL,  -- NULL = personal
    created_by UUID NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    description TEXT,
    system_prompt TEXT,
    tools JSONB DEFAULT '[]',       -- list of tool names
    model_config JSONB DEFAULT '{}', -- tier, temperature, etc.
    tags JSONB DEFAULT '[]',
    visibility TEXT DEFAULT 'private',  -- private, org, public
    fork_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_templates_org ON agent_templates(org_id);
CREATE INDEX IF NOT EXISTS idx_templates_public ON agent_templates(visibility) WHERE visibility = 'public';

-- ============================================================
-- AGENT TEMPLATE FORKS (track lineage)
-- ============================================================
CREATE TABLE IF NOT EXISTS template_forks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    original_id UUID NOT NULL REFERENCES agent_templates(id) ON DELETE CASCADE,
    forked_id UUID NOT NULL REFERENCES agent_templates(id) ON DELETE CASCADE,
    forked_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- COMMENTS (on agent responses)
-- ============================================================
CREATE TABLE IF NOT EXISTS comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    parent_id UUID REFERENCES comments(id) ON DELETE CASCADE,  -- threaded replies
    content TEXT NOT NULL,
    comment_type TEXT DEFAULT 'comment',  -- comment, feedback, approval
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_comments_session ON comments(session_id, created_at);

-- ============================================================
-- FEEDBACK (thumbs up/down on responses)
-- ============================================================
CREATE TABLE IF NOT EXISTS feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    message_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    user_id UUID NOT NULL REFERENCES users(id),
    rating INTEGER NOT NULL,  -- 1 = thumbs down, 5 = thumbs up
    comment TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(session_id, message_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_feedback_session ON feedback(session_id);
