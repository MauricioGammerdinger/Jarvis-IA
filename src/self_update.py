"""
Auto-atualização do próprio JARVIS — puxa do GitHub, mas em 3 passos bem
separados, nunca escondidos:

1. CHECAR — automático, só leitura (git fetch + compara). Não muda nada.
2. APLICAR — precisa de aprovação explícita (`aplicar_atualizacao_jarvis`
   como tool, ou o endpoint). Faz o `git pull` de verdade.
3. REINICIAR — o usuário mesmo clica "Reiniciar servidor" no ícone de
   bandeja (já existe, já testado) — o processo do servidor NÃO consegue
   recarregar o próprio código sozinho, então nunca finge que consegue.
"""

import os
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent  # raiz do projeto (onde fica o .git)


def _run_git(args: list[str], timeout: int = 15) -> tuple[bool, str]:
    import subprocess

    try:
        result = subprocess.run(
            ["git"] + args, cwd=str(PROJECT_DIR), capture_output=True, text=True, timeout=timeout
        )
        return result.returncode == 0, (result.stdout or result.stderr).strip()
    except Exception as e:
        return False, str(e)


def check_for_updates() -> dict:
    """Só leitura — nunca muda nada no disco. Devolve se tem atualização disponível, e um resumo dos commits novos."""
    ok, _ = _run_git(["fetch"])
    if not ok:
        return {"ok": False, "motivo": "Não consegui buscar atualizações (sem internet? repositório não configurado?)."}

    ok, branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    if not ok:
        return {"ok": False, "motivo": "Não consegui identificar a branch atual."}

    ok, contagem = _run_git(["rev-list", "--count", f"HEAD..origin/{branch}"])
    if not ok:
        return {"ok": False, "motivo": "Não consegui comparar com o repositório remoto."}

    total_novos = int(contagem) if contagem.isdigit() else 0
    if total_novos == 0:
        return {"ok": True, "tem_atualizacao": False, "total_commits_novos": 0}

    ok, log = _run_git(["log", f"HEAD..origin/{branch}", "--oneline", "-10"])
    mensagens = log.splitlines() if ok else []

    return {
        "ok": True,
        "tem_atualizacao": True,
        "total_commits_novos": total_novos,
        "commits": mensagens,
    }


def apply_update() -> dict:
    """Aplica de verdade (git pull) — só chame depois de aprovação explícita do usuário."""
    verificacao = check_for_updates()
    if not verificacao["ok"]:
        return verificacao
    if not verificacao["tem_atualizacao"]:
        return {"ok": True, "aplicado": False, "motivo": "Já está tudo atualizado."}

    ok, saida = _run_git(["pull"])
    if not ok:
        return {"ok": False, "motivo": f"Falha ao aplicar a atualização: {saida}"}

    return {
        "ok": True,
        "aplicado": True,
        "commits_aplicados": verificacao["total_commits_novos"],
        "mensagem": "Atualizado! Precisa reiniciar o servidor (ícone da bandeja → 'Reiniciar servidor') pra rodar o código novo de verdade.",
    }
