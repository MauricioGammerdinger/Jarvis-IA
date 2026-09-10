"""
Reconhecimento de quem está falando — só pra PERSONALIZAÇÃO (nome,
tratamento), NUNCA pra restringir ações ou qualquer coisa de segurança.
Usa características clássicas de voz (MFCC — coeficientes que capturam
o timbre/formato do trato vocal), não uma rede neural pesada — é uma
abordagem mais simples e mais leve, adequada pro caso de uso (baixo
risco se errar, já que só muda como o JARVIS se dirige à pessoa).

⚠️ Isso é reconhecido como MENOS preciso que embeddings de rede neural
dedicados — pode confundir vozes parecidas, ou errar com ruído de
fundo. Adequado porque o pior caso de erro aqui é só chamar a pessoa
errada de "senhor" por engano, não uma falha de segurança.
"""

import io
import os

import librosa
import numpy as np

VOICE_MATCH_THRESHOLD = float(os.environ.get("JARVIS_VOICE_MATCH_THRESHOLD", "0.85"))


def _extract_signature(wav_bytes: bytes) -> list[float]:
    """Extrai a 'assinatura' de voz — MFCC médio ao longo do tempo, um vetor de tamanho fixo por pessoa."""
    import subprocess
    import tempfile
    from pathlib import Path

    # Converte pra WAV via ffmpeg primeiro, sempre — cobre qualquer formato
    # que chegue (webm do navegador, wav do listener, etc.) sem precisar
    # adivinhar o formato antes. librosa sozinho não lê webm de bytes em
    # memória (só arquivo com extensão certa via audioread), então essa
    # conversão evita esse problema de vez.
    with tempfile.TemporaryDirectory() as tmp:
        entrada = Path(tmp) / "entrada"
        saida = Path(tmp) / "saida.wav"
        entrada.write_bytes(wav_bytes)
        resultado = subprocess.run(
            ["ffmpeg", "-y", "-i", str(entrada), "-ar", "16000", "-ac", "1", str(saida)],
            capture_output=True, timeout=15,
        )
        if resultado.returncode != 0 or not saida.exists():
            raise ValueError(f"Não consegui processar o áudio (formato inválido ou corrompido).")
        audio, sr = librosa.load(str(saida), sr=16000, mono=True)

    if len(audio) < sr * 0.3:
        raise ValueError("Áudio curto demais pra extrair uma assinatura de voz confiável (mínimo ~0.3s).")
    mfcc = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=20)
    assinatura = np.mean(mfcc, axis=1)
    return assinatura.tolist()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    a, b = np.array(a), np.array(b)
    norma_a, norma_b = np.linalg.norm(a), np.linalg.norm(b)
    if norma_a == 0 or norma_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norma_a * norma_b))


def enroll_voice(nome: str, wav_bytes: bytes, tratamento: str | None = None) -> None:
    """Cadastra (ou recadastra) o perfil de voz de uma pessoa a partir de uma amostra de áudio."""
    import database as db

    assinatura = _extract_signature(wav_bytes)
    db.save_voice_profile(nome, assinatura, tratamento)


def identify_speaker(wav_bytes: bytes) -> dict | None:
    """
    Compara o áudio contra os perfis cadastrados. Devolve o melhor match
    (nome + tratamento) se a similaridade for forte o bastante, ou None
    se não bater com ninguém cadastrado (ou ninguém foi cadastrado ainda).
    """
    import database as db

    perfis = db.list_voice_profiles()
    if not perfis:
        return None

    try:
        assinatura_atual = _extract_signature(wav_bytes)
    except ValueError:
        return None  # áudio curto demais — não é erro, só não dá pra identificar

    melhor_perfil = None
    melhor_similaridade = 0.0
    for perfil in perfis:
        similaridade = _cosine_similarity(assinatura_atual, perfil["assinatura"])
        if similaridade > melhor_similaridade:
            melhor_similaridade = similaridade
            melhor_perfil = perfil

    if melhor_perfil is None or melhor_similaridade < VOICE_MATCH_THRESHOLD:
        return None

    return {"nome": melhor_perfil["nome"], "tratamento": melhor_perfil.get("tratamento"), "similaridade": melhor_similaridade}
