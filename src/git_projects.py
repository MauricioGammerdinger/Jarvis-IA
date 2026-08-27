"""
Status do git dos seus projetos, pra aparecer no Painel de Agentes.
Não é um "agente de fundo" no sentido de rodar sozinho — é uma checagem
periódica do estado real do repositório (commits, mudanças pendentes,
sincronia com o GitHub), tratada como um "agente" a mais no painel.
"""

import json
import subprocess
from pathlib import Path

CODE_PROJECTS_PATH = Path(__file__).parent.parent / "code_projects.json"


def load_code_projects() -> list[dict]:
    if not CODE_PROJECTS_PATH.exists():
        return []
    with open(CODE_PROJECTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_code_projects(projects: list[dict]) -> None:
    with open(CODE_PROJECTS_PATH, "w", encoding="utf-8") as f:
        json.dump(projects, f, ensure_ascii=False, indent=2)


def add_code_project(nome: str, caminho: str) -> None:
    projects = load_code_projects()
    projects = [p for p in projects if p["nome"] != nome]
    projects.append({"nome": nome, "caminho": caminho})
    save_code_projects(projects)


def remove_code_project(nome: str) -> bool:
    projects = load_code_projects()
    filtered = [p for p in projects if p["nome"] != nome]
    if len(filtered) == len(projects):
        return False
    save_code_projects(filtered)
    return True


def _run_git(caminho: str, args: list[str], timeout: int = 8) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git"] + args, cwd=caminho, capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            return False, result.stderr.strip() or "Comando git falhou."
        return True, result.stdout.strip()
    except FileNotFoundError:
        return False, "Git não está instalado ou não foi encontrado."
    except subprocess.TimeoutExpired:
        return False, "Comando git demorou demais (timeout)."
    except Exception as e:
        return False, str(e)


def get_git_status(caminho: str) -> dict:
    path = Path(caminho)
    if not path.exists():
        return {"erro": f"Pasta não encontrada: {caminho}"}

    ok, _ = _run_git(caminho, ["rev-parse", "--is-inside-work-tree"])
    if not ok:
        return {"erro": f"'{caminho}' não é um repositório git."}

    ok, status_output = _run_git(caminho, ["status", "--porcelain"])
    if not ok:
        return {"erro": status_output}
    mudancas_pendentes = len([l for l in status_output.splitlines() if l.strip()])

    ok, last_commit = _run_git(caminho, ["log", "-1", "--format=%h|%s|%cr|%cI"])
    commit_hash, commit_msg, commit_relative, commit_iso = (
        last_commit.split("|", 3) if ok and last_commit else (None, None, None, None)
    )

    ok, branch = _run_git(caminho, ["rev-parse", "--abbrev-ref", "HEAD"])
    branch = branch if ok else "?"

    ahead, behind = 0, 0
    ok, counts = _run_git(caminho, ["rev-list", "--left-right", "--count", "HEAD...@{u}"])
    if ok and counts:
        parts = counts.split()
        if len(parts) == 2:
            ahead, behind = int(parts[0]), int(parts[1])

    return {
        "branch": branch,
        "mudancas_pendentes": mudancas_pendentes,
        "commit_hash": commit_hash,
        "commit_msg": commit_msg,
        "commit_relative": commit_relative,
        "commit_iso": commit_iso,
        "ahead": ahead,
        "behind": behind,
    }
