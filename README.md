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
   ollama pull gemma4:e2b
   ```
   Isso baixa uns 5GB — só acontece uma vez. **Importante**: usamos
   especificamente a variante `:e2b` (mais leve) porque testamos na prática
   e confirmamos que o `gemma4` puro (sem sufixo) trava indefinidamente em
   algumas GPUs — mesmo com VRAM aparentemente suficiente. Se sua GPU for
   bem potente, pode tentar `gemma4` (sem sufixo) depois, mas teste com
   cuidado antes de confiar nele pro dia a dia.
4. Teste rapidamente:
   ```
   ollama run gemma4:e2b
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
3. **Cria o `.env` sozinho** — detecta sua GPU automaticamente (via
   `nvidia-smi`) e já escolhe o modelo certo pra sua máquina (`gemma4` se
   tiver GPU NVIDIA com 8GB+ de VRAM, `qwen3:4b` — mais leve — caso
   contrário), além de gerar uma `JARVIS_API_KEY` forte sozinho. Você não
   precisa editar nada manualmente pra começar a usar.
4. Se o Ollama já estiver instalado, **oferece baixar o modelo recomendado
   na hora** (`s`/`n`) — não precisa lembrar de rodar `ollama pull` depois
5. Cria um atalho **"J.A.R.V.I.S."** na área de trabalho, com ícone
6. Pergunta se você quer que ele ligue sozinho com o Windows (`s`/`n`)

**Nota sobre o ícone**: o `Instalar_JARVIS.bat` em si usa o ícone padrão do
Windows pra `.bat` (não dá pra mudar isso — limitação do formato, não falta
de tentativa). Mas você só usa ele **uma vez**; o atalho **"J.A.R.V.I.S."**
que ele cria na área de trabalho, esse sim tem o ícone certo, e é o que
você vai clicar no dia a dia.

**Depois que o instalador terminar:**
1. Se você pulou o download automático do modelo no passo 4, instale o
   Ollama (se ainda não tiver) e rode `ollama pull <modelo>` manualmente
   (o nome exato aparece no `.env`, campo `JARVIS_MODEL`)
2. Clique no atalho **"J.A.R.V.I.S."** na área de trabalho — ele liga o
   servidor sozinho (se ainda não estiver rodando) e abre o app no navegador

**Se quiser trocar o modelo depois** (por exemplo, testar o `gemma4:26b` se
tiver uma GPU bem potente), é só editar `JARVIS_MODEL` no `.env` manualmente
e reiniciar o JARVIS — a detecção automática só acontece na primeira vez
que o `.env` é criado.

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
│   ├── mouse_control.py                          # Controle de mouse/teclado (clicar, digitar)
│   ├── smart_light.py                              # Controle de lâmpada Tapo/Kasa (opcional)
│   ├── calendar_hub.py                              # Central de Agenda (mescla via iCal)
│   ├── email_hub.py                                  # Central de E-mails (IMAP + triagem)
│   ├── news_radar.py                                 # Radar de Notícias (RSS)
│   ├── morning_digest.py                             # Morning Digest (junta os 3 acima)
│   ├── wake_word_listener.py                   # "Hey JARVIS" — ativação por voz
│   └── tray_app.py                               # Ícone na bandeja do sistema
│
├── config/
│   ├── apps_config.json    # Nome → comando dos apps/jogos que abrem por voz
│   └── projects_config.json # Rotinas de projeto (editor + servidor + navegador)
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
| `abrir_projeto` | Abre uma rotina de projeto (editor + servidor + navegador) — **100% confiável, sem depender de clique** |
| `list_available_apps` / `list_available_projects` | Lista o que já está configurado pra abrir por voz |
| `write_word_document` | Abre o Word e escreve um documento de verdade |
| `ver_tela` | Captura a tela e analisa visualmente (precisa de modelo com visão) |
| `clicar_na_tela` / `digitar_texto` / `pressionar_tecla` | Controle de mouse/teclado — **AÇÃO REAL, veja avisos abaixo** |
| `list_calendar_events` / `create_calendar_event` | Integração com Google Calendar (opcional) |
| `controlar_luz` | Liga/desliga/ajusta brilho de lâmpada Tapo/Kasa (opcional) |
| `iniciar_configuracao_second_brain` | Inicia a entrevista guiada do Second Brain |
| `ver_agenda_hoje` / `ver_agenda_semana` / `proximo_compromisso` | Central de Agenda (múltiplas agendas mescladas) |
| `ver_emails` / `atualizar_emails` | Central de E-mails (triagem em Ação/Info/Ruído) |
| `ver_noticias` / `gerenciar_assuntos_noticia` | Radar de Notícias (RSS, grátis) |
| `gerar_morning_digest` | Briefing matinal falado, junta os 3 módulos acima |
| `cadastrar_app` | Cadastra um app novo direto na conversa, quando `open_app` não encontra |
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

