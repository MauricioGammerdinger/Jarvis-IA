@echo off
REM Sobe o servidor JARVIS manualmente, com janela visível (útil pra depuração).
REM Este arquivo fica em scripts/, mas venv/ e app.py ficam na raiz do projeto.
cd /d "%~dp0.."
call venv\Scripts\activate.bat 2>nul
uvicorn app:app --host 0.0.0.0 --port 8000
