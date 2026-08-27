"""
Central de E-mails — conecta em quantas contas IMAP você quiser, lê os
mais recentes (sem marcar como lido) e triagem em 3 baldes: AÇÃO, INFO,
RUÍDO. Usa `imaplib` nativo do Python.

Como conseguir a "senha de app" (nunca é a senha normal do Gmail):
1. Ativa a verificação em 2 etapas primeiro (myaccount.google.com/security)
2. Depois, myaccount.google.com/apppasswords → cria um app "JARVIS" →
   copia a senha de 16 letras
3. Cola essa senha aqui (nunca a senha normal da conta)

Segurança: a senha de app só dá acesso de LEITURA via IMAP. Fica salva só
no seu PC, nunca é logada, e nunca é enviada pra API de IA — só
remetente/assunto/trecho vão pro modelo LOCAL fazer a triagem.
"""

import email
import email.message
import imaplib
import json
import re
from email.header import decode_header
from pathlib import Path

EMAIL_ACCOUNTS_PATH = Path(__file__).parent.parent / "email_accounts.json"

ALLOWED_IMAP_HOSTS = {
    "imap.gmail.com",
    "imap.mail.yahoo.com",
    "outlook.office365.com",
    "imap-mail.outlook.com",
    "imap.mail.me.com",
}


def load_email_accounts() -> list[dict]:
    if not EMAIL_ACCOUNTS_PATH.exists():
        return []
    with open(EMAIL_ACCOUNTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_email_accounts(accounts: list[dict]) -> None:
    with open(EMAIL_ACCOUNTS_PATH, "w", encoding="utf-8") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)


def add_email_account(apelido: str, cor: str, host: str, usuario: str, senha_app: str) -> str | None:
    if host not in ALLOWED_IMAP_HOSTS:
        return f"Host '{host}' não está na lista permitida ({', '.join(sorted(ALLOWED_IMAP_HOSTS))})."
    accounts = load_email_accounts()
    accounts = [a for a in accounts if a["apelido"] != apelido]
    accounts.append({"apelido": apelido, "cor": cor, "host": host, "usuario": usuario, "senha_app": senha_app})
    save_email_accounts(accounts)
    return None


def remove_email_account(apelido: str) -> bool:
    accounts = load_email_accounts()
    filtered = [a for a in accounts if a["apelido"] != apelido]
    if len(filtered) == len(accounts):
        return False
    save_email_accounts(filtered)
    return True


def _decode_mime_words(s: str) -> str:
    if not s:
        return ""
    parts = decode_header(s)
    return "".join(
        part.decode(enc or "utf-8", errors="replace") if isinstance(part, bytes) else part
        for part, enc in parts
    )


def _get_body_snippet(msg: email.message.Message, max_chars: int = 500) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                try:
                    charset = part.get_content_charset() or "utf-8"
                    body = part.get_payload(decode=True).decode(charset, errors="replace")
                    break
                except Exception:
                    continue
        if not body:
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    try:
                        charset = part.get_content_charset() or "utf-8"
                        html = part.get_payload(decode=True).decode(charset, errors="replace")
                        body = re.sub(r"<[^>]+>", " ", html)
                        break
                    except Exception:
                        continue
    else:
        try:
            charset = msg.get_content_charset() or "utf-8"
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(charset, errors="replace")
        except Exception:
            body = ""

    return re.sub(r"\s+", " ", body).strip()[:max_chars]


def fetch_emails_for_account(account: dict, quantidade: int = 20) -> list[dict]:
    if account["host"] not in ALLOWED_IMAP_HOSTS:
        return [{"erro": f"Host '{account['host']}' não permitido.", "conta": account["apelido"]}]

    try:
        imap = imaplib.IMAP4_SSL(account["host"], 993)
        imap.login(account["usuario"], account["senha_app"])
        imap.select("INBOX", readonly=True)

        status, data = imap.search(None, "ALL")
        if status != "OK":
            imap.logout()
            return [{"erro": "Falha ao listar mensagens.", "conta": account["apelido"]}]

        ids = data[0].split()
        ids = ids[-quantidade:] if len(ids) > quantidade else ids
        ids = list(reversed(ids))

        emails = []
        for msg_id in ids:
            status, msg_data = imap.fetch(msg_id, "(BODY.PEEK[])")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            message_id = msg.get("Message-ID") or f"sem-id-{account['apelido']}-{msg_id.decode()}"
            emails.append({
                "id": message_id,
                "conta": account["apelido"],
                "cor": account["cor"],
                "remetente": _decode_mime_words(msg.get("From", "desconhecido")),
                "assunto": _decode_mime_words(msg.get("Subject", "(sem assunto)")),
                "data": msg.get("Date", ""),
                "trecho": _get_body_snippet(msg),
            })

        imap.logout()
        return emails
    except imaplib.IMAP4.error:
        return [{
            "erro": "Senha de app inválida ou verificação em 2 etapas desativada — "
                    "refaça em myaccount.google.com/apppasswords",
            "conta": account["apelido"],
        }]
    except Exception as e:
        return [{"erro": f"Falha ao conectar: {e}", "conta": account["apelido"]}]


