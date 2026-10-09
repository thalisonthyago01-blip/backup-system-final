from typing import Annotated

import httpx

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    HTTPException,
    Depends,
    Form,
    Cookie
)

from fastapi.responses import StreamingResponse, Response
from fastapi.openapi.docs import (
    get_swagger_ui_oauth2_redirect_html
)

from pydantic import BaseModel, Field

from api.openapi import custom_openapi
from api.docs import custom_docs

from api.services.machine_authentication import (
    autenticar_instalacao
)

from api.services.auth import (
    autenticar_client
)

from api.services.admin_auth import (
    autenticar_admin,
    encerrar_sessao,
    definir_cookie_sessao,
    remover_cookie_sessao,
    autenticar_admin_request,
    existe_admin,
    criar_primeiro_admin,
    cadastrar_admin,
    listar_admins,
    atualizar_admin,
)

from api.services.admin_management import (
    listar_maquinas,
    listar_pastas_admin,
    adicionar_pasta,
    atualizar_pasta,
    remover_pasta,
)

from api.services.machine_registration import (
    registrar_maquina
)

from api.services.backup_metadata import (
    criar_backup_com_metadata,
    listar_backups_machine,
    obter_backup_machine,
    excluir_backup_metadata,
    criar_backup_files_metadata,
    listar_backup_files
)

from api.services.client_folders import (
    sincronizar_pastas,
    listar_pastas
)

from api.services.backup_jobs import (
    criar_backup_job,
    obter_backup_job,
    atualizar_progresso_backup_job,
)

from api.services.jobs import (
    obter_proximo_job,
    concluir_job,
    falhar_job as registrar_falha_job
)

from api.services.restore_jobs import (
    criar_restore_job,
    obter_restore_job
)


app = FastAPI(
    title="Backup System API",
    docs_url=None,
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)


BACKUP_SERVICE_URL = "http://backup:8001"


app.openapi = lambda: custom_openapi(app)


class MachineRegistration(BaseModel):

    identidade: dict
    fingerprint: str


class MachineAuthentication(BaseModel):

    installation_id: str
    client_key: str


class RestoreRequest(BaseModel):

    destination: str = "default"
    overwrite: bool = False


class RestoreFailure(BaseModel):

    error: str


class ClientFoldersRequest(BaseModel):

    folders: list[dict]


class AdminLoginRequest(BaseModel):

    username: str
    password: str


class AdminUserCreate(BaseModel):

    username: str
    password: str


class AdminUserUpdate(BaseModel):

    active: bool | None = None
    password: str | None = None


class AdminFolderCreate(BaseModel):

    path: str
    label: str = ""


class AdminFolderUpdate(BaseModel):

    enabled: bool | None = None
    label: str | None = None


class BackupJobRequest(BaseModel):

    folder_id: str
    selection_type: str = "folder"
    selection_paths: list[str] = []


class BackupJobProgress(BaseModel):
    progress_percent: int = Field(ge=0, le=100)
    bytes_sent: int = Field(ge=0)
    bytes_total: int = Field(ge=0)
    files_sent: int = Field(ge=0)
    files_total: int = Field(ge=0)
    progress_message: str = "Enviando arquivos"


@app.post("/admin/login")
def admin_login(data: AdminLoginRequest, response: Response):

    resultado = autenticar_admin(data.username, data.password)
    if resultado is None:
        raise HTTPException(
            status_code=401,
            detail="Usuário ou senha do administrador inválidos."
        )

    definir_cookie_sessao(response, resultado["token"])
    return {
        "authenticated": True,
        "username": resultado["username"],
        "expires_at": resultado["expires_at"],
    }


@app.post("/admin/logout")
def admin_logout(
    response: Response,
    bs_admin_session: str | None = Cookie(default=None),
    admin=Depends(autenticar_admin_request)
):

    encerrar_sessao(bs_admin_session)
    remover_cookie_sessao(response)
    return {"authenticated": False}


@app.get("/admin/me")
def admin_me(admin=Depends(autenticar_admin_request)):
    return {"authenticated": True, **admin}


@app.get("/admin/setup")
def admin_setup_status():
    """Informa se ainda é preciso criar o primeiro administrador."""
    return {"needs_setup": not existe_admin()}