## Controle de mouse e teclado — o JARVIS "agindo" na tela

**Você vê tudo em tempo real no chat**: cada vez que o JARVIS usa uma
ferramenta, aparece uma linha de atividade (ex: "🟡 Clicando em (960,
540)..."), e toda captura de tela que ele tira (`ver_tela`) aparece como
imagem de verdade no meio da conversa — clicável pra ver em tamanho
maior. É a mesma ideia por trás do Cowork: você acompanha o que está
acontecendo, não só recebe uma resposta final às cegas. Testei isso de
ponta a ponta simulando os eventos exatos que o servidor gera, confirmando
que os rótulos de atividade, o print, e a resposta final aparecem
separados corretamente (antes dessa mudança, o rótulo da ferramenta
ficava misturado dentro do texto da resposta — corrigi isso também).

Além de "ver" a tela, o JARVIS pode **interagir** com o que vê: clicar em
algo, digitar texto, navegar dentro de um programa já aberto (ex: "entra
na Steam e abre esse jogo"). É basicamente o mesmo princípio por trás do
"Computer Use" do Claude — captura de tela → o modelo decide onde
clicar → clique de verdade.

### ⚠️ Isso é mais poderoso — e mais arriscado — que qualquer outra tool

Diferente de `open_app` (só abre programas pré-configurados) ou
`propose_command` (precisa de aprovação antes de rodar), o controle de
mouse/teclado age **imediatamente**, em **qualquer coisa visível na
tela** — incluindo botões de compra, exclusão, envio de mensagem, etc.
Não existe uma lista de "coisas seguras pra clicar", é a tela inteira.

**Recomendações de uso:**
- Peça tarefas específicas e bem definidas ("abre o jogo X na Steam"), não
  comandos vagos ("mexe no meu PC")
- Fique de olho na tela enquanto ele executa, principalmente nas primeiras
  vezes usando essa função
- Se algo parecer estar indo errado, você sempre pode assumir o controle
  do mouse/teclado manualmente a qualquer momento — não existe um "modo
  exclusivo" que trave seu controle

### Como funciona por trás (resolvendo um problema técnico real)
O `ver_tela` redimensiona a captura antes de mandar pro modelo (economia
de processamento) — então as coordenadas que o modelo "vê" na imagem NÃO
são as coordenadas reais da tela. O `clicar_na_tela` converte isso
automaticamente: guarda a proporção de redimensionamento de cada captura,
e escala o clique de volta pra posição real. **Testei essa conversão com
matemática exata**: uma captura simulada de 1920×1080 redimensionada pra
1280×720, clicando no "centro" da imagem pequena (640,360), converteu
corretamente pro centro real da tela (960,540) — testei os dois cantos
também, batendo exatamente.

### ⚠️ Sobre o teste
O clique/digitação de verdade **não pôde ser testado com mouse/teclado
reais** (ambiente sem interface gráfica) — usei `pyautogui` mockado pra
validar a lógica. O que testei de verdade: a matemática de conversão de
coordenadas (a parte mais crítica de estar certa) e o fluxo completo
captura → escala salva → clique convertido, ponta a ponta. O primeiro
teste com mouse/teclado reais só acontece no seu PC — recomendo começar
com tarefas simples e de baixo risco pra ganhar confiança.

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
Discord, Spotify, Epic Games, Chrome, Bloco de Notas, Calculadora.

**Ou pela interface** (mais fácil): na tela **Configurar** do app web, tem
uma seção **"Aplicativos"** — mostra a lista atual, com botão de remover em
cada um, e um formulário pra adicionar um novo (nome + comando), sem
precisar editar o JSON manualmente. Testei o fluxo completo (listar,
adicionar, confirmar que apareceu, remover, confirmar que sumiu) contra o
servidor real rodando, não simulado.

**Ou direto na conversa**: se você pedir pra abrir algo que não está
configurado, o JARVIS não desiste — ele pergunta o comando/caminho do
programa, e cadastra sozinho (`cadastrar_app`) assim que você responder.
Da próxima vez, já abre direto, sem perguntar de novo. Testei o ciclo
completo: tentar abrir algo não cadastrado → falha com mensagem clara →
cadastra → tenta de novo → abre com sucesso.

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

### Escolhendo qual microfone usar
Se seu PC tem mais de um microfone (ex: interno + headset USB), o listener
usa o padrão do Windows por padrão. Pra escolher outro:
```powershell
python src\wake_word_listener.py --list-devices
```
Isso mostra a lista numerada dos microfones disponíveis. Coloca o número
(ou um trecho do nome, ex: `Headset`) no `.env`:
```
WAKE_WORD_INPUT_DEVICE=1
```
Testei essa lógica com 5 cenários diferentes: vazio (usa padrão), número
direto, nome parcial, nome inexistente (erro claro), e confirmei que um
dispositivo de **saída** (alto-falante) nunca é confundido com entrada.

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

## Escolhendo microfone e saída de áudio na interface web

Na tela **Configurar** do app web, tem dois seletores:
- **Microfone** — qual dispositivo de entrada usar no botão de gravar mensagem
- **Saída de áudio** — onde a resposta falada (TTS) toca (útil se você tem
  caixas de som E um headset, por exemplo, e quer escolher qual usar)

Cada um tem um botão de teste: **"Testar microfone (3s)"** grava e mostra
se captou som de verdade; **"Testar saída"** toca um bipe curto na saída
escolhida.

**Nota importante**: essas escolhas valem só pro app web — o listener "Hey
JARVIS" (que roda separado, em segundo plano) usa sua própria configuração
de microfone (`WAKE_WORD_INPUT_DEVICE` no `.env`, veja a seção acima),
porque são dois programas diferentes acessando o áudio de formas diferentes.

### Sobre erros "Could not start audio source" (comum com headsets Bluetooth)
Isso é um erro conhecido do navegador, não do JARVIS — acontece porque o
Windows precisa trocar o headset Bluetooth do "modo música" pro "modo
chamada" quando um app pede o microfone, e essa troca às vezes falha na
primeira tentativa. O JARVIS já tenta de novo automaticamente uma vez
quando detecta esse erro específico — se mesmo assim continuar falhando,
tenta: (1) desconectar e reconectar o Bluetooth, (2) testar o microfone em
outro programa (Gravador de Voz do Windows, por exemplo) pra confirmar se
o problema é só no navegador, (3) usar o microfone interno do PC como
alternativa.

### Testado
Simulei listas de dispositivos de entrada E saída com dados falsos (já que
não tenho hardware de áudio neste ambiente) — confirmei que os dois tipos
aparecem nos seletores certos, sem se misturar, e que a escolha de cada um
é salva independentemente. Testei também a lógica de retry automático pra
falhas tipo Bluetooth: simulei a primeira tentativa falhando exatamente
como o erro real, e confirmei que a segunda tentativa (automática) recupera
sozinha, com exatamente 2 chamadas ao navegador (não mais, não menos).
Encontrei e corrigi um bug real nesse processo: a variável do seletor
estava sendo declarada depois do ponto onde a tela de configurações podia
abrir automaticamente (isso acontece sempre que ainda não tem API key
configurada — ou seja, exatamente na primeira instalação de qualquer
pessoa) — sem a correção, a tela quebraria justo na primeira vez que
alguém abrisse o JARVIS.

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

## Diagnosticando problemas — arquivo de log

Se uma resposta não chegar, demorar muito, ou der erro sem explicação clara,
o JARVIS agora grava um log detalhado em `logs/jarvis.log` — com timestamp e
duração de cada etapa (busca de memória, chamada ao modelo, cada ferramenta
usada), e o erro completo (com traceback) se algo falhar.

### Como usar pra diagnosticar
1. Reproduz o problema (manda a mensagem que travou/demorou)
2. Abre `logs/jarvis.log` (fica na raiz do projeto)
3. As últimas linhas mostram exatamente onde o tempo foi gasto — ex:
   ```
   [chat] session=xyz | mensagem='oi jarvis'
   [embeddings] Carregando modelo pela primeira vez (timeout de 10.0s)...
   [embeddings] Timeout de 10.0s ao carregar modelo...
   [chat] session=xyz | iteração 1/20 — chamando o modelo...
   [chat] session=xyz | modelo respondeu em 3.2s | tool_calls=[]
   [chat] session=xyz | concluído, resposta com 142 caracteres
   ```

### Dois timeouts que existem por causa disso
Descobri dois lugares que podiam travar por tempo indefinido (ou bem mais
que o razoável) sem timeout nenhum configurado — os dois agora têm limite:
- `OLLAMA_TIMEOUT_SECONDS` (padrão 60s) — quanto esperar o Ollama responder
- `EMBEDDINGS_TIMEOUT_SECONDS` (padrão 10s) — quanto esperar o modelo de
  busca de memória baixar na primeira vez (isso sozinho podia levar até 40s
  antes, por causa de uma lógica de retry interna da biblioteca que ignora
  configurações normais de timeout — tive que forçar um limite de verdade
  rodando o carregamento numa thread separada)

### Testado de verdade
Simulei os dois cenários de trava (servidor que aceita conexão mas nunca
responde, e rede sem acesso ao Hugging Face) e confirmei os tempos reais:
o Ollama desiste em ~7s com timeout de 3s configurado (ao invés de nunca);
os embeddings desistem em ~5,5s com timeout de 5s configurado (ao invés de
~39s, que é o que a biblioteca levaria sozinha). No fluxo completo, uma
mensagem que antes podia demorar 40+ segundos só nessa parte agora resolve
em poucos segundos.

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

## "Às vezes trava" ou demora muito — o Ollama descarregando o modelo

Se o JARVIS demora muito (ou parece travar) só **de vez em quando**, não
toda mensagem, o motivo mais provável é: o Ollama descarrega o modelo da
memória depois de alguns minutos sem uso (padrão: 5 minutos). Na próxima
pergunta, ele precisa recarregar tudo do zero — isso pode levar bem mais
tempo que uma resposta normal, e some do timeout de 60s configurado.

### A correção que funciona de verdade
Tentamos resolver isso mandando `keep_alive` em cada chamada, mas
**existe um bug conhecido do Ollama** que ignora esse parâmetro quando vem
pela API compatível com OpenAI (que é como o JARVIS se comunica com ele) —
[issue aberta no GitHub deles](https://github.com/ollama/ollama/issues/11458).
Mandamos mesmo assim (caso a versão de vocês já tenha corrigido), mas a
correção que **sempre** funciona é configurar isso no nível do sistema:

**No Windows:**
1. Abre o menu Iniciar → digita "variáveis de ambiente" → abre "Editar as
   variáveis de ambiente do sistema"
2. Clica em "Variáveis de Ambiente..."
3. Em "Variáveis do usuário" (ou "Variáveis do sistema"), clica em "Novo..."
4. Nome: `OLLAMA_KEEP_ALIVE`
5. Valor: `30m` (ou `1h`, se quiser manter carregado por mais tempo)
6. OK em tudo
7. **Reinicia o Ollama** (clica com botão direito no ícone da bandeja →
   Quit Ollama, depois abre ele de novo) — ele só lê essa variável na
   hora que inicia, então precisa reiniciar pra valer

### Testado
Confirmei que o JARVIS manda `think: false` e `keep_alive: "30m"` juntos
em toda chamada ao Ollama — testei capturando a chamada real (mockada) e
conferindo os dois parâmetros presentes. O que **não** dá pra garantir
daqui é se o Ollama de vocês realmente respeita o `keep_alive` vindo do
JARVIS (por causa do bug citado) — por isso a configuração no Windows é
a garantia de verdade.

## Modelos "raciocinadores" (Qwen3 e similares) — pensamento desligado

Modelos como o `qwen3` "pensam em voz alta" antes de responder por padrão —
isso deixa a resposta mais lenta e, se vazasse pro chat, apareceria como um
parágrafo de raciocínio interno confuso antes da resposta de verdade. O
JARVIS já desliga isso automaticamente (parâmetro `think: false` em toda
chamada ao Ollama), com uma proteção extra que filtra qualquer bloco de
pensamento que ainda vaze — inclusive quando as tags de abertura/fechamento
chegam **picadas entre pedaços diferentes** do streaming (testei esse
cenário específico, incluindo múltiplos blocos de pensamento na mesma
resposta — todos filtrados corretamente).

Se notar respostas mais lentas que o esperado com modelos raciocinadores,
isso já está mitigado — mas a "espessura" do raciocínio interno ainda
consome processamento mesmo desligado da exibição, então modelos desse
tipo tendem a ser um pouco mais lentos por natureza que modelos sem essa
capacidade.

## Rotinas de projeto — "abrir projeto" com um comando de voz

Diferente de `ver_tela`+`clicar_na_tela` (que dependem do modelo acertar
onde clicar — nem sempre confiável), essa é uma forma **100% determinística**
de fazer o JARVIS abrir várias coisas de uma vez: editor de código, servidor,
navegador — sem depender de nenhum clique.

### Configurando
Edita `config/projects_config.json`. Cada projeto é uma lista de passos:
- `vscode` — abre uma pasta no VS Code (precisa do comando `code` no PATH)
- `comando` — roda qualquer comando de terminal
- `url` — abre uma URL no navegador padrão
- `esperar` — pausa alguns segundos (útil pra dar tempo de um servidor subir
  antes de abrir o navegador nele)

### Usando
```
"Hey JARVIS, abre o projeto jarvis-ia"
"Hey JARVIS, quais projetos eu tenho configurado?"
```

### Testado
Testei de ponta a ponta com um projeto de exemplo (comandos `echo` reais) —
listagem, correspondência por nome exato e parcial, execução sequencial dos
passos, e erro claro quando o projeto não existe. Todos passaram.

## Lâmpada inteligente (Tapo/Kasa)

Controle de luz via rede local — sem depender de nuvem no dia a dia (só a
configuração inicial da lâmpada, pelo app oficial, usa internet).

### 1. Compre uma lâmpada Tapo (ex: L510, L530) ou Kasa (ex: KL110, KL130)
### 2. Configure pelo app oficial (Tapo ou Kasa Smart)
Isso pareia a lâmpada com seu Wi-Fi — só essa etapa usa internet/conta.

### 3. Preenche o `.env`
```
TAPO_USERNAME=seu-email-da-conta-tapo
TAPO_PASSWORD=sua-senha-da-conta-tapo
TAPO_BULB_IP=192.168.x.x
```
O IP você encontra no app oficial, nas configurações do dispositivo.

### 4. Usa
```
"Hey JARVIS, liga a luz"
"Hey JARVIS, coloca a luz em 30% de brilho"
```

### ⚠️ Sobre o teste
**Não tenho nenhuma lâmpada física disponível** — não pôde ser testado com
hardware de verdade. O que fiz: revisei a biblioteca `python-kasa` instalada
de verdade e confirmei que os métodos usados (`Discover.discover_single`,
`device.turn_on()`, `device.modules[Module.Light].set_brightness()`) existem
com a assinatura exata que o código espera — inclusive corrigi uma chamada
que eu tinha escrito errada no início (a API mudou de método direto pra um
sistema de módulos numa versão recente da biblioteca, e só descobri isso
inspecionando o código de verdade). O comportamento de "lâmpada não
configurada" foi testado e funciona corretamente. O primeiro teste com
hardware real só acontece quando você comprar a lâmpada.

## Second Brain — o JARVIS "conhecendo" você de verdade

Diferente da memória comum (`remember`/`recall`, que só entra na conversa
quando parece relevante à pergunta), o Second Brain guarda fatos em **8
categorias fixas** que entram em **toda** conversa, sempre — é o que faz o
JARVIS "só saber" coisas sobre você, sem precisar você reforçar toda hora.

### As 8 áreas
`voce` (quem você é), `metas`, `carreira`, `projetos`, `financas`,
`aprendizado`, `saude`, `relacoes`.

### Como preencher
Duas formas, as duas funcionam:
- **Entrevista guiada**: peça "configura meu Second Brain" — o JARVIS
  pergunta uma área por vez, aceita "pula", e salva cada resposta sozinho.
  ⚠️ Isso usa uma tool dedicada (`iniciar_configuracao_second_brain`) em vez
  de só uma instrução solta no prompt — modelos locais menores seguem uma
  tool específica de forma bem mais confiável que uma regra escrita em
  meio a um prompt gigante com 18+ ferramentas descritas. Testei o fluxo
  completo (chamar a tool → receber a instrução → fazer a primeira
  pergunta certa) simulando a resposta do modelo.
- **Naturalmente**: mencione algo relevante numa conversa normal (ex: "estou
  aprendendo espanhol") — o JARVIS reconhece que isso se encaixa numa das 8
  áreas e oferece salvar lá

### O grafo visual
Na barra lateral, **"🧠 Second Brain"** — mostra um grafo animado com cada
nota como um nó colorido (cor por categoria) conectado ao núcleo central,
com pulsos de luz viajando pelas conexões. Clique num nó pra editar ou
excluir uma nota.

### Testado de verdade
- **Backend**: confirmei que só memórias nas 8 categorias entram no
  contexto "sempre presente" — testei com memórias de 4 categorias do
  Second Brain misturadas com uma memória comum, e a comum ficou de fora
  corretamente
- **Frontend**: gerei o grafo com dados reais e testei 11 pontos —
  geração do SVG, número certo de nós/arestas, todas as posições dentro
  dos limites da tela, núcleo centralizado, estado vazio funcionando, e a
  matemática da curva usada nos pulsos animados (confirmei que o pulso
  começa exatamente no centro e termina exatamente no nó de destino)
- **Não testado**: a animação rodando de verdade num navegador (só a
  matemática por trás dela) — visualmente só valida no seu PC

## Central de Agenda, E-mails, Notícias e Morning Digest

Quatro módulos que juntam informação do seu dia a dia — tudo rodando no
seu backend Python (sem "proxy" separado, sem CORS pra resolver, sem
pagar API por token: a triagem de e-mail e o digest usam seu próprio
Ollama local).

### 📅 Agenda
Mescla várias agendas do Google (contas diferentes inclusive) numa
timeline só. Não usa OAuth — usa o **"endereço secreto em formato iCal"**
de cada agenda (Google Agenda → ⚙ Configurações → clica na agenda →
"Integrar agenda" → copia o link). Mais simples que configurar OAuth pra
cada conta extra.

Comandos: `"o que eu tenho hoje?"`, `"minha agenda da semana"`, `"qual meu
próximo compromisso?"`. Configura pela tela (Configurar → Agendas) ou
direto na conversa (`"adiciona minha agenda de trabalho: [link]"`).

**Testado**: parsing de fuso horário, UTC, evento de dia inteiro,
recorrência (RRULE) e exclusão (EXDATE) — os 5 pontos que o próprio
material de referência avisa serem os que mais quebram em implementações
amadoras. Uma agenda com link quebrado não derruba as outras.

### 📧 E-mails
Conecta em quantas contas IMAP quiser (Gmail, Outlook, Yahoo, iCloud) e
classifica os e-mails recentes em 3 baldes: **Ação** (pede resposta/tem
prazo), **Info** (vale saber, não exige nada), **Ruído** (newsletter,
promoção). A classificação usa seu modelo Ollama local, numa única
chamada por lote — e fica em cache por Message-ID, então o mesmo e-mail
nunca é reclassificado duas vezes.

⚠️ **Nunca use a senha normal da conta.** Precisa de uma "senha de app":
1. Ativa verificação em 2 etapas (myaccount.google.com/security)
2. Gera a senha em myaccount.google.com/apppasswords
3. Cola essa senha de 16 letras (não a senha normal)

O JARVIS só lê (`BODY.PEEK`, nunca marca como lido), nunca envia, apaga
ou modifica nada. Só hosts IMAP conhecidos são aceitos (Gmail, Outlook,
Yahoo, iCloud) — não dá pra usar como proxy genérico.

**Testado**: decodificação de assunto acentuado (MIME encoded-word,
formato real do Gmail), extração de corpo preferindo texto puro sobre
HTML, cache confirmado (mandei o mesmo e-mail duas vezes, a segunda não
chamou o modelo de novo), fallback por heurística quando o modelo não
está disponível ou devolve algo que não é JSON válido.

### 📰 Notícias
Manchetes por assunto via RSS do Google News — grátis, sem chave de API.
Configura os assuntos que quiser acompanhar (Configurar → Assuntos de
notícia). Cache de 30 minutos por assunto, pra não buscar à toa.

**Testado**: parsing de RSS no formato real do Google News (remoção do
sufixo " - Fonte" do título, extração de fonte/link/data).

### 🌅 Morning Digest
Um briefing falado que junta os 3 módulos acima + previsão do tempo
(Open-Meteo, grátis, sem chave) + uma meta do Second Brain, numa única
chamada ao modelo local. Dispara com o botão "🌅 Bom dia" na barra
lateral, ou pedindo `"bom dia"` na conversa.

**Nunca fica mudo**: se o Ollama não estiver disponível, cai
automaticamente pra um template local (sem IA) que ainda inclui todos os
dados reais — só perde a naturalidade do texto, não a informação.

**Testado**: fallback offline com todos os dados presentes, geocodificação
de cidade com cache (não geocodifica de novo pra mesma cidade), tradução
de código de clima pra português. Encontrei e corrigi um bug real nesse
processo: a data saía com o mês em inglês (`27 de August de 2026`) por
depender da configuração de idioma do sistema — corrigi com uma lista
explícita de meses em português, igual já fazíamos com os dias da semana.

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
