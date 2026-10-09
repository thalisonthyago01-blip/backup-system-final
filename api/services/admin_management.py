import uuid
from pathlib import Path

from database.connection import get_connection


def listar_maquinas():
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    m.id, m.fingerprint, m.hostname,
                    m.operating_system, m.os_version,
                    m.created_at, m.updated_at,
                    COUNT(f.id) FILTER (WHERE f.enabled = TRUE) AS enabled_folders,
                    COUNT(f.id) AS total_folders,
                    MAX(i.last_seen) AS last_seen
                FROM machines m
                LEFT JOIN client_folders f ON f.machine_id = m.id
                LEFT JOIN installations i ON i.machine_id = m.id
                GROUP BY m.id
                ORDER BY m.hostname NULLS LAST, m.created_at DESC
                """
            )
            rows = cursor.fetchall()
        return [
            {
                "id": str(r[0]),
                "fingerprint": r[1],
                "hostname": r[2],
                "operating_system": r[3],
                "os_version": r[4],
                "created_at": r[5].isoformat(),
                "updated_at": r[6].isoformat(),
                "enabled_folders": int(r[7] or 0),
                "total_folders": int(r[8] or 0),
                "last_seen": r[9].isoformat() if r[9] else None,
            }
            for r in rows
        ]
    finally:
        connection.close()


def listar_pastas_admin(machine_id):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, path, label, enabled, created_at, updated_at
                FROM client_folders
                WHERE machine_id = %s
                ORDER BY enabled DESC, label, path
                """,
                (machine_id,),
            )
            rows = cursor.fetchall()
        return [_folder(r) for r in rows]
    finally:
        connection.close()


def adicionar_pasta(machine_id, path, label):
    caminho = str(path).strip()
    rotulo = str(label).strip() or Path(caminho).name or caminho
    if not caminho:
        raise ValueError("Informe o caminho da pasta.")

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM machines WHERE id = %s", (machine_id,))
            if cursor.fetchone() is None:
                return None

            cursor.execute(
                """
                INSERT INTO client_folders (id, machine_id, path, label, enabled)
                VALUES (%s, %s, %s, %s, TRUE)
                ON CONFLICT (machine_id, path)
                DO UPDATE SET label = EXCLUDED.label,
                              enabled = TRUE,
                              updated_at = NOW()
                RETURNING id, path, label, enabled, created_at, updated_at
                """,
                (uuid.uuid4(), machine_id, caminho, rotulo[:100]),
            )
            row = cursor.fetchone()
        connection.commit()
        return _folder(row)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def atualizar_pasta(folder_id, enabled=None, label=None):
    campos = []
    valores = []
    if enabled is not None:
        campos.append("enabled = %s")
        valores.append(bool(enabled))
    if label is not None:
        rotulo = str(label).strip()
        if not rotulo:
            raise ValueError("O nome da pasta não pode ficar vazio.")
        campos.append("label = %s")
        valores.append(rotulo[:100])

    if not campos:
        return None

    valores.append(folder_id)
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE client_folders
                SET {', '.join(campos)}, updated_at = NOW()
                WHERE id = %s
                RETURNING id, path, label, enabled, created_at, updated_at
                """,
                tuple(valores),
            )
            row = cursor.fetchone()
        connection.commit()
        return _folder(row) if row else None
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def remover_pasta(folder_id):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM client_folders WHERE id = %s RETURNING id",
                (folder_id,),
            )
            row = cursor.fetchone()
        connection.commit()
        return row is not None
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _folder(row):
    return {
        "id": str(row[0]),
        "path": row[1],
        "label": row[2],
        "enabled": row[3],
        "created_at": row[4].isoformat(),
        "updated_at": row[5].isoformat(),
    }
