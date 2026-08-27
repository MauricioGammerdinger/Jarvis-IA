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
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

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
import calendar_hub
import background_agents
import code_editor
import ai_tokens
import git_projects
import email_hub
import morning_digest
import news_radar
import tools
from tools import TOOLS, execute_approved_command, execute_tool

# ── Logging — grava em arquivo (logs/jarvis.log) além do terminal. Se algo
# der errado (ex: resposta não chega), esse arquivo mostra exatamente onde
# travou, com timestamp e erro completo, em vez de só "não sei o que houve".
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("jarvis")
logger.setLevel(logging.DEBUG)
logger.propagate = False

if not logger.handlers:
    file_handler = RotatingFileHandler(
        LOG_DIR / "jarvis.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(console_handler)

API_KEY = os.environ.get("JARVIS_API_KEY", "")
MAX_UPLOAD_MB = 40

SYSTEM_PROMPT = """Você é J.A.R.V.I.S., um assistente pessoal de IA rodando 100% local no \
computador do usuário. Personalidade: educado, formal, leal, calmo e analítico, com humor \
seco sutil quando apropriado. Seja direto.

Use `remember`/`recall` para memória de longo prazo. Use `propose_command` quando o usuário \
pedir uma ação real no sistema — o comando NUNCA executa na hora, fica pendente até aprovação \
via API. Use `write_word_document` pra criar documentos do Word — confirme o conteúdo com o \
usuário antes, a menos que ele já tenha dado o texto completo.

SECOND BRAIN — 8 categorias especiais de memória que entram em TODA conversa, sempre: \
`voce`, `metas`, `carreira`, `projetos`, `financas`, `aprendizado`, `saude`, `relacoes`. Use \
esses nomes exatos (minúsculo, sem acento) ao chamar `remember` pra essas áreas. Se o usuário \
pedir pra "configurar", "montar" ou "começar" o Second Brain, chame a tool \
`iniciar_configuracao_second_brain` — ela te diz exatamente o que fazer a seguir.

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
nome exato configurado. Se `open_app` avisar que o app NÃO está configurado, NÃO desista — \
pergunte ao usuário qual é o comando ou caminho do executável desse programa, e quando ele \
te disser, chame `cadastrar_app` pra salvar (aí sim, `open_app` funciona de verdade da \
próxima vez, sem precisar perguntar de novo).

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

AGENDA: `ver_agenda_hoje`, `ver_agenda_semana`, `proximo_compromisso` mostram eventos de \
TODAS as agendas configuradas, já mescladas. `cadastrar_agenda` adiciona uma nova (peça o \
link "endereço secreto em formato iCal" do Google Agenda).

E-MAILS: `ver_emails` (com balde 'acao'/'info'/'ruido', ou sem parâmetro pra resumo geral) e \
`atualizar_emails`. `cadastrar_conta_email` precisa de uma SENHA DE APP (nunca a senha normal \
— gerada em myaccount.google.com/apppasswords).

NOTÍCIAS: `ver_noticias` (com ou sem assunto) e `gerenciar_assuntos_noticia` (adicionar/remover/listar).

MORNING DIGEST: `gerar_morning_digest` — use quando o usuário disser "bom dia" ou pedir um \
resumo do dia. Junta agenda + e-mails de ação + notícias + clima + uma meta.

CÓDIGO: `ler_arquivo_codigo`/`editar_arquivo_codigo`/`listar_pasta_codigo` dão acesso direto a \
arquivos de qualquer pasta (sem restrição, por decisão do usuário) — `editar_arquivo_codigo` \
EXECUTA NA HORA, sem pedir confirmação (o usuário quer ver a mudança ao vivo no editor), mas \
sempre relia o arquivo com `ler_arquivo_codigo` antes de editar, pra saber o conteúdo real \
atual, nunca suponha. `cadastrar_projeto_codigo` e `status_git_projeto` mostram o estado do \
git de um projeto (mudanças pendentes, sincronia com o GitHub). Pra abrir um projeto \
visualmente (VS Code) antes de mexer nele, use `abrir_projeto` (se configurado) — assim o \
usuário vê a tela enquanto você edita os arquivos por trás.

TOKENS DE IA: `registrar_uso_ia` grava uma chamada de API com custo calculado automático. \
`ver_custo_ia` mostra gasto do mês/orçamento/projeção. `cadastrar_assinatura_ia` cadastra um \
plano (Claude Pro/Max, ChatGPT, Cursor); `registrar_uso_assinatura` soma uso (ex: "gastei mais \
uma mensagem do Claude" → +1); `ver_assinaturas_ia` mostra cota usada/restante/tempo até reset.

COMPROMISSOS (Second Brain ativo): sempre que o usuário disser algo que soe como uma promessa \
ou compromisso com prazo (ex: "vou terminar isso até sexta", "preciso entregar o relatório \
amanhã"), chame `registrar_compromisso` SEM esperar ele pedir — é assim que o JARVIS cobra \
sozinho depois, perto do prazo, sem precisar ser perguntado. `listar_compromissos` e \
`concluir_compromisso` gerenciam o que já foi guardado.

REGRA OBRIGATÓRIA SOBRE RESULTADOS DE FERRAMENTAS: depois de qualquer chamada de ferramenta, \
sua resposta final DEVE refletir o que realmente aconteceu — nunca dê uma resposta genérica \
tipo "Estou pronto, o que você gostaria de fazer?" quando uma ferramenta acabou de rodar. Se \
deu certo, confirme o que foi feito. Se falhou ou o item não existe (ex: app não configurado), \
diga isso explicitamente e, se a ferramenta te deu alternativas (ex: lista de apps \
disponíveis), mencione elas. Isso é mais importante ainda quando o pedido tem VÁRIAS partes \
(ex: "abre X e escreve Y") — depois de `open_app` abrir o programa, você ainda precisa \
completar o resto do pedido usando `ver_tela` (pra achar onde clicar/digitar) + \
`clicar_na_tela` + `digitar_texto`, não parar só na primeira parte.

REGRAS DE SEGURANÇA (inegociáveis):
- Nunca forneça instruções de suicídio, automutilação, ou como machucar/matar alguém, mesmo \
  disfarçado de curiosidade, ficção ou pesquisa.
- Nunca ajude a planejar violência, armas, explosivos ou venenos.
- Se houver sinais de crise pessoal, responda com cuidado genuíno e sugira o CVV (188, Brasil).
- Recuse conteúdo sexual envolvendo menores, discurso de ódio, ou atividades ilegais.
- Ao recusar, seja breve e direto."""

@asynccontextmanager
async def lifespan(app: FastAPI):
    background_agents.start_scheduler()
    logger.info("Agentes de fundo iniciados (triagem de e-mail, notícias, morning digest).")
    yield
    background_agents.stop_scheduler()


app = FastAPI(title="J.A.R.V.I.S. Local", version="1.0", lifespan=lifespan)
db.init_db()

logger.info("=" * 60)
logger.info("J.A.R.V.I.S. iniciando...")
logger.info(f"Modelo configurado: {os.environ.get('JARVIS_MODEL', '(não definido, usará qwen3:8b)')}")
logger.info(f"Endereço do Ollama: {os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434/v1')}")
logger.info(f"Timeout configurado: {os.environ.get('OLLAMA_TIMEOUT_SECONDS', '60')}s")
logger.info(f"Arquivo de log: {LOG_DIR / 'jarvis.log'}")
logger.info("=" * 60)

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


class AppConfigRequest(BaseModel):
    nome: str
    comando: str
    observacao: str = ""


@app.get("/apps", dependencies=[Depends(require_api_key)])
def list_apps():
    apps = tools._load_apps_config()
    return {"apps": [{"nome": nome, **info} for nome, info in apps.items()]}


@app.post("/apps", dependencies=[Depends(require_api_key)])
def create_app(req: AppConfigRequest):
    if not req.nome.strip() or not req.comando.strip():
        raise HTTPException(status_code=400, detail="Nome e comando são obrigatórios.")
    tools.save_app_config(req.nome, req.comando, req.observacao)
    return {"ok": True}


@app.delete("/apps/{nome}", dependencies=[Depends(require_api_key)])
def remove_app(nome: str):
    removed = tools.delete_app_config(nome)
    if not removed:
        raise HTTPException(status_code=404, detail=f"App '{nome}' não encontrado.")
    return {"ok": True}


# ── Central de Agenda ──────────────────────────────────────────────────
class CalendarConfigRequest(BaseModel):
    nome: str
    cor: str = "#5fe3f0"
    ics_url: str


@app.get("/calendar/events", dependencies=[Depends(require_api_key)])
def get_calendar_events(dias: int = 7):
    return {"events": calendar_hub.get_merged_events(days_ahead=dias)}


@app.get("/calendar/config", dependencies=[Depends(require_api_key)])
def list_calendars():
    return {"calendars": calendar_hub.load_calendars_config()}


@app.post("/calendar/config", dependencies=[Depends(require_api_key)])
def add_calendar_config(req: CalendarConfigRequest):
    if not req.nome.strip() or not req.ics_url.strip():
        raise HTTPException(status_code=400, detail="Nome e link iCal são obrigatórios.")
    calendar_hub.add_calendar(req.nome, req.cor, req.ics_url)
    return {"ok": True}


@app.delete("/calendar/config/{nome}", dependencies=[Depends(require_api_key)])
def remove_calendar_config(nome: str):
    removed = calendar_hub.remove_calendar(nome)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Agenda '{nome}' não encontrada.")
    return {"ok": True}


# ── Central de E-mails ──────────────────────────────────────────────────
class EmailAccountRequest(BaseModel):
    apelido: str
    cor: str = "#5fe3f0"
    host: str
    usuario: str
    senha_app: str


@app.get("/email/triaged", dependencies=[Depends(require_api_key)])
def get_triaged_emails_endpoint():
    return email_hub.get_triaged_emails()


@app.get("/email/config", dependencies=[Depends(require_api_key)])
def list_email_accounts():
    # NUNCA devolve a senha de app de volta pro navegador
    accounts = email_hub.load_email_accounts()
    return {"accounts": [{"apelido": a["apelido"], "cor": a["cor"], "host": a["host"], "usuario": a["usuario"]} for a in accounts]}


@app.post("/email/config", dependencies=[Depends(require_api_key)])
def add_email_account_config(req: EmailAccountRequest):
    if not all([req.apelido.strip(), req.host.strip(), req.usuario.strip(), req.senha_app.strip()]):
        raise HTTPException(status_code=400, detail="Todos os campos (menos cor) são obrigatórios.")
    erro = email_hub.add_email_account(req.apelido, req.cor, req.host, req.usuario, req.senha_app)
    if erro:
        raise HTTPException(status_code=400, detail=erro)
    return {"ok": True}


@app.delete("/email/config/{apelido}", dependencies=[Depends(require_api_key)])
def remove_email_account_config(apelido: str):
    removed = email_hub.remove_email_account(apelido)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Conta '{apelido}' não encontrada.")
    return {"ok": True}


@app.get("/email/allowed-hosts", dependencies=[Depends(require_api_key)])
def get_allowed_email_hosts():
    return {"hosts": sorted(email_hub.ALLOWED_IMAP_HOSTS)}


# ── Radar de Notícias ────────────────────────────────────────────────────
class NewsTopicRequest(BaseModel):
    assunto: str


@app.get("/news", dependencies=[Depends(require_api_key)])
def get_news():
    return {"news": news_radar.get_all_headlines()}


@app.get("/news/topics", dependencies=[Depends(require_api_key)])
def list_news_topics():
    return {"topics": news_radar.load_topics()}


@app.post("/news/topics", dependencies=[Depends(require_api_key)])
def add_news_topic(req: NewsTopicRequest):
    if not req.assunto.strip():
        raise HTTPException(status_code=400, detail="Assunto é obrigatório.")
    news_radar.add_topic(req.assunto)
    return {"ok": True}


@app.delete("/news/topics/{assunto}", dependencies=[Depends(require_api_key)])
def remove_news_topic(assunto: str):
    removed = news_radar.remove_topic(assunto)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Assunto '{assunto}' não encontrado.")
    return {"ok": True}


class NarrationHourRequest(BaseModel):
    hora: int


@app.get("/news/narration-hour", dependencies=[Depends(require_api_key)])
def get_narration_hour_endpoint():
    return {"hora": news_radar.get_narration_hour()}


@app.post("/news/narration-hour", dependencies=[Depends(require_api_key)])
def set_narration_hour_endpoint(req: NarrationHourRequest):
    if not (0 <= req.hora <= 23):
        raise HTTPException(status_code=400, detail="Hora precisa estar entre 0 e 23.")
    news_radar.set_narration_hour(req.hora)
    return {"ok": True}


class DiscoverSourcesRequest(BaseModel):
    nicho: str


class AddSourceRequest(BaseModel):
    nome: str
    feed_url: str


@app.get("/news/sources", dependencies=[Depends(require_api_key)])
def list_news_sources():
    return {"sources": news_radar.load_sources()}


@app.post("/news/sources/discover", dependencies=[Depends(require_api_key)])
def discover_news_sources(req: DiscoverSourcesRequest):
    if not req.nicho.strip():
        raise HTTPException(status_code=400, detail="Nicho é obrigatório.")
    return {"resultados": news_radar.discover_and_validate_sources(req.nicho)}


@app.post("/news/sources", dependencies=[Depends(require_api_key)])
def add_news_source(req: AddSourceRequest):
    if not req.nome.strip() or not req.feed_url.strip():
        raise HTTPException(status_code=400, detail="Nome e link do feed são obrigatórios.")
    news_radar.add_source(req.nome, req.feed_url)
    return {"ok": True}


@app.delete("/news/sources/{nome}", dependencies=[Depends(require_api_key)])
def remove_news_source(nome: str):
    removed = news_radar.remove_source(nome)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Fonte '{nome}' não encontrada.")
    return {"ok": True}


@app.get("/news/narrate", dependencies=[Depends(require_api_key)])
def narrate_news_now(assunto: str | None = None):
    return {"texto": news_radar.narrate_news(assunto=assunto)}


# ── Projetos de código (aparecem no Painel de Agentes) ──────────────────
class CodeProjectRequest(BaseModel):
    nome: str
    caminho: str


@app.get("/code-projects", dependencies=[Depends(require_api_key)])
def list_code_projects():
    return {"projects": git_projects.load_code_projects()}


@app.post("/code-projects", dependencies=[Depends(require_api_key)])
def add_code_project_endpoint(req: CodeProjectRequest):
    if not req.nome.strip() or not req.caminho.strip():
        raise HTTPException(status_code=400, detail="Nome e caminho são obrigatórios.")
    git_projects.add_code_project(req.nome, req.caminho)
    return {"ok": True}


@app.delete("/code-projects/{nome}", dependencies=[Depends(require_api_key)])
def remove_code_project_endpoint(nome: str):
    removed = git_projects.remove_code_project(nome)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Projeto '{nome}' não encontrado.")
    return {"ok": True}


# ── Dashboard de Tokens de IA ─────────────────────────────────────────────
class AiUsageRequest(BaseModel):
    data: str
    projeto: str
    modelo: str
    input_tokens: int
    output_tokens: int


class AiConfigRequest(BaseModel):
    budget_monthly_usd: float | None = None
    alert_pct: float | None = None
    currency: str | None = None
    usd_to_brl: float | None = None


class AiPriceRequest(BaseModel):
    modelo: str
    preco_input: float
    preco_output: float


class AiSubscriptionRequest(BaseModel):
    nome: str
    unidade: str
    limite: float
    tipo_reset: str
    reset_a_cada_horas: float | None = None
    custo_mensal_usd: float = 0


class AiSubscriptionIncrementRequest(BaseModel):
    quantidade: float = 1


@app.get("/ai-tokens/summary", dependencies=[Depends(require_api_key)])
def get_ai_summary_endpoint(mes: str | None = None):
    api = ai_tokens.get_api_summary(mes=mes)
    total = ai_tokens.get_total_ai_cost_this_month()
    return {"api": api, "total": total}


@app.get("/ai-tokens/usage", dependencies=[Depends(require_api_key)])
def list_ai_usage_endpoint(dias: int | None = None):
    return {"usage": ai_tokens.get_usage_with_cost(periodo_dias=dias)}


@app.post("/ai-tokens/usage", dependencies=[Depends(require_api_key)])
def add_ai_usage_endpoint(req: AiUsageRequest):
    resultado = ai_tokens.register_usage(req.data, req.projeto, req.modelo, req.input_tokens, req.output_tokens)
    return {"ok": True, **resultado}


@app.put("/ai-tokens/usage/{usage_id}", dependencies=[Depends(require_api_key)])
def update_ai_usage_endpoint(usage_id: int, req: AiUsageRequest):
    updated = db.update_ai_usage(usage_id, req.data, req.projeto, req.modelo, req.input_tokens, req.output_tokens)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Uso #{usage_id} não encontrado.")
    return {"ok": True}


@app.delete("/ai-tokens/usage/{usage_id}", dependencies=[Depends(require_api_key)])
def delete_ai_usage_endpoint(usage_id: int):
    removed = db.delete_ai_usage(usage_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Uso #{usage_id} não encontrado.")
    return {"ok": True}


@app.get("/ai-tokens/prices", dependencies=[Depends(require_api_key)])
def get_ai_prices_endpoint():
    return {"prices": ai_tokens.load_price_table()}


@app.post("/ai-tokens/prices", dependencies=[Depends(require_api_key)])
def set_ai_price_endpoint(req: AiPriceRequest):
    ai_tokens.set_model_price(req.modelo, req.preco_input, req.preco_output)
    return {"ok": True}


@app.get("/ai-tokens/config", dependencies=[Depends(require_api_key)])
def get_ai_config_endpoint():
    return ai_tokens.load_config()


@app.post("/ai-tokens/config", dependencies=[Depends(require_api_key)])
def update_ai_config_endpoint(req: AiConfigRequest):
    return ai_tokens.update_config(**req.model_dump())


@app.get("/ai-tokens/subscriptions", dependencies=[Depends(require_api_key)])
def list_ai_subscriptions_endpoint():
    return {"subscriptions": ai_tokens.get_subscriptions_snapshot()}


@app.post("/ai-tokens/subscriptions", dependencies=[Depends(require_api_key)])
def add_ai_subscription_endpoint(req: AiSubscriptionRequest):
    try:
        ai_tokens.add_subscription(req.nome, req.unidade, req.limite, req.tipo_reset, req.reset_a_cada_horas, custo_mensal_usd=req.custo_mensal_usd)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@app.delete("/ai-tokens/subscriptions/{nome}", dependencies=[Depends(require_api_key)])
def delete_ai_subscription_endpoint(nome: str):
    removed = db.delete_subscription(nome)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Assinatura '{nome}' não encontrada.")
    return {"ok": True}


@app.post("/ai-tokens/subscriptions/{nome}/increment", dependencies=[Depends(require_api_key)])
def increment_ai_subscription_endpoint(nome: str, req: AiSubscriptionIncrementRequest):
    try:
        sub = ai_tokens.increment_subscription(nome, req.quantidade)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True, "subscription": sub}


@app.post("/ai-tokens/subscriptions/{nome}/reset", dependencies=[Depends(require_api_key)])
def reset_ai_subscription_endpoint(nome: str):
    try:
        sub = ai_tokens.reset_subscription_now(nome)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True, "subscription": sub}


