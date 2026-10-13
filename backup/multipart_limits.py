"""Limites configuráveis do parser multipart para backups com muitos arquivos.

Starlette não expõe esses limites como uma configuração do FastAPI. Este módulo
ajusta os padrões usados por Request.form(), mantendo limites finitos para
proteger o serviço contra requisições acidentais ou abusivas.
"""
import os
from starlette.requests import Request

MAX_MULTIPART_FILES = int(os.getenv("BACKUP_MAX_MULTIPART_FILES", "100000"))
MAX_MULTIPART_FIELDS = int(os.getenv("BACKUP_MAX_MULTIPART_FIELDS", "100000"))

_original_get_form = Request._get_form


async def _get_form_with_backup_limits(self, *args, **kwargs):
    # FastAPI pode passar explicitamente max_files=1000 e max_fields=1000.
    # setdefault() não substitui esses valores; por isso sobrescrevemos aqui.
    kwargs["max_files"] = max(MAX_MULTIPART_FILES, int(kwargs.get("max_files", 0) or 0))
    kwargs["max_fields"] = max(MAX_MULTIPART_FIELDS, int(kwargs.get("max_fields", 0) or 0))
    return await _original_get_form(self, *args, **kwargs)


# Aplicado uma vez ao importar o módulo.
Request._get_form = _get_form_with_backup_limits
