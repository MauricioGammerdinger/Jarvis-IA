"""
Ícone de bandeja do J.A.R.V.I.S. — fica na área de notificação do Windows
(perto do relógio), sem nenhuma janela de terminal visível.

Clique direito no ícone pra: abrir o app, ligar/desligar o "Hey JARVIS",
reiniciar o servidor, ou sair (encerra tudo).

⚠️ NÃO TESTADO EM AMBIENTE REAL: pystray precisa de uma interface gráfica
de verdade (bandeja do sistema) — o ambiente onde isso foi escrito é um
servidor Linux sem interface gráfica, então o ícone em si nunca pôde ser
exibido nem clicado de verdade aqui. A lógica de start/stop dos processos
foi testada isoladamente (mockada). Teste no seu PC antes de confiar 100%.

Uso:
    pythonw.exe tray_app.py     (pythonw = sem console, é o que o
                                 start_tray.bat já faz automaticamente)
"""

import subprocess
import sys
import webbrowser
from pathlib import Path

import pystray
from PIL import Image

PROJECT_DIR = Path(__file__).parent.parent  # tray_app.py está em src/, a raiz do projeto é um nível acima
SRC_DIR = Path(__file__).parent  # onde os outros módulos (app.py, wake_word_listener.py) moram
IS_WINDOWS = sys.platform == "win32"
CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0

_venv_python = PROJECT_DIR / "venv" / "Scripts" / "python.exe"
PYTHON = _venv_python if _venv_python.exists() else Path(sys.executable)

APP_URL = "http://localhost:8000/app"

server_process: subprocess.Popen | None = None
wake_word_process: subprocess.Popen | None = None
wake_word_enabled = True  # começa ligado por padrão, igual antes (as duas coisas subiam juntas)


def _is_alive(proc: subprocess.Popen | None) -> bool:
    return proc is not None and proc.poll() is None


def start_server() -> None:
    global server_process
    if _is_alive(server_process):
        return
    server_process = subprocess.Popen(
        [str(PYTHON), "-m", "uvicorn", "app:app", "--app-dir", str(SRC_DIR), "--host", "0.0.0.0", "--port", "8000"],
        cwd=PROJECT_DIR,  # importante: cwd continua na raiz, pra "static/" (relativo) ser achado certo
        creationflags=CREATE_NO_WINDOW,
    )


def stop_server() -> None:
    global server_process
    if _is_alive(server_process):
        server_process.terminate()
    server_process = None


def start_wake_word() -> None:
    global wake_word_process
    if _is_alive(wake_word_process):
        return
    wake_word_process = subprocess.Popen(
        [str(PYTHON), str(SRC_DIR / "wake_word_listener.py")],
        cwd=PROJECT_DIR,
        creationflags=CREATE_NO_WINDOW,
    )


def stop_wake_word() -> None:
    global wake_word_process
    if _is_alive(wake_word_process):
        wake_word_process.terminate()
    wake_word_process = None


def toggle_wake_word(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    global wake_word_enabled
    wake_word_enabled = not wake_word_enabled
    if wake_word_enabled:
        start_wake_word()
    else:
        stop_wake_word()
    icon.update_menu()


def open_app(icon: pystray.Icon = None, item: pystray.MenuItem = None) -> None:
    webbrowser.open(APP_URL)


def restart_server(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    stop_server()
    start_server()


def quit_app(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    stop_server()
    stop_wake_word()
    icon.stop()


def _wake_word_checked(item: pystray.MenuItem) -> bool:
    return wake_word_enabled


def build_menu() -> pystray.Menu:
    return pystray.Menu(
        pystray.MenuItem("Abrir J.A.R.V.I.S.", open_app, default=True),
        pystray.MenuItem("Hey JARVIS (voz)", toggle_wake_word, checked=_wake_word_checked),
        pystray.MenuItem("Reiniciar servidor", restart_server),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Sair", quit_app),
    )


def main() -> None:
    start_server()
    if wake_word_enabled:
        start_wake_word()

    icon_path = PROJECT_DIR / "static" / "icon-192.png"
    image = Image.open(icon_path)

    icon = pystray.Icon("jarvis", image, "J.A.R.V.I.S.", build_menu())
    icon.run()


if __name__ == "__main__":
    main()
