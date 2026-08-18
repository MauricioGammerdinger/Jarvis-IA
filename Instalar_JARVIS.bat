@echo off
REM Duplo-clique aqui pra instalar tudo — nao precisa abrir PowerShell manualmente.
REM Isso so precisa ser rodado UMA VEZ. Depois, use o atalho "J.A.R.V.I.S."
REM que aparece na area de trabalho.

cd /d "%~dp0"
echo Iniciando instalacao do J.A.R.V.I.S....
echo (uma janela do PowerShell vai abrir - isso e esperado)
echo.

powershell -ExecutionPolicy Bypass -File "%~dp0setup.ps1"

echo.
echo Se tudo deu certo, tem um atalho "J.A.R.V.I.S." na sua area de trabalho agora.
pause
