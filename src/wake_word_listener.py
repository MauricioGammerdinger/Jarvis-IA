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

# ── Modo de conversa contínua ("Ele fala primeiro" item 2) ──────────────
# Depois de responder, o JARVIS continua ouvindo por um tempo, SEM precisar
# de "Hey JARVIS" de novo — só encerra se você ficar em silêncio por muito
# tempo. Ajustável, mas os padrões abaixo funcionam bem na prática.
CONVERSATION_MODE_ENABLED = os.environ.get("JARVIS_CONVERSATION_MODE", "1") == "1"
FOLLOWUP_MAX_WAIT_SECONDS = float(os.environ.get("JARVIS_FOLLOWUP_MAX_WAIT", "8"))  # quanto tempo espera você começar a falar
TRAILING_SILENCE_SECONDS = float(os.environ.get("JARVIS_TRAILING_SILENCE", "1.1"))  # quanto de silêncio indica que você terminou de falar
VAD_ENERGY_THRESHOLD = float(os.environ.get("JARVIS_VAD_THRESHOLD", "500"))  # RMS mínimo pra considerar "tem fala" (ajustável por ambiente)
MAX_UTTERANCE_SECONDS = float(os.environ.get("JARVIS_MAX_UTTERANCE_SECONDS", "20"))  # trava de segurança, nunca grava pra sempre

# Ditação longa: tolera pausas maiores (fala natural tem mais pausa que
# comando curto) e permite gravação bem mais longa — reaproveita a MESMA
# máquina de estados do modo de conversa, só com parâmetros diferentes.
DICTATION_MAX_WAIT_SECONDS = float(os.environ.get("JARVIS_DICTATION_MAX_WAIT", "10"))
DICTATION_TRAILING_SILENCE_SECONDS = float(os.environ.get("JARVIS_DICTATION_TRAILING_SILENCE", "2.5"))
DICTATION_MAX_SECONDS = float(os.environ.get("JARVIS_DICTATION_MAX_SECONDS", "300"))

# Interromper o JARVIS enquanto ele fala — DESLIGADO por padrão (opt-in),
# porque sem headset o próprio áudio saindo da caixa de som pode ser
# captado pelo microfone e confundido com "o usuário interrompendo"
# (eco/feedback). Limiar de energia mais alto que o VAD normal, de
# propósito, pra reduzir esse falso positivo — mesmo assim, funciona
# bem melhor com headset do que com caixa de som + microfone separados.
INTERRUPT_ENABLED = os.environ.get("JARVIS_INTERRUPT_ENABLED", "0") == "1"
INTERRUPT_ENERGY_THRESHOLD = float(os.environ.get("JARVIS_INTERRUPT_THRESHOLD", "1800"))
INTERRUPT_GRACE_PERIOD_SECONDS = 0.3  # não checa logo no início, evita pop/click do começo do áudio

SAMPLE_RATE = 16000
CHUNK_SIZE = 1280  # 80ms — tamanho de frame que o openWakeWord espera

HEADERS = {"X-API-Key": JARVIS_API_KEY}


def _rms_energy(chunk: np.ndarray) -> float:
    """
    Calcula a energia (RMS) de um pedaço de áudio — é isso que diferencia
    "tem alguém falando" de "silêncio/ruído de fundo baixo". Função pura,
    testável com áudio sintético, sem precisar de microfone de verdade.
    """
    if len(chunk) == 0:
        return 0.0
    return float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))


def _capture_utterance_frames(
    read_frame_fn,
    sample_rate: int = SAMPLE_RATE,
    chunk_seconds: float = CHUNK_SIZE / SAMPLE_RATE,
    energy_threshold: float = VAD_ENERGY_THRESHOLD,
    max_wait_seconds: float = FOLLOWUP_MAX_WAIT_SECONDS,
    trailing_silence_seconds: float = TRAILING_SILENCE_SECONDS,
    max_utterance_seconds: float = MAX_UTTERANCE_SECONDS,
):
    """
    Máquina de estados da conversa contínua: espera a pessoa começar a
    falar (energia acima do limiar); se não falar nada dentro de
    `max_wait_seconds`, devolve None (encerra o modo de conversa). Se
    começar a falar, acumula os frames até detectar silêncio sustentado
    por `trailing_silence_seconds` — aí devolve os frames capturados.

    `read_frame_fn` é uma função que devolve o PRÓXIMO frame de áudio (ou
    None se não tiver nada ainda) — isso é o que permite testar essa
    lógica inteira com áudio sintético, sem precisar de microfone real.
    """
    frames_por_chunk_silencio = max(1, int(trailing_silence_seconds / chunk_seconds))
    max_chunks_espera = max(1, int(max_wait_seconds / chunk_seconds))
    max_chunks_total = max(1, int(max_utterance_seconds / chunk_seconds))

    falando = False
    frames_capturados = []
    chunks_silencio_seguidos = 0
    chunks_esperados = 0
    chunks_totais = 0

    while True:
        chunk = read_frame_fn()
        if chunk is None:
            continue

        energia = _rms_energy(chunk)
        tem_fala = energia > energy_threshold

        if not falando:
            chunks_esperados += 1
            if tem_fala:
                falando = True
                frames_capturados.append(chunk)
            elif chunks_esperados >= max_chunks_espera:
                return None  # ninguém falou nada — encerra o modo de conversa
        else:
            frames_capturados.append(chunk)
            chunks_totais += 1
            if tem_fala:
                chunks_silencio_seguidos = 0
            else:
                chunks_silencio_seguidos += 1
                if chunks_silencio_seguidos >= frames_por_chunk_silencio:
                    return frames_capturados  # silêncio sustentado = terminou de falar
            if chunks_totais >= max_chunks_total:
                return frames_capturados  # trava de segurança, nunca grava pra sempre


