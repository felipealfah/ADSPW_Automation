@echo off
setlocal enabledelayedexpansion

echo ================================================
echo     Configuracao do ambiente Adspower_RPA
echo ================================================
echo.

REM Verificar se o Docker está instalado
docker --version > nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo X Docker nao esta instalado. Por favor, instale o Docker Desktop primeiro.
    echo   Visite https://docs.docker.com/desktop/install/windows-install/
    pause
    exit /b 1
)

REM Verificar se o Docker Compose está instalado
docker-compose --version > nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    docker compose version > nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo X Docker Compose nao esta instalado. Por favor, instale o Docker Desktop com Docker Compose.
        echo   Visite https://docs.docker.com/desktop/install/windows-install/
        pause
        exit /b 1
    )
)

echo V Docker e Docker Compose estao instalados.

REM Verificar e configurar o AdsPower
echo.
echo Verificando instalacao do AdsPower...

REM Possíveis locais de instalação do AdsPower
set "ADSPOWER_FOUND=0"
set "ADSPOWER_PATH="

REM Verificar AdsPower normal
if exist "%APPDATA%\AdsPower" (
    echo V AdsPower encontrado em: %APPDATA%\AdsPower
    set "ADSPOWER_FOUND=1"
    set "ADSPOWER_PATH=%APPDATA%\AdsPower"
    goto :adspower_found
)

if exist "%LOCALAPPDATA%\AdsPower" (
    echo V AdsPower encontrado em: %LOCALAPPDATA%\AdsPower
    set "ADSPOWER_FOUND=1"
    set "ADSPOWER_PATH=%LOCALAPPDATA%\AdsPower"
    goto :adspower_found
)

REM Verificar AdsPower Global
if exist "%APPDATA%\adspower_global" (
    echo V AdsPower Global encontrado em: %APPDATA%\adspower_global
    set "ADSPOWER_FOUND=1"
    set "ADSPOWER_PATH=%APPDATA%\adspower_global"
    goto :adspower_found
)

if exist "%LOCALAPPDATA%\adspower_global" (
    echo V AdsPower Global encontrado em: %LOCALAPPDATA%\adspower_global
    set "ADSPOWER_FOUND=1"
    set "ADSPOWER_PATH=%LOCALAPPDATA%\adspower_global"
    goto :adspower_found
)

if exist "%APPDATA%\AdsPower Global" (
    echo V AdsPower Global encontrado em: %APPDATA%\AdsPower Global
    set "ADSPOWER_FOUND=1"
    set "ADSPOWER_PATH=%APPDATA%\AdsPower Global"
    goto :adspower_found
)

if exist "%LOCALAPPDATA%\AdsPower Global" (
    echo V AdsPower Global encontrado em: %LOCALAPPDATA%\AdsPower Global
    set "ADSPOWER_FOUND=1"
    set "ADSPOWER_PATH=%LOCALAPPDATA%\AdsPower Global"
    goto :adspower_found
)

REM Verificar instalação no Program Files
if exist "C:\Program Files\AdsPower" (
    echo V AdsPower encontrado em: C:\Program Files\AdsPower
    set "ADSPOWER_FOUND=1"
    set "ADSPOWER_PATH=C:\Program Files\AdsPower"
    goto :adspower_found
)

if exist "C:\Program Files\AdsPower Global" (
    echo V AdsPower Global encontrado em: C:\Program Files\AdsPower Global
    set "ADSPOWER_FOUND=1"
    set "ADSPOWER_PATH=C:\Program Files\AdsPower Global"
    goto :adspower_found
)

if exist "C:\Program Files (x86)\AdsPower" (
    echo V AdsPower encontrado em: C:\Program Files (x86)\AdsPower
    set "ADSPOWER_FOUND=1"
    set "ADSPOWER_PATH=C:\Program Files (x86)\AdsPower"
    goto :adspower_found
)

if exist "C:\Program Files (x86)\AdsPower Global" (
    echo V AdsPower Global encontrado em: C:\Program Files (x86)\AdsPower Global
    set "ADSPOWER_FOUND=1"
    set "ADSPOWER_PATH=C:\Program Files (x86)\AdsPower Global"
    goto :adspower_found
)

