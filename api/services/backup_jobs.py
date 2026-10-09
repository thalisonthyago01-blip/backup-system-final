import uuid
import json

from database.connection import get_connection

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"


def criar_backup_job(machine_id, folder_id, selection_type="folder", selection_paths=None):
    selection_paths = selection_paths or []
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, label
                FROM client_folders
                WHERE id = %s
                  AND machine_id = %s
                  AND enabled = TRUE
                """,
                (folder_id, machine_id),
            )
            folder = cursor.fetchone()
            if folder is None:
                return None

            job_id = uuid.uuid4()
            cursor.execute(
                """
                INSERT INTO backup_jobs (
                    id, machine_id, folder_id, status, selection_type, selection_paths
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id, machine_id, folder_id, status, created_at
                """,
                (job_id, machine_id, folder[0], STATUS_PENDING, selection_type, json.dumps(selection_paths)),
            )
            row = cursor.fetchone()
        connection.commit()
        return _row_to_dict(row, folder_label=folder[1])
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def obter_backup_job(machine_id, job_id):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    j.id, j.machine_id, j.folder_id, j.status,
                    j.created_at, j.started_at, j.finished_at, j.error,
                    f.label, j.selection_type, j.selection_paths,
                    j.progress_percent, j.bytes_sent, j.bytes_total,
                    j.files_sent, j.files_total, j.progress_message
                FROM backup_jobs j
                JOIN client_folders f ON f.id = j.folder_id
                WHERE j.id = %s AND j.machine_id = %s
                """,
                (job_id, machine_id),
            )
            row = cursor.fetchone()
        return _row_to_dict_full(row) if row else None
    finally:
        connection.close()


def _row_to_dict(row, folder_label=None):
    return {
        "id": str(row[0]),
        "type": "backup",
        "machine_id": str(row[1]),
        "folder_id": str(row[2]),
        "status": row[3],
        "created_at": row[4].isoformat(),
        "label": folder_label,
        "progress_percent": 0,
        "bytes_sent": 0,
        "bytes_total": 0,
        "files_sent": 0,
        "files_total": 0,
        "progress_message": "Aguardando o cliente",
    }


def _row_to_dict_full(row):
    return {
        "id": str(row[0]),
        "type": "backup",
        "machine_id": str(row[1]),
        "folder_id": str(row[2]),
        "status": row[3],
        "created_at": row[4].isoformat(),
        "started_at": row[5].isoformat() if row[5] else None,
        "finished_at": row[6].isoformat() if row[6] else None,
        "error": row[7],
        "label": row[8],
        "selection_type": row[9],
        "selection_paths": row[10] or [],
        "progress_percent": row[11],
        "bytes_sent": row[12],
        "bytes_total": row[13],
        "files_sent": row[14],
        "files_total": row[15],
        "progress_message": row[16],
    }


def atualizar_progresso_backup_job(machine_id, job_id, progresso):
    """Registra o andamento informado pelo cliente autenticado."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE backup_jobs
                SET progress_percent = %s,
                    bytes_sent = %s,
                    bytes_total = %s,
                    files_sent = %s,
                    files_total = %s,
                    progress_message = %s
                WHERE id = %s
                  AND machine_id = %s
                  AND status = %s
                RETURNING id, status, progress_percent, bytes_sent, bytes_total,
                          files_sent, files_total, progress_message
                """,
                (
                    max(0, min(100, int(progresso.progress_percent))),
                    max(0, int(progresso.bytes_sent)),
                    max(0, int(progresso.bytes_total)),
                    max(0, int(progresso.files_sent)),
                    max(0, int(progresso.files_total)),
                    str(progresso.progress_message or "Enviando arquivos")[:500],
                    job_id, machine_id, STATUS_RUNNING,
                ),
            )
            row = cursor.fetchone()
        if row is None:
            connection.rollback()
            return None
        connection.commit()
        return {
            "id": str(row[0]),
            "status": row[1],
            "progress_percent": row[2],
            "bytes_sent": row[3],
            "bytes_total": row[4],
            "files_sent": row[5],
            "files_total": row[6],
            "progress_message": row[7],
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def concluir_backup_job(machine_id, job_id):
    return _alterar_status(machine_id, job_id, STATUS_COMPLETED, None)


def falhar_backup_job(machine_id, job_id, error):
    mensagem = str(error).strip() or "Erro desconhecido durante o backup."
    return _alterar_status(machine_id, job_id, STATUS_FAILED, mensagem[:4000])


def _alterar_status(machine_id, job_id, status, error):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE backup_jobs
                SET status = %s,
                    finished_at = NOW(),
                    error = %s,
                    progress_percent = CASE WHEN %s = %s THEN 100 ELSE progress_percent END,
                    bytes_sent = CASE WHEN %s = %s THEN bytes_total ELSE bytes_sent END,
                    files_sent = CASE WHEN %s = %s THEN files_total ELSE files_sent END,
                    progress_message = CASE
                        WHEN %s = %s THEN 'Backup concluído'
                        WHEN %s = %s THEN 'Backup falhou'
                        ELSE progress_message
                    END
                WHERE id = %s
                  AND machine_id = %s
                  AND status = %s
                RETURNING id, machine_id, folder_id, status,
                          created_at, started_at, finished_at, error,
                          progress_percent, bytes_sent, bytes_total,
                          files_sent, files_total, progress_message
                """,
                (
                    status, error,
                    status, STATUS_COMPLETED,
                    status, STATUS_COMPLETED,
                    status, STATUS_COMPLETED,
                    status, STATUS_COMPLETED, status, STATUS_FAILED,
                    job_id, machine_id, STATUS_RUNNING,
                ),
            )
            row = cursor.fetchone()

        if row is None:
            connection.rollback()
            return None

        connection.commit()
        return {
            "id": str(row[0]),
            "type": "backup",
            "machine_id": str(row[1]),
            "folder_id": str(row[2]),
            "status": row[3],
            "created_at": row[4].isoformat(),
            "started_at": row[5].isoformat() if row[5] else None,
            "finished_at": row[6].isoformat() if row[6] else None,
            "error": row[7],
            "progress_percent": row[8],
            "bytes_sent": row[9],
            "bytes_total": row[10],
            "files_sent": row[11],
            "files_total": row[12],
            "progress_message": row[13],
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
