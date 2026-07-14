-- Phase 6: Marketplace

-- Marketplace packages (published agents + tools/plugins)
CREATE TABLE marketplace_packages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    publisher_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    description TEXT,
    long_description TEXT,
    category TEXT DEFAULT 'general',
    tags TEXT[] DEFAULT '{}',
    icon_url TEXT,
    screenshot_urls TEXT[] DEFAULT '{}',
    license TEXT DEFAULT 'MIT',
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'pending_review', 'reviewing', 'published', 'suspended', 'archived')),
    review_notes TEXT,
    reviewed_by UUID REFERENCES users(id),
    reviewed_at TIMESTAMPTZ,
    installs_count INTEGER DEFAULT 0,
    rating_avg NUMERIC(3,2) DEFAULT 0.0,
    rating_count INTEGER DEFAULT 0,
    downloads_total INTEGER DEFAULT 0,
    featured BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_marketplace_category ON marketplace_packages(category);
CREATE INDEX idx_marketplace_status ON marketplace_packages(status);
CREATE INDEX idx_marketplace_publisher ON marketplace_packages(publisher_id);
CREATE INDEX idx_marketplace_tags ON marketplace_packages USING GIN(tags);

-- Package versions
CREATE TABLE package_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    package_id UUID NOT NULL REFERENCES marketplace_packages(id) ON DELETE CASCADE,
    version TEXT NOT NULL,
    manifest JSONB DEFAULT '{}',
    code_path TEXT,
    changelog TEXT,
    file_size_bytes INTEGER DEFAULT 0,
    checksum TEXT,
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'pending_review', 'published', 'rejected')),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(package_id, version)
);

CREATE INDEX idx_package_versions_pkg ON package_versions(package_id);

-- Reviews
CREATE TABLE package_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    package_id UUID NOT NULL REFERENCES marketplace_packages(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    title TEXT,
    content TEXT,
    helpful_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(package_id, user_id)
);

CREATE INDEX idx_package_reviews_pkg ON package_reviews(package_id);

-- Downloads (for analytics)
CREATE TABLE package_downloads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    package_id UUID NOT NULL REFERENCES marketplace_packages(id) ON DELETE CASCADE,
    version_id UUID REFERENCES package_versions(id) ON DELETE SET NULL,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    org_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
    ip_address TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_package_downloads_pkg ON package_downloads(package_id);
CREATE INDEX idx_package_downloads_created ON package_downloads(created_at);

-- Revenue / pricing
CREATE TABLE package_pricing (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    package_id UUID NOT NULL REFERENCES marketplace_packages(id) ON DELETE CASCADE,
    price_type TEXT DEFAULT 'free' CHECK (price_type IN ('free', 'one_time', 'subscription')),
    price_cents INTEGER DEFAULT 0,
    currency TEXT DEFAULT 'USD',
    trial_days INTEGER DEFAULT 0,
    subscription_interval TEXT CHECK (subscription_interval IN ('monthly', 'yearly')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Payouts
CREATE TABLE developer_payouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount_cents INTEGER NOT NULL,
    currency TEXT DEFAULT 'USD',
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    stripe_transfer_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_developer_payouts_user ON developer_payouts(user_id);
CREATE INDEX idx_developer_payouts_status ON developer_payouts(status);

-- Revenue transactions
CREATE TABLE revenue_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    package_id UUID NOT NULL REFERENCES marketplace_packages(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount_cents INTEGER NOT NULL,
    developer_share_cents INTEGER NOT NULL,
    platform_share_cents INTEGER NOT NULL,
    currency TEXT DEFAULT 'USD',
    transaction_type TEXT CHECK (transaction_type IN ('purchase', 'subscription', 'refund')),
    stripe_payment_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_revenue_transactions_pkg ON revenue_transactions(package_id);
CREATE INDEX idx_revenue_transactions_user ON revenue_transactions(user_id);

-- Abuse / security scan results
CREATE TABLE package_scans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    package_id UUID NOT NULL REFERENCES marketplace_packages(id) ON DELETE CASCADE,
    version_id UUID REFERENCES package_versions(id) ON DELETE SET NULL,
    scan_type TEXT NOT NULL CHECK (scan_type IN ('security', 'sandbox', 'license', 'manual')),
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'passed', 'failed')),
    findings JSONB DEFAULT '[]',
    scanned_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_package_scans_pkg ON package_scans(package_id);
