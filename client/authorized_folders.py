import json
import os
from pathlib import Path

from client.client_state import BASE_DIR


AUTHORIZED_FOLDERS_FILE = BASE_DIR / "client_authorized_folders.json"

def salvar_pastas_autorizadas(pastas: list[dict]) -> None:
    autorizadas = []
    for pasta in pastas:
        if not pasta.get("enabled", True):
            continue

        folder_id = str(pasta.get("id", "")).strip()
        caminho = str(pasta.get("path", "")).strip()
        if not folder_id or not caminho:
            continue

        autorizadas.append({
            "id": folder_id,
            "path": caminho,
            "label": str(pasta.get("label", "")).strip() or caminho,
            "enabled": True,
        })

    AUTHORIZED_FOLDERS_FILE.write_text(
        json.dumps(autorizadas, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def carregar_pastas_autorizadas() -> list[dict]:
    if not AUTHORIZED_FOLDERS_FILE.exists():
        return []

    try:
        dados = json.loads(
            AUTHORIZED_FOLDERS_FILE.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(dados, list):
        return []

    return [p for p in dados if isinstance(p, dict) and p.get("enabled", True)]


def obter_pasta_por_id(folder_id: str) -> Path:
    folder_id = str(folder_id).strip()
    for pasta in carregar_pastas_autorizadas():
        if str(pasta.get("id", "")).strip() != folder_id:
            continue

        caminho = Path(str(pasta.get("path", ""))).expanduser().resolve()
        if not caminho.is_dir():
            raise RuntimeError(
                f"A pasta autorizada não está disponível: {caminho}"
            )
        return caminho

    raise RuntimeError(
        f"A pasta {folder_id} não está autorizada neste client."
    )


def obter_pasta_original(source_root: str, caminhos_relativos: list[str]) -> Path:
    """Resolve a origem original do backup e garante que ela continua autorizada.

    Backups novos armazenam ``source_root`` como a raiz real da seleção:
    - pasta autorizada inteira -> a própria pasta autorizada;
    - subpasta -> a subpasta selecionada;
    - arquivos -> a raiz autorizada que contém os arquivos.

    Portanto, não é necessário exigir que os arquivos tenham uma única pasta
    raiz dentro do ZIP. O ``source_root`` já identifica a raiz correta.
    """
    source_root = str(source_root or "").strip()
    if not source_root:
        raise RuntimeError(
            "Este backup não possui a origem registrada; "
            "não é possível restaurá-lo automaticamente na pasta original."
        )

    candidato = Path(source_root).expanduser().resolve()

    # A pasta pode ter sido apagada desde o backup. Isso não significa
    # que ela deixou de ser autorizada: a autorização é verificada
    # estruturalmente contra as raízes registradas abaixo.
    #
    # O restore será responsável por recriar a pasta com mkdir(parents=True).
    # Não usamos is_dir() aqui justamente para permitir restaurar uma
    # árvore inteira que foi removida.

    # A origem registrada precisa continuar dentro de alguma pasta autorizada.
    for pasta in carregar_pastas_autorizadas():
        autorizada = Path(str(pasta.get("path", ""))).expanduser().resolve()
        try:
            candidato.relative_to(autorizada)
            return candidato
        except ValueError:
            continue

    raise RuntimeError(
        f"A pasta original não está autorizada neste client: {candidato}"
    )


def obter_raiz_autorizada(caminho: str | Path) -> Path:
    """Retorna a raiz registrada que contém o caminho informado."""
    candidato = Path(caminho).expanduser().resolve()
    if not candidato.exists():
        raise RuntimeError(f"Caminho não encontrado: {candidato}")

    correspondencias = []
    for pasta in carregar_pastas_autorizadas():
        raiz = Path(str(pasta.get("path", ""))).expanduser().resolve()
        try:
            candidato.relative_to(raiz)
            correspondencias.append(raiz)
        except ValueError:
            continue

    if not correspondencias:
        raise RuntimeError(
            f"Acesso negado: o caminho não pertence a nenhuma pasta autorizada: {candidato}"
        )

    return max(correspondencias, key=lambda caminho: len(caminho.parts))


def caminho_autorizado(caminho: str | Path) -> Path:
    """Valida que o caminho está dentro de alguma raiz autorizada.

    O caminho pode ser a própria raiz registrada ou uma subpasta dela.
    Caminhos fora das raízes autorizadas são recusados.
    """
    candidato = Path(caminho).expanduser().resolve()

    if not candidato.exists():
        raise RuntimeError(f"Caminho não encontrado: {candidato}")

    for pasta in carregar_pastas_autorizadas():
        raiz = Path(str(pasta.get("path", ""))).expanduser().resolve()
        try:
            candidato.relative_to(raiz)
            return candidato
        except ValueError:
            continue

    raise RuntimeError(
        f"Acesso negado: o caminho não pertence a nenhuma pasta autorizada: {candidato}"
    )
