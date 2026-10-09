import hashlib
import json
import os
import platform
import socket
import subprocess
from pathlib import Path


def executar_powershell(comando: str) -> str:
    """Executa PowerShell apenas no Windows."""
    resultado = subprocess.run(
        ["powershell", "-NoProfile", "-Command", comando],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return resultado.stdout.strip()


def _ler_arquivo(caminho: str) -> str:
    try:
        return Path(caminho).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def _coletar_windows() -> dict:
    system_uuid = executar_powershell(
        "(Get-CimInstance Win32_ComputerSystemProduct).UUID"
    )

    placa = executar_powershell(
        "(Get-CimInstance Win32_BaseBoard | "
        "Select-Object Manufacturer, Product, SerialNumber | "
        "ConvertTo-Json -Compress)"
    )

    return {
        "system_uuid": system_uuid,
        "motherboard": placa,
    }


def _coletar_linux() -> dict:
    # machine-id é fornecido pelo próprio sistema operacional e é adequado
    # como identificador estável da instalação.
    machine_id = (
        _ler_arquivo("/etc/machine-id")
        or _ler_arquivo("/var/lib/dbus/machine-id")
    )

    system_uuid = _ler_arquivo(
        "/sys/class/dmi/id/product_uuid"
    )

    motherboard = {
        "manufacturer": _ler_arquivo(
            "/sys/class/dmi/id/board_vendor"
        ),
        "product": _ler_arquivo(
            "/sys/class/dmi/id/board_name"
        ),
        "serial": _ler_arquivo(
            "/sys/class/dmi/id/board_serial"
        ),
    }

    return {
        "machine_id": machine_id,
        "system_uuid": system_uuid,
        "motherboard": motherboard,
    }


def coletar_identidade() -> dict:
    sistema = platform.system()

    if sistema == "Windows":
        hardware = _coletar_windows()
    elif sistema == "Linux":
        hardware = _coletar_linux()
    else:
        hardware = {
            "system_uuid": "",
            "motherboard": {},
        }

    return {
        "hardware": hardware,
        "system": {
            "hostname": socket.gethostname(),
            "operating_system": sistema,
            "os_version": platform.version(),
            "architecture": platform.machine(),
        },
    }


def gerar_fingerprint(identidade: dict) -> str:
    """Gera um identificador determinístico sem enviar os dados brutos."""
    hardware = identidade["hardware"]

    dados = json.dumps(
        hardware,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        dados.encode("utf-8")
    ).hexdigest()
