"""
Ferramentas do J.A.R.V.I.S. local.

Diferença importante em relação à versão na nuvem: `run_command` aqui
executa DE VERDADE, na sua máquina, assim que você aprova — não existe mais
"agente remoto" porque o servidor já É o seu PC. A aprovação continua
existindo (nunca executa sozinho, sem você confirmar), só que agora é
imediata em vez de esperar um agente separado buscar o comando.
"""

import base64
import io
import json
import os
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

import httpx
from PIL import Image, ImageGrab

import database as db
import embeddings
import google_calendar
import mouse_control
import smart_light
import word_control

APPS_CONFIG_PATH = Path(__file__).parent.parent / "config" / "apps_config.json"  # tools.py agora está em src/, config/ fica na raiz
PROJECTS_CONFIG_PATH = Path(__file__).parent.parent / "config" / "projects_config.json"

LINEAR_API_KEY = os.environ.get("LINEAR_API_KEY", "")
LINEAR_TEAM_ID = os.environ.get("LINEAR_TEAM_ID", "")
LINEAR_API_URL = "https://api.linear.app/graphql"


def capture_screen_base64(max_width: int = 1280) -> str:
    """
    Tira um screenshot da tela e devolve como JPEG em base64, redimensionado
    pra não gastar contexto/tokens à toa (uma tela 4K não precisa ir em
    resolução total pro modelo entender o que tem nela).
    """
    if sys.platform not in ("win32", "darwin"):
        raise RuntimeError(
            "Captura de tela só é suportada no Windows ou Mac (via PIL.ImageGrab). "
            f"Plataforma detectada: {sys.platform}."
        )

    img = ImageGrab.grab()
    real_width, real_height = img.width, img.height
    resized_width, resized_height = real_width, real_height

    if img.width > max_width:
        ratio = max_width / img.width
        resized_width = max_width
        resized_height = int(img.height * ratio)
        img = img.resize((resized_width, resized_height), Image.LANCZOS)

    # Guarda a proporção real<->redimensionada, pra clicar depois no lugar certo
    mouse_control.set_screenshot_scale(real_width, real_height, resized_width, resized_height)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _load_apps_config() -> dict:
    if not APPS_CONFIG_PATH.exists():
        return {}
    with open(APPS_CONFIG_PATH, encoding="utf-8") as f:
        data = json.load(f)
    data.pop("_comentario", None)
    return data

