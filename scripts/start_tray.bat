@echo off
REM Sobe o icone de bandeja do JARVIS, sem nenhuma janela de console.
REM Usa "pythonw.exe" (com w) de proposito -- ele roda Python sem abrir
REM janela de terminal, diferente do "python.exe" normal.
REM Este arquivo fica em scripts/, mas venv/ e tray_app.py ficam na raiz
REM do projeto -- por isso o "cd .." antes de tudo.

cd /d "%~dp0.."

if exist "venv\Scripts\pythonw.exe" (
    start "" "venv\Scripts\pythonw.exe" tray_app.py
) else (
    start "" pythonw tray_app.py
)
