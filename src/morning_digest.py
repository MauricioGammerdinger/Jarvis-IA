"""
Morning Digest — briefing falado da manhã, juntando agenda + e-mails que
pedem ação + notícias + previsão do tempo + uma meta do Second Brain,
numa ÚNICA chamada ao modelo local (compacta os dados ANTES de chamar).

Tem fallback 100% offline (template local, sem IA) — o JARVIS nunca fica
mudo de manhã, mesmo sem Ollama disponível.
"""

import json
from datetime import date, datetime
from pathlib import Path

import requests

LAST_DIGEST_PATH = Path(__file__).parent.parent / "last_digest.json"
WEATHER_CITY_CACHE_PATH = Path(__file__).parent.parent / "weather_city_cache.json"


def _load_last_digest_date() -> str | None:
    if not LAST_DIGEST_PATH.exists():
        return None
    with open(LAST_DIGEST_PATH, encoding="utf-8") as f:
        return json.load(f).get("data")


def _save_last_digest_date() -> None:
    with open(LAST_DIGEST_PATH, "w", encoding="utf-8") as f:
        json.dump({"data": date.today().isoformat()}, f)


def already_ran_today() -> bool:
    return _load_last_digest_date() == date.today().isoformat()


def _geocode_city(cidade: str) -> tuple[float, float] | None:
    """Geocodifica a cidade uma única vez e guarda em cache (Open-Meteo, grátis, sem chave)."""
    cache = {}
    if WEATHER_CITY_CACHE_PATH.exists():
        with open(WEATHER_CITY_CACHE_PATH, encoding="utf-8") as f:
            cache = json.load(f)
    if cidade in cache:
        return tuple(cache[cidade])

    try:
        resp = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": cidade, "count": 1, "language": "pt"},
            timeout=8,
        )
        resp.raise_for_status()
        results = resp.json().get("results")
        if not results:
            return None
        lat, lon = results[0]["latitude"], results[0]["longitude"]
        cache[cidade] = [lat, lon]
        with open(WEATHER_CITY_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        return lat, lon
    except Exception:
        return None


_WEATHER_CODES = {
    0: "céu limpo", 1: "poucas nuvens", 2: "parcialmente nublado", 3: "nublado",
    45: "neblina", 48: "neblina com geada", 51: "garoa fraca", 53: "garoa", 55: "garoa forte",
    61: "chuva fraca", 63: "chuva", 65: "chuva forte", 71: "neve fraca", 73: "neve", 75: "neve forte",
    80: "pancadas de chuva fracas", 81: "pancadas de chuva", 82: "pancadas de chuva fortes",
    95: "trovoada", 96: "trovoada com granizo",
}


def get_weather(cidade: str) -> str | None:
    coords = _geocode_city(cidade)
    if not coords:
        return None
    lat, lon = coords
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,weathercode",
                "timezone": "America/Sao_Paulo",
            },
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()["daily"]
        tmax, tmin = data["temperature_2m_max"][0], data["temperature_2m_min"][0]
        code = data["weathercode"][0]
        descricao = _WEATHER_CODES.get(code, "tempo variável")
        return f"{descricao}, entre {tmin:.0f}°C e {tmax:.0f}°C"
    except Exception:
        return None


def _build_offline_digest(context: dict) -> str:
    """Fallback sem IA — template local, sempre funciona."""
    partes = [f"Bom dia! Hoje é {context['dia_semana']}, {context['data_extenso']}."]
    if context.get("clima"):
        partes.append(f"O tempo hoje: {context['clima']}.")
    if context["eventos_hoje"]:
        partes.append("Sua agenda: " + "; ".join(context["eventos_hoje"]) + ".")
    else:
        partes.append("Você não tem nenhum evento marcado pra hoje.")
    if context["emails_acao_count"] > 0:
        partes.append(f"Você tem {context['emails_acao_count']} e-mail(s) pedindo ação.")
    else:
        partes.append("Nenhum e-mail pedindo ação no momento.")
    for assunto, titulos in context["manchetes"].items():
        if titulos:
            partes.append(f"Em {assunto}: {titulos[0]}.")
    return " ".join(partes)


def _gather_context(tamanho: str = "medio") -> dict:
    """Reúne tudo LOCALMENTE, sem gastar nenhum token — compacta antes de chamar o modelo."""
    import calendar_hub
    import email_hub
    import news_radar

    hoje = datetime.now()
    dias_semana = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]

    eventos = calendar_hub.get_today_events()
    eventos_validos = [e for e in eventos if "erro" not in e]
    eventos_str = [f"{e['inicio_display']} {e['titulo']}" for e in eventos_validos[:15]]

    emails = email_hub.get_triaged_emails()
    emails_acao = emails["acao"]

    news = news_radar.get_all_headlines(quantidade=3)
    manchetes = {n["assunto"]: [h["titulo"] for h in n.get("manchetes", [])[:3]] for n in news}

    goals = []
    try:
        import database as db
        memories = db.list_memories()
        goals = [m["content"] for m in memories if m["category"] == "metas"][:2]
    except Exception:
        pass

    return {
        "dia_semana": dias_semana[hoje.weekday()],
        "data_extenso": f"{hoje.day} de {meses[hoje.month - 1]} de {hoje.year}",
        "eventos_hoje": eventos_str,
        "emails_acao_count": len(emails_acao),
        "emails_acao_resumos": [e["resumo"] for e in emails_acao[:5]],
        "manchetes": manchetes,
        "metas": goals,
        "clima": None,
    }


def generate_digest(cidade_clima: str | None = None, tamanho: str = "medio") -> dict:
    """
    Monta o digest. Tenta gerar com o modelo local (natural, na
    personalidade do JARVIS); se falhar, usa o template offline.
    """
    context = _gather_context(tamanho)
    if cidade_clima:
        context["clima"] = get_weather(cidade_clima)

    max_tokens = 500 if tamanho == "curto" else 800

    prompt_compacto = {
        "dia": f"{context['dia_semana']}, {context['data_extenso']}",
        "clima": context["clima"],
        "agenda_hoje": context["eventos_hoje"],
        "emails_pedindo_acao": context["emails_acao_resumos"],
        "total_emails_acao": context["emails_acao_count"],
        "manchetes": context["manchetes"],
        "metas": context["metas"],
    }

    try:
        import llm_client

        system = (
            "Você é o J.A.R.V.I.S., dando um briefing matinal falado, natural e "
            "caloroso (não uma lista seca). Use os dados abaixo pra montar um "
            "texto corrido, terminando com uma frase de foco pro dia, conectada "
            "às metas se houver. Não invente informação que não está nos dados."
        )
        result = llm_client.chat(
            messages=[{"role": "user", "content": json.dumps(prompt_compacto, ensure_ascii=False)}],
            tools=[],
            system=system,
        )
        texto = result["text"].strip()
        if not texto:
            raise ValueError("Resposta vazia do modelo")
    except Exception:
        texto = _build_offline_digest(context)

    _save_last_digest_date()
    return {"texto": texto, "contexto": context}
