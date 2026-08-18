@echo off
REM Sobe o listener "Hey JARVIS" manualmente, com janela visível (depuração).
REM Este arquivo fica em scripts/; wake_word_listener.py agora fica em src/.
timeout /t 8 /nobreak >nul
cd /d "%~dp0.."
call venv\Scripts\activate.bat 2>nul
python src\wake_word_listener.py
