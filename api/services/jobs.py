from database.connection import get_connection

from api.services.restore_jobs import STATUS_PENDING, STATUS_RUNNING


def obter_proximo_job(machine_id):
    """Obtém atomicamente o job pendente mais antigo, de backup ou restore."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT j.id, j.created_at, f.label, j.selection_type, j.selection_paths
                FROM backup_jobs j
                JOIN client_folders f ON f.id = j.folder_id
                WHERE j.machine_id = %s AND j.status = %s
                ORDER BY j.created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                (machine_id, STATUS_PENDING),
            )
            backup_row = cursor.fetchone()

            cursor.execute(
                """
                SELECT id, created_at
                FROM restore_jobs
                WHERE machine_id = %s AND status = %s
                ORDER BY created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                (machine_id, STATUS_PENDING),
            )
            restore_row = cursor.fetchone()

            if backup_row is None and restore_row is None:
                connection.commit()
                return None

            use_backup = (
                restore_row is None
                or (
                    backup_row is not None
                    and backup_row[1] <= restore_row[1]
                )
            )

            if use_backup:
                job_id = backup_row[0]
                cursor.execute(
                    """
                    UPDATE backup_jobs
                    SET status = %s, started_at = NOW(), error = NULL
                    WHERE id = %s AND machine_id = %s
                    RETURNING id, machine_id, folder_id, status,
                              created_at, started_at, selection_type, selection_paths
                    """,
                    (STATUS_RUNNING, job_id, machine_id),
                )
                row = cursor.fetchone()
                result = {
                    "id": str(row[0]),
                    "type": "backup",
                    "machine_id": str(row[1]),
                    "folder_id": str(row[2]),
                    "status": row[3],
                    "created_at": row[4].isoformat(),
                    "started_at": row[5].isoformat() if row[5] else None,
                    "label": backup_row[2],
                    "selection_type": row[6],
                    "selection_paths": row[7] or [],
                }
            else:
                job_id = restore_row[0]
                cursor.execute(
                    """
                    UPDATE restore_jobs
                    SET status = %s, started_at = NOW(), error = NULL
                    WHERE id = %s AND machine_id = %s
                    RETURNING id, backup_id, machine_id, status,
                              destination, overwrite, created_at,
                              started_at
                    """,
                    (STATUS_RUNNING, job_id, machine_id),
                )
                row = cursor.fetchone()
                result = {
                    "id": str(row[0]),
                    "type": "restore",
                    "backup_id": str(row[1]),
                    "machine_id": str(row[2]),
                    "status": row[3],
                    "destination": row[4],
                    "overwrite": row[5],
                    "created_at": row[6].isoformat(),
                    "started_at": row[7].isoformat() if row[7] else None,
                }

            connection.commit()
            return result
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def concluir_job(machine_id, job_id):
    from api.services.restore_jobs import concluir_restore_job
    from api.services.backup_jobs import concluir_backup_job

    result = concluir_restore_job(machine_id, job_id)
    if result is not None:
        return result
    return concluir_backup_job(machine_id, job_id)


def falhar_job(machine_id, job_id, error):
    from api.services.restore_jobs import falhar_restore_job
    from api.services.backup_jobs import falhar_backup_job

    result = falhar_restore_job(machine_id, job_id, error)
    if result is not None:
        return result
    return falhar_backup_job(machine_id, job_id, error)
