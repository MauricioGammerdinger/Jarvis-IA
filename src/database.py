"""
Persistência do J.A.R.V.I.S. local — SQLite, um arquivo só (jarvis.db).

Sem servidor de banco pra configurar: quem baixar do GitHub só roda e o
arquivo é criado sozinho. Voltamos de Postgres pra SQLite porque agora tudo
roda na mesma máquina — não faz sentido a complexidade de um banco gerenciado
externo pra um app 100% local.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "jarvis.db"  # fica na raiz do projeto, não em src/ — não mexe onde as memórias já existentes estão salvas


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                created_at TEXT NOT NULL,
                embedding TEXT
            )
            """
        )
        try:
            conn.execute("ALTER TABLE memories ADD COLUMN embedding TEXT")
        except sqlite3.OperationalError:
            pass  # coluna já existe

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command TEXT NOT NULL,
                explicacao TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                result TEXT,
                created_at TEXT NOT NULL,
                resolved_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS email_triage_cache (
                message_id TEXT PRIMARY KEY,
                balde TEXT NOT NULL,
                resumo TEXT,
                triado_em TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news_cache (
                assunto TEXT PRIMARY KEY,
                headlines_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_state (
                agent_id TEXT PRIMARY KEY,
                last_run TEXT,
                status TEXT NOT NULL DEFAULT 'idle',
                detail TEXT,
                metric TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS article_summary_cache (
                link TEXT PRIMARY KEY,
                summary_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL,
                projeto TEXT NOT NULL,
                modelo TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_subscriptions (
                nome TEXT PRIMARY KEY,
                unidade TEXT NOT NULL,
                limite REAL NOT NULL,
                usado REAL NOT NULL DEFAULT 0,
                tipo_reset TEXT NOT NULL,
                reset_a_cada_horas REAL,
                reset_ancora TEXT NOT NULL,
                custo_mensal_usd REAL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL,
                titulo TEXT NOT NULL,
                mensagem TEXT NOT NULL,
                created_at TEXT NOT NULL,
                lida INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS commitments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                texto TEXT NOT NULL,
                prazo TEXT,
                status TEXT NOT NULL DEFAULT 'pendente',
                criado_em TEXT NOT NULL,
                cobrado INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # Coluna de controle: já criamos uma notificação pra esse e-mail?
        # Evita avisar 2x sobre o mesmo e-mail em rodadas seguintes da triagem.
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(email_triage_cache)").fetchall()]
        if "notificado" not in cols:
            conn.execute("ALTER TABLE email_triage_cache ADD COLUMN notificado INTEGER NOT NULL DEFAULT 0")
        conn.commit()


# ── Cache de triagem de e-mail (por Message-ID, nunca reprocessa) ─────────
def get_email_triage(message_ids: list[str]) -> dict[str, dict]:
    if not message_ids:
        return {}
    with _connect() as conn:
        placeholders = ",".join("?" * len(message_ids))
        rows = conn.execute(
            f"SELECT message_id, balde, resumo FROM email_triage_cache WHERE message_id IN ({placeholders})",
            message_ids,
        ).fetchall()
        return {r["message_id"]: {"balde": r["balde"], "resumo": r["resumo"]} for r in rows}


def save_email_triage(message_id: str, balde: str, resumo: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO email_triage_cache (message_id, balde, resumo, triado_em) VALUES (?, ?, ?, ?)",
            (message_id, balde, resumo, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


# ── Cache de notícias (por assunto, respeita intervalo de atualização) ────
def get_news_cache(assunto: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT headlines_json, fetched_at FROM news_cache WHERE assunto = ?", (assunto,)
        ).fetchone()
        if not row:
            return None
        return {"headlines": json.loads(row["headlines_json"]), "fetched_at": row["fetched_at"]}


def save_news_cache(assunto: str, headlines: list[dict]) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO news_cache (assunto, headlines_json, fetched_at) VALUES (?, ?, ?)",
            (assunto, json.dumps(headlines, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


# ── Estado dos agentes de fundo (prova de vida) ───────────────────────────
def record_agent_run(agent_id: str, status: str, detail: str = "", metric: str = "") -> None:
    """Grava que um agente rodou agora — a 'prova de vida' que o painel lê."""
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO agent_state (agent_id, last_run, status, detail, metric) VALUES (?, ?, ?, ?, ?)",
            (agent_id, datetime.now(timezone.utc).isoformat(), status, detail, metric),
        )
        conn.commit()


def get_agent_state(agent_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM agent_state WHERE agent_id = ?", (agent_id,)).fetchone()
        return dict(row) if row else None


def get_all_agent_states() -> dict[str, dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM agent_state").fetchall()
        return {r["agent_id"]: dict(r) for r in rows}


# ── Cache de resumo de artigos (por link, nunca resume duas vezes) ────────
def get_article_summary(link: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT summary_json FROM article_summary_cache WHERE link = ?", (link,)).fetchone()
        return json.loads(row["summary_json"]) if row else None


def save_article_summary(link: str, summary: dict) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO article_summary_cache (link, summary_json, created_at) VALUES (?, ?, ?)",
            (link, json.dumps(summary, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


# ── Uso de API de IA (custo pago por uso) ──────────────────────────────
def add_ai_usage(data: str, projeto: str, modelo: str, input_tokens: int, output_tokens: int) -> int:
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO ai_usage (data, projeto, modelo, input_tokens, output_tokens, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (data, projeto, modelo, input_tokens, output_tokens, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cursor.lastrowid


def list_ai_usage() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM ai_usage ORDER BY data DESC, id DESC").fetchall()
        return [dict(r) for r in rows]


def delete_ai_usage(usage_id: int) -> bool:
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM ai_usage WHERE id = ?", (usage_id,))
        conn.commit()
        return cursor.rowcount > 0


def update_ai_usage(usage_id: int, data: str, projeto: str, modelo: str, input_tokens: int, output_tokens: int) -> bool:
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE ai_usage SET data = ?, projeto = ?, modelo = ?, input_tokens = ?, output_tokens = ? WHERE id = ?",
            (data, projeto, modelo, input_tokens, output_tokens, usage_id),
        )
        conn.commit()
        return cursor.rowcount > 0


# ── Assinaturas de IA (cota do plano) ──────────────────────────────────
def upsert_subscription(nome: str, unidade: str, limite: float, tipo_reset: str, reset_a_cada_horas: float | None, reset_ancora: str, custo_mensal_usd: float = 0) -> None:
    with _connect() as conn:
        existente = conn.execute("SELECT usado FROM ai_subscriptions WHERE nome = ?", (nome,)).fetchone()
        usado = existente["usado"] if existente else 0
        conn.execute(
            """INSERT OR REPLACE INTO ai_subscriptions
               (nome, unidade, limite, usado, tipo_reset, reset_a_cada_horas, reset_ancora, custo_mensal_usd)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (nome, unidade, limite, usado, tipo_reset, reset_a_cada_horas, reset_ancora, custo_mensal_usd),
        )
        conn.commit()


def list_subscriptions() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM ai_subscriptions ORDER BY nome").fetchall()
        return [dict(r) for r in rows]


def get_subscription(nome: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM ai_subscriptions WHERE nome = ?", (nome,)).fetchone()
        return dict(row) if row else None


def delete_subscription(nome: str) -> bool:
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM ai_subscriptions WHERE nome = ?", (nome,))
        conn.commit()
        return cursor.rowcount > 0


def increment_subscription_usage(nome: str, quantidade: float) -> bool:
    with _connect() as conn:
        cursor = conn.execute("UPDATE ai_subscriptions SET usado = usado + ? WHERE nome = ?", (quantidade, nome))
        conn.commit()
        return cursor.rowcount > 0


def set_subscription_usage(nome: str, novo_ancora: str) -> bool:
    """Zera o uso e avança a âncora do ciclo (usado no reset, manual ou automático)."""
    with _connect() as conn:
        cursor = conn.execute("UPDATE ai_subscriptions SET usado = 0, reset_ancora = ? WHERE nome = ?", (novo_ancora, nome))
        conn.commit()
        return cursor.rowcount > 0


# ── Notificações proativas — "o JARVIS fala primeiro" ──────────────────
def create_notification(tipo: str, titulo: str, mensagem: str) -> int:
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO notifications (tipo, titulo, mensagem, created_at, lida) VALUES (?, ?, ?, ?, 0)",
            (tipo, titulo, mensagem, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cursor.lastrowid


def list_unread_notifications() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM notifications WHERE lida = 0 ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]


def list_all_notifications(limite: int = 50) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
        return [dict(r) for r in rows]


def mark_notification_read(notification_id: int) -> bool:
    with _connect() as conn:
        cursor = conn.execute("UPDATE notifications SET lida = 1 WHERE id = ?", (notification_id,))
        conn.commit()
        return cursor.rowcount > 0


def mark_all_notifications_read() -> int:
    with _connect() as conn:
        cursor = conn.execute("UPDATE notifications SET lida = 1 WHERE lida = 0")
        conn.commit()
        return cursor.rowcount


# ── Controle de "já avisei sobre esse e-mail?" ──────────────────────────
def get_unnotified_action_emails(message_ids: list[str]) -> list[str]:
    """De uma lista de Message-IDs (todos já classificados como 'ação'), devolve só os que AINDA não geraram notificação."""
    if not message_ids:
        return []
    with _connect() as conn:
        placeholders = ",".join("?" * len(message_ids))
        rows = conn.execute(
            f"SELECT message_id FROM email_triage_cache WHERE message_id IN ({placeholders}) AND notificado = 0",
            message_ids,
        ).fetchall()
        return [r["message_id"] for r in rows]


def mark_emails_notified(message_ids: list[str]) -> None:
    if not message_ids:
        return
    with _connect() as conn:
        placeholders = ",".join("?" * len(message_ids))
        conn.execute(f"UPDATE email_triage_cache SET notificado = 1 WHERE message_id IN ({placeholders})", message_ids)
        conn.commit()


# ── Compromissos — "Second Brain ativo", cobra pendências sozinho ────────
def add_commitment(texto: str, prazo: str | None = None) -> int:
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO commitments (texto, prazo, status, criado_em, cobrado) VALUES (?, ?, 'pendente', ?, 0)",
            (texto, prazo, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cursor.lastrowid


def list_commitments(status: str | None = None) -> list[dict]:
    with _connect() as conn:
        if status:
            rows = conn.execute("SELECT * FROM commitments WHERE status = ? ORDER BY prazo IS NULL, prazo ASC", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM commitments ORDER BY prazo IS NULL, prazo ASC").fetchall()
        return [dict(r) for r in rows]


def complete_commitment(commitment_id: int) -> bool:
    with _connect() as conn:
        cursor = conn.execute("UPDATE commitments SET status = 'concluido' WHERE id = ?", (commitment_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_pending_commitments_needing_followup(horas_de_antecedencia: float = 24) -> list[dict]:
    """Pendências com prazo VENCIDO ou PRÓXIMO (dentro de `horas_de_antecedencia`), ainda não cobradas."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM commitments WHERE status = 'pendente' AND cobrado = 0 AND prazo IS NOT NULL"
        ).fetchall()
    resultado = []
    limite = datetime.now(timezone.utc) + timedelta(hours=horas_de_antecedencia)
    for r in rows:
        c = dict(r)
        try:
            prazo_dt = datetime.fromisoformat(c["prazo"])
            if prazo_dt.tzinfo is None:
                prazo_dt = prazo_dt.replace(tzinfo=timezone.utc)
            if prazo_dt <= limite:  # vencido OU dentro da janela de antecedência
                resultado.append(c)
        except ValueError:
            continue  # prazo mal formatado — ignora em vez de quebrar
    return resultado


def mark_commitment_followed_up(commitment_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE commitments SET cobrado = 1 WHERE id = ?", (commitment_id,))
        conn.commit()


# ── Memórias ─────────────────────────────────────────────────────────────
def add_memory(content: str, category: str = "general", embedding: str | None = None) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO memories (content, category, created_at, embedding) VALUES (?, ?, ?, ?)",
            (content, category, datetime.now(timezone.utc).isoformat(), embedding),
        )
        conn.commit()
        return cur.lastrowid


def all_memories_with_embeddings() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, content, category, created_at, embedding FROM memories WHERE embedding IS NOT NULL"
        ).fetchall()
        return [dict(r) for r in rows]


def list_memories() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, content, category, created_at FROM memories ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def search_memories(query: str, limit: int = 5) -> list[dict]:
    """Busca por palavra-chave simples — fallback quando embeddings não estão disponíveis."""
    terms = [w for w in query.split() if w.strip()]
    if not terms:
        return []
    with _connect() as conn:
        conditions = " AND ".join(["content LIKE ?"] * len(terms))
        params = [f"%{t}%" for t in terms]
        rows = conn.execute(
            f"SELECT id, content, category, created_at FROM memories WHERE {conditions} "
            f"ORDER BY id DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_memory(memory_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        conn.commit()
        return cur.rowcount > 0


def count_memories() -> int:
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]


# ── Conversas ────────────────────────────────────────────────────────────
def append_message(session_id: str, role: str, content) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, json.dumps(content), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def get_history(session_id: str, limit: int = 30) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        rows = list(reversed(rows))
        return [{"role": r["role"], "content": json.loads(r["content"])} for r in rows]


def list_sessions() -> list[str]:
    with _connect() as conn:
        rows = conn.execute("SELECT DISTINCT session_id FROM messages").fetchall()
        return [r["session_id"] for r in rows]


# ── Comandos — agora simples, porque roda tudo na mesma máquina ──────────
# Sem "agente remoto": pending -> approved (e já executa na hora) ou rejected.
def create_pending_command(command: str, explicacao: str) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO pending_commands (command, explicacao, status, created_at) VALUES (?, ?, 'pending', ?)",
            (command, explicacao, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cur.lastrowid


def get_pending_command(command_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM pending_commands WHERE id = ?", (command_id,)).fetchone()
        return dict(row) if row else None


def list_pending_commands(status: str | None = None) -> list[dict]:
    with _connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM pending_commands WHERE status = ? ORDER BY id DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM pending_commands ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


def resolve_command(command_id: int, status: str, result: str | None) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE pending_commands SET status = ?, result = ?, resolved_at = ? WHERE id = ?",
            (status, result, datetime.now(timezone.utc).isoformat(), command_id),
        )
        conn.commit()
