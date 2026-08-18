"""
Processamento de mídia para o J.A.R.V.I.S.

Claude não recebe vídeo nem áudio nativamente — só texto, imagem e documento.
Então a estratégia aqui é converter:
  - Áudio  -> transcrição de texto (faster-whisper, 100% local)
  - Vídeo  -> N frames extraídos (viram blocos de imagem) + a trilha de áudio
              extraída e transcrita do mesmo jeito que um áudio puro.

Isso dá ao modelo uma visão "amostrada" do vídeo (o que se vê + o que se fala)
em vez de compreensão de vídeo de verdade — é a aproximação que dá pra fazer
com as ferramentas disponíveis, e cobre bem a maioria dos casos de uso reais
(explicar um vídeo, resumir uma reunião gravada, ver o que tem numa cena).
"""

import base64
import os
import subprocess
import tempfile
from pathlib import Path

_whisper_model = None


def _get_whisper_model():
    """Carrega o modelo Whisper sob demanda (lazy) — só na primeira transcrição.

    Na primeira execução ele baixa o modelo (~75MB no tamanho 'small') e
    precisa de internet nesse momento único; depois disso funciona 100%
    offline. Troque o tamanho do modelo abaixo se quiser mais precisão
    (custo: mais RAM/CPU) ou mais velocidade.
    """
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        # 'small' é mais preciso mas mais pesado pra baixar de novo a cada
        # "acordar" do tier grátis da nuvem. Configurável via env var —
        # considere 'tiny' ou 'base' se estiver na Render free tier.
        model_size = os.environ.get("WHISPER_MODEL_SIZE", "small")
        _whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _whisper_model


def transcribe_audio(audio_path: str) -> str:
    """Transcreve um arquivo de áudio (qualquer formato que o ffmpeg leia) para texto."""
    model = _get_whisper_model()
    segments, info = model.transcribe(audio_path, language=None)
    text = " ".join(seg.text.strip() for seg in segments).strip()
    if not text:
        return "(áudio sem fala detectável)"
    return text


def extract_audio_from_video(video_path: str, out_wav_path: str) -> bool:
    """Extrai a trilha de áudio de um vídeo para WAV 16kHz mono (formato ideal pro Whisper).

    Retorna False se o vídeo não tiver trilha de áudio (não é erro).
    """
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-ac", "1", "-ar", "16000",
            out_wav_path,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.returncode == 0 and Path(out_wav_path).exists() and Path(out_wav_path).stat().st_size > 0


def extract_video_frames(video_path: str, out_dir: str, max_frames: int = 6) -> list[str]:
    """Extrai até `max_frames` frames distribuídos uniformemente ao longo do vídeo.

    Retorna a lista de caminhos dos arquivos .jpg gerados, em ordem cronológica.
    """
    duration = _get_video_duration(video_path)
    if duration <= 0:
        # fallback: pelo menos um frame do início
        duration = 1.0

    interval = max(duration / max_frames, 0.5)
    out_pattern = str(Path(out_dir) / "frame_%03d.jpg")

    subprocess.run(
        [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", f"fps=1/{interval}",
            "-frames:v", str(max_frames),
            "-q:v", "3",
            out_pattern,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return sorted(str(p) for p in Path(out_dir).glob("frame_*.jpg"))


def _get_video_duration(video_path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def image_to_base64_block(image_path: str, media_type: str = "image/jpeg") -> dict:
    """Converte um arquivo de imagem em bloco de conteúdo no formato da API da Anthropic."""
    data = base64.b64encode(Path(image_path).read_bytes()).decode("utf-8")
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}


def process_video(video_bytes: bytes, suffix: str = ".mp4", max_frames: int = 6) -> dict:
    """
    Pipeline completo pra vídeo: salva temporariamente, extrai frames + áudio,
    transcreve o áudio se houver, e devolve blocos de conteúdo prontos + o texto
    da transcrição (para o system prompt saber o que aconteceu).
    """
    with tempfile.TemporaryDirectory() as tmp:
        video_path = str(Path(tmp) / f"input{suffix}")
        Path(video_path).write_bytes(video_bytes)

        frame_paths = extract_video_frames(video_path, tmp, max_frames=max_frames)
        image_blocks = [image_to_base64_block(p) for p in frame_paths]

        audio_path = str(Path(tmp) / "audio.wav")
        transcript = None
        if extract_audio_from_video(video_path, audio_path):
            transcript = transcribe_audio(audio_path)

        return {
            "image_blocks": image_blocks,
            "frame_count": len(frame_paths),
            "transcript": transcript,
        }


def process_audio(audio_bytes: bytes, suffix: str = ".wav") -> str:
    """Pipeline completo pra áudio puro: salva temporariamente e transcreve."""
    with tempfile.TemporaryDirectory() as tmp:
        audio_path = str(Path(tmp) / f"input{suffix}")
        Path(audio_path).write_bytes(audio_bytes)
        return transcribe_audio(audio_path)
