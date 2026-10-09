import hashlib

from database.connection import get_connection


def gerar_hash(valor):
    return hashlib.sha256(
        valor.encode("utf-8")
    ).hexdigest()


def autenticar_instalacao(
    installation_id,
    client_key
):

    client_key_hash = gerar_hash(client_key)

    connection = get_connection()

    try:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    machine_id,
                    client_key_hash
                FROM installations
                WHERE installation_id = %s
                """,
                (installation_id,)
            )

            resultado = cursor.fetchone()

            if resultado is None:
                return None

            machine_id, hash_armazenado = resultado

            if client_key_hash != hash_armazenado:
                return None

            cursor.execute(
                """
                UPDATE installations
                SET last_seen = NOW()
                WHERE installation_id = %s
                """,
                (installation_id,)
            )

        connection.commit()

        return {
            "machine_id": str(machine_id),
            "installation_id": installation_id
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()