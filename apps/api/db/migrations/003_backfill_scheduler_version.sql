ALTER TABLE review_logs
    ADD COLUMN IF NOT EXISTS scheduler_version VARCHAR(30) NOT NULL DEFAULT 'sm2-v1';
