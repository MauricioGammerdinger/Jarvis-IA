@echo off
REM Duplo-clique aqui pra desinstalar o JARVIS (atalho + inicializacao automatica).
REM Vai perguntar se voce quer apagar tambem suas memorias/configuracoes.

cd /d "%~dp0"
echo Iniciando desinstalacao do J.A.R.V.I.S....
echo.

powershell -ExecutionPolicy Bypass -File "%~dp0scripts\uninstall.ps1"

pause
