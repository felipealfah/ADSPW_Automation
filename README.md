# Adspower_RPA: Sistema de Automação RPA

Este sistema integra automações RPA (Robotic Process Automation) para o AdsPower com uma API de webhooks personalizados, permitindo a execução de automações via chamadas HTTP.

## Requisitos

- AdsPower instalado no sistema host
- Python 3.8+
- Conexão com a internet
- Conta no Cloudflare (para acesso externo à API)

## Requisitos Mínimos de Hardware

Para executar o sistema completo, recomendamos:

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

1. Certifique-se de que o AdsPower está instalado e configurado
2. Instale o Python 3.8 ou superior
3. Clone este repositório
4. Execute o script de setup para configurar o ambiente

## Documentação da API (Swagger)

O sistema inclui documentação completa da API utilizando Swagger UI. Esta interface permite explorar todos os endpoints disponíveis, entender os parâmetros necessários e testar as chamadas diretamente pelo navegador.

### Como acessar a documentação

1. Inicie o serviço de API webhooks
2. Acesse a documentação em: `http://localhost:5001/api/docs`
3. Se estiver utilizando o Cloudflare Tunnel, a documentação estará disponível em: `https://api.seudominio.com/api/docs`

### Recursos disponíveis na documentação

- Descrição detalhada de todos os endpoints
- Parâmetros de requisição e respostas esperadas
- Interface para testes em tempo real
- Exemplos de requisições e respostas
- Modelos de dados utilizados na API

A documentação é gerada automaticamente a partir das definições do código, garantindo que esteja sempre atualizada conforme a implementação atual da API.

## Acesso Externo via Cloudflare Tunnel

Para disponibilizar o sistema para acesso externo, utilizamos o Cloudflare Zero Trust para criar um túnel seguro. Este método oferece várias vantagens:

- Não é necessário abrir portas no firewall
- Comunicação criptografada
- Autenticação e controle de acesso
- Proteção contra ataques DDoS

### Configuração do Cloudflare Tunnel

1. **Pré-requisitos:**
   - Domínio registrado e configurado no Cloudflare
   - Conta Cloudflare com Zero Trust habilitado

2. **Passos para configuração:**

   a. **Criar um túnel no Cloudflare Zero Trust:**
   - Acesse o painel Cloudflare Zero Trust (https://dash.teams.cloudflare.com)
   - Navegue até Access > Tunnels
   - Clique em "Create Tunnel" e siga as instruções para instalar o connector no servidor

   b. **Configurar o domínio para apontar para o serviço:**
   - No painel do túnel, adicione uma rota pública
   - Configure seu subdomínio (ex: api.seudominio.com)
   - Aponte para o serviço local (ex: localhost:5001)
   - Salve as configurações

   c. **Verificar a configuração:**
   - Execute o connector do Cloudflare (cloudflared)
   - Verifique se o túnel está ativo no painel do Cloudflare
   - Teste o acesso através do domínio configurado

3. **Usando o serviço:**
   - A API estará disponível em: `https://api.seudominio.com`
   - Utilize este endereço para todos os webhooks e chamadas de API
   - Todos os endpoints descritos na documentação da API estarão disponíveis através deste domínio

### Segurança Adicional (Opcional)

Para aumentar a segurança, você pode configurar políticas de acesso no Cloudflare Zero Trust:

- Restrinja o acesso por endereço IP
- Exija autenticação para acessar a API
- Configure regras baseadas em identidade para diferentes níveis de acesso

### Benefícios da Arquitetura

Esta arquitetura com Cloudflare Tunnel proporciona:

- **Escalabilidade:** O serviço pode ser acessado de qualquer lugar, facilitando integrações com ferramentas externas
- **Segurança:** Tráfego criptografado e proteção contra ataques
- **Monitoramento:** Logs de acesso e análise de tráfego no painel do Cloudflare
- **Simplicidade:** Não é necessário configurar portas, encaminhamento ou certificados SSL manualmente

### Troubleshooting

Se encontrar problemas com o túnel:

1. Verifique se o serviço do cloudflared está em execução
2. Confirme que o túnel aparece como "Connected" no painel do Cloudflare
3. Verifique os logs do cloudflared para possíveis erros
4. Confirme que o serviço local (webhook API) está em execução e acessível no endereço e porta configurados
