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
        try:
            # Controla quando cada memória foi puxada de volta numa conversa
            # sozinha ("Second Brain ativo") — evita repetir a mesma toda hora.
            conn.execute("ALTER TABLE memories ADD COLUMN ultima_cobranca_em TEXT")
        except sqlite3.OperationalError:
            pass  # coluna já existe
        try:
            # Sincronização entre PCs: um ID numérico (autoincrement) colide
            # entre máquinas diferentes (os dois podem ter um registro com
            # id=5, sendo coisas totalmente diferentes) — um UUID é único de
            # verdade, independente de onde foi criado.
            conn.execute("ALTER TABLE memories ADD COLUMN sync_uuid TEXT")
            conn.execute("ALTER TABLE memories ADD COLUMN origem_maquina TEXT")
        except sqlite3.OperationalError:
            pass  # coluna já existe
        _backfill_sync_uuid(conn, "memories")

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
        try:
            conn.execute("ALTER TABLE commitments ADD COLUMN sync_uuid TEXT")
            conn.execute("ALTER TABLE commitments ADD COLUMN origem_maquina TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            # Sem isso, a retrospectiva semanal não tem como saber QUANDO
            # um compromisso foi concluído — só que está concluído agora.
            conn.execute("ALTER TABLE commitments ADD COLUMN concluido_em TEXT")
        except sqlite3.OperationalError:
            pass
        _backfill_sync_uuid(conn, "commitments")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS people (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                relacao TEXT,
                aniversario TEXT,
                notas TEXT,
                criado_em TEXT NOT NULL,
                ultimo_lembrete_ano INTEGER
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS goal_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id INTEGER NOT NULL,
                valor REAL,
                nota TEXT,
                criado_em TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS routines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE,
                passos TEXT NOT NULL,
                criado_em TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL,
                categoria TEXT NOT NULL,
                valor REAL NOT NULL,
                descricao TEXT,
                data TEXT NOT NULL,
                criado_em TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS category_budgets (
                categoria TEXT PRIMARY KEY,
                limite_mensal REAL NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL,
                descricao TEXT NOT NULL,
                caminho_arquivo TEXT,
                backup_path TEXT,
                created_at TEXT NOT NULL,
                desfeito INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS voice_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                estado TEXT NOT NULL DEFAULT 'idle',
                updated_at TEXT NOT NULL
            )
            """
        )
        # Coluna de controle: já criamos uma notificação pra esse e-mail?
        # Evita avisar 2x sobre o mesmo e-mail em rodadas seguintes da triagem.
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(email_triage_cache)").fetchall()]
        if "notificado" not in cols:
            conn.execute("ALTER TABLE email_triage_cache ADD COLUMN notificado INTEGER NOT NULL DEFAULT 0")
        conn.commit()


def _backfill_sync_uuid(conn, tabela: str) -> None:
    """
    Preenche sync_uuid/origem_maquina pra registros que já existiam antes
    dessa coluna existir — sem isso, tudo que já estava salvo ficaria de
    fora da sincronização entre PCs pra sempre.
    """
    import uuid as uuid_module

    machine_id = _get_or_create_machine_id()
    rows = conn.execute(f"SELECT id FROM {tabela} WHERE sync_uuid IS NULL").fetchall()
    for row in rows:
        conn.execute(
            f"UPDATE {tabela} SET sync_uuid = ?, origem_maquina = ? WHERE id = ?",
            (str(uuid_module.uuid4()), machine_id, row["id"]),
        )


def _get_or_create_machine_id() -> str:
    """Identificador único e ESTÁVEL dessa máquina — gerado uma vez, guardado num arquivo local, nunca muda depois."""
    import uuid as uuid_module

    machine_id_path = DB_PATH.parent / "machine_id.txt"
    if machine_id_path.exists():
        return machine_id_path.read_text(encoding="utf-8").strip()
    novo_id = str(uuid_module.uuid4())[:8]
    machine_id_path.write_text(novo_id, encoding="utf-8")
    return novo_id


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
    import uuid as uuid_module

    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO commitments (texto, prazo, status, criado_em, cobrado, sync_uuid, origem_maquina) VALUES (?, ?, 'pendente', ?, 0, ?, ?)",
            (texto, prazo, datetime.now(timezone.utc).isoformat(), str(uuid_module.uuid4()), _get_or_create_machine_id()),
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


def get_weekly_retrospective_data(dias: int = 7) -> dict:
    """Junta o que aconteceu na última semana — usado pra montar a retrospectiva."""
    with _connect() as conn:
        corte = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()

        concluidos = conn.execute(
            "SELECT texto, concluido_em FROM commitments WHERE status = 'concluido' AND concluido_em >= ? ORDER BY concluido_em",
            (corte,),
        ).fetchall()
        ainda_pendentes = conn.execute(
            "SELECT texto, prazo FROM commitments WHERE status = 'pendente'"
        ).fetchall()
        metas_novas = conn.execute(
            "SELECT content FROM memories WHERE category = 'metas' AND created_at >= ? ORDER BY created_at",
            (corte,),
        ).fetchall()

        return {
            "compromissos_concluidos": [dict(r) for r in concluidos],
            "compromissos_ainda_pendentes": [dict(r) for r in ainda_pendentes],
            "metas_novas": [dict(r) for r in metas_novas],
        }


def complete_commitment(commitment_id: int) -> bool:
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE commitments SET status = 'concluido', concluido_em = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), commitment_id),
        )
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
    import uuid as uuid_module

    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO memories (content, category, created_at, embedding, sync_uuid, origem_maquina) VALUES (?, ?, ?, ?, ?, ?)",
            (content, category, datetime.now(timezone.utc).isoformat(), embedding, str(uuid_module.uuid4()), _get_or_create_machine_id()),
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


# ── Sincronização entre PCs — leitura/escrita completas, com sync_uuid ────
def get_memories_for_sync() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, content, category, created_at, sync_uuid, origem_maquina FROM memories"
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_memory_from_sync(sync_uuid: str, content: str, category: str, created_at: str, origem_maquina: str) -> bool:
    """Insere uma memória vinda de outra máquina, só se esse sync_uuid ainda não existir localmente. Devolve True se inseriu algo novo."""
    with _connect() as conn:
        existe = conn.execute("SELECT 1 FROM memories WHERE sync_uuid = ?", (sync_uuid,)).fetchone()
        if existe:
            return False
        conn.execute(
            "INSERT INTO memories (content, category, created_at, sync_uuid, origem_maquina) VALUES (?, ?, ?, ?, ?)",
            (content, category, created_at, sync_uuid, origem_maquina),
        )
        conn.commit()
        return True


def get_commitments_for_sync() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, texto, prazo, status, criado_em, cobrado, sync_uuid, origem_maquina FROM commitments"
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_commitment_from_sync(sync_uuid: str, texto: str, prazo: str | None, status: str, criado_em: str, origem_maquina: str) -> str:
    """
    Insere ou atualiza um compromisso vindo de outra máquina.
    - Se não existe localmente: insere.
    - Se existe e a versão remota está 'concluido' mas a local ainda 'pendente':
      marca como concluído também (propagação só nesse sentido — nunca reabre
      um compromisso que já foi concluído localmente, mesmo que a cópia remota
      esteja desatualizada).
    Devolve 'inserido', 'atualizado' ou 'sem_mudanca'.
    """
    with _connect() as conn:
        local = conn.execute("SELECT status FROM commitments WHERE sync_uuid = ?", (sync_uuid,)).fetchone()
        if not local:
            conn.execute(
                "INSERT INTO commitments (texto, prazo, status, criado_em, cobrado, sync_uuid, origem_maquina) VALUES (?, ?, ?, ?, 0, ?, ?)",
                (texto, prazo, status, criado_em, sync_uuid, origem_maquina),
            )
            conn.commit()
            return "inserido"
        if status == "concluido" and local["status"] == "pendente":
            conn.execute(
                "UPDATE commitments SET status = 'concluido', concluido_em = ? WHERE sync_uuid = ?",
                (datetime.now(timezone.utc).isoformat(), sync_uuid),
            )
            conn.commit()
            return "atualizado"
        return "sem_mudanca"


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


# ── Second Brain ativo: "puxa fatos sozinho" ────────────────────────────
def get_memory_for_checkin(dias_minimos_entre_cobrancas: int = 20) -> dict | None:
    """
    Escolhe UMA memória pra trazer de volta numa conversa, sem o usuário
    perguntar — prioriza a categoria 'metas' (é o que mais faz sentido
    "cobrar"), pega a que está há mais tempo sem ser mencionada (ou nunca
    foi), e nunca repete a mesma antes de `dias_minimos_entre_cobrancas`
    dias — senão vira spam da mesma coisa toda hora.
    """
    with _connect() as conn:
        limite = (datetime.now(timezone.utc) - timedelta(days=dias_minimos_entre_cobrancas)).isoformat()
        row = conn.execute(
            """
            SELECT * FROM memories
            WHERE category = 'metas'
              AND (ultima_cobranca_em IS NULL OR ultima_cobranca_em < ?)
            ORDER BY ultima_cobranca_em IS NOT NULL, ultima_cobranca_em ASC, created_at ASC
            LIMIT 1
            """,
            (limite,),
        ).fetchone()
        return dict(row) if row else None


def mark_memory_checked_in(memory_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE memories SET ultima_cobranca_em = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), memory_id),
        )
        conn.commit()


# ── Trilha de auditoria — tudo que o JARVIS fez sozinho, revisável ────────
def add_audit_entry(tipo: str, descricao: str, caminho_arquivo: str | None = None, backup_path: str | None = None) -> int:
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO audit_log (tipo, descricao, caminho_arquivo, backup_path, created_at, desfeito) VALUES (?, ?, ?, ?, ?, 0)",
            (tipo, descricao, caminho_arquivo, backup_path, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cursor.lastrowid


def list_audit_log(limite: int = 100) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
        return [dict(r) for r in rows]


def get_audit_entry(entry_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM audit_log WHERE id = ?", (entry_id,)).fetchone()
        return dict(row) if row else None


def mark_audit_entry_undone(entry_id: int) -> bool:
    with _connect() as conn:
        cursor = conn.execute("UPDATE audit_log SET desfeito = 1 WHERE id = ?", (entry_id,))
        conn.commit()
        return cursor.rowcount > 0


# ── Pessoas importantes e aniversários ────────────────────────────────
def add_person(nome: str, relacao: str | None = None, aniversario: str | None = None, notas: str | None = None) -> int:
    """`aniversario` aceita 'YYYY-MM-DD' (se souber o ano) ou só 'MM-DD' (se não souber)."""
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO people (nome, relacao, aniversario, notas, criado_em) VALUES (?, ?, ?, ?, ?)",
            (nome, relacao, aniversario, notas, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cursor.lastrowid


def list_people() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM people ORDER BY nome").fetchall()
        return [dict(r) for r in rows]


def delete_person(person_id: int) -> bool:
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM people WHERE id = ?", (person_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_people_needing_birthday_reminder(dias_de_antecedencia: int = 7) -> list[dict]:
    """
    Pessoas com aniversário dentro da janela de antecedência, que ainda
    não foram lembradas ESSE ANO (`ultimo_lembrete_ano` != ano atual) —
    isso permite lembrar de novo todo ano, sem repetir dentro do mesmo ano.
    """
    with _connect() as conn:
        pessoas = conn.execute("SELECT * FROM people WHERE aniversario IS NOT NULL").fetchall()

    hoje = datetime.now().date()
    ano_atual = hoje.year
    resultado = []

    for p in pessoas:
        p = dict(p)
        if p["ultimo_lembrete_ano"] == ano_atual:
            continue  # já lembrou esse ano

        try:
            partes = p["aniversario"].split("-")
            mes, dia = int(partes[-2]), int(partes[-1])
        except (ValueError, IndexError):
            continue  # data mal formatada — ignora em vez de quebrar

        try:
            proximo_aniversario = datetime(ano_atual, mes, dia).date()
        except ValueError:
            continue  # data inválida (ex: 30 de fevereiro)

        if proximo_aniversario < hoje:
            proximo_aniversario = datetime(ano_atual + 1, mes, dia).date()

        dias_ate = (proximo_aniversario - hoje).days
        if 0 <= dias_ate <= dias_de_antecedencia:
            p["dias_ate_aniversario"] = dias_ate
            resultado.append(p)

    return resultado


def mark_birthday_reminded(person_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE people SET ultimo_lembrete_ano = ? WHERE id = ?", (datetime.now().year, person_id))
        conn.commit()


# ── Progresso de metas — pro gráfico ao longo do tempo ────────────────
def find_or_create_goal(texto_meta: str, similarity_threshold: float = 0.4) -> int:
    """
    Encontra uma meta já existente (categoria 'metas') parecida com o
    texto dado (comparação simples via difflib, biblioteca padrão — sem
    dependência de NLP), ou cria uma nova se não achar nada parecido o
    suficiente. Evita duplicar "correr 5km" e "correr cinco quilômetros"
    como metas diferentes.
    """
    import difflib

    with _connect() as conn:
        metas = conn.execute("SELECT id, content FROM memories WHERE category = 'metas'").fetchall()

    melhor_id = None
    melhor_similaridade = 0.0
    for m in metas:
        similaridade = difflib.SequenceMatcher(None, texto_meta.lower(), m["content"].lower()).ratio()
        if similaridade > melhor_similaridade:
            melhor_similaridade = similaridade
            melhor_id = m["id"]

    if melhor_id is not None and melhor_similaridade >= similarity_threshold:
        return melhor_id

    return add_memory(texto_meta, "metas")


def add_goal_progress(memory_id: int, valor: float | None = None, nota: str | None = None) -> int:
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO goal_progress (memory_id, valor, nota, criado_em) VALUES (?, ?, ?, ?)",
            (memory_id, valor, nota, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cursor.lastrowid


def get_goal_progress(memory_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM goal_progress WHERE memory_id = ? ORDER BY criado_em", (memory_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def list_goals_with_progress_count() -> list[dict]:
    """Metas + quantos registros de progresso cada uma tem — pra saber quais já têm gráfico pra mostrar."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT m.id, m.content, COUNT(g.id) as total_registros
            FROM memories m
            LEFT JOIN goal_progress g ON g.memory_id = m.id
            WHERE m.category = 'metas'
            GROUP BY m.id
            ORDER BY m.id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


# ── Rotinas — sequência de ações encadeadas, disparadas por voz ─────────
def add_routine(nome: str, passos: list[dict]) -> int:
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO routines (nome, passos, criado_em) VALUES (?, ?, ?) "
            "ON CONFLICT(nome) DO UPDATE SET passos = excluded.passos",
            (nome, json.dumps(passos, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cursor.lastrowid


def get_routine(nome: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM routines WHERE nome = ?", (nome,)).fetchone()
        if not row:
            return None
        resultado = dict(row)
        resultado["passos"] = json.loads(resultado["passos"])
        return resultado


def list_routines() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM routines ORDER BY nome").fetchall()
        resultado = []
        for r in rows:
            d = dict(r)
            d["passos"] = json.loads(d["passos"])
            resultado.append(d)
        return resultado


def delete_routine(nome: str) -> bool:
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM routines WHERE nome = ?", (nome,))
        conn.commit()
        return cursor.rowcount > 0


# ── Dashboard financeiro geral (não só IA) ─────────────────────────────
def add_transaction(tipo: str, categoria: str, valor: float, descricao: str | None, data: str) -> int:
    """`tipo` é 'receita' ou 'despesa'."""
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO transactions (tipo, categoria, valor, descricao, data, criado_em) VALUES (?, ?, ?, ?, ?, ?)",
            (tipo, categoria, valor, descricao, data, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cursor.lastrowid


def list_transactions(mes: str | None = None) -> list[dict]:
    """`mes` no formato 'YYYY-MM'. Sem isso, lista tudo."""
    with _connect() as conn:
        if mes:
            rows = conn.execute(
                "SELECT * FROM transactions WHERE data LIKE ? ORDER BY data DESC", (f"{mes}%",)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM transactions ORDER BY data DESC").fetchall()
        return [dict(r) for r in rows]


def delete_transaction(transaction_id: int) -> bool:
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
        conn.commit()
        return cursor.rowcount > 0


def set_category_budget(categoria: str, limite_mensal: float) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO category_budgets (categoria, limite_mensal) VALUES (?, ?) "
            "ON CONFLICT(categoria) DO UPDATE SET limite_mensal = excluded.limite_mensal",
            (categoria, limite_mensal),
        )
        conn.commit()


def get_category_budgets() -> dict[str, float]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM category_budgets").fetchall()
        return {r["categoria"]: r["limite_mensal"] for r in rows}


# ── Estado de voz — ponte entre o processo do listener e a FACE no navegador ──
VOICE_STATE_STALE_SECONDS = 30  # se não atualizar em 30s, assume que travou/caiu e volta pro idle


def set_voice_state(estado: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO voice_state (id, estado, updated_at) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET estado = excluded.estado, updated_at = excluded.updated_at",
            (estado, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def get_voice_state() -> str:
    """Devolve o estado atual — mas se faz tempo demais desde a última atualização (processo travou/caiu), assume 'idle' em vez de ficar preso num estado errado pra sempre."""
    with _connect() as conn:
        row = conn.execute("SELECT estado, updated_at FROM voice_state WHERE id = 1").fetchone()
        if not row:
            return "idle"
        atualizado_em = datetime.fromisoformat(row["updated_at"])
        if atualizado_em.tzinfo is None:
            atualizado_em = atualizado_em.replace(tzinfo=timezone.utc)
        segundos_desde_atualizacao = (datetime.now(timezone.utc) - atualizado_em).total_seconds()
        if segundos_desde_atualizacao > VOICE_STATE_STALE_SECONDS:
            return "idle"
        return row["estado"]


def get_full_timeline(limite: int = 100) -> list[dict]:
    """
    Junta a trilha de auditoria (ações com efeito, tipo edição de arquivo)
    e as notificações proativas (avisos, sem efeito colateral) numa única
    linha do tempo cronológica — "tudo que o JARVIS fez sozinho", num
    lugar só, do mais recente pro mais antigo.
    """
    auditoria = [{**a, "origem": "auditoria"} for a in list_audit_log(limite)]
    notifs = [{**n, "origem": "notificacao", "descricao": f"{n['titulo']}: {n['mensagem']}"} for n in list_all_notifications(limite)]
    combinado = auditoria + notifs
    combinado.sort(key=lambda x: x["created_at"], reverse=True)
    return combinado[:limite]


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