TOOLS = [
    {
        "name": "remember",
        "description": (
            "Salva um fato, preferência ou informação pessoal do usuário na memória de "
            "longo prazo, pra lembrar em conversas futuras (mesmo depois de reiniciar o "
            "JARVIS). USE quando o usuário disser algo como 'lembra que...', 'anota que...', "
            "'não esquece que...', ou mencionar uma preferência/fato sobre si mesmo de forma "
            "natural (ex: 'eu prefiro café sem açúcar', 'meu aniversário é dia X'). "
            "NÃO use pra fatos genéricos sem relação com o usuário, nem pra pedidos de ação "
            "(isso não é uma lista de tarefas, é memória de longo prazo)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "O fato a lembrar, escrito de forma clara e independente de contexto (ex: 'Usuário prefere café sem açúcar', não só 'sem açúcar').",
                },
                "category": {"type": "string", "description": "Categoria (pessoal, preferencia, projeto, trabalho...)."},
            },
            "required": ["content"],
        },
    },
    {
        "name": "recall",
        "description": (
            "Busca na memória de longo prazo por informações relevantes já salvas antes. "
            "USE sempre que o usuário perguntar algo que dependa de contexto pessoal dele "
            "(ex: 'o que eu prefiro?', 'você lembra do meu projeto X?', 'qual é minha "
            "preferência de Y?'), ou quando não tiver certeza se já sabe algo sobre o "
            "usuário e a resposta poderia mudar dependendo disso. Prefira chamar recall a "
            "assumir/inventar uma informação sobre o usuário que você não tem certeza."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Termos de busca, focados no assunto (ex: 'café' ou 'preferências de bebida')."}},
            "required": ["query"],
        },
    },
    {
        "name": "get_datetime",
        "description": (
            "Retorna a data e hora atuais do sistema. USE sempre que o usuário perguntar "
            "'que horas são', 'que dia é hoje', ou quando precisar saber a data/hora atual "
            "pra responder algo corretamente (ex: calcular quanto falta pra um evento). "
            "NÃO tente adivinhar a data/hora sozinho — sempre chame essa tool pra ter "
            "certeza, já que você não tem noção de tempo real sem ela."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "propose_command",
        "description": (
            "Propõe um comando de terminal genérico pra ser executado NESTE computador — "
            "NÃO executa na hora, cria um pedido pendente que precisa ser aprovado pelo "
            "usuário antes de rodar. USE pra ações no sistema que NÃO estão cobertas por "
            "outra tool mais específica (ex: listar arquivos de uma pasta, rodar um script "
            "próprio, mover/renomear arquivo, verificar espaço em disco). "
            "NÃO use pra abrir programas já configurados em apps_config.json — pra isso, "
            "use `open_app`, que é mais direto e não precisa de aprovação. Só caia aqui se "
            "`open_app` não cobrir o pedido."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "O comando de shell proposto, exato como seria digitado no terminal."},
                "explicacao": {"type": "string", "description": "O que esse comando faz, em português simples, pro usuário entender antes de aprovar."},
            },
            "required": ["command", "explicacao"],
        },
    },
    {
        "name": "write_word_document",
        "description": (
            "Abre o Microsoft Word e cria um novo documento com o conteúdo fornecido, salvando "
            "na pasta Documentos (ou outra pasta especificada). Só funciona no Windows com Word "
            "instalado. USE quando o usuário pedir explicitamente pra 'escrever um documento', "
            "'criar um Word', 'anotar isso no Word', etc — não use pra qualquer texto genérico, "
            "só quando o pedido for especificamente sobre um documento do Word. "
            "AÇÃO REAL E VISÍVEL (abre o Word na tela) — confirme o conteúdo com o usuário antes "
            "de chamar, a menos que ele já tenha ditado o texto completo explicitamente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "O texto a escrever no documento."},
                "filename": {"type": "string", "description": "Nome do arquivo (ex: 'anotacoes.docx')."},
            },
            "required": ["content"],
        },
    },
    {
        "name": "open_app",
        "description": (
            "Abre um programa/jogo/plataforma pré-configurado (ex: Steam, Discord, League of "
            "Legends, Chrome). Executa IMEDIATAMENTE, sem precisar de aprovação — é a forma "
            "PREFERIDA de abrir qualquer programa que esteja na lista configurada. USE sempre "
            "que o usuário disser 'abre o/a X' e X for um programa/jogo comum. Se não tiver "
            "certeza se está configurado, chame primeiro `list_available_apps`. Só use "
            "`propose_command` pra abrir algo se esse app não estiver na lista."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "app_name": {"type": "string", "description": "Nome do app/jogo/plataforma a abrir, como o usuário falou."},
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "abrir_projeto",
        "description": (
            "Abre uma 'rotina de projeto' pré-configurada — vários passos de uma vez (ex: abrir "
            "o VS Code numa pasta, ligar um servidor, abrir uma URL no navegador). MUITO mais "
            "confiável que usar `ver_tela`+`clicar_na_tela` pra isso, porque não depende de "
            "clique nenhum — só executa comandos já configurados. USE quando o usuário disser "
            "'abre o projeto X' ou 'abre meu ambiente de trabalho'. Se não tiver certeza do nome "
            "exato, chame `list_available_projects` primeiro."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome do projeto/rotina a abrir, como configurado."},
            },
            "required": ["nome"],
        },
    },
    {
        "name": "list_available_projects",
        "description": "Lista as rotinas de projeto já configuradas e prontas pra abrir por voz via `abrir_projeto`.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_available_apps",
        "description": (
            "Lista os apps/jogos/plataformas já configurados e prontos pra abrir por voz via "
            "`open_app`. USE quando o usuário perguntar 'quais apps você consegue abrir' ou "
            "quando você não tiver certeza se um app específico está configurado antes de "
            "tentar abrir com `open_app`."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "ver_tela",
        "description": (
            "Tira uma captura da tela atual do usuário e permite analisar visualmente o que "
            "está sendo exibido. USE quando o usuário pedir pra 'ver', 'olhar', 'descrever', "
            "'ler' ou entender algo que está na tela dele agora (ex: 'o que tem nessa janela?', "
            "'lê esse erro pra mim', 'o que você está vendo?'). Requer um modelo do Ollama com "
            "suporte a visão (ex: gemma4) — se o modelo atual não tiver visão, a captura "
            "funciona mas você não vai conseguir 'ver' de verdade; nesse caso, avise o usuário "
            "com clareza em vez de inventar o que estaria na tela."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "clicar_na_tela",
        "description": (
            "Move o mouse e clica numa posição da tela. AS COORDENADAS (x, y) DEVEM SER "
            "BASEADAS NA ÚLTIMA IMAGEM QUE VOCÊ VIU via `ver_tela` — sempre chame `ver_tela` "
            "primeiro pra saber onde as coisas estão antes de clicar. USE quando o usuário "
            "pedir pra clicar em algo específico, abrir um item dentro de um programa já "
            "aberto (ex: 'abre esse jogo na Steam', 'clica no botão X'). AÇÃO REAL E "
            "POTENCIALMENTE IRREVERSÍVEL — se não tiver certeza absoluta de onde clicar, "
            "chame `ver_tela` de novo em vez de arriscar um clique errado. NUNCA clique em "
            "botões de confirmação de compra, exclusão, ou envio de mensagem sem confirmação "
            "explícita do usuário antes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "Posição X, conforme vista na última captura de ver_tela."},
                "y": {"type": "integer", "description": "Posição Y, conforme vista na última captura de ver_tela."},
                "duplo_clique": {"type": "boolean", "description": "true pra clique duplo (ex: abrir um ícone). Padrão: false."},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "digitar_texto",
        "description": (
            "Digita um texto na posição atual do cursor/foco (onde quer que esteja clicado "
            "no momento). USE depois de clicar num campo de texto com `clicar_na_tela`, "
            "quando o usuário pedir pra escrever algo num campo específico de um programa. "
            "NÃO use pra digitar senhas ou dados sensíveis — o JARVIS nunca lida com "
            "credenciais (veja as regras sobre login mais abaixo)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"texto": {"type": "string", "description": "O texto a digitar."}},
            "required": ["texto"],
        },
    },
    {
        "name": "pressionar_tecla",
        "description": (
            "Pressiona uma tecla especial (ex: 'enter', 'esc', 'tab', 'delete'). USE pra "
            "confirmar um campo de texto (enter), fechar uma janela (esc), navegar entre "
            "campos (tab), etc — depois de `clicar_na_tela` ou `digitar_texto`."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"tecla": {"type": "string", "description": "Nome da tecla (enter, esc, tab, delete, space, etc)."}},
            "required": ["tecla"],
        },
    },
    {
        "name": "list_linear_teams",
        "description": (
            "Lista os times do Linear disponíveis, com seus IDs. USE antes de "
            "`create_linear_issue` se você não souber o team_id certo, ou se o usuário "
            "não especificar em qual time criar a issue."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_linear_issue",
        "description": (
            "Cria uma issue de verdade no Linear — AÇÃO REAL E IRREVERSÍVEL (não dá pra "
            "desfazer automaticamente). REGRA OBRIGATÓRIA: antes de chamar essa tool, mostre "
            "ao usuário em texto normal o título, a descrição e o time que você vai usar, e "
            "espere a confirmação explícita dele numa mensagem seguinte. NUNCA chame essa "
            "tool na mesma resposta em que você descreve o plano — só depois do usuário "
            "confirmar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Título da issue."},
                "description": {"type": "string", "description": "Descrição da issue (markdown), opcional."},
                "team_id": {"type": "string", "description": "ID do time. Se omitido, usa o padrão configurado."},
            },
            "required": ["title"],
        },
    },
    {
        "name": "list_calendar_events",
        "description": (
            "Lista os próximos eventos do Google Calendar do usuário. USE quando o usuário "
            "perguntar 'o que eu tenho hoje', 'minha agenda', 'meus próximos compromissos', "
            "etc. Requer que o Google Calendar já tenha sido configurado (veja o README) — "
            "se não estiver, a tool avisa isso claramente em vez de inventar eventos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "quantidade": {"type": "integer", "description": "Quantos eventos listar (padrão: 10)."},
            },
        },
    },
    {
        "name": "create_calendar_event",
        "description": (
            "Cria um evento novo no Google Calendar do usuário — AÇÃO REAL. REGRA OBRIGATÓRIA: "
            "confirme título, data/hora e duração com o usuário antes de chamar essa tool, na "
            "mensagem anterior, e só chame depois de confirmação explícita. Use `get_datetime` "
            "primeiro se precisar calcular uma data relativa (ex: 'amanhã às 15h')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Título do evento."},
                "start_iso": {"type": "string", "description": "Data/hora de início em formato ISO, ex: '2026-08-20T14:00:00'."},
                "duration_minutes": {"type": "integer", "description": "Duração em minutos (padrão: 60)."},
                "description": {"type": "string", "description": "Descrição opcional do evento."},
            },
            "required": ["title", "start_iso"],
        },
    },
    {
        "name": "controlar_luz",
        "description": (
            "Liga, desliga ou ajusta o brilho de uma lâmpada inteligente Tapo/Kasa configurada. "
            "USE quando o usuário pedir pra ligar/desligar/ajustar a luz. Se a lâmpada não "
            "estiver configurada ainda, a tool avisa isso claramente — não invente que "
            "funcionou."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "acao": {"type": "string", "enum": ["ligar", "desligar", "brilho"], "description": "Ação a realizar."},
                "brilho_percentual": {"type": "integer", "description": "Necessário só se acao='brilho'. De 1 a 100."},
            },
            "required": ["acao"],
        },
    },
]


def execute_tool(name: str, tool_input: dict) -> str:
    if name == "remember":
        memory_id = embeddings.add_memory_with_embedding(
            tool_input["content"], tool_input.get("category", "general")
        )
        return f"Memória salva (id={memory_id})."

    if name == "recall":
        results = embeddings.smart_search(tool_input["query"])
        if not results:
            return "Nenhuma memória relevante encontrada."
        return "\n".join(f"- {r['content']} (categoria: {r['category']})" for r in results)

    if name == "get_datetime":
        return datetime.now().strftime("%A, %d de %B de %Y, %H:%M")

    if name == "propose_command":
        command_id = db.create_pending_command(
            command=tool_input["command"], explicacao=tool_input.get("explicacao", "")
        )
        return (
            f"Comando registrado como pedido pendente (id={command_id}). "
            f"Precisa ser aprovado via POST /commands/{command_id}/approve antes de rodar."
        )

    if name == "write_word_document":
        try:
            path = word_control.write_word_document(
                content=tool_input["content"],
                filename=tool_input.get("filename", "documento_jarvis.docx"),
            )
            return f"Documento criado e salvo em: {path}"
        except Exception as e:
            return f"Erro ao criar documento no Word: {e}"

    if name == "open_app":
        return _open_app(tool_input["app_name"])

    if name == "abrir_projeto":
        return _abrir_projeto(tool_input["nome"])

    if name == "list_available_projects":
        projects = _load_projects_config()
        if not projects:
            return "Nenhum projeto configurado ainda em config/projects_config.json."
        return "Projetos disponíveis: " + ", ".join(
            f"{nome} ({info.get('descricao', 'sem descrição')})" for nome, info in projects.items()
        )

    if name == "clicar_na_tela":
        try:
            return mouse_control.click_at(
                x=tool_input["x"], y=tool_input["y"], double=tool_input.get("duplo_clique", False)
            )
        except Exception as e:
            return f"Erro ao clicar: {e}"

    if name == "digitar_texto":
        try:
            return mouse_control.type_text(tool_input["texto"])
        except Exception as e:
            return f"Erro ao digitar: {e}"

    if name == "pressionar_tecla":
        try:
            return mouse_control.press_key(tool_input["tecla"])
        except Exception as e:
            return f"Erro ao pressionar tecla: {e}"

    if name == "list_available_apps":
        apps = _load_apps_config()
        if not apps:
            return "Nenhum app configurado ainda em apps_config.json."
        return "Apps disponíveis: " + ", ".join(apps.keys())

    if name == "list_linear_teams":
        return _list_linear_teams()

    if name == "create_linear_issue":
        return _create_linear_issue(
            title=tool_input["title"],
            description=tool_input.get("description", ""),
            team_id=tool_input.get("team_id") or LINEAR_TEAM_ID,
        )

    if name == "list_calendar_events":
        return _list_calendar_events(tool_input.get("quantidade", 10))

    if name == "create_calendar_event":
        return _create_calendar_event(
            title=tool_input["title"],
            start_iso=tool_input["start_iso"],
            duration_minutes=tool_input.get("duration_minutes", 60),
            description=tool_input.get("description", ""),
        )

    if name == "controlar_luz":
        acao = tool_input["acao"]
        if acao == "ligar":
            return smart_light.turn_on()
        if acao == "desligar":
            return smart_light.turn_off()
        if acao == "brilho":
            return smart_light.set_brightness(tool_input.get("brilho_percentual", 100))
        return f"Ação de luz desconhecida: {acao}"

    return f"Ferramenta desconhecida: {name}"


