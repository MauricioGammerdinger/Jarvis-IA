"""
Listener de wake word — "Hey JARVIS" sempre ouvindo.

Roda separado do servidor principal, em segundo plano. Fica escutando o
microfone continuamente (localmente, nada é enviado pra fora só de ouvir);
quando detecta "hey jarvis", grava sua fala seguinte, manda pro servidor
JARVIS transcrever e responder, e toca a resposta em voz.

Testado neste ambiente: o carregamento do modelo "hey jarvis" (via
openWakeWord) e a detecção com áudio sintético funcionam de verdade. A
captura contínua de microfone e a reprodução de áudio (winsound) NÃO
puderam ser testadas aqui — o ambiente de desenvolvimento não tem microfone
nem é Windows. Teste no seu PC antes de confiar 100%.

Uso:
    python wake_word_listener.py
"""

import glob
import io
import os
import sys
import tempfile
import time
import wave

import httpx
import numpy as np
import sounddevice as sd
from openwakeword.model import Model

JARVIS_API_URL = os.environ.get("JARVIS_API_URL", "http://localhost:8000")
JARVIS_API_KEY = os.environ.get("JARVIS_API_KEY", "")
WAKE_THRESHOLD = float(os.environ.get("WAKE_WORD_THRESHOLD", "0.5"))
RECORD_SECONDS = float(os.environ.get("WAKE_WORD_RECORD_SECONDS", "5"))
INPUT_DEVICE = os.environ.get("WAKE_WORD_INPUT_DEVICE", "").strip()

SAMPLE_RATE = 16000
CHUNK_SIZE = 1280  # 80ms — tamanho de frame que o openWakeWord espera

HEADERS = {"X-API-Key": JARVIS_API_KEY}


def list_input_devices() -> None:
    """Lista os microfones disponíveis, com o índice/nome que vai no .env (WAKE_WORD_INPUT_DEVICE)."""
    print("Dispositivos de entrada de áudio disponíveis:\n")
    devices = sd.query_devices()
    found = False
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] > 0:
            found = True
            default_mark = " (padrão atual)" if i == sd.default.device[0] else ""
            print(f"  [{i}] {dev['name']}{default_mark}")
    if not found:
        print("  Nenhum microfone encontrado.")
    print("\nPra usar um específico, coloque o número OU um trecho do nome em")
    print("WAKE_WORD_INPUT_DEVICE no .env (ex: WAKE_WORD_INPUT_DEVICE=2 ou WAKE_WORD_INPUT_DEVICE=Headset).")
    print("Deixe em branco pra usar o microfone padrão do Windows.")


def _resolve_input_device():
    """
    Converte o valor de WAKE_WORD_INPUT_DEVICE (índice numérico, trecho do
    nome, ou vazio) no formato que o sounddevice espera. Vazio = usa o
    padrão do sistema (não especifica nada, deixa o sounddevice decidir).
    """
    if not INPUT_DEVICE:
        return None
    if INPUT_DEVICE.isdigit():
        return int(INPUT_DEVICE)

    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] > 0 and INPUT_DEVICE.lower() in dev["name"].lower():
            return i
    raise RuntimeError(
        f"Nenhum microfone encontrado com o nome '{INPUT_DEVICE}'. "
        f"Rode 'python wake_word_listener.py --list-devices' pra ver os disponíveis."
    )


def _find_hey_jarvis_model() -> str:
    """O modelo 'hey jarvis' já vem embutido no pacote openwakeword — não precisa baixar nada."""
    import openwakeword

    base = os.path.dirname(openwakeword.__file__)
    matches = glob.glob(os.path.join(base, "resources", "models", "hey_jarvis*.onnx"))
    if not matches:
        raise RuntimeError("Modelo 'hey_jarvis' não encontrado no pacote openwakeword.")
    return matches[0]


def play_audio_bytes(wav_bytes: bytes) -> None:
    """Toca um WAV usando winsound (Windows, biblioteca padrão — sem dependência extra)."""
    if sys.platform != "win32":
        print("[jarvis] Reprodução de áudio automática só suportada no Windows por enquanto.")
        return
    import winsound

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        temp_path = f.name
    try:
        winsound.PlaySound(temp_path, winsound.SND_FILENAME)
    finally:
        os.unlink(temp_path)


def beep_ack() -> None:
    """Bipe curto confirmando que ouviu a wake word — feedback rápido antes da resposta chegar."""
    if sys.platform == "win32":
        import winsound

        winsound.Beep(880, 120)
    else:
        print("[jarvis] *beep* (wake word detectada)")


