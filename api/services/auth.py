from fastapi import Header, HTTPException

from api.services.machine_authentication import (
    autenticar_instalacao
)


def autenticar_client(
    x_installation_id: str | None = Header(default=None),
    x_client_key: str | None = Header(default=None)
):

    if not x_installation_id or not x_client_key:
        raise HTTPException(
            status_code=401,
            detail="Credenciais do client não informadas"
        )

    resultado = autenticar_instalacao(
        x_installation_id,
        x_client_key
    )

    if resultado is None:
        raise HTTPException(
            status_code=401,
            detail="Credenciais inválidas"
        )

    return resultado