@app.post("/admin/setup")
def admin_setup(data: AdminUserCreate, response: Response):
    """Cria o primeiro administrador pelo navegador e já abre a sessão.

    Só funciona enquanto não existir nenhum administrador cadastrado.
    """
    try:
        criar_primeiro_admin(data.username, data.password)
    except PermissionError as erro:
        raise HTTPException(status_code=409, detail=str(erro))
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro))

    resultado = autenticar_admin(data.username, data.password)
    definir_cookie_sessao(response, resultado["token"])
    return {
        "authenticated": True,
        "username": resultado["username"],
        "expires_at": resultado["expires_at"],
    }


@app.get("/admin/users")
def admin_users(admin=Depends(autenticar_admin_request)):
    return {"users": listar_admins()}


@app.post("/admin/users")
def admin_users_create(
    data: AdminUserCreate,
    admin=Depends(autenticar_admin_request)
):
    try:
        return cadastrar_admin(data.username, data.password)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro))


@app.patch("/admin/users/{user_id}")
def admin_users_update(
    user_id: str,
    data: AdminUserUpdate,
    admin=Depends(autenticar_admin_request)
):
    try:
        usuario = atualizar_admin(
            user_id,
            admin["id"],
            active=data.active,
            password=data.password,
        )
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro))

    if usuario is None:
        raise HTTPException(status_code=404, detail="Administrador não encontrado.")

    return usuario


@app.get("/admin/machines")
def admin_machines(admin=Depends(autenticar_admin_request)):
    return {"machines": listar_maquinas()}


@app.get("/admin/machines/{machine_id}/folders")
def admin_machine_folders(
    machine_id: str,
    admin=Depends(autenticar_admin_request)
):
    return {"folders": listar_pastas_admin(machine_id)}


@app.post("/admin/machines/{machine_id}/folders")
def admin_add_folder(
    machine_id: str,
    data: AdminFolderCreate,
    admin=Depends(autenticar_admin_request)
):
    try:
        pasta = adicionar_pasta(machine_id, data.path, data.label)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro))

    if pasta is None:
        raise HTTPException(status_code=404, detail="Máquina não encontrada.")

    return pasta


@app.patch("/admin/folders/{folder_id}")
def admin_update_folder(
    folder_id: str,
    data: AdminFolderUpdate,
    admin=Depends(autenticar_admin_request)
):
    try:
        pasta = atualizar_pasta(
            folder_id,
            enabled=data.enabled,
            label=data.label,
        )
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro))

    if pasta is None:
        raise HTTPException(status_code=404, detail="Pasta não encontrada.")

    return pasta


@app.delete("/admin/folders/{folder_id}")
def admin_delete_folder(
    folder_id: str,
    admin=Depends(autenticar_admin_request)
):
    removida = remover_pasta(folder_id)
    if not removida:
        raise HTTPException(status_code=404, detail="Pasta não encontrada.")

    return {"ok": True, "message": "Pasta removida."}


@app.post("/machines/register")
def registrar_machine(
    data: MachineRegistration
):

    try:

        return registrar_maquina(
            data.identidade,
            data.fingerprint
        )

    except Exception as erro:

        raise HTTPException(
            status_code=500,
            detail=str(erro)
        )


@app.post("/machines/authenticate")
def autenticar_machine(
    data: MachineAuthentication
):

    try:

        resultado = autenticar_instalacao(
            data.installation_id,
            data.client_key
        )

        if resultado is None:

            raise HTTPException(
                status_code=401,
                detail="Credencial inválida"
            )

        return {
            "authenticated": True,
            **resultado
        }

    except HTTPException:

        raise

    except Exception as erro:

        raise HTTPException(
            status_code=500,
            detail=str(erro)
        )


@app.get(
    "/docs",
    include_in_schema=False
)
async def docs():

    return custom_docs()


@app.get(
    "/docs/oauth2-redirect",
    include_in_schema=False
)
async def swagger_ui_redirect():

    return get_swagger_ui_oauth2_redirect_html()


@app.get("/")
def home():

    return {
        "message": "API funcionando!"
    }


