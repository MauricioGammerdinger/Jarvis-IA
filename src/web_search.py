"""
Pesquisa na web — o JARVIS é 100% local (sem internet pra responder com
o que já sabe), mas às vezes a pergunta precisa de informação atual, que
o modelo não tem. Isso usa o DuckDuckGo (via biblioteca `ddgs`), que não
exige chave de API nem cobra por uso — mantém a filosofia do projeto
inteiro (sem custo, sem conta em serviço de terceiro pra manter).
"""


def search_web(query: str, max_results: int = 5) -> list[dict]:
    """Busca na web e devolve título, link e um trecho de cada resultado. Nunca lança exceção — devolve lista vazia em caso de falha."""
    try:
        from ddgs import DDGS

        resultados = DDGS().text(query, max_results=max_results)
        return [
            {"titulo": r.get("title", ""), "link": r.get("href", ""), "trecho": r.get("body", "")}
            for r in resultados
        ]
    except Exception:
        return []


def format_search_results(query: str, resultados: list[dict]) -> str:
    if not resultados:
        return f"Não encontrei resultados pra '{query}' (ou a busca falhou — confira sua internet)."
    linhas = [f"Resultados pra '{query}':"]
    for r in resultados:
        linhas.append(f"- {r['titulo']}: {r['trecho'][:200]} ({r['link']})")
    return "\n".join(linhas)
