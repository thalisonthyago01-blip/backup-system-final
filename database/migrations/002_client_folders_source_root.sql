ALTER TABLE backups ADD COLUMN IF NOT EXISTS source_root TEXT;

CREATE TABLE IF NOT EXISTS client_folders (
    id UUID PRIMARY KEY,
    machine_id UUID NOT NULL,
    path TEXT NOT NULL,
    label VARCHAR(100) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_client_folder_machine
        FOREIGN KEY (machine_id) REFERENCES machines(id) ON DELETE CASCADE,
    CONSTRAINT uq_client_folder_path UNIQUE (machine_id, path)
);

CREATE INDEX IF NOT EXISTS idx_client_folders_machine_enabled
    ON client_folders (machine_id, enabled);
