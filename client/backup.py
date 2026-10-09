from pathlib import Path
import time
import uuid

import httpx

from client.client_state import carregar_estado
from client.authorized_folders import (
    caminho_autorizado,
    obter_pasta_por_id,
    obter_raiz_autorizada,
)


def _headers(estado: dict) -> dict:
    return {
        "X-Installation-ID": estado["installation_id"],
        "X-Client-Key": estado["client_key"],
    }


def coletar_arquivos(pasta: Path):
    arquivos = []
    raiz = pasta.resolve()

    for caminho in sorted(pasta.rglob("*")):
        if not caminho.is_file():
            continue

        try:
            caminho.resolve().relative_to(raiz)
        except ValueError:
            continue

        arquivos.append(caminho)

    return arquivos


def _enviar_backup(estado: dict, arquivos: list[Path], source_root: Path, progress_callback=None):
    """Envia multipart em streaming e informa bytes reais lidos/enfileirados."""
    source_root = source_root.resolve()
    if not source_root.is_dir():
        raise RuntimeError(f"Raiz de origem não encontrada: {source_root}")

    caminhos = []
    normalizados = []
    for caminho in arquivos:
        caminho = caminho.resolve()
        try:
            relativo = caminho.relative_to(source_root)
        except ValueError as erro:
            raise RuntimeError(
                f"O arquivo não pertence à raiz do backup: {caminho}"
            ) from erro
        normalizados.append(caminho)
        caminhos.append(relativo.as_posix())

    if len(set(caminhos)) != len(caminhos):
        raise RuntimeError("Existem arquivos duplicados na seleção do backup.")
    if not normalizados:
        raise RuntimeError("Nenhum arquivo foi selecionado para backup.")

    tamanhos = [arquivo.stat().st_size for arquivo in normalizados]
    bytes_total = sum(tamanhos)
    arquivos_total = len(normalizados)
    boundary = "----BackupSystem" + uuid.uuid4().hex
    crlf = b"\r\n"

    def campo(nome: str, valor: str) -> bytes:
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{nome}"\r\n\r\n'
        ).encode("utf-8") + str(valor).encode("utf-8") + crlf

    file_headers = []
    for arquivo in normalizados:
        nome = arquivo.name.replace("\\", "_").replace('"', "%22").replace("\r", "_").replace("\n", "_")
        cabecalho = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="files"; filename="{nome}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8")
        file_headers.append(cabecalho)

    path_parts = [campo("paths", caminho) for caminho in caminhos]
    source_part = campo("source_root", str(source_root))
    final_boundary = f"--{boundary}--\r\n".encode("ascii")
    content_length = (
        sum(len(file_headers[i]) + tamanhos[i] + len(crlf) for i in range(arquivos_total))
        + sum(len(part) for part in path_parts)
        + len(source_part)
        + len(final_boundary)
    )

    print(f"Raiz do backup: {source_root}")
    print(f"Arquivos: {arquivos_total}")
    print(f"Tamanho total: {bytes_total} bytes")
    print("Enviando backup...")

    bytes_enviados = 0
    arquivos_enviados = 0
    ultima_notificacao = 0.0
    ultimo_percentual = -1

    def notificar(atual: int, total_arquivos: int, nome_atual: str, force=False):
        nonlocal ultima_notificacao, ultimo_percentual
        if progress_callback is None:
            return
        if bytes_total > 0:
            percentual = min(100, int(atual * 100 / bytes_total))
        else:
            percentual = min(100, int(total_arquivos * 100 / arquivos_total))
        agora = time.monotonic()
        if not force and percentual < 100 and (agora - ultima_notificacao < 0.6) and (percentual - ultimo_percentual < 2):
            return
        dados = {
            "progress_percent": percentual,
            "bytes_sent": min(atual, bytes_total),
            "bytes_total": bytes_total,
            "files_sent": total_arquivos,
            "files_total": arquivos_total,
            "progress_message": (f"Enviando: {nome_atual}" if nome_atual else "Preparando envio"),
        }
        try:
            progress_callback(dados)
            ultima_notificacao = agora
            ultimo_percentual = percentual
        except Exception as erro:
            # Falha em atualizar a barra não deve cancelar o backup em si.
            print(f"Aviso: não foi possível atualizar o progresso: {erro}")

    def corpo_multipart():
        nonlocal bytes_enviados, arquivos_enviados
        notificar(0, 0, "", force=True)
        for indice, arquivo in enumerate(normalizados):
            yield file_headers[indice]
            with arquivo.open("rb") as origem:
                while True:
                    bloco = origem.read(1024 * 256)
                    if not bloco:
                        break
                    yield bloco
                    bytes_enviados += len(bloco)
                    notificar(bytes_enviados, arquivos_enviados, caminhos[indice])
            yield crlf
            arquivos_enviados += 1
            notificar(
                bytes_enviados,
                arquivos_enviados,
                caminhos[indice],
                force=(arquivos_enviados == arquivos_total),
            )

        for part in path_parts:
            yield part
        yield source_part
        yield final_boundary

    with httpx.Client(timeout=300) as client:
        response = client.post(
            f"{estado['server']}/backup",
            headers={
                **_headers(estado),
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(content_length),
            },
            content=corpo_multipart(),
            timeout=300,
        )

    if response.status_code >= 400:
        raise RuntimeError(response.text)

    resultado = response.json()
    notificar(bytes_total, arquivos_total, "", force=True)
    print("Backup criado com sucesso.")
    print(f"ID: {resultado['id']}")
    print(f"Arquivos: {resultado['files']}")
    print(f"Tamanho: {resultado['size']} bytes")
    return resultado