def fetch_all_emails(quantidade_por_conta: int = 20) -> list[dict]:
    accounts = load_email_accounts()
    all_emails = []
    for account in accounts:
        all_emails.extend(fetch_emails_for_account(account, quantidade_por_conta))
    return all_emails


_NOISE_KEYWORDS = ["noreply", "no-reply", "newsletter", "unsubscribe", "descadastrar", "promoção", "promocao", "publicidade"]
_ACTION_KEYWORDS = ["por favor", "prazo", "fatura", "reunião", "reuniao", "confirmar", "urgente", "pendente", "responda", "aguardo retorno", "?"]


def _heuristic_triage(item: dict) -> tuple[str, str]:
    combined = f"{item.get('assunto', '')} {item.get('remetente', '')} {item.get('trecho', '')}".lower()
    if any(k in combined for k in _NOISE_KEYWORDS):
        return "ruido", "Classificado por heurística (sem IA disponível)."
    if any(k in combined for k in _ACTION_KEYWORDS):
        return "acao", "Classificado por heurística (sem IA disponível)."
    return "info", "Classificado por heurística (sem IA disponível)."


def triage_batch(emails: list[dict]) -> dict[str, dict]:
    """Classifica e-mails NOVOS numa ÚNICA chamada ao modelo local, com fallback heurístico."""
    if not emails:
        return {}

    import llm_client

    items = [
        {"id": e["id"], "remetente": e["remetente"], "assunto": e["assunto"], "trecho": e["trecho"][:200]}
        for e in emails
    ]

    system = (
        "Você classifica e-mails em 3 baldes: 'acao' (pede resposta, tarefa, decisão, "
        "ou tem prazo), 'info' (vale saber, mas não exige nada), 'ruido' (promoção, "
        "newsletter, notificação automática). "
        'Responda APENAS um JSON válido: [{"id": "...", "balde": "acao|info|ruido", '
        '"resumo": "uma frase curta em português"}]. Nada de texto antes ou depois do JSON.'
    )

    try:
        result = llm_client.chat(
            messages=[{"role": "user", "content": json.dumps(items, ensure_ascii=False)}],
            tools=[],
            system=system,
        )
        text = result["text"].strip()
        match = re.search(r"\[[\s\S]*\]", text)
        if not match:
            raise ValueError("Resposta do modelo não contém um JSON válido.")
        parsed = json.loads(match.group(0))
        triage_map = {}
        for item in parsed:
            if item.get("id") and item.get("balde") in ("acao", "info", "ruido"):
                triage_map[item["id"]] = {"balde": item["balde"], "resumo": item.get("resumo", "")}
        for e in emails:
            if e["id"] not in triage_map:
                balde, resumo = _heuristic_triage(e)
                triage_map[e["id"]] = {"balde": balde, "resumo": resumo}
        return triage_map
    except Exception:
        return {e["id"]: dict(zip(("balde", "resumo"), _heuristic_triage(e))) for e in emails}


def get_triaged_emails(quantidade_por_conta: int = 20) -> dict:
    """Busca e-mails de todas as contas, triando só os que ainda não estão em cache."""
    import database as db

    raw_emails = fetch_all_emails(quantidade_por_conta)
    valid_emails = [e for e in raw_emails if "erro" not in e]
    errors = [e for e in raw_emails if "erro" in e]

    cached = db.get_email_triage([e["id"] for e in valid_emails])
    novos = [e for e in valid_emails if e["id"] not in cached]

    if novos:
        novas_triagens = triage_batch(novos)
        for msg_id, triagem in novas_triagens.items():
            db.save_email_triage(msg_id, triagem["balde"], triagem["resumo"])
        cached.update(novas_triagens)

    buckets = {"acao": [], "info": [], "ruido": []}
    for e in valid_emails:
        triagem = cached.get(e["id"], {"balde": "info", "resumo": ""})
        item = dict(e)
        item["balde"] = triagem["balde"]
        item["resumo"] = triagem["resumo"]
        buckets[triagem["balde"]].append(item)

    return {"acao": buckets["acao"], "info": buckets["info"], "ruido": buckets["ruido"], "erros": errors}


# ── Ação autônoma segura: rascunho de resposta, NUNCA envia sozinho ───────
def draft_reply(remetente: str, assunto: str, trecho: str) -> str:
    """
    Prepara uma sugestão de resposta pro e-mail — o JARVIS já fez o
    trabalho de pensar/escrever, mas NUNCA envia sozinho (não temos nem
    capacidade de enviar e-mail, só de ler). Fica pronto pra você revisar,
    editar e mandar do seu jeito.
    """
    import llm_client

    system = (
        "Você escreve um RASCUNHO curto de resposta a um e-mail, em português, tom profissional "
        "mas natural. 2-4 frases. Não invente compromissos ou informações que não foram dadas — "
        "se precisar de mais contexto, deixe isso claro no rascunho (ex: peça mais detalhes)."
    )
    prompt = f"De: {remetente}\nAssunto: {assunto}\nTrecho: {trecho[:400]}"
    try:
        result = llm_client.chat(messages=[{"role": "user", "content": prompt}], tools=[], system=system)
        return result["text"].strip()
    except Exception:
        return ""
