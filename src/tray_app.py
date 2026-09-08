"""
Ícone de bandeja do J.A.R.V.I.S. — fica na área de notificação do Windows
(perto do relógio), sem nenhuma janela de terminal visível.

Clique direito no ícone pra: abrir o app, ligar/desligar o "Hey JARVIS",
reiniciar o servidor, ou sair (encerra tudo). Também roda uma checagem de
saúde ao ligar (Ollama, modelo, microfone) e reinicia sozinho servidor
ou escuta de voz se algum cair, com aviso — até um limite, pra não entrar
num loop infinito de crash se algo estiver fundamentalmente quebrado.

⚠️ NÃO TESTADO EM AMBIENTE REAL: pystray precisa de uma interface gráfica
de verdade (bandeja do sistema) — o ambiente onde isso foi escrito é um
servidor Linux sem interface gráfica, então o ícone em si nunca pôde ser
exibido nem clicado de verdade aqui. Toda a LÓGICA (start/stop de
processo, limite de reinício, checagem de saúde) foi testada isoladamente
com mocks — só a parte visual/clique do ícone em si não pôde ser testada.
Teste no seu PC antes de confiar 100%.

Uso:
    pythonw.exe tray_app.py     (pythonw = sem console, é o que o
                                 start_tray.bat já faz automaticamente)
"""

import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import pystray
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import health_check

PROJECT_DIR = Path(__file__).parent.parent  # tray_app.py está em src/, a raiz do projeto é um nível acima
SRC_DIR = Path(__file__).parent  # onde os outros módulos (app.py, wake_word_listener.py) moram
IS_WINDOWS = sys.platform == "win32"
CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0

_venv_python = PROJECT_DIR / "venv" / "Scripts" / "python.exe"
PYTHON = _venv_python if _venv_python.exists() else Path(sys.executable)

APP_URL = "http://localhost:8000/app"

# Reinício automático (autocura) — com limite, pra nunca entrar num loop
# infinito de crash se algo estiver fundamentalmente quebrado (ex: falta
# uma dependência). Depois de esgotar as tentativas numa janela de tempo,
# para de tentar sozinho e avisa — melhor um aviso claro do que ficar
# reiniciando pra sempre sem nunca dar certo.
WATCHDOG_INTERVAL_SECONDS = 15
MAX_RESTART_ATTEMPTS = 5
RESTART_WINDOW_SECONDS = 300  # 5 minutos

server_process: subprocess.Popen | None = None
wake_word_process: subprocess.Popen | None = None
wake_word_enabled = True  # começa ligado por padrão, igual antes (as duas coisas subiam juntas)
_watchdog_stop = threading.Event()
_restart_timestamps: dict[str, list[float]] = {"server": [], "wake_word": []}


def _is_alive(proc: subprocess.Popen | None) -> bool:
    return proc is not None and proc.poll() is None


def _should_attempt_restart(nome: str) -> bool:
    """Limita reinícios numa janela de tempo — evita loop infinito de crash."""
    agora = time.time()
    _restart_timestamps[nome] = [t for t in _restart_timestamps[nome] if agora - t < RESTART_WINDOW_SECONDS]
    return len(_restart_timestamps[nome]) < MAX_RESTART_ATTEMPTS


def _record_restart_attempt(nome: str) -> None:
    _restart_timestamps[nome].append(time.time())


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
    _watchdog_stop.set()
    stop_server()
    stop_wake_word()
    icon.stop()


def _wake_word_checked(item: pystray.MenuItem) -> bool:
    return wake_word_enabled


def _watchdog_loop(icon: pystray.Icon) -> None:
    """
    Roda em segundo plano, olhando de tempos em tempos se o servidor e a
    escuta de voz continuam vivos — se algum caiu sozinho (crash), reinicia
    automaticamente. Só para de tentar depois de esgotar o limite numa
    janela de 5 minutos, e nesse caso avisa em vez de ficar tentando pra
    sempre sem sucesso.
    """
    while not _watchdog_stop.wait(WATCHDOG_INTERVAL_SECONDS):
        if not _is_alive(server_process):
            if _should_attempt_restart("server"):
                _record_restart_attempt("server")
                start_server()
                icon.notify("O servidor caiu sozinho — reiniciei automaticamente.", "J.A.R.V.I.S.")
            else:
                icon.notify("O servidor está caindo repetidamente — parei de tentar reiniciar sozinho. Confira o log.", "J.A.R.V.I.S.")

        if wake_word_enabled and not _is_alive(wake_word_process):
            if _should_attempt_restart("wake_word"):
                _record_restart_attempt("wake_word")
                start_wake_word()
                icon.notify("A escuta de voz caiu sozinha — reiniciei automaticamente.", "J.A.R.V.I.S.")
            else:
                icon.notify("A escuta de voz está caindo repetidamente — parei de tentar reiniciar sozinho. Confira o log.", "J.A.R.V.I.S.")


def _run_health_check_async(icon: pystray.Icon) -> None:
    """Roda a checagem de saúde numa thread separada (evita travar o ícone esperando rede) e notifica o resultado."""
    def _worker():
        resultado = health_check.run_all_checks()
        if resultado["tudo_ok"]:
            icon.notify("Tudo certo — Ollama, modelo e microfone prontos.", "J.A.R.V.I.S.")
        else:
            problemas = [nome for nome, c in resultado["checks"].items() if not c["ok"]]
            icon.notify(f"Encontrei um problema em: {', '.join(problemas)}. Veja o log pra detalhes.", "J.A.R.V.I.S.")
    threading.Thread(target=_worker, daemon=True).start()


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

    _run_health_check_async(icon)
    threading.Thread(target=_watchdog_loop, args=(icon,), daemon=True).start()

    icon.run()


if __name__ == "__main__":
    main()
