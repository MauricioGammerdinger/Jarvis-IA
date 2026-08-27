"""
Dashboard de Controle de Tokens de IA — rastreia gasto de API (pago por
uso) e cota de assinaturas (Claude Pro/Max, ChatGPT, Cursor, etc), com
custo real, projeção, e contagem regressiva até o reset.

Tabela de preços e configuração ficam em JSON editável (mesmo padrão de
apps_config.json) — preços de API mudam com frequência, o usuário deve
conferir no site do provedor de tempos em tempos.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

PRICE_TABLE_PATH = Path(__file__).parent.parent / "ai_price_table.json"
CONFIG_PATH = Path(__file__).parent.parent / "ai_dashboard_config.json"

# Catálogo padrão — US$ por 1 milhão de tokens. Preços de referência de
# jan/2026; SEMPRE conferir no site do provedor, isso muda com frequência.
DEFAULT_PRICE_TABLE = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "claude-opus-4": {"input": 15.00, "output": 75.00},
    "claude-sonnet-4": {"input": 3.00, "output": 15.00},
    "claude-haiku": {"input": 0.80, "output": 4.00},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "deepseek-v3": {"input": 0.27, "output": 1.10},
}

DEFAULT_CONFIG = {
    "budget_monthly_usd": 200,
    "alert_pct": 80,
    "currency": "USD",
    "usd_to_brl": 5.40,
}


def load_price_table() -> dict:
    if not PRICE_TABLE_PATH.exists():
        save_price_table(DEFAULT_PRICE_TABLE)
        return dict(DEFAULT_PRICE_TABLE)
    with open(PRICE_TABLE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_price_table(tabela: dict) -> None:
    with open(PRICE_TABLE_PATH, "w", encoding="utf-8") as f:
        json.dump(tabela, f, ensure_ascii=False, indent=2)


def set_model_price(modelo: str, preco_input: float, preco_output: float) -> None:
    tabela = load_price_table()
    tabela[modelo] = {"input": preco_input, "output": preco_output}
    save_price_table(tabela)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    return {**DEFAULT_CONFIG, **config}


def save_config(config: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def update_config(**kwargs) -> dict:
    config = load_config()
    config.update({k: v for k, v in kwargs.items() if v is not None})
    save_config(config)
    return config


def calculate_cost(modelo: str, input_tokens: int, output_tokens: int) -> float:
    """custo = (inputTokens/1e6 * preçoInput) + (outputTokens/1e6 * preçoOutput)"""
    tabela = load_price_table()
    precos = tabela.get(modelo, {"input": 0, "output": 0})
    return (input_tokens / 1_000_000 * precos["input"]) + (output_tokens / 1_000_000 * precos["output"])


def register_usage(data: str, projeto: str, modelo: str, input_tokens: int, output_tokens: int) -> dict:
    import database as db

    usage_id = db.add_ai_usage(data, projeto, modelo, input_tokens, output_tokens)
    custo = calculate_cost(modelo, input_tokens, output_tokens)
    return {"id": usage_id, "custo": custo}


def get_usage_with_cost(periodo_dias: int | None = None) -> list[dict]:
    import database as db

    usos = db.list_ai_usage()
    if periodo_dias is not None:
        corte = (datetime.now() - timedelta(days=periodo_dias)).date().isoformat()
        usos = [u for u in usos if u["data"] >= corte]

    for u in usos:
        u["custo"] = calculate_cost(u["modelo"], u["input_tokens"], u["output_tokens"])
    return usos


def _dias_no_mes(ano: int, mes: int) -> int:
    if mes == 12:
        proximo = datetime(ano + 1, 1, 1)
    else:
        proximo = datetime(ano, mes + 1, 1)
    return (proximo - datetime(ano, mes, 1)).days


def get_api_summary(mes: str | None = None) -> dict:
    """Resumo do gasto de API no mês, com breakdown e projeção até o fim do mês."""
    config = load_config()
    hoje = datetime.now()
    mes = mes or hoje.strftime("%Y-%m")

    todos_usos = get_usage_with_cost()
    usos_do_mes = [u for u in todos_usos if u["data"].startswith(mes)]

    total_gasto = sum(u["custo"] for u in usos_do_mes)
    orcamento = config["budget_monthly_usd"]
    pct_orcamento = (total_gasto / orcamento * 100) if orcamento > 0 else 0

    por_modelo: dict[str, float] = {}
    por_projeto: dict[str, float] = {}
    for u in usos_do_mes:
        por_modelo[u["modelo"]] = por_modelo.get(u["modelo"], 0) + u["custo"]
        por_projeto[u["projeto"]] = por_projeto.get(u["projeto"], 0) + u["custo"]

    ano, mes_num = map(int, mes.split("-"))
    if ano == hoje.year and mes_num == hoje.month:
        dias_passados = hoje.day
        dias_no_mes = _dias_no_mes(ano, mes_num)
        dias_restantes = dias_no_mes - dias_passados
        ritmo_diario = total_gasto / dias_passados if dias_passados > 0 else 0
        projecao_fim_mes = total_gasto + (ritmo_diario * dias_restantes)
    else:
        projecao_fim_mes = total_gasto

    return {
        "mes": mes,
        "total_gasto": total_gasto,
        "orcamento": orcamento,
        "pct_orcamento": pct_orcamento,
        "estourou": total_gasto > orcamento,
        "alerta": pct_orcamento >= config["alert_pct"],
        "por_modelo": por_modelo,
        "por_projeto": por_projeto,
        "projecao_fim_mes": projecao_fim_mes,
    }


# ── Assinaturas (cota do plano) ────────────────────────────────────────
UNIDADE_LABELS = {"messages": "mensagens", "requests": "requests", "credits": "créditos", "tokens": "tokens"}


def add_subscription(nome: str, unidade: str, limite: float, tipo_reset: str,
                      reset_a_cada_horas: float | None = None, reset_ancora: str | None = None,
                      custo_mensal_usd: float = 0) -> None:
    import database as db

    if unidade not in UNIDADE_LABELS:
        raise ValueError(f"Unidade inválida: {unidade}. Use uma de: {list(UNIDADE_LABELS)}")
    if tipo_reset not in ("rolling", "daily", "monthly"):
        raise ValueError(f"Tipo de reset inválido: {tipo_reset}. Use 'rolling', 'daily' ou 'monthly'.")
    if tipo_reset == "rolling" and not reset_a_cada_horas:
        raise ValueError("Reset do tipo 'rolling' precisa de reset_a_cada_horas.")

    ancora = reset_ancora or datetime.now().isoformat()
    db.upsert_subscription(nome, unidade, limite, tipo_reset, reset_a_cada_horas, ancora, custo_mensal_usd)


def _next_reset(sub: dict, agora: datetime) -> datetime:
    """Calcula o PRÓXIMO reset a partir da âncora, avançando ciclos já passados."""
    ancora = datetime.fromisoformat(sub["reset_ancora"])

    if sub["tipo_reset"] == "rolling":
        horas = sub["reset_a_cada_horas"]
        proximo = ancora
        while proximo <= agora:
            proximo += timedelta(hours=horas)
        return proximo

    if sub["tipo_reset"] == "daily":
        proximo = ancora
        while proximo <= agora:
            proximo += timedelta(days=1)
        return proximo

    if sub["tipo_reset"] == "monthly":
        proximo = ancora
        while proximo <= agora:
            ano, mes = proximo.year, proximo.month
            if mes == 12:
                proximo = proximo.replace(year=ano + 1, month=1)
            else:
                proximo = proximo.replace(month=mes + 1)
        return proximo

    raise ValueError(f"Tipo de reset desconhecido: {sub['tipo_reset']}")


def _auto_reset_if_needed(sub: dict) -> dict:
    """Se o ciclo já virou (passou do reset), zera o uso e avança a âncora automaticamente — nos 3 tipos de reset."""
    import database as db

    agora = datetime.now()
    ancora = datetime.fromisoformat(sub["reset_ancora"])
    ancora_naive = ancora.replace(tzinfo=None) if ancora.tzinfo else ancora

    if sub["tipo_reset"] == "rolling":
        horas = sub["reset_a_cada_horas"]
        nova_ancora = ancora_naive
        ciclos_passados = 0
        while nova_ancora + timedelta(hours=horas) <= agora:
            nova_ancora += timedelta(hours=horas)
            ciclos_passados += 1
        if ciclos_passados > 0:
            db.set_subscription_usage(sub["nome"], nova_ancora.isoformat())
            sub = db.get_subscription(sub["nome"])

    elif sub["tipo_reset"] == "daily":
        nova_ancora = ancora_naive
        ciclos_passados = 0
        while nova_ancora + timedelta(days=1) <= agora:
            nova_ancora += timedelta(days=1)
            ciclos_passados += 1
        if ciclos_passados > 0:
            db.set_subscription_usage(sub["nome"], nova_ancora.isoformat())
            sub = db.get_subscription(sub["nome"])

    elif sub["tipo_reset"] == "monthly":
        nova_ancora = ancora_naive
        ciclos_passados = 0
        while True:
            ano, mes = nova_ancora.year, nova_ancora.month
            proximo = nova_ancora.replace(year=ano + 1, month=1) if mes == 12 else nova_ancora.replace(month=mes + 1)
            if proximo > agora:
                break
            nova_ancora = proximo
            ciclos_passados += 1
        if ciclos_passados > 0:
            db.set_subscription_usage(sub["nome"], nova_ancora.isoformat())
            sub = db.get_subscription(sub["nome"])

    return sub


def get_subscriptions_snapshot() -> list[dict]:
    """Estado de cada assinatura: usado/limite, restante, contagem regressiva, projeção, e status (ok/aviso/critico)."""
    import database as db

    config = load_config()
    subs = db.list_subscriptions()
    agora = datetime.now()
    resultado = []

    for sub in subs:
        sub = _auto_reset_if_needed(sub)

        usado_pct = (sub["usado"] / sub["limite"] * 100) if sub["limite"] > 0 else 0
        restante = max(0, sub["limite"] - sub["usado"])

        try:
            proximo_reset = _next_reset(sub, agora)
            segundos_ate_reset = (proximo_reset - agora).total_seconds()
        except Exception:
            proximo_reset = None
            segundos_ate_reset = None

        # Projeção: ritmo de consumo por hora, desde a âncora, x horas até o reset.
        # Só confia na projeção depois de pelo menos 15min de dados — senão,
        # uma assinatura recém-criada (âncora = agora mesmo) gera uma taxa
        # artificialmente altíssima e acusa "vai estourar" sem sentido.
        projecao_estoura = False
        if segundos_ate_reset is not None and segundos_ate_reset > 0:
            ancora = datetime.fromisoformat(sub["reset_ancora"])
            horas_desde_ancora = (agora - ancora).total_seconds() / 3600
            if horas_desde_ancora >= 0.25:
                ritmo_por_hora = sub["usado"] / horas_desde_ancora
                horas_ate_reset = segundos_ate_reset / 3600
                projecao_uso_final = sub["usado"] + (ritmo_por_hora * horas_ate_reset)
                projecao_estoura = projecao_uso_final > sub["limite"]

        if usado_pct >= 100:
            status = "critico"
        elif usado_pct >= config["alert_pct"] or projecao_estoura:
            status = "aviso"
        else:
            status = "ok"

        resultado.append({
            **sub,
            "unidade_label": UNIDADE_LABELS.get(sub["unidade"], sub["unidade"]),
            "usado_pct": usado_pct,
            "restante": restante,
            "proximo_reset": proximo_reset.isoformat() if proximo_reset else None,
            "segundos_ate_reset": segundos_ate_reset,
            "projecao_estoura": projecao_estoura,
            "status": status,
        })

    return resultado


def format_countdown(segundos: float) -> str:
    if segundos is None or segundos < 0:
        return "—"
    horas = int(segundos // 3600)
    minutos = int((segundos % 3600) // 60)
    if horas >= 24:
        dias = horas // 24
        horas_restantes = horas % 24
        return f"{dias}d {horas_restantes}h"
    return f"{horas}h {minutos}min"


def increment_subscription(nome: str, quantidade: float = 1) -> dict:
    import database as db

    sub = db.get_subscription(nome)
    if not sub:
        raise ValueError(f"Assinatura '{nome}' não encontrada.")
    db.increment_subscription_usage(nome, quantidade)
    return db.get_subscription(nome)


def reset_subscription_now(nome: str) -> dict:
    import database as db

    sub = db.get_subscription(nome)
    if not sub:
        raise ValueError(f"Assinatura '{nome}' não encontrada.")
    db.set_subscription_usage(nome, datetime.now().isoformat())
    return db.get_subscription(nome)


def get_total_ai_cost_this_month() -> dict:
    """Custo total de IA = gasto de API no mês + soma dos custos fixos mensais das assinaturas cadastradas."""
    import database as db

    api = get_api_summary()
    subs = db.list_subscriptions()
    custo_assinaturas = sum(s["custo_mensal_usd"] for s in subs)
    return {
        "custo_api": api["total_gasto"],
        "custo_assinaturas": custo_assinaturas,
        "total": api["total_gasto"] + custo_assinaturas,
    }
