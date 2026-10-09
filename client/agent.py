import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

from client.client_state import carregar_estado, STATE_FILE
from client.registration import registrar_cliente
from client.restore import executar_restore
from client.backup import executar_backup
from client.folders import descobrir_pastas_locais
from client.authorized_folders import (
    salvar_pastas_autorizadas,
    obter_pasta_por_id,
    obter_raiz_autorizada,
    carregar_pastas_autorizadas,
)


INTERVALO = 5
INTERVALO_SINCRONIZACAO = 30
LOCAL_DISCOVERY_HOST = "127.0.0.1"
LOCAL_DISCOVERY_PORT = 8765


class _CredenciaisHandler(BaseHTTPRequestHandler):
    """Ponte local entre o navegador e o client instalado.

    O navegador não consegue acessar caminhos absolutos do computador por
    motivos de segurança. Por isso, as ações da tela principal pedem ao
    próprio client para selecionar a pasta/arquivos e criar o mesmo job
    usado pelo botão "Backup pelo client".
    """

    def do_OPTIONS(self):
        self.send_response(204)
        self._cabecalhos()
        self.end_headers()

    def do_GET(self):
        if self.path != "/credentials":
            self.send_error(404)
            return

        estado = carregar_estado()
        if not estado:
            self.send_error(404)
            return

        self._responder_json({
            "installation_id": estado["installation_id"],
            "client_key": estado["client_key"],
        })

    def do_POST(self):
        rotas = {
            "/backup/folder": self._backup_pasta,
            "/backup/files": self._backup_arquivos,
            "/backup/drop": self._backup_drop,
        }

        handler = rotas.get(self.path)
        if handler is None:
            self.send_error(404)
            return

        origem = self.headers.get("Origin", "")
        if origem not in {"http://localhost:8080", "http://127.0.0.1:8080"}:
            self.send_error(403)
            return

        try:
            dados = self._ler_json()
            estado = carregar_estado()
            if not estado:
                raise RuntimeError("Client ainda não está registrado.")

            resultado = handler(estado, dados)
            self._responder_json(resultado)
        except Exception as erro:
            self._responder_json({"detail": str(erro)}, status=400)

    def _ler_json(self):
        tamanho = int(self.headers.get("Content-Length", "0") or 0)
        if tamanho > 1024 * 1024:
            raise RuntimeError("Requisição muito grande.")

        bruto = self.rfile.read(tamanho) if tamanho else b"{}"
        try:
            dados = json.loads(bruto.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as erro:
            raise RuntimeError("JSON inválido.") from erro

        if not isinstance(dados, dict):
            raise RuntimeError("Dados inválidos.")
        return dados

    def _responder_json(self, dados, status=200):
        conteudo = json.dumps(
            dados,
            ensure_ascii=False,
        ).encode("utf-8")

        self.send_response(status)
        self._cabecalhos()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(conteudo)))
        self.end_headers()
        self.wfile.write(conteudo)

    def _cabecalhos(self):
        origem = self.headers.get("Origin", "")
        if origem in {"http://localhost:8080", "http://127.0.0.1:8080"}:
            self.send_header("Access-Control-Allow-Origin", origem)
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type",
        )
        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, POST, OPTIONS",
        )
        self.send_header("Cache-Control", "no-store")

    @staticmethod
    def _selecionar_pasta():
        try:
            import tkinter as tk
            from tkinter import filedialog
        except Exception as erro:
            raise RuntimeError(
                "Não foi possível abrir o seletor de pastas no client."
            ) from erro

        raiz = tk.Tk()
        raiz.withdraw()
        raiz.attributes("-topmost", True)
        try:
            caminho = filedialog.askdirectory(
                title="Selecione a pasta para o backup"
            )
        finally:
            raiz.destroy()

        if not caminho:
            raise RuntimeError("Seleção cancelada.")
        return Path(caminho).expanduser().resolve()

    @staticmethod
    def _selecionar_arquivos():
        try:
            import tkinter as tk
            from tkinter import filedialog
        except Exception as erro:
            raise RuntimeError(
                "Não foi possível abrir o seletor de arquivos no client."
            ) from erro

        raiz = tk.Tk()
        raiz.withdraw()
        raiz.attributes("-topmost", True)
        try:
            caminhos = filedialog.askopenfilenames(
                title="Selecione os arquivos para o backup"
            )
        finally:
            raiz.destroy()

        if not caminhos:
            raise RuntimeError("Seleção cancelada.")

        return [Path(c).expanduser().resolve() for c in caminhos]

    @staticmethod
    def _pasta_por_caminho(caminho):
        caminho = Path(caminho).resolve()
        correspondencias = []

        for pasta in carregar_pastas_autorizadas():
            raiz = Path(str(pasta.get("path", ""))).expanduser().resolve()
            try:
                caminho.relative_to(raiz)
                correspondencias.append((raiz, pasta))
            except ValueError:
                continue

        if not correspondencias:
            raise RuntimeError(
                f"O caminho não pertence a nenhuma pasta autorizada: {caminho}"
            )

        raiz, pasta = max(
            correspondencias,
            key=lambda item: len(item[0].parts),
        )
        return raiz, pasta

    @classmethod
    def _job_pasta(cls, estado, caminho):
        caminho = Path(caminho).resolve()
        if not caminho.is_dir():
            raise RuntimeError(f"A pasta não existe: {caminho}")

        raiz, pasta = cls._pasta_por_caminho(caminho)
        relativa = caminho.relative_to(raiz).as_posix()

        if not relativa:
            tipo = "folder"
            selecoes = []
        else:
            tipo = "subfolder"
            selecoes = [relativa]

        return criar_job_backup(
            estado,
            str(pasta["id"]),
            tipo,
            selecoes,
        )

    @classmethod
    def _job_arquivos(cls, estado, caminhos):
        if not caminhos:
            raise RuntimeError("Nenhum arquivo foi selecionado.")

        caminhos = [Path(c).resolve() for c in caminhos]
        raiz, pasta = cls._pasta_por_caminho(caminhos[0])

        relativos = []
        for caminho in caminhos:
            if not caminho.is_file():
                raise RuntimeError(f"Arquivo não encontrado: {caminho}")

            outra_raiz, outra_pasta = cls._pasta_por_caminho(caminho)
            if outra_raiz.resolve() != raiz.resolve():
                raise RuntimeError(
                    "Todos os arquivos selecionados precisam estar dentro "
                    "da mesma pasta autorizada."
                )

            relativos.append(caminho.relative_to(raiz).as_posix())

        return criar_job_backup(
            estado,
            str(pasta["id"]),
            "files",
            relativos,
        )

    @classmethod
    def _backup_pasta(cls, estado, dados):
        return cls._job_pasta(
            estado,
            cls._selecionar_pasta(),
        )

    @classmethod
    def _backup_arquivos(cls, estado, dados):
        return cls._job_arquivos(
            estado,
            cls._selecionar_arquivos(),
        )

    @staticmethod
    def _localizar_pasta_por_nome(nome):
        alvo = str(nome or "").strip().casefold()
        if not alvo:
            return []

        candidatos = []
        for pasta in carregar_pastas_autorizadas():
            raiz = Path(str(pasta.get("path", ""))).expanduser().resolve()
            if not raiz.is_dir():
                continue

            # Primeiro considera a própria raiz autorizada.
            if raiz.name.casefold() == alvo or str(pasta.get("label", "")).casefold() == alvo:
                candidatos.append(raiz)

            # Depois procura subpastas. O navegador não entrega o caminho
            # absoluto do item arrastado, então o nome é a única informação
            # de localização disponível para este fluxo.
            try:
                for candidato in raiz.rglob("*"):
                    if candidato.is_dir() and candidato.name.casefold() == alvo:
                        candidatos.append(candidato.resolve())
            except OSError:
                continue

        unicos = {}
        for candidato in candidatos:
            unicos[str(candidato).casefold()] = candidato
        return list(unicos.values())

    @staticmethod
    def _localizar_arquivo_por_nome(nome):
        alvo = str(nome or "").strip().casefold()
        if not alvo:
            return []

        candidatos = []
        for pasta in carregar_pastas_autorizadas():
            raiz = Path(str(pasta.get("path", ""))).expanduser().resolve()
            if not raiz.is_dir():
                continue
            try:
                for candidato in raiz.rglob("*"):
                    if candidato.is_file() and candidato.name.casefold() == alvo:
                        candidatos.append(candidato.resolve())
            except OSError:
                continue

        unicos = {}
        for candidato in candidatos:
            unicos[str(candidato).casefold()] = candidato
        return list(unicos.values())

    @classmethod
    def _backup_drop(cls, estado, dados):
        tipo = str(dados.get("kind", "")).strip().lower()
        nome = str(dados.get("name", "")).strip()

        if tipo == "folder":
            candidatos = cls._localizar_pasta_por_nome(nome)
            if len(candidatos) == 1:
                return cls._job_pasta(estado, candidatos[0])
            if not candidatos:
                raise RuntimeError(
                    f'Não foi possível localizar automaticamente a pasta arrastada: "{nome}". '
                    "Ela precisa estar dentro de uma pasta autorizada."
                )
            raise RuntimeError(
                f'A pasta "{nome}" existe em mais de um local autorizado. '
                "Use o botão Enviar pasta para selecionar a origem."
            )

        nomes = dados.get("names") or ([nome] if nome else [])
        if not isinstance(nomes, list):
            raise RuntimeError("Arquivos arrastados inválidos.")

        nomes = [str(item).strip() for item in nomes if str(item).strip()]
        if not nomes:
            raise RuntimeError("Nenhum arquivo foi informado pelo arrastar e soltar.")

        caminhos = []
        for nome_arquivo in nomes:
            candidatos = cls._localizar_arquivo_por_nome(nome_arquivo)
            if len(candidatos) == 0:
                raise RuntimeError(
                    f'Não foi possível localizar automaticamente o arquivo "{nome_arquivo}" '
                    "em uma pasta autorizada."
                )
            if len(candidatos) > 1:
                raise RuntimeError(
                    f'O arquivo "{nome_arquivo}" existe em mais de um local autorizado. '
                    "Use o botão Enviar documentos para selecionar a origem."
                )
            caminhos.append(candidatos[0])

        return cls._job_arquivos(estado, caminhos)

    def log_message(self, *_args):
        return

