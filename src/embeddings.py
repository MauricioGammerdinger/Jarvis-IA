"""
Busca semântica para a memória de longo prazo.

Antes, a busca era só por palavra-chave (SQLite FTS5) — "prefiro café" não
batia com a pergunta "que bebidas quentes eu gosto". Aqui trocamos por
embeddings: cada memória vira um vetor numérico que captura o SIGNIFICADO
do texto, e a busca compara vetores por similaridade de cosseno.

Usamos `fastembed` (ONNX, roda em CPU, sem precisar do PyTorch) em vez de
`sentence-transformers` — o mesmo resultado prático, mas um download bem
menor (~90MB vs ~1GB+) e mais leve pra rodar 24/7 no seu PC.

Na primeira chamada, baixa o modelo automaticamente (precisa de internet
nesse momento único); depois disso funciona 100% offline.
"""

import concurrent.futures
import json
import logging
import math
import os
import time

logger = logging.getLogger("jarvis")  # mesmo logger do app.py — vai pro mesmo arquivo de log

_embedding_model = None
_model_unavailable = False  # evita tentar baixar de novo a cada chamada, se já falhou uma vez
_download_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def _get_model():
    global _embedding_model, _model_unavailable
    if _model_unavailable:
        raise RuntimeError("Modelo de embeddings indisponível nesta execução (falhou antes; reinicie o servidor pra tentar de novo).")
    if _embedding_model is None:
        t0 = time.monotonic()
        timeout_s = float(os.environ.get("EMBEDDINGS_TIMEOUT_SECONDS", "10"))
        logger.info(f"[embeddings] Carregando modelo pela primeira vez (timeout de {timeout_s}s)...")

        # Roda numa thread separada com timeout DE VERDADE — o fastembed tem sua
        # própria lógica de retry com backoff (3s+9s+27s = ~39s) que ignora
        # parâmetros de timeout normais; isso aqui desiste na hora certa não
        # importa o que a biblioteca esteja fazendo por baixo dos panos.
        from fastembed import TextEmbedding

        future = _download_executor.submit(TextEmbedding, model_name=MODEL_NAME)
        try:
            _embedding_model = future.result(timeout=timeout_s)
            logger.info(f"[embeddings] Modelo carregado em {time.monotonic() - t0:.1f}s")
        except concurrent.futures.TimeoutError:
            _model_unavailable = True
            logger.warning(
                f"[embeddings] Timeout de {timeout_s}s ao carregar modelo (provável rede lenta/bloqueada "
                f"pro Hugging Face). A busca de memória vai usar só palavra-chave pelo resto desta execução."
            )
            raise RuntimeError(f"Timeout de {timeout_s}s ao carregar modelo de embeddings.")
        except Exception as e:
            _model_unavailable = True
            logger.warning(
                f"[embeddings] Falha ao carregar modelo depois de {time.monotonic() - t0:.1f}s: {e}. "
                f"A busca de memória vai usar só palavra-chave (sem entender sinônimos) pelo resto desta execução."
            )
            raise
    return _embedding_model


def embed_text(text: str) -> list[float]:
    """Converte um texto num vetor numérico (embedding)."""
    model = _get_model()
    vector = next(model.embed([text]))
    return vector.tolist()


def embedding_to_json(vector: list[float]) -> str:
    return json.dumps(vector)


