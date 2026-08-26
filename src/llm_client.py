"""
Cliente do modelo de IA local (Ollama).

O Ollama expõe uma API compatível com a da OpenAI em http://localhost:11434/v1
— então em vez de reinventar o formato de chamada, usamos o próprio pacote
`openai` apontado pro endereço local. O modelo nunca sai da sua máquina.

Pré-requisito: o Ollama precisa estar instalado e rodando (`ollama serve`,
geralmente já roda sozinho depois de instalado), com o modelo já baixado
(`ollama pull qwen3:8b` ou o que você escolher em MODEL_NAME abaixo).
"""

import json
import os
import re

from openai import OpenAI

client = OpenAI(
    base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
    api_key="ollama",
    timeout=float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "60")),  # sem isso, uma trava no Ollama prendia o JARVIS pra sempre
    max_retries=1,  # a biblioteca tenta de novo antes de desistir — sem limitar isso, o timeout real vira timeout×tentativas
)

# Modelos "raciocinadores" (Qwen3 e outros) por padrão "pensam em voz alta"
# antes de responder — isso deixa a resposta mais lenta e, se vazar pro
# texto final, poluído com um parágrafo de raciocínio interno que ninguém
# pediu pra ver. Desligamos isso explicitamente.
DISABLE_THINKING_EXTRA_BODY = {"think": False}

_THINK_BLOCK_RE = re.compile(r"<think>[\s\S]*?</think>\s*", re.IGNORECASE)


def _strip_thinking(text: str) -> str:
    """Remove qualquer bloco <think>...</think> que ainda vaze na resposta,
    mesmo com think:false pedido — proteção extra, caso o modelo ignore o parâmetro."""
    return _THINK_BLOCK_RE.sub("", text or "").strip()


def _get_model_name() -> str:
    """
    Lê JARVIS_MODEL do ambiente TODA VEZ que é chamada, em vez de guardar
    numa variável fixada na hora do import. Isso evita um bug real que já
    aconteceu: se este módulo for importado antes do .env ser carregado
    (load_dotenv()), uma leitura única na hora do import pegaria sempre o
    valor padrão, ignorando o que está no .env, para sempre, até reiniciar
    o processo inteiro com a ordem de import corrigida.
    """
    return os.environ.get("JARVIS_MODEL", "qwen3:8b")


def to_openai_tool_schema(tools: list[dict]) -> list[dict]:
    """
    Converte nosso formato interno de tool (name/description/input_schema)
    pro formato que a API OpenAI-compatible do Ollama espera.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]


def chat(messages: list[dict], tools: list[dict], system: str) -> dict:
    """
    Chamada simples (sem streaming). Retorna um dict normalizado:
    {"text": str, "tool_calls": [{"id", "name", "arguments"}] , "raw_message": dict}
    """
    full_messages = [{"role": "system", "content": system}] + messages
    response = client.chat.completions.create(
        model=_get_model_name(),
        messages=full_messages,
        tools=to_openai_tool_schema(tools) if tools else None,
        extra_body=DISABLE_THINKING_EXTRA_BODY,
    )
    message = response.choices[0].message
    tool_calls = []
    if message.tool_calls:
        for tc in message.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                args = {}
            tool_calls.append({"id": tc.id, "name": tc.function.name, "arguments": args})

    return {
        "text": _strip_thinking(message.content or ""),
        "tool_calls": tool_calls,
        "raw_message": message.model_dump(),
    }


def _partial_tag_suffix_len(buffer: str, tag: str) -> int:
    """
    Detecta se o FIM do buffer pode ser o INÍCIO de uma tag ainda incompleta
    (ex: o chunk terminou bem no meio de "<think>", só chegou "<thi").
    Sem isso, filtrar tag por tag entre pedaços de streaming quebraria a
    tag ao meio e deixaria ela vazar sem querer.
    """
    max_check = min(len(tag) - 1, len(buffer))
    for length in range(max_check, 0, -1):
        if buffer.endswith(tag[:length]):
            return length
    return 0


def chat_stream(messages: list[dict], tools: list[dict], system: str):
    """
    Gera pedaços de texto conforme chegam (streaming). Se o modelo decidir
    chamar uma ferramenta, o streaming não devolve texto nessa rodada — quem
    chama essa função deve, nesse caso, cair de volta pra `chat()` normal
    pra pegar o tool_call estruturado (streaming + tool call juntos é mais
    frágil em modelos locais, então simplificamos assim).

    Filtra qualquer bloco <think>...</think> (raciocínio interno de modelos
    como Qwen3) ANTES de repassar pro chamador — mesmo que a tag venha
    picada em pedaços diferentes entre um chunk e outro.
    """
    full_messages = [{"role": "system", "content": system}] + messages
    stream = client.chat.completions.create(
        model=_get_model_name(),
        messages=full_messages,
        tools=to_openai_tool_schema(tools) if tools else None,
        stream=True,
        extra_body=DISABLE_THINKING_EXTRA_BODY,
    )

    buffer = ""
    in_think = False

    for chunk in stream:
        delta = chunk.choices[0].delta
        if not delta.content:
            continue
        buffer += delta.content

        while True:
            if not in_think:
                idx = buffer.find("<think>")
                if idx == -1:
                    safe_len = len(buffer) - _partial_tag_suffix_len(buffer, "<think>")
                    if safe_len > 0:
                        yield buffer[:safe_len]
                        buffer = buffer[safe_len:]
                    break
                if idx > 0:
                    yield buffer[:idx]
                buffer = buffer[idx + len("<think>"):]
                in_think = True
            else:
                idx = buffer.find("</think>")
                if idx == -1:
                    # Pode ser que só uma PARTE de "</think>" tenha chegado
                    # nesse chunk (ex: "</th"), com o resto vindo no próximo.
                    # Guarda essa parte, descarta o resto (é conteúdo de
                    # pensamento mesmo, sem essa proteção o fechamento nunca
                    # seria detectado se viesse picado).
                    partial = _partial_tag_suffix_len(buffer, "</think>")
                    buffer = buffer[len(buffer) - partial:] if partial > 0 else ""
                    break
                buffer = buffer[idx + len("</think>"):]
                in_think = False

    if buffer and not in_think:
        yield buffer
