#!/bin/bash

set -e

echo "================================================"
echo "    Configuracao do ambiente Adspower_RPA"
echo "================================================"
echo ""

# Verificar se o Docker está instalado
if ! command -v docker &> /dev/null; then
    echo "❌ Docker não está instalado. Por favor, instale o Docker primeiro."
    echo "📚 Visite https://docs.docker.com/get-docker/ para instruções de instalação."
    exit 1
fi

# Verificar se o Docker Compose está instalado
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose não está instalado. Por favor, instale o Docker Compose primeiro."
    echo "📚 Visite https://docs.docker.com/compose/install/ para instruções de instalação."
    exit 1
fi

echo "✅ Docker e Docker Compose estão instalados."

# Detectar o sistema operacional
OS="$(uname)"
echo "🖥️ Sistema operacional detectado: $OS"

# Verificar e configurar o AdsPower
echo "🔍 Verificando instalação do AdsPower..."

# Caminhos possíveis de instalação do AdsPower
ADSPOWER_PATHS=()

if [ "$OS" = "Darwin" ]; then
    # MacOS
    ADSPOWER_PATHS=(
        "$HOME/Library/Application Support/AdsPower"
        "/Applications/AdsPower.app"
    )
elif [ "$OS" = "Linux" ]; then
    # Linux
    ADSPOWER_PATHS=(
        "$HOME/.config/AdsPower"
        "$HOME/.AdsPower"
        "/opt/AdsPower"
    )
fi

ADSPOWER_FOUND=false
ADSPOWER_PATH=""

for path in "${ADSPOWER_PATHS[@]}"; do
    if [ -d "$path" ]; then
        echo "✅ AdsPower encontrado em: $path"
        ADSPOWER_FOUND=true
        ADSPOWER_PATH="$path"
        break
    fi
done

if [ "$ADSPOWER_FOUND" = false ]; then
    echo "⚠️ AdsPower não foi encontrado nos locais padrão."
    echo "⚠️ Certifique-se de que o AdsPower está instalado e configurado corretamente."
else
    echo "🔧 Tentando configurar o AdsPower automaticamente..."
    
    # Possíveis localizações do arquivo de configuração
    CONFIG_FILES=(
        "$ADSPOWER_PATH/config.json"
        "$HOME/Library/Application Support/AdsPower/config.json"
        "$HOME/.config/AdsPower/config.json"
    )
    
    CONFIG_FOUND=false
    CONFIG_PATH=""
    
    for config in "${CONFIG_FILES[@]}"; do
        if [ -f "$config" ]; then
            echo "✅ Arquivo de configuração encontrado: $config"
            CONFIG_FOUND=true
            CONFIG_PATH="$config"
            break
        fi
    done
    
    if [ "$CONFIG_FOUND" = true ]; then
        echo "📋 Criando backup do arquivo de configuração..."
        cp "$CONFIG_PATH" "${CONFIG_PATH}.backup_$(date +%Y%m%d%H%M%S)"
        
        echo "🔧 Modificando configurações do AdsPower..."
        
        # Verificar se já existe configuração API
        if grep -q "serverIp" "$CONFIG_PATH"; then
            # Substituir a configuração existente
            if [ "$OS" = "Darwin" ]; then
                # MacOS usa sed -i '' para editar arquivos in-place
                sed -i '' 's/"serverIp": ".*"/"serverIp": "0.0.0.0"/g' "$CONFIG_PATH"
                sed -i '' 's/"enableApi": false/"enableApi": true/g' "$CONFIG_PATH"
            else
                # Linux e outros sistemas
                sed -i 's/"serverIp": ".*"/"serverIp": "0.0.0.0"/g' "$CONFIG_PATH"
                sed -i 's/"enableApi": false/"enableApi": true/g' "$CONFIG_PATH"
            fi
        else
            # Adicionar nova configuração se não existir
            if [ "$OS" = "Darwin" ]; then
                # MacOS
                perl -i -pe 's/\{/\{\n  "serverIp": "0.0.0.0",\n  "enableApi": true,/g' "$CONFIG_PATH"
            else
                # Linux e outros
                perl -i -pe 's/\{/\{\n  "serverIp": "0.0.0.0",\n  "enableApi": true,/g' "$CONFIG_PATH"
            fi
        fi
        
        echo "✅ Configuração do AdsPower atualizada com sucesso!"
        echo "⚠️ Você precisa reiniciar o AdsPower para que as alterações tenham efeito."
    else
        echo "⚠️ Arquivo de configuração não encontrado."
        echo "⚠️ Você precisará configurar o AdsPower manualmente."
    fi
fi

# Instruções para configuração manual
echo ""
echo "📝 INSTRUÇÕES PARA CONFIGURAÇÃO MANUAL DO ADSPOWER:"
echo "1. Abra o AdsPower"
echo "2. Clique no ícone de engrenagem (⚙️) no canto superior direito"
echo "3. Vá para a guia 'API'"
echo "4. Marque a opção 'Enable API'"
echo "5. Configure o 'Server IP' para '0.0.0.0'"
echo "6. Mantenha a porta como '50325'"
echo "7. Clique em 'Save' e reinicie o AdsPower"
echo ""

