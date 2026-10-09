import hashlib
import secrets
import uuid

from database.connection import get_connection


def gerar_hash(valor):
    return hashlib.sha256(
        valor.encode("utf-8")
    ).hexdigest()


def registrar_maquina(identidade, fingerprint):

    hardware = identidade["hardware"]
    sistema = identidade["system"]

    connection = get_connection()

    try:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT id
                FROM machines
                WHERE fingerprint = %s
                """,
                (fingerprint,)
            )

            maquina = cursor.fetchone()

            if maquina:
                machine_id = maquina[0]

                cursor.execute(
                    """
                    UPDATE machines
                    SET hostname = %s,
                        operating_system = %s,
                        os_version = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        sistema["hostname"],
                        sistema["operating_system"],
                        sistema["os_version"],
                        machine_id
                    )
                )

            else:
                machine_id = uuid.uuid4()

                cursor.execute(
                    """
                    INSERT INTO machines (
                        id,
                        fingerprint,
                        hostname,
                        operating_system,
                        os_version
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        machine_id,
                        fingerprint,
                        sistema["hostname"],
                        sistema["operating_system"],
                        sistema["os_version"]
                    )
                )

            installation_id = uuid.uuid4()

            client_key = secrets.token_urlsafe(32)

            client_key_hash = gerar_hash(client_key)

            cursor.execute(
                """
                INSERT INTO installations (
                    id,
                    machine_id,
                    installation_id,
                    client_key_hash
                )
                VALUES (%s, %s, %s, %s)
                """,
                (
                    uuid.uuid4(),
                    machine_id,
                    installation_id,
                    client_key_hash
                )
            )

        connection.commit()

        return {
            "machine_id": str(machine_id),
            "installation_id": str(installation_id),
            "client_key": client_key
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()