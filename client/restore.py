import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path, PurePosixPath

import httpx

from client.client_state import carregar_estado
from client.authorized_folders import obter_pasta_original


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _headers(estado: dict) -> dict:
    return {
        "X-Installation-ID": estado["installation_id"],
        "X-Client-Key": estado["client_key"],
    }


def validar_caminho_relativo(caminho: str) -> PurePosixPath:
    """Valida um caminho vindo do manifest antes de usá-lo no filesystem."""
    if not isinstance(caminho, str) or not caminho.strip():
        raise ValueError("Caminho relativo inválido.")

    normalizado = caminho.replace("\\", "/")
    caminho_posix = PurePosixPath(normalizado)

    # Impede caminhos absolutos e caminhos com unidade do Windows.
    if caminho_posix.is_absolute() or (len(normalizado) >= 2 and normalizado[1] == ":"):
        raise ValueError(f"Caminho absoluto não permitido: {caminho}")

    partes = caminho_posix.parts

    if not partes or any(parte in ("", ".", "..") for parte in partes):
        raise ValueError(f"Caminho inseguro: {caminho}")

    if "\x00" in caminho:
        raise ValueError("Caminho contém caractere inválido.")

    return PurePosixPath(*partes)


def destino_seguro(raiz: Path, relativo: PurePosixPath) -> Path:
    raiz = raiz.resolve()
    destino = (raiz / Path(*relativo.parts)).resolve()

    try:
        destino.relative_to(raiz)
    except ValueError as erro:
        raise ValueError(f"Caminho escaparia da pasta de restauração: {relativo}") from erro

    return destino


def sha256_zip_entry(zip_file: zipfile.ZipFile, nome: str) -> tuple[str, int]:
    sha256 = hashlib.sha256()
    tamanho = 0

    with zip_file.open(nome, "r") as origem:
        while True:
            bloco = origem.read(1024 * 1024)
            if not bloco:
                break
            tamanho += len(bloco)
            sha256.update(bloco)

    return sha256.hexdigest(), tamanho


def baixar_backup(estado: dict, backup_id: str, destino_zip: Path) -> dict:
    headers = _headers(estado)
    server = estado["server"]

    print("Consultando backup...")
    response = httpx.get(
        f"{server}/backups/{backup_id}",
        headers=headers,
        timeout=60,
    )

    if response.status_code != 200:
        raise RuntimeError(f"Não foi possível consultar o backup: {response.text}")

    backup = response.json()

    print(f"Backup: {backup['id']}")
    print(f"Arquivos: {backup['files']}")
    print(f"Tamanho: {backup['size']} bytes")

    print("Verificando integridade no servidor...")
    response = httpx.get(
        f"{server}/backups/{backup_id}/verify",
        headers=headers,
        timeout=60,
    )

    if response.status_code != 200:
        raise RuntimeError(f"Falha na verificação do backup: {response.text}")

    verificacao = response.json()

    if verificacao.get("integridade") != "ok":
        raise RuntimeError("O servidor informou que o backup está corrompido.")

    print("Integridade no servidor: OK.")
    print("Baixando backup...")

    destino_zip.parent.mkdir(parents=True, exist_ok=True)

    with httpx.stream(
        "GET",
        f"{server}/backups/{backup_id}/download",
        headers=headers,
        timeout=300,
    ) as response:
        if response.status_code != 200:
            raise RuntimeError(f"Falha no download: {response.text}")

        with open(destino_zip, "wb") as arquivo:
            for bloco in response.iter_bytes(1024 * 1024):
                arquivo.write(bloco)

    print(f"ZIP baixado: {destino_zip}")

    sha256 = hashlib.sha256()
    with open(destino_zip, "rb") as arquivo:
        while True:
            bloco = arquivo.read(1024 * 1024)
            if not bloco:
                break
            sha256.update(bloco)

    checksum_local = sha256.hexdigest()

    if checksum_local != backup["checksum"]:
        destino_zip.unlink(missing_ok=True)
        raise RuntimeError("Checksum do ZIP baixado não corresponde ao backup.")

    print("Checksum do ZIP: OK.")
    return backup


