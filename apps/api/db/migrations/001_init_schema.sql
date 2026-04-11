CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email);

CREATE TABLE IF NOT EXISTS decks (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_decks_user_id ON decks (user_id);

CREATE TABLE IF NOT EXISTS import_jobs (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    deck_name VARCHAR(255) NOT NULL,
    source_filename VARCHAR(255) NOT NULL,
    source_path VARCHAR(500),
    status VARCHAR(50) NOT NULL DEFAULT 'queued',
    extraction_method VARCHAR(30),
    page_count INTEGER,
    extracted_char_count INTEGER,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_import_jobs_user_id ON import_jobs (user_id);
CREATE INDEX IF NOT EXISTS ix_import_jobs_status ON import_jobs (status);

CREATE TABLE IF NOT EXISTS sections (
    id VARCHAR(36) PRIMARY KEY,
    import_job_id VARCHAR(36) NOT NULL REFERENCES import_jobs(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    order_index INTEGER NOT NULL DEFAULT 0,
    content TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_sections_import_job_id ON sections (import_job_id);

CREATE TABLE IF NOT EXISTS cards (
    id VARCHAR(36) PRIMARY KEY,
    deck_id VARCHAR(36) NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    section_id VARCHAR(36) REFERENCES sections(id) ON DELETE SET NULL,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    type VARCHAR(50) NOT NULL DEFAULT 'definition',
    difficulty_estimate DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_cards_deck_id ON cards (deck_id);
CREATE INDEX IF NOT EXISTS ix_cards_section_id ON cards (section_id);

CREATE TABLE IF NOT EXISTS card_states (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    card_id VARCHAR(36) NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    ease_factor DOUBLE PRECISION NOT NULL DEFAULT 2.5,
    reps INTEGER NOT NULL DEFAULT 0,
    interval_days INTEGER NOT NULL DEFAULT 0,
    last_review_at TIMESTAMPTZ,
    due_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status VARCHAR(20) NOT NULL DEFAULT 'new',
    suspended BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_card_states_user_card UNIQUE (user_id, card_id)
);

CREATE INDEX IF NOT EXISTS ix_card_states_user_id ON card_states (user_id);
CREATE INDEX IF NOT EXISTS ix_card_states_card_id ON card_states (card_id);
CREATE INDEX IF NOT EXISTS ix_card_states_due_at ON card_states (due_at);
CREATE INDEX IF NOT EXISTS ix_card_states_status ON card_states (status);

CREATE TABLE IF NOT EXISTS concepts (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    subject VARCHAR(100) NOT NULL,
    difficulty_estimate DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    CONSTRAINT uq_concepts_name_subject UNIQUE (name, subject)
);

CREATE INDEX IF NOT EXISTS ix_concepts_name ON concepts (name);
CREATE INDEX IF NOT EXISTS ix_concepts_subject ON concepts (subject);

CREATE TABLE IF NOT EXISTS card_concepts (
    id BIGSERIAL PRIMARY KEY,
    card_id VARCHAR(36) NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    concept_id VARCHAR(36) NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL DEFAULT 'primary',
    CONSTRAINT uq_card_concepts_card_concept_role UNIQUE (card_id, concept_id, role)
);

CREATE INDEX IF NOT EXISTS ix_card_concepts_card_id ON card_concepts (card_id);
CREATE INDEX IF NOT EXISTS ix_card_concepts_concept_id ON card_concepts (concept_id);

CREATE TABLE IF NOT EXISTS concept_edges (
    id BIGSERIAL PRIMARY KEY,
    from_concept_id VARCHAR(36) NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    to_concept_id VARCHAR(36) NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    relation_type VARCHAR(30) NOT NULL DEFAULT 'prerequisite',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_concept_edges_unique UNIQUE (from_concept_id, to_concept_id, relation_type)
);

CREATE INDEX IF NOT EXISTS ix_concept_edges_from_concept_id ON concept_edges (from_concept_id);
CREATE INDEX IF NOT EXISTS ix_concept_edges_to_concept_id ON concept_edges (to_concept_id);

CREATE TABLE IF NOT EXISTS review_logs (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    card_id VARCHAR(36) NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    quality INTEGER NOT NULL,
    elapsed_since_last_review_sec INTEGER,
    response_time_ms INTEGER,
    card_type VARCHAR(50) NOT NULL DEFAULT 'definition',
    concept_id VARCHAR(36) REFERENCES concepts(id) ON DELETE SET NULL,
    scheduler_version VARCHAR(30) NOT NULL DEFAULT 'sm2-v1'
);

CREATE INDEX IF NOT EXISTS ix_review_logs_user_id ON review_logs (user_id);
CREATE INDEX IF NOT EXISTS ix_review_logs_card_id ON review_logs (card_id);
CREATE INDEX IF NOT EXISTS ix_review_logs_timestamp ON review_logs (timestamp);
