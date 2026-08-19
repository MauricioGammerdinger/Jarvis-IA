"""
Integração com o Google Calendar.

⚠️ PRÉ-REQUISITO OBRIGATÓRIO, só você pode fazer: criar um projeto no Google
Cloud Console e gerar credenciais OAuth. Isso é uma exigência do próprio
Google pra qualquer aplicativo que acesse o Calendar de alguém — não existe
como pular essa etapa. Veja o passo a passo completo no README principal,
seção "Integração com Google Calendar".

Depois de ter o `credentials.json` (baixado do Google Cloud Console) na raiz
do projeto, rode uma vez:
    python scripts/setup_google_calendar.py
Isso abre o navegador pra você autorizar, e salva um `token.json` — depois
disso, o JARVIS usa esse token sozinho, sem abrir navegador de novo (a menos
que o token expire e precise renovar, o que a biblioteca faz sozinha).
"""

import os
from datetime import datetime, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]
PROJECT_ROOT = Path(__file__).parent.parent
TOKEN_PATH = PROJECT_ROOT / "token.json"
CREDENTIALS_PATH = PROJECT_ROOT / "credentials.json"


def _get_credentials() -> Credentials:
    if not TOKEN_PATH.exists():
        raise RuntimeError(
            "Google Calendar não configurado ainda. Rode 'python scripts/setup_google_calendar.py' "
            "primeiro (precisa do credentials.json na raiz do projeto — veja o README)."
        )

    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    return creds


def _get_service():
    creds = _get_credentials()
    return build("calendar", "v3", credentials=creds)


def list_upcoming_events(max_results: int = 10) -> list[dict]:
    """Lista os próximos eventos do calendário principal do usuário."""
    service = _get_service()
    now = datetime.utcnow().isoformat() + "Z"

    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    events = events_result.get("items", [])

    return [
        {
            "id": e["id"],
            "titulo": e.get("summary", "(sem título)"),
            "inicio": e["start"].get("dateTime", e["start"].get("date")),
            "fim": e["end"].get("dateTime", e["end"].get("date")),
        }
        for e in events
    ]


def create_event(title: str, start_iso: str, duration_minutes: int = 60, description: str = "") -> dict:
    """
    Cria um evento novo no calendário principal do usuário.

    start_iso: data/hora de início em formato ISO (ex: "2026-08-20T14:00:00").
    """
    service = _get_service()

    start_dt = datetime.fromisoformat(start_iso)
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    event = {
        "summary": title,
        "description": description,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "America/Sao_Paulo"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "America/Sao_Paulo"},
    }

    created = service.events().insert(calendarId="primary", body=event).execute()
    return {"id": created["id"], "link": created.get("htmlLink", "")}


def is_configured() -> bool:
    """Confere rapidamente se a integração já foi configurada, sem lançar erro."""
    return TOKEN_PATH.exists()
