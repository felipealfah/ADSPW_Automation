@echo off
REM Start do projeto ADSPW_Automation no Windows
setlocal enabledelayedexpansion

REM Navegar para o diretório da aplicação
pushd "%~dp0\automation_py"

echo Clearing caches and logs...
if exist "credentials\adspower_cache.json" del /q "credentials\adspower_cache.json"
REM Limpar arquivos de job e SMS pendentes
if exist "sms_data\jobs\*.json" del /q "sms_data\jobs\*.json"
if exist "sms_data\*.json" del /q "sms_data\*.json"
REM Limpar logs de execução
if exist "server.log" del /q "server.log"
if exist "logs\*.log" del /q "logs\*.log"

REM Remover pastas __pycache__ recursivamente
for /f "delims=" %%d in ('dir /b /s /ad __pycache__ 2^>nul') do (
    rmdir /s /q "%%d"
)

echo Starting project...
REM Ativar o ambiente virtual se existir
if exist ".venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call ".venv\Scripts\activate.bat"
)

REM Executar o script Python principal
python run.py

popd
endlocal 