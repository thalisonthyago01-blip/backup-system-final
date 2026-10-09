from typing import Annotated

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse

from pathlib import Path

import uuid
import shutil
import hashlib

from collections import Counter
from datetime import datetime, timezone

from backup.services.compression import compactar_arquivos


app = FastAPI()


BASE_DIR = Path(__file__).resolve().parent.parent

STORAGE = BASE_DIR / "storage"
TEMP = BASE_DIR / "temp"


STORAGE.mkdir(exist_ok=True)
TEMP.mkdir(exist_ok=True)


def obter_pasta_machine(machine_id: str):

    try:
        machine_uuid = uuid.UUID(machine_id)

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="machine_id inválido"
        )

    pasta = STORAGE / str(machine_uuid)

    pasta.mkdir(
        parents=True,
        exist_ok=True
    )

    return pasta


def encontrar_backup(
    machine_id: str,
    backup_id: str
):

    try:

        machine_uuid = uuid.UUID(machine_id)
        backup_uuid = uuid.UUID(backup_id)

    except ValueError:

        return None

    pasta_machine = STORAGE / str(machine_uuid)

    arquivo = (
        pasta_machine /
        f"backup-{backup_uuid}.zip"
    )

    if arquivo.exists():

        return arquivo

    return None


def calcular_checksum(arquivo: Path):

    sha256 = hashlib.sha256()

    with open(arquivo, "rb") as file:

        while True:

            bloco = file.read(1024 * 1024)

            if not bloco:
                break

            sha256.update(bloco)

    return sha256.hexdigest()


def limpar_caminho(caminho: str) -> str:
    """
    Transforma o caminho enviado pelo cliente em um caminho relativo e
    seguro para guardar dentro do ZIP. Recusa caminhos com '..'.
    Exemplos:
        "Documentos\\tcc.docx"    -> "Documentos/tcc.docx"
        "C:\\Users\\Enzo\\a.txt"  -> "C/Users/Enzo/a.txt"
    """

    texto = caminho.replace("\\", "/")

    if len(texto) >= 2 and texto[1] == ":" and texto[0].isalpha():
        texto = texto[0] + "/" + texto[2:]

    partes = []

    for parte in texto.split("/"):

        if parte in ("", "."):
            continue

        if parte == ".." or "\x00" in parte:

            raise HTTPException(
                status_code=400,
                detail=f"Caminho inválido: {caminho}"
            )

        partes.append(parte)

    if not partes:

        raise HTTPException(
            status_code=400,
            detail="Caminho vazio"
        )

    return "/".join(partes)


@app.get("/")
def home():

    return {
        "service": "backup",
        "message": "Backup service funcionando!"
    }


@app.post("/create")
async def criar_backup(
    files: Annotated[list[UploadFile], File()],
    machine_id: str,
    paths: Annotated[list[str] | None, Form()] = None,
    source_root: str | None = Form(default=None)
):

    pasta_machine = obter_pasta_machine(
        machine_id
    )

    if paths is None:

        # Sem caminhos: mantém o comportamento antigo (só o nome)
        paths = [
            Path(
                (file.filename or "arquivo").replace("\\", "/")
            ).name
            for file in files
        ]

    if len(files) != len(paths):

        raise HTTPException(
            status_code=400,
            detail="Quantidade de arquivos e caminhos não corresponde"
        )

    caminhos_limpos = [
        limpar_caminho(caminho)
        for caminho in paths
    ]

    contagem = Counter(caminhos_limpos)

    for caminho, quantidade in contagem.items():

        if quantidade > 1:

            raise HTTPException(
                status_code=400,
                detail=f"Caminho repetido: {caminho}"
            )

    backup_id = str(uuid.uuid4())

    pasta_temporaria = TEMP / backup_id

    pasta_arquivos = pasta_temporaria / "files"

    pasta_arquivos.mkdir(
        parents=True,
        exist_ok=True
    )

    arquivos = []
    itens = []

    try:

        for file, original, limpo in zip(
            files,
            paths,
            caminhos_limpos
        ):

            caminho = pasta_arquivos / limpo

            if pasta_arquivos.resolve() not in caminho.resolve().parents:

                raise HTTPException(
                    status_code=400,
                    detail=f"Caminho inválido: {original}"
                )

            try:

                caminho.parent.mkdir(
                    parents=True,
                    exist_ok=True
                )

                with open(
                    caminho,
                    "wb"
                ) as arquivo:

                    shutil.copyfileobj(
                        file.file,
                        arquivo
                    )

            except (
                FileExistsError,
                NotADirectoryError,
                IsADirectoryError
            ):

                raise HTTPException(
                    status_code=400,
                    detail=f"Caminhos em conflito: {original}"
                )

            arquivos.append(
                caminho
            )

            itens.append(
                {
                    "relative_path": limpo,
                    "backup_path": f"files/{limpo}",
                    "size": caminho.stat().st_size,
                    "sha256": calcular_checksum(caminho)
                }
            )

        manifest = {
            "versao": 1,
            "backup_id": backup_id,
            "machine_id": machine_id,
            "criado_em": datetime.now(
                timezone.utc
            ).isoformat(),
            "files": itens
        }

        arquivo_zip = (
            pasta_machine /
            f"backup-{backup_id}.zip"
        )

        compactar_arquivos(
            arquivos,
            arquivo_zip,
            pasta_temporaria,
            manifest
        )

        tamanho = arquivo_zip.stat().st_size

        checksum = calcular_checksum(
            arquivo_zip
        )

        return {
            "id": backup_id,
            "filename": str(
                Path(machine_id) /
                arquivo_zip.name
            ),
            "format": "zip",
            "files": len(arquivos),
            "size": tamanho,
            "files_metadata": [
                {
                    "relative_path": item["relative_path"],
                    "size": item["size"],
                    "sha256": item["sha256"]
                }
                for item in itens
            ],
            "checksum": checksum,
            "status": "completed"
        }

    finally:

        shutil.rmtree(
            pasta_temporaria,
            ignore_errors=True
        )


@app.get(
    "/backups/{backup_id}/download"
)
def baixar_backup(
    backup_id: str,
    machine_id: str
):

    arquivo = encontrar_backup(
        machine_id,
        backup_id
    )

    if arquivo is None:

        raise HTTPException(
            status_code=404,
            detail="Backup não encontrado"
        )

    return FileResponse(
        path=arquivo,
        filename=arquivo.name,
        media_type="application/zip"
    )


@app.get(
    "/backups/{backup_id}/verify"
)
def verificar_backup(
    backup_id: str,
    machine_id: str,
    checksum: str
):

    arquivo = encontrar_backup(
        machine_id,
        backup_id
    )

    if arquivo is None:

        raise HTTPException(
            status_code=404,
            detail="Backup não encontrado"
        )

    checksum_atual = calcular_checksum(
        arquivo
    )

    if checksum_atual == checksum:

        return {
            "id": backup_id,
            "integridade": "ok",
            "checksum_registrado": checksum,
            "checksum_atual": checksum_atual
        }

    return {
        "id": backup_id,
        "integridade": "invalid",
        "checksum_registrado": checksum,
        "checksum_atual": checksum_atual
    }


@app.delete(
    "/backups/{backup_id}"
)
def excluir_backup(
    backup_id: str,
    machine_id: str
):

    arquivo = encontrar_backup(
        machine_id,
        backup_id
    )

    if arquivo is None:

        raise HTTPException(
            status_code=404,
            detail="Backup não encontrado"
        )

    arquivo.unlink()

    return {
        "id": backup_id,
        "status": "deleted"
    }
