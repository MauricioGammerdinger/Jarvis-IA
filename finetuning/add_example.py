"""
Ferramenta simples pra adicionar exemplos ao dataset de treino, sem precisar
editar o .jsonl na mão (e sem risco de quebrar o formato JSON).

Uso:
    python add_example.py
"""

import json
from pathlib import Path

DATASET_PATH = Path(__file__).parent / "dataset.jsonl"


def main():
    print("=== Adicionar exemplo de treino ===")
    print("(Ctrl+C a qualquer momento pra cancelar)\n")

    while True:
        user_msg = input("Mensagem do usuário: ").strip()
        if not user_msg:
            print("Vazio, tentando de novo.\n")
            continue

        assistant_msg = input("Resposta do JARVIS (do jeito que você quer): ").strip()
        if not assistant_msg:
            print("Vazio, tentando de novo.\n")
            continue

        example = {
            "messages": [
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": assistant_msg},
            ]
        }

        with open(DATASET_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(example, ensure_ascii=False) + "\n")

        print("Salvo!\n")

        again = input("Adicionar outro? (s/n): ").strip().lower()
        if again != "s":
            break

    total = sum(1 for _ in open(DATASET_PATH, encoding="utf-8") if _.strip())
    print(f"\nDataset agora tem {total} exemplos no total.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelado.")
