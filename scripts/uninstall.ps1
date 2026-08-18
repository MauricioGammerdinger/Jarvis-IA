# Desinstalador do J.A.R.V.I.S. — desfaz o que o setup.ps1 fez.
# NÃO apaga a pasta do projeto nem seus dados por padrão — você escolhe.

$ErrorActionPreference = "SilentlyContinue"  # não trava se algo já não existir (ex: tarefa não registrada)
$ScriptDir = $PSScriptRoot
$ProjectDir = Split-Path $ScriptDir -Parent  # este script está em scripts/, a raiz do projeto é um nível acima

Write-Host "=== Desinstalador do J.A.R.V.I.S. ===" -ForegroundColor Cyan

# 1. Fechar processos do JARVIS que estejam rodando (servidor, voz, bandeja)
Write-Host "`n[1/5] Encerrando processos do JARVIS, se estiverem rodando..." -ForegroundColor Yellow
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*tray_app.py*" -or
    $_.CommandLine -like "*wake_word_listener.py*" -or
    ($_.CommandLine -like "*uvicorn*" -and $_.CommandLine -like "*app:app*")
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
Write-Host "     -> Feito (ou não havia nada rodando)." -ForegroundColor Green

# 2. Remover a inicialização automática (pasta de Inicialização do Windows)
Write-Host "`n[2/5] Removendo inicialização automática com o Windows..." -ForegroundColor Yellow
$StartupFolder = [Environment]::GetFolderPath("Startup")
# Formato atual (ícone de bandeja, um atalho só)
Remove-Item "$StartupFolder\J.A.R.V.I.S..lnk" -Force -ErrorAction SilentlyContinue
# Formatos de versões anteriores deste projeto, caso esteja atualizando de uma instalação antiga
Remove-Item "$StartupFolder\J.A.R.V.I.S. Servidor.lnk" -Force -ErrorAction SilentlyContinue
Remove-Item "$StartupFolder\J.A.R.V.I.S. Voz (Hey Jarvis).lnk" -Force -ErrorAction SilentlyContinue
schtasks /delete /tn "JARVIS Server" /f 2>$null | Out-Null
schtasks /delete /tn "JARVIS Wake Word" /f 2>$null | Out-Null
Write-Host "     -> Feito (ou não estava configurado)." -ForegroundColor Green

# 3. Remover o atalho da área de trabalho
Write-Host "`n[3/5] Removendo atalho da área de trabalho..." -ForegroundColor Yellow
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = "$DesktopPath\J.A.R.V.I.S..lnk"
if (Test-Path $ShortcutPath) {
    Remove-Item $ShortcutPath -Force
    Write-Host "     -> Atalho removido." -ForegroundColor Green
} else {
    Write-Host "     -> Não havia atalho pra remover." -ForegroundColor Gray
}

# 4. Perguntar sobre apagar dados pessoais (memórias e configurações)
Write-Host "`n[4/5] Suas memórias e configurações" -ForegroundColor Yellow
$apagarDados = Read-Host "Apagar TAMBÉM suas memórias (jarvis.db) e configurações (.env)? Isso não pode ser desfeito. (s/n)"
if ($apagarDados -eq "s") {
    Remove-Item "$ProjectDir\jarvis.db" -Force -ErrorAction SilentlyContinue
    Remove-Item "$ProjectDir\.env" -Force -ErrorAction SilentlyContinue
    Write-Host "     -> Memórias e configurações apagadas." -ForegroundColor Green
} else {
    Write-Host "     -> Mantidos. Se reinstalar depois, suas memórias continuam lá." -ForegroundColor Gray
}

# 5. Perguntar sobre remover o ambiente virtual Python (libera espaço em disco)
Write-Host "`n[5/5] Ambiente virtual Python (venv)" -ForegroundColor Yellow
$apagarVenv = Read-Host "Remover o ambiente virtual (libera espaço, ~1-2GB)? Ele é recriado sozinho se você reinstalar. (s/n)"
if ($apagarVenv -eq "s") {
    Remove-Item "$ProjectDir\venv" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "     -> Ambiente virtual removido." -ForegroundColor Green
} else {
    Write-Host "     -> Mantido." -ForegroundColor Gray
}

Write-Host "`n=== Desinstalação concluída ===" -ForegroundColor Cyan
Write-Host "O atalho e a inicialização automática foram removidos."
Write-Host "Pra remover o JARVIS por completo, feche esta janela e apague"
Write-Host "manualmente a pasta do projeto:"
Write-Host "  $ProjectDir" -ForegroundColor Yellow
Write-Host "(Não consegui apagar essa pasta sozinho porque este script está"
Write-Host "rodando de dentro dela — apagar a própria pasta em execução"
Write-Host "pode causar erro.)"
