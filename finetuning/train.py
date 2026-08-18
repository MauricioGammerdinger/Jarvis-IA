"""
Fine-tuning LoRA do J.A.R.V.I.S. — treina a personalidade em cima do gemma4.

⚠️ ISSO SÓ RODA COM GPU NVIDIA. O ambiente onde este script foi escrito não
tem GPU nenhuma disponível — não foi possível rodar o treino de verdade
durante o desenvolvimento. A lógica segue o padrão oficial documentado pelo
Unsloth pro Gemma 4, mas o primeiro treino real só acontece no seu PC.

O que este script faz:
  1. Carrega o modelo base (gemma-4-E4B, a variante compatível com sua GPU)
  2. Adiciona uma camada leve de treino (LoRA) por cima — não retreina o
     modelo inteiro, só uma fração pequena dos parâmetros
  3. Treina com os exemplos de dataset.jsonl
  4. Salva o resultado, pronto pra exportar pro Ollama (veja export_to_ollama.py)

Uso:
    pip install -r requirements.txt
    python train.py
"""

from unsloth import FastLanguageModel
from trl import SFTTrainer
from transformers import TrainingArguments
from datasets import load_dataset

MODEL_NAME = "unsloth/gemma-4-E4B-it"  # variante que cabe em GPUs de 8GB+ (ex: RTX 5050)
MAX_SEQ_LENGTH = 2048
OUTPUT_DIR = "./jarvis-personalidade"


def main():
    print("=== Fine-tuning do J.A.R.V.I.S. (LoRA sobre gemma4) ===\n")

    print("[1/4] Carregando modelo base (baixa na primeira vez, ~5-8GB)...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=True,  # QLoRA — reduz uso de VRAM bastante
    )

    print("[2/4] Adicionando camada de treino (LoRA)...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,  # rank do LoRA — mais alto = mais "capacidade de aprender", mais VRAM
        lora_alpha=32,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )

    print("[3/4] Carregando dataset...")
    dataset = load_dataset("json", data_files="dataset.jsonl", split="train")
    print(f"     {len(dataset)} exemplos carregados.")

    print("[4/4] Treinando (isso demora — de minutos a algumas horas, dependendo da GPU)...")
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=TrainingArguments(
            output_dir=OUTPUT_DIR,
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,
            num_train_epochs=3,  # 3 passadas pelo dataset — ajuste se tiver mais exemplos
            learning_rate=2e-4,
            warmup_ratio=0.1,
            lr_scheduler_type="cosine",
            bf16=True,
            logging_steps=5,
            save_strategy="epoch",
        ),
    )
    trainer.train()

    print(f"\n=== Treino concluído! Resultado salvo em {OUTPUT_DIR} ===")
    print("Próximo passo: rode export_to_ollama.py pra usar esse resultado no JARVIS.")


if __name__ == "__main__":
    main()
