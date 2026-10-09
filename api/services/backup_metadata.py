from database.connection import get_connection


def criar_backup_com_metadata(
    backup_id,
    machine_id,
    filename,
    formato,
    quantidade_arquivos,
    tamanho,
    checksum,
    status,
    arquivos,
    source_root=None
):
    """
    Registra o backup e seus arquivos em uma única transação.

    Assim, se o registro de qualquer arquivo falhar, o registro
    principal do backup também é revertido.
    """
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO backups (
                    id, machine_id, filename, format, files, size,
                    checksum, source_root, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    backup_id, machine_id, filename, formato,
                    quantidade_arquivos, tamanho, checksum, source_root, status
                )
            )

            for arquivo in arquivos:
                cursor.execute(
                    """
                    INSERT INTO backup_files (
                        id, backup_id, relative_path, size, sha256
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        __import__("uuid").uuid4(),
                        backup_id,
                        arquivo["relative_path"],
                        arquivo["size"],
                        arquivo["sha256"]
                    )
                )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()



def listar_backups_machine(machine_id):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    machine_id,
                    filename,
                    format,
                    files,
                    size,
                    checksum,
                    source_root,
                    status,
                    created_at
                FROM backups
                WHERE machine_id = %s
                ORDER BY created_at DESC
                """,
                (machine_id,)
            )
            resultados = cursor.fetchall()
        return [
            {
                "id": str(resultado[0]),
                "machine_id": str(resultado[1]),
                "filename": resultado[2],
                "format": resultado[3],
                "files": resultado[4],
                "size": resultado[5],
                "checksum": resultado[6],
                "source_root": resultado[7],
                "status": resultado[8],
                "created_at": resultado[9].isoformat()
            }
            for resultado in resultados
        ]
    finally:
        connection.close()


def obter_backup_machine(
    machine_id,
    backup_id
):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    machine_id,
                    filename,
                    format,
                    files,
                    size,
                    checksum,
                    source_root,
                    status,
                    created_at
                FROM backups
                WHERE id = %s
                  AND machine_id = %s
                """,
                (
                    backup_id,
                    machine_id
                )
            )
            resultado = cursor.fetchone()

        if resultado is None:
            return None

        return {
            "id": str(resultado[0]),
            "machine_id": str(resultado[1]),
            "filename": resultado[2],
            "format": resultado[3],
            "files": resultado[4],
            "size": resultado[5],
            "checksum": resultado[6],
            "source_root": resultado[7],
            "status": resultado[8],
            "created_at": resultado[9].isoformat()
        }

    finally:
        connection.close()


def excluir_backup_metadata(
    machine_id,
    backup_id
):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM backups
                WHERE id = %s
                  AND machine_id = %s
                """,
                (
                    backup_id,
                    machine_id
                )
            )
            excluido = cursor.rowcount > 0

        connection.commit()
        return excluido

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def criar_backup_files_metadata(backup_id, arquivos):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            for arquivo in arquivos:
                cursor.execute(
                    """
                    INSERT INTO backup_files (
                        id, backup_id, relative_path, size, sha256
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        __import__("uuid").uuid4(),
                        backup_id,
                        arquivo["relative_path"],
                        arquivo["size"],
                        arquivo["sha256"]
                    )
                )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def listar_backup_files(backup_id):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT relative_path, size, sha256
                FROM backup_files
                WHERE backup_id = %s
                ORDER BY relative_path
                """,
                (backup_id,)
            )
            resultados = cursor.fetchall()
        return [
            {
                "relative_path": resultado[0],
                "size": resultado[1],
                "sha256": resultado[2]
            }
            for resultado in resultados
        ]
    finally:
        connection.close()
