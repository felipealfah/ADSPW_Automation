# Gmail Account Creator - AdsPower Automation

Este projeto é uma automação para criar contas do Gmail utilizando o AdsPower Browser.

## Requisitos

- Python 3.8+
- AdsPower Browser instalado e configurado
- Conta ativa no AdsPower
- Serviço de SMS para verificação (opcional, dependendo da configuração)
- Para acesso a api do sms (https://sms-activate.guru/en/api2)

## Instalação
Crie um Ambiente Virtual no python

```bash
python -m venv nome_do_ambiente
```
ou 
```bash
python3 -m venv nome_do_ambiente

```
Ativar o Ambiente Virtual:

Para sistemas baseados em Windows, ative o ambiente virtual com:
```bash
.\nome_do_ambiente\Scripts\activate
```

Para sistemas baseados em Unix ou MacOS, use:
```bash
source nome_do_ambiente/bin/activate
```
Após ativar o ambiente virtual, você verá o nome do ambiente virtual geralmente entre parênteses no início da linha de comando, indicando que qualquer pacote Python que você instalar usando pip será colocado neste ambiente isolado, separado da instalação global do Python.

1. Clone o repositório:
```bash
git clone https://github.com/seu-usuario/gmail-automation.git
cd gmail-automation
```

2. Instale as dependências:
```bash
pip install -r requirements.txt
```

3. Para começar a executar a aplicação o comando:
```bash
streamlit run ui/app.py
```

## Estrutura do Projeto

```
.
├── automations/
│   └── gmail_creator/
│       ├── core.py              # Classe principal da automação
│       ├── account_setup.py     # Configuração inicial da conta
│       ├── phone_verify.py      # Verificação de telefone
│       ├── terms_handler.py     # Aceitação dos termos
│       ├── account_verify.py    # Verificação final da conta
│       ├── config.py           # Configurações e timeouts
│       ├── exceptions.py       # Exceções personalizadas
│       └── locators.py         # Localizadores de elementos
├── powerads_api/
│   ├── browser_manager.py      # Gerenciamento do browser
│   ├── ads_power_manager.py    # Interface com AdsPower
│   └── profiles.py            # Gerenciamento de perfis
└── requirements.txt
```


## Funcionalidades

- Criação automatizada de contas Gmail
- Integração com AdsPower Browser
- Suporte a verificação por SMS
- Gerenciamento de perfis do AdsPower
- Tratamento de erros e exceções
- Logs detalhados do processo

## Licença

Este projeto está sob a licença MIT. Veja o arquivo LICENSE para mais detalhes.
