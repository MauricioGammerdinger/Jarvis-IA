"""
Checagem de saúde na inicialização — em vez de só dizer "pronto" e deixar
você descobrir na marra que o Ollama não está rodando (ou o microfone não
foi encontrado) só quando for usar de verdade, confere os 3 pontos mais
comuns de falha ANTES, e avisa com clareza o que está faltando.
"""

import os


def check_ollama() -> dict:
    """Confirma que o Ollama está de pé e respondendo, no endereço configurado."""
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    try:
        import httpx
        resp = httpx.get(base_url.replace("/v1", "") + "/api/tags", timeout=5)
        if resp.status_code == 200:
            return {"ok": True, "detalhe": "Ollama respondendo normalmente."}
        return {"ok": False, "detalhe": f"Ollama respondeu com status {resp.status_code} — algo está errado."}
    except Exception as e:
        return {"ok": False, "detalhe": f"Não consegui alcançar o Ollama em {base_url} — ele está rodando? ({e})"}


def check_model_available() -> dict:
    """Confirma que o modelo configurado (JARVIS_MODEL) já foi baixado no Ollama."""
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    modelo = os.environ.get("JARVIS_MODEL", "").strip()
    if not modelo:
        return {"ok": False, "detalhe": "JARVIS_MODEL não está definido no .env."}
    try:
        import httpx
        resp = httpx.get(base_url.replace("/v1", "") + "/api/tags", timeout=5)
        if resp.status_code != 200:
            return {"ok": False, "detalhe": "Não consegui checar — Ollama não respondeu direito."}
        modelos_instalados = [m["name"] for m in resp.json().get("models", [])]
        # Ollama às vezes guarda com ":latest" implícito — compara com e sem
        modelo_base = modelo.split(":")[0]
        encontrado = any(m == modelo or m.startswith(modelo_base + ":") for m in modelos_instalados)
        if encontrado:
            return {"ok": True, "detalhe": f"Modelo '{modelo}' encontrado."}
        return {
            "ok": False,
            "detalhe": f"Modelo '{modelo}' não está baixado ainda. Rode: ollama pull {modelo}",
        }
    except Exception as e:
        return {"ok": False, "detalhe": f"Não consegui checar o modelo: {e}"}


def check_microphone() -> dict:
    """Confirma que existe pelo menos um dispositivo de entrada de áudio disponível."""
    try:
        import sounddevice as sd
        dispositivos = sd.query_devices()
        entradas = [d for d in dispositivos if d.get("max_input_channels", 0) > 0]
        if entradas:
            return {"ok": True, "detalhe": f"{len(entradas)} microfone(s) encontrado(s)."}
        return {"ok": False, "detalhe": "Nenhum microfone encontrado — a escuta por voz não vai funcionar."}
    except Exception as e:
        return {"ok": False, "detalhe": f"Não consegui checar o microfone: {e}"}


def run_all_checks() -> dict:
    """Roda os 3 checks e devolve um resumo — nunca lança exceção, sempre devolve algo usável."""
    resultados = {
        "ollama": check_ollama(),
        "modelo": check_model_available(),
        "microfone": check_microphone(),
    }
    tudo_ok = all(r["ok"] for r in resultados.values())
    return {"tudo_ok": tudo_ok, "checks": resultados}


def format_summary(resultado: dict) -> str:
    """Formata o resultado de forma legível, pra print/log/notificação."""
    if resultado["tudo_ok"]:
        return "✅ Tudo certo — Ollama, modelo e microfone prontos."
    linhas = ["⚠️ Encontrei um ou mais problemas antes de começar:"]
    for nome, check in resultado["checks"].items():
        if not check["ok"]:
            linhas.append(f"  - {nome}: {check['detalhe']}")
    return "\n".join(linhas)
