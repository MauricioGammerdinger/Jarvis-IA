"""
Controle de mouse e teclado — permite ao JARVIS interagir com o que vê na
tela (clicar em algo, digitar texto, navegar dentro de um app já aberto).

Funciona em conjunto com `ver_tela` (em tools.py): o fluxo típico é
1) tirar um print, 2) o modelo decide onde clicar baseado no que viu,
3) clicar nesse ponto.

⚠️ PROBLEMA TÉCNICO IMPORTANTE QUE ESTE MÓDULO RESOLVE: o `ver_tela`
redimensiona a captura (pra não gastar tokens à toa numa imagem 4K) — então
as coordenadas que o modelo "vê" na imagem NÃO são as mesmas coordenadas
reais da tela. Este módulo guarda a proporção de redimensionamento da
última captura e converte automaticamente as coordenadas de clique de
volta pra escala real da tela.

⚠️ ISSO É MAIS PODEROSO E MAIS ARRISCADO que as outras ferramentas — o
JARVIS passa a poder clicar em QUALQUER coisa visível na tela, incluindo
ações irreversíveis (confirmar compra, deletar algo, enviar mensagem).
Teste com atenção redobrada antes de confiar em tarefas importantes.

⚠️ NÃO TESTADO COM TELA DE VERDADE: o ambiente onde isso foi escrito não
tem interface gráfica. A lógica de escala de coordenadas foi testada com
matemática pura; o clique/digitação de verdade só valida no seu PC.
"""

import sys

_last_screenshot_scale: tuple[float, float] | None = None  # (escala_x, escala_y) da última captura


def set_screenshot_scale(real_width: int, real_height: int, resized_width: int, resized_height: int) -> None:
    """Chamado por `ver_tela` toda vez que tira um print, pra guardar a proporção de redimensionamento."""
    global _last_screenshot_scale
    _last_screenshot_scale = (real_width / resized_width, real_height / resized_height)


def _scale_coords(x: int, y: int) -> tuple[int, int]:
    """Converte coordenadas vistas na imagem redimensionada pra coordenadas reais da tela."""
    if _last_screenshot_scale is None:
        # Nenhuma captura foi feita ainda nesta sessão — assume que não há escala
        # (arriscado, mas melhor que travar; o ideal é sempre chamar ver_tela antes).
        return x, y
    scale_x, scale_y = _last_screenshot_scale
    return round(x * scale_x), round(y * scale_y)


def _check_platform():
    if sys.platform not in ("win32", "darwin"):
        raise RuntimeError(f"Controle de mouse/teclado só suportado no Windows/Mac. Plataforma: {sys.platform}.")


def click_at(x: int, y: int, button: str = "left", double: bool = False) -> str:
    """Move o mouse até (x, y) — nas coordenadas da ÚLTIMA captura de tela — e clica."""
    _check_platform()
    import pyautogui

    real_x, real_y = _scale_coords(x, y)
    pyautogui.moveTo(real_x, real_y, duration=0.2)
    if double:
        pyautogui.doubleClick(button=button)
    else:
        pyautogui.click(button=button)
    return f"Clique realizado em ({real_x}, {real_y}) na tela real (coordenadas informadas: {x}, {y})."


def type_text(text: str) -> str:
    """Digita um texto na posição atual do cursor (onde quer que o foco esteja)."""
    _check_platform()
    import pyautogui

    pyautogui.write(text, interval=0.02)
    return f"Texto digitado: '{text}'"


def press_key(key: str) -> str:
    """Pressiona uma tecla especial (enter, esc, tab, etc)."""
    _check_platform()
    import pyautogui

    pyautogui.press(key)
    return f"Tecla '{key}' pressionada."
