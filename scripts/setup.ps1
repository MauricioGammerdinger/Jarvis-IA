# Instalador do J.A.R.V.I.S. — rode isso UMA VEZ.
# Depois disso, use sempre o atalho criado na área de trabalho.
# Pra atualizar o código no futuro, use update.bat (não rode este setup.ps1 de novo).

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$ProjectDir = Split-Path $ScriptDir -Parent  # este script está em scripts/, a raiz do projeto é um nível acima

Write-Host "=== Instalador do J.A.R.V.I.S. ===" -ForegroundColor Cyan
Write-Host "Pasta do projeto: $ProjectDir"

# Encontra um Python de verdade instalado — não confia cegamente no comando
# "python" existir, porque no Windows sem Python instalado esse comando abre
# um aviso da Microsoft Store em vez de dar erro claro. Testamos de verdade
# rodando "--version" e conferindo o código de saída.
function Find-SystemPython {
    foreach ($candidate in @("py", "python", "python3")) {
        try {
            & $candidate --version *>$null
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        } catch {
            continue
        }
    }
    return $null
}

$PythonCmd = Find-SystemPython
if (-not $PythonCmd) {
    Write-Host "`nERRO: Python não foi encontrado nesta máquina." -ForegroundColor Red
    Write-Host "   Instale em https://python.org/downloads — na primeira tela do" -ForegroundColor Red
    Write-Host "   instalador, MARQUE a caixa 'Add python.exe to PATH' antes de instalar." -ForegroundColor Red
    Write-Host "   Depois, rode este instalador de novo." -ForegroundColor Red
    Read-Host "`nPressione Enter pra fechar"
    exit 1
}
Write-Host "Python encontrado: $PythonCmd" -ForegroundColor Green

# O Ollama é quem roda o modelo de IA local — sem ele, o JARVIS instala mas
# não consegue conversar de verdade. Não dá pra instalar ele sozinho de
# forma 100% automática (o instalador oficial do Ollama não tem opção de
# instalação silenciosa/sem clique — isso é uma limitação deles, não nossa),
# então checamos e já facilitamos o máximo possível: abrimos a página de
# download pronta, sem você precisar procurar.
function Find-Ollama {
    try {
        & ollama --version *>$null
        if ($LASTEXITCODE -eq 0) { return $true }
    } catch {}
    return $false
}

if (-not (Find-Ollama)) {
    Write-Host "`nATENCAO: o Ollama nao foi encontrado nesta maquina." -ForegroundColor Yellow
    Write-Host "   Ele e o programa que roda a IA local -- sem ele, o JARVIS nao" -ForegroundColor Yellow
    Write-Host "   consegue responder nada, mesmo com o resto instalado certo." -ForegroundColor Yellow
    Write-Host "   Abrindo a pagina de download pra voce..." -ForegroundColor Yellow
    Start-Process "https://ollama.com/download"
    Write-Host "`n   Depois de instalar o Ollama, rode no terminal:" -ForegroundColor Yellow
    Write-Host "     ollama pull gemma4:e2b" -ForegroundColor Cyan
    Write-Host "   (Pode fazer isso agora ou depois -- este instalador continua," -ForegroundColor Yellow
    Write-Host "   mas o JARVIS só vai responder de verdade depois desse passo.)" -ForegroundColor Yellow
    Read-Host "`nPressione Enter pra continuar a instalação do JARVIS mesmo assim"
} else {
    Write-Host "Ollama encontrado." -ForegroundColor Green
}

# 1. Criar ambiente virtual Python (isolado, não mistura com outros projetos)
if (-not (Test-Path "$ProjectDir\venv")) {
    Write-Host "`n[1/5] Criando ambiente virtual Python..." -ForegroundColor Yellow
    & $PythonCmd -m venv "$ProjectDir\venv"
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path "$ProjectDir\venv\Scripts\python.exe")) {
        Write-Host "`nERRO: falha ao criar o ambiente virtual." -ForegroundColor Red
        Write-Host "   Confirme que o Python está instalado corretamente e tente de novo." -ForegroundColor Red
        Read-Host "`nPressione Enter pra fechar"
        exit 1
    }
} else {
    Write-Host "`n[1/5] Ambiente virtual já existe, pulando." -ForegroundColor Yellow
}

# 2. Instalar dependências
Write-Host "`n[2/5] Instalando dependências (pode demorar alguns minutos)..." -ForegroundColor Yellow
& "$ProjectDir\venv\Scripts\pip.exe" install -r "$ProjectDir\requirements.txt"
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nERRO: falha ao instalar dependências. Veja a mensagem acima." -ForegroundColor Red
    Read-Host "`nPressione Enter pra fechar"
    exit 1
}

