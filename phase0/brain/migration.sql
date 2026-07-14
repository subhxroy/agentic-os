-- Obsidian Brain: Personal Knowledge Graph
CREATE TABLE IF NOT EXISTS brain_notes (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    content TEXT DEFAULT '',
    tags JSONB DEFAULT '[]',
    links JSONB DEFAULT '[]',
    word_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_brain_notes_user ON brain_notes(user_id);
CREATE INDEX IF NOT EXISTS idx_brain_notes_org ON brain_notes(org_id);
CREATE INDEX IF NOT EXISTS idx_brain_notes_tags ON brain_notes USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_brain_notes_links ON brain_notes USING GIN(links);
CREATE INDEX IF NOT EXISTS idx_brain_notes_title ON brain_notes USING GIN(to_tsvector('english', title));
CREATE INDEX IF NOT EXISTS idx_brain_notes_updated ON brain_notes(updated_at DESC);

-- Refresh tokens table
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    revoked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
