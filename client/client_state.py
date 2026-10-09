import json
import os
import sys
from pathlib import Path


APP_NAME = "BackupSystem"


def _legacy_base_dir() -> Path:
    """Retorna a pasta antiga usada pelas versões anteriores do client."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _base_dir() -> Path:
    """Pasta persistente compartilhada pela instalação do client.

    No Windows, o estado não fica mais ao lado do .exe. Assim, o mesmo
    estado é utilizado pelo Python e pelo executável, mesmo que sejam
    executados a partir de pastas diferentes.
    """
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            base = Path(local_app_data) / APP_NAME
        else:
            base = Path.home() / "AppData" / "Local" / APP_NAME
    else:
        base = Path.home() / ".local" / "share" / APP_NAME

    base.mkdir(parents=True, exist_ok=True)
    return base


BASE_DIR = _base_dir()
STATE_FILE = BASE_DIR / "client_state.json"


def _migrar_estado_antigo() -> None:
    """Migra uma credencial legada para o armazenamento compartilhado.

    A prioridade é o estado ao lado do executável, pois é o estado que
    normalmente foi usado pela versão .exe instalada. Depois tentamos o
    estado antigo do código-fonte.
    """
    if STATE_FILE.exists():
        return

    candidatos = [
        _legacy_base_dir() / "client_state.json",
        Path(__file__).resolve().parent / "client_state.json",
    ]

    for origem in candidatos:
        if origem == STATE_FILE or not origem.exists():
            continue

        try:
            dados = json.loads(origem.read_text(encoding="utf-8"))
            if not isinstance(dados, dict):
                continue
            if not all(
                dados.get(chave)
                for chave in ("machine_id", "installation_id", "client_key", "server")
            ):
                continue

            STATE_FILE.write_text(
                json.dumps(dados, indent=4, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"Estado do client migrado para: {STATE_FILE}")
            return
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue


_migrar_estado_antigo()


def carregar_estado():
    if not STATE_FILE.exists():
        return None

    with open(STATE_FILE, "r", encoding="utf-8") as arquivo:
        return json.load(arquivo)


def salvar_estado(estado):
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as arquivo:
        json.dump(estado, arquivo, indent=4, ensure_ascii=False)
