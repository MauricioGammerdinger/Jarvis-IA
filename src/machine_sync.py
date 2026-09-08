"""
Sincronização entre PCs — via arquivo JSON numa pasta compartilhada (ex:
dentro do OneDrive, que já sincroniza sozinho entre as máquinas). NÃO
sincroniza o banco SQLite diretamente — isso é arriscado de verdade
(sincronização de arquivo no meio de uma escrita pode corromper o banco,
problema conhecido de SQLite dentro de pasta de nuvem). Em vez disso,
cada máquina exporta pra um arquivo PRÓPRIO (nomeado com o ID dela), e lê
os arquivos das OUTRAS máquinas pra importar só o que ainda não tem.

Pra ativar: define JARVIS_SYNC_FOLDER no .env, apontando pra uma pasta
dentro do OneDrive (ou qualquer outra pasta que sincronize sozinha entre
as máquinas). Sem essa variável, a sincronização fica desligada — não
tenta nada, não quebra nada.
"""

import json
import os
from pathlib import Path

SYNC_FOLDER_ENV = "JARVIS_SYNC_FOLDER"


def get_sync_folder() -> Path | None:
    caminho = os.environ.get(SYNC_FOLDER_ENV, "").strip()
    if not caminho:
        return None
    return Path(caminho)


def is_sync_enabled() -> bool:
    return get_sync_folder() is not None


def export_local_data() -> dict:
    """Exporta os dados locais pra um arquivo JSON na pasta compartilhada, nomeado com o ID dessa máquina."""
    import database as db

    pasta = get_sync_folder()
    if not pasta:
        return {"ok": False, "motivo": "Sincronização não configurada (defina JARVIS_SYNC_FOLDER)."}

    pasta.mkdir(parents=True, exist_ok=True)
    machine_id = db._get_or_create_machine_id()

    dados = {
        "machine_id": machine_id,
        "memories": db.get_memories_for_sync(),
        "commitments": db.get_commitments_for_sync(),
    }

    # Escreve num arquivo temporário e move por cima — evita que o
    # OneDrive tente sincronizar um arquivo pela metade, no meio da escrita.
    arquivo_final = pasta / f"jarvis_sync_{machine_id}.json"
    arquivo_temp = pasta / f"jarvis_sync_{machine_id}.tmp"
    with open(arquivo_temp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    arquivo_temp.replace(arquivo_final)

    return {"ok": True, "arquivo": str(arquivo_final), "memories": len(dados["memories"]), "commitments": len(dados["commitments"])}


def import_remote_data() -> dict:
    """Lê os arquivos de sincronização de OUTRAS máquinas (nunca o próprio) e importa só o que ainda não existe localmente."""
    import database as db

    pasta = get_sync_folder()
    if not pasta or not pasta.exists():
        return {"ok": False, "motivo": "Pasta de sincronização não configurada ou não existe ainda."}

    machine_id = db._get_or_create_machine_id()
    memories_novas = 0
    commitments_novos = 0
    commitments_atualizados = 0
    maquinas_vistas = []
    arquivos_com_problema = []

    for arquivo in sorted(pasta.glob("jarvis_sync_*.json")):
        if arquivo.stem == f"jarvis_sync_{machine_id}":
            continue  # nunca importa o próprio arquivo

        try:
            with open(arquivo, encoding="utf-8") as f:
                dados = json.load(f)
        except Exception:
            # Arquivo corrompido ou sendo escrito nesse instante pela outra
            # máquina — não é erro fatal, só pula essa rodada e tenta de
            # novo no próximo ciclo do job de fundo.
            arquivos_com_problema.append(arquivo.name)
            continue

        for m in dados.get("memories", []):
            if not m.get("sync_uuid"):
                continue
            if db.upsert_memory_from_sync(m["sync_uuid"], m["content"], m["category"], m["created_at"], m.get("origem_maquina", "?")):
                memories_novas += 1

        for c in dados.get("commitments", []):
            if not c.get("sync_uuid"):
                continue
            resultado = db.upsert_commitment_from_sync(
                c["sync_uuid"], c["texto"], c.get("prazo"), c["status"], c["criado_em"], c.get("origem_maquina", "?")
            )
            if resultado == "inserido":
                commitments_novos += 1
            elif resultado == "atualizado":
                commitments_atualizados += 1

        maquinas_vistas.append(dados.get("machine_id", arquivo.stem))

    return {
        "ok": True,
        "maquinas": maquinas_vistas,
        "memories_novas": memories_novas,
        "commitments_novos": commitments_novos,
        "commitments_atualizados": commitments_atualizados,
        "arquivos_com_problema": arquivos_com_problema,
    }


def sync_now() -> dict:
    """Exporta e importa numa tacada só — é isso que o job de fundo chama."""
    return {"export": export_local_data(), "import": import_remote_data()}