echo ! AdsPower nao foi encontrado nos locais padrao.
echo ! Certifique-se de que o AdsPower esta instalado.
goto :config_manual

:adspower_found
echo Tentando configurar o AdsPower automaticamente...

REM Verificar arquivo de configuração
set "CONFIG_FOUND=0"
set "CONFIG_PATH="

REM Possíveis locais do arquivo de configuração
set "CONFIG_PATHS=%ADSPOWER_PATH%\config.json %APPDATA%\AdsPower\config.json %APPDATA%\adspower_global\config.json %APPDATA%\AdsPower Global\config.json %LOCALAPPDATA%\AdsPower\config.json %LOCALAPPDATA%\adspower_global\config.json %LOCALAPPDATA%\AdsPower Global\config.json %APPDATA%\Roaming\adspower_global\cwd_global\source\local_api"

for %%C in (%CONFIG_PATHS%) do (
    if exist "%%C" (
        echo V Arquivo de configuracao encontrado: %%C
        set "CONFIG_FOUND=1"
        set "CONFIG_PATH=%%C"
        goto :config_found
    )
)

echo ! Arquivo de configuracao nao encontrado.
echo ! Voce precisara configurar o AdsPower manualmente.
goto :local_api_check

:config_found
echo Criando backup do arquivo de configuracao...
for /f "tokens=2-4 delims=/ " %%a in ('date /t') do (
    set "date=%%c%%a%%b"
)
for /f "tokens=1-2 delims=: " %%a in ('time /t') do (
    set "time=%%a%%b"
)
copy "%CONFIG_PATH%" "%CONFIG_PATH%.backup_%date%%time%" > nul

echo Modificando configuracoes do AdsPower...
powershell -Command "(Get-Content '%CONFIG_PATH%') -replace '\"serverIp\": \".*\"', '\"serverIp\": \"0.0.0.0\"' -replace '\"enableApi\": false', '\"enableApi\": true' | Set-Content '%CONFIG_PATH%'"

echo V Configuracao do AdsPower atualizada com sucesso!
echo ! Voce precisa reiniciar o AdsPower para que as alteracoes tenham efeito.

:local_api_check
echo.
echo Procurando pelo arquivo local_api...

set "LOCAL_API_FOUND=0"
set "LOCAL_API_PATH="

REM Procurar local_api no AdsPower normal
if not "%ADSPOWER_PATH%"=="" (
    if exist "%ADSPOWER_PATH%\cwd\source\local_api" (
        echo V Arquivo local_api encontrado: %ADSPOWER_PATH%\cwd\source\local_api
        set "LOCAL_API_FOUND=1"
        set "LOCAL_API_PATH=%ADSPOWER_PATH%\cwd\source\local_api"
        goto :local_api_found
    )
    
    REM AdsPower Global
    if exist "%ADSPOWER_PATH%\cwd_global\source\local_api" (
        echo V Arquivo local_api encontrado: %ADSPOWER_PATH%\cwd_global\source\local_api
        set "LOCAL_API_FOUND=1"
        set "LOCAL_API_PATH=%ADSPOWER_PATH%\cwd_global\source\local_api"
        goto :local_api_found
    )
)

REM Procurar em locais alternativos
set "ALT_PATHS=%APPDATA%\AdsPower\cwd\source\local_api %APPDATA%\adspower_global\cwd_global\source\local_api %APPDATA%\AdsPower Global\cwd_global\source\local_api %LOCALAPPDATA%\AdsPower\cwd\source\local_api %LOCALAPPDATA%\adspower_global\cwd_global\source\local_api %LOCALAPPDATA%\AdsPower Global\cwd_global\source\local_api"

for %%P in (%ALT_PATHS%) do (
    if exist "%%P" (
        echo V Arquivo local_api encontrado: %%P
        set "LOCAL_API_FOUND=1"
        set "LOCAL_API_PATH=%%P"
        goto :local_api_found
    )
)

echo ! Arquivo local_api nao encontrado automaticamente.
echo ! Voce precisara localizar e modificar manualmente o arquivo 'local_api'.
echo   Conteudo para colocar no arquivo: http://0.0.0.0:50325/
goto :config_manual

