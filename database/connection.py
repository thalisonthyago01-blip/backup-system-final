import os
import psycopg


def get_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "backup_system"),
        user=os.getenv("DB_USER", "backup_user"),
        password=os.getenv("DB_PASSWORD", "backup_password")
    )
