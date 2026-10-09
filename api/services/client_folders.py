import uuid

from database.connection import get_connection


def sincronizar_pastas(machine_id, pastas):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            for pasta in pastas:
                caminho = str(pasta.get("path", "")).strip()
                label = str(pasta.get("label", "")).strip() or caminho
                if not caminho:
                    continue
                cursor.execute(
                    """
                    INSERT INTO client_folders (id, machine_id, path, label, enabled)
                    VALUES (%s, %s, %s, %s, FALSE)
                    ON CONFLICT (machine_id, path)
                    DO UPDATE SET label = EXCLUDED.label,
                                  updated_at = NOW()
                    """,
                    (uuid.uuid4(), machine_id, caminho, label[:100])
                )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def listar_pastas(machine_id):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, path, label, enabled, created_at, updated_at
                FROM client_folders
                WHERE machine_id = %s
                ORDER BY label, path
                """,
                (machine_id,)
            )
            rows = cursor.fetchall()
        return [
            {
                "id": str(row[0]),
                "path": row[1],
                "label": row[2],
                "enabled": row[3],
                "created_at": row[4].isoformat(),
                "updated_at": row[5].isoformat(),
            }
            for row in rows
        ]
    finally:
        connection.close()
