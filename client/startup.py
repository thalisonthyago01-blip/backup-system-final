import os
import sys


APP_NAME = "BackupSystem Client"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "BackupSystemClient"


def _comando_inicio():
    """Monta o comando usado pelo Windows para iniciar o client."""
    if getattr(sys, "frozen", False):
        return f'"{os.path.abspath(sys.executable)}" --startup'

    python = os.path.abspath(sys.executable)
    main = os.path.abspath(os.path.join(os.path.dirname(__file__), "main.py"))
    return f'"{python}" "{main}" agent'


def configurar_inicio_automatico():
    """Registra o executável para iniciar automaticamente com o Windows.

    Usa apenas HKCU, portanto não exige administrador.
    """
    if os.name != "nt":
        return False

    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as chave:
            winreg.SetValueEx(
                chave,
                VALUE_NAME,
                0,
                winreg.REG_SZ,
                _comando_inicio(),
            )
        return True
    except OSError:
        return False


def remover_inicio_automatico():
    if os.name != "nt":
        return False

    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as chave:
            try:
                winreg.DeleteValue(chave, VALUE_NAME)
            except FileNotFoundError:
                pass
        return True
    except OSError:
        return False
