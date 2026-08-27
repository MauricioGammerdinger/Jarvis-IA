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

import ai_tokens
import calendar_hub
import code_editor
import git_projects
import database as db
import email_hub
import embeddings
import google_calendar
import morning_digest
import mouse_control
import news_radar
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


def save_app_config(nome: str, comando: str, observacao: str = "") -> None:
    """Adiciona (ou atualiza) uma entrada em apps_config.json, sem apagar as outras."""
    if APPS_CONFIG_PATH.exists():
        with open(APPS_CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}
    data[nome.strip().lower()] = {"comando": comando, "observacao": observacao}
    with open(APPS_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def delete_app_config(nome: str) -> bool:
    """Remove uma entrada de apps_config.json. Devolve True se removeu, False se não existia."""
    if not APPS_CONFIG_PATH.exists():
        return False
    with open(APPS_CONFIG_PATH, encoding="utf-8") as f:
        data = json.load(f)
    key = nome.strip().lower()
    if key not in data:
        return False
    del data[key]
    with open(APPS_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return True

TOOLS = [
    {
        "name": "remember",
        "description": (
            "Salva um fato, preferência ou informação pessoal do usuário na memória de "
            "longo prazo, pra lembrar em conversas futuras (mesmo depois de reiniciar o "
            "JARVIS). USE quando o usuário disser algo como 'lembra que...', 'anota que...', "
            "'não esquece que...', ou mencionar uma preferência/fato sobre si mesmo de forma "
            "natural (ex: 'eu prefiro café sem açúcar', 'meu aniversário é dia X'). "
            "CATEGORIAS ESPECIAIS DO SECOND BRAIN (entram em TODA conversa, sempre — use "
            "esses nomes exatos quando aplicável): voce, metas, carreira, projetos, "
            "financas, aprendizado, saude, relacoes. Pra qualquer outra coisa, use uma "
            "categoria livre (ex: preferencia). NÃO use pra fatos genéricos sem relação com "
            "o usuário, nem pra pedidos de ação (isso não é uma lista de tarefas)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "O fato a lembrar, escrito de forma clara e independente de contexto (ex: 'Usuário prefere café sem açúcar', não só 'sem açúcar').",
                },
                "category": {"type": "string", "description": "Categoria do Second Brain (voce/metas/carreira/projetos/financas/aprendizado/saude/relacoes) ou uma categoria livre."},
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
    {
        "name": "iniciar_configuracao_second_brain",
        "description": (
            "Inicia a entrevista guiada de configuração do Second Brain. USE quando o usuário "
            "pedir explicitamente pra 'configurar', 'montar' ou 'começar' o Second Brain. Essa "
            "tool devolve as instruções exatas de como conduzir a entrevista — siga elas à "
            "risca depois de chamar."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cadastrar_app",
        "description": (
            "Cadastra um app/programa novo na lista de coisas que o JARVIS pode abrir por voz "
            "(open_app). USE quando `open_app` falhar avisando que o app não está configurado "
            "E o usuário te der (ou você souber) o comando certo pra abrir esse programa. NÃO "
            "invente um comando — se não souber o comando certo, pergunte ao usuário (ex: "
            "'qual é o comando ou caminho do executável desse programa?') antes de chamar essa "
            "tool. Depois de cadastrar, o app já pode ser aberto normalmente por open_app."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome do app, como o usuário vai falar pra abrir (ex: 'photoshop')."},
                "comando": {"type": "string", "description": "Comando de shell pra abrir (ex: 'start photoshop', ou o caminho completo do .exe entre aspas)."},
            },
            "required": ["nome", "comando"],
        },
    },
    {
        "name": "ver_agenda_hoje",
        "description": "Lista os eventos de HOJE, de todas as agendas configuradas, mesclados em ordem de horário.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "ver_agenda_semana",
        "description": "Lista os eventos dos próximos 7 dias, de todas as agendas configuradas.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "proximo_compromisso",
        "description": "Mostra o PRÓXIMO evento a partir de agora, com contagem regressiva (ex: 'em 2h 15min').",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cadastrar_agenda",
        "description": (
            "Adiciona uma agenda do Google pra ser mesclada na Central de Agenda. Precisa do "
            "'endereço secreto em formato iCal' — o usuário pega em: Google Agenda → "
            "Configurações → clica na agenda na lista → 'Integrar agenda' → copia o link. "
            "Se o usuário não souber pegar esse link, explique o caminho acima."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome pra identificar essa agenda (ex: 'Pessoal', 'Trabalho')."},
                "cor": {"type": "string", "description": "Cor em hex pra diferenciar visualmente (ex: '#5fe3f0'). Se não souber, use uma cor razoável."},
                "ics_url": {"type": "string", "description": "O link 'endereço secreto em formato iCal' completo."},
            },
            "required": ["nome", "ics_url"],
        },
    },
    {
        "name": "listar_agendas",
        "description": "Lista as agendas do Google já configuradas na Central de Agenda.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "ver_emails",
        "description": (
            "Mostra os e-mails já triados, filtrados por balde. USE 'acao' quando o usuário "
            "perguntar o que precisa responder/fazer, 'info' pra coisas que só precisa saber, "
            "'ruido' pra ver o que foi ignorado, ou não passe o parâmetro pra ver um resumo dos "
            "3 baldes de uma vez."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"balde": {"type": "string", "enum": ["acao", "info", "ruido"], "description": "Qual balde ver. Se omitido, mostra resumo dos 3."}},
        },
    },
    {
        "name": "atualizar_emails",
        "description": "Força buscar e-mails novos agora, em vez de esperar a atualização automática.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cadastrar_conta_email",
        "description": (
            "Adiciona uma conta de e-mail pra Central de E-mails ler via IMAP. IMPORTANTE: "
            "NUNCA é a senha normal da conta — é uma 'senha de app' de 16 letras, gerada em "
            "myaccount.google.com/apppasswords (precisa ativar verificação em 2 etapas "
            "primeiro). Se o usuário não souber gerar isso, explique o caminho."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "apelido": {"type": "string", "description": "Nome pra identificar essa conta (ex: 'Pessoal', 'Trabalho')."},
                "cor": {"type": "string", "description": "Cor em hex pra diferenciar visualmente."},
                "host": {"type": "string", "description": "Servidor IMAP (ex: 'imap.gmail.com')."},
                "usuario": {"type": "string", "description": "O e-mail completo (ex: 'nome@gmail.com')."},
                "senha_app": {"type": "string", "description": "A senha de app de 16 letras (NUNCA a senha normal)."},
            },
            "required": ["apelido", "host", "usuario", "senha_app"],
        },
    },
    {
        "name": "listar_contas_email",
        "description": "Lista as contas de e-mail já configuradas na Central de E-mails.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "ver_noticias",
        "description": "Mostra as manchetes mais recentes. Se não passar assunto, mostra de todos os assuntos configurados.",
        "input_schema": {
            "type": "object",
            "properties": {"assunto": {"type": "string", "description": "Assunto específico. Se omitido, mostra todos."}},
        },
    },
    {
        "name": "gerenciar_assuntos_noticia",
        "description": "Adiciona ou remove um assunto do Radar de Notícias.",
        "input_schema": {
            "type": "object",
            "properties": {
                "acao": {"type": "string", "enum": ["adicionar", "remover", "listar"]},
                "assunto": {"type": "string", "description": "Necessário pra 'adicionar'/'remover'."},
            },
            "required": ["acao"],
        },
    },
    {
        "name": "descobrir_fontes_noticia",
        "description": (
            "Sugere sites/blogs conhecidos de um nicho E valida CADA UM de verdade (checa se "
            "o RSS existe e funciona, não confia só na sugestão do modelo). Use quando o "
            "usuário pedir pra encontrar fontes/sites de um assunto específico, não só buscar "
            "por palavra-chave."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"nicho": {"type": "string", "description": "O nicho/assunto (ex: 'inteligência artificial', 'fitness')."}},
            "required": ["nicho"],
        },
    },
    {
        "name": "cadastrar_fonte_noticia",
        "description": "Cadastra uma fonte RSS específica já validada (use depois de `descobrir_fontes_noticia` confirmar que funciona).",
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome curto da fonte."},
                "feed_url": {"type": "string", "description": "URL do feed RSS, já validada."},
            },
            "required": ["nome", "feed_url"],
        },
    },
    {
        "name": "resumir_noticia",
        "description": (
            "Abre um link de notícia de verdade e faz um resumo aprofundado: manchete + 5 "
            "bullets + por que isso importa. USE quando o usuário pedir pra entender melhor "
            "uma manchete específica, não só ver o título."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"link": {"type": "string", "description": "O link do artigo (geralmente vem de `ver_noticias`)."}},
            "required": ["link"],
        },
    },
    {
        "name": "narrar_noticias",
        "description": (
            "Compõe uma narração falada natural das manchetes atuais (não é só ler uma lista "
            "de títulos, é um texto corrido). USE quando o usuário pedir pra 'ouvir' ou 'narrar' "
            "as notícias, a qualquer hora do dia (diferente do Morning Digest, que só roda de manhã)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"assunto": {"type": "string", "description": "Assunto específico. Se omitido, narra de todos os assuntos configurados."}},
        },
    },
    {
        "name": "configurar_horario_noticias",
        "description": "Define um horário fixo do dia pra gerar a narração das notícias automaticamente (além da atualização a cada 30min).",
        "input_schema": {
            "type": "object",
            "properties": {"hora": {"type": "integer", "description": "Hora do dia, 0-23 (ex: 8 pras 8h da manhã)."}},
            "required": ["hora"],
        },
    },
    {
        "name": "gerar_morning_digest",
        "description": (
            "Gera o briefing matinal (Morning Digest) — junta agenda de hoje, e-mails que "
            "pedem ação, manchetes, clima e uma meta do Second Brain numa fala natural. USE "
            "quando o usuário disser algo como 'bom dia', 'me dá um resumo do dia', ou pedir "
            "o digest diretamente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"cidade_clima": {"type": "string", "description": "Cidade pra buscar o clima (opcional)."}},
        },
    },
    {
        "name": "ler_arquivo_codigo",
        "description": (
            "Lê o conteúdo de um arquivo de código, de qualquer pasta do PC. USE quando o "
            "usuário pedir pra ver/analisar um arquivo, ou antes de editar (pra saber o que "
            "já existe lá)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"caminho": {"type": "string", "description": "Caminho completo do arquivo."}},
            "required": ["caminho"],
        },
    },
    {
        "name": "editar_arquivo_codigo",
        "description": (
            "Sobrescreve um arquivo de código com um conteúdo novo — AÇÃO REAL E IMEDIATA, "
            "sem pedir confirmação (o usuário decidiu assim, pra ver a mudança acontecer ao "
            "vivo no VS Code). Um backup automático do conteúdo anterior é sempre feito antes. "
            "Pastas do sistema operacional (Windows, Program Files, AppData) são sempre "
            "bloqueadas. IMPORTANTE: sempre releia o arquivo com `ler_arquivo_codigo` antes de "
            "editar, pra saber o conteúdo completo atual — nunca sobrescreva baseado em "
            "suposição do que está lá."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "caminho": {"type": "string", "description": "Caminho completo do arquivo."},
                "novo_conteudo": {"type": "string", "description": "O conteúdo COMPLETO novo do arquivo (substitui tudo)."},
            },
            "required": ["caminho", "novo_conteudo"],
        },
    },
    {
        "name": "listar_pasta_codigo",
        "description": "Lista os arquivos e subpastas de uma pasta, pra explorar a estrutura de um projeto.",
        "input_schema": {
            "type": "object",
            "properties": {"caminho": {"type": "string", "description": "Caminho completo da pasta."}},
            "required": ["caminho"],
        },
    },
    {
        "name": "cadastrar_projeto_codigo",
        "description": "Cadastra um projeto de código (pasta com repositório git) pra aparecer no Painel de Agentes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome curto do projeto (ex: 'Gatolíngua')."},
                "caminho": {"type": "string", "description": "Caminho completo da pasta do projeto."},
            },
            "required": ["nome", "caminho"],
        },
    },
    {
        "name": "status_git_projeto",
        "description": "Mostra o status git de um projeto: mudanças pendentes, último commit, se está sincronizado com o GitHub.",
        "input_schema": {
            "type": "object",
            "properties": {"nome_ou_caminho": {"type": "string", "description": "Nome de um projeto já cadastrado, ou o caminho completo direto."}},
            "required": ["nome_ou_caminho"],
        },
    },
    {
        "name": "registrar_uso_ia",
        "description": "Registra uma chamada de API de IA (custo pago por uso) — data, projeto, modelo, tokens de entrada e saída. Calcula o custo automaticamente pela tabela de preços.",
        "input_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "string", "description": "Data no formato YYYY-MM-DD. Se omitido, usa hoje."},
                "projeto": {"type": "string", "description": "Nome do projeto/app que fez a chamada."},
                "modelo": {"type": "string", "description": "Nome do modelo (ex: 'claude-sonnet-4', 'gpt-4o')."},
                "input_tokens": {"type": "integer"},
                "output_tokens": {"type": "integer"},
            },
            "required": ["projeto", "modelo", "input_tokens", "output_tokens"],
        },
    },
    {
        "name": "ver_custo_ia",
        "description": "Mostra o gasto de API de IA no mês, % do orçamento usado, projeção até o fim do mês, e o custo total (API + assinaturas).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "definir_orcamento_ia",
        "description": "Define o orçamento mensal em dólares pra gasto de API de IA.",
        "input_schema": {
            "type": "object",
            "properties": {"valor_usd": {"type": "number"}},
            "required": ["valor_usd"],
        },
    },
    {
        "name": "definir_preco_modelo_ia",
        "description": "Adiciona ou atualiza o preço de um modelo na tabela (US$ por 1 milhão de tokens).",
        "input_schema": {
            "type": "object",
            "properties": {
                "modelo": {"type": "string"},
                "preco_input": {"type": "number", "description": "US$ por 1M tokens de entrada."},
                "preco_output": {"type": "number", "description": "US$ por 1M tokens de saída."},
            },
            "required": ["modelo", "preco_input", "preco_output"],
        },
    },
    {
        "name": "cadastrar_assinatura_ia",
        "description": "Cadastra uma assinatura de IA (Claude Pro/Max, ChatGPT Plus, Cursor, etc) pra acompanhar a cota.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string"},
                "unidade": {"type": "string", "enum": ["messages", "requests", "credits", "tokens"]},
                "limite": {"type": "number", "description": "Limite por ciclo, na unidade escolhida."},
                "tipo_reset": {"type": "string", "enum": ["rolling", "daily", "monthly"]},
                "reset_a_cada_horas": {"type": "number", "description": "Obrigatório se tipo_reset='rolling' (ex: 5 pras janelas do Claude)."},
                "custo_mensal_usd": {"type": "number", "description": "Custo fixo mensal do plano (opcional, soma no custo total)."},
            },
            "required": ["nome", "unidade", "limite", "tipo_reset"],
        },
    },
    {
        "name": "registrar_uso_assinatura",
        "description": "Soma uso numa assinatura já cadastrada (ex: '+1 mensagem'). USE quando o usuário disser algo como 'gastei mais uma mensagem do Claude'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string"},
                "quantidade": {"type": "number", "description": "Quanto somar (padrão 1)."},
            },
            "required": ["nome"],
        },
    },
    {
        "name": "ver_assinaturas_ia",
        "description": "Mostra o estado de todas as assinaturas: cota usada, restante, contagem regressiva até o reset, e se a projeção indica que vai estourar antes do reset.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "registrar_compromisso",
        "description": (
            "Guarda um compromisso/promessa que o usuário assumiu na conversa (ex: 'vou terminar "
            "X até sexta'). USE sempre que notar o usuário se comprometendo com algo, mesmo sem "
            "ele pedir explicitamente pra anotar — o JARVIS cobra isso sozinho depois, perto do "
            "prazo, sem precisar ser perguntado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "texto": {"type": "string", "description": "O compromisso, resumido (ex: 'Terminar o relatório do cliente X')."},
                "prazo": {"type": "string", "description": "Data/hora ISO do prazo, se houver (ex: '2026-08-29T18:00:00'). Omitir se não tiver prazo definido."},
            },
            "required": ["texto"],
        },
    },
    {
        "name": "listar_compromissos",
        "description": "Lista os compromissos guardados, com prazo e status.",
        "input_schema": {
            "type": "object",
            "properties": {"status": {"type": "string", "enum": ["pendente", "concluido"], "description": "Filtra por status. Omitir pra ver todos."}},
        },
    },
    {
        "name": "concluir_compromisso",
        "description": "Marca um compromisso como concluído.",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "integer", "description": "ID do compromisso (veja em listar_compromissos)."}},
            "required": ["id"],
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

    if name == "iniciar_configuracao_second_brain":
        return (
            "Comece a entrevista agora. Explique rapidamente que você vai perguntar sobre "
            "8 áreas da vida da pessoa, uma por vez, e que ela pode dizer 'pula' pra pular "
            "qualquer uma. Depois, faça a PRIMEIRA pergunta, sobre a área 'voce': pergunte "
            "quem ela é, idade, o que faz, onde mora. NÃO pergunte todas as áreas de uma vez "
            "— só essa primeira. Depois que ela responder, salve com `remember` (category="
            "'voce') e siga pra próxima área nessa ordem: metas, carreira, projetos, "
            "financas, aprendizado, saude, relacoes — sempre uma pergunta por vez, esperando "
            "a resposta antes de continuar. Se ela mencionar vários itens numa área (ex: "
            "vários projetos), salve uma memória separada pra cada. No final das 8 áreas, "
            "resuma o que foi salvo."
        )

    if name == "cadastrar_app":
        try:
            save_app_config(tool_input["nome"], tool_input["comando"])
            return f"App '{tool_input['nome']}' cadastrado com sucesso. Já pode ser aberto normalmente."
        except Exception as e:
            return f"Erro ao cadastrar o app: {e}"

    if name == "ver_agenda_hoje":
        return _format_agenda(calendar_hub.get_today_events())

    if name == "ver_agenda_semana":
        return _format_agenda(calendar_hub.get_merged_events(days_ahead=7))

    if name == "proximo_compromisso":
        proximo = calendar_hub.get_next_event()
        if not proximo:
            return "Nenhum compromisso encontrado nos próximos 7 dias."
        return f"{proximo['titulo']} às {proximo['inicio_display']} — daqui a {proximo['countdown']}."

    if name == "cadastrar_agenda":
        calendar_hub.add_calendar(tool_input["nome"], tool_input.get("cor", "#5fe3f0"), tool_input["ics_url"])
        return f"Agenda '{tool_input['nome']}' cadastrada. Já entra na próxima consulta de agenda."

    if name == "listar_agendas":
        agendas = calendar_hub.load_calendars_config()
        if not agendas:
            return "Nenhuma agenda configurada ainda."
        return "Agendas configuradas: " + ", ".join(a["nome"] for a in agendas)

    if name == "ver_emails":
        resultado = email_hub.get_triaged_emails()
        balde = tool_input.get("balde")
        if balde:
            itens = resultado.get(balde, [])
            if not itens:
                return f"Nenhum e-mail no balde '{balde}'."
            return f"E-mails em '{balde}':\n" + "\n".join(f"- {e['remetente']}: {e['assunto']} ({e['resumo']})" for e in itens)
        return (
            f"Resumo: {len(resultado['acao'])} pedindo ação, "
            f"{len(resultado['info'])} informativo(s), {len(resultado['ruido'])} ruído."
        )

    if name == "atualizar_emails":
        resultado = email_hub.get_triaged_emails()
        return f"Atualizado: {len(resultado['acao'])} pedindo ação, {len(resultado['info'])} informativo(s), {len(resultado['ruido'])} ruído."

    if name == "cadastrar_conta_email":
        erro = email_hub.add_email_account(
            tool_input["apelido"], tool_input.get("cor", "#5fe3f0"), tool_input["host"],
            tool_input["usuario"], tool_input["senha_app"],
        )
        if erro:
            return erro
        return f"Conta '{tool_input['apelido']}' cadastrada com sucesso."

    if name == "listar_contas_email":
        contas = email_hub.load_email_accounts()
        if not contas:
            return "Nenhuma conta de e-mail configurada ainda."
        return "Contas configuradas: " + ", ".join(c["apelido"] for c in contas)

    if name == "ver_noticias":
        assunto = tool_input.get("assunto")
        if assunto:
            resultado = news_radar.fetch_headlines(assunto)
            if "erro" in resultado:
                return f"Erro ao buscar notícias de '{assunto}': {resultado['erro']}"
            return f"Manchetes de '{assunto}':\n" + "\n".join(f"- {h['titulo']} ({h['tempo_relativo']})" for h in resultado["manchetes"])
        todos = news_radar.get_all_headlines()
        if not todos:
            return "Nenhum assunto configurado no Radar de Notícias ainda."
        partes = []
        for n in todos:
            if "erro" in n:
                partes.append(f"{n['assunto']}: erro ao buscar")
            else:
                partes.append(f"{n['assunto']}: " + "; ".join(h["titulo"] for h in n["manchetes"][:2]))
        return "\n".join(partes)

    if name == "gerenciar_assuntos_noticia":
        acao = tool_input["acao"]
        if acao == "listar":
            assuntos = news_radar.load_topics()
            return "Assuntos configurados: " + ", ".join(assuntos) if assuntos else "Nenhum assunto configurado."
        if acao == "adicionar":
            news_radar.add_topic(tool_input["assunto"])
            return f"Assunto '{tool_input['assunto']}' adicionado ao Radar de Notícias."
        if acao == "remover":
            removido = news_radar.remove_topic(tool_input["assunto"])
            return f"Assunto '{tool_input['assunto']}' removido." if removido else f"Assunto '{tool_input['assunto']}' não estava configurado."
        return f"Ação desconhecida: {acao}"

    if name == "descobrir_fontes_noticia":
        resultados = news_radar.discover_and_validate_sources(tool_input["nicho"])
        if not resultados:
            return "Não consegui sugerir nenhuma fonte pra esse nicho."
        validas = [r for r in resultados if r["valido"]]
        invalidas = [r for r in resultados if not r["valido"]]
        partes = [f"✓ {r['site']} (feed: {r['feed_url']}, exemplo: \"{r.get('exemplo_titulo', '')}\")" for r in validas]
        partes += [f"✗ {r['site']} — {r.get('motivo', 'não validado')}" for r in invalidas]
        return "\n".join(partes)

    if name == "cadastrar_fonte_noticia":
        news_radar.add_source(tool_input["nome"], tool_input["feed_url"])
        return f"Fonte '{tool_input['nome']}' cadastrada."

    if name == "resumir_noticia":
        resumo = news_radar.summarize_article(tool_input["link"])
        if "erro" in resumo:
            return resumo["erro"]
        bullets = "\n".join(f"- {b}" for b in resumo.get("bullets", []))
        return f"{resumo.get('manchete', '')}\n\n{bullets}\n\nPor que importa: {resumo.get('por_que_importa', '')}"

    if name == "narrar_noticias":
        return news_radar.narrate_news(assunto=tool_input.get("assunto"))

    if name == "configurar_horario_noticias":
        news_radar.set_narration_hour(tool_input["hora"])
        return f"Narração automática das notícias configurada pras {tool_input['hora']}h."

    if name == "gerar_morning_digest":
        resultado = morning_digest.generate_digest(cidade_clima=tool_input.get("cidade_clima"))
        return resultado["texto"]

    if name == "ler_arquivo_codigo":
        return code_editor.read_file(tool_input["caminho"])

    if name == "editar_arquivo_codigo":
        return code_editor.write_file(tool_input["caminho"], tool_input["novo_conteudo"])

    if name == "listar_pasta_codigo":
        return code_editor.list_directory(tool_input["caminho"])

    if name == "cadastrar_projeto_codigo":
        git_projects.add_code_project(tool_input["nome"], tool_input["caminho"])
        return f"Projeto '{tool_input['nome']}' cadastrado. Já aparece no Painel de Agentes."

    if name == "status_git_projeto":
        alvo = tool_input["nome_ou_caminho"]
        projetos = git_projects.load_code_projects()
        caminho = next((p["caminho"] for p in projetos if p["nome"].lower() == alvo.lower()), alvo)
        status = git_projects.get_git_status(caminho)
        if "erro" in status:
            return status["erro"]
        return (
            f"Branch '{status['branch']}', {status['mudancas_pendentes']} mudança(s) pendente(s). "
            f"Último commit: {status['commit_msg']} ({status['commit_relative']}). "
            f"{status['ahead']} commit(s) à frente, {status['behind']} atrás do remoto."
        )

    if name == "registrar_uso_ia":
        import datetime as dt_module
        data = tool_input.get("data") or dt_module.date.today().isoformat()
        resultado = ai_tokens.register_usage(data, tool_input["projeto"], tool_input["modelo"], tool_input["input_tokens"], tool_input["output_tokens"])
        return f"Uso registrado: {tool_input['input_tokens']} tokens de entrada + {tool_input['output_tokens']} de saída, custo de ${resultado['custo']:.4f}."

    if name == "ver_custo_ia":
        resumo = ai_tokens.get_api_summary()
        total = ai_tokens.get_total_ai_cost_this_month()
        return (
            f"Gasto de API este mês: ${resumo['total_gasto']:.2f} de ${resumo['orcamento']:.2f} "
            f"({resumo['pct_orcamento']:.1f}% do orçamento). Projeção até o fim do mês: ${resumo['projecao_fim_mes']:.2f}. "
            f"{'⚠ Já estourou o orçamento!' if resumo['estourou'] else ''} "
            f"Custo total de IA (API + assinaturas): ${total['total']:.2f}."
        )

    if name == "definir_orcamento_ia":
        ai_tokens.update_config(budget_monthly_usd=tool_input["valor_usd"])
        return f"Orçamento mensal de IA definido em ${tool_input['valor_usd']:.2f}."

    if name == "definir_preco_modelo_ia":
        ai_tokens.set_model_price(tool_input["modelo"], tool_input["preco_input"], tool_input["preco_output"])
        return f"Preço de '{tool_input['modelo']}' definido: ${tool_input['preco_input']}/1M entrada, ${tool_input['preco_output']}/1M saída."

    if name == "cadastrar_assinatura_ia":
        try:
            ai_tokens.add_subscription(
                tool_input["nome"], tool_input["unidade"], tool_input["limite"], tool_input["tipo_reset"],
                reset_a_cada_horas=tool_input.get("reset_a_cada_horas"), custo_mensal_usd=tool_input.get("custo_mensal_usd", 0),
            )
            return f"Assinatura '{tool_input['nome']}' cadastrada."
        except ValueError as e:
            return str(e)

    if name == "registrar_uso_assinatura":
        try:
            sub = ai_tokens.increment_subscription(tool_input["nome"], tool_input.get("quantidade", 1))
            return f"'{tool_input['nome']}' agora em {sub['usado']:.0f}/{sub['limite']:.0f} {sub['unidade']}."
        except ValueError as e:
            return str(e)

    if name == "ver_assinaturas_ia":
        snapshot = ai_tokens.get_subscriptions_snapshot()
        if not snapshot:
            return "Nenhuma assinatura cadastrada ainda."
        partes = []
        for s in snapshot:
            aviso = " ⚠ vai estourar antes do reset!" if s["projecao_estoura"] else ""
            partes.append(
                f"{s['nome']}: {s['usado']:.0f}/{s['limite']:.0f} {s['unidade_label']} "
                f"({s['usado_pct']:.0f}%), reseta em {ai_tokens.format_countdown(s['segundos_ate_reset'])}.{aviso}"
            )
        return "\n".join(partes)

    if name == "registrar_compromisso":
        commitment_id = db.add_commitment(tool_input["texto"], tool_input.get("prazo"))
        prazo_txt = f" (prazo: {tool_input['prazo']})" if tool_input.get("prazo") else " (sem prazo definido)"
        return f"Compromisso #{commitment_id} guardado: '{tool_input['texto']}'{prazo_txt}. Vou cobrar isso sozinho perto do prazo."

    if name == "listar_compromissos":
        compromissos = db.list_commitments(tool_input.get("status"))
        if not compromissos:
            return "Nenhum compromisso encontrado."
        partes = []
        for c in compromissos:
            prazo_txt = f" — prazo: {c['prazo']}" if c["prazo"] else ""
            partes.append(f"#{c['id']} [{c['status']}] {c['texto']}{prazo_txt}")
        return "\n".join(partes)

    if name == "concluir_compromisso":
        sucesso = db.complete_commitment(tool_input["id"])
        return f"Compromisso #{tool_input['id']} marcado como concluído!" if sucesso else f"Compromisso #{tool_input['id']} não encontrado."

    return f"Ferramenta desconhecida: {name}"


def _format_agenda(eventos: list[dict]) -> str:
    if not eventos:
        return "Nenhum evento encontrado."
    linhas = []
    for e in eventos:
        if "erro" in e:
            linhas.append(f"⚠ {e['erro']}")
        else:
            linhas.append(f"{e['inicio_display']} — {e['titulo']} ({e['agenda_nome']})")
    return "\n".join(linhas)


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