def _list_calendar_events(quantidade: int) -> str:
    if not google_calendar.is_configured():
        return (
            "Google Calendar ainda não foi configurado. Rode "
            "'python scripts/setup_google_calendar.py' primeiro (veja o README)."
        )
    try:
        events = google_calendar.list_upcoming_events(max_results=quantidade)
    except Exception as e:
        return f"Erro ao acessar o Google Calendar: {e}"

    if not events:
        return "Nenhum evento próximo encontrado."
    return "\n".join(f"- {e['titulo']} ({e['inicio']} até {e['fim']})" for e in events)


def _create_calendar_event(title: str, start_iso: str, duration_minutes: int, description: str) -> str:
    if not google_calendar.is_configured():
        return (
            "Google Calendar ainda não foi configurado. Rode "
            "'python scripts/setup_google_calendar.py' primeiro (veja o README)."
        )
    try:
        result = google_calendar.create_event(title, start_iso, duration_minutes, description)
    except Exception as e:
        return f"Erro ao criar evento no Google Calendar: {e}"
    return f"Evento '{title}' criado com sucesso. Link: {result['link']}"


def execute_approved_command(command: str) -> tuple[str, str]:
    """Executa de verdade um comando já aprovado, nesta máquina. Retorna (status, output)."""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        output = ((result.stdout or "") + (result.stderr or "")).strip() or "(sem saída)"
        return "executed", output[:4000]
    except subprocess.TimeoutExpired:
        return "failed", "Timeout de 30s excedido."
    except Exception as e:
        return "failed", str(e)