# 3. Criar o .env se ainda não existir (nunca sobrescreve um .env já configurado)
if (-not (Test-Path "$ProjectDir\.env")) {
    Write-Host "`n[3/5] Configurando o .env automaticamente..." -ForegroundColor Yellow

    # Detecta a GPU pra recomendar o modelo certo sozinho -- evita o problema
    # comum de alguém baixar um modelo grande demais pra placa que tem.
    $RecommendedModel = "qwen3:4b"  # padrão seguro: roda em qualquer PC, mesmo sem GPU dedicada
    try {
        $vramOutput = & nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>$null
        if ($LASTEXITCODE -eq 0 -and $vramOutput) {
            $vramMB = [int]($vramOutput -replace '[^\d]', '')
            if ($vramMB -ge 8000) {
                $RecommendedModel = "gemma4:e2b"
                Write-Host "     -> GPU NVIDIA com $([math]::Round($vramMB/1024,1))GB de VRAM detectada." -ForegroundColor Green
            } else {
                Write-Host "     -> GPU NVIDIA detectada, mas com pouca VRAM ($([math]::Round($vramMB/1024,1))GB)." -ForegroundColor Yellow
            }
        } else {
            Write-Host "     -> Nenhuma GPU NVIDIA detectada (ou driver não instalado)." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "     -> Não foi possível detectar a GPU automaticamente." -ForegroundColor Yellow
    }
    Write-Host "     -> Modelo recomendado pra essa máquina: $RecommendedModel" -ForegroundColor Green

    $envContent = Get-Content "$ProjectDir\.env.example" -Raw
    $envContent = $envContent -replace 'JARVIS_MODEL=.*', "JARVIS_MODEL=$RecommendedModel"
    Set-Content -Path "$ProjectDir\.env" -Value $envContent -NoNewline

    Write-Host "     -> .env criado com modelo '$RecommendedModel'. Chave padrão: secreta123" -ForegroundColor Green
    Write-Host "     -> Isso é adequado só pra uso local/privado. Se um dia expuser o servidor" -ForegroundColor Gray
    Write-Host "        pra fora (Tailscale, etc), troque por uma chave forte no .env." -ForegroundColor Gray

    # Oferece baixar o modelo recomendado na hora, se o Ollama já estiver instalado
    if (Find-Ollama) {
        $baixarAgora = Read-Host "`nBaixar o modelo '$RecommendedModel' agora? Pode demorar alguns minutos (s/n)"
        if ($baixarAgora -eq "s") {
            Write-Host "Baixando $RecommendedModel — acompanhe o progresso abaixo..." -ForegroundColor Yellow
            & ollama pull $RecommendedModel
        } else {
            Write-Host "Pulado. Rode 'ollama pull $RecommendedModel' manualmente antes de usar o JARVIS." -ForegroundColor Gray
        }
    }
} else {
    Write-Host "`n[3/5] .env já existe, mantendo suas configurações atuais." -ForegroundColor Yellow
}

# 4. Criar o atalho na área de trabalho, com ícone
Write-Host "`n[4/5] Criando atalho na área de trabalho..." -ForegroundColor Yellow
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = "$DesktopPath\J.A.R.V.I.S..lnk"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "$ProjectDir\scripts\launch_jarvis.bat"
$Shortcut.WorkingDirectory = $ProjectDir
$Shortcut.IconLocation = "$ProjectDir\assets\icon.ico"
$Shortcut.Description = "Abre o J.A.R.V.I.S."
$Shortcut.Save()
Write-Host "     -> Atalho criado em: $ShortcutPath" -ForegroundColor Green

# 5. Perguntar sobre auto-start no boot
Write-Host "`n[5/5] Auto-iniciar com o Windows?" -ForegroundColor Yellow
$resposta = Read-Host "Quer que o JARVIS ligue sozinho quando o Windows iniciar (ícone na bandeja)? (s/n)"
if ($resposta -eq "s") {
    # Um atalho só, na pasta de Inicialização, apontando pro ícone de bandeja
    # (que por sua vez liga servidor + voz por trás, sem nenhuma janela visível).
    # Aparece no Gerenciador de Tarefas > Aplicativos de inicialização, com
    # ícone e nome, habilitável/desabilitável direto por lá.
    $StartupFolder = [Environment]::GetFolderPath("Startup")

    $ShortcutTray = $WshShell.CreateShortcut("$StartupFolder\J.A.R.V.I.S..lnk")
    $ShortcutTray.TargetPath = "$ProjectDir\scripts\start_tray.bat"
    $ShortcutTray.WorkingDirectory = $ProjectDir
    $ShortcutTray.IconLocation = "$ProjectDir\assets\icon.ico"
    $ShortcutTray.Description = "Liga o J.A.R.V.I.S. (ícone na bandeja do sistema)."
    $ShortcutTray.WindowStyle = 7  # minimizado (não que apareça janela, mas por segurança)
    $ShortcutTray.Save()

    Write-Host "     -> Adicionado à pasta de Inicialização do Windows." -ForegroundColor Green
    Write-Host "     -> Confira em: Gerenciador de Tarefas > Aplicativos de inicialização" -ForegroundColor Green
    Write-Host "        (procure por 'J.A.R.V.I.S.')" -ForegroundColor Green
} else {
    Write-Host "     -> Pulado. Use o atalho da área de trabalho manualmente quando quiser." -ForegroundColor Gray
}

Write-Host "`n=== Instalação concluída! ===" -ForegroundColor Cyan
Write-Host "1. Abra o .env e confirme suas chaves (JARVIS_API_KEY, etc)."
Write-Host "2. Instale o Ollama e rode: ollama pull qwen3:8b"
Write-Host "3. Use o atalho '$ShortcutPath' pra abrir o JARVIS."
