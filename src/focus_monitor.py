"""
Detecção de "travado numa tarefa" — DESLIGADO por padrão, opt-in de
verdade (precisa ligar explicitamente no .env). Rastreia SÓ o título da
janela em foco + há quanto tempo não tem atividade de mouse/teclado —
nunca screenshot, nunca OCR, nunca histórico de tecla digitada. E o mais
importante: nada disso é GRAVADO em disco — fica só na memória enquanto
o processo roda, e se o processo reiniciar, o rastreamento começa do
zero (não existe um "histórico de janelas" em lugar nenhum).

A ideia: se você fica muito tempo na MESMA janela sem trocar, e sem
ficar muito tempo parado (o que indicaria que você saiu do lugar, não
que está "travado" trabalhando), o JARVIS oferece ajuda uma vez —
nunca fica repetindo sobre a mesma sessão de foco.
"""

import os
import sys
import time

IS_WINDOWS = sys.platform == "win32"

FOCUS_MONITOR_ENABLED = os.environ.get("JARVIS_FOCUS_MONITOR", "0") == "1"
STUCK_THRESHOLD_MINUTES = float(os.environ.get("JARVIS_STUCK_THRESHOLD_MINUTES", "45"))
# Tempo parado (sem mexer o mouse/teclado) que já conta como "saiu do lugar",
# não "travado pensando" — evita avisar quando a pessoa só foi num café.
IDLE_THRESHOLD_MINUTES = float(os.environ.get("JARVIS_IDLE_THRESHOLD_MINUTES", "3"))

# Estado em memória, nunca gravado em disco — reseta sozinho ao reiniciar o processo.
_estado = {"titulo_atual": None, "desde": None, "ja_avisado": False}


def get_active_window_title() -> str | None:
    """Só o título da janela em foco agora — nada mais. None fora do Windows ou se falhar."""
    if not IS_WINDOWS:
        return None
    try:
        import win32gui

        hwnd = win32gui.GetForegroundWindow()
        return win32gui.GetWindowText(hwnd)
    except Exception:
        return None


def get_idle_seconds() -> float | None:
    """Há quantos segundos não tem input de mouse/teclado — não sabe QUAL tecla, só que teve ou não atividade."""
    if not IS_WINDOWS:
        return None
    try:
        import win32api

        tick_atual = win32api.GetTickCount()
        ultimo_input_tick = win32api.GetLastInputInfo()
        return (tick_atual - ultimo_input_tick) / 1000
    except Exception:
        return None


def check_stuck(agora: float | None = None) -> dict | None:
    """
    Chamado periodicamente (a cada poucos minutos). Devolve um aviso só
    quando detecta "muito tempo na mesma janela, sem ficar parado
    demais" — senão devolve None. `agora` é parâmetro só pra facilitar
    teste (simular passagem de tempo sem precisar esperar de verdade).
    """
    if not FOCUS_MONITOR_ENABLED:
        return None

    titulo = get_active_window_title()
    if not titulo:
        return None

    agora = agora if agora is not None else time.time()
    idle_segundos = get_idle_seconds()

    if titulo != _estado["titulo_atual"]:
        # Mudou de janela — reseta o rastreamento, começa a contar de novo.
        _estado["titulo_atual"] = titulo
        _estado["desde"] = agora
        _estado["ja_avisado"] = False
        return None

    if _estado["desde"] is None:
        _estado["desde"] = agora
        return None

    tempo_na_mesma_janela_min = (agora - _estado["desde"]) / 60

    # Parado demais = provavelmente saiu do lugar, não "travado pensando".
    if idle_segundos is not None and (idle_segundos / 60) > IDLE_THRESHOLD_MINUTES:
        return None

    if tempo_na_mesma_janela_min >= STUCK_THRESHOLD_MINUTES and not _estado["ja_avisado"]:
        _estado["ja_avisado"] = True
        return {"titulo": titulo, "minutos": round(tempo_na_mesma_janela_min)}

    return None


def reset_state() -> None:
    """Só pra teste — limpa o estado em memória entre um cenário e outro."""
    _estado["titulo_atual"] = None
    _estado["desde"] = None
    _estado["ja_avisado"] = False
