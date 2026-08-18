@echo off
REM Atualiza o código do JARVIS SEM apagar suas configurações (.env) nem
REM suas memórias (jarvis.db) — os dois ficam de fora do controle de versão
REM (.gitignore), então "git pull" nunca toca neles.

cd /d "%~dp0"

echo === Atualizando o J.A.R.V.I.S. ===
echo.

if not exist ".git" (
    echo ERRO: esta pasta nao parece ter sido baixada via "git clone".
    echo Se voce baixou um .zip manualmente, precisa repetir esse processo:
    echo   1. Baixe a nova versao
    echo   2. Copie os arquivos NOVOS por cima dos antigos
    echo   3. NAO sobrescreva .env nem jarvis.db
    pause
    exit /b 1
)

echo [1/2] Puxando as atualizacoes do GitHub...
git pull

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Deu erro no "git pull" - provavelmente voce tem alteracoes locais
    echo que conflitam. Se nao editou nada manualmente, rode:
    echo   git stash ^&^& git pull ^&^& git stash pop
    pause
    exit /b 1
)

echo.
echo [2/2] Reinstalando dependencias (caso tenha alguma nova)...
call venv\Scripts\activate.bat 2>nul
pip install -r requirements.txt --quiet --upgrade

echo.
echo === Atualizado! Suas configuracoes e memorias continuam intactas. ===
echo Use o atalho da area de trabalho normalmente.
pause