# ── Notificações proativas ────────────────────────────────────────────────
@app.get("/notifications", dependencies=[Depends(require_api_key)])
def get_notifications(apenas_nao_lidas: bool = True):
    if apenas_nao_lidas:
        return {"notifications": db.list_unread_notifications()}
    return {"notifications": db.list_all_notifications()}


@app.post("/notifications/{notification_id}/read", dependencies=[Depends(require_api_key)])
def mark_notification_read_endpoint(notification_id: int):
    marked = db.mark_notification_read(notification_id)
    if not marked:
        raise HTTPException(status_code=404, detail=f"Notificação #{notification_id} não encontrada.")
    return {"ok": True}


@app.post("/notifications/read-all", dependencies=[Depends(require_api_key)])
def mark_all_notifications_read_endpoint():
    quantidade = db.mark_all_notifications_read()
    return {"ok": True, "marcadas": quantidade}


# ── Morning Digest ───────────────────────────────────────────────────────
@app.get("/digest", dependencies=[Depends(require_api_key)])
def get_morning_digest(cidade: str | None = None):
    return morning_digest.generate_digest(cidade_clima=cidade)


# ── Painel de Agentes ────────────────────────────────────────────────────
# Constante nomeada, fácil de ajustar: um agente "atrasa" quando passa
# desse múltiplo da própria cadência sem rodar.
AGENT_STALE_FACTOR = 2.5
# Pro Hey JARVIS (contínuo, sem cadência): grava heartbeat a cada 20s —
# se passar bem disso sem atualizar, o processo provavelmente morreu.
AGENT_CONTINUOUS_STALE_SECONDS = 90


