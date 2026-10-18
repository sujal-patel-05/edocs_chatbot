-- Migration 001: Initial schema for Symitar eDocs Assistant
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS ingest_runs (
    id SERIAL PRIMARY KEY,
    release VARCHAR(64) NOT NULL,
    chm_hashes JSONB NOT NULL DEFAULT '{}'::jsonb,
    documents_count INT NOT NULL DEFAULT 0,
    chunks_count INT NOT NULL DEFAULT 0,
    fields_count INT NOT NULL DEFAULT 0,
    links_count INT NOT NULL DEFAULT 0,
    duration_seconds REAL NOT NULL DEFAULT 0.0,
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(32) NOT NULL DEFAULT 'completed',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    doc_id VARCHAR(512) PRIMARY KEY,
    release VARCHAR(64) NOT NULL,
    chm VARCHAR(128) NOT NULL,
    path VARCHAR(512) NOT NULL,
    title TEXT NOT NULL,
    breadcrumbs JSONB NOT NULL DEFAULT '[]'::jsonb,
    toc_order INT,
    topic_type VARCHAR(64) NOT NULL,
    product_area TEXT NOT NULL,
    summary TEXT,
    markdown TEXT NOT NULL,
    images JSONB NOT NULL DEFAULT '[]'::jsonb,
    also_in JSONB NOT NULL DEFAULT '[]'::jsonb,
    orphan BOOLEAN NOT NULL DEFAULT FALSE,
    content_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_docs_release ON documents(release);
CREATE INDEX IF NOT EXISTS idx_docs_topic_type ON documents(topic_type);
CREATE INDEX IF NOT EXISTS idx_docs_product_area ON documents(product_area);
CREATE INDEX IF NOT EXISTS idx_docs_content_hash ON documents(content_hash);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id VARCHAR(512) PRIMARY KEY,
    doc_id VARCHAR(512) NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    release VARCHAR(64) NOT NULL,
    text TEXT NOT NULL,
    section_path JSONB NOT NULL DEFAULT '[]'::jsonb,
    anchor VARCHAR(256),
    topic_type VARCHAR(64) NOT NULL,
    product_area TEXT NOT NULL,
    kind VARCHAR(32) NOT NULL,
    token_count INT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chunks_release ON chunks(release);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_kind ON chunks(kind);
CREATE INDEX IF NOT EXISTS idx_chunks_content_hash ON chunks(content_hash);

CREATE TABLE IF NOT EXISTS fields (
    id SERIAL PRIMARY KEY,
    release VARCHAR(64) NOT NULL,
    record TEXT NOT NULL,
    field_name TEXT NOT NULL,
    field_number VARCHAR(64),
    poweron_mnemonic VARCHAR(128),
    symxchange_mnemonic VARCHAR(128),
    data_type TEXT,
    source TEXT,
    help_file VARCHAR(64),
    default_control TEXT,
    default_value TEXT,
    description TEXT,
    doc_id VARCHAR(512) NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_fields_release ON fields(release);
CREATE INDEX IF NOT EXISTS idx_fields_poweron_trgm ON fields USING gin (poweron_mnemonic gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_fields_name_trgm ON fields USING gin (field_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_fields_record_trgm ON fields USING gin (record gin_trgm_ops);

CREATE TABLE IF NOT EXISTS keywords (
    id SERIAL PRIMARY KEY,
    release VARCHAR(64) NOT NULL,
    term TEXT NOT NULL,
    doc_id VARCHAR(512) NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_keywords_term_trgm ON keywords USING gin (term gin_trgm_ops);

CREATE TABLE IF NOT EXISTS doc_links (
    id SERIAL PRIMARY KEY,
    source_doc_id VARCHAR(512) NOT NULL,
    target_doc_id VARCHAR(512) NOT NULL,
    anchor VARCHAR(256),
    link_text TEXT
);

CREATE INDEX IF NOT EXISTS idx_links_source ON doc_links(source_doc_id);
CREATE INDEX IF NOT EXISTS idx_links_target ON doc_links(target_doc_id);

CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(128),
    title TEXT,
    release VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS retrievals (
    id SERIAL PRIMARY KEY,
    message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    chunk_id VARCHAR(512) NOT NULL,
    rank INT NOT NULL,
    dense_score REAL,
    sparse_score REAL,
    rerank_score REAL
);

CREATE TABLE IF NOT EXISTS feedback (
    id SERIAL PRIMARY KEY,
    message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    rating VARCHAR(16) NOT NULL,
    reason VARCHAR(32),
    comment TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
