@echo off
setlocal enabledelayedexpansion

echo ================================================
echo    Configuracao do ambiente Adspower_RPA
echo ================================================
echo.

:: Verificar se o Docker está instalado
docker --version > nul 2>&1
if %errorlevel% neq 0 (
    echo X Docker nao encontrado. Por favor, instale o Docker Desktop primeiro:
    echo    https://docs.docker.com/desktop/install/windows-install/
    pause
    exit /b 1
)

:: Verificar se o Docker Compose está instalado
docker-compose --version > nul 2>&1
if %errorlevel% neq 0 (
    echo X Docker Compose nao encontrado. Certifique-se de que o Docker Desktop esta instalado com o Compose.
    pause
    exit /b 1
)

echo  Sistema detectado: Windows
echo.

:: Verificar se o AdsPower está instalado
set "ADSPOWER_PATH="
if exist "C:\Program Files (x86)\AdsPower\AdsPower.exe" (
    set "ADSPOWER_PATH=C:\Program Files (x86)\AdsPower"
    echo  AdsPower encontrado em C:\Program Files (x86)\AdsPower\AdsPower.exe
) else if exist "C:\Program Files\AdsPower\AdsPower.exe" (
    set "ADSPOWER_PATH=C:\Program Files\AdsPower"
    echo  AdsPower encontrado em C:\Program Files\AdsPower\AdsPower.exe
) else (
    echo  AdsPower nao parece estar instalado no local padrao.
    echo    Por favor, certifique-se de que o AdsPower esta instalado no seu sistema.
)

echo.
echo ================================================
echo    Configurando o AdsPower
echo ================================================
echo.

:: Tentar configurar o AdsPower automaticamente
set "CONFIG_FOUND=0"
set "CONFIG_UPDATED=0"
set "CONFIG_FILES_TO_CHECK=%APPDATA%\AdsPower\config.json %APPDATA%\AdsPower\user_preferences.json %LOCALAPPDATA%\AdsPower\config.json %USERPROFILE%\.adspower\config.json"

:: Verificar pasta CWD do AdsPower (possível solução para problemas de API)
if exist "%APPDATA%\AdsPower\cwd" (
    echo  Pasta CWD do AdsPower encontrada em %APPDATA%\AdsPower\cwd
    echo  NOTA: Se tiver problemas com a API, pode ser necessário renomear esta pasta.
)

echo Tentando configurar o AdsPower automaticamente...

for %%f in (%CONFIG_FILES_TO_CHECK%) do (
    if exist "%%f" (
        echo  Arquivo de configuracao encontrado: %%f
        set "CONFIG_FOUND=1"
        
        :: Criar backup do arquivo
        copy "%%f" "%%f.backup" > nul
        if !errorlevel! equ 0 (
            echo  Backup criado em %%f.backup
            
            :: Tentar modificar o arquivo para habilitar API com endereço 0.0.0.0
            powershell -Command "(Get-Content '%%f') -replace '\"server_ip\": \"[^\"]*\"', '\"server_ip\": \"0.0.0.0\"' | Set-Content '%%f'"
            powershell -Command "(Get-Content '%%f') -replace '\"api_enabled\": false', '\"api_enabled\": true' | Set-Content '%%f'"
            
            echo  Tentativa de atualização da configuração concluída.
            echo  IMPORTANTE: Você ainda precisará reiniciar o AdsPower para aplicar as alterações.
            set "CONFIG_UPDATED=1"
        ) else (
            echo X Não foi possível criar backup de %%f. Configuração manual será necessária.
        )
    )
)

if %CONFIG_FOUND% equ 0 (
    echo X Arquivo de configuração do AdsPower não encontrado. Configuração manual será necessária.
)

echo.
echo Instruções para configuração manual do AdsPower:
echo 1. Abra o aplicativo AdsPower
echo 2. Vá para 'Configurações' ^> 'API'
echo 3. Certifique-se de que a porta está definida como 50325
echo 4. Ative a opção 'Habilitar API'
echo 5. Configure o endereço para: 0.0.0.0 (para permitir acesso de Docker)
echo 6. Salve as configurações e reinicie o AdsPower
echo.