def executar_backup(pasta: str | None = None, folder_id: str | None = None, relative_path: str | None = None, paths: list[str] | None = None, progress_callback=None):
    estado = carregar_estado()
    if not estado:
        raise RuntimeError("Client ainda não está registrado.")

    if folder_id:
        raiz_autorizada = obter_pasta_por_id(folder_id)
        if pasta is not None:
            informado = Path(pasta).expanduser().resolve()
            caminho_autorizado(informado)
        if paths is not None:
            arquivos = []
            for rel in paths:
                rel = str(rel).replace("\\", "/").strip("/")
                if not rel or rel == ".." or rel.startswith("../") or "/../" in f"/{rel}/":
                    raise RuntimeError("Caminho relativo inválido.")
                arquivo = (raiz_autorizada / Path(rel)).resolve()
                try:
                    arquivo.relative_to(raiz_autorizada)
                except ValueError as erro:
                    raise RuntimeError("Arquivo fora da pasta autorizada.") from erro
                if not arquivo.is_file():
                    raise RuntimeError(f"Arquivo não encontrado: {arquivo}")
                arquivos.append(arquivo)
            return _enviar_backup(estado, arquivos, raiz_autorizada, progress_callback=progress_callback)

        raiz = raiz_autorizada
        if relative_path:
            rel = str(relative_path).replace("\\", "/").strip("/")
            if rel == ".." or rel.startswith("../") or "/../" in f"/{rel}/":
                raise RuntimeError("Caminho relativo inválido.")
            raiz = (raiz_autorizada / Path(rel)).resolve()
            try:
                raiz.relative_to(raiz_autorizada)
            except ValueError as erro:
                raise RuntimeError("Subpasta fora da pasta autorizada.") from erro
            if not raiz.is_dir():
                raise RuntimeError(f"Subpasta não encontrada: {raiz}")

        arquivos = coletar_arquivos(raiz)
        if not arquivos:
            raise RuntimeError(f"A pasta não possui arquivos: {raiz}")
        return _enviar_backup(estado, arquivos, raiz, progress_callback=progress_callback)

    if pasta:
        candidato = Path(pasta).expanduser().resolve()
        if candidato.is_dir():
            raiz = caminho_autorizado(candidato)
            arquivos = coletar_arquivos(raiz)
            return _enviar_backup(estado, arquivos, raiz, progress_callback=progress_callback)
        if candidato.is_file():
            raiz = obter_raiz_autorizada(candidato)
            return _enviar_backup(estado, [candidato], raiz, progress_callback=progress_callback)
        raise RuntimeError(f"Caminho não encontrado: {candidato}")

    raise RuntimeError("Nenhuma pasta de backup foi informada.")


def executar_backup_arquivos(caminhos: list[str], progress_callback=None):
    """Faz backup de vários arquivos, desde que estejam sob a mesma raiz autorizada."""
    estado = carregar_estado()
    if not estado:
        raise RuntimeError("Client ainda não está registrado.")
    if not caminhos:
        raise RuntimeError("Nenhum arquivo foi informado.")

    arquivos = []
    raiz_autorizada = None

    for caminho in caminhos:
        arquivo = Path(caminho).expanduser().resolve()
        if not arquivo.is_file():
            raise RuntimeError(f"Arquivo não encontrado: {arquivo}")

        raiz = obter_raiz_autorizada(arquivo)
        if raiz_autorizada is None:
            raiz_autorizada = raiz
        elif raiz.resolve() != raiz_autorizada.resolve():
            raise RuntimeError(
                "Todos os arquivos selecionados precisam estar dentro da mesma "
                "pasta autorizada."
            )
        arquivos.append(arquivo)

    return _enviar_backup(estado, arquivos, raiz_autorizada, progress_callback=progress_callback)
