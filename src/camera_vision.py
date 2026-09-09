"""
Visão por câmera — duas capacidades bem diferentes, tratadas com cuidados
diferentes:

1. `describe_scene()` — você pergunta, ele olha uma vez e descreve. Como
   pedir uma foto, sob demanda. Precisa de um modelo com visão configurado
   (`JARVIS_VISION_MODEL` no .env) — os modelos de texto padrão (qwen3,
   gemma) NÃO enxergam imagem, por isso é um modelo separado.

2. `analyze_emotion()` / o job de fundo associado — DESLIGADO por padrão,
   opt-in de verdade. Roda de tempos em tempos, tira UM frame, roda
   detecção de emoção (biblioteca DeepFace, modelo já publicado,
   amplamente usado — não é algo que eu treinei). Isso é reconhecido na
   literatura como impreciso (rosto cansado/concentrado vira "triste"
   com facilidade) — por isso o JARVIS NUNCA afirma um diagnóstico
   ("você está triste"), só pergunta com cuidado, e só depois de ver o
   mesmo sinal se repetir por um tempo, não numa foto só.

Em NENHUM dos dois casos a imagem é salva em disco — captura, analisa
na memória, descarta. Nem uma imagem sequer fica gravada em lugar
nenhum.
"""

import os

CAMERA_INDEX = int(os.environ.get("JARVIS_CAMERA_INDEX", "0"))
VISION_MODEL = os.environ.get("JARVIS_VISION_MODEL", "").strip()

# Detecção de emoção — DESLIGADA por padrão (opt-in de verdade)
EMOTION_CHECK_ENABLED = os.environ.get("JARVIS_EMOTION_CHECK_ENABLED", "0") == "1"
EMOTION_CHECK_INTERVAL_MINUTES = int(os.environ.get("JARVIS_EMOTION_CHECK_INTERVAL_MINUTES", "30"))
# Quantas checagens seguidas com emoção negativa antes de considerar
# "vale perguntar" — nunca reage a UMA foto só (muito ruído/imprecisão).
EMOTION_SUSTAINED_READINGS_NEEDED = int(os.environ.get("JARVIS_EMOTION_SUSTAINED_READINGS", "3"))
EMOCOES_NEGATIVAS = {"sad", "angry", "fear"}


def capture_frame():
    """Tira UM frame da webcam. Devolve None se não tiver câmera ou falhar — nunca lança exceção."""
    try:
        import cv2

        cam = cv2.VideoCapture(CAMERA_INDEX)
        if not cam.isOpened():
            return None
        ok, frame = cam.read()
        cam.release()
        return frame if ok else None
    except Exception:
        return None


def describe_scene() -> str:
    """Tira uma foto e descreve o que vê, usando um modelo com visão separado do modelo de texto principal."""
    if not VISION_MODEL:
        return "Nenhum modelo com visão configurado — defina JARVIS_VISION_MODEL no .env (veja o README)."

    frame = capture_frame()
    if frame is None:
        return "Não consegui acessar a câmera — ela está conectada e disponível?"

    try:
        import base64

        import cv2

        ok, buffer = cv2.imencode(".jpg", frame)
        if not ok:
            return "Não consegui processar a imagem da câmera."
        b64_imagem = base64.b64encode(buffer).decode("utf-8")

        import llm_client

        resposta = llm_client.chat_with_vision(VISION_MODEL, b64_imagem, "Descreva em poucas frases o que você vê nessa imagem, em português.")
        return resposta
    except Exception as e:
        return f"Erro ao descrever a cena: {e}"


def analyze_emotion_now() -> dict:
    """
    Roda a detecção de emoção UMA vez, no frame atual. Devolve um dict
    com a emoção dominante e se é negativa — mas isso é só um dado bruto,
    NUNCA deve virar afirmação direta pro usuário (ver `EMOCOES_NEGATIVAS`
    e a lógica de "sustentado" antes de perguntar qualquer coisa).
    """
    frame = capture_frame()
    if frame is None:
        return {"ok": False, "motivo": "Câmera não disponível."}

    try:
        from deepface import DeepFace

        resultado = DeepFace.analyze(frame, actions=["emotion"], enforce_detection=True, silent=True)
        dominante = resultado[0]["dominant_emotion"]
        return {"ok": True, "emocao_dominante": dominante, "negativa": dominante in EMOCOES_NEGATIVAS}
    except ValueError:
        # DeepFace lança ValueError quando não encontra rosto na imagem — comum e esperado, não é erro de verdade
        return {"ok": False, "motivo": "Nenhum rosto detectado no frame."}
    except Exception as e:
        return {"ok": False, "motivo": str(e)}


# ── Decisão de quando vale perguntar — nunca reage a uma foto só ─────────
# Histórico em memória, nunca gravado em disco (mesma filosofia do
# focus_monitor) — reseta sozinho se o processo reiniciar.
_leituras_recentes: list[str] = []
_ja_perguntou_dessa_vez = False


def register_reading_and_check(emocao_dominante: str, negativa: bool) -> bool:
    """
    Registra uma leitura e decide se já vale perguntar — só depois de
    `EMOTION_SUSTAINED_READINGS_NEEDED` leituras SEGUIDAS negativas, nunca
    numa foto só (uma leitura isolada é ruído, não sinal). Devolve True só
    na primeira vez que o sinal sustentado aparece — não fica perguntando
    de novo a cada checagem seguinte enquanto a mesma sequência continuar.
    """
    global _ja_perguntou_dessa_vez

    if not negativa:
        _leituras_recentes.clear()
        _ja_perguntou_dessa_vez = False
        return False

    _leituras_recentes.append(emocao_dominante)
    if len(_leituras_recentes) < EMOTION_SUSTAINED_READINGS_NEEDED:
        return False

    if _ja_perguntou_dessa_vez:
        return False  # já perguntou nessa sequência, não repete até quebrar a sequência (voltar pra neutro/positivo)

    _ja_perguntou_dessa_vez = True
    return True


def reset_emotion_tracking() -> None:
    """Só pra teste — limpa o estado em memória entre um cenário e outro."""
    global _ja_perguntou_dessa_vez
    _leituras_recentes.clear()
    _ja_perguntou_dessa_vez = False