def _compute_agent_snapshot(agent_id: str) -> dict:
    meta = background_agents.AGENTS_REGISTRY[agent_id]
    state_row = db.get_agent_state(agent_id)
    now = datetime.now(timezone.utc)
    off = background_agents.is_agent_off(agent_id)

    last_iso = state_row["last_run"] if state_row else None
    age_min = None
    if last_iso:
        try:
            last_dt = datetime.fromisoformat(last_iso)
            age_min = (now - last_dt).total_seconds() / 60
        except ValueError:
            age_min = None  # timestamp corrompido — trata como se nunca tivesse rodado

    every_min = meta["every_min"]
    phase = None
    next_in_min = None
    if every_min is not None and age_min is not None:
        phase = min(1.0, age_min / every_min)
        next_in_min = max(0.0, every_min - age_min)

    if off:
        state = "off"
    elif age_min is None:
        state = "idle"
    elif state_row["status"] == "error":
        state = "error"
    elif every_min is not None and age_min > every_min * AGENT_STALE_FACTOR:
        state = "stale"
    elif every_min is None and age_min * 60 > AGENT_CONTINUOUS_STALE_SECONDS:
        state = "stale"
    else:
        state = "ok"

    run = {"url": meta["run_path"], "method": "POST", "body": {}} if meta["run_path"] else None

    return {
        "id": agent_id,
        "nome": meta["nome"],
        "icon": meta["icon"],
        "faz": meta["faz"],
        "every_min": every_min,
        "last": last_iso,
        "age_min": round(age_min, 1) if age_min is not None else None,
        "next_in_min": round(next_in_min, 1) if next_in_min is not None else None,
        "phase": round(phase, 3) if phase is not None else None,
        "state": state,
        "metric": (state_row["metric"] if state_row else "") or "",
        "detail": (state_row["detail"] if state_row else "") or "",
        "run": run,
        "arquivo": meta["arquivo"],
    }


