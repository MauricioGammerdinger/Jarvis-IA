"""
Radar de Notícias — manchetes por assunto via RSS do Google News. Grátis,
sem chave de API, sem limite prático. Usa `feedparser` (biblioteca
testada) em vez de parsear XML na mão.
"""

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import feedparser

NEWS_TOPICS_PATH = None  # definido abaixo, evita import circular na declaração


def _topics_path():
    from pathlib import Path
    return Path(__file__).parent.parent / "news_topics.json"


def load_topics() -> list[str]:
    path = _topics_path()
    if not path.exists():
        return []
    import json
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_topics(topics: list[str]) -> None:
    import json
    with open(_topics_path(), "w", encoding="utf-8") as f:
        json.dump(topics, f, ensure_ascii=False, indent=2)


def add_topic(assunto: str) -> None:
    topics = load_topics()
    if assunto.strip().lower() not in [t.lower() for t in topics]:
        topics.append(assunto.strip())
        save_topics(topics)


def remove_topic(assunto: str) -> bool:
    topics = load_topics()
    filtered = [t for t in topics if t.lower() != assunto.strip().lower()]
    if len(filtered) == len(topics):
        return False
    save_topics(filtered)
    return True


def _clean_title(title: str) -> str:
    """Remove o sufixo ' - Fonte' que o Google News sempre adiciona ao título."""
    return re.sub(r"\s+-\s+[^-]+$", "", title).strip()


def _relative_time(published_parsed) -> str:
    if not published_parsed:
        return ""
    published = datetime(*published_parsed[:6], tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - published
    hours = delta.total_seconds() / 3600
    if hours < 1:
        return f"há {int(delta.total_seconds() / 60)} min"
    if hours < 24:
        return f"há {int(hours)} h"
    return f"há {int(hours / 24)} dias"


def fetch_headlines(assunto: str, quantidade: int = 5, idioma: str = "pt-BR", regiao: str = "BR") -> dict:
    """Busca as manchetes mais recentes de um assunto. Nunca lança exceção — devolve erro no dict."""
    url = f"https://news.google.com/rss/search?q={quote(assunto)}&hl={idioma}&gl={regiao}&ceid={regiao}:{idioma.split('-')[0]}"
    try:
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            return {"assunto": assunto, "erro": "Não foi possível buscar notícias desse assunto agora.", "manchetes": []}

        manchetes = []
        for entry in feed.entries[:quantidade]:
            manchetes.append({
                "titulo": _clean_title(entry.get("title", "")),
                "fonte": entry.get("source", {}).get("title", "") if hasattr(entry, "source") else "",
                "link": entry.get("link", ""),
                "tempo_relativo": _relative_time(entry.get("published_parsed")),
            })
        return {"assunto": assunto, "manchetes": manchetes}
    except Exception as e:
        return {"assunto": assunto, "erro": str(e), "manchetes": []}


def get_all_headlines(quantidade: int = 5, forcar_atualizacao: bool = False, intervalo_minutos: int = 30) -> list[dict]:
    """Busca manchetes de todos os assuntos configurados, respeitando o cache."""
    import database as db

    topics = load_topics()
    if not topics:
        return []

    results = []
    for assunto in topics:
        cached = None if forcar_atualizacao else db.get_news_cache(assunto)
        if cached:
            fetched_at = datetime.fromisoformat(cached["fetched_at"])
            idade_minutos = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 60
            if idade_minutos < intervalo_minutos:
                results.append({"assunto": assunto, "manchetes": cached["headlines"], "do_cache": True})
                continue

        fresh = fetch_headlines(assunto, quantidade)
        if "erro" not in fresh:
            db.save_news_cache(assunto, fresh["manchetes"])
        fresh["do_cache"] = False
        results.append(fresh)

    return results
