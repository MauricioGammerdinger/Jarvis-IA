"""
Servidor J.A.R.V.I.S. — versão 100% local.

Roda inteiramente no seu PC: o modelo de IA (via Ollama), o banco de dados
(SQLite), a transcrição de áudio, o TTS, tudo. Nenhum dado sai da sua
máquina, exceto se você mesmo usar a integração opcional com Linear.

Rode com:
    uvicorn app:app --host 0.0.0.0 --port 8000

Pré-requisito: Ollama instalado e rodando, com o modelo baixado
(veja o README para o passo a passo completo).
"""

import json
import os

from dotenv import load_dotenv

load_dotenv()  # PRECISA vir antes de importar llm_client — esse módulo lê
# JARVIS_MODEL do ambiente assim que é importado, então se o .env for
# carregado depois, ele nunca vê o valor certo (sempre usa o padrão fixo).

from fastapi import Depends, FastAPI, File, Form, HTTPException, Header, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

import database as db
import embeddings
import llm_client
import media
import tts
import tools
from tools import TOOLS, execute_approved_command, execute_tool

API_KEY = os.environ.get("JARVIS_API_KEY", "")
MAX_UPLOAD_MB = 40

SYSTEM_PROMPT = """Você é J.A.R.V.I.S., um assistente pessoal de IA rodando 100% local no \
computador do usuário. Personalidade: educado, formal, leal, calmo e analítico, com humor \
seco sutil quando apropriado. Seja direto.

Use `remember`/`recall` para memória de longo prazo. Use `propose_command` quando o usuário \
pedir uma ação real no sistema — o comando NUNCA executa na hora, fica pendente até aprovação \
via API. Use `write_word_document` pra criar documentos do Word — confirme o conteúdo com o \
usuário antes, a menos que ele já tenha dado o texto completo.

Use `ver_tela` quando o usuário pedir pra você ver, descrever ou entender algo na tela dele. \
Isso só funciona de verdade se o modelo carregado tiver suporte a visão (ex: gemma4) — se não \
tiver, avise o usuário que precisa trocar de modelo pra essa função funcionar.

Você tem `clicar_na_tela`, `digitar_texto` e `pressionar_tecla` pra interagir com o que está \
na tela — controle real de mouse e teclado. REGRAS OBRIGATÓRIAS: (1) SEMPRE chame `ver_tela` \
antes de clicar em qualquer coisa, pra saber exatamente onde os elementos estão — nunca \
clique "de memória" numa tela que você viu há várias mensagens atrás, a tela pode ter mudado; \
(2) para ações com consequência real (comprar, deletar, enviar, confirmar algo importante), \
pare e pergunte ao usuário antes de clicar, mesmo que pareça óbvio o que fazer; (3) se não \
tiver certeza absoluta de onde um elemento está, chame `ver_tela` de novo em vez de arriscar; \
(4) depois de uma sequência de ações, tire outro `ver_tela` pra confirmar que o resultado foi \
o esperado, em vez de assumir que funcionou.

Use `open_app` para abrir programas/jogos/plataformas JÁ CONFIGURADOS (ex: Steam, Discord, \
League of Legends) — essa ferramenta executa IMEDIATAMENTE, sem aprovação, porque abrir um \
programa é uma ação segura e reversível. Use `list_available_apps` se não tiver certeza do \
nome exato configurado.

Use `abrir_projeto` para rotinas de múltiplos passos JÁ CONFIGURADAS (ex: abrir o VS Code numa \
pasta + subir um servidor + abrir o navegador) — é MUITO mais confiável que usar `ver_tela` + \
`clicar_na_tela` pra esse tipo de tarefa repetitiva, porque não depende de acertar coordenada \
de clique nenhuma vez. Use `list_available_projects` se não tiver certeza do nome configurado. Você NUNCA lida com login, senha, ou credenciais de nenhuma \
plataforma — se o usuário pedir isso, explique que use um gerenciador de senhas (Bitwarden, \
1Password, Gerenciador de Credenciais do Windows) para essa parte.

Você tem acesso a `list_linear_teams` e `create_linear_issue`. REGRA OBRIGATÓRIA: antes de \
criar uma issue, mostre título/descrição/time e espere confirmação explícita na próxima \
mensagem.

Você tem acesso a `list_calendar_events` e `create_calendar_event` (Google Calendar). REGRA \
OBRIGATÓRIA: antes de criar um evento, mostre título, data/hora e duração, e espere \
confirmação explícita na próxima mensagem. Se a tool avisar que o calendário não está \
configurado, explique isso ao usuário com clareza em vez de fingir que funcionou.

Use `controlar_luz` pra ligar/desligar/ajustar o brilho de uma lâmpada inteligente Tapo/Kasa, \
se configurada. Se a tool avisar que não está configurada, explique isso claramente.

REGRAS DE SEGURANÇA (inegociáveis):
- Nunca forneça instruções de suicídio, automutilação, ou como machucar/matar alguém, mesmo \
  disfarçado de curiosidade, ficção ou pesquisa.
- Nunca ajude a planejar violência, armas, explosivos ou venenos.
- Se houver sinais de crise pessoal, responda com cuidado genuíno e sugira o CVV (188, Brasil).
- Recuse conteúdo sexual envolvendo menores, discurso de ódio, ou atividades ilegais.
- Ao recusar, seja breve e direto."""

