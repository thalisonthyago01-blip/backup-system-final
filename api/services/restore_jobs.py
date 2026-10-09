import uuid

from database.connection import get_connection


STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"


def criar_restore_job(machine_id, backup_id, destination="default", overwrite=False):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO restore_jobs (
                    id, backup_id, machine_id, status,
                    destination, overwrite
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, backup_id, machine_id, status,
                          destination, overwrite, created_at
                """,
                (
                    uuid.uuid4(),
                    backup_id,
                    machine_id,
                    STATUS_PENDING,
                    destination,
                    overwrite,
                )
            )
            row = cursor.fetchone()
        connection.commit()
        return _row_to_dict(row)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def obter_restore_job(machine_id, job_id):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, backup_id, machine_id, status,
                       destination, overwrite, created_at,
                       started_at, finished_at, error
                FROM restore_jobs
                WHERE id = %s AND machine_id = %s
                """,
                (job_id, machine_id)
            )
            row = cursor.fetchone()
        return _row_to_dict(row, detailed=True) if row else None
    finally:
        connection.close()


def obter_proximo_job(machine_id):
    """Retira atomicamente o próximo job pendente desta máquina."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, backup_id, machine_id, status,
                       destination, overwrite, created_at
                FROM restore_jobs
                WHERE machine_id = %s
                  AND status = %s
                ORDER BY created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                (machine_id, STATUS_PENDING)
            )
            row = cursor.fetchone()

            if row is None:
                connection.commit()
                return None

            job_id = row[0]
            cursor.execute(
                """
                UPDATE restore_jobs
                SET status = %s, started_at = NOW(), error = NULL
                WHERE id = %s
                RETURNING id, backup_id, machine_id, status,
                          destination, overwrite, created_at,
                          started_at, finished_at, error
                """,
                (STATUS_RUNNING, job_id)
            )
            updated = cursor.fetchone()

        connection.commit()
        return _row_to_dict(updated, detailed=True)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def concluir_restore_job(machine_id, job_id):
    return _alterar_status(
        machine_id,
        job_id,
        STATUS_COMPLETED,
        None,
    )


def falhar_restore_job(machine_id, job_id, error):
    mensagem = str(error).strip() or "Erro desconhecido durante a restauração."
    return _alterar_status(
        machine_id,
        job_id,
        STATUS_FAILED,
        mensagem[:4000],
    )


def _alterar_status(machine_id, job_id, status, error):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE restore_jobs
                SET status = %s,
                    finished_at = NOW(),
                    error = %s
                WHERE id = %s
                  AND machine_id = %s
                  AND status = %s
                RETURNING id, backup_id, machine_id, status,
                          destination, overwrite, created_at,
                          started_at, finished_at, error
                """,
                (
                    status,
                    error,
                    job_id,
                    machine_id,
                    STATUS_RUNNING,
                )
            )
            row = cursor.fetchone()

        if row is None:
            connection.rollback()
            return None

        connection.commit()
        return _row_to_dict(row, detailed=True)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _row_to_dict(row, detailed=False):
    if row is None:
        return None

    resultado = {
        "id": str(row[0]),
        "backup_id": str(row[1]),
        "machine_id": str(row[2]),
        "status": row[3],
        "destination": row[4],
        "overwrite": row[5],
        "created_at": row[6].isoformat(),
    }

    if detailed:
        resultado.update({
            "started_at": row[7].isoformat() if row[7] else None,
            "finished_at": row[8].isoformat() if row[8] else None,
            "error": row[9],
        })

    return resultado
