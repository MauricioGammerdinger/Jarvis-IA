# J.A.R.V.I.S. local — 100% no seu PC, sem custo de IA

Assistente pessoal rodando inteiramente no seu computador: modelo de IA local
(via Ollama, gratuito), memória persistente, transcrição de áudio, texto pra
fala, controle do Word, comandos no sistema (com aprovação) — sem pagar nada
por token de IA, sem dado saindo da sua máquina (exceto se você mesmo usar a
integração opcional com Linear).

## O que você precisa saber antes de começar

Este projeto usa **Ollama** rodando um modelo aberto (recomendado: `qwen3:8b`)
em vez do Claude/GPT/Gemini pagos. A qualidade das respostas e a confiabilidade
do uso de ferramentas (memória, comandos, Word, Linear) é **boa, mas inferior**
a um modelo de ponta pago — é a troca consciente por não pagar nada. Se em
algum momento notar o JARVIS "esquecendo" de usar uma ferramenta ou
entendendo mal um pedido, geralmente ajuda: reformular de forma mais direta,
ou trocar pra um modelo Ollama maior (se sua GPU aguentar).

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
   ollama pull qwen3:8b
   ```
   Isso baixa uns 5-6GB — só acontece uma vez.
4. Teste rapidamente:
   ```
   ollama run qwen3:8b
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
2. Instale o Ollama e rode `ollama pull qwen3:8b` (passo 1 acima, se ainda não fez)
3. Clique no atalho **"J.A.R.V.I.S."** na área de trabalho — ele liga o
   servidor sozinho (se ainda não estiver rodando) e abre o app no navegador

### Rodando manualmente, sem o instalador (alternativa)
```powershell
pip install -r requirements.txt
copy .env.example .env
uvicorn app:app --host 0.0.0.0 --port 8000
```
Abra **http://localhost:8000/docs** (Swagger) ou **http://localhost:8000/app** (chat).

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
├── app.py                  # API principal (FastAPI)
├── database.py             # Persistência (SQLite — um arquivo só)
├── llm_client.py             # Fala com o Ollama (modelo local)
├── tools.py                   # Ferramentas: memória, comandos, Word, Linear
├── word_control.py             # Automação do Microsoft Word (Windows only)
├── wake_word_listener.py        # "Hey JARVIS" — ativação por voz em segundo plano
├── apps_config.json               # Nome → comando dos apps/jogos que abrem por voz
├── media.py                       # Processamento de áudio/vídeo
├── embeddings.py                    # Busca semântica na memória
├── tts.py                             # Texto pra fala (espeak-ng)
├── start_server.bat                    # Auto-start do servidor (Agendador de Tarefas)
├── start_wake_word.bat                  # Auto-start do wake word (Agendador de Tarefas)
├── setup.ps1                              # Instalador — roda 1x, cria atalho na área de trabalho
├── Instalar_JARVIS.bat                     # Duplo-clique aqui pra rodar o setup.ps1 (sem terminal)
├── launch_jarvis.bat                       # O que o atalho executa (liga servidor + abre app)
├── update.bat                                # Atualiza o código sem mexer no .env/memórias
├── icon.ico                                    # Ícone do atalho
├── static/                                # App web instalável (PWA), servido em /app
├── requirements.txt
├── .env.example
├── .gitignore
└── LICENSE                                  # MIT — outras pessoas podem usar livremente
```

## Ferramentas disponíveis

| Ferramenta | O que faz |
|---|---|
| `remember` / `recall` | Memória de longo prazo com busca semântica |
| `propose_command` | Comando de terminal genérico — precisa de aprovação |
| `open_app` | Abre um app/jogo pré-configurado (Steam, Discord, League...) — **executa na hora, sem aprovação** |
| `list_available_apps` | Lista o que já está configurado pra abrir por voz |
| `write_word_document` | Abre o Word e escreve um documento de verdade |
| `list_linear_teams` / `create_linear_issue` | Integração com Linear (opcional) |

## Abrindo jogos e programas por voz

O `open_app` é diferente do `propose_command`: em vez do modelo tentar
"adivinhar" o comando certo pra abrir um programa (e errar o caminho do
executável, que varia de PC pra PC), você mesmo mapeia nome → comando uma
vez em `apps_config.json`, e depois é só falar o nome — abre na hora, sem
pedir aprovação (abrir um programa é seguro e reversível, diferente de um
comando genérico de terminal).

### Configurando
Abra `apps_config.json` e ajuste os caminhos — principalmente os do Riot
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
Com o servidor principal já rodando (`uvicorn app:app ...` num terminal),
abra outro terminal:
```powershell
python wake_word_listener.py
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

## Ligando junto com o Windows

Se você já rodou o `setup.ps1` e respondeu "s" na pergunta sobre auto-start,
isso já está configurado — pode pular esta seção.

Se pulou na hora e quer ativar depois, ou prefere fazer manualmente:

### Via linha de comando (PowerShell como Administrador)
```powershell
schtasks /create /tn "JARVIS Server" /tr "C:\caminho\completo\jarvis-ia\start_server.bat" /sc onlogon
schtasks /create /tn "JARVIS Wake Word" /tr "C:\caminho\completo\jarvis-ia\start_wake_word.bat" /sc onlogon
```

### Ou pela interface gráfica
Abra o **Agendador de Tarefas** → **Criar Tarefa Básica** → gatilho "Ao
fazer logon" → ação "Iniciar um programa" → selecione `start_server.bat`
(repita para `start_wake_word.bat`).

Depois de configurado, reinicie o PC uma vez pra confirmar que sobe sozinho.

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
clonada, e rodar `ollama pull qwen3:8b`.

**Nota importante**: o `update.bat` só funciona se o projeto foi baixado
via `git clone` (não um `.zip` baixado manualmente) — é o `git pull` por
trás que permite atualizar sem perder configurações. Se você (ou alguém
que baixou) pegou via `.zip`, a recomendação é clonar via git desde o
início, exatamente pra ter esse caminho de atualização mais fácil.

## Limitações desta versão (comparado à versão que usava Claude)

- **Sem visão** — não analisa imagens (a maioria dos modelos locais leves
  não tem essa capacidade; dá pra trocar por um modelo com visão como
  `llama3.2-vision` depois, se quiser, mas é mais pesado).
- **Sem busca na web nativa** — esse recurso dependia de um tool exclusivo
  da Anthropic.
- **Ferramentas menos confiáveis** — o modelo local erra mais ao decidir
  quando chamar `remember`, `propose_command` etc, comparado ao Claude.
- **Precisa do PC ligado** — voltamos a essa realidade ao escolher "zero custo",
  é a mesma troca que discutimos antes de decidir essa arquitetura.

## Próximos passos possíveis
- Testar modelos maiores (`qwen3:14b`) se quiser mais qualidade e sua GPU aguentar.
- Adicionar um modelo com visão pra recuperar a análise de imagem.
- Trocar `espeak-ng` por Piper pra voz mais natural (ainda local).
- Se um dia quiser voltar a rodar 24/7 sem o PC ligado, a versão anterior
  (Claude + Render + Neon) continua sendo a arquitetura certa pra isso — as
  duas versões podem conviver, são só configurações diferentes do mesmo
  conceito de produto.