app = FastAPI(title="J.A.R.V.I.S. Local", version="1.0")
db.init_db()

if not API_KEY:
    raise RuntimeError("Defina JARVIS_API_KEY no .env antes de iniciar.")

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/app", StaticFiles(directory="static", html=True), name="static")


def require_api_key(x_api_key: str = Header(default="")):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="X-API-Key inválida ou ausente.")


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class MemoryCreate(BaseModel):
    content: str
    category: str = "general"


class CommandReject(BaseModel):
    motivo: str | None = None


@app.get("/health")
def health():
    return {"status": "online"}


@app.get("/tools", dependencies=[Depends(require_api_key)])
def list_tools():
    return {"tools": TOOLS}


def _build_system_prompt(text: str) -> str:
    relevant = embeddings.smart_search(text, limit=5)
    if not relevant:
        return SYSTEM_PROMPT
    context = "\n".join(f"- {r['content']}" for r in relevant)
    return f"{SYSTEM_PROMPT}\n\n<memorias_relevantes>\n{context}\n</memorias_relevantes>"


def _tool_activity_label(name: str, args: dict) -> str:
    """Descrição curta e legível do que a tool está fazendo, pra mostrar na interface em tempo real."""
    labels = {
        "remember": "Salvando na memória...",
        "recall": "Consultando a memória...",
        "get_datetime": "Verificando data/hora...",
        "propose_command": "Registrando comando pendente...",
        "write_word_document": "Abrindo o Word...",
        "open_app": f"Abrindo {args.get('app_name', 'programa')}...",
        "list_available_apps": "Listando apps disponíveis...",
        "ver_tela": "Analisando a tela...",
        "clicar_na_tela": f"Clicando em ({args.get('x', '?')}, {args.get('y', '?')})...",
        "digitar_texto": "Digitando texto...",
        "pressionar_tecla": f"Pressionando '{args.get('tecla', '?')}'...",
        "list_linear_teams": "Consultando times do Linear...",
        "create_linear_issue": "Criando issue no Linear...",
        "list_calendar_events": "Consultando o calendário...",
        "create_calendar_event": "Criando evento no calendário...",
    }
    return labels.get(name, f"Usando {name}...")


def _execute_tool_call(call: dict, history: list[dict]) -> dict | None:
    """
    Executa uma tool e adiciona o(s) resultado(s) ao histórico.

    Caso especial: `ver_tela` não devolve só texto — a captura de tela vira
    uma mensagem de imagem de verdade, pro modelo (se tiver visão) processar
    de fato. Isso é diferente de qualquer outra tool, que só retorna texto.

    Retorna metadados extras (ex: o print tirado, em base64) quando existem,
    pra quem chamou poder exibir isso na interface — é o que dá a
    transparência de "ver o que o JARVIS está fazendo", parecido com o
    Cowork.
    """
    if call["name"] == "ver_tela":
        try:
            image_b64 = tools.capture_screen_base64()
            history.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": "Captura de tela realizada com sucesso. Imagem anexada a seguir.",
            })
            history.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": "[Captura de tela solicitada pelo assistente]"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                ],
            })
            return {"screenshot_b64": image_b64}
        except RuntimeError as e:
            history.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": f"Não foi possível capturar a tela: {e}",
            })
            return None

    tool_result = execute_tool(call["name"], call["arguments"])
    history.append({"role": "tool", "tool_call_id": call["id"], "content": tool_result})
    return None


