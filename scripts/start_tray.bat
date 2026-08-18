@echo off
REM Sobe o icone de bandeja do JARVIS, sem nenhuma janela de console.
REM Usa "pythonw.exe" (com w) de proposito -- ele roda Python sem abrir
REM janela de terminal, diferente do "python.exe" normal.
REM Este arquivo fica em scripts/; tray_app.py agora fica em src/; venv/ fica na raiz.

cd /d "%~dp0.."

if exist "venv\Scripts\pythonw.exe" (
    start "" "venv\Scripts\pythonw.exe" src\tray_app.py
) else (
    start "" pythonw src\tray_app.py
)