:local_api_found
echo Criando backup do arquivo local_api...
for /f "tokens=2-4 delims=/ " %%a in ('date /t') do (
    set "date=%%c%%a%%b"
)
for /f "tokens=1-2 delims=: " %%a in ('time /t') do (
    set "time=%%a%%b"
)
copy "%LOCAL_API_PATH%" "%LOCAL_API_PATH%.backup_%date%%time%" > nul

echo Atualizando endereco da API para 0.0.0.0:50325...
echo http://0.0.0.0:50325/ > "%LOCAL_API_PATH%"

echo V Arquivo local_api atualizado com sucesso!
echo ! Lembre-se de reiniciar o AdsPower para que as alteracoes tenham efeito.

:config_manual
echo.
echo INSTRUCOES PARA CONFIGURACAO MANUAL DO ADSPOWER:
echo 1. Abra o AdsPower
echo 2. Clique no icone de engrenagem no canto superior direito
echo 3. Va para a guia 'API'
echo 4. Marque a opcao 'Enable API'
echo 5. Configure o 'Server IP' para '0.0.0.0'
echo 6. Mantenha a porta como '50325'
echo 7. Clique em 'Save' e reinicie o AdsPower
echo.
echo INSTRUCOES PARA MODIFICAR MANUALMENTE O ARQUIVO local_api:
echo 1. Localize o arquivo 'local_api' na instalacao do AdsPower
echo    (normalmente em uma pasta como cwd\source\ ou cwd_global\source\)
echo 2. Edite o arquivo e substitua todo o conteudo por: http://0.0.0.0:50325/
echo 3. Salve o arquivo e reinicie o AdsPower
echo.

REM Testar conexão com AdsPower
echo Testando conexao com AdsPower...
powershell -Command "try { Invoke-RestMethod -Uri 'http://localhost:50325/status' -Method Get -TimeoutSec 5; Write-Host 'V Conexao com AdsPower estabelecida com sucesso!' } catch { Write-Host '! Nao foi possivel conectar ao AdsPower.'; Write-Host '! Certifique-se de que o AdsPower esta em execucao e configurado corretamente.'; Write-Host '! API deve estar habilitada e configurada para responder em 0.0.0.0:50325' }"

echo.
echo ================================================
echo     Configurando ambiente
echo ================================================
echo.

REM Criar arquivo .env para configuração
echo # Configuracao do ambiente Adspower_RPA> .env
echo # Gerado automaticamente por setup.bat>> .env
echo.>> .env
echo # Endereco da API do AdsPower>> .env
echo ADSPOWER_API_URL=http://host.docker.internal:50325>> .env
echo.>> .env
echo # Enderecos alternativos (descomente se necessario)>> .env
echo # ADSPOWER_API_URL=http://127.0.0.1:50325>> .env
echo # ADSPOWER_API_URL=http://localhost:50325>> .env

echo Arquivo .env criado com sucesso

REM Testando conexão com o AdsPower
echo.
echo ================================================
echo     Testando conexao com o AdsPower
echo ================================================
echo.

echo Tentando conectar ao AdsPower em diferentes enderecos...
echo.

REM Verificar se o PowerShell está disponível
powershell -Command "exit" > nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo X PowerShell nao encontrado. Nao foi possivel testar a conexao com o AdsPower.
    echo   Por favor, verifique manualmente se o AdsPower esta configurado corretamente.
    goto :skip_tests
)

REM Teste com local.adspower.net
echo 1. Testando http://local.adspower.net:50325/status...
powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://local.adspower.net:50325/status' -Method Get -TimeoutSec 5 -ErrorAction Stop; Write-Host (' Conexao com local.adspower.net bem-sucedida!'); (Get-Content '.env') -replace '^ADSPOWER_API_URL=.*', 'ADSPOWER_API_URL=http://local.adspower.net:50325' | Set-Content '.env' } catch { Write-Host (' Falha na conexao ou resposta inesperada: ' + $_.Exception.Message) }"

