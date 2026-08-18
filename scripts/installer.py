"""
Instalador do J.A.R.V.I.S. — este arquivo vira um .exe de verdade (com o
ícone do JARVIS embutido) usando PyInstaller. Veja o passo a passo de build
no README, seção "Gerando o instalador .exe".

Faz a mesma coisa que o setup.ps1: cria ambiente virtual, instala
dependências, cria o .env, cria o atalho na área de trabalho, e
opcionalmente registra o início automático com o Windows — só que
empacotado como .exe, pra abrir com duplo-clique igual instalador de
programa de verdade (Discord, Chrome, etc), com ícone próprio.

⚠️ NÃO TESTADO COMO .EXE DE VERDADE: este código foi escrito e revisado
com cuidado, mas o ambiente onde foi desenvolvido é Linux — não é possível
compilar nem rodar um .exe do Windows aqui. A compilação e o primeiro teste
real só acontecem no seu PC.
"""

import os
import subprocess
import sys
from pathlib import Path

# Quando compilado pelo PyInstaller (--onefile via build_installer.bat), o
# .exe é colocado na RAIZ do projeto (não em scripts/) — então sys.executable
# já aponta pro lugar certo. Quando rodado como script Python puro (sem
# compilar), este arquivo mora em scripts/, então a raiz do projeto fica
# um nível acima.
FROZEN = getattr(sys, "frozen", False)
PROJECT_DIR = Path(sys.executable).parent if FROZEN else Path(__file__).parent.parent


def _find_system_python() -> str:
    """
    Localiza um Python de verdade instalado no sistema (não o próprio .exe).
    Tenta o launcher oficial do Windows primeiro (mais confiável), depois
    cai para variações comuns de PATH.
    """
    candidates = ["py", "python", "python3"]
    for candidate in candidates:
        try:
            result = subprocess.run(
                [candidate, "--version"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return candidate
        except (FileNotFoundError, OSError):
            continue
    raise RuntimeError(
        "Python não foi encontrado no sistema. Instale o Python "
        "(python.org) e marque 'Add to PATH' durante a instalação, "
        "depois rode este instalador de novo."
    )


def _create_shortcut(shortcut_path: Path, target: Path, icon: Path, description: str) -> None:
    """Cria um atalho .lnk do Windows via win32com (mesma tecnologia que o setup.ps1 usava via PowerShell)."""
    import win32com.client

    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(str(shortcut_path))
    shortcut.TargetPath = str(target)
    shortcut.WorkingDirectory = str(PROJECT_DIR)
    shortcut.IconLocation = str(icon)
    shortcut.Description = description
    shortcut.save()


def main() -> None:
    print("=== Instalador do J.A.R.V.I.S. ===")
    print(f"Pasta do projeto: {PROJECT_DIR}\n")

    venv_dir = PROJECT_DIR / "venv"
    venv_python = venv_dir / "Scripts" / "python.exe"

    # 1. Criar ambiente virtual
    if not venv_dir.exists():
        print("[1/5] Criando ambiente virtual Python...")
        system_python = _find_system_python()
        subprocess.run([system_python, "-m", "venv", str(venv_dir)], check=True)
    else:
        print("[1/5] Ambiente virtual já existe, pulando.")

    # 2. Instalar dependências
    print("\n[2/5] Instalando dependências (pode demorar alguns minutos)...")
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "-r", str(PROJECT_DIR / "requirements.txt")],
        check=True,
    )

    # 3. Criar o .env se ainda não existir
    env_path = PROJECT_DIR / ".env"
    env_example_path = PROJECT_DIR / ".env.example"
    if not env_path.exists():
        print("\n[3/5] Criando .env a partir do modelo...")
        env_path.write_text(env_example_path.read_text(encoding="utf-8"), encoding="utf-8")
        print("      -> Abra o .env e preencha JARVIS_API_KEY antes de usar!")
    else:
        print("\n[3/5] .env já existe, mantendo suas configurações atuais.")

    # 4. Criar o atalho na área de trabalho
    print("\n[4/5] Criando atalho na área de trabalho...")
    try:
        import winreg  # só existe no Windows — usado aqui só pra confirmar a plataforma

        desktop = Path(os.path.expanduser("~")) / "Desktop"
        shortcut_path = desktop / "J.A.R.V.I.S..lnk"
        _create_shortcut(
            shortcut_path,
            target=PROJECT_DIR / "scripts" / "launch_jarvis.bat",
            icon=PROJECT_DIR / "assets" / "icon.ico",
            description="Abre o J.A.R.V.I.S.",
        )
        print(f"      -> Atalho criado em: {shortcut_path}")
    except ImportError:
        print("      -> Não é Windows, pulando criação de atalho.")
    except Exception as e:
        print(f"      -> Não consegui criar o atalho automaticamente ({e}).")
        print("         Crie manualmente um atalho pra launch_jarvis.bat, se quiser.")

    # 5. Perguntar sobre auto-start no boot
    print("\n[5/5] Auto-iniciar com o Windows?")
    resposta = input(
        "Quer que o JARVIS ligue sozinho quando o Windows iniciar (ícone na bandeja)? (s/n): "
    ).strip().lower()
    if resposta == "s":
        try:
            startup = (
                Path(os.path.expanduser("~"))
                / "AppData" / "Roaming" / "Microsoft" / "Windows"
                / "Start Menu" / "Programs" / "Startup"
            )
            shortcut_path = startup / "J.A.R.V.I.S..lnk"
            _create_shortcut(
                shortcut_path,
                target=PROJECT_DIR / "scripts" / "start_tray.bat",
                icon=PROJECT_DIR / "assets" / "icon.ico",
                description="Liga o J.A.R.V.I.S. (ícone na bandeja do sistema).",
            )
            print("      -> Adicionado à pasta de Inicialização do Windows.")
            print("      -> Confira em: Gerenciador de Tarefas > Aplicativos de inicialização")
        except Exception as e:
            print(f"      -> Não consegui configurar automaticamente ({e}).")
    else:
        print("      -> Pulado. Use o atalho da área de trabalho manualmente quando quiser.")

    print("\n=== Instalação concluída! ===")
    print("1. Abra o .env e confirme suas chaves (JARVIS_API_KEY, etc).")
    print("2. Instale o Ollama e rode: ollama pull qwen3:8b")
    print("3. Use o atalho 'J.A.R.V.I.S.' pra abrir o JARVIS.")
    input("\nPressione Enter pra fechar...")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERRO: {e}")
        input("\nPressione Enter pra fechar...")
        sys.exit(1)
