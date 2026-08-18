"""
Ferramentas do J.A.R.V.I.S. local.

Diferença importante em relação à versão na nuvem: `run_command` aqui
executa DE VERDADE, na sua máquina, assim que você aprova — não existe mais
"agente remoto" porque o servidor já É o seu PC. A aprovação continua
existindo (nunca executa sozinho, sem você confirmar), só que agora é
imediata em vez de esperar um agente separado buscar o comando.
"""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

import httpx

import database as db
import embeddings
import word_control

APPS_CONFIG_PATH = Path(__file__).parent / "config" / "apps_config.json"

LINEAR_API_KEY = os.environ.get("LINEAR_API_KEY", "")
LINEAR_TEAM_ID = os.environ.get("LINEAR_TEAM_ID", "")
LINEAR_API_URL = "https://api.linear.app/graphql"


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
        "description": "Salva um fato ou preferência importante sobre o usuário na memória de longo prazo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "O fato a lembrar."},
                "category": {"type": "string", "description": "Categoria (pessoal, preferencia, projeto...)."},
            },
            "required": ["content"],
        },
    },
    {
        "name": "recall",
        "description": "Busca na memória de longo prazo por informações relevantes.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Termos de busca."}},
            "required": ["query"],
        },
    },
    {
        "name": "get_datetime",
        "description": "Retorna a data e hora atuais.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "propose_command",
        "description": (
            "Propõe um comando de terminal para ser executado NESTE computador. NÃO executa "
            "na hora — cria um pedido pendente que precisa ser aprovado via API "
            "(POST /commands/{id}/approve) antes de rodar. Use pra ações reais no sistema "
            "(listar arquivos, rodar script, abrir programa, etc)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "O comando de shell proposto."},
                "explicacao": {"type": "string", "description": "O que esse comando faz, em português simples."},
            },
            "required": ["command", "explicacao"],
        },
    },
    {
        "name": "write_word_document",
        "description": (
            "Abre o Microsoft Word e cria um novo documento com o conteúdo fornecido, salvando "
            "na pasta Documentos (ou outra pasta especificada). Só funciona no Windows com Word "
            "instalado. AÇÃO REAL — confirme o conteúdo com o usuário antes de chamar, a menos "
            "que ele já tenha dado o texto completo explicitamente."
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
            "Abre um programa/plataforma pré-configurado (ex: Steam, Discord, League of Legends). "
            "Executa IMEDIATAMENTE, sem precisar de aprovação — só funciona para apps já cadastrados "
            "em apps_config.json. Se o app pedido não estiver na lista, informe ao usuário que ele "
            "precisa ser adicionado no arquivo de configuração primeiro."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "app_name": {"type": "string", "description": "Nome do app/jogo/plataforma a abrir."},
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "list_available_apps",
        "description": "Lista os apps/jogos/plataformas já configurados e prontos pra abrir por voz.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_linear_teams",
        "description": "Lista os times do Linear disponíveis, com seus IDs.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_linear_issue",
        "description": (
            "Cria uma issue de verdade no Linear. AÇÃO REAL — mostre título/descrição/time "
            "ao usuário e espere confirmação explícita antes de chamar."
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

    return f"Ferramenta desconhecida: {name}"


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
