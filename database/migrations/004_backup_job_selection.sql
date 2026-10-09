ALTER TABLE backup_jobs
    ADD COLUMN IF NOT EXISTS selection_type VARCHAR(20) NOT NULL DEFAULT 'folder',
    ADD COLUMN IF NOT EXISTS selection_paths JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE backup_jobs
    DROP CONSTRAINT IF EXISTS ck_backup_job_selection_type;

ALTER TABLE backup_jobs
    ADD CONSTRAINT ck_backup_job_selection_type
    CHECK (selection_type IN ('folder', 'subfolder', 'files'));
