"""
Agentes de fundo — rodam sozinhos, sem intervenção do usuário. Cada
rodada grava "prova de vida" na tabela `agent_state` do banco — é isso
que o painel de agentes lê pra saber se está tudo em dia.

O AGENTS_REGISTRY é a ÚNICA fonte de verdade sobre quais agentes existem,
o que fazem, e de quanto em quanto tempo rodam — tanto o agendador quanto
o endpoint `/api/agents` leem daqui, evitando duplicar a "verdade".
"""

import datetime
import time

from apscheduler.schedulers.background import BackgroundScheduler

AGENTS_REGISTRY = {
    "email_triage": {
        "nome": "Triagem de E-mail",
        "icon": "📬",
        "faz": "Busca e-mails novos nas contas configuradas e classifica em Ação/Info/Ruído.",
        "every_min": 15,
        "run_path": "/agents/email_triage/run",
        "arquivo": "jarvis.db (tabela email_triage_cache)",
    },
    "news_radar": {
        "nome": "Radar de Notícias",
        "icon": "📰",
        "faz": "Busca manchetes novas dos assuntos configurados.",
        "every_min": 30,
        "run_path": "/agents/news_radar/run",
        "arquivo": "jarvis.db (tabela news_cache)",
    },
    "morning_digest": {
        "nome": "Morning Digest",
        "icon": "🌅",
        "faz": "Gera o briefing matinal automaticamente, uma vez por dia às 7h.",
        "every_min": 24 * 60,
        "run_path": "/agents/morning_digest/run",
        "arquivo": "last_digest.json",
    },
    "news_narration": {
        "nome": "Narração de Notícias",
        "icon": "🔊",
        "faz": "Narra as notícias automaticamente, uma vez por dia, no horário configurado.",
        "every_min": 24 * 60,
        "run_path": "/agents/news_narration/run",
        "arquivo": "jarvis.db (tabela agent_state)",
    },
    "hey_jarvis": {
        "nome": "Hey JARVIS (escuta)",
        "icon": "🎙️",
        "faz": "Fica sempre ouvindo a palavra de ativação, em segundo plano.",
        "every_min": None,
        "run_path": None,
        "arquivo": "jarvis.db (tabela agent_state, heartbeat)",
    },
    "commitments_followup": {
        "nome": "Cobrança de Compromissos",
        "icon": "⏰",
        "faz": "Cobra sozinho compromissos com prazo vencido ou próximo (Second Brain ativo).",
        "every_min": 30,
        "run_path": "/agents/commitments_followup/run",
        "arquivo": "jarvis.db (tabela commitments)",
    },
}


def _agent_is_configured(agent_id: str) -> bool:
    try:
        if agent_id == "email_triage":
            import email_hub
            return bool(email_hub.load_email_accounts())
        if agent_id == "news_radar":
            import news_radar
            return bool(news_radar.load_topics())
        if agent_id == "morning_digest":
            return True
        if agent_id == "news_narration":
            import news_radar
            return news_radar.get_narration_hour() is not None
        if agent_id == "hey_jarvis":
            return True
        if agent_id == "commitments_followup":
            return True
    except Exception:
        return False
    return True


def is_agent_off(agent_id: str) -> bool:
    return not _agent_is_configured(agent_id)


def _run_with_retry(fn, max_tentativas: int = 2, espera_segundos: float = 2.0):
    """
    Autocura: tenta de novo automaticamente antes de desistir — muitos
    erros de agente de fundo são passageiros (rede instável, servidor
    IMAP ocupado por um instante), e insistir sozinho evita um alarme
    falso que o usuário teria que resolver manualmente sem necessidade.
    Devolve (resultado, tentativas_usadas). Propaga a última exceção se
    todas as tentativas falharem.
    """
    ultimo_erro = None
    for tentativa in range(1, max_tentativas + 1):
        try:
            return fn(), tentativa
        except Exception as e:
            ultimo_erro = e
            if tentativa < max_tentativas:
                time.sleep(espera_segundos)
    raise ultimo_erro


def run_email_triage_job() -> None:
    import database as db
    import email_hub

    if not email_hub.load_email_accounts():
        return

    def _tentar_triagem():
        resultado = email_hub.get_triaged_emails()
        if resultado.get("erros"):
            # Transforma em exceção de propósito, pra _run_with_retry conseguir
            # tentar de novo automaticamente — get_triaged_emails() nunca levanta
            # exceção sozinho, só devolve o erro dentro do dict.
            raise RuntimeError(resultado["erros"][0].get("erro", "Erro desconhecido"))
        return resultado

    try:
        resultado, tentativas = _run_with_retry(_tentar_triagem)
    except Exception as e:
        db.record_agent_run("email_triage", "error", str(e), "")
        return

    metric = f"{len(resultado['acao'])} ação, {len(resultado['info'])} info, {len(resultado['ruido'])} ruído"

    # Notificação proativa: só dos e-mails de ação que AINDA não avisamos —
    # senão, a cada 15min ele repetiria o aviso do mesmo e-mail sem parar.
    emails_acao = resultado["acao"]
    ids_acao = [e["id"] for e in emails_acao]
    novos_ids = db.get_unnotified_action_emails(ids_acao)
    if novos_ids:
        novos_emails = [e for e in emails_acao if e["id"] in novos_ids]

        # Ação autônoma segura: prepara um RASCUNHO de resposta pra cada
        # e-mail urgente novo — nunca envia sozinho, só deixa pronto pra
        # revisar. Só o primeiro (o mais relevante pra caber na notificação).
        rascunho_preview = ""
        try:
            primeiro = novos_emails[0]
            rascunho = email_hub.draft_reply(primeiro["remetente"], primeiro["assunto"], primeiro.get("trecho", ""))
            if rascunho:
                rascunho_preview = f"\n\n💬 Rascunho pronto: \"{rascunho[:120]}{'...' if len(rascunho) > 120 else ''}\""
        except Exception:
            pass  # rascunho é só um extra — nunca pode derrubar a notificação principal por causa disso

        if len(novos_emails) == 1:
            e = novos_emails[0]
            titulo = "📬 Novo e-mail pedindo ação"
            mensagem = f"{e['remetente']}: {e['assunto']}" + (f" — {e['resumo']}" if e.get("resumo") else "") + rascunho_preview
        else:
            titulo = f"📬 {len(novos_emails)} novos e-mails pedindo ação"
            mensagem = "; ".join(f"{e['remetente']}: {e['assunto']}" for e in novos_emails[:3])
            if len(novos_emails) > 3:
                mensagem += f" (+{len(novos_emails) - 3} outro(s))"
            mensagem += rascunho_preview
        db.create_notification("email", titulo, mensagem)
        db.mark_emails_notified(novos_ids)

    detail = "Triagem concluída" if tentativas == 1 else f"Triagem concluída (recuperou sozinho na tentativa {tentativas} — autocura)"
    db.record_agent_run("email_triage", "ok", detail, metric)