set /p adspower_ready="O AdsPower está configurado corretamente? (s/n): "
if /i not "%adspower_ready%" == "s" (
    echo  Por favor, configure o AdsPower antes de continuar.
    echo    Execute este script novamente após configurar o AdsPower.
    pause
    exit /b 1
)

echo.
echo ================================================
echo    Configurando ambiente
echo ================================================
echo.

:: Criar arquivo .env para configuração
echo # Configuracao do ambiente Adspower_RPA > .env
echo # Gerado automaticamente por setup.bat >> .env
echo. >> .env
echo # Endereco da API do AdsPower >> .env
echo ADSPOWER_API_URL=http://host.docker.internal:50325 >> .env
echo # Enderecos alternativos (descomente se necessario) >> .env
echo # ADSPOWER_API_URL=http://127.0.0.1:50325 >> .env
echo # ADSPOWER_API_URL=http://localhost:50325 >> .env

echo  Arquivo .env criado com sucesso

:: Testando conexão com o AdsPower
echo.
echo ================================================
echo    Testando conexao com o AdsPower
echo ================================================
echo.

echo Tentando conectar ao AdsPower em diferentes endereços...
echo.

:: Teste com local.adspower.net
echo 1. Testando http://local.adspower.net:50325/status...
powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://local.adspower.net:50325/status' -TimeoutSec 5 -UseBasicParsing; if ($response.StatusCode -eq 200) { Write-Host '  Conexao com AdsPower bem-sucedida!' } else { Write-Host '  Resposta inesperada:' $response.StatusCode } } catch { Write-Host '  Falha na conexao' }"

:: Teste com localhost
echo 2. Testando http://localhost:50325/status...
powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://localhost:50325/status' -TimeoutSec 5 -UseBasicParsing; if ($response.StatusCode -eq 200) { Write-Host '  Conexao com AdsPower bem-sucedida!' } else { Write-Host '  Resposta inesperada:' $response.StatusCode } } catch { Write-Host '  Falha na conexao' }"

:: Teste com 127.0.0.1
echo 3. Testando http://127.0.0.1:50325/status...
powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://127.0.0.1:50325/status' -TimeoutSec 5 -UseBasicParsing; if ($response.StatusCode -eq 200) { Write-Host '  Conexao com AdsPower bem-sucedida!' } else { Write-Host '  Resposta inesperada:' $response.StatusCode } } catch { Write-Host '  Falha na conexao' }"

echo.
echo Se todos os testes falharem, verifique se:
echo  1. O AdsPower esta em execucao
echo  2. A API esta ativada e configurada no endereco 0.0.0.0:50325
echo  3. Nao ha firewalls bloqueando a conexao
echo  4. Tente renomear a pasta %%APPDATA%%\AdsPower\cwd se continuar tendo problemas
echo  5. Desative temporariamente software de seguranca ou proxies

echo.
echo ================================================
echo    Iniciando os containers Docker
echo ================================================
echo.

:: Criar pastas necessárias
if not exist "shared_data" mkdir shared_data

:: Iniciar os contêineres Docker
echo Iniciando containers Docker...
docker-compose up -d

if %errorlevel% equ 0 (
    echo.
    echo  Aplicacao iniciada com sucesso!
    echo.
    echo Acesse os servicos em:
    echo - Streamlit UI: http://localhost:8501
    echo - Webhook API: http://localhost:5001
    echo.
    echo Para verificar os logs, execute:
    echo docker-compose logs -f
) else (
    echo.
    echo X Ocorreu um erro ao iniciar os containers Docker.
    echo    Execute 'docker-compose logs' para ver os detalhes do erro.
)

echo.
echo ================================================
echo    Configuracao concluida
echo ================================================
echo.
echo NOTA: Se tiver problemas de conexao com a API do AdsPower, tente:
echo  1. Editar o arquivo .env e descomentar um dos enderecos alternativos
echo  2. Reiniciar os containers com: docker-compose restart
echo  3. Verificar se o AdsPower esta executando com a API habilitada
echo  4. Desativar temporariamente firewalls e software antivirus
echo.

pause