# J.A.R.V.I.S. local — 100% no seu PC, sem custo de IA

Assistente pessoal rodando inteiramente no seu computador: modelo de IA local
(via Ollama, gratuito), memória persistente, transcrição de áudio, texto pra
fala, controle do Word, comandos no sistema (com aprovação) — sem pagar nada
por token de IA, sem dado saindo da sua máquina (exceto se você mesmo usar a
integração opcional com Linear).

## O que você precisa saber antes de começar

Este projeto usa **Ollama** rodando um modelo aberto (recomendado: `gemma4`,
que tem visão e tool-calling nativos juntos) em vez do Claude/GPT/Gemini
pagos. A qualidade das respostas e a confiabilidade do uso de ferramentas
(memória, comandos, Word, Linear) é **boa, mas inferior** a um modelo de
ponta pago — é a troca consciente por não pagar nada. Se em algum momento
notar o JARVIS "esquecendo" de usar uma ferramenta ou entendendo mal um
pedido, geralmente ajuda: reformular de forma mais direta, ou trocar pra um
modelo Ollama maior (se sua GPU aguentar). Se não precisar de visão
(`ver_tela`), `qwen3:8b` é mais leve e roda mais rápido.

## Requisitos
- Windows 10/11
- Python 3.11+
- Sua GPU (ex: RTX 5050, 16GB RAM) — suficiente pra modelos de 7-8B, talvez 14B

## 1. Instalar o Ollama
1. Baixe em **ollama.com** (Windows) e instale normalmente.
2. Depois de instalado, ele já roda em segundo plano automaticamente
   (ícone na bandeja do sistema).
3. Abra o PowerShell ou Prompt de Comando e baixe o modelo recomendado:
   ```
   ollama pull gemma4
   ```
   Isso baixa uns 5-6GB — só acontece uma vez.
4. Teste rapidamente:
   ```
   ollama run gemma4
   ```
   Se abrir um chat e responder, está funcionando. Digite `/bye` pra sair.

## 2. Instalar as dependências do ffmpeg e espeak-ng
Necessários pra áudio/vídeo e voz. No Windows, o jeito mais fácil é com
**Chocolatey** (gerenciador de pacotes):
```powershell
choco install ffmpeg espeak-ng
```
Sem Chocolatey? Baixe manualmente:
- ffmpeg: ffmpeg.org/download.html (adicione a pasta `bin` ao PATH do Windows)
- espeak-ng: github.com/espeak-ng/espeak-ng/releases (baixe o instalador `.msi`)

## 3. Instalar tudo de uma vez (com atalho na área de trabalho)

**Dê duplo-clique em `Instalar_JARVIS.bat`** — não precisa abrir PowerShell
nem digitar nenhum comando. Uma janela abre sozinha e faz tudo:

1. Cria um ambiente Python isolado
2. Instala todas as dependências
3. Cria o `.env` (se ainda não existir)
4. Cria um atalho **"J.A.R.V.I.S."** na área de trabalho, com ícone
5. Pergunta se você quer que ele ligue sozinho com o Windows (`s`/`n`)

**Nota sobre o ícone**: o `Instalar_JARVIS.bat` em si usa o ícone padrão do
Windows pra `.bat` (não dá pra mudar isso — limitação do formato, não falta
de tentativa). Mas você só usa ele **uma vez**; o atalho **"J.A.R.V.I.S."**
que ele cria na área de trabalho, esse sim tem o ícone certo, e é o que
você vai clicar no dia a dia.

**Depois que o instalador terminar:**
1. Abra o `.env` (criado automaticamente) e confirme/preencha `JARVIS_API_KEY`
2. Instale o Ollama e rode `ollama pull gemma4` (passo 1 acima, se ainda não fez)
3. Clique no atalho **"J.A.R.V.I.S."** na área de trabalho — ele liga o
   servidor sozinho (se ainda não estiver rodando) e abre o app no navegador

### Rodando manualmente, sem o instalador (alternativa)
```powershell
pip install -r requirements.txt
copy .env.example .env
uvicorn app:app --app-dir src --host 0.0.0.0 --port 8000
```
Abra **http://localhost:8000/docs** (Swagger) ou **http://localhost:8000/app** (chat).

## Gerando o instalador .exe (com ícone próprio, opcional)

Se quiser um instalador de verdade — `.exe`, com o ícone do JARVIS, igual
Discord/Chrome — em vez do `.bat` (que usa o ícone genérico do Windows),
dá pra compilar um. **Isso é opcional**: o `Instalar_JARVIS.bat` já
funciona sozinho sem esse passo extra.