@app.post("/backup")
async def criar_backup(
    files: Annotated[
        list[UploadFile],
        File()
    ],
    paths: Annotated[
        list[str],
        Form()
    ],
    source_root: Annotated[str | None, Form()] = None,
    client=Depends(autenticar_client)
):

    if len(files) != len(paths):

        raise HTTPException(
            status_code=400,
            detail="Quantidade de arquivos e caminhos não corresponde"
        )

    arquivos = []

    for index, file in enumerate(files):

        conteudo = await file.read()

        arquivos.append(
            (
                "files",
                (
                    file.filename,
                    conteudo,
                    file.content_type
                )
            )
        )

    formularios = {"paths": paths}

    with httpx.Client() as http_client:

        response = http_client.post(
            f"{BACKUP_SERVICE_URL}/create",
            params={
                "machine_id": client["machine_id"]
            },
            files=arquivos,
            data={**formularios, "source_root": source_root or ""},
            timeout=300
        )

    if response.status_code >= 400:

        raise HTTPException(
            status_code=response.status_code,
            detail=response.text
        )

    backup = response.json()

    try:

        criar_backup_com_metadata(
            backup_id=backup["id"],
            machine_id=client["machine_id"],
            filename=backup["filename"],
            formato=backup["format"],
            quantidade_arquivos=backup["files"],
            tamanho=backup["size"],
            checksum=backup["checksum"],
            status=backup["status"],
            arquivos=backup.get("files_metadata", []),
            source_root=source_root or None
        )

    except Exception as erro:

        try:

            with httpx.Client() as http_client:

                http_client.delete(
                    f"{BACKUP_SERVICE_URL}/backups/{backup['id']}",
                    params={
                        "machine_id": client["machine_id"]
                    },
                    timeout=60
                )

        except Exception:

            pass

        raise HTTPException(
            status_code=500,
            detail=(
                "Backup criado, mas não foi possível "
                f"registrar os metadados: {erro}"
            )
        )

    backup.pop("files_metadata", None)

    return backup


@app.get("/backups")
async def listar_backups(
    client=Depends(autenticar_client)
):

    return listar_backups_machine(
        client["machine_id"]
    )


@app.get("/backups/{backup_id}")
async def obter_backup(
    backup_id: str,
    client=Depends(autenticar_client)
):

    backup = obter_backup_machine(
        client["machine_id"],
        backup_id
    )

    if backup is None:

        raise HTTPException(
            status_code=404,
            detail="Backup não encontrado"
        )

    backup["files_metadata"] = listar_backup_files(backup_id)

    return backup


@app.get(
    "/backups/{backup_id}/download"
)
async def baixar_backup(
    backup_id: str,
    client=Depends(autenticar_client)
):

    backup = obter_backup_machine(
        client["machine_id"],
        backup_id
    )

    if backup is None:

        raise HTTPException(
            status_code=404,
            detail="Backup não encontrado"
        )

    http_client = httpx.AsyncClient()

    response = await http_client.get(
        f"{BACKUP_SERVICE_URL}/backups/{backup_id}/download",
        params={
            "machine_id": client["machine_id"]
        },
        timeout=300
    )

    if response.status_code != 200:

        await http_client.aclose()

        raise HTTPException(
            status_code=response.status_code,
            detail=response.text
        )

    async def gerar_arquivo():

        try:

            yield response.content

        finally:

            await http_client.aclose()

    return StreamingResponse(
        gerar_arquivo(),
        media_type="application/zip",
        headers={
            "Content-Disposition":
                response.headers.get(
                    "content-disposition",
                    (
                        f'attachment; '
                        f'filename="backup-{backup_id}.zip"'
                    )
                )
        }
    )


@app.get(
    "/backups/{backup_id}/verify"
)
async def verificar_backup(
    backup_id: str,
    client=Depends(autenticar_client)
):

    backup = obter_backup_machine(
        client["machine_id"],
        backup_id
    )

    if backup is None:

        raise HTTPException(
            status_code=404,
            detail="Backup não encontrado"
        )

    async with httpx.AsyncClient() as http_client:

        response = await http_client.get(
            f"{BACKUP_SERVICE_URL}/backups/{backup_id}/verify",
            params={
                "machine_id": client["machine_id"],
                "checksum": backup["checksum"]
            }
        )

    if response.status_code >= 400:

        raise HTTPException(
            status_code=response.status_code,
            detail=response.text
        )

    return response.json()


@app.get("/client/folders")
async def consultar_pastas_client(
    client=Depends(autenticar_client)
):
    return listar_pastas(client["machine_id"])


@app.post("/client/folders/sync")
async def sincronizar_pastas_client(
    data: ClientFoldersRequest,
    client=Depends(autenticar_client)
):
    sincronizar_pastas(client["machine_id"], data.folders)
    return {"folders": listar_pastas(client["machine_id"])}