REM Teste com localhost
echo 2. Testando http://localhost:50325/status...
powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://localhost:50325/status' -Method Get -TimeoutSec 5 -ErrorAction Stop; Write-Host (' Conexao com localhost bem-sucedida!'); if (-not ((Get-Content '.env') -match '^ADSPOWER_API_URL=http://local.adspower.net:50325')) { (Get-Content '.env') -replace '^ADSPOWER_API_URL=.*', 'ADSPOWER_API_URL=http://localhost:50325' | Set-Content '.env' } } catch { Write-Host (' Falha na conexao ou resposta inesperada: ' + $_.Exception.Message) }"

REM Teste com 127.0.0.1
echo 3. Testando http://127.0.0.1:50325/status...
powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://127.0.0.1:50325/status' -Method Get -TimeoutSec 5 -ErrorAction Stop; Write-Host (' Conexao com 127.0.0.1 bem-sucedida!'); if (-not ((Get-Content '.env') -match '^ADSPOWER_API_URL=http://local.adspower.net:50325') -and -not ((Get-Content '.env') -match '^ADSPOWER_API_URL=http://localhost:50325')) { (Get-Content '.env') -replace '^ADSPOWER_API_URL=.*', 'ADSPOWER_API_URL=http://127.0.0.1:50325' | Set-Content '.env' } } catch { Write-Host (' Falha na conexao ou resposta inesperada: ' + $_.Exception.Message) }"

REM Verificar se algum endereço funcionou
powershell -Command "$success = $false; try { Invoke-WebRequest -Uri 'http://local.adspower.net:50325/status' -Method Get -TimeoutSec 2 -ErrorAction Stop; $success = $true } catch {} try { if (-not $success) { Invoke-WebRequest -Uri 'http://localhost:50325/status' -Method Get -TimeoutSec 2 -ErrorAction Stop; $success = $true } } catch {} try { if (-not $success) { Invoke-WebRequest -Uri 'http://127.0.0.1:50325/status' -Method Get -TimeoutSec 2 -ErrorAction Stop; $success = $true } } catch {} if (-not $success) { Write-Host ''; Write-Host '! ATENCAO: Nenhuma conexao com o AdsPower foi bem-sucedida!'; Write-Host '! Verifique se o AdsPower esta em execucao e configurado corretamente.' } else { Write-Host ''; Write-Host 'V Pelo menos uma conexao com o AdsPower foi bem-sucedida!'; Write-Host 'V O arquivo .env foi atualizado para usar o endereco que funcionou.' }"

:skip_tests
echo.
echo Se todos os testes falharem, verifique se:
echo   1. O AdsPower esta em execucao
echo   2. A API esta ativada e configurada no endereco 0.0.0.0:50325
echo   3. Nao ha firewalls bloqueando a conexao
echo   4. Tente renomear a pasta CWD do AdsPower se continuar tendo problemas
echo   5. Desative temporariamente software de seguranca ou proxies

echo.
echo ================================================
echo     Iniciando os containers Docker
echo ================================================
echo.

REM Criar pastas necessárias
if not exist "shared_data" mkdir shared_data

REM Iniciar os contêineres Docker
echo Iniciando containers Docker...
docker-compose up -d

if %ERRORLEVEL% EQU 0 (
    echo.
    echo Aplicacao iniciada com sucesso!
    echo.
    echo ACESSO AOS SERVICOS:
    echo - Interface Web: http://localhost:8501
    echo - Webhook API: http://localhost:8000
    echo.
    echo Configuracao concluida!
) else (
    echo.
    echo X Ocorreu um erro ao iniciar os containers Docker.
    echo   Execute 'docker-compose logs' para ver os detalhes do erro.
)

echo.
echo ================================================
echo     Configuracao concluida
echo ================================================
echo.
echo NOTA: Se tiver problemas de conexao com a API do AdsPower, tente:
echo   1. Editar o arquivo .env e descomentar um dos enderecos alternativos
echo   2. Reiniciar os containers com: docker-compose restart
echo   3. Verificar se o AdsPower esta executando com a API habilitada
echo   4. Desativar temporariamente firewalls e software antivirus
echo.

pause
pause