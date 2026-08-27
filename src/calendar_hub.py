"""
Central de Agenda — mescla várias agendas do Google (contas diferentes
inclusive) numa timeline única, via "endereço secreto em formato iCal"
(link de leitura, sem precisar de OAuth nem Google Cloud Console).

Onde pegar o link: Google Agenda no computador → ⚙ Configurações →
clica na agenda na lista à esquerda → "Integrar agenda" → copia o
"Endereço secreto em formato iCal".

Usa bibliotecas testadas (icalendar + recurring_ical_events) em vez de
parsear ICS/RRULE na mão — é exatamente o tipo de coisa que quebra em
projeto amador (fusos horários, eventos recorrentes, EXDATE).
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import recurring_ical_events
import requests
from icalendar import Calendar

CALENDARS_CONFIG_PATH = Path(__file__).parent.parent / "calendars_config.json"
DEFAULT_TIMEZONE = "America/Sao_Paulo"


def load_calendars_config() -> list[dict]:
    if not CALENDARS_CONFIG_PATH.exists():
        return []
    with open(CALENDARS_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_calendars_config(calendars: list[dict]) -> None:
    with open(CALENDARS_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(calendars, f, ensure_ascii=False, indent=2)


def add_calendar(nome: str, cor: str, ics_url: str) -> None:
    calendars = load_calendars_config()
    calendars = [c for c in calendars if c["nome"] != nome]  # substitui se já existir
    calendars.append({"nome": nome, "cor": cor, "ics_url": ics_url})
    save_calendars_config(calendars)


def remove_calendar(nome: str) -> bool:
    calendars = load_calendars_config()
    filtered = [c for c in calendars if c["nome"] != nome]
    if len(filtered) == len(calendars):
        return False
    save_calendars_config(filtered)
    return True


def _fetch_ics(url: str, timeout: int = 10) -> str:
    # O Google recusa requisições sem User-Agent de navegador
    headers = {"User-Agent": "Mozilla/5.0 (compatible; JARVIS-IA/1.0)"}
    resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    return resp.text


def get_merged_events(days_ahead: int = 7) -> list[dict]:
    """
    Busca eventos de TODAS as agendas configuradas e mescla em ordem
    cronológica. Se uma agenda falhar (link inválido, fora do ar), NÃO
    derruba as outras — o erro fica marcado só naquela entrada.
    """
    calendars = load_calendars_config()
    if not calendars:
        return []

    tz = ZoneInfo(DEFAULT_TIMEZONE)
    now = datetime.now(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=days_ahead)

    all_events = []
    for cal_config in calendars:
        try:
            ics_text = _fetch_ics(cal_config["ics_url"])
            cal = Calendar.from_ical(ics_text)
            events = recurring_ical_events.of(cal, skip_bad_series=True).between(start, end)

            for event in events:
                summary = str(event.get("SUMMARY", "(sem título)"))
                location = str(event.get("LOCATION", "")) or None
                dtstart_raw = event["DTSTART"].dt

                is_all_day = not isinstance(dtstart_raw, datetime)
                if is_all_day:
                    start_display = "DIA TODO"
                    sort_key = datetime.combine(dtstart_raw, datetime.min.time()).replace(tzinfo=tz)
                else:
                    dtstart = dtstart_raw if dtstart_raw.tzinfo else dtstart_raw.replace(tzinfo=tz)
                    dtstart = dtstart.astimezone(tz)
                    start_display = dtstart.strftime("%H:%M")
                    sort_key = dtstart

                all_events.append({
                    "titulo": summary,
                    "local": location,
                    "inicio_iso": sort_key.isoformat(),
                    "inicio_display": start_display,
                    "dia_todo": is_all_day,
                    "agenda_nome": cal_config["nome"],
                    "agenda_cor": cal_config["cor"],
                    "_sort_key": sort_key,
                })
        except Exception as e:
            all_events.append({
                "erro": f"Falha ao carregar agenda '{cal_config['nome']}': {e}",
                "agenda_nome": cal_config["nome"],
                "_sort_key": datetime.max.replace(tzinfo=tz),
            })

    all_events.sort(key=lambda e: e["_sort_key"])
    for e in all_events:
        del e["_sort_key"]

    return all_events


def get_today_events() -> list[dict]:
    """Só os eventos de hoje — usado no comando de voz e no Morning Digest."""
    tz = ZoneInfo(DEFAULT_TIMEZONE)
    today = datetime.now(tz).date()
    all_events = get_merged_events(days_ahead=1)
    return [
        e for e in all_events
        if "erro" in e or datetime.fromisoformat(e["inicio_iso"]).date() == today
    ]


def get_next_event() -> dict | None:
    """O próximo evento a partir de agora, com contagem regressiva."""
    tz = ZoneInfo(DEFAULT_TIMEZONE)
    now = datetime.now(tz)
    events = get_merged_events(days_ahead=7)
    for e in events:
        if "erro" in e:
            continue
        event_time = datetime.fromisoformat(e["inicio_iso"])
        if event_time >= now:
            delta = event_time - now
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            minutes = remainder // 60
            e = dict(e)
            e["countdown"] = f"{hours}h {minutes}min" if hours else f"{minutes}min"
            return e
    return None


def format_compact_for_prompt(days_ahead: int = 1) -> str:
    """Formato compacto ('09:00 reunião X · 14:00 dentista') pro system prompt."""
    events = get_today_events() if days_ahead == 1 else get_merged_events(days_ahead)
    valid = [e for e in events if "erro" not in e]
    if not valid:
        return "Nenhum evento."
    return " · ".join(f"{e['inicio_display']} {e['titulo']}" for e in valid[:15])
