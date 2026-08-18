"""
Exporta o resultado do fine-tuning pro formato GGUF e registra no Ollama
como um modelo customizado — depois disso, o JARVIS pode usar sua versão
treinada em vez do gemma4 original.

⚠️ Não testado de ponta a ponta (depende do treino real ter rodado antes,
que por sua vez depende de GPU que este ambiente não tem).

Uso (depois de rodar train.py):
    python export_to_ollama.py
"""

from pathlib import Path

from unsloth import FastLanguageModel

MODEL_DIR = "./jarvis-personalidade"
GGUF_OUTPUT = "./jarvis-personalidade.gguf"
OLLAMA_MODEL_NAME = "jarvis-custom"


def main():
    print("=== Exportando o modelo treinado pro Ollama ===\n")

    print("[1/3] Carregando o modelo treinado...")
    model, tokenizer = FastLanguageModel.from_pretrained(model_name=MODEL_DIR)

    print("[2/3] Convertendo pra GGUF (formato que o Ollama entende)...")
    model.save_pretrained_gguf(GGUF_OUTPUT, tokenizer, quantization_method="q4_k_m")

    modelfile_content = f"""FROM {GGUF_OUTPUT}
TEMPLATE \"\"\"{{{{ .Prompt }}}}\"\"\"
PARAMETER temperature 0.7
"""
    Path("Modelfile").write_text(modelfile_content, encoding="utf-8")

    print("[3/3] Pronto! Agora rode no terminal:")
    print(f"     ollama create {OLLAMA_MODEL_NAME} -f Modelfile")
    print(f"\nDepois, no .env do JARVIS, troque:")
    print(f"     JARVIS_MODEL={OLLAMA_MODEL_NAME}")
    print("\nE reinicie o JARVIS pra usar sua versão treinada.")


if __name__ == "__main__":
    main()
