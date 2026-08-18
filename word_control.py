"""
Controle do Microsoft Word — só funciona no Windows, com o Word instalado.

Usa `pywin32` (win32com.client) pra controlar o Word de verdade via COM —
a mesma tecnologia que macros de VBA usam. É bem mais confiável que tentar
simular clique de mouse/teclado (pyautogui): aqui é o próprio Word sendo
comandado pela API dele, não uma simulação visual que quebra se a janela
mudar de posição.

⚠️ NÃO TESTADO EM AMBIENTE REAL: este código foi escrito com base na API
documentada do win32com/Word, mas o ambiente onde ele foi desenvolvido é
Linux e não tem Word instalado — não foi possível rodar de ponta a ponta.
Teste com cuidado no seu PC antes de confiar 100% nele.
"""

import sys
from pathlib import Path


def _check_windows():
    if sys.platform != "win32":
        raise RuntimeError(
            "Automação do Word só funciona no Windows (detectei: " + sys.platform + "). "
            "No Linux/Mac, essa ferramenta fica indisponível."
        )


def write_word_document(content: str, filename: str = "documento_jarvis.docx", save_dir: str | None = None) -> str:
    """
    Abre o Word, cria um novo documento, escreve o conteúdo e salva.
    Retorna o caminho completo do arquivo salvo.
    """
    _check_windows()
    try:
        import win32com.client
    except ImportError:
        raise RuntimeError(
            "Biblioteca pywin32 não instalada. Rode: pip install pywin32"
        )

    save_dir = save_dir or str(Path.home() / "Documents")
    Path(save_dir).mkdir(parents=True, exist_ok=True)
    full_path = str(Path(save_dir) / filename)
    if not full_path.endswith(".docx"):
        full_path += ".docx"

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = True  # deixa visível de propósito — você vê o JARVIS escrevendo, não é uma ação escondida
    try:
        doc = word.Documents.Add()
        doc.Content.Text = content
        doc.SaveAs(full_path)
        return full_path
    finally:
        # Não fechamos o Word nem o documento — deixa aberto pra você conferir/editar.
        pass


def append_to_word_document(content: str, full_path: str) -> str:
    """Abre um documento .docx já existente e adiciona texto ao final."""
    _check_windows()
    try:
        import win32com.client
    except ImportError:
        raise RuntimeError("Biblioteca pywin32 não instalada. Rode: pip install pywin32")

    if not Path(full_path).exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {full_path}")

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = True
    doc = word.Documents.Open(full_path)
    try:
        doc.Content.InsertAfter("\n" + content)
        doc.Save()
        return full_path
    finally:
        pass