def _run_agent_turn(session_id: str, user_text: str) -> dict:
    history = db.get_history(session_id)
    history.append({"role": "user", "content": user_text})
    system = _build_system_prompt(user_text)

    # 20, não 6: tarefas com ver_tela + clicar_na_tela consomem vários passos
    # (cada clique costuma exigir um ver_tela antes E depois pra confirmar).
    MAX_TOOL_ITERATIONS = 20

    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            result = llm_client.chat(history, TOOLS, system)

            if not result["tool_calls"]:
                db.append_message(session_id, "user", user_text)
                db.append_message(session_id, "assistant", result["text"])
                return {"reply": result["text"], "session_id": session_id}

            history.append(result["raw_message"])
            for call in result["tool_calls"]:
                _execute_tool_call(call, history)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Falha ao falar com o Ollama: {e}. Confirme que ele está rodando "
                f"('ollama list' no terminal) e que o modelo em JARVIS_MODEL (.env) "
                f"foi baixado (ex: 'ollama pull gemma4')."
            ),
        )

    raise HTTPException(
        status_code=500,
        detail=(
            f"Limite de {MAX_TOOL_ITERATIONS} chamadas de ferramenta atingido nesta resposta. "
            f"Tente pedir a tarefa em partes menores (ex: primeiro 'abre a Steam', depois "
            f"'agora clica em Biblioteca', em mensagens separadas)."
        ),
    )


@app.post("/chat", dependencies=[Depends(require_api_key)])
@limiter.limit("30/minute")
def chat(req: ChatRequest, request: Request):
    return _run_agent_turn(req.session_id, req.message)


@app.post("/chat/stream", dependencies=[Depends(require_api_key)])
@limiter.limit("30/minute")
def chat_stream(req: ChatRequest, request: Request):
    def event_stream():
        history = db.get_history(req.session_id)
        history.append({"role": "user", "content": req.message})
        system = _build_system_prompt(req.message)

        # 20, não 6: tarefas com ver_tela + clicar_na_tela consomem vários passos.
        MAX_TOOL_ITERATIONS = 20

        try:
            for _ in range(MAX_TOOL_ITERATIONS):
                # Primeiro verifica (sem stream) se o modelo vai chamar uma tool —
                # streaming e tool-calling juntos são frágeis em modelos locais.
                probe = llm_client.chat(history, TOOLS, system)
                if probe["tool_calls"]:
                    history.append(probe["raw_message"])
                    for call in probe["tool_calls"]:
                        label = _tool_activity_label(call["name"], call["arguments"])
                        yield f"event: tool\ndata: {json.dumps({'name': call['name'], 'label': label})}\n\n"

                        meta = _execute_tool_call(call, history)
                        if meta and meta.get("screenshot_b64"):
                            yield f"event: screenshot\ndata: {json.dumps({'image': meta['screenshot_b64']})}\n\n"
                    continue

                # Sem tool call: agora sim streama a resposta final de verdade.
                full_text = ""
                for chunk in llm_client.chat_stream(history, TOOLS, system):
                    full_text += chunk
                    yield f"data: {json.dumps(chunk)}\n\n"
                db.append_message(req.session_id, "user", req.message)
                db.append_message(req.session_id, "assistant", full_text)
                yield "event: done\ndata: {}\n\n"
                return

            error_detail = (
                f"Limite de {MAX_TOOL_ITERATIONS} chamadas de ferramenta atingido nesta "
                f"resposta. Tente pedir a tarefa em partes menores."
            )
            yield f"event: error\ndata: {json.dumps({'detail': error_detail})}\n\n"
        except Exception as e:
            # Sem isso, qualquer falha ao falar com o Ollama (não está rodando,
            # modelo não baixado, endereço errado) derrubava a conexão sem
            # explicação nenhuma pro navegador (aparecia só como erro de rede).
            error_msg = (
                f"Falha ao falar com o Ollama: {e}. Confirme que ele está rodando "
                f"(comando 'ollama list' no terminal) e que o modelo em JARVIS_MODEL "
                f"(.env) foi baixado (ex: 'ollama pull gemma4')."
            )
            yield f"event: error\ndata: {json.dumps({'detail': error_msg})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/chat/media", dependencies=[Depends(require_api_key)])