def _frames_to_wav_bytes(frames: list, sample_rate: int = SAMPLE_RATE) -> bytes:
    audio = np.concatenate(frames) if frames else np.array([], dtype=np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


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


def send_to_jarvis(audio_wav: bytes) -> dict:
    """Manda o áudio gravado pro servidor JARVIS e devolve a resposta completa (texto + sinalizadores como 'iniciar_ditado')."""
    files = {"audio": ("comando.wav", audio_wav, "audio/wav")}
    data = {"session_id": "voz", "message": ""}
    resp = httpx.post(f"{JARVIS_API_URL}/chat/media", headers=HEADERS, data=data, files=files, timeout=60)
    resp.raise_for_status()
    return resp.json()


def report_voice_state(estado: str) -> None:
    """Avisa o servidor em que estado o listener está (idle/ouvindo/processando/falando) — é isso que sincroniza a FACE no navegador com o que está acontecendo de verdade. Nunca lança exceção — se falhar, só não sincroniza dessa vez, não trava o listener por causa disso."""
    try:
        httpx.post(f"{JARVIS_API_URL}/voice-state", headers=HEADERS, data={"estado": estado}, timeout=3)
    except Exception:
        pass


def speak(text: str) -> None:
    """Pede pro servidor sintetizar o texto em áudio (TTS) e toca."""
    report_voice_state("falando")
    resp = httpx.post(f"{JARVIS_API_URL}/tts", headers=HEADERS, data={"text": text}, timeout=30)
    if resp.status_code == 200:
        play_audio_bytes(resp.content)
    else:
        print(f"[jarvis] Falha no TTS ({resp.status_code}): {resp.text}")
    report_voice_state("idle")


def _estimate_wav_duration(wav_bytes: bytes) -> float:
    """Duração do WAV em segundos — usado pra saber quanto tempo escutar por interrupção. Chute seguro (5s) se não conseguir ler."""
    try:
        with wave.open(io.BytesIO(wav_bytes)) as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        return 5.0


def speak_interruptible(text: str, device=None) -> list | None:
    """
    Toca a resposta falada, mas ouve ENQUANTO fala (só se
    `INTERRUPT_ENABLED`) — se detectar energia acima do limiar de
    interrupção, para a fala na hora e começa a capturar o que a pessoa
    está dizendo. Devolve os frames capturados se foi interrompido, ou
    None se a fala terminou normalmente (sem interrupção, ou em sistemas
    sem suporte a isso — nesse caso cai pro `speak()` normal, bloqueante).
    """
    report_voice_state("falando")
    resp = httpx.post(f"{JARVIS_API_URL}/tts", headers=HEADERS, data={"text": text}, timeout=30)
    if resp.status_code != 200:
        print(f"[jarvis] Falha no TTS ({resp.status_code}): {resp.text}")
        report_voice_state("idle")
        return None

    if sys.platform != "win32" or not INTERRUPT_ENABLED:
        play_audio_bytes(resp.content)
        report_voice_state("idle")
        return None

    import winsound

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(resp.content)
        temp_path = f.name

    try:
        duracao = _estimate_wav_duration(resp.content)
        winsound.PlaySound(temp_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        inicio = time.time()

        while time.time() - inicio < duracao:
            if time.time() - inicio < INTERRUPT_GRACE_PERIOD_SECONDS:
                time.sleep(0.05)
                continue
            chunk = _read_chunk_blocking(device)
            if _rms_energy(chunk) > INTERRUPT_ENERGY_THRESHOLD:
                winsound.PlaySound(None, winsound.SND_PURGE)
                print("[jarvis] Interrompido — ouvindo o que você está dizendo...")
                report_voice_state("ouvindo")
                frames_restantes = _capture_utterance_frames(lambda: _read_chunk_blocking(device))
                return [chunk] + (frames_restantes or [])
        return None
    finally:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        report_voice_state("idle")


def _read_chunk_blocking(device) -> np.ndarray:
    """Grava um único chunk (80ms) de forma síncrona e independente — mesmo padrão do record_command, que já funciona sem depender do stream de escuta da wake word."""
    recording = sd.rec(CHUNK_SIZE, samplerate=SAMPLE_RATE, channels=1, dtype="int16", device=device)
    sd.wait()
    return recording[:, 0]


def handle_wake_word_detected(device=None) -> None:
    print("[jarvis] 'Hey JARVIS' detectado! Ouvindo seu comando...")
    beep_ack()
    report_voice_state("ouvindo")
    audio = record_command(RECORD_SECONDS)
    print("[jarvis] Processando...")
    report_voice_state("processando")
    try:
        resposta = send_to_jarvis(audio)
        reply = resposta["reply"]
        print(f"[jarvis] Resposta: {reply}")
        speak(reply)  # já reporta 'falando' -> 'idle' sozinho
    except httpx.HTTPStatusError as e:
        print(f"[jarvis] Erro do servidor: {e}")
        report_voice_state("idle")
        return
    except httpx.RequestError as e:
        print(f"[jarvis] Falha de conexão — o servidor JARVIS está rodando? {e}")
        report_voice_state("idle")
        return

    if resposta.get("iniciar_ditado"):
        run_dictation_mode(device)
    elif CONVERSATION_MODE_ENABLED:
        run_conversation_mode(device)


def run_conversation_mode(device=None) -> None:
    """
    Depois de uma resposta, continua ouvindo SEM precisar de "Hey JARVIS"
    de novo — só sai do modo de conversa quando a pessoa fica em silêncio
    por tempo demais (`FOLLOWUP_MAX_WAIT_SECONDS`). Cada chunk é lido de
    forma independente (`_read_chunk_blocking`), não depende do stream de
    escuta da wake word estar rodando ao mesmo tempo — importante porque,
    nesse momento, estamos dentro da própria chamada que a wake word
    disparou, então o callback dela está pausado.

    Se `INTERRUPT_ENABLED`, a fala do JARVIS pode ser interrompida — nesse
    caso, os frames capturados durante a interrupção já viram o PRÓXIMO
    turno direto, sem precisar esperar de novo (a pessoa já estava
    falando, não faz sentido descartar isso e pedir pra repetir).
    """
    frames_de_interrupcao = None
    while True:
        if frames_de_interrupcao is not None:
            frames = frames_de_interrupcao
            frames_de_interrupcao = None
        else:
            print("[jarvis] (modo de conversa — pode continuar falando, sem 'Hey JARVIS')")
            report_voice_state("ouvindo")
            frames = _capture_utterance_frames(lambda: _read_chunk_blocking(device))
            if frames is None:
                print("[jarvis] Silêncio — voltando a escutar por 'Hey JARVIS'.")
                report_voice_state("idle")
                return

        audio_wav = _frames_to_wav_bytes(frames)
        print("[jarvis] Processando resposta de acompanhamento...")
        report_voice_state("processando")
        try:
            resposta = send_to_jarvis(audio_wav)
            reply = resposta["reply"]
            print(f"[jarvis] Resposta: {reply}")
            if INTERRUPT_ENABLED:
                frames_de_interrupcao = speak_interruptible(reply, device)
            else:
                speak(reply)
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            print(f"[jarvis] Falha ao processar acompanhamento: {e}")
            report_voice_state("idle")
            return

        if resposta.get("iniciar_ditado"):
            run_dictation_mode(device)
            return


def run_dictation_mode(device=None) -> None:
    """
    Ditado longo: tolera pausas maiores (fala natural tem mais pausa que
    comando curto) e grava por bem mais tempo (até `DICTATION_MAX_SECONDS`).
    Reaproveita a MESMA máquina de estados do modo de conversa
    (`_capture_utterance_frames`), só com parâmetros diferentes — é
    exatamente o tipo de reaproveitamento que já foi testado a fundo ali.
    """
    print("[jarvis] (modo de ditado — pode falar um texto longo, aviso quando parar de ouvir)")
    report_voice_state("ouvindo")
    frames = _capture_utterance_frames(
        lambda: _read_chunk_blocking(device),
        max_wait_seconds=DICTATION_MAX_WAIT_SECONDS,
        trailing_silence_seconds=DICTATION_TRAILING_SILENCE_SECONDS,
        max_utterance_seconds=DICTATION_MAX_SECONDS,
    )
    if frames is None:
        print("[jarvis] Não ouvi nada — saindo do modo de ditado.")
        speak("Não ouvi nada, saindo do modo de ditado.")
        return

    audio_wav = _frames_to_wav_bytes(frames)
    print("[jarvis] Processando o texto ditado...")
    report_voice_state("processando")
    try:
        resposta = send_to_jarvis(audio_wav)
        reply = resposta["reply"]
        print(f"[jarvis] Resposta: {reply}")
        speak(reply)
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        print(f"[jarvis] Falha ao processar o ditado: {e}")
        report_voice_state("idle")


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
            handle_wake_word_detected(device)

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
