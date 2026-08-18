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

from openai import OpenAI

client = OpenAI(base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"), api_key="ollama")


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
        "text": message.content or "",
        "tool_calls": tool_calls,
        "raw_message": message.model_dump(),
    }


def chat_stream(messages: list[dict], tools: list[dict], system: str):
    """
    Gera pedaços de texto conforme chegam (streaming). Se o modelo decidir
    chamar uma ferramenta, o streaming não devolve texto nessa rodada — quem
    chama essa função deve, nesse caso, cair de volta pra `chat()` normal
    pra pegar o tool_call estruturado (streaming + tool call juntos é mais
    frágil em modelos locais, então simplificamos assim).
    """
    full_messages = [{"role": "system", "content": system}] + messages
    stream = client.chat.completions.create(
        model=_get_model_name(),
        messages=full_messages,
        tools=to_openai_tool_schema(tools) if tools else None,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content
