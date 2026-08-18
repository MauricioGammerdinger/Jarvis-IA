# Fine-tuning do J.A.R.V.I.S. — dando personalidade própria ao modelo

Isso é **opcional e avançado** — o JARVIS funciona perfeitamente sem isso,
usando o `gemma4` puro. Esse processo aqui ensina o modelo a responder com
uma personalidade mais consistente (formal, chama de "senhor", humor seco),
em vez de depender só do system prompt pra isso.

## O que isso muda de verdade (e o que não muda)

- ✅ Jeito de falar mais consistente, sem precisar reforçar no prompt toda hora
- ✅ Menos "escorregões" de personalidade em respostas longas
- ❌ **Não** fica mais inteligente que o `gemma4` original — a capacidade de
  raciocínio de base continua a mesma, isso só ajusta o estilo

## Requisitos
- GPU NVIDIA com pelo menos 8GB de VRAM (a variante `gemma-4-E4B` usada aqui
  cabe em GPUs desse porte, como a RTX 5050, usando QLoRA)
- ~15GB de espaço livre em disco (modelo base + checkpoints de treino)
- Paciência — o treino pode levar de alguns minutos a algumas horas,
  dependendo de quantos exemplos você tiver e da sua GPU

## Passo a passo

### 1. Instalar as dependências (separadas do resto do JARVIS)
```bash
cd finetuning
pip install -r requirements.txt
```

### 2. Adicionar seus próprios exemplos
O dataset já vem com 20 exemplos iniciais (`dataset.jsonl`), mas quanto mais
exemplos SEUS, mais a personalidade fica do jeito que você quer. Use a
ferramenta interativa:
```bash
python add_example.py
```
Ele pergunta a mensagem do usuário e a resposta que você gostaria que o
JARVIS desse, e salva no formato certo automaticamente.

**Dica**: pense em situações do dia a dia com o JARVIS (abrir programa,
pedir uma info, agradecer, corrigir um erro) e escreva a resposta exatamente
como você gostaria de ouvir. Quanto mais variado, melhor — uns 50-100
exemplos já fazem diferença perceptível; 200+ é ainda melhor.

### 3. Treinar
```bash
python train.py
```
Isso baixa o modelo base (~5-8GB, só na primeira vez) e treina uma camada
leve (LoRA) por cima, usando seus exemplos. Acompanhe o progresso no
terminal — ele mostra o "loss" caindo a cada poucos passos (número menor =
melhor, é o sinal de que está aprendendo).

### 4. Exportar pro Ollama
```bash
python export_to_ollama.py
```
Isso converte o resultado pro formato GGUF (que o Ollama entende) e monta
um `Modelfile`. Depois, registra no Ollama:
```bash
ollama create jarvis-custom -f Modelfile
```

### 5. Usar no JARVIS
No `.env` da raiz do projeto, troque:
```
JARVIS_MODEL=jarvis-custom
```
Reinicia o JARVIS (bandeja → Sair, abre de novo) e teste conversar — deve
notar a diferença de personalidade.

## ⚠️ Sobre o que foi testado (e o que não foi)

Este ambiente de desenvolvimento **não tem GPU** — não foi possível rodar
o treino de verdade, nem baixar o modelo base, durante a criação disso. O
que testei de verdade:
- O formato do `dataset.jsonl` (JSON válido, estrutura correta) — 20 exemplos
  validados
- A ferramenta `add_example.py` — testei adicionando um exemplo de verdade
  e conferindo que salvou certo
- A sintaxe dos scripts `train.py` e `export_to_ollama.py`

O que **não pude testar**: o treino em si rodando numa GPU de verdade, e a
exportação/importação real no Ollama. O código segue o padrão oficial
documentado pelo Unsloth pro Gemma 4, mas o primeiro teste de ponta a ponta
só acontece no seu PC. Se der erro em algum passo, me manda a mensagem
exata que ajusto.

## Se quiser voltar pro modelo original
No `.env`, troca de volta:
```
JARVIS_MODEL=gemma4
```
O `jarvis-custom` continua salvo no Ollama, não precisa re-treinar se quiser
alternar entre os dois.