# Testar conexão com AdsPower
echo "🔄 Testando conexão com AdsPower..."
if curl -s http://localhost:50325/status > /dev/null; then
    echo "✅ Conexão com AdsPower estabelecida com sucesso!"
else
    echo "⚠️ Não foi possível conectar ao AdsPower."
    echo "⚠️ Certifique-se de que o AdsPower está em execução e configurado corretamente."
    echo "⚠️ API deve estar habilitada e configurada para responder em 0.0.0.0:50325"
fi

echo ""
echo "================================================"
echo "    Configurando ambiente"
echo "================================================"
echo ""

# Criar arquivo .env para configuração
cat > .env << EOL
# Configuracao do ambiente Adspower_RPA
# Gerado automaticamente por setup.sh

# Endereco da API do AdsPower
ADSPOWER_API_URL=http://host.docker.internal:50325

# Enderecos alternativos (descomente se necessario)
# ADSPOWER_API_URL=http://127.0.0.1:50325
# ADSPOWER_API_URL=http://localhost:50325
EOL

echo " Arquivo .env criado com sucesso"

# Testando conexão com o AdsPower
echo ""
echo "================================================"
echo "    Testando conexao com o AdsPower"
echo "================================================"
echo ""

echo "Tentando conectar ao AdsPower em diferentes endereços..."
echo ""

if command -v curl &> /dev/null; then
    # Teste com local.adspower.net
    echo "1. Testando http://local.adspower.net:50325/status..."
    response=$(curl -s -o /dev/null -w "%{http_code}" http://local.adspower.net:50325/status -m 5 2>/dev/null)
    if [ "$response" == "200" ]; then
        echo " Conexao com local.adspower.net bem-sucedida!"
    else
        echo " Falha na conexão ou resposta inesperada: $response"
    fi
    
    # Teste com localhost
    echo "2. Testando http://localhost:50325/status..."
    response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:50325/status -m 5 2>/dev/null)
    if [ "$response" == "200" ]; then
        echo " Conexao com localhost bem-sucedida!"
    else
        echo " Falha na conexão ou resposta inesperada: $response"
    fi
    
    # Teste com 127.0.0.1
    echo "3. Testando http://127.0.0.1:50325/status..."
    response=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:50325/status -m 5 2>/dev/null)
    if [ "$response" == "200" ]; then
        echo " Conexao com 127.0.0.1 bem-sucedida!"
    else
        echo " Falha na conexão ou resposta inesperada: $response"
    fi
else
    echo "X curl não encontrado. Não foi possível testar a conexão com o AdsPower."
    echo "  Por favor, verifique manualmente se o AdsPower está configurado corretamente."
fi

echo ""
echo "Se todos os testes falharem, verifique se:"
echo "  1. O AdsPower esta em execucao"
echo "  2. A API esta ativada e configurada no endereco 0.0.0.0:50325"
echo "  3. Nao ha firewalls bloqueando a conexao"
echo "  4. Tente renomear a pasta CWD do AdsPower se continuar tendo problemas"
echo "  5. Desative temporariamente software de seguranca ou proxies"

echo ""
echo "================================================"
echo "    Iniciando os containers Docker"
echo "================================================"
echo ""

# Criar pastas necessárias
mkdir -p shared_data

# Iniciar os contêineres Docker
echo "🐳 Iniciando containers Docker..."
docker-compose up -d

if [ $? -eq 0 ]; then
    echo ""
    echo " Aplicacao iniciada com sucesso!"
    echo ""
    echo "🌐 ACESSO AOS SERVIÇOS:"
    echo "- Interface Web: http://localhost:8501"
    echo "- Webhook API: http://localhost:8000"
    echo ""
    echo "✨ Configuração concluída! ✨"
else
    echo ""
    echo "X Ocorreu um erro ao iniciar os containers Docker."
    echo "   Execute 'docker-compose logs' para ver os detalhes do erro."
fi

echo ""
echo "================================================"
echo "    Configuracao concluida"
echo "================================================"
echo ""
echo "NOTA: Se tiver problemas de conexao com a API do AdsPower, tente:"
echo "  1. Editar o arquivo .env e descomentar um dos enderecos alternativos"
echo "  2. Reiniciar os containers com: docker-compose restart"
echo "  3. Verificar se o AdsPower esta executando com a API habilitada"
echo "  4. Desativar temporariamente firewalls e software antivirus"
echo ""

# Execute este comando na raiz do projeto, não dentro de automation_py/
sudo docker buildx create --use && docker buildx build --platform linux/amd64,linux/arm64 -t felipealfah/pwads_automation:1.0 -t felipealfah/pwads_automation:latest . --push