### Compilar (rode uma vez, precisa de Python instalado)
```powershell
build_installer.bat
```
Isso instala o PyInstaller temporariamente, compila `scripts\installer.py`
num `Instalar_JARVIS.exe` (colocado na raiz do projeto) com o ícone
embutido, e limpa os arquivos temporários. Vai levar um ou dois minutos.

### O que isso resolve, e o que **não** resolve
- ✅ Resolve: o instalador em si vira um `.exe` de verdade, com ícone
  próprio, sem precisar do `.bat` com ícone genérico.
- ❌ **Não** resolve: seu PC (ou de quem for usar) ainda precisa ter
  **Python instalado** — o `.exe` do instalador só automatiza os mesmos
  passos de sempre (criar ambiente virtual, instalar dependências), ele
  não elimina a necessidade de Python existir no sistema. Isso é inerente
  ao JARVIS ser um programa Python — não tem como contornar isso sem
  reescrever o projeto inteiro em outra linguagem.

### ⚠️ Sobre o teste deste `.exe`
Não foi possível rodar o `.exe` do Windows de verdade durante o
desenvolvimento (ambiente Linux, sem Windows disponível). O que foi
validado de verdade: o PyInstaller processa o `scripts\installer.py` sem
erros de análise de dependências (inclusive a parte do `win32com`,
específica do Windows) — testei isso duas vezes, antes e depois de mover o
arquivo pra pasta `scripts/`. Também rodei o binário resultante (versão
Linux, só pra testar a lógica) simulando a estrutura real de pastas, e
confirmei que ele calcula corretamente a raiz do projeto a partir de onde
o `.exe` está. O primeiro teste do `.exe` compilado
de verdade só acontece no seu PC — se der erro, me manda a mensagem exata.

## Atualizando depois de mudanças novas

**Isso é o mais importante pra quem já instalou**: quando eu (ou você)
mudar algo no código, você **não precisa desinstalar nada**. Só rode:
```powershell
update.bat
```
Ele puxa as mudanças do GitHub e reinstala dependências novas, se houver —
seu `.env` e suas memórias (`jarvis.db`) **nunca são tocados**, porque os
dois ficam fora do controle de versão de propósito. O atalho da área de
trabalho continua funcionando igual, sem precisar recriar nada.

## Estrutura do projeto

```
jarvis-ia/
├── Instalar_JARVIS.bat      # 1º clique: instala tudo (chama scripts/setup.ps1)
├── Desinstalar_JARVIS.bat   # Desinstala (chama scripts/uninstall.ps1)
├── update.bat               # Atualiza o código sem mexer no .env/memórias
├── build_installer.bat      # Opcional: compila um .exe com ícone (scripts/installer.py)
├── README.md
├── LICENSE                  # MIT — outras pessoas podem usar livremente
├── requirements.txt
├── .env.example
├── .gitignore
│
├── src/                      # Todo o código Python da aplicação, junto
│   ├── app.py                  # API principal (FastAPI)
│   ├── database.py               # Persistência (SQLite — fica na raiz, não aqui)
│   ├── tools.py                    # Ferramentas: memória, comandos, Word, Linear, apps
│   ├── llm_client.py                 # Fala com o Ollama (modelo local)
│   ├── media.py                        # Processamento de áudio/vídeo
│   ├── embeddings.py                     # Busca semântica na memória
│   ├── tts.py                              # Texto pra fala (espeak-ng)
│   ├── word_control.py                       # Automação do Microsoft Word (Windows only)
│   ├── google_calendar.py                      # Integração com Google Calendar
│   ├── wake_word_listener.py                   # "Hey JARVIS" — ativação por voz
│   └── tray_app.py                               # Ícone na bandeja do sistema
│
├── config/
│   └── apps_config.json    # Nome → comando dos apps/jogos que abrem por voz
│
├── assets/
│   └── icon.ico             # Ícone usado pelos atalhos
│
├── static/                  # App web instalável (PWA), servido em /app
│   ├── index.html
│   ├── manifest.json
│   ├── icon-192.png
│   └── icon-512.png
│
├── .github/
│   └── workflows/
│       └── ci.yml           # Checa sintaxe + instalação no Windows a cada commit
│
├── scripts/                 # Lógica interna de instalação (não mexa direto aqui)
│   ├── setup.ps1             # O que o Instalar_JARVIS.bat roda por trás
│   ├── uninstall.ps1          # O que o Desinstalar_JARVIS.bat roda por trás
│   ├── installer.py            # Mesma lógica do setup.ps1, em Python — compilável em .exe
│   ├── setup_google_calendar.py  # Autorização inicial do Google Calendar (rode 1x)
│   ├── launch_jarvis.bat        # O que o atalho da área de trabalho executa
│   ├── start_tray.bat            # Sobe a bandeja sem nenhuma janela visível
│   ├── start_server.bat           # Rodar manualmente p/ depuração (janela visível)
│   └── start_wake_word.bat         # Rodar manualmente p/ depuração (janela visível)
│
└── finetuning/               # Opcional: personalizar a personalidade do modelo (LoRA)
    ├── dataset.jsonl           # Exemplos de treino (personalidade JARVIS)
    ├── add_example.py           # Ferramenta pra adicionar exemplos facilmente
    ├── train.py                   # Script de treino (Unsloth + LoRA)
    ├── export_to_ollama.py         # Exporta o resultado pro Ollama
    ├── requirements.txt             # Dependências específicas (torch, unsloth, etc)
    └── README.md                     # Passo a passo completo
```

