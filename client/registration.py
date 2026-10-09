import httpx

from client.machine_identity import coletar_identidade, gerar_fingerprint
from client.client_state import carregar_estado, salvar_estado


SERVER_URL = "http://localhost:8000"


def registrar_cliente(server_url: str = SERVER_URL):
    """Registra esta instalação no servidor e salva as credenciais recebidas."""
    estado = carregar_estado()

    if estado:
        return {
            "registered": True,
            "new_registration": False,
            "state": estado,
        }

    identidade = coletar_identidade()
    fingerprint = gerar_fingerprint(identidade)

    dados = {
        "identidade": identidade,
        "fingerprint": fingerprint,
    }

    response = httpx.post(
        f"{server_url}/machines/register",
        json=dados,
        timeout=10,
    )
    response.raise_for_status()

    registro = response.json()

    estado = {
        "machine_id": registro["machine_id"],
        "installation_id": registro["installation_id"],
        "client_key": registro["client_key"],
        "server": server_url,
    }

    salvar_estado(estado)

    return {
        "registered": True,
        "new_registration": True,
        "state": estado,
    }