def _load_projects_config() -> dict:
    if not PROJECTS_CONFIG_PATH.exists():
        return {}
    with open(PROJECTS_CONFIG_PATH, encoding="utf-8") as f:
        data = json.load(f)
    data.pop("_comentario", None)
    return data


def _abrir_projeto(nome: str) -> str:
    projects = _load_projects_config()
    if not projects:
        return "Nenhum projeto configurado ainda. Adicione entradas em config/projects_config.json primeiro."

    key = nome.strip().lower()
    match = None
    matched_name = None
    for proj_name, info in projects.items():
        if proj_name.lower() == key or key in proj_name.lower() or proj_name.lower() in key:
            match = info
            matched_name = proj_name
            break

    if not match:
        available = ", ".join(projects.keys())
        return f"Projeto '{nome}' não encontrado. Projetos disponíveis: {available}."

    passos = match.get("passos", [])
    resultados = []
    for passo in passos:
        tipo = passo.get("tipo")
        try:
            if tipo == "vscode":
                subprocess.Popen(["code", passo["caminho"]], shell=True)
                resultados.append(f"VS Code aberto em {passo['caminho']}")
            elif tipo == "comando":
                subprocess.Popen(passo["comando"], shell=True)
                resultados.append(f"Comando executado: {passo['comando']}")
            elif tipo == "url":
                webbrowser.open(passo["url"])
                resultados.append(f"Navegador aberto em {passo['url']}")
            elif tipo == "esperar":
                time.sleep(passo.get("segundos", 1))
                resultados.append(f"Aguardou {passo.get('segundos', 1)}s")
            else:
                resultados.append(f"Tipo de passo desconhecido: {tipo}")
        except Exception as e:
            resultados.append(f"Erro no passo '{tipo}': {e}")

    return f"Projeto '{matched_name}' aberto. Passos executados: " + "; ".join(resultados)


