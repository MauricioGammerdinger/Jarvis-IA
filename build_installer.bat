@echo off
REM Compila o installer.py num .exe de verdade, com o icone do JARVIS embutido.
REM Rode isso UMA VEZ no seu PC (precisa do Python instalado). Depois disso,
REM o arquivo "Instalar_JARVIS.exe" gerado pode ser copiado/distribuido
REM (junto com o resto da pasta do projeto) e aberto com duplo-clique,
REM sem precisar de Python instalado em quem for so usar o .exe final.

cd /d "%~dp0"

echo === Preparando para compilar o instalador (.exe) ===
echo.

echo [1/3] Instalando PyInstaller e pywin32 (necessarios so para compilar)...
pip install pyinstaller pywin32 --quiet

echo.
echo [2/3] Compilando scripts\installer.py em Instalar_JARVIS.exe...
pyinstaller --onefile --console --icon=assets\icon.ico --name=Instalar_JARVIS scripts\installer.py --distpath . --workpath build_temp --specpath build_temp

echo.
echo [3/3] Limpando arquivos temporarios de build...
rmdir /s /q build_temp 2>nul

echo.
echo === Pronto! ===
echo O arquivo Instalar_JARVIS.exe foi criado nesta pasta, com o icone do JARVIS.
echo A partir de agora, use ele (duplo-clique) em vez do Instalar_JARVIS.bat.
pause