def embedding_from_json(raw: str) -> list[float]:
    return json.loads(raw)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def rank_by_similarity(query_vector: list[float], candidates: list[dict], limit: int = 5) -> list[dict]:
    """
    Recebe uma lista de dicts com uma chave 'embedding' (JSON de vetor) e
    devolve os `limit` mais similares ao `query_vector`, ordenados por
    relevância, com o score de similaridade anexado.
    """
    scored = []
    for c in candidates:
        if not c.get("embedding"):
            continue
        vec = embedding_from_json(c["embedding"])
        score = cosine_similarity(query_vector, vec)
        scored.append((score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{**c, "similarity": round(score, 4)} for score, c in scored[:limit]]


def add_memory_with_embedding(content: str, category: str = "general") -> int:
    """
    Salva uma memória já calculando o embedding, se o modelo estiver disponível.
    Se o modelo falhar (ex: sem internet na primeira vez), salva sem embedding —
    a busca cai automaticamente pra palavra-chave (FTS) pra essa entrada.
    """
    import database as db

    try:
        vector = embed_text(content)
        return db.add_memory(content, category, embedding=embedding_to_json(vector))
    except Exception:
        return db.add_memory(content, category, embedding=None)


def add_engineering_memory_with_embedding(
    tipo: str, titulo: str, descricao: str, solucao: str | None = None, projeto: str | None = None
) -> int:
    """Mesmo padrão de `add_memory_with_embedding` — calcula embedding se possível, salva sem se o modelo falhar."""
    import database as db

    texto_pra_embedding = f"{titulo}. {descricao}. {solucao or ''}"
    try:
        vector = embed_text(texto_pra_embedding)
        return db.add_engineering_memory(tipo, titulo, descricao, solucao, projeto, embedding=vector)
    except Exception:
        return db.add_engineering_memory(tipo, titulo, descricao, solucao, projeto, embedding=None)


def smart_search(query: str, limit: int = 5) -> list[dict]:
    """
    Busca semântica com fallback automático:
    1. Tenta embeddings (entende significado, não só palavra exata).
    2. Se o modelo não estiver disponível, cai pra busca por palavra-chave (FTS5).
    """
    import database as db

    t0 = time.monotonic()
    try:
        query_vector = embed_text(query)
        candidates = db.all_memories_with_embeddings()
        if candidates:
            results = rank_by_similarity(query_vector, candidates, limit=limit)
            logger.debug(f"[embeddings] smart_search (via embeddings) levou {time.monotonic() - t0:.1f}s")
            return results
    except Exception as e:
        logger.debug(f"[embeddings] smart_search caiu pro fallback de palavra-chave depois de {time.monotonic() - t0:.1f}s: {e}")
    # Fallback: palavra-chave normal
    return db.search_memories(query, limit=limit)


# ── "Conectar fatos sozinho" — acha uma conexão relevante com o que já foi guardado ──
CONNECTION_SIMILARITY_THRESHOLD = float(os.environ.get("JARVIS_CONNECTION_THRESHOLD", "0.55"))


def find_relevant_connection(mensagem_usuario: str) -> dict | None:
    """
    Busca no Second Brain algo relacionado com a mensagem atual — pra o
    JARVIS conseguir puxar uma conexão sozinho ("isso tem a ver com
    aquela meta de dezembro"), sem o usuário pedir. Só devolve algo se a
    similaridade for forte o bastante (evita forçar conexão fraca/
    aleatória) — no fallback por palavra-chave (sem embeddings
    disponível), não tem esse score, então aceita o primeiro resultado
    encontrado (a busca por palavra-chave já filtra por relevância
    mínima sozinha, de outro jeito).

    ⚠️ O limiar (`JARVIS_CONNECTION_THRESHOLD`) não pôde ser calibrado
    com embeddings de verdade no ambiente onde isso foi escrito (rede
    bloqueada) — é um valor razoável por padrão, mas ajuste no .env se
    perceber conexões fracas demais (sobe o valor) ou nenhuma conexão
    aparecendo nunca (desce o valor).
    """
    if len(mensagem_usuario.strip()) < 15:
        return None  # mensagem curta demais, não vale a pena buscar (ex: "oi", "obrigado")

    resultados = smart_search(mensagem_usuario, limit=1)
    if not resultados:
        return None

    melhor = resultados[0]
    if "similarity" in melhor and melhor["similarity"] < CONNECTION_SIMILARITY_THRESHOLD:
        return None  # veio de embeddings, mas não é parecido o suficiente

    return melhor


# ── Memória de Engenharia — busca semântica com fallback, mesmo padrão do Second Brain ──
ENGINEERING_MEMORY_SIMILARITY_THRESHOLD = float(os.environ.get("JARVIS_ENGINEERING_MEMORY_THRESHOLD", "0.5"))


def smart_search_engineering_memory(query: str, limit: int = 3) -> list[dict]:
    """Busca semântica na Memória de Engenharia, com fallback pra palavra-chave — mesmo padrão de `smart_search`."""
    import database as db

    try:
        query_vector = embed_text(query)
        candidates = db.all_engineering_memories_with_embeddings()
        if candidates:
            return rank_by_similarity(query_vector, candidates, limit=limit)
    except Exception as e:
        logger.debug(f"[embeddings] smart_search_engineering_memory caiu pro fallback de palavra-chave: {e}")
    return db.search_engineering_memories_by_keyword(query, limit=limit)


def find_relevant_engineering_memory(mensagem_usuario: str) -> dict | None:
    """
    Busca na Memória de Engenharia algo relacionado com o problema atual
    — pro JARVIS conseguir lembrar sozinho de um bug/decisão parecida de
    outro projeto. Só devolve se a similaridade for forte o bastante (via
    embeddings) — no fallback por palavra-chave, aceita o primeiro
    resultado (a busca por palavra-chave já filtra relevância mínima
    sozinha, de outro jeito).
    """
    if len(mensagem_usuario.strip()) < 15:
        return None

    resultados = smart_search_engineering_memory(mensagem_usuario, limit=1)
    if not resultados:
        return None

    melhor = resultados[0]
    if "similarity" in melhor and melhor["similarity"] < ENGINEERING_MEMORY_SIMILARITY_THRESHOLD:
        return None

    return melhor