def iniciar_descoberta_local():
    servidor = ThreadingHTTPServer(
        (LOCAL_DISCOVERY_HOST, LOCAL_DISCOVERY_PORT),
        _CredenciaisHandler,
    )
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    print(f"Descoberta automática disponível em http://{LOCAL_DISCOVERY_HOST}:{LOCAL_DISCOVERY_PORT}/credentials")
    return servidor


def _headers(estado: dict) -> dict:
    return {
        "X-Installation-ID": estado["installation_id"],
        "X-Client-Key": estado["client_key"],
    }


def sincronizar_pastas(client: httpx.Client, estado: dict):
    pastas = descobrir_pastas_locais()

    response = client.post(
        f"{estado['server']}/client/folders/sync",
        headers=_headers(estado),
        json={"folders": pastas},
        timeout=15,
    )
    response.raise_for_status()
    resposta = response.json()
    pastas_autorizadas = resposta.get("folders", [])
    salvar_pastas_autorizadas(pastas_autorizadas)

    print("Pastas locais autorizadas:")
    for pasta in pastas_autorizadas:
        if pasta.get("enabled"):
            print(f"  - {pasta['label']}: {pasta['path']}")



def criar_job_backup(estado: dict, folder_id: str, selection_type: str, selection_paths: list[str]):
    if selection_type not in {"folder", "subfolder", "files"}:
        raise RuntimeError("Tipo de seleção inválido.")

    caminhos = [
        str(c).replace("\\", "/").strip("/")
        for c in selection_paths
        if str(c).strip()
    ]

    response = httpx.post(
        f"{estado['server']}/backup-jobs",
        headers=_headers(estado),
        json={
            "folder_id": folder_id,
            "selection_type": selection_type,
            "selection_paths": caminhos,
        },
        timeout=15,
    )

    if response.status_code >= 400:
        try:
            detalhe = response.json().get("detail", response.text)
        except Exception:
            detalhe = response.text
        raise RuntimeError(str(detalhe))

    return response.json()

