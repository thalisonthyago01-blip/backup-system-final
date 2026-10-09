from getpass import getpass

from api.services.admin_auth import criar_admin


def main():
    print("=== Criar administrador do Backup System ===")
    username = input("Usuário: ").strip()
    password = getpass("Senha: ")
    confirmacao = getpass("Confirme a senha: ")

    if password != confirmacao:
        raise SystemExit("As senhas não conferem.")

    try:
        admin = criar_admin(username, password)
    except Exception as erro:
        raise SystemExit(f"Não foi possível criar o administrador: {erro}")

    print(f"Administrador criado: {admin['username']}")


if __name__ == "__main__":
    main()