def _compute_git_project_snapshot(nome: str, caminho: str) -> dict:
    """
    Projetos de código não são 'agentes de fundo' no sentido de rodar
    sozinhos — são uma checagem ao vivo do estado real do git. Por isso
    não têm cadência/fase (every_min=None), mas ainda mostram há quanto
    tempo foi o último commit, igual os outros agentes.
    """
    status = git_projects.get_git_status(caminho)
    agent_id = f"git_{nome}"

    if "erro" in status:
        return {
            "id": agent_id, "nome": nome, "icon": "💻",
            "faz": f"Repositório git em {caminho}",
            "every_min": None, "last": None, "age_min": None, "next_in_min": None, "phase": None,
            "state": "off", "metric": "", "detail": status["erro"],
            "run": None, "arquivo": caminho,
        }

    age_min = None
    if status.get("commit_iso"):
        try:
            commit_dt = datetime.fromisoformat(status["commit_iso"])
            age_min = (datetime.now(timezone.utc) - commit_dt).total_seconds() / 60
        except ValueError:
            age_min = None

    if status["mudancas_pendentes"] > 0 or status["ahead"] > 0 or status["behind"] > 0:
        state = "stale"
    else:
        state = "ok"

    partes = []
    if status["mudancas_pendentes"] > 0:
        partes.append(f"{status['mudancas_pendentes']} pendente(s)")
    if status["ahead"] > 0:
        partes.append(f"{status['ahead']} à frente")
    if status["behind"] > 0:
        partes.append(f"{status['behind']} atrás")
    metric = ", ".join(partes) if partes else "sincronizado"

    return {
        "id": agent_id, "nome": nome, "icon": "💻",
        "faz": f"Repositório git (branch {status['branch']})",
        "every_min": None,
        "last": status.get("commit_iso"),
        "age_min": round(age_min, 1) if age_min is not None else None,
        "next_in_min": None, "phase": None,
        "state": state, "metric": metric, "detail": status.get("commit_msg") or "",
        "run": None, "arquivo": caminho,
    }


