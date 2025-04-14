# Adspower_RPA: Sistema de Automação RPA

Este sistema integra automações RPA (Robotic Process Automation) para o AdsPower com uma API de webhooks personalizados, permitindo a execução de automações via chamadas HTTP.

## Requisitos

- Docker e Docker Compose
- AdsPower instalado no sistema host
- Conexão com a internet

## Requisitos Mínimos de Hardware

Para executar o sistema completo (AdsPower + Docker com RPA), recomendamos:

### Requisitos Mínimos
- **CPU:** 4 cores (Intel i5/AMD Ryzen 5 ou superior)
- **Memória RAM:** 8GB (mínimo absoluto)
- **Armazenamento:** 20GB de espaço livre
- **Conexão de Internet:** 10 Mbps ou superior

### Requisitos Recomendados
- **CPU:** 8 cores (Intel i7/AMD Ryzen 7 ou superior)
- **Memória RAM:** 16GB
- **Armazenamento:** 50GB de espaço livre em SSD
- **Conexão de Internet:** 25 Mbps ou superior

### Requisitos por Número de Perfis AdsPower
| Número de Perfis **Simultâneos** | RAM Recomendada | CPU Recomendado |
|------------------|-----------------|-----------------|
| 1-5              | 8GB             | 4 cores         |
| 6-10             | 16GB            | 8 cores         |
| 11-20            | 32GB            | 8+ cores        |
| 20+              | 64GB+           | 12+ cores       |

**Observação importante:** 
- A tabela acima refere-se a perfis executados **simultaneamente**. 
- Se você planeja executar os perfis **sequencialmente** (um de cada vez), os requisitos são significativamente menores:
  - **Execução Sequencial (um por vez):** 
    - CPU: 2 cores (mínimo)
    - RAM: 4GB (mínimo)
    - Armazenamento: 20GB
  - Neste caso, o sistema consegue reutilizar os recursos entre as execuções.

O AdsPower executa instâncias Chrome separadas para cada perfil, e cada instância consome aproximadamente 300-500MB de RAM em estado ocioso, podendo chegar a 1GB+ durante automações intensivas. Ajuste os requisitos de hardware de acordo com sua estratégia de execução.

## Instalação Rápida

### Windows

