-- Initial database schema
-- Migration: 001

-- Domains table
CREATE TABLE IF NOT EXISTS domains (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    update_frequency_hours INTEGER DEFAULT 24,
    last_updated_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Items table (individual discoveries)
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    domain_id TEXT NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT,
    published_date TIMESTAMP,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    summary TEXT NOT NULL,
    significance TEXT NOT NULL,
    significance_score REAL NOT NULL CHECK(significance_score >= 0.0 AND significance_score <= 1.0),
    raw_content TEXT,
    embedding_id TEXT,
    UNIQUE(domain_id, source_url)
);

-- Updates table (synthesized domain summaries)
CREATE TABLE IF NOT EXISTS updates (
    id TEXT PRIMARY KEY,
    domain_id TEXT NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    summary TEXT NOT NULL,
    item_ids TEXT NOT NULL,  -- JSON array of item IDs
    open_questions TEXT,     -- JSON array of questions
    token_usage INTEGER
);

-- User annotations table
CREATE TABLE IF NOT EXISTS user_annotations (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    note TEXT,
    tags TEXT,  -- JSON array
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_items_domain ON items(domain_id);
CREATE INDEX IF NOT EXISTS idx_items_discovered ON items(discovered_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_significance ON items(significance_score DESC);
CREATE INDEX IF NOT EXISTS idx_items_domain_significance ON items(domain_id, significance_score DESC);
CREATE INDEX IF NOT EXISTS idx_updates_domain ON updates(domain_id);
CREATE INDEX IF NOT EXISTS idx_updates_created ON updates(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_annotations_item ON user_annotations(item_id);

-- Migration tracking table
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Record this migration
INSERT INTO schema_migrations (version) VALUES (1);