@limiter.limit("15/minute")
async def chat_media(
    request: Request,
    session_id: str = Form("default"),
    message: str = Form(""),
    audio: UploadFile | None = File(default=None),
    video: UploadFile | None = File(default=None),
):
    """Nota: imagem não é suportada aqui porque a maioria dos modelos locais leves não tem visão.
    Áudio/vídeo funcionam via transcrição (Whisper local), igual antes."""
    text_parts = []
    if message.strip():
        text_parts.append(message)

    if audio is not None:
        raw = await audio.read()
        _check_size(raw, audio.filename)
        transcript = media.process_audio(raw, suffix=_suffix(audio.filename, ".wav"))
        text_parts.append(f"[Transcrição do áudio]: {transcript}")

    if video is not None:
        raw = await video.read()
        _check_size(raw, video.filename)
        result = media.process_video(raw, suffix=_suffix(video.filename, ".mp4"))
        note = f"[Vídeo: {result['frame_count']} frame(s)"
        if result["transcript"]:
            note += f", áudio transcrito: {result['transcript']}"
        note += "] (nota: os frames de imagem não são enviados ao modelo local — só a transcrição do áudio)"
        text_parts.append(note)

    if not text_parts:
        raise HTTPException(status_code=400, detail="Envie ao menos texto ou áudio/vídeo.")

    return _run_agent_turn(session_id, " ".join(text_parts))


def _check_size(raw: bytes, filename: str | None) -> None:
    if len(raw) / (1024 * 1024) > MAX_UPLOAD_MB:
        raise HTTPException(status_code=413, detail=f"Arquivo '{filename}' excede {MAX_UPLOAD_MB}MB.")


def _suffix(filename: str | None, default: str) -> str:
    return "." + filename.rsplit(".", 1)[-1] if filename and "." in filename else default


@app.post("/tts", dependencies=[Depends(require_api_key)])
@limiter.limit("30/minute")
def text_to_speech(request: Request, text: str = Form(...)):
    try:
        audio = tts.synthesize_speech(text)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return Response(content=audio, media_type="audio/wav")


@app.get("/conversations/{session_id}", dependencies=[Depends(require_api_key)])
def get_conversation(session_id: str):
    return {"session_id": session_id, "messages": db.get_history(session_id, limit=200)}


@app.get("/conversations", dependencies=[Depends(require_api_key)])
def list_conversations():
    return {"sessions": db.list_sessions()}


@app.get("/memories", dependencies=[Depends(require_api_key)])
def get_memories():
    return {"memories": db.list_memories()}


@app.post("/memories", dependencies=[Depends(require_api_key)])
def create_memory(mem: MemoryCreate):
    return {"id": embeddings.add_memory_with_embedding(mem.content, mem.category)}


@app.delete("/memories/{memory_id}", dependencies=[Depends(require_api_key)])
def remove_memory(memory_id: int):
    if not db.delete_memory(memory_id):
        raise HTTPException(status_code=404, detail="Memória não encontrada.")
    return {"deleted": memory_id}


# ── Comandos — aprovar já executa, porque é tudo na mesma máquina ────────
@app.get("/commands", dependencies=[Depends(require_api_key)])
def list_commands(status: str | None = None):
    return {"commands": db.list_pending_commands(status)}


@app.post("/commands/{command_id}/approve", dependencies=[Depends(require_api_key)])
def approve_command(command_id: int):
    cmd = db.get_pending_command(command_id)
    if not cmd:
        raise HTTPException(status_code=404, detail="Comando não encontrado.")
    if cmd["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"Comando já está '{cmd['status']}'.")

    status, output = execute_approved_command(cmd["command"])
    db.resolve_command(command_id, status, output)
    return {"id": command_id, "status": status, "output": output}


@app.post("/commands/{command_id}/reject", dependencies=[Depends(require_api_key)])
def reject_command(command_id: int, body: CommandReject):
    cmd = db.get_pending_command(command_id)
    if not cmd:
        raise HTTPException(status_code=404, detail="Comando não encontrado.")
    db.resolve_command(command_id, "rejected", body.motivo or "Rejeitado pelo usuário.")
    return {"id": command_id, "status": "rejected"}