@app.post("/backup-jobs")
async def solicitar_backup(
    data: BackupJobRequest,
    client=Depends(autenticar_client)
):

    if data.selection_type not in {"folder", "subfolder", "files"}:
        raise HTTPException(status_code=400, detail="Tipo de seleção inválido.")

    caminhos = [str(p).replace("\\", "/").strip("/") for p in data.selection_paths if str(p).strip()]
    if any(not p or p.startswith("../") or "/../" in f"/{p}/" or p == ".." for p in caminhos):
        raise HTTPException(status_code=400, detail="Caminho de seleção inválido.")

    if data.selection_type == "folder" and caminhos:
        raise HTTPException(status_code=400, detail="Uma seleção de pasta não deve informar caminhos.")
    if data.selection_type in {"subfolder", "files"} and not caminhos:
        raise HTTPException(status_code=400, detail="Informe ao menos um caminho relativo.")
    if data.selection_type == "subfolder" and len(caminhos) != 1:
        raise HTTPException(status_code=400, detail="Uma subpasta deve informar um único caminho.")

    job = criar_backup_job(
        machine_id=client["machine_id"],
        folder_id=data.folder_id,
        selection_type=data.selection_type,
        selection_paths=caminhos,
    )

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Pasta não encontrada ou desativada para esta máquina."
        )

    return job


@app.get("/backup-jobs/{job_id}")
async def consultar_backup_job(
    job_id: str,
    client=Depends(autenticar_client)
):

    job = obter_backup_job(
        client["machine_id"],
        job_id
    )

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Tarefa de backup não encontrada"
        )

    return job


@app.post("/backups/{backup_id}/restore")
async def solicitar_restauracao(
    backup_id: str,
    data: RestoreRequest,
    client=Depends(autenticar_client)
):

    if data.destination != "default":
        raise HTTPException(
            status_code=400,
            detail="Por enquanto, somente a pasta padrão do client está disponível."
        )

    backup = obter_backup_machine(
        client["machine_id"],
        backup_id
    )

    if backup is None:
        raise HTTPException(
            status_code=404,
            detail="Backup não encontrado"
        )

    job = criar_restore_job(
        machine_id=client["machine_id"],
        backup_id=backup_id,
        destination=data.destination,
        overwrite=data.overwrite
    )

    return job


@app.get("/restore-jobs/{job_id}")
async def consultar_restauracao(
    job_id: str,
    client=Depends(autenticar_client)
):

    job = obter_restore_job(
        client["machine_id"],
        job_id
    )

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Tarefa de restauração não encontrada"
        )

    return job


@app.get("/client/jobs/next")
async def proximo_job(
    client=Depends(autenticar_client)
):

    job = obter_proximo_job(client["machine_id"])

    if job is None:
        return Response(status_code=204)

    return job


@app.post("/client/jobs/{job_id}/progress")
async def atualizar_progresso_job(
    job_id: str,
    data: BackupJobProgress,
    client=Depends(autenticar_client),
):
    job = atualizar_progresso_backup_job(
        client["machine_id"],
        job_id,
        data,
    )
    if job is None:
        raise HTTPException(
            status_code=409,
            detail="A tarefa não está em execução ou não pertence a esta máquina.",
        )
    return job


@app.post("/client/jobs/{job_id}/complete")
async def completar_job(
    job_id: str,
    client=Depends(autenticar_client)
):

    job = concluir_job(
        client["machine_id"],
        job_id
    )

    if job is None:
        raise HTTPException(
            status_code=409,
            detail="Tarefa não está em execução ou não pertence a esta máquina."
        )

    return job


@app.post("/client/jobs/{job_id}/fail")
async def falhar_job(
    job_id: str,
    data: RestoreFailure,
    client=Depends(autenticar_client)
):

    job = registrar_falha_job(
        client["machine_id"],
        job_id,
        data.error
    )

    if job is None:
        raise HTTPException(
            status_code=409,
            detail="Tarefa não está em execução ou não pertence a esta máquina."
        )

    return job


@app.delete(
    "/backups/{backup_id}"
)
async def excluir_backup(
    backup_id: str,
    client=Depends(autenticar_client)
):

    backup = obter_backup_machine(
        client["machine_id"],
        backup_id
    )

    if backup is None:

        raise HTTPException(
            status_code=404,
            detail="Backup não encontrado"
        )

    async with httpx.AsyncClient() as http_client:

        response = await http_client.delete(
            f"{BACKUP_SERVICE_URL}/backups/{backup_id}",
            params={
                "machine_id": client["machine_id"]
            }
        )

    if response.status_code >= 400:

        raise HTTPException(
            status_code=response.status_code,
            detail=response.text
        )

    excluir_backup_metadata(
        client["machine_id"],
        backup_id
    )

    return response.json()