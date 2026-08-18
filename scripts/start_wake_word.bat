@echo off
REM Sobe o listener "Hey JARVIS" manualmente, com janela visível (depuração).
REM Este arquivo fica em scripts/, mas venv/ e wake_word_listener.py ficam na raiz.
timeout /t 8 /nobreak >nul
cd /d "%~dp0.."
call venv\Scripts\activate.bat 2>nul
python wake_word_listener.py
