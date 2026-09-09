"""
Briefing rápido — "fala comigo, JARVIS". Diferente do Morning Digest
(mais elaborado: clima, notícias, todos os e-mails, roda de manhã e é
mais longo pra ouvir), isso é uma sitrep de poucos segundos, sob pedido,
a qualquer hora: só o que importa AGORA.
"""


def get_quick_briefing() -> str:
    """Junta o essencial — próximo compromisso, e-mails pendentes de ação, notificações não lidas — numa frase curta."""
    partes = []

    try:
        import calendar_hub

        proximo = calendar_hub.get_next_event()
        if proximo:
            partes.append(f"Próximo compromisso: {proximo['titulo']} (em {proximo['countdown']}).")
    except Exception:
        pass  # calendário não configurado, ou falhou — não é crítico pro briefing, só pula essa parte

    try:
        import email_hub

        if email_hub.load_email_accounts():
            resultado = email_hub.get_triaged_emails()
            n_acao = len(resultado.get("acao", []))
            if n_acao > 0:
                partes.append(f"{n_acao} e-mail(is) pedindo ação.")
    except Exception:
        pass

    try:
        import database as db

        nao_lidas = db.list_unread_notifications()
        if nao_lidas:
            partes.append(f"{len(nao_lidas)} notificação(ões) não lida(s).")
    except Exception:
        pass

    if not partes:
        return "Tudo tranquilo por aqui — nada pendente no momento."

    return " ".join(partes)
