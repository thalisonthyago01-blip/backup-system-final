import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, HTTPException, Response

from database.connection import get_connection

PASSWORD_ITERATIONS = 310_000
SESSION_HOURS = 8
COOKIE_NAME = "bs_admin_session"


def _hash_password(password: str, salt: bytes | None = None) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("Senha inválida.")

    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return (
        f"pbkdf2_sha256${PASSWORD_ITERATIONS}$"
        f"{salt.hex()}${digest.hex()}"
    )


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algoritmo, iteracoes, salt_hex, digest_hex = encoded.split("$", 3)
        if algoritmo != "pbkdf2_sha256":
            return False
        iteracoes = int(iteracoes)
        salt = bytes.fromhex(salt_hex)
        esperado = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False

    atual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iteracoes,
    )
    return secrets.compare_digest(atual, esperado)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def criar_admin(username: str, password: str):
    username = username.strip().lower()
    if not username:
        raise ValueError("Usuário administrador inválido.")
    if len(password) < 8:
        raise ValueError("A senha do administrador deve ter pelo menos 8 caracteres.")

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM admin_users WHERE username = %s",
                (username,),
            )
            if cursor.fetchone() is not None:
                raise ValueError("Este administrador já existe.")

            cursor.execute(
                """
                INSERT INTO admin_users (username, password_hash)
                VALUES (%s, %s)
                RETURNING id, username, created_at
                """,
                (username, _hash_password(password)),
            )
            row = cursor.fetchone()
        connection.commit()
        return {
            "id": str(row[0]),
            "username": row[1],
            "created_at": row[2].isoformat(),
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def autenticar_admin(username: str, password: str):
    username = username.strip().lower()
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, username, password_hash
                FROM admin_users
                WHERE username = %s AND active = TRUE
                """,
                (username,),
            )
            row = cursor.fetchone()

            if row is None or not _verify_password(password, row[2]):
                return None

            token = secrets.token_urlsafe(48)
            expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)

            cursor.execute(
                """
                INSERT INTO admin_sessions (
                    id, admin_id, token_hash, expires_at
                )
                VALUES (gen_random_uuid(), %s, %s, %s)
                """,
                (row[0], _hash_token(token), expires_at),
            )
        connection.commit()

        return {
            "token": token,
            "username": row[1],
            "expires_at": expires_at.isoformat(),
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def encerrar_sessao(token: str | None):
    if not token:
        return

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM admin_sessions WHERE token_hash = %s",
                (_hash_token(token),),
            )
        connection.commit()
    finally:
        connection.close()


def obter_admin_atual(token: str | None):
    if not token:
        raise HTTPException(status_code=401, detail="Sessão administrativa não encontrada.")

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT a.id, a.username, s.expires_at
                FROM admin_sessions s
                JOIN admin_users a ON a.id = s.admin_id
                WHERE s.token_hash = %s
                  AND s.expires_at > NOW()
                  AND a.active = TRUE
                """,
                (_hash_token(token),),
            )
            row = cursor.fetchone()

            if row is None:
                raise HTTPException(status_code=401, detail="Sessão administrativa inválida ou expirada.")

            cursor.execute(
                "UPDATE admin_sessions SET last_seen = NOW() WHERE token_hash = %s",
                (_hash_token(token),),
            )
        connection.commit()

        return {
            "id": str(row[0]),
            "username": row[1],
            "expires_at": row[2].isoformat(),
        }
    finally:
        connection.close()


def autenticar_admin_request(bs_admin_session: str | None = Cookie(default=None)):
    return obter_admin_atual(bs_admin_session)


def definir_cookie_sessao(response: Response, token: str):
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=SESSION_HOURS * 3600,
        path="/",
    )


def remover_cookie_sessao(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")


# ---------------------------------------------------------------------------
# Gerenciamento de administradores (tela de cadastro no painel)
# ---------------------------------------------------------------------------

import re

USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,40}$")


def _validar_dados_admin(username: str, password: str) -> str:
    username = (username or "").strip().lower()
    if not USERNAME_RE.match(username):
        raise ValueError(
            "O usuário deve ter de 3 a 40 caracteres: letras minúsculas, "
            "números, ponto, hífen ou sublinhado."
        )
    _validar_senha(password)
    return username


