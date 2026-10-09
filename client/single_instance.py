import os


_mutex_handle = None


def garantir_instancia_unica() -> bool:
    """Retorna False quando outra instância do client já está executando."""
    global _mutex_handle

    if os.name != "nt":
        return True

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE

        nome = "Global\\BackupSystemClientSingleInstance"
        _mutex_handle = kernel32.CreateMutexW(None, False, nome)

        if not _mutex_handle:
            return True

        ERROR_ALREADY_EXISTS = 183
        return ctypes.get_last_error() != ERROR_ALREADY_EXISTS
    except Exception:
        # Falhar aqui não deve impedir o funcionamento do client.
        return True
