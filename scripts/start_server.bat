@echo off
REM Sobe o servidor JARVIS manualmente, com janela visível (útil pra depuração).
REM Este arquivo fica em scripts/; app.py agora fica em src/; venv/ fica na raiz.
cd /d "%~dp0.."
call venv\Scripts\activate.bat 2>nul
uvicorn app:app --app-dir src --host 0.0.0.0 --port 8000
