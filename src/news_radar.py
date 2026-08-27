"""
Radar de Notícias — manchetes por assunto via RSS do Google News. Grátis,
sem chave de API, sem limite prático. Usa `feedparser` (biblioteca
testada) em vez de parsear XML na mão.
"""

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urljoin

import feedparser
import requests

NEWS_TOPICS_PATH = None  # definido abaixo, evita import circular na declaração
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JARVIS-IA/1.0)"}


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


def fetch_headlines_from_source(nome: str, feed_url: str, quantidade: int = 5) -> dict:
    """Busca manchetes direto de uma fonte RSS específica (não busca por palavra-chave)."""
    try:
        feed = feedparser.parse(feed_url)
        if feed.bozo and not feed.entries:
            return {"assunto": nome, "erro": "Não foi possível buscar essa fonte agora.", "manchetes": []}
        manchetes = []
        for entry in feed.entries[:quantidade]:
            manchetes.append({
                "titulo": _clean_title(entry.get("title", "")),
                "fonte": nome,
                "link": entry.get("link", ""),
                "tempo_relativo": _relative_time(entry.get("published_parsed")),
            })
        return {"assunto": nome, "manchetes": manchetes}
    except Exception as e:
        return {"assunto": nome, "erro": str(e), "manchetes": []}


def get_all_headlines(quantidade: int = 5, forcar_atualizacao: bool = False, intervalo_minutos: int = 30) -> list[dict]:
    """Busca manchetes de todos os ASSUNTOS (busca por palavra-chave) E FONTES (RSS direto) configurados, respeitando o cache."""
    import database as db

    topics = load_topics()
    sources = load_sources()
    if not topics and not sources:
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

    for fonte in sources:
        cache_key = f"fonte:{fonte['nome']}"  # prefixo evita colisão com um assunto de mesmo nome
        cached = None if forcar_atualizacao else db.get_news_cache(cache_key)
        if cached:
            fetched_at = datetime.fromisoformat(cached["fetched_at"])
            idade_minutos = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 60
            if idade_minutos < intervalo_minutos:
                results.append({"assunto": fonte["nome"], "manchetes": cached["headlines"], "do_cache": True})
                continue

        fresh = fetch_headlines_from_source(fonte["nome"], fonte["feed_url"], quantidade)
        if "erro" not in fresh:
            db.save_news_cache(cache_key, fresh["manchetes"])
        fresh["do_cache"] = False
        results.append(fresh)

    return results


# ── Descoberta de fontes — sugere candidatos, mas VALIDA cada um de ─────
# verdade antes de considerar confiável (nunca confia só no que o modelo
# "acha" que existe — isso é exatamente o tipo de coisa que alucina).
def _find_feed_in_html(base_url: str) -> str | None:
    """Procura a tag <link rel="alternate" type="application/rss+xml"> na página inicial."""
    try:
        resp = requests.get(base_url, timeout=8, headers=_HEADERS)
        match = re.search(
            r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]+href=["\']([^"\']+)["\']',
            resp.text, re.IGNORECASE,
        )
        if match:
            feed_url = match.group(1)
            if not feed_url.startswith("http"):
                feed_url = urljoin(base_url, feed_url)
            return feed_url
    except Exception:
        pass
    return None


def _try_common_feed_paths(base_url: str) -> str | None:
    """Tenta os caminhos mais comuns de RSS, um por um, até achar um que responda de verdade."""
    for path in ["/feed", "/feed/", "/rss", "/rss.xml", "/feed.xml", "/atom.xml", "/index.xml"]:
        url = base_url.rstrip("/") + path
        try:
            resp = requests.get(url, timeout=5, headers=_HEADERS)
            if resp.status_code == 200 and ("<rss" in resp.text[:600] or "<feed" in resp.text[:600]):
                return url
        except Exception:
            continue
    return None


