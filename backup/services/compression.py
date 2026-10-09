import json

from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def compactar_arquivos(
    arquivos: list[Path],
    destino: Path,
    base_dir: Path,
    manifest: dict | None = None
):
    with ZipFile(
        destino,
        "w",
        ZIP_DEFLATED
    ) as zip_file:

        for arquivo in arquivos:

            caminho_relativo = arquivo.relative_to(
                base_dir
            )

            zip_file.write(
                arquivo,
                arcname=caminho_relativo.as_posix()
            )

        if manifest is not None:

            zip_file.writestr(
                "manifest.json",
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    indent=2
                )
            )
