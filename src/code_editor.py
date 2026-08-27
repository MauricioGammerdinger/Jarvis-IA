"""
Leitura e escrita de arquivos de código — pra o JARVIS "ver" e editar
projetos de verdade, sem restrição de pasta (por decisão explícita do
usuário). Duas redes de segurança BARATAS, que não atrapalham a
velocidade de edição direta:

1. Backup automático (.jarvis_backups/arquivo.timestamp.bak) antes de
   qualquer sobrescrita — se um comando de voz for mal-entendido, ou o
   modelo local errar alguma coisa, sempre dá pra recuperar o que tinha
   antes, sem confirmação nenhuma no meio do caminho.
2. Bloqueio só de pastas do SISTEMA OPERACIONAL (Windows, Program Files,
   AppData) — não é sobre não confiar no usuário, é sobre um comando mal
   entendido não conseguir, na pior das hipóteses, estragar o próprio
   Windows. Qualquer outra pasta do PC (incluindo todos os projetos) fica
   liberada, como pedido.
"""

import shutil
from datetime import datetime
from pathlib import Path

BACKUP_DIR_NAME = ".jarvis_backups"

# Prefixos de pastas do sistema — nunca editamos aqui, mesmo sem
# restrição de projeto. Comparação case-insensitive.
_BLOCKED_PREFIXES = [
    "c:\\windows",
    "c:\\program files",
    "c:\\programdata",
    "c:\\$recycle.bin",
]


def _is_blocked(caminho_str: str) -> bool:
    """
    Compara a STRING do caminho diretamente (normalizando barras e
    maiúsculas), em vez de usar Path(...).resolve() — isso importa porque
    a interpretação de caminhos "C:\\..." depende do sistema operacional
    onde o Python está rodando. Comparar a string direto funciona igual
    em qualquer lugar (testado neste ambiente Linux, roda de verdade no
    Windows do usuário).
    """
    normalized = caminho_str.replace("/", "\\").lower()
    if any(normalized.startswith(prefix) for prefix in _BLOCKED_PREFIXES):
        return True
    if "\\appdata\\" in normalized:
        return True
    return False


def read_file(caminho: str) -> str:
    path = Path(caminho)
    if not path.exists():
        return f"Arquivo não encontrado: {caminho}"
    if not path.is_file():
        return f"'{caminho}' não é um arquivo (talvez seja uma pasta?)."
    try:
        conteudo = path.read_text(encoding="utf-8", errors="replace")
        if len(conteudo) > 50_000:
            return conteudo[:50_000] + "\n\n[... arquivo truncado, muito grande pra mostrar inteiro ...]"
        return conteudo
    except Exception as e:
        return f"Erro ao ler '{caminho}': {e}"


def write_file(caminho: str, novo_conteudo: str) -> str:
    if _is_blocked(caminho):
        return (
            f"Bloqueado por segurança: '{caminho}' está numa pasta do sistema operacional "
            f"(Windows/Program Files/AppData). Isso nunca é liberado, mesmo sem restrição "
            f"de projeto — é a única rede de segurança que existe aqui."
        )

    path = Path(caminho)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(novo_conteudo, encoding="utf-8")
            return f"Arquivo novo criado: {path}"
        except Exception as e:
            return f"Erro ao criar '{caminho}': {e}"

    # Backup automático antes de sobrescrever — a edição em si é direta,
    # sem pedir confirmação, mas isso garante que sempre dá pra desfazer.
    try:
        backup_dir = path.parent / BACKUP_DIR_NAME
        backup_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{path.name}.{timestamp}.bak"
        shutil.copy2(path, backup_path)
    except Exception as e:
        return f"Não consegui fazer o backup antes de editar — abortando por segurança. Erro: {e}"

    try:
        path.write_text(novo_conteudo, encoding="utf-8")
        return f"'{path.name}' atualizado com sucesso. Backup do conteúdo anterior em {backup_path}."
    except Exception as e:
        return f"Erro ao escrever '{caminho}' (o backup foi feito, nada foi perdido): {e}"


def list_directory(caminho: str) -> str:
    path = Path(caminho)
    if not path.exists():
        return f"Pasta não encontrada: {caminho}"
    if not path.is_dir():
        return f"'{caminho}' não é uma pasta."
    try:
        itens = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        linhas = [f"{'📁' if i.is_dir() else '📄'} {i.name}" for i in itens if i.name != BACKUP_DIR_NAME]
        if not linhas:
            return "(pasta vazia)"
        if len(linhas) > 100:
            linhas = linhas[:100] + ["... (mais itens, pasta grande)"]
        return "\n".join(linhas)
    except Exception as e:
        return f"Erro ao listar '{caminho}': {e}"