def buscar_job(client: httpx.Client, estado: dict):
    response = client.get(
        f"{estado['server']}/client/jobs/next",
        headers=_headers(estado),
        timeout=15,
    )

    if response.status_code == 204:
        return None

    if response.status_code == 401:
        raise RuntimeError("Credenciais do client foram rejeitadas pelo servidor.")

    response.raise_for_status()
    return response.json()


def informar_conclusao(client: httpx.Client, estado: dict, job_id: str):
    response = client.post(
        f"{estado['server']}/client/jobs/{job_id}/complete",
        headers=_headers(estado),
        timeout=30,
    )
    response.raise_for_status()


def informar_falha(client: httpx.Client, estado: dict, job_id: str, erro: Exception):
    try:
        response = client.post(
            f"{estado['server']}/client/jobs/{job_id}/fail",
            headers=_headers(estado),
            json={"error": str(erro)},
            timeout=30,
        )
        response.raise_for_status()
    except Exception as envio_erro:
        print(f"Não foi possível registrar a falha do job: {envio_erro}")


def executar_job(client: httpx.Client, estado: dict, job: dict):
    job_id = job["id"]
    tipo = job.get("type")

    try:
        if tipo == "backup":
            folder_id = job.get("folder_id")
            if not folder_id:
                raise RuntimeError("A tarefa de backup não informou a pasta autorizada.")

            caminho = obter_pasta_por_id(folder_id)
            selection_type = job.get("selection_type", "folder")
            selection_paths = job.get("selection_paths") or []
            print(f"Tarefa de backup recebida: {job_id}")
            print(f"Pasta autorizada: {caminho}")
            def informar_progresso(progresso):
                response = httpx.post(
                    f"{estado['server']}/client/jobs/{job_id}/progress",
                    headers=_headers(estado),
                    json=progresso,
                    timeout=10,
                )
                response.raise_for_status()

            if selection_type == "folder":
                executar_backup(folder_id=folder_id, progress_callback=informar_progresso)
            elif selection_type == "subfolder":
                executar_backup(folder_id=folder_id, relative_path=selection_paths[0], progress_callback=informar_progresso)
            elif selection_type == "files":
                executar_backup(folder_id=folder_id, paths=selection_paths, progress_callback=informar_progresso)
            else:
                raise RuntimeError(f"Tipo de seleção desconhecido: {selection_type}")

        elif tipo == "restore":
            backup_id = job["backup_id"]
            overwrite = bool(job.get("overwrite", False))

            print(f"Tarefa de restauração recebida: {job_id}")
            print(f"Backup: {backup_id}")

            executar_restore(
                backup_id,
                destino=None,
                sobrescrever=overwrite,
            )

        else:
            raise RuntimeError(f"Tipo de tarefa desconhecido: {tipo}")

        informar_conclusao(client, estado, job_id)
        print(f"Tarefa concluída: {job_id}")
    except Exception as erro:
        print(f"Falha na tarefa {job_id}: {erro}")
        informar_falha(client, estado, job_id, erro)