def _open_app(app_name: str) -> str:
    apps = _load_apps_config()
    if not apps:
        return "Nenhum app configurado ainda. Adicione entradas em apps_config.json primeiro."

    # Match exato, depois tolera variação de maiúsculas/minúsculas e espaços
    key = app_name.strip().lower()
    match = apps.get(key)
    if not match:
        for name_key in apps:
            if name_key.lower() == key or key in name_key.lower() or name_key.lower() in key:
                match = apps[name_key]
                break

    if not match:
        available = ", ".join(apps.keys())
        return (
            f"'{app_name}' não está configurado. Apps disponíveis: {available}. "
            f"Pra adicionar, edite apps_config.json."
        )

    try:
        subprocess.Popen(match["comando"], shell=True)
        return f"Abrindo {app_name}..."
    except Exception as e:
        return f"Erro ao tentar abrir '{app_name}': {e}"


def _linear_request(query: str, variables: dict) -> dict:
    if not LINEAR_API_KEY:
        raise RuntimeError("LINEAR_API_KEY não configurada no .env.")
    response = httpx.post(
        LINEAR_API_URL,
        json={"query": query, "variables": variables},
        headers={"Authorization": LINEAR_API_KEY, "Content-Type": "application/json"},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    if "errors" in data:
        raise RuntimeError(f"Linear retornou erro: {data['errors']}")
    return data["data"]


def _list_linear_teams() -> str:
    try:
        data = _linear_request("query { teams { nodes { id name key } } }", {})
    except Exception as e:
        return f"Erro ao listar times do Linear: {e}"
    teams = data["teams"]["nodes"]
    if not teams:
        return "Nenhum time encontrado no Linear."
    return "\n".join(f"- {t['name']} (key: {t['key']}, id: {t['id']})" for t in teams)


def _create_linear_issue(title: str, description: str, team_id: str) -> str:
    if not LINEAR_API_KEY:
        return "LINEAR_API_KEY não configurada no .env."
    if not team_id:
        return "Time do Linear não definido. Use list_linear_teams ou configure LINEAR_TEAM_ID no .env."
    mutation = """
    mutation IssueCreate($input: IssueCreateInput!) {
      issueCreate(input: $input) { success issue { id identifier title url } }
    }
    """
    try:
        data = _linear_request(mutation, {"input": {"title": title, "description": description, "teamId": team_id}})
    except Exception as e:
        return f"Erro ao criar issue no Linear: {e}"
    result = data["issueCreate"]
    if not result["success"]:
        return "Linear recusou a criação da issue."
    issue = result["issue"]
    return f"Issue criada: {issue['identifier']} — {issue['title']} ({issue['url']})"