@app.get("/api/agents", dependencies=[Depends(require_api_key)])
def get_agents_snapshot():
    agents = [_compute_agent_snapshot(agent_id) for agent_id in background_agents.AGENTS_REGISTRY]
    agents += [
        _compute_git_project_snapshot(p["nome"], p["caminho"]) for p in git_projects.load_code_projects()
    ]
    resumo = {"total": len(agents), "ok": 0, "atencao": 0, "off": 0}
    pior = None
    pior_prioridade = -1
    prioridade_por_estado = {"error": 3, "stale": 2, "idle": 1, "ok": 0, "off": -1}
    for a in agents:
        if a["state"] in ("ok",):
            resumo["ok"] += 1
        elif a["state"] == "off":
            resumo["off"] += 1
        else:
            resumo["atencao"] += 1
        prioridade = prioridade_por_estado.get(a["state"], 0)
        if prioridade > pior_prioridade:
            pior_prioridade = prioridade
            pior = a["id"]
    resumo["pior"] = pior

    return {"ok": True, "now": datetime.now(timezone.utc).isoformat(), "agents": agents, "resumo": resumo}


@app.post("/agents/email_triage/run", dependencies=[Depends(require_api_key)])
def run_email_triage_now():
    background_agents.run_email_triage_job()
    return {"ok": True, "snapshot": _compute_agent_snapshot("email_triage")}