def executar_agent(intervalo: int = INTERVALO, stop_event=None):
    """Mantém o client residente mesmo quando o servidor ainda não está disponível.

    O Windows pode iniciar o client antes do Docker/API. Por isso, falhas de
    registro, sincronização ou comunicação são tratadas como temporárias e o
    processo continua vivo na bandeja, tentando novamente.
    """
    servidor_descoberta = None

    while not (stop_event is not None and stop_event.is_set()):
        estado = carregar_estado()

        if not estado:
            try:
                print("Client ainda não está registrado. Tentando registrar...")
                resultado = registrar_cliente()
                estado = resultado["state"]
                print("Client registrado com sucesso.")
            except Exception as erro:
                print(f"Servidor indisponível durante o registro: {erro}")
                if stop_event is not None:
                    stop_event.wait(10)
                else:
                    time.sleep(10)
                continue

        if servidor_descoberta is None:
            try:
                servidor_descoberta = iniciar_descoberta_local()
            except OSError as erro:
                # Outra instância pode ter deixado a ponte local aberta.
                # Nesse caso o processo continua funcionando e tenta reutilizar
                # a porta sem derrubar o client.
                print(f"Aviso ao iniciar descoberta local: {erro}")

        print("Backup Client Agent iniciado.")
        print(f"Servidor: {estado['server']}")
        print(f"Machine ID: {estado['machine_id']}")
        print(f"Installation ID: {estado['installation_id']}")
        print(f"Estado: {STATE_FILE}")
        print(f"Verificação de tarefas a cada {intervalo}s.")

        try:
            with httpx.Client() as client:
                ultima_sincronizacao = 0.0

                while not (stop_event is not None and stop_event.is_set()):
                    try:
                        agora = time.monotonic()
                        if agora - ultima_sincronizacao >= INTERVALO_SINCRONIZACAO:
                            sincronizar_pastas(client, estado)
                            ultima_sincronizacao = agora

                        job = buscar_job(client, estado)

                        if job:
                            executar_job(client, estado, job)

                    except KeyboardInterrupt:
                        print("Agent encerrado.")
                        return
                    except Exception as erro:
                        # Erros de rede/API não encerram o aplicativo. O client
                        # permanece na bandeja e tenta novamente no próximo ciclo.
                        print(f"Erro temporário do client: {erro}")

                    if stop_event is not None:
                        stop_event.wait(intervalo)
                    else:
                        time.sleep(intervalo)

        except Exception as erro:
            print(f"Erro no ciclo do client: {erro}")
            if stop_event is not None:
                stop_event.wait(10)
            else:
                time.sleep(10)

    print("Backup Client encerrado.")
