from pathlib import Path


def descobrir_pastas_locais() -> list[dict]:
    """Descobre pastas comuns do usuário sem iniciar nenhum backup.

    O client apenas informa à API quais pastas existem nesta máquina.
    O conteúdo delas só será enviado quando um job de backup for criado.
    """
    home = Path.home()

    candidatos = [
        ("Área de Trabalho", home / "Desktop"),
        ("Documentos", home / "Documents"),
        ("Downloads", home / "Downloads"),
        ("Imagens", home / "Pictures"),
    ]

    # Windows em português pode usar nomes localizados. O diretório físico
    # nem sempre segue o idioma, então só adicionamos alternativas quando
    # a pasta padrão não existe.
    alternativas = [
        ("Área de Trabalho", home / "Área de Trabalho"),
        ("Documentos", home / "Documentos"),
        ("Downloads", home / "Transferências"),
        ("Imagens", home / "Imagens"),
    ]

    encontrados: list[dict] = []
    vistos: set[str] = set()

    for label, caminho in candidatos + alternativas:
        try:
            if not caminho.is_dir():
                continue
            normalizado = str(caminho.resolve())
        except OSError:
            continue

        chave = normalizado.casefold()
        if chave in vistos:
            continue

        vistos.add(chave)
        encontrados.append({
            "label": label,
            "path": normalizado,
        })

    return encontrados