@app.post("/agents/news_radar/run", dependencies=[Depends(require_api_key)])
def run_news_radar_now():
    background_agents.run_news_radar_job()
    return {"ok": True, "snapshot": _compute_agent_snapshot("news_radar")}


@app.post("/agents/morning_digest/run", dependencies=[Depends(require_api_key)])
def run_morning_digest_now():
    background_agents.run_morning_digest_job(forcar=True)
    return {"ok": True, "snapshot": _compute_agent_snapshot("morning_digest")}


@app.post("/agents/news_narration/run", dependencies=[Depends(require_api_key)])
def run_news_narration_now():
    background_agents.run_news_narration_job(forcar=True)
    return {"ok": True, "snapshot": _compute_agent_snapshot("news_narration")}


@app.post("/agents/commitments_followup/run", dependencies=[Depends(require_api_key)])
def run_commitments_followup_now():
    background_agents.run_commitments_followup_job()
    return {"ok": True, "snapshot": _compute_agent_snapshot("commitments_followup")}


# Endpoints simples de compromissos, pra uso futuro numa interface dedicada
@app.get("/commitments", dependencies=[Depends(require_api_key)])
def list_commitments_endpoint(status: str | None = None):
    return {"commitments": db.list_commitments(status)}


@app.post("/commitments/{commitment_id}/complete", dependencies=[Depends(require_api_key)])
def complete_commitment_endpoint(commitment_id: int):
    sucesso = db.complete_commitment(commitment_id)
    if not sucesso:
        raise HTTPException(status_code=404, detail=f"Compromisso #{commitment_id} não encontrado.")
    return {"ok": True}


