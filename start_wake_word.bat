@echo off
REM Sobe o listener "Hey JARVIS". Usado pelo Agendador de Tarefas pra iniciar sozinho no boot.
REM Espera alguns segundos pro servidor principal subir primeiro.
timeout /t 8 /nobreak >nul
cd /d "%~dp0"
call venv\Scripts\activate.bat 2>nul
python wake_word_listener.py
