@echo off
REM Sobe o servidor JARVIS. Usado pelo Agendador de Tarefas pra iniciar sozinho no boot.
cd /d "%~dp0"
call venv\Scripts\activate.bat 2>nul
uvicorn app:app --host 0.0.0.0 --port 8000