# As 8 áreas do "Second Brain" — memórias nessas categorias entram em TODA
# conversa, sempre, diferente da busca por relevância (que só traz o que
# parece pertinente à pergunta atual). Isso é o que faz o JARVIS "conhecer"
# você de verdade, não só lembrar quando perguntado.
SECOND_BRAIN_CATEGORIES = {
    "voce": "Sobre você",
    "metas": "Metas",
    "carreira": "Carreira",
    "projetos": "Projetos",
    "financas": "Finanças",
    "aprendizado": "Aprendizado",
    "saude": "Saúde",
    "relacoes": "Relações",
}


def _build_second_brain_context() -> str:
    all_memories = db.list_memories()
    by_category: dict[str, list[str]] = {}
    for m in all_memories:
        if m["category"] in SECOND_BRAIN_CATEGORIES:
            by_category.setdefault(m["category"], []).append(m["content"])

    if not by_category:
        return ""

    lines = []
    for cat, label in SECOND_BRAIN_CATEGORIES.items():
        if cat in by_category:
            lines.append(f"{label}: " + "; ".join(by_category[cat]))
    return "\n".join(lines)


def _build_system_prompt(text: str) -> str:
    prompt = SYSTEM_PROMPT

    second_brain = _build_second_brain_context()
    if second_brain:
        prompt += (
            "\n\n<second_brain>\nInformações centrais sobre o usuário — SEMPRE "
            f"leve isso em conta, mesmo sem ele perguntar diretamente:\n{second_brain}\n</second_brain>"
        )

    relevant = embeddings.smart_search(text, limit=5)
    if relevant:
        context = "\n".join(f"- {r['content']}" for r in relevant)
        prompt += f"\n\n<memorias_relevantes>\n{context}\n</memorias_relevantes>"

    return prompt


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
    logger.info(f"[chat] session={session_id} | mensagem='{user_text[:80]}'")
    history = db.get_history(session_id)
    history.append({"role": "user", "content": user_text})
    system = _build_system_prompt(user_text)

    # 20, não 6: tarefas com ver_tela + clicar_na_tela consomem vários passos
    # (cada clique costuma exigir um ver_tela antes E depois pra confirmar).
    MAX_TOOL_ITERATIONS = 20

    try:
        for i in range(MAX_TOOL_ITERATIONS):
            t0 = time.monotonic()
            logger.debug(f"[chat] session={session_id} | iteração {i+1}/{MAX_TOOL_ITERATIONS} — chamando o modelo...")
            result = llm_client.chat(history, TOOLS, system)
            duracao = time.monotonic() - t0
            logger.info(
                f"[chat] session={session_id} | modelo respondeu em {duracao:.1f}s "
                f"| tool_calls={[c['name'] for c in result['tool_calls']]}"
            )

            if not result["tool_calls"]:
                db.append_message(session_id, "user", user_text)
                db.append_message(session_id, "assistant", result["text"])
                logger.info(f"[chat] session={session_id} | concluído, resposta com {len(result['text'])} caracteres")
                return {"reply": result["text"], "session_id": session_id}

            history.append(result["raw_message"])
            for call in result["tool_calls"]:
                t_tool = time.monotonic()
                _execute_tool_call(call, history)
                logger.info(
                    f"[chat] session={session_id} | tool '{call['name']}' executada em "
                    f"{time.monotonic() - t_tool:.1f}s"
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[chat] session={session_id} | ERRO ao falar com o Ollama")
        raise HTTPException(
            status_code=502,
            detail=(
                f"Falha ao falar com o Ollama: {e}. Confirme que ele está rodando "
                f"('ollama list' no terminal) e que o modelo em JARVIS_MODEL (.env) "
                f"foi baixado (ex: 'ollama pull gemma4')."
            ),
        )

    logger.warning(f"[chat] session={session_id} | limite de {MAX_TOOL_ITERATIONS} chamadas de ferramenta atingido")
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
        logger.info(f"[stream] session={req.session_id} | mensagem='{req.message[:80]}'")
        history = db.get_history(req.session_id)
        history.append({"role": "user", "content": req.message})
        system = _build_system_prompt(req.message)

        # 20, não 6: tarefas com ver_tela + clicar_na_tela consomem vários passos.
        MAX_TOOL_ITERATIONS = 20

        try:
            for i in range(MAX_TOOL_ITERATIONS):
                # Primeiro verifica (sem stream) se o modelo vai chamar uma tool —
                # streaming e tool-calling juntos são frágeis em modelos locais.
                t0 = time.monotonic()
                logger.debug(f"[stream] session={req.session_id} | iteração {i+1}/{MAX_TOOL_ITERATIONS} — chamando o modelo (probe)...")
                probe = llm_client.chat(history, TOOLS, system)
                logger.info(
                    f"[stream] session={req.session_id} | probe respondeu em {time.monotonic() - t0:.1f}s "
                    f"| tool_calls={[c['name'] for c in probe['tool_calls']]}"
                )
                if probe["tool_calls"]:
                    history.append(probe["raw_message"])
                    for call in probe["tool_calls"]:
                        label = _tool_activity_label(call["name"], call["arguments"])
                        yield f"event: tool\ndata: {json.dumps({'name': call['name'], 'label': label})}\n\n"

                        t_tool = time.monotonic()
                        meta = _execute_tool_call(call, history)
                        logger.info(f"[stream] session={req.session_id} | tool '{call['name']}' em {time.monotonic() - t_tool:.1f}s")
                        if meta and meta.get("screenshot_b64"):
                            yield f"event: screenshot\ndata: {json.dumps({'image': meta['screenshot_b64']})}\n\n"
                    continue

                # Sem tool call: agora sim streama a resposta final de verdade.
                t_stream = time.monotonic()
                full_text = ""
                for chunk in llm_client.chat_stream(history, TOOLS, system):
                    full_text += chunk
                    yield f"data: {json.dumps(chunk)}\n\n"
                logger.info(
                    f"[stream] session={req.session_id} | streaming final levou "
                    f"{time.monotonic() - t_stream:.1f}s, {len(full_text)} caracteres"
                )
                db.append_message(req.session_id, "user", req.message)
                db.append_message(req.session_id, "assistant", full_text)
                yield "event: done\ndata: {}\n\n"
                return

            error_detail = (
                f"Limite de {MAX_TOOL_ITERATIONS} chamadas de ferramenta atingido nesta "
                f"resposta. Tente pedir a tarefa em partes menores."
            )
            logger.warning(f"[stream] session={req.session_id} | {error_detail}")
            yield f"event: error\ndata: {json.dumps({'detail': error_detail})}\n\n"
        except Exception as e:
            # Sem isso, qualquer falha ao falar com o Ollama (não está rodando,
            # modelo não baixado, endereço errado) derrubava a conexão sem
            # explicação nenhuma pro navegador (aparecia só como erro de rede).
            logger.exception(f"[stream] session={req.session_id} | ERRO ao falar com o Ollama")
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
    transcript_for_display = None

    if message.strip():
        text_parts.append(message)

    if audio is not None:
        raw = await audio.read()
        _check_size(raw, audio.filename)
        transcript = media.process_audio(raw, suffix=_suffix(audio.filename, ".wav"))
        text_parts.append(f"[Transcrição do áudio]: {transcript}")
        transcript_for_display = transcript

    if video is not None:
        raw = await video.read()
        _check_size(raw, video.filename)
        result = media.process_video(raw, suffix=_suffix(video.filename, ".mp4"))
        note = f"[Vídeo: {result['frame_count']} frame(s)"
        if result["transcript"]:
            note += f", áudio transcrito: {result['transcript']}"
            transcript_for_display = result["transcript"]
        note += "] (nota: os frames de imagem não são enviados ao modelo local — só a transcrição do áudio)"
        text_parts.append(note)

    if not text_parts:
        raise HTTPException(status_code=400, detail="Envie ao menos texto ou áudio/vídeo.")

    result = _run_agent_turn(session_id, " ".join(text_parts))
    if transcript_for_display:
        result["transcript"] = transcript_for_display
    return result


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
