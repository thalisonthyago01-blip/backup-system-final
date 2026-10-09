CREATE TABLE machines (
    id UUID PRIMARY KEY,
    fingerprint VARCHAR(64) NOT NULL UNIQUE,
    hostname VARCHAR(255),
    operating_system VARCHAR(100),
    os_version VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE installations (
    id UUID PRIMARY KEY,
    machine_id UUID NOT NULL,
    installation_id UUID NOT NULL UNIQUE,
    client_key_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_installation_machine
        FOREIGN KEY (machine_id)
        REFERENCES machines(id)
        ON DELETE CASCADE
);

CREATE TABLE backups (
    id UUID PRIMARY KEY,
    machine_id UUID NOT NULL,
    filename VARCHAR(255) NOT NULL,
    format VARCHAR(20) NOT NULL,
    files INTEGER NOT NULL,
    size BIGINT NOT NULL,
    checksum VARCHAR(64),
    source_root TEXT,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_backup_machine
        FOREIGN KEY (machine_id)
        REFERENCES machines(id)
        ON DELETE CASCADE
);


CREATE TABLE client_folders (
    id UUID PRIMARY KEY,
    machine_id UUID NOT NULL,
    path TEXT NOT NULL,
    label VARCHAR(100) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_client_folder_machine
        FOREIGN KEY (machine_id)
        REFERENCES machines(id)
        ON DELETE CASCADE,
    CONSTRAINT uq_client_folder_path
        UNIQUE (machine_id, path)
);

CREATE INDEX idx_client_folders_machine_enabled
    ON client_folders (machine_id, enabled);

CREATE TABLE backup_files (
    id UUID PRIMARY KEY,
    backup_id UUID NOT NULL,
    relative_path TEXT NOT NULL,
    size BIGINT NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    CONSTRAINT fk_backup_file_backup
        FOREIGN KEY (backup_id)
        REFERENCES backups(id)
        ON DELETE CASCADE,
    CONSTRAINT uq_backup_file_path
        UNIQUE (backup_id, relative_path)
);


CREATE TABLE restore_jobs (
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

CREATE INDEX idx_restore_jobs_machine_status_created
    ON restore_jobs (machine_id, status, created_at);

CREATE TABLE IF NOT EXISTS backup_jobs (
    id UUID PRIMARY KEY,
    machine_id UUID NOT NULL,
    folder_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error TEXT,
    progress_percent INTEGER NOT NULL DEFAULT 0,
    bytes_sent BIGINT NOT NULL DEFAULT 0,
    bytes_total BIGINT NOT NULL DEFAULT 0,
    files_sent INTEGER NOT NULL DEFAULT 0,
    files_total INTEGER NOT NULL DEFAULT 0,
    progress_message TEXT NOT NULL DEFAULT 'Aguardando o cliente',
    CONSTRAINT fk_backup_job_machine
        FOREIGN KEY (machine_id) REFERENCES machines(id) ON DELETE CASCADE,
    CONSTRAINT fk_backup_job_folder
        FOREIGN KEY (folder_id) REFERENCES client_folders(id) ON DELETE CASCADE,
    CONSTRAINT ck_backup_job_status
        CHECK (status IN ('pending', 'running', 'completed', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_backup_jobs_machine_status_created
    ON backup_jobs (machine_id, status, created_at);

ALTER TABLE backup_jobs
    ADD COLUMN IF NOT EXISTS selection_type VARCHAR(20) NOT NULL DEFAULT 'folder',
    ADD COLUMN IF NOT EXISTS selection_paths JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE backup_jobs
    DROP CONSTRAINT IF EXISTS ck_backup_job_selection_type;

ALTER TABLE backup_jobs
    ADD CONSTRAINT ck_backup_job_selection_type
    CHECK (selection_type IN ('folder', 'subfolder', 'files'));

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS admin_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(120) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS admin_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_id UUID NOT NULL,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT fk_admin_session_admin
        FOREIGN KEY (admin_id) REFERENCES admin_users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_admin_sessions_expires
    ON admin_sessions (expires_at);

CREATE INDEX IF NOT EXISTS idx_admin_sessions_admin
    ON admin_sessions (admin_id);

ALTER TABLE backup_jobs
    ADD COLUMN IF NOT EXISTS progress_percent INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS bytes_sent BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS bytes_total BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS files_sent INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS files_total INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS progress_message TEXT NOT NULL DEFAULT 'Aguardando o cliente';
