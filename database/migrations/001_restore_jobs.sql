CREATE TABLE IF NOT EXISTS restore_jobs (
    id UUID PRIMARY KEY,
    backup_id UUID NOT NULL,
    machine_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    destination VARCHAR(30) NOT NULL DEFAULT 'default',
    overwrite BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error TEXT,
    CONSTRAINT fk_restore_job_backup
        FOREIGN KEY (backup_id)
        REFERENCES backups(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_restore_job_machine
        FOREIGN KEY (machine_id)
        REFERENCES machines(id)
        ON DELETE CASCADE,
    CONSTRAINT ck_restore_job_status
        CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    CONSTRAINT ck_restore_job_destination
        CHECK (destination = 'default')
);

CREATE INDEX IF NOT EXISTS idx_restore_jobs_machine_status_created
    ON restore_jobs (machine_id, status, created_at);
