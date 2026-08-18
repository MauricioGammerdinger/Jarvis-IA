"""
Persistência do J.A.R.V.I.S. local — SQLite, um arquivo só (jarvis.db).

Sem servidor de banco pra configurar: quem baixar do GitHub só roda e o
arquivo é criado sozinho. Voltamos de Postgres pra SQLite porque agora tudo
roda na mesma máquina — não faz sentido a complexidade de um banco gerenciado
externo pra um app 100% local.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "jarvis.db"


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