**Nota técnica**: os arquivos em `src/` continuam se importando entre si
normalmente (`import database as db`, `import tools`, etc) — o comando
`uvicorn app:app --app-dir src` avisa o uvicorn pra procurar o `app.py`
dentro de `src/` e automaticamente deixa os módulos vizinhos visíveis pros
imports. `database.py` e `tools.py` sabem "subir um nível" pra continuar
salvando o banco de dados (`jarvis.db`) e lendo o `config/apps_config.json`
na raiz do projeto, não dentro de `src/`.

## Ferramentas disponíveis

| Ferramenta | O que faz |
|---|---|
| `remember` / `recall` | Memória de longo prazo com busca semântica |
| `propose_command` | Comando de terminal genérico — precisa de aprovação |
| `open_app` | Abre um app/jogo pré-configurado (Steam, Discord, League...) — **executa na hora, sem aprovação** |
| `list_available_apps` | Lista o que já está configurado pra abrir por voz |
| `write_word_document` | Abre o Word e escreve um documento de verdade |
| `ver_tela` | Captura a tela e analisa visualmente (precisa de modelo com visão) |
| `list_calendar_events` / `create_calendar_event` | Integração com Google Calendar (opcional) |
| `list_linear_teams` / `create_linear_issue` | Integração com Linear (opcional) |

## Visão — o JARVIS "vendo" sua tela

A tool `ver_tela` tira uma captura da tela atual e manda pro modelo analisar
de verdade — "Hey JARVIS, o que tem de errado nessa tela?" ou "descreve o
que está aberto agora".

### Requisito
Só funciona com um modelo que tenha **suporte a visão nativo**. O padrão
recomendado (`gemma4`) já tem isso. Modelos só-texto (como `qwen3:8b`)
recebem a captura, mas não conseguem "enxergar" o conteúdo — o JARVIS vai
avisar que precisa trocar de modelo se isso acontecer.

### Como funciona por trás
A tela é capturada, redimensionada (evita gastar processamento à toa numa
imagem 4K) e comprimida em JPEG antes de ir pro modelo — testei isso de
verdade: uma captura simulada de 3840×2160 virou 1280×720 mantendo a
proporção, e decodificou de volta sem problema.

### ⚠️ Sobre o teste
A captura de tela em si (`PIL.ImageGrab`) não pôde ser testada com uma tela
de verdade neste ambiente (servidor Linux sem interface gráfica) — só
simulei com uma imagem sintética no lugar de uma captura real. O bloqueio
de plataforma (Windows/Mac apenas) funciona corretamente. O fluxo completo
de "modelo pede pra ver a tela → captura → imagem chega no histórico da
conversa → modelo responde sobre o que viu" foi testado de ponta a ponta
com a captura mockada, e funcionou certinho.

## Abrindo jogos e programas por voz

O `open_app` é diferente do `propose_command`: em vez do modelo tentar
"adivinhar" o comando certo pra abrir um programa (e errar o caminho do
executável, que varia de PC pra PC), você mesmo mapeia nome → comando uma
vez em `config/apps_config.json`, e depois é só falar o nome — abre na hora, sem
pedir aprovação (abrir um programa é seguro e reversível, diferente de um
comando genérico de terminal).