def discover_feed_for_site(site: str) -> dict:
    """
    Valida UM site de verdade: tenta achar um RSS real (primeiro pela tag
    HTML oficial, depois pelos caminhos comuns), e confirma que o feed
    encontrado realmente tem conteúdo parseável — não só que a URL responde.
    """
    url = site if site.startswith("http") else f"https://{site}"
    feed_url = _find_feed_in_html(url) or _try_common_feed_paths(url)

    if not feed_url:
        return {"site": site, "feed_url": None, "valido": False, "motivo": "Nenhum feed RSS encontrado."}

    try:
        parsed = feedparser.parse(feed_url)
        if not parsed.entries:
            return {"site": site, "feed_url": feed_url, "valido": False, "motivo": "Feed encontrado, mas sem itens."}
        return {
            "site": site, "feed_url": feed_url, "valido": True,
            "exemplo_titulo": _clean_title(parsed.entries[0].get("title", "")),
        }
    except Exception as e:
        return {"site": site, "feed_url": feed_url, "valido": False, "motivo": str(e)}


def suggest_sources_for_niche(nicho: str) -> list[str]:
    """
    Pede candidatos ao modelo local — são só SUGESTÕES. Cada um é validado
    de verdade depois (discover_feed_for_site), nunca aceito só por o
    modelo ter dito que existe.
    """
    import json as json_module

    import llm_client

    system = (
        "Liste de 6 a 10 sites ou blogs REAIS E CONHECIDOS, especializados no nicho indicado. "
        'Responda APENAS um JSON: ["dominio1.com", "dominio2.com", ...]. Só domínios, sem '
        '"https://" nem caminho. Se não tiver certeza de um site existir de verdade, não inclua.'
    )
    try:
        result = llm_client.chat(messages=[{"role": "user", "content": f"Nicho: {nicho}"}], tools=[], system=system)
        match = re.search(r"\[[\s\S]*\]", result["text"])
        if not match:
            return []
        candidatos = json_module.loads(match.group(0))
        return [c for c in candidatos if isinstance(c, str)]
    except Exception:
        return []


def discover_and_validate_sources(nicho: str) -> list[dict]:
    """Fluxo completo: sugere candidatos e valida CADA UM com uma checagem HTTP real."""
    candidatos = suggest_sources_for_niche(nicho)
    return [discover_feed_for_site(site) for site in candidatos]


def add_source(nome: str, feed_url: str) -> None:
    """Adiciona uma fonte RSS validada (site específico), diferente de um 'assunto' de busca."""
    fontes = load_sources()
    fontes = [f for f in fontes if f["nome"] != nome]
    fontes.append({"nome": nome, "feed_url": feed_url})
    save_sources(fontes)


def load_sources() -> list[dict]:
    from pathlib import Path
    path = Path(__file__).parent.parent / "news_sources.json"
    if not path.exists():
        return []
    import json as json_module
    with open(path, encoding="utf-8") as f:
        return json_module.load(f)


def save_sources(fontes: list[dict]) -> None:
    from pathlib import Path
    import json as json_module
    path = Path(__file__).parent.parent / "news_sources.json"
    with open(path, "w", encoding="utf-8") as f:
        json_module.dump(fontes, f, ensure_ascii=False, indent=2)


def remove_source(nome: str) -> bool:
    fontes = load_sources()
    filtered = [f for f in fontes if f["nome"] != nome]
    if len(filtered) == len(fontes):
        return False
    save_sources(filtered)
    return True


# ── Horário fixo pra narração automática (4ª melhoria pedida) ────────────
def _narration_config_path():
    from pathlib import Path
    return Path(__file__).parent.parent / "news_narration_config.json"


def get_narration_hour() -> int | None:
    path = _narration_config_path()
    if not path.exists():
        return None
    import json as json_module
    with open(path, encoding="utf-8") as f:
        return json_module.load(f).get("hora")


def set_narration_hour(hora: int) -> None:
    if not (0 <= hora <= 23):
        raise ValueError("Hora precisa estar entre 0 e 23.")
    import json as json_module
    with open(_narration_config_path(), "w", encoding="utf-8") as f:
        json_module.dump({"hora": hora}, f)


