"""
Texto → fala, para o JARVIS "falar" as respostas.

Dois motores, escolhidos por `JARVIS_TTS_ENGINE` no .env:

- "espeak" (padrão) — usa o `espeak-ng` (binário do sistema). Funciona
  imediatamente, offline, sem baixar modelo nenhum, mas a qualidade é
  robótica ("voz de robô de filme antigo").
- "piper" — voz por rede neural (ainda 100% local, sem custo), soa muito
  mais natural. Precisa baixar um modelo de voz em português antes (veja
  o README, seção "Trocando pra uma voz mais natural (Piper)") — os
  arquivos NÃO vêm inclusos no projeto (alguns MB, cada voz).
"""

import os
import subprocess
import tempfile
import wave
from pathlib import Path

DEFAULT_VOICE = "pt-br"  # espeak-ng usa esse código pra português do Brasil

TTS_ENGINE = os.environ.get("JARVIS_TTS_ENGINE", "espeak").strip().lower()
PIPER_MODEL_PATH = os.environ.get("JARVIS_PIPER_MODEL_PATH", "").strip()

_piper_voice_cache = None  # carrega o modelo uma vez só, não a cada frase (é lento pra carregar)


def _load_piper_voice():
    global _piper_voice_cache
    if _piper_voice_cache is not None:
        return _piper_voice_cache

    if not PIPER_MODEL_PATH:
        raise RuntimeError(
            "JARVIS_TTS_ENGINE=piper, mas JARVIS_PIPER_MODEL_PATH não está definido no .env. "
            "Aponte pro arquivo .onnx da voz baixada (veja o README)."
        )
    model_path = Path(PIPER_MODEL_PATH)
    if not model_path.exists():
        raise RuntimeError(
            f"Modelo de voz do Piper não encontrado em '{model_path}'. "
            f"Baixe o modelo antes (veja o README, seção Piper) e confira o caminho no .env."
        )

    from piper import PiperVoice

    _piper_voice_cache = PiperVoice.load(str(model_path))
    return _piper_voice_cache


def _synthesize_piper(text: str) -> bytes:
    voice = _load_piper_voice()
    with tempfile.TemporaryDirectory() as tmp:
        out_path = str(Path(tmp) / "speech.wav")
        with wave.open(out_path, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)
        return Path(out_path).read_bytes()


def _synthesize_espeak(text: str, voice: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        out_path = str(Path(tmp) / "speech.wav")
        try:
            result = subprocess.run(
                ["espeak-ng", "-v", voice, "-s", "165", "-w", out_path, text],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "espeak-ng não está instalado no servidor. "
                "Instale com: sudo apt-get install espeak-ng"
            )

        if result.returncode != 0:
            raise RuntimeError(f"Falha ao gerar áudio: {result.stderr}")

        return Path(out_path).read_bytes()


def synthesize_speech(text: str, voice: str = DEFAULT_VOICE) -> bytes:
    """Converte texto em áudio WAV (bytes), usando o motor configurado (espeak-ng ou Piper)."""
    if not text.strip():
        raise ValueError("Texto vazio não pode ser sintetizado.")

    if TTS_ENGINE == "piper":
        try:
            return _synthesize_piper(text)
        except Exception as e:
            # Nunca deixa o JARVIS ficar mudo por causa disso — cai pro
            # espeak-ng (sempre disponível) e avisa no log o motivo real.
            print(f"[tts] Piper falhou ({e}) — usando espeak-ng como alternativa dessa vez.")
            return _synthesize_espeak(text, voice)

    return _synthesize_espeak(text, voice)