### Configurando
Abra `config/apps_config.json` e ajuste os caminhos — principalmente os do Riot
Client/League/Valorant, que **não têm um link universal** e variam
conforme onde você instalou. Pra confirmar o caminho certo no seu PC:
clique direito no atalho → Propriedades → campo "Destino".

Já vem configurado com URIs oficiais (funcionam sem editar nada): Steam,
Discord, Spotify, Epic Games, Chrome.

### Usando
```
"Hey JARVIS, abre o Steam"
"Hey JARVIS, abre o League"
"Hey JARVIS, quais apps eu tenho configurado?"
```

### Por que login/senha ficou de fora — de propósito

Cogitamos automatizar login também (copiar usuário/senha e "colar" na
plataforma certa), mas decidimos não construir isso. Não é falta de
capacidade técnica — é que uma IA decidindo, a partir de comando de voz,
quando e onde digitar uma senha é um risco real: se a wake word detectar
errado, ou a janela ativa não for a esperada, a senha pode ir pro lugar
errado. Diferente de abrir um programa (no pior caso, abre errado e você
fecha), errar um login é um problema sem volta fácil.

**Use um gerenciador de senhas de verdade pra essa parte** — Bitwarden,
1Password, ou o Gerenciador de Credenciais do Windows. Todos têm
autofill/atalho de teclado rápido. O JARVIS abre o programa, você loga com
o gerenciador — continua rápido, mas a senha nunca passa pela IA.

## Sobre o `propose_command` e o Word — leia antes de usar

Como tudo roda na mesma máquina agora, **aprovar um comando já executa na
hora** — não existe mais a fila remota com agente separado (isso só fazia
sentido quando o servidor estava na nuvem). Fluxo:

1. Você pede algo que exige ação no sistema.
2. O modelo registra o comando (`pending`) e avisa o ID.
3. Você confere com `GET /commands?status=pending`.
4. Aprova: `POST /commands/{id}/approve` — **executa imediatamente** e devolve o resultado.

O `write_word_document` é mais direto ainda: ele controla o Word via COM
(a mesma tecnologia de macros VBA) — abre o Word de propósito **visível**,
você vê o documento sendo criado, não é uma ação escondida.

**⚠️ Sobre a automação do Word especificamente**: esse código foi escrito
com base na documentação da API, mas não pôde ser testado de ponta a ponta
durante o desenvolvimento (ambiente sem Windows/Word disponível). Teste com
cuidado antes de confiar nele pra algo importante — se der erro, me mostre
a mensagem que ajusto.

## "Hey JARVIS" — ativação por voz, sempre ouvindo

Além do botão de microfone no `/app`, tem um segundo jeito de usar: um
programa separado que fica escutando o microfone em segundo plano — sem
precisar abrir navegador nem clicar em nada. Fala **"Hey JARVIS"**, espera o
bipe, fala seu pedido, e a resposta vem falada de volta.

### Como funciona
Usa o **openWakeWord** com o modelo `hey_jarvis` (já incluído no pacote — não
precisa baixar nada separado). Só o trecho "hey jarvis" é processado
localmente e continuamente; o áudio da sua fala só é enviado ao servidor
**depois** da wake word ser detectada.

### Rodar
Com o servidor principal já rodando (`uvicorn app:app --app-dir src ...`
num terminal), abra outro terminal:
```powershell
python src\wake_word_listener.py
```
Fala "Hey JARVIS", espera o bipe, fala seu pedido. A resposta toca no
alto-falante automaticamente.

### Ajustando a sensibilidade
Se ele disparar sozinho sem ninguém falando (falso positivo), aumente
`WAKE_WORD_THRESHOLD` no `.env` (ex: `0.6` ou `0.7`). Se ele não te ouvir
mesmo falando claramente, diminua (ex: `0.4`).

### ⚠️ O que não pôde ser testado
A captura contínua de microfone e a detecção em tempo real **não puderam
ser testadas** durante o desenvolvimento (o ambiente onde este código foi
escrito não tem microfone). O que testei de verdade: o modelo "hey jarvis"
carrega corretamente, faz predições reais (silêncio → score 0.0), a
montagem do arquivo de áudio gravado está correta, e a comunicação com o
servidor funciona. A parte "ao vivo" (você falando de verdade no seu
microfone) só vai ser validada quando você rodar no seu PC.

## Ícone na bandeja do sistema

Em vez de janelas de terminal minimizadas, o JARVIS roda como um **ícone na
bandeja** (perto do relógio, junto com Discord, Steam, etc) — clique direito
nele pra:

- **Abrir J.A.R.V.I.S.** — abre o app no navegador
- **Hey JARVIS (voz)** — liga/desliga o listener de voz, com um ✓ mostrando
  o estado atual
- **Reiniciar servidor**
- **Sair** — encerra tudo (servidor + voz) de vez

Nenhuma janela de console fica visível — o ícone de bandeja gerencia os
processos por trás das cenas.

**Pra depuração**: se algo não estiver funcionando e você quiser ver os
logs/erros em tempo real, `scripts\start_server.bat` e
`scripts\start_wake_word.bat` (com janela visível) continuam funcionando —
rode-os manualmente quando precisar investigar algum problema.

### Ligando junto com o Windows

Se você já rodou o `Instalar_JARVIS.bat` (que chama o `scripts\setup.ps1`
por trás) e respondeu "s"
na pergunta sobre auto-start, isso já está configurado — pode pular esta
seção.

### Onde isso aparece e como gerenciar
O instalador coloca **um atalho** ("J.A.R.V.I.S.") na **pasta de
Inicialização** do Windows (`shell:startup`) — não no Agendador de Tarefas.
Isso é de propósito: itens ali aparecem no **Gerenciador de Tarefas → aba
"Aplicativos de inicialização"**, com ícone e nome, e um botão de
**Habilitar/Desabilitar** direto por lá — igual qualquer outro programa que
abre sozinho com o Windows (Steam, Discord, etc). Se quiser desligar o
auto-start temporariamente sem desinstalar nada, é só desabilitar por ali.

### Ativando manualmente depois (se pulou na instalação)
Abra a pasta de Inicialização (`Win+R` → digite `shell:startup` → Enter) e
crie um atalho pra `scripts\start_tray.bat` ali dentro (clique direito no
arquivo → Enviar para → Área de trabalho, depois mova o atalho gerado pra
essa pasta). Ou rode o `Instalar_JARVIS.bat` de novo — ele não reinstala as
dependências se já existirem, só refaz essa parte.

Depois de configurado, reinicie o PC uma vez pra confirmar que sobe
sozinho (procure o ícone na bandeja).

## Acessando do celular

Como não tem mais URL pública (era a Render antes), pra acessar do celular
sem abrir porta no roteador, use **Tailscale** (gratuito):
1. Instale o Tailscale no PC e no celular, mesma conta.
2. No PC, rode `tailscale ip` pra pegar seu endereço (`100.x.x.x`).
3. Do celular: `http://100.x.x.x:8000/app`.

## Instalando como app
Com o link acima aberto no navegador do celular ou do PC: menu → "Instalar
app" (Android/Chrome/Edge) ou compartilhar → "Adicionar à Tela de Início"
(iPhone, precisa ser Safari).

## Desinstalando

**Dê duplo-clique em `Desinstalar_JARVIS.bat`** — mesmo padrão do
instalador, sem precisar abrir PowerShell.

Ele remove:
- O atalho da área de trabalho
- A inicialização automática com o Windows (se estava configurada)
- Processos do JARVIS que estejam rodando no momento

E pergunta (você decide, nada é apagado sem confirmar):
- Se quer apagar suas memórias (`jarvis.db`) e configurações (`.env`) — **isso não pode ser desfeito**
- Se quer remover o ambiente virtual Python (`venv`) — libera espaço, mas é recriado sozinho se reinstalar depois

**O que ele não faz sozinho**: apagar a pasta do projeto inteira. Como o
script roda de dentro dela, apagar a própria pasta em execução é frágil
— ao final, ele te mostra o caminho exato pra você apagar manualmente,
se quiser remover tudo por completo.

## Publicando no GitHub

```powershell
cd jarvis-ia
git init
git add .
git status   # confirme que .env NÃO aparece na lista
git commit -m "J.A.R.V.I.S. local — primeira versão"
gh repo create jarvis-ia --public --source=. --push
```

Como a licença é MIT, qualquer pessoa pode clonar, instalar o Ollama, e
rodar sua própria cópia:
```powershell
git clone https://github.com/SEU-USUARIO/jarvis-ia.git
```
Depois é só dar duplo-clique em `Instalar_JARVIS.bat` dentro da pasta
clonada, e rodar `ollama pull gemma4`.