1. **Instale o Docker Desktop**
   - Baixe e instale do [site oficial](https://www.docker.com/products/docker-desktop/)
   - Siga as instruções de instalação e reinicie o computador se necessário

2. **Instale o AdsPower**
   - Baixe e instale do [site oficial](https://www.adspower.net/)
   - Complete a instalação e inicie o aplicativo

3. **Execute o script de instalação**
   - Clique com o botão direito em `setup.bat` e selecione "Executar como administrador"
   - O script tentará automaticamente:
     - Verificar se o AdsPower está instalado
     - Encontrar e modificar o arquivo de configuração do AdsPower para usar o endereço `0.0.0.0:50325`
     - Habilitar a API do AdsPower
   - Caso a configuração automática falhe, o script fornecerá instruções para configuração manual
   - Siga as instruções na tela para concluir a instalação

4. **Configuração manual do AdsPower (se necessário)**
   - Se a configuração automática falhar, siga as instruções manuais:
   - Abra o AdsPower
   - Vá para "Configurações" > "API"
   - Certifique-se de que a opção "Habilitar API" está ativada
   - Altere o endereço para: `0.0.0.0`
   - Mantenha a porta como `50325`
   - Clique em "Salvar" ou "Apply"
   - Reinicie o AdsPower para aplicar as alterações

### macOS

1. **Instale o Docker Desktop**
   - Baixe e instale do [site oficial](https://www.docker.com/products/docker-desktop/)
   - Arraste o aplicativo para a pasta Aplicações

2. **Instale o AdsPower**
   - Baixe e instale do [site oficial](https://www.adspower.net/)
   - Arraste o aplicativo para a pasta Aplicações

3. **Execute o script de instalação**
   - Abra o Terminal
   - Navegue até a pasta do projeto: `cd caminho/para/Adspower_RPA`
   - Torne o script executável: `chmod +x setup.sh`
   - Execute o script: `./setup.sh`
   - O script tentará automaticamente:
     - Verificar se o AdsPower está instalado
     - Encontrar e modificar o arquivo de configuração do AdsPower para usar o endereço `0.0.0.0:50325`
     - Habilitar a API do AdsPower
   - Caso a configuração automática falhe, o script fornecerá instruções para configuração manual
   - Siga as instruções na tela para concluir a instalação

4. **Configuração manual do AdsPower (se necessário)**
   - Se a configuração automática falhar, siga as instruções manuais:
   - Abra o AdsPower
   - Vá para "Configurações" > "API"
   - Certifique-se de que a opção "Habilitar API" está ativada
   - Altere o endereço para: `0.0.0.0`
   - Mantenha a porta como `50325`
   - Clique em "Salvar" ou "Apply"
   - Reinicie o AdsPower para aplicar as alterações

### Linux

1. **Instale o Docker e Docker Compose**
   ```bash
   # Instalar Docker
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   
   # Adicionar usuário ao grupo docker
   sudo usermod -aG docker $USER
   
   # Instalar Docker Compose
   sudo apt-get update
   sudo apt-get install docker-compose-plugin
   ```

2. **Instale o AdsPower**
   - O AdsPower não tem uma versão nativa para Linux
   - Opção 1: Instale usando Wine
     ```bash
     sudo apt-get install wine
     # Baixe o instalador do AdsPower para Windows e execute com Wine
     wine AdsPower_setup.exe
     ```
   - Opção 2: Use uma máquina virtual Windows
     - Instale VirtualBox ou VMware
     - Configure uma VM Windows
     - Instale o AdsPower na VM
     - Configure redirecionamento de porta para 50325

3. **Execute o script de instalação**
   - Abra o Terminal
   - Navegue até a pasta do projeto: `cd caminho/para/Adspower_RPA`
   - Torne o script executável: `chmod +x setup.sh`
   - Execute o script: `./setup.sh`
   - O script tentará automaticamente:
     - Verificar onde o AdsPower está instalado via Wine (se aplicável)
     - Encontrar e modificar o arquivo de configuração do AdsPower para usar o endereço `0.0.0.0:50325`
     - Habilitar a API do AdsPower
   - Caso a configuração automática falhe, o script fornecerá instruções para configuração manual
   - Siga as instruções na tela para concluir a instalação

4. **Configuração manual do AdsPower (se necessário)**
   - Se a configuração automática falhar, siga as instruções manuais:
   - Abra o AdsPower (via Wine ou VM)
   - Vá para "Configurações" > "API"
   - Certifique-se de que a opção "Habilitar API" está ativada
   - Altere o endereço para: `0.0.0.0`
   - Mantenha a porta como `50325`
   - Clique em "Salvar" ou "Apply"
   - Reinicie o AdsPower para aplicar as alterações

## Configuração do Ambiente

1. Clone este repositório:
```bash
git clone <url-do-repositorio>
cd Adspower_RPA
```

2. Ajuste as variáveis no arquivo `.env` se necessário:
```
ADSPOWER_HOST=host.docker.internal  # Para Windows/Mac
# ADSPOWER_HOST=192.168.1.x  # Para Linux, use o IP real da sua máquina
ADSPOWER_PORT=50325
```

## Executando com Docker Compose

### Método 1: Usando a imagem pré-construída do Docker Hub

```bash
docker-compose up
```

### Método 2: Construindo a imagem localmente

```bash
docker-compose up --build
```

## Verificando a Instalação

Após a conclusão da instalação, você poderá acessar:

- **Streamlit UI**: http://localhost:8501
  - Interface de usuário para interagir com as automações

- **Webhook API**: http://localhost:5001
  - API para integração com serviços externos

## Uso Básico

### Utilizando a API de Webhooks

Você pode executar automações chamando os endpoints da API webhook:

1. Envie uma solicitação HTTP POST para o endpoint desejado:
   ```bash
   curl -X POST http://localhost:5001/api/endpoint -H "Content-Type: application/json" -d '{"param1": "value1"}'
   ```

2. A automação será executada e o resultado retornado como resposta HTTP

### Interface Streamlit

A interface Streamlit oferece uma maneira fácil de interagir com as automações:

1. Acesse http://localhost:8501 no navegador
2. Use os controles da interface para configurar e executar automações
3. Visualize os resultados e logs diretamente na interface

### Gerenciando Perfis no AdsPower

Os perfis do AdsPower são gerenciados diretamente na interface do AdsPower:

1. Abra o AdsPower em seu sistema
2. Crie novos perfis conforme necessário
3. Os perfis podem ser acessados pela aplicação RPA via API

## Construindo sua própria imagem

### Construção Básica

Se quiser construir e publicar sua própria versão da imagem:

```bash
# Construir a imagem (na mesma arquitetura do host)
docker build -t seu-usuario/nome-da-imagem:tag .

# Publicar a imagem no Docker Hub
docker push seu-usuario/nome-da-imagem:tag
```

### Construção Multiplataforma

A imagem Docker agora suporta tanto arquiteturas x86_64 (AMD64) quanto ARM64 (Apple Silicon M1/M2/M3). O Dockerfile detecta automaticamente a arquitetura e instala o navegador apropriado:

- Para AMD64 (Intel/AMD): Google Chrome + ChromeDriver
- Para ARM64 (Apple Silicon): Chromium + ChromeDriver (já que o Google Chrome não está disponível para ARM)

#### Construção Manual para Cada Arquitetura

Para construir manualmente para diferentes arquiteturas:

```bash
# Para ARM64 (nativa no Mac M1/M2/M3)
docker build -t seu-usuario/nome-da-imagem:arm64 .

# Para AMD64 (nativa em PCs Intel/AMD, emulação em Mac M1/M2/M3)
docker build --platform linux/amd64 -t seu-usuario/nome-da-imagem:amd64 .
```

#### Construção com BuildX para Múltiplas Arquiteturas Simultaneamente

Para construir para múltiplas arquiteturas de uma só vez e enviar para o Docker Hub:

```bash
# Configurar o buildx para construções multiplataforma
docker buildx create --use

# Construir a imagem para múltiplas plataformas e enviar para o Docker Hub
docker buildx build --platform linux/amd64,linux/arm64 -t seu-usuario/nome-da-imagem:latest -t seu-usuario/nome-da-imagem:1.0 . --push
```

Em seguida, atualize o arquivo `docker-compose.yml` para usar sua imagem:

```yaml
services:
  automation-rpa:
    image: seu-usuario/nome-da-imagem:latest
    volumes:
      - ./automation_py:/app
    # resto da configuração...
```

#### Execução em Diferentes Sistemas Operacionais

A aplicação foi projetada para funcionar em todas as plataformas seguintes:

**Windows:**
- Docker Desktop para Windows deve estar instalado e em execução
- WSL2 (Windows Subsystem for Linux) é recomendado
- Certifique-se de que o AdsPower está configurado para escutar em 0.0.0.0:50325

**macOS (Intel):**
- Docker Desktop para Mac deve estar instalado e em execução
- A imagem AMD64 será usada automaticamente
- Certifique-se de que o AdsPower está configurado para escutar em 0.0.0.0:50325

**macOS (Apple Silicon M1/M2/M3):**
- Docker Desktop para Mac (versão Apple Silicon) deve estar instalado
- A imagem ARM64 será usada automaticamente
- Se precisar executar a versão AMD64, pode usar a emulação com `--platform linux/amd64`
- Certifique-se de que o AdsPower está configurado para escutar em 0.0.0.0:50325

**Linux:**
- Docker e Docker Compose devem estar instalados
- Use a imagem correspondente à arquitetura do seu sistema (geralmente AMD64)
- Para o AdsPower, você precisará usar Wine ou uma VM Windows

#### Notas sobre Compatibilidade

- A versão ARM64 usa Chromium em vez de Google Chrome
- Ambas as versões são compatíveis com as automações do AdsPower
- Na maioria dos casos, não há diferença funcional entre as duas versões

## Estrutura do Projeto

```
Adspower_RPA/
├── docker-compose.yml      # Configuração dos containers Docker
├── setup.sh                # Script de instalação para Linux/macOS
├── setup.bat               # Script de instalação para Windows
├── .env                    # Configurações de ambiente (gerado automaticamente)
├── automation_py/          # Código-fonte da aplicação RPA
│   ├── Dockerfile          # Configuração para construir a imagem Docker
│   ├── requirements.txt    # Dependências Python
│   ├── run.py              # Ponto de entrada da aplicação
│   ├── docker-entrypoint.sh # Script de inicialização do container
│   ├── apis/               # Implementações de APIs
│   ├── automations/        # Scripts de automação
│   ├── ui/                 # Interface Streamlit
│   └── webhooks/           # Endpoints webhook
└── README.md               # Este arquivo
```

## Solução de Problemas

### Docker não inicia

- Verifique se o Docker Desktop está em execução
- No Windows/macOS, verifique se o Docker Desktop está inicializado corretamente
- No Linux, verifique se o serviço Docker está ativo: `sudo systemctl status docker`

### AdsPower não é detectado

1. Verifique se o AdsPower está em execução
2. Verifique se a API está habilitada nas configurações
3. Verifique se o endereço da API está configurado como `0.0.0.0`
4. Verifique se a porta `50325` está livre e não bloqueada por firewall

### Configuração automática do AdsPower falhou

1. Reinicie o AdsPower e tente executar o script de instalação novamente
2. Verifique se o seu usuário tem permissões para modificar os arquivos de configuração
3. Se o problema persistir, siga as instruções de configuração manual
4. Locais comuns de arquivos de configuração do AdsPower:
   - Windows: `%APPDATA%\AdsPower\config.json` ou `%LOCALAPPDATA%\AdsPower\config.json`
   - macOS: `~/Library/Application Support/AdsPower/config.json`
   - Linux (Wine): `~/.wine/drive_c/users/[seu_usuario]/AppData/Roaming/AdsPower/config.json`

### Erro de conexão entre containers

- Verifique os logs: `docker-compose logs`
- Verifique se a rede Docker foi criada corretamente: `docker network ls`
- Reinicie os containers: `docker-compose restart`

### Problemas com automações

1. Verifique os logs da aplicação: `docker-compose logs automation-rpa`
2. Verifique se o ChromeDriver está na versão correta
3. Teste a conexão com o AdsPower manualmente:
   ```bash
   curl http://localhost:50325/status
   ```

### Problemas de conexão com o AdsPower

Se você encontrar problemas de conexão com o AdsPower:

1. Verifique se o AdsPower está em execução e configurado corretamente
2. Tente modificar o ADSPOWER_HOST no arquivo .env para:
   - `127.0.0.1` (localhost)
   - O endereço IP real da sua máquina
3. Verifique se as portas 50325, 5001 e 8501 não estão bloqueadas pelo firewall

## Backups e Manutenção

### Backup dos Dados

- Perfis AdsPower: Use o recurso de exportação do AdsPower
- Volumes Docker: Faça backup da pasta `shared_data`

### Atualização do Sistema

1. Pare os containers: `docker-compose down`
2. Atualize o repositório: `git pull`
3. Reconstrua as imagens: `docker-compose build`
4. Inicie os containers: `docker-compose up -d`

## Informações Adicionais

### Portas Utilizadas

- 8501: Streamlit UI
- 5001: Webhook e API RPA
- 50325: API do AdsPower (no host)

### Compatibilidade

- Windows 10/11
- macOS 11 (Big Sur) ou superior
- Ubuntu 20.04 LTS ou superior (com ajustes adicionais para AdsPower)

### Recursos e Limitações

- O sistema requer que o AdsPower esteja em execução no sistema host
- As automações são executadas em containers Docker isolados
- A comunicação com o AdsPower é feita via API HTTP
- Os recursos de hardware necessários dependem do número de perfis do AdsPower em uso

## Suporte e Contribuição

Para relatar problemas ou contribuir com o projeto:

1. Abra uma issue no repositório
2. Descreva detalhadamente o problema ou a melhoria
3. Para contribuições, envie um pull request com suas alterações

---

Este projeto fornece uma infraestrutura containerizada para automações RPA utilizando AdsPower, que pode ser facilmente implantada em diferentes sistemas operacionais e integrada com outros sistemas através da API de webhooks. 

build:
  context: ./automation_py
  dockerfile: dockerfile 
  volumes:
    - ./automation_py:/app 