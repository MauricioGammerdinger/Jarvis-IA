"""
Leitura de PDF — extrai o texto pra o JARVIS conseguir discutir o
conteúdo de um documento. Só leitura (análise), não cria/edita PDF —
isso já é outra categoria de ferramenta.
"""

from pathlib import Path


def read_pdf(caminho: str, max_paginas: int = 50, max_chars: int = 30_000) -> str:
    """Extrai o texto de um PDF. Nunca lança exceção — devolve mensagem de erro clara se falhar."""
    path = Path(caminho)
    if not path.exists():
        return f"Arquivo não encontrado: {caminho}"
    if path.suffix.lower() != ".pdf":
        return f"'{caminho}' não parece ser um PDF (extensão: {path.suffix})."

    try:
        import pypdf

        leitor = pypdf.PdfReader(str(path))
        total_paginas = len(leitor.pages)
        paginas_a_ler = min(total_paginas, max_paginas)

        partes = []
        for i in range(paginas_a_ler):
            texto_pagina = leitor.pages[i].extract_text() or ""
            if texto_pagina.strip():
                partes.append(texto_pagina)

        texto_completo = "\n\n".join(partes).strip()
        if not texto_completo:
            return f"O PDF tem {total_paginas} página(s), mas não consegui extrair texto (pode ser um PDF escaneado, só imagem)."

        aviso_truncado = ""
        if len(texto_completo) > max_chars:
            texto_completo = texto_completo[:max_chars]
            aviso_truncado = "\n\n[... texto truncado, PDF muito longo pra mostrar inteiro ...]"
        if paginas_a_ler < total_paginas:
            aviso_truncado += f"\n[Mostrando só as primeiras {paginas_a_ler} de {total_paginas} páginas.]"

        return texto_completo + aviso_truncado
    except Exception as e:
        return f"Erro ao ler o PDF '{caminho}': {e}"


def get_pdf_info(caminho: str) -> dict:
    """Metadados básicos — número de páginas, título se tiver, sem extrair o texto todo."""
    path = Path(caminho)
    if not path.exists():
        return {"erro": f"Arquivo não encontrado: {caminho}"}
    try:
        import pypdf

        leitor = pypdf.PdfReader(str(path))
        metadata = leitor.metadata or {}
        return {
            "paginas": len(leitor.pages),
            "titulo": metadata.get("/Title", "") or path.stem,
            "autor": metadata.get("/Author", ""),
        }
    except Exception as e:
        return {"erro": str(e)}