**Nota importante**: o `update.bat` só funciona se o projeto foi baixado
via `git clone` (não um `.zip` baixado manualmente) — é o `git pull` por
trás que permite atualizar sem perder configurações. Se você (ou alguém
que baixou) pegou via `.zip`, a recomendação é clonar via git desde o
início, exatamente pra ter esse caminho de atualização mais fácil.

## Limitações desta versão (comparado à versão que usava Claude)

- **Visão via `ver_tela` funciona, mas depende do modelo** — só com modelos
  que tenham suporte nativo (ex: `gemma4`). Modelos só-texto recebem a
  captura sem conseguir "ver" de verdade.
- **Sem busca na web nativa** — esse recurso dependia de um tool exclusivo
  da Anthropic.
- **Ferramentas menos confiáveis** — o modelo local erra mais ao decidir
  quando chamar `remember`, `propose_command` etc, comparado ao Claude.
- **Precisa do PC ligado** — voltamos a essa realidade ao escolher "zero custo",
  é a mesma troca que discutimos antes de decidir essa arquitetura.

## Integração com Google Calendar

Assim como o Linear, essa integração usa a API oficial do Google — e tem um
**pré-requisito que só você pode fazer**: criar credenciais no Google Cloud
Console. Não tem como automatizar isso, é uma exigência de segurança do
próprio Google pra qualquer app que acesse dados pessoais de alguém.

### 1. Criar as credenciais (uma vez só, ~10-15 minutos)
1. Acesse **console.cloud.google.com**
2. Crie um projeto novo (qualquer nome, ex: "JARVIS")
3. No menu, vá em **APIs e Serviços → Biblioteca**, procure **"Google
   Calendar API"** e clique em **Ativar**
4. Vá em **APIs e Serviços → Tela de consentimento OAuth**:
   - Tipo de usuário: **Externo** (a menos que tenha Google Workspace)
   - Preenche nome do app, e-mail — o resto pode deixar padrão
   - Em "Escopos", não precisa adicionar nada manualmente
   - Em "Usuários de teste", adiciona seu próprio e-mail do Google
5. Vá em **APIs e Serviços → Credenciais → Criar Credenciais → ID do
   cliente OAuth**:
   - Tipo de aplicativo: **App para computador (Desktop app)**
   - Nome: qualquer um
6. Depois de criar, clica em **Baixar JSON** — isso baixa um arquivo
7. Renomeia esse arquivo pra `credentials.json` e coloca na **raiz** do
   projeto (do lado do `.env`)

### 2. Autorizar (uma vez só)
```bash
python scripts/setup_google_calendar.py
```
Isso abre o navegador, você loga na sua conta Google e autoriza. Depois
disso, salva um `token.json` na raiz — o JARVIS usa esse arquivo sozinho
dali em diante, sem abrir navegador de novo (a menos que expire, aí ele
renova sozinho).

### 3. Usar
```
"Hey JARVIS, o que eu tenho na agenda?"
"Hey JARVIS, marca uma reunião amanhã às 15h"
```

### Segurança
`credentials.json` e `token.json` **nunca são commitados** (já protegidos
no `.gitignore`) — testei isso de verdade, criando os dois arquivos e
confirmando com `git status` que nenhum aparece pra commit. O `token.json`
em especial dá acesso direto ao seu calendário — trate como uma senha.

### ⚠️ Sobre o teste
Não tenho como gerar credenciais reais do Google nem abrir navegador aqui —
o fluxo de autorização (OAuth) só valida no seu PC. O que testei de
verdade: a lógica de criação de evento (cálculo de horário de início/fim
a partir da duração) com a API do Google mockada, e o comportamento de
"calendário não configurado ainda" avisando com clareza em vez de inventar
eventos.

## Fine-tuning — dando personalidade própria ao modelo

Tem uma pasta `finetuning/` com um pipeline completo de LoRA fine-tuning
pra ensinar o JARVIS a responder com uma personalidade mais consistente
(estilo formal, "senhor", humor seco) — veja `finetuning/README.md` pro
passo a passo completo. É opcional e avançado; requer GPU NVIDIA com pelo
menos 8GB de VRAM.

## Próximos passos possíveis
- Testar modelos maiores (`qwen3:14b`) se quiser mais qualidade e sua GPU aguentar.
- Trocar `espeak-ng` por Piper pra voz mais natural (ainda local).
- Se um dia quiser voltar a rodar 24/7 sem o PC ligado, a versão anterior
  (Claude + Render + Neon) continua sendo a arquitetura certa pra isso — as
  duas versões podem conviver, são só configurações diferentes do mesmo
  conceito de produto.
