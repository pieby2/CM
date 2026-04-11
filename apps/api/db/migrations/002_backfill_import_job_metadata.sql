ALTER TABLE import_jobs
    ADD COLUMN IF NOT EXISTS source_path VARCHAR(500),
    ADD COLUMN IF NOT EXISTS extraction_method VARCHAR(30),
    ADD COLUMN IF NOT EXISTS page_count INTEGER,
    ADD COLUMN IF NOT EXISTS extracted_char_count INTEGER;

CREATE INDEX IF NOT EXISTS ix_import_jobs_status ON import_jobs (status);