def validar_manifest_e_metadados(zip_file: zipfile.ZipFile, backup: dict) -> list[dict]:
    nomes = set(zip_file.namelist())

    if "manifest.json" not in nomes:
        raise RuntimeError("manifest.json não encontrado no backup.")

    try:
        manifest = json.loads(zip_file.read("manifest.json").decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as erro:
        raise RuntimeError("manifest.json inválido.") from erro

    itens_manifest = manifest.get("files")
    itens_banco = backup.get("files_metadata")

    if not isinstance(itens_manifest, list) or not isinstance(itens_banco, list):
        raise RuntimeError("Metadados de arquivos ausentes ou inválidos.")

    if manifest.get("backup_id") != backup["id"]:
        raise RuntimeError("O backup_id do manifest não corresponde ao backup consultado.")

    if manifest.get("machine_id") != backup["machine_id"]:
        raise RuntimeError("O machine_id do manifest não corresponde ao backup consultado.")

    def mapa(itens):
        resultado = {}
        for item in itens:
            caminho = item.get("relative_path")
            validar_caminho_relativo(caminho)
            if caminho in resultado:
                raise RuntimeError(f"Caminho duplicado nos metadados: {caminho}")
            resultado[caminho] = item
        return resultado

    manifest_map = mapa(itens_manifest)
    banco_map = mapa(itens_banco)

    if set(manifest_map) != set(banco_map):
        raise RuntimeError("Manifest e banco possuem conjuntos de arquivos diferentes.")

    for caminho, item in manifest_map.items():
        banco_item = banco_map[caminho]

        if item.get("backup_path") != f"files/{caminho}":
            raise RuntimeError(f"backup_path inválido no manifest: {caminho}")

        if item.get("size") != banco_item.get("size"):
            raise RuntimeError(f"Tamanho divergente para: {caminho}")

        if item.get("sha256") != banco_item.get("sha256"):
            raise RuntimeError(f"SHA-256 divergente para: {caminho}")

        nome_zip = item["backup_path"]
        if nome_zip not in nomes:
            raise RuntimeError(f"Arquivo ausente no ZIP: {nome_zip}")

        info = zip_file.getinfo(nome_zip)
        if info.is_dir():
            raise RuntimeError(f"Entrada esperada como arquivo, mas é pasta: {nome_zip}")

    return itens_manifest


def restaurar_backup(backup: dict, arquivo_zip: Path, raiz_restauracao: Path, sobrescrever: bool = False):
    raiz_restauracao = raiz_restauracao.resolve()
    raiz_restauracao.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(arquivo_zip, "r") as zip_file:
        itens = validar_manifest_e_metadados(zip_file, backup)

        print(f"Arquivos validados: {len(itens)}")
        print(f"Destino: {raiz_restauracao}")

        destinos = []
        for item in itens:
            relativo = validar_caminho_relativo(item["relative_path"])
            destino = destino_seguro(raiz_restauracao, relativo)
            destinos.append((item, destino))

        existentes = [destino for _, destino in destinos if destino.exists()]
        if existentes and not sobrescrever:
            exemplo = existentes[0]
            raise RuntimeError(
                "A restauração encontrou arquivos existentes. "
                f"Use --overwrite para substituir. Exemplo: {exemplo}"
            )

        for item, destino in destinos:
            nome_zip = item["backup_path"]
            esperado_sha = item["sha256"]
            esperado_tamanho = item["size"]

            sha256 = hashlib.sha256()
            tamanho = 0
            destino.parent.mkdir(parents=True, exist_ok=True)

            # Escreve primeiro em um arquivo temporário ao lado do destino.
            temporario = destino.with_name(destino.name + ".backup-tmp")
            temporario.unlink(missing_ok=True)

            try:
                with zip_file.open(nome_zip, "r") as origem, open(temporario, "wb") as saida:
                    while True:
                        bloco = origem.read(1024 * 1024)
                        if not bloco:
                            break
                        saida.write(bloco)
                        tamanho += len(bloco)
                        sha256.update(bloco)

                if tamanho != esperado_tamanho:
                    raise RuntimeError(f"Tamanho divergente durante restauração: {item['relative_path']}")

                if sha256.hexdigest() != esperado_sha:
                    raise RuntimeError(f"SHA-256 divergente durante restauração: {item['relative_path']}")

                if destino.exists() and sobrescrever:
                    destino.unlink()

                temporario.replace(destino)
                print(f"Restaurado: {destino}")

            except Exception:
                temporario.unlink(missing_ok=True)
                raise


def executar_restore(backup_id: str, destino: str | None = None, sobrescrever: bool = False):
    estado = carregar_estado()

    if estado is None:
        raise RuntimeError("Client ainda não está registrado.")

    arquivo_zip = _base_dir() / f"restore-{backup_id}.zip"

    try:
        backup = baixar_backup(estado, backup_id, arquivo_zip)
        print("Validando manifest e metadados...")

        with zipfile.ZipFile(arquivo_zip, "r") as zip_file:
            itens = validar_manifest_e_metadados(zip_file, backup)

        if destino:
            # Destino explícito continua disponível para uso administrativo,
            # mas a restauração normal do agente usa a origem original.
            raiz = Path(destino).expanduser().resolve()
        else:
            raiz = obter_pasta_original(
                backup.get("source_root"),
                [item["relative_path"] for item in itens],
            )

        print(f"Destino original autorizado: {raiz}")
        restaurar_backup(backup, arquivo_zip, raiz, sobrescrever)
        print()
        print("RESTAURAÇÃO CONCLUÍDA.")
        print(f"Arquivos restaurados em: {raiz.resolve()}")
    finally:
        arquivo_zip.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Restaura um backup do Backup System.")
    parser.add_argument("backup_id", help="ID do backup a restaurar")
    parser.add_argument(
        "--dest",
        help="Pasta raiz onde os caminhos relativos serão recriados",
        default=None,
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Permite substituir arquivos existentes",
    )
    args = parser.parse_args()

    try:
        executar_restore(args.backup_id, args.dest, args.overwrite)
    except Exception as erro:
        print(f"ERRO: {erro}")
        sys.exit(1)


if __name__ == "__main__":
    main()
