CREATE TABLE IF NOT EXISTS backup_jobs (
    id UUID PRIMARY KEY,
    machine_id UUID NOT NULL,
    folder_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error TEXT,
    CONSTRAINT fk_backup_job_machine
        FOREIGN KEY (machine_id) REFERENCES machines(id) ON DELETE CASCADE,
    CONSTRAINT fk_backup_job_folder
        FOREIGN KEY (folder_id) REFERENCES client_folders(id) ON DELETE CASCADE,
    CONSTRAINT ck_backup_job_status
        CHECK (status IN ('pending', 'running', 'completed', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_backup_jobs_machine_status_created
    ON backup_jobs (machine_id, status, created_at);