def run_news_radar_job() -> None:
    import database as db
    import news_radar

    if not news_radar.load_topics():
        return

    def _tentar_busca():
        resultados = news_radar.get_all_headlines(forcar_atualizacao=True)
        erros = [r for r in resultados if "erro" in r]
        if erros:
            raise RuntimeError(erros[0]["erro"])
        return resultados

    try:
        resultados, tentativas = _run_with_retry(_tentar_busca)
        total = sum(len(r.get("manchetes", [])) for r in resultados)
        detail = "Atualizado" if tentativas == 1 else f"Atualizado (recuperou sozinho na tentativa {tentativas} — autocura)"
        db.record_agent_run("news_radar", "ok", detail, f"{total} manchetes, {len(resultados)} assunto(s)")
    except Exception as e:
        db.record_agent_run("news_radar", "error", str(e), "")


def run_morning_digest_job(forcar: bool = False) -> None:
    """Roda de verdade só na janela das 7h (a menos que `forcar=True`, usado pelo botão manual)."""
    import database as db
    import morning_digest

    if not forcar:
        if morning_digest.already_ran_today():
            return
        if datetime.datetime.now().hour != 7:
            return
    try:
        morning_digest.generate_digest()
        db.record_agent_run("morning_digest", "ok", "Digest gerado com sucesso", "")
    except Exception as e:
        db.record_agent_run("morning_digest", "error", str(e), "")


def run_news_narration_job(forcar: bool = False) -> None:
    """
    Roda a narração automática das notícias só se: (1) um horário foi
    configurado, (2) é a hora certa, e (3) ainda não rodou hoje — a menos
    que `forcar=True` (botão manual).
    """
    import database as db
    import news_radar

    if not forcar:
        hora_configurada = news_radar.get_narration_hour()
        if hora_configurada is None:
            return  # ninguém configurou um horário — não roda, fica "off"

        agora = datetime.datetime.now()
        if agora.hour != hora_configurada:
            return

        estado_anterior = db.get_agent_state("news_narration")
        if estado_anterior and estado_anterior.get("last_run"):
            try:
                ultimo = datetime.datetime.fromisoformat(estado_anterior["last_run"])
                if ultimo.date() == agora.date():
                    return  # já rodou hoje, não roda de novo
            except ValueError:
                pass

    try:
        texto = news_radar.narrate_news()
        resumo = texto[:150] + ("..." if len(texto) > 150 else "")
        db.record_agent_run("news_narration", "ok", resumo, "")
    except Exception as e:
        db.record_agent_run("news_narration", "error", str(e), "")


def run_commitments_followup_job() -> None:
    """
    Second Brain ativo: cobra compromissos com prazo vencido ou próximo,
    sem esperar você perguntar — gera uma notificação proativa (mesmo
    sistema do 'JARVIS fala primeiro') pra cada um, uma única vez.
    """
    import database as db

    pendencias = db.get_pending_commitments_needing_followup(horas_de_antecedencia=24)
    if not pendencias:
        db.record_agent_run("commitments_followup", "ok", "Nada pra cobrar agora", "0 pendência(s)")
        return

    for c in pendencias:
        prazo_dt = datetime.datetime.fromisoformat(c["prazo"])
        agora = datetime.datetime.now(datetime.timezone.utc)
        if prazo_dt.tzinfo is None:
            prazo_dt = prazo_dt.replace(tzinfo=datetime.timezone.utc)
        vencido = prazo_dt <= agora

        titulo = "⏰ Compromisso vencido" if vencido else "⏰ Compromisso se aproximando"
        mensagem = c["texto"]
        db.create_notification("compromisso", titulo, mensagem)
        db.mark_commitment_followed_up(c["id"])

    db.record_agent_run("commitments_followup", "ok", "Cobrança enviada", f"{len(pendencias)} pendência(s)")


_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler(daemon=True)
    now = datetime.datetime.now()
    _scheduler.add_job(run_email_triage_job, "interval", minutes=15, id="email_triage", next_run_time=now)
    _scheduler.add_job(run_news_radar_job, "interval", minutes=30, id="news_radar", next_run_time=now)
    _scheduler.add_job(run_morning_digest_job, "interval", minutes=5, id="morning_digest_check", next_run_time=now)
    _scheduler.add_job(run_news_narration_job, "interval", minutes=5, id="news_narration_check", next_run_time=now)
    _scheduler.add_job(run_commitments_followup_job, "interval", minutes=30, id="commitments_followup", next_run_time=now)
    _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
