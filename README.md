# Adspower_RPA: Sistema de Automação RPA

Este sistema integra automações RPA (Robotic Process Automation) para o AdsPower com uma API de webhooks personalizados, permitindo a execução de automações via chamadas HTTP.

## Requisitos

- AdsPower instalado no sistema host
- Python 3.8+
- Conexão com a internet

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
