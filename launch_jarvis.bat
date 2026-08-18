@echo off
REM Este é o arquivo que o atalho da área de trabalho aponta.
REM Verifica se o servidor já está rodando; se não estiver, liga; depois abre o navegador.

cd /d "%~dp0"

echo Verificando se o JARVIS ja esta rodando...
powershell -Command "try { $r = Invoke-WebRequest -Uri http://localhost:8000/health -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }"

if %ERRORLEVEL% EQU 0 (
    echo JARVIS ja esta rodando, so abrindo o navegador...
) else (
    echo Ligando o JARVIS pela primeira vez...
    start "JARVIS Server" /min cmd /c "call venv\Scripts\activate.bat 2>nul & uvicorn app:app --host 0.0.0.0 --port 8000"
    echo Aguardando o servidor iniciar...
    timeout /t 5 /nobreak >nul
)

start http://localhost:8000/app