# ── Resumo profundo de um artigo específico (manchete + 5 bullets + "por que importa") ──
def _extract_article_text(link: str, max_chars: int = 6000) -> str:
    """
    Usa trafilatura (biblioteca especializada em extrair SÓ o conteúdo
    real do artigo) em vez de regex simples — regex deixa passar lixo
    como sidebar de anúncio, "leia também", newsletter embutida, etc,
    que não são parte do artigo de verdade.
    """
    import trafilatura

    downloaded = trafilatura.fetch_url(link)
    if not downloaded:
        raise ValueError("Não consegui baixar o conteúdo da página.")
    texto = trafilatura.extract(downloaded)
    if not texto:
        raise ValueError("Trafilatura não conseguiu identificar o conteúdo principal do artigo.")
    return texto[:max_chars]


def summarize_article(link: str) -> dict:
    """Manchete + 5 bullets + 'por que importa', via modelo local, a partir do artigo de verdade. Cacheado por link — nunca resume o mesmo artigo duas vezes."""
    import database as db
    import llm_client

    cached = db.get_article_summary(link)
    if cached:
        return cached

    try:
        texto = _extract_article_text(link)
    except Exception as e:
        return {"erro": f"Não consegui acessar o artigo: {e}"}

    if len(texto) < 200:
        return {"erro": "Conteúdo do artigo muito curto ou não extraído corretamente."}

    system = (
        "Resuma a notícia abaixo em português. Responda APENAS um JSON: "
        '{"manchete": "...", "bullets": ["...", "...", "...", "...", "..."], "por_que_importa": "..."}. '
        "Exatamente 5 bullets, cada um uma frase curta. Use só informação que está no texto."
    )
    try:
        result = llm_client.chat(messages=[{"role": "user", "content": texto}], tools=[], system=system)
        match = re.search(r"\{[\s\S]*\}", result["text"])
        if not match:
            return {"erro": "Modelo não devolveu um resumo em formato válido."}
        import json as json_module
        resumo = json_module.loads(match.group(0))
        db.save_article_summary(link, resumo)
        return resumo
    except Exception as e:
        return {"erro": f"Falha ao resumir: {e}"}


# ── Narração natural (não é só ler a lista, é um texto falado coeso) ─────
def narrate_news(assunto: str | None = None) -> str:
    """Compõe um parágrafo falado natural a partir das manchetes atuais — usável a qualquer hora, não só no Morning Digest."""
    import llm_client

    if assunto:
        dados = fetch_headlines(assunto, quantidade=5)
        manchetes_por_assunto = {assunto: dados.get("manchetes", [])}
    else:
        todos = get_all_headlines()
        manchetes_por_assunto = {n["assunto"]: n.get("manchetes", []) for n in todos if "erro" not in n}

    if not any(manchetes_por_assunto.values()):
        return "Não encontrei manchetes pra narrar agora."

    resumo_compacto = {
        assunto: [h["titulo"] for h in manchetes[:4]] for assunto, manchetes in manchetes_por_assunto.items()
    }

    system = (
        "Você é o J.A.R.V.I.S., narrando as notícias em voz alta de forma natural e fluida "
        "(não uma lista seca de títulos). Use só as manchetes fornecidas, não invente detalhes "
        "que não estão nelas."
    )
    try:
        import json as json_module
        result = llm_client.chat(
            messages=[{"role": "user", "content": json_module.dumps(resumo_compacto, ensure_ascii=False)}],
            tools=[], system=system,
        )
        return result["text"].strip()
    except Exception:
        # Fallback sem IA — nunca fica muda
        partes = []
        for assunto, titulos in resumo_compacto.items():
            if titulos:
                partes.append(f"Em {assunto}: " + "; ".join(titulos[:2]) + ".")
        return " ".join(partes) if partes else "Não encontrei manchetes pra narrar agora."
