# Instalador do J.A.R.V.I.S. — rode isso UMA VEZ.
# Depois disso, use sempre o atalho criado na área de trabalho.
# Pra atualizar o código no futuro, use update.bat (não rode este setup.ps1 de novo).

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot

Write-Host "=== Instalador do J.A.R.V.I.S. ===" -ForegroundColor Cyan
Write-Host "Pasta do projeto: $ProjectDir"

# 1. Criar ambiente virtual Python (isolado, não mistura com outros projetos)
if (-not (Test-Path "$ProjectDir\venv")) {
    Write-Host "`n[1/5] Criando ambiente virtual Python..." -ForegroundColor Yellow
    python -m venv "$ProjectDir\venv"
} else {
    Write-Host "`n[1/5] Ambiente virtual já existe, pulando." -ForegroundColor Yellow
}

# 2. Instalar dependências
Write-Host "`n[2/5] Instalando dependências (pode demorar alguns minutos)..." -ForegroundColor Yellow
& "$ProjectDir\venv\Scripts\pip.exe" install -r "$ProjectDir\requirements.txt"

# 3. Criar o .env se ainda não existir (nunca sobrescreve um .env já configurado)
if (-not (Test-Path "$ProjectDir\.env")) {
    Write-Host "`n[3/5] Criando .env a partir do modelo..." -ForegroundColor Yellow
    Copy-Item "$ProjectDir\.env.example" "$ProjectDir\.env"
    Write-Host "     -> Abra o .env e preencha JARVIS_API_KEY antes de usar!" -ForegroundColor Red
} else {
    Write-Host "`n[3/5] .env já existe, mantendo suas configurações atuais." -ForegroundColor Yellow
}

# 4. Criar o atalho na área de trabalho, com ícone
Write-Host "`n[4/5] Criando atalho na área de trabalho..." -ForegroundColor Yellow
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = "$DesktopPath\J.A.R.V.I.S..lnk"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "$ProjectDir\launch_jarvis.bat"
$Shortcut.WorkingDirectory = $ProjectDir
$Shortcut.IconLocation = "$ProjectDir\icon.ico"
$Shortcut.Description = "Abre o J.A.R.V.I.S."
$Shortcut.Save()
Write-Host "     -> Atalho criado em: $ShortcutPath" -ForegroundColor Green

# 5. Perguntar sobre auto-start no boot
Write-Host "`n[5/5] Auto-iniciar com o Windows?" -ForegroundColor Yellow
$resposta = Read-Host "Quer que o JARVIS (servidor + wake word) ligue sozinho quando o Windows iniciar? (s/n)"
if ($resposta -eq "s") {
    schtasks /create /tn "JARVIS Server" /tr "$ProjectDir\start_server.bat" /sc onlogon /f
    schtasks /create /tn "JARVIS Wake Word" /tr "$ProjectDir\start_wake_word.bat" /sc onlogon /f
    Write-Host "     -> Registrado no Agendador de Tarefas." -ForegroundColor Green
} else {
    Write-Host "     -> Pulado. Use o atalho da área de trabalho manualmente quando quiser." -ForegroundColor Gray
}

Write-Host "`n=== Instalação concluída! ===" -ForegroundColor Cyan
Write-Host "1. Abra o .env e confirme suas chaves (JARVIS_API_KEY, etc)."
Write-Host "2. Instale o Ollama e rode: ollama pull qwen3:8b"
Write-Host "3. Use o atalho '$ShortcutPath' pra abrir o JARVIS."
