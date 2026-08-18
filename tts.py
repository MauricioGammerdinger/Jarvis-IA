"""
Texto → fala, para o JARVIS "falar" as respostas.

Usa o `espeak-ng` (binário do sistema, não é biblioteca Python) — funciona
imediatamente, offline, sem baixar modelo nenhum. A qualidade é robótica
(bem "voz de robô de filme antigo"), não é uma voz natural como as de
serviços pagos — é a troca consciente que fazemos aqui pra manter tudo
local, gratuito e sem dependência de API externa. Se um dia quiser voz mais
natural, dá pra trocar por Piper (voz por rede neural, ainda local) sem
mudar a interface desta função.
"""

import subprocess
import tempfile
from pathlib import Path

DEFAULT_VOICE = "pt-br"  # espeak-ng usa esse código pra português do Brasil


def synthesize_speech(text: str, voice: str = DEFAULT_VOICE) -> bytes:
    """Converte texto em áudio WAV (bytes). Lança RuntimeError se o espeak-ng não estiver instalado."""
    if not text.strip():
        raise ValueError("Texto vazio não pode ser sintetizado.")

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
