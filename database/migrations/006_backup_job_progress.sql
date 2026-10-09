-- Campos para exibir o progresso real do envio de arquivos no painel.
ALTER TABLE backup_jobs
    ADD COLUMN IF NOT EXISTS progress_percent INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS bytes_sent BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS bytes_total BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS files_sent INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS files_total INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS progress_message TEXT NOT NULL DEFAULT 'Aguardando o cliente';

UPDATE backup_jobs
SET progress_percent = 100,
    progress_message = 'Backup concluído'
WHERE status = 'completed';
