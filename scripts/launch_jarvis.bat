@echo off
REM Este é o arquivo que o atalho da área de trabalho aponta.
REM Verifica se o servidor já está rodando; se não estiver, liga via bandeja
REM do sistema (sem nenhuma janela visível); depois abre o navegador.

cd /d "%~dp0"

echo Verificando se o JARVIS ja esta rodando...
powershell -Command "try { $r = Invoke-WebRequest -Uri http://localhost:8000/health -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }"

if %ERRORLEVEL% EQU 0 (
    echo JARVIS ja esta rodando, so abrindo o navegador...
) else (
    echo Ligando o JARVIS pela primeira vez...
    call start_tray.bat
    echo Aguardando o servidor iniciar...
    timeout /t 6 /nobreak >nul
)

start http://localhost:8000/app
