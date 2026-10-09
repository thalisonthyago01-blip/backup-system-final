import json
import sys
import threading
from pathlib import Path

from client.machine_identity import coletar_identidade, gerar_fingerprint
from client.registration import registrar_cliente, SERVER_URL
from client.client_state import BASE_DIR
from client.startup import configurar_inicio_automatico
from client.tray import ClientTray
from client.single_instance import garantir_instancia_unica


def caminho_saida() -> Path:
    return BASE_DIR / "client_identity.json"
def gerar_arquivo_identidade() -> Path:
    identidade = coletar_identidade()
    fingerprint = gerar_fingerprint(identidade)

    dados = {
        "version": 1,
        "fingerprint": fingerprint,
        "identity": identidade,
    }

    destino = caminho_saida()

    destino.write_text(
        json.dumps(
            dados,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return destino


def iniciar_client_residente():
    """Inicia o client como aplicativo residente, sem janela de console."""
    if not garantir_instancia_unica():
        return

    configurar_inicio_automatico()

    stop_event = threading.Event()
    tray = ClientTray(stop_event)
    thread_tray = threading.Thread(
        target=tray.executar,
        name="backup-client-tray",
        daemon=True,
    )
    thread_tray.start()

    from client.agent import executar_agent

    try:
        # O agent é responsável por permanecer vivo mesmo quando a API/Docker
        # ainda estiver inicializando. Assim o executável não depende de CMD.
        executar_agent(stop_event=stop_event)
    except Exception as erro:
        try:
            from client.client_state import BASE_DIR
            with (BASE_DIR / "client_error.log").open(
                "a", encoding="utf-8"
            ) as arquivo:
                arquivo.write(f"Erro fatal ao iniciar o client: {erro!r}\n")
        except Exception:
            pass
        stop_event.set()
        if tray.icon is not None:
            tray.icon.stop()


def main():
    # Comandos do client podem ser usados pelo executável sem alterar
    # o comportamento antigo de simplesmente registrar a máquina.
    if len(sys.argv) >= 2 and sys.argv[1] == "backup":
        from client.backup import executar_backup

        if len(sys.argv) < 3:
            print("Uso: python -m client.main backup CAMINHO_DA_PASTA_OU_ARQUIVO")
            sys.exit(1)

        try:
            executar_backup(sys.argv[2])
        except Exception as erro:
            print(f"ERRO: {erro}")
            sys.exit(1)
        return

    if len(sys.argv) >= 2 and sys.argv[1] == "sync-folders":
        from client.folders import descobrir_pastas_locais
        from client.client_state import carregar_estado
        import httpx

        estado = carregar_estado()
        if not estado:
            print("ERRO: Client ainda não está registrado.")
            sys.exit(1)

        pastas = descobrir_pastas_locais()
        headers = {
            "X-Installation-ID": estado["installation_id"],
            "X-Client-Key": estado["client_key"],
        }
        response = httpx.post(
            f"{estado['server']}/client/folders/sync",
            headers=headers,
            json={"folders": pastas},
            timeout=15,
        )
        response.raise_for_status()
        from client.authorized_folders import salvar_pastas_autorizadas
        resposta = response.json()
        salvar_pastas_autorizadas(resposta.get("folders", []))
        print("Pastas autorizadas:")
        for pasta in resposta.get("folders", []):
            if pasta.get("enabled"):
                print(f"- {pasta['label']}: {pasta['path']}")
        return

    if len(sys.argv) >= 2 and sys.argv[1] == "backup-files":
        from client.backup import executar_backup_arquivos

        if len(sys.argv) < 3:
            print("Uso: python -m client.main backup-files ARQUIVO [ARQUIVO ...]")
            sys.exit(1)

        try:
            executar_backup_arquivos(sys.argv[2:])
        except Exception as erro:
            print(f"ERRO: {erro}")
            sys.exit(1)
        return

    if len(sys.argv) >= 2 and sys.argv[1] in {"agent", "--startup"}:
        iniciar_client_residente()
        return

    if len(sys.argv) >= 2 and sys.argv[1] == "restore":
        from client.restore import executar_restore

        if len(sys.argv) < 3:
            print("Uso: backup-client.exe restore BACKUP_ID [--dest CAMINHO] [--overwrite]")
            sys.exit(1)

        backup_id = sys.argv[2]
        destino = None
        sobrescrever = False
        i = 3

        while i < len(sys.argv):
            argumento = sys.argv[i]

            if argumento == "--overwrite":
                sobrescrever = True
            elif argumento == "--dest":
                i += 1
                if i >= len(sys.argv):
                    print("ERRO: --dest precisa de um caminho.")
                    sys.exit(1)
                destino = sys.argv[i]
            else:
                print(f"ERRO: argumento desconhecido: {argumento}")
                sys.exit(1)

            i += 1

        try:
            executar_restore(backup_id, destino, sobrescrever)
        except Exception as erro:
            print(f"ERRO: {erro}")
            sys.exit(1)

        return

    iniciar_client_residente()

if __name__ == "__main__":
    main()
