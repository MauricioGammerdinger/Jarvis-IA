"""
Dashboard financeiro geral — receitas, despesas, saldo, e orçamento por
categoria. Diferente do Dashboard de Tokens de IA (que é só sobre gasto
com IA), esse é sobre finanças pessoais em geral.
"""

from datetime import datetime


def get_monthly_summary(mes: str | None = None) -> dict:
    """Resumo do mês: total de receita, despesa, saldo, e gasto por categoria (com comparação ao orçamento, se definido)."""
    import database as db

    mes = mes or datetime.now().strftime("%Y-%m")
    transacoes = db.list_transactions(mes=mes)
    orcamentos = db.get_category_budgets()

    total_receitas = sum(t["valor"] for t in transacoes if t["tipo"] == "receita")
    total_despesas = sum(t["valor"] for t in transacoes if t["tipo"] == "despesa")
    saldo = total_receitas - total_despesas

    despesas_por_categoria: dict[str, float] = {}
    for t in transacoes:
        if t["tipo"] == "despesa":
            despesas_por_categoria[t["categoria"]] = despesas_por_categoria.get(t["categoria"], 0) + t["valor"]

    categorias_com_orcamento = []
    for categoria, gasto in despesas_por_categoria.items():
        limite = orcamentos.get(categoria)
        item = {"categoria": categoria, "gasto": gasto, "limite": limite}
        if limite is not None:
            item["pct_orcamento"] = (gasto / limite * 100) if limite > 0 else 0
            item["estourou"] = gasto > limite
        categorias_com_orcamento.append(item)

    return {
        "mes": mes,
        "total_receitas": total_receitas,
        "total_despesas": total_despesas,
        "saldo": saldo,
        "despesas_por_categoria": categorias_com_orcamento,
    }


def format_summary(resumo: dict) -> str:
    linhas = [
        f"Resumo de {resumo['mes']}:",
        f"Receitas: R$ {resumo['total_receitas']:.2f}",
        f"Despesas: R$ {resumo['total_despesas']:.2f}",
        f"Saldo: R$ {resumo['saldo']:.2f}",
    ]
    for c in resumo["despesas_por_categoria"]:
        linha = f"  {c['categoria']}: R$ {c['gasto']:.2f}"
        if c.get("limite") is not None:
            linha += f" de R$ {c['limite']:.2f} ({c['pct_orcamento']:.0f}%)"
            if c["estourou"]:
                linha += " ⚠ estourou"
        linhas.append(linha)
    return "\n".join(linhas)
