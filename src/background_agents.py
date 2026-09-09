"""
Agentes de fundo — rodam sozinhos, sem intervenção do usuário. Cada
rodada grava "prova de vida" na tabela `agent_state` do banco — é isso
que o painel de agentes lê pra saber se está tudo em dia.

O AGENTS_REGISTRY é a ÚNICA fonte de verdade sobre quais agentes existem,
o que fazem, e de quanto em quanto tempo rodam — tanto o agendador quanto
o endpoint `/api/agents` leem daqui, evitando duplicar a "verdade".
"""

import datetime
import json
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
    "second_brain_checkin": {
        "nome": "Check-in do Second Brain",
        "icon": "🧠",
        "faz": "Puxa uma meta de volta de vez em quando, sem você perguntar.",
        "every_min": 24 * 60,
        "run_path": "/agents/second_brain_checkin/run",
        "arquivo": "jarvis.db (tabela memories)",
    },
    "machine_sync": {
        "nome": "Sincronização entre PCs",
        "icon": "🔄",
        "faz": "Compartilha Second Brain e compromissos com suas outras máquinas.",
        "every_min": 10,
        "run_path": "/agents/machine_sync/run",
        "arquivo": "pasta compartilhada (JARVIS_SYNC_FOLDER)",
    },
    "weekly_retrospective": {
        "nome": "Retrospectiva Semanal",
        "icon": "📅",
        "faz": "Resume o que você realizou na semana — compromissos, metas, commits.",
        "every_min": 7 * 24 * 60,
        "run_path": "/agents/weekly_retrospective/run",
        "arquivo": "jarvis.db (commitments + memories) + projetos de código",
    },
    "focus_monitor": {
        "nome": "Detecção de Foco",
        "icon": "👀",
        "faz": "Avisa se você ficar muito tempo na mesma janela (opt-in, desligado por padrão).",
        "every_min": 3,
        "run_path": None,  # não faz sentido "forçar" — é uma checagem de estado momentâneo
        "arquivo": "memória do processo (nunca grava em disco)",
    },
    "emotion_check": {
        "nome": "Check-in Emocional",
        "icon": "💬",
        "faz": "Pergunta como você está se detectar sinal sustentado (opt-in, desligado por padrão).",
        "every_min": 30,
        "run_path": None,
        "arquivo": "câmera (nunca salva imagem em disco)",
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
        if agent_id == "second_brain_checkin":
            return True
        if agent_id == "machine_sync":
            import machine_sync as ms
            return ms.is_sync_enabled()
        if agent_id == "weekly_retrospective":
            return True
        if agent_id == "focus_monitor":
            import focus_monitor as fm
            return fm.FOCUS_MONITOR_ENABLED
        if agent_id == "emotion_check":
            import camera_vision as cam
            return cam.EMOTION_CHECK_ENABLED
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


def run_second_brain_checkin_job() -> None:
    """
    Second Brain ativo, parte 2: de vez em quando, puxa UMA meta de volta
    numa notificação, sem o usuário perguntar — "você mencionou querer X,
    como está indo?". Roda devagar e nunca repete a mesma meta antes de
    20 dias — e também nunca manda MAIS de um check-in por dia no total,
    mesmo que existam várias metas pendentes de cobrança ao mesmo tempo
    (senão viraria bombardeio em vez de "de vez em quando").
    """
    import database as db

    ultimo_checkin = [n for n in db.list_all_notifications(limite=20) if n["tipo"] == "second_brain"]
    if ultimo_checkin:
        ultimo = datetime.datetime.fromisoformat(ultimo_checkin[0]["created_at"])
        if ultimo.tzinfo is None:
            ultimo = ultimo.replace(tzinfo=datetime.timezone.utc)
        horas_desde_ultimo = (datetime.datetime.now(datetime.timezone.utc) - ultimo).total_seconds() / 3600
        if horas_desde_ultimo < 20:
            db.record_agent_run("second_brain_checkin", "ok", "Ainda dentro do intervalo mínimo entre check-ins", "")
            return

    memoria = db.get_memory_for_checkin(dias_minimos_entre_cobrancas=20)
    if not memoria:
        db.record_agent_run("second_brain_checkin", "ok", "Nada pra puxar agora", "")
        return

    try:
        import llm_client

        system = (
            "Gere UMA frase curta, natural e calorosa, perguntando como está indo uma meta que a "
            "pessoa mencionou antes. Não seja robótico. Exemplo de tom: 'Você mencionou querer "
            "aprender inglês fluente — como está indo isso?'. Responda só a frase, nada mais."
        )
        result = llm_client.chat(messages=[{"role": "user", "content": memoria["content"]}], tools=[], system=system)
        mensagem = result["text"].strip() or f"Você mencionou: '{memoria['content']}' — como está indo isso?"
    except Exception:
        mensagem = f"Você mencionou: '{memoria['content']}' — como está indo isso?"

    db.create_notification("second_brain", "🧠 Só checando...", mensagem)
    db.mark_memory_checked_in(memoria["id"])
    db.record_agent_run("second_brain_checkin", "ok", "Check-in enviado", memoria["content"][:60])


def run_machine_sync_job() -> None:
    """Sincroniza Second Brain e compromissos com outras máquinas, via pasta compartilhada (ex: OneDrive). Não faz nada se não estiver configurado."""
    import database as db
    import machine_sync as ms

    if not ms.is_sync_enabled():
        return  # sem JARVIS_SYNC_FOLDER configurado — não é erro, só está desligado de propósito

    resultado = ms.sync_now()
    if not resultado["export"]["ok"] or not resultado["import"]["ok"]:
        motivo = resultado["export"].get("motivo") or resultado["import"].get("motivo") or "erro desconhecido"
        db.record_agent_run("machine_sync", "error", motivo, "")
        return

    imp = resultado["import"]
    metric = f"{imp['memories_novas']} memória(s) nova(s), {imp['commitments_novos']} compromisso(s) novo(s), {imp['commitments_atualizados']} atualizado(s)"
    detail = f"Sincronizado com {len(imp['maquinas'])} máquina(s)" if imp["maquinas"] else "Nenhuma outra máquina encontrada ainda"
    db.record_agent_run("machine_sync", "ok", detail, metric)


def _build_offline_retrospective(contexto: dict) -> str:
    """Fallback sem IA — template local, sempre funciona, mesmo sem Ollama disponível."""
    partes = ["Sua semana em resumo:"]
    if contexto["compromissos_concluidos"]:
        partes.append("Você concluiu: " + "; ".join(contexto["compromissos_concluidos"]) + ".")
    if contexto["metas_mencionadas"]:
        partes.append("Metas novas mencionadas: " + "; ".join(contexto["metas_mencionadas"]) + ".")
    if contexto["total_commits"] > 0:
        partes.append(f"{contexto['total_commits']} commit(s): " + ", ".join(contexto["commits_por_projeto"]) + ".")
    if contexto["compromissos_ainda_pendentes"]:
        partes.append(f"Ainda pendente: {len(contexto['compromissos_ainda_pendentes'])} compromisso(s).")
    return " ".join(partes)


def run_weekly_retrospective_job(forcar: bool = False) -> None:
    """
    Retrospectiva semanal: junta compromissos concluídos, metas novas
    mencionadas, e commits nos projetos cadastrados na última semana — e
    manda como notificação. Roda no máximo 1x a cada 6 dias sozinho (a
    menos que `forcar=True`, usado quando o usuário pede na hora).
    """
    import database as db
    import git_projects

    if not forcar:
        ultimas = [n for n in db.list_all_notifications(limite=20) if n["tipo"] == "retrospectiva"]
        if ultimas:
            ultimo_dt = datetime.datetime.fromisoformat(ultimas[0]["created_at"])
            if ultimo_dt.tzinfo is None:
                ultimo_dt = ultimo_dt.replace(tzinfo=datetime.timezone.utc)
            dias_desde_ultima = (datetime.datetime.now(datetime.timezone.utc) - ultimo_dt).total_seconds() / 86400
            if dias_desde_ultima < 6:
                db.record_agent_run("weekly_retrospective", "ok", "Ainda dentro do intervalo mínimo (1x por semana)", "")
                return

    dados = db.get_weekly_retrospective_data(dias=7)

    total_commits = 0
    projetos_com_commit = []
    for projeto in git_projects.load_code_projects():
        commits = git_projects.count_commits_since(projeto["caminho"], dias=7)
        if commits > 0:
            total_commits += commits
            projetos_com_commit.append(f"{projeto['nome']} ({commits})")

    nada_relevante = not dados["compromissos_concluidos"] and not dados["metas_novas"] and total_commits == 0
    if nada_relevante:
        db.record_agent_run("weekly_retrospective", "ok", "Semana tranquila, nada relevante pra destacar", "")
        return "Semana tranquila por aqui — nada de compromisso concluído, meta nova, ou commit nos projetos cadastrados."

    contexto = {
        "compromissos_concluidos": [c["texto"] for c in dados["compromissos_concluidos"]],
        "compromissos_ainda_pendentes": [c["texto"] for c in dados["compromissos_ainda_pendentes"]],
        "metas_mencionadas": [m["content"] for m in dados["metas_novas"]],
        "commits_por_projeto": projetos_com_commit,
        "total_commits": total_commits,
    }

    try:
        import llm_client

        system = (
            "Monte uma retrospectiva semanal curta e calorosa (não robótica), 3-5 frases, "
            "destacando o que a pessoa realizou essa semana com os dados abaixo. Termine com "
            "um comentário positivo ou de incentivo. Não invente nada que não está nos dados."
        )
        result = llm_client.chat(messages=[{"role": "user", "content": json.dumps(contexto, ensure_ascii=False)}], tools=[], system=system)
        texto = result["text"].strip() or _build_offline_retrospective(contexto)
    except Exception:
        texto = _build_offline_retrospective(contexto)

    db.create_notification("retrospectiva", "📅 Sua semana em resumo", texto)
    db.record_agent_run(
        "weekly_retrospective", "ok", "Retrospectiva enviada",
        f"{total_commits} commit(s), {len(dados['compromissos_concluidos'])} compromisso(s) concluído(s)",
    )
    return texto


def run_focus_monitor_job() -> None:
    """
    Detecção de "travado numa tarefa" — desligado por padrão (opt-in via
    JARVIS_FOCUS_MONITOR=1 no .env). Só cria notificação quando o próprio
    módulo detecta tempo demais na mesma janela sem ficar parado — nunca
    grava nada em disco, o estado vive só na memória do processo.
    """
    import database as db
    import focus_monitor as fm

    if not fm.FOCUS_MONITOR_ENABLED:
        return  # desligado de propósito — nem tenta, nem registra estado

    aviso = fm.check_stuck()
    if aviso:
        db.create_notification(
            "foco",
            "👀 Notei que você está há um tempo na mesma tela",
            f"Faz {aviso['minutos']} minutos que você está em \"{aviso['titulo']}\" — precisa de ajuda com algo?",
        )
        db.record_agent_run("focus_monitor", "ok", "Detectou tempo prolongado na mesma janela", aviso["titulo"][:60])
    else:
        db.record_agent_run("focus_monitor", "ok", "Monitorando", "")


def run_emotion_check_job() -> None:
    """
    Check-in emocional por câmera — desligado por padrão (opt-in via
    JARVIS_EMOTION_CHECK_ENABLED=1 no .env). Só age depois de várias
    leituras seguidas indicando algo negativo (nunca uma foto só — isso
    seria ruído, não sinal real). A pergunta é injetada DE VERDADE na
    conversa (sessão "voz"), não só um aviso solto — assim, quando a
    pessoa responder, o JARVIS tem contexto de que foi ele mesmo que
    perguntou, e consegue continuar a conversa naturalmente.

    A frase NUNCA afirma um diagnóstico ("você está triste") — sempre uma
    pergunta aberta e cuidadosa, porque detecção de emoção por expressão
    facial é conhecidamente imprecisa (rosto cansado/concentrado vira
    "triste" com facilidade).
    """
    import database as db
    import camera_vision as cam

    if not cam.EMOTION_CHECK_ENABLED:
        return

    resultado = cam.analyze_emotion_now()
    if not resultado["ok"]:
        db.record_agent_run("emotion_check", "ok", resultado["motivo"], "")
        return

    deve_perguntar = cam.register_reading_and_check(resultado["emocao_dominante"], resultado["negativa"])
    if not deve_perguntar:
        db.record_agent_run("emotion_check", "ok", f"Lendo — última leitura: {resultado['emocao_dominante']}", "")
        return

    try:
        import llm_client

        system = (
            "Gere UMA frase curta e calorosa, verificando com cuidado como a pessoa está, sem "
            "afirmar nenhum diagnóstico ou nomear uma emoção específica dela. Nunca diga "
            "'você parece triste' ou similar — é intrusivo e pode estar errado. Algo mais no "
            "estilo 'Faz um tempo que não paramos pra conversar — como você está?'. Responda só a frase."
        )
        result = llm_client.chat(messages=[{"role": "user", "content": "gerar pergunta de check-in"}], tools=[], system=system)
        pergunta = result["text"].strip() or "Faz um tempo que não conversamos direito — como você está?"
    except Exception:
        pergunta = "Faz um tempo que não conversamos direito — como você está?"

    # Injeta na conversa de verdade (sessão "voz") — não só um toast solto.
    db.append_message("voz", "assistant", pergunta)
    db.create_notification("emocional", "💬 Um oi rapidinho", pergunta)
    db.record_agent_run("emotion_check", "ok", "Check-in enviado, injetado na conversa", "")


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
    _scheduler.add_job(run_second_brain_checkin_job, "interval", hours=6, id="second_brain_checkin", next_run_time=now)
    _scheduler.add_job(run_machine_sync_job, "interval", minutes=10, id="machine_sync", next_run_time=now)
    _scheduler.add_job(run_weekly_retrospective_job, "interval", hours=12, id="weekly_retrospective_check", next_run_time=now)
    _scheduler.add_job(run_focus_monitor_job, "interval", minutes=3, id="focus_monitor", next_run_time=now)
    import camera_vision as _cam_config
    _scheduler.add_job(run_emotion_check_job, "interval", minutes=_cam_config.EMOTION_CHECK_INTERVAL_MINUTES, id="emotion_check", next_run_time=now)
    _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