def record_command(seconds: float) -> bytes:
    """Grava `seconds` de áudio do microfone e devolve como bytes de um WAV válido."""
    recording = sd.rec(
        int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16", device=_resolve_input_device()
    )
    sd.wait()

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # int16 = 2 bytes
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(recording.tobytes())
    return buf.getvalue()


def send_to_jarvis(audio_wav: bytes) -> str:
    """Manda o áudio gravado pro servidor JARVIS e devolve o texto da resposta."""
    files = {"audio": ("comando.wav", audio_wav, "audio/wav")}
    data = {"session_id": "voz", "message": ""}
    resp = httpx.post(f"{JARVIS_API_URL}/chat/media", headers=HEADERS, data=data, files=files, timeout=60)
    resp.raise_for_status()
    return resp.json()["reply"]


def speak(text: str) -> None:
    """Pede pro servidor sintetizar o texto em áudio (TTS) e toca."""
    resp = httpx.post(f"{JARVIS_API_URL}/tts", headers=HEADERS, data={"text": text}, timeout=30)
    if resp.status_code == 200:
        play_audio_bytes(resp.content)
    else:
        print(f"[jarvis] Falha no TTS ({resp.status_code}): {resp.text}")


def handle_wake_word_detected() -> None:
    print("[jarvis] 'Hey JARVIS' detectado! Ouvindo seu comando...")
    beep_ack()
    audio = record_command(RECORD_SECONDS)
    print("[jarvis] Processando...")
    try:
        reply = send_to_jarvis(audio)
        print(f"[jarvis] Resposta: {reply}")
        speak(reply)
    except httpx.HTTPStatusError as e:
        print(f"[jarvis] Erro do servidor: {e}")
    except httpx.RequestError as e:
        print(f"[jarvis] Falha de conexão — o servidor JARVIS está rodando? {e}")


def main():
    if "--list-devices" in sys.argv:
        list_input_devices()
        return

    if not JARVIS_API_KEY:
        print("Erro: defina JARVIS_API_KEY antes de rodar (mesma chave do servidor).")
        sys.exit(1)

    device = None
    try:
        device = _resolve_input_device()
    except RuntimeError as e:
        print(f"Erro: {e}")
        sys.exit(1)

    model_path = _find_hey_jarvis_model()
    model = Model(wakeword_model_paths=[model_path])
    model_key = list(model.models.keys())[0]

    print(f"[jarvis] Escutando por 'Hey JARVIS'... (Ctrl+C pra parar)")
    print(f"[jarvis] Servidor: {JARVIS_API_URL}")
    if device is not None:
        print(f"[jarvis] Usando microfone: {sd.query_devices(device)['name']}")

    cooldown_until = 0.0

    def audio_callback(indata, frames, time_info, status):
        nonlocal cooldown_until
        if time.time() < cooldown_until:
            return  # evita disparar de novo enquanto ainda está processando o comando anterior

        audio_chunk = indata[:, 0]
        prediction = model.predict(audio_chunk)
        score = prediction[model_key]

        if score > WAKE_THRESHOLD:
            cooldown_until = time.time() + RECORD_SECONDS + 3  # bloqueia novas detecções durante o processamento
            handle_wake_word_detected()

    # Grava "sinal de vida" no banco periodicamente — é isso que o painel
    # de agentes lê pra saber que esse processo (separado do servidor
    # principal) está de fato rodando. Não escreve a cada 100ms (seria
    # sobrecarga à toa), só a cada 20s.
    HEARTBEAT_INTERVAL = 20
    last_heartbeat = 0.0

    def write_heartbeat():
        try:
            import database as db
            db.record_agent_run("hey_jarvis", "ok", "Ouvindo ativamente", "")
        except Exception:
            pass  # o heartbeat nunca pode derrubar o listener por causa de um erro de banco

    try:
        with sd.InputStream(
            channels=1, samplerate=SAMPLE_RATE, blocksize=CHUNK_SIZE, dtype="int16",
            callback=audio_callback, device=device,
        ):
            write_heartbeat()
            last_heartbeat = time.time()
            while True:
                time.sleep(0.1)
                if time.time() - last_heartbeat >= HEARTBEAT_INTERVAL:
                    write_heartbeat()
                    last_heartbeat = time.time()
    except KeyboardInterrupt:
        print("\n[jarvis] Encerrando.")


if __name__ == "__main__":
    main()