def _validar_senha(password: str):
    if not isinstance(password, str) or len(password) < 8:
        raise ValueError("A senha deve ter pelo menos 8 caracteres.")
    if len(password) > 256:
        raise ValueError("A senha é longa demais.")


def existe_admin() -> bool:
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT EXISTS (SELECT 1 FROM admin_users)")
            return bool(cursor.fetchone()[0])
    finally:
        connection.close()


def criar_primeiro_admin(username: str, password: str):
    """Cria o primeiro administrador. Só funciona enquanto não existir nenhum.

    A tabela é travada durante a transação para que duas pessoas não consigam
    criar o "primeiro" administrador ao mesmo tempo.
    """
    if existe_admin():
        raise PermissionError("O primeiro administrador já foi criado.")
    username = _validar_dados_admin(username, password)

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("LOCK TABLE admin_users IN EXCLUSIVE MODE")
            cursor.execute("SELECT EXISTS (SELECT 1 FROM admin_users)")
            if cursor.fetchone()[0]:
                raise PermissionError("O primeiro administrador já foi criado.")

            cursor.execute(
                """
                INSERT INTO admin_users (username, password_hash)
                VALUES (%s, %s)
                RETURNING id, username, created_at
                """,
                (username, _hash_password(password)),
            )
            row = cursor.fetchone()
        connection.commit()
        return {"id": str(row[0]), "username": row[1], "created_at": row[2].isoformat()}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def cadastrar_admin(username: str, password: str):
    """Cadastro feito por um administrador já autenticado (pelo painel)."""
    username = _validar_dados_admin(username, password)
    return criar_admin(username, password)


def listar_admins():
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT a.id, a.username, a.active, a.created_at,
                       MAX(s.last_seen) AS ultimo_acesso
                FROM admin_users a
                LEFT JOIN admin_sessions s ON s.admin_id = a.id
                GROUP BY a.id
                ORDER BY a.active DESC, a.username
                """
            )
            rows = cursor.fetchall()
        return [
            {
                "id": str(r[0]),
                "username": r[1],
                "active": bool(r[2]),
                "created_at": r[3].isoformat() if r[3] else None,
                "last_seen": r[4].isoformat() if r[4] else None,
            }
            for r in rows
        ]
    finally:
        connection.close()


def atualizar_admin(admin_id: str, admin_atual_id: str, active=None, password=None):
    """Ativa/desativa um administrador ou redefine a senha dele.

    Regras:
    - ninguém pode desativar a própria conta;
    - sempre precisa sobrar pelo menos um administrador ativo;
    - ao desativar ou trocar a senha, as sessões abertas daquele administrador
      são encerradas (exceto a de quem está trocando a própria senha).
    """
    if active is None and password is None:
        raise ValueError("Nada para atualizar.")
    if password is not None:
        _validar_senha(password)

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, username, active FROM admin_users WHERE id = %s FOR UPDATE",
                (admin_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None

            if active is False and str(row[0]) == str(admin_atual_id):
                raise ValueError("Você não pode desativar a sua própria conta.")

            if active is False and row[2]:
                cursor.execute(
                    "SELECT COUNT(*) FROM admin_users WHERE active = TRUE AND id <> %s",
                    (admin_id,),
                )
                if cursor.fetchone()[0] == 0:
                    raise ValueError("É preciso manter pelo menos um administrador ativo.")

            if active is not None:
                cursor.execute(
                    "UPDATE admin_users SET active = %s, updated_at = NOW() WHERE id = %s",
                    (active, admin_id),
                )
                if active is False:
                    cursor.execute(
                        "DELETE FROM admin_sessions WHERE admin_id = %s",
                        (admin_id,),
                    )

            if password is not None:
                cursor.execute(
                    "UPDATE admin_users SET password_hash = %s, updated_at = NOW() WHERE id = %s",
                    (_hash_password(password), admin_id),
                )
                if str(row[0]) != str(admin_atual_id):
                    cursor.execute(
                        "DELETE FROM admin_sessions WHERE admin_id = %s",
                        (admin_id,),
                    )

            cursor.execute(
                "SELECT id, username, active, created_at FROM admin_users WHERE id = %s",
                (admin_id,),
            )
            atualizado = cursor.fetchone()
        connection.commit()
        return {
            "id": str(atualizado[0]),
            "username": atualizado[1],
            "active": bool(atualizado[2]),
            "created_at": atualizado[3].isoformat() if atualizado[3] else None,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
