import sys
import time
import json
import logging
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os

# Criar diretório de logs se não existir
os.makedirs("logs", exist_ok=True)

# Configurar logging para exibir no terminal e no arquivo
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/gmail_automation.log"),
        logging.StreamHandler(sys.stdout)  # Adiciona handler para o terminal
    ]
)

# Adicionar o caminho correto do projeto
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Importações
from apis.sms_api import SMSAPI
from powerads_api.ads_power_manager import AdsPowerManager
from apis.phone_manager import PhoneManager
from credentials.credentials_manager import load_credentials, add_or_update_api_key, delete_api_key, get_credential
from powerads_api.browser_manager import BrowserManager, BrowserConfig
from powerads_api.profiles import get_profiles, ProfileManager
from automations.data_generator import generate_gmail_credentials
from automations.gmail_creator.core import GmailCreator

# Função para recarregar configurações das APIs quando necessário


def refresh_api_configurations():
    """Recarrega as configurações das APIs a partir das credenciais mais recentes."""
    logging.info("Recarregando configurações das APIs")

    # Recarregar credenciais (usar cache interno do gerenciador)
    credentials = load_credentials()

    # Configurar cabeçalhos do AdsPower com base nas credenciais atualizadas
    pa_api_key = credentials.get("PA_API_KEY", None)
    pa_base_url = credentials.get(
        "PA_BASE_URL", "http://local.adspower.net:50325")

    headers = {
        "Authorization": f"Bearer {pa_api_key}",
        "Content-Type": "application/json"
    } if pa_api_key else {}

    # Atualizar a instância da API de SMS
    sms_api = SMSAPI(api_key=None)  # Inicializa sem chave
    sms_api.refresh_credentials()   # Recarrega a chave da API das credenciais

    # Criar ou atualizar AdsPowerManager
    adspower_manager = None
    if pa_api_key:
        adspower_manager = AdsPowerManager(pa_base_url, pa_api_key)

    return {
        "sms_api": sms_api,
        "pa_base_url": pa_base_url,
        "pa_headers": headers,
        "adspower_manager": adspower_manager
    }

# Função para recarregar perfis do AdsPower


def reload_profiles():
    """Recarrega a lista de perfis do AdsPower."""
    logging.info("Recarregando perfis do AdsPower")
    try:
        # Verificar se já temos perfis em cache e se são recentes (menos de 30 segundos)
        current_time = time.time()
        if (hasattr(st.session_state, 'profiles') and
            hasattr(st.session_state, 'last_reload') and
                current_time - st.session_state.last_reload < 30):
            logging.info("Usando cache de perfis (menos de 30 segundos)")
            return st.session_state.profiles

        # Criar instância do ProfileManager
        profile_manager = ProfileManager(st.session_state)

        # Adicionar atraso para evitar limite de taxa
        time.sleep(1)

        # Obter perfis ativos
        active_profiles = profile_manager.get_all_profiles(force_refresh=True)

        if active_profiles:
            # Atualizar o estado da sessão
            profile_dict = {p["name"]: p["user_id"] for p in active_profiles}
            st.session_state.profiles = profile_dict
            st.session_state.last_reload = time.time()

            # Inicializar o cache de perfis se necessário
            if not hasattr(st.session_state, 'profiles_cache'):
                st.session_state.profiles_cache = {}

            # Atualizar o cache com informações detalhadas dos perfis
            for profile in active_profiles:
                st.session_state.profiles_cache[profile["user_id"]] = profile

            # Aguardar antes de fazer mais requisições
            time.sleep(1)

            logging.info(f"Total de perfis ativos: {len(active_profiles)}")
            return profile_dict
        else:
            logging.warning("Nenhum perfil ativo encontrado no AdsPower")
            return {}
    except Exception as e:
        logging.error(f"Erro ao recarregar perfis: {str(e)}")
        return {}

# Função para remover uma conta da lista


def delete_account(idx):
    logging.info(f"Tentando remover conta no índice {idx}")
    try:
        # Carregar lista atual
        if os.path.exists(CREDENTIALS_PATH) and os.path.getsize(CREDENTIALS_PATH) > 0:
            with open(CREDENTIALS_PATH, "r") as file:
                accounts = json.load(file)

            # Remover a conta pelo índice
            if 0 <= idx < len(accounts):
                removed_account = accounts.pop(idx)

                # Salvar a lista atualizada
                with open(CREDENTIALS_PATH, "w") as file:
                    json.dump(accounts, file, indent=4)

                logging.info(
                    f"Conta {removed_account.get('email', 'Conta desconhecida')} removida com sucesso")
                return True, removed_account.get('email', 'Conta desconhecida')
            return False, "Índice inválido"
        return False, "Arquivo não encontrado"
    except Exception as e:
        logging.error(f"Erro ao remover conta: {str(e)}")
        return False, str(e)

# Função para limpar todas as contas


def clear_all_accounts():
    logging.info("Tentando limpar todas as contas")
    try:
        if os.path.exists(CREDENTIALS_PATH):
            with open(CREDENTIALS_PATH, "w") as file:
                json.dump([], file)
            logging.info("Todas as contas foram removidas com sucesso")
            return True
        return False
    except Exception as e:
        logging.error(f"Erro ao limpar contas: {str(e)}")
        st.error(f"Erro ao limpar contas: {str(e)}")
        return False


# Obter configurações iniciais das APIs
api_config = refresh_api_configurations()
sms_api = api_config["sms_api"]
PA_BASE_URL = api_config["pa_base_url"]
HEADERS = api_config["pa_headers"]
adspower_manager = api_config["adspower_manager"]

# Caminho para salvar credenciais do Gmail
CREDENTIALS_PATH = "credentials/gmail.json"

# Inicializar estado da sessão para rastrear atualizações de credenciais
if 'current_page' not in st.session_state:
    st.session_state.current_page = " Gerenciar Credenciais"  # Inicializa a página atual

# Ativar recarregamento amplo na sessão para componentes gerenciados
if 'initialized' not in st.session_state:
    st.session_state.initialized = False
    st.session_state.active_profile = None
    st.session_state.profiles = {}  # Adicionar profiles ao estado da sessão
    st.session_state.last_reload = 0  # Timestamp da última recarga de perfis

# Inicializar gerenciadores
phone_manager = PhoneManager()

# Criar menu lateral no Streamlit
st.sidebar.title(" Menu de Navegação")

# Seção de Automações
st.sidebar.subheader("Automações")
if st.sidebar.button(" Automação Gmail"):
    st.session_state.current_page = " Automação Gmail"

# Seção de Administração
st.sidebar.subheader("Adm")
if st.sidebar.button(" Gerenciar Credenciais"):
    st.session_state.current_page = " Gerenciar Credenciais"

if st.sidebar.button(" Contas Criadas"):
    st.session_state.current_page = " Contas Criadas"

if st.sidebar.button("[TELEFONE] Gerenciar Números"):
    st.session_state.current_page = "[TELEFONE] Gerenciar Números"

# Adicionar ao menu lateral no arquivo app.py, após a seção "Adm"
if st.sidebar.button(" Consulta de Preços"):
    st.session_state.current_page = " Consulta de Preços"

# Adicionar informações de saldo na barra lateral
try:
    sms_balance = sms_api.get_balance()
    if sms_balance is not None:
        saldo_color = "green" if sms_balance > 20 else "orange" if sms_balance > 5 else "red"
        st.sidebar.markdown(
            f" **Saldo SMS:** <span style='color:{saldo_color}'>{sms_balance:.2f} RUB</span>", unsafe_allow_html=True)
    else:
        st.sidebar.warning("[AVISO] Não foi possível obter o saldo SMS")
except Exception as e:
    logging.error(f"Erro ao obter saldo SMS: {str(e)}")

# Adicionar status do AdsPower na barra lateral
if adspower_manager:
    api_health = adspower_manager.check_api_health()
    if api_health:
        st.sidebar.success("[OK] AdsPower conectado")
    else:
        st.sidebar.error("[ERRO] AdsPower não disponível")
else:
    st.sidebar.warning("[AVISO] Chave de API do AdsPower não configurada")

# **ABA 1 - GERENCIAMENTO DE CREDENCIAIS**
if st.session_state.current_page == " Gerenciar Credenciais":
    st.title(" Gerenciamento de Credenciais")
    logging.info("Acessando aba de Gerenciamento de Credenciais")

    # Botão para recarregar credenciais manualmente (para debugging)
    if st.button("[ATUALIZANDO] Recarregar Credenciais"):
        logging.info("Recarregando credenciais manualmente")
        st.session_state.last_credentials_update = time.time()
        api_config = refresh_api_configurations()
        sms_api = api_config["sms_api"]
        PA_BASE_URL = api_config["pa_base_url"]
        HEADERS = api_config["pa_headers"]
        adspower_manager = api_config["adspower_manager"]
        st.success("[OK] Credenciais recarregadas com sucesso!")

    # Carregar credenciais existentes
    credentials = load_credentials(force_reload=True)
    st.subheader(" Credenciais Atuais")
    if credentials:
        for key, value in credentials.items():
            # Esconder a parte principal da chave de API para segurança
            if key.endswith("_API_KEY") and value and len(value) > 8:
                display_value = value[:4] + "*" * (len(value) - 8) + value[-4:]
            else:
                display_value = value
            st.write(f"**{key}**: `{display_value}`")
    else:
        st.warning("[AVISO] Nenhuma credencial encontrada.")

    # Seção específica para configuração do AdsPower
    st.subheader(" Configuração da API AdsPower")

    with st.form("adspower_config_form"):
        pa_base_url = st.text_input(
            "Endereço da API do AdsPower",
            value=credentials.get(
                "PA_BASE_URL", "http://local.adspower.net:50325"),
            help="Por exemplo: http://local.adspower.net:50325 ou http://localhost:50325"
        )

        pa_api_key = st.text_input(
            "Chave da API do AdsPower",
            value=credentials.get("PA_API_KEY", ""),
            type="password",
            help="Chave de API para autenticação com o AdsPower"
        )

        sms_activate_key = st.text_input(
            "Chave da API de SMS",
            value=credentials.get("SMS_ACTIVATE_API_KEY", ""),
            type="password",
            help="Chave de API para o serviço de SMS"
        )

        adspower_submit = st.form_submit_button(
            "[SALVO] Salvar Configurações AdsPower")

        if adspower_submit:
            changes_made = False

            # Salvar PA_BASE_URL
            if pa_base_url:
                if add_or_update_api_key("PA_BASE_URL", pa_base_url):
                    changes_made = True
                    logging.info(f"PA_BASE_URL atualizado para: {pa_base_url}")

            # Salvar PA_API_KEY
            if pa_api_key:
                if add_or_update_api_key("PA_API_KEY", pa_api_key):
                    changes_made = True
                    logging.info("PA_API_KEY atualizado")

            # Salvar SMS_ACTIVATE_API_KEY
            if sms_activate_key:
                if add_or_update_api_key("SMS_ACTIVATE_API_KEY", sms_activate_key):
                    changes_made = True
                    logging.info("SMS_ACTIVATE_API_KEY atualizado")

            if changes_made:
                st.session_state.last_credentials_update = time.time()
                api_config = refresh_api_configurations()
                sms_api = api_config["sms_api"]
                PA_BASE_URL = api_config["pa_base_url"]
                HEADERS = api_config["pa_headers"]
                adspower_manager = api_config["adspower_manager"]
                st.success(
                    "[OK] Configurações do AdsPower atualizadas com sucesso!")
            else:
                st.warning("[AVISO] Nenhuma mudança foi feita nas configurações.")

    # Dicas para a configuração do AdsPower
    st.info("""
    ** Dicas para configuração do AdsPower:**
    
    1. Verifique se o AdsPower está em execução em sua máquina
    2. Certifique-se de que a API está habilitada nas configurações do AdsPower
    3. O endereço padrão é `http://local.adspower.net:50325`
    4. Você também pode usar `http://localhost:50325` se o padrão não funcionar
    5. Para ambiente de produção, use o endereço IP exato da máquina onde o AdsPower está instalado
    """)

    # Formulário para adicionar/atualizar chave (opcional, para outras chaves)
    st.subheader(" Adicionar/Atualizar Outras Chaves")
    with st.form("add_key_form"):
        key_name = st.text_input("Nome da Chave (ex: CUSTOM_API_KEY)")
        key_value = st.text_input("Valor da Chave", type="password")
        submit_button = st.form_submit_button("[SALVO] Salvar Chave")

        if submit_button:
            if key_name and key_value:
                logging.info(f"Tentando adicionar/atualizar chave: {key_name}")
                if add_or_update_api_key(key_name, key_value):
                    st.session_state.last_credentials_update = time.time()
                    api_config = refresh_api_configurations()
                    sms_api = api_config["sms_api"]
                    PA_BASE_URL = api_config["pa_base_url"]
                    HEADERS = api_config["pa_headers"]
                    adspower_manager = api_config["adspower_manager"]
                    st.success(
                        f"[OK] Chave '{key_name}' adicionada/atualizada com sucesso!")
                    logging.info(
                        f"Chave '{key_name}' adicionada/atualizada com sucesso")
                else:
                    st.error("[ERRO] Erro ao salvar a chave. Verifique os logs.")
                    logging.error(f"Erro ao salvar a chave '{key_name}'")
            else:
                st.error("[ERRO] Nome e valor da chave são obrigatórios.")
                logging.warning("Tentativa de salvar chave sem nome ou valor")

    # Seção para excluir chave
    st.subheader(" Remover Chave de API")
    key_to_delete = st.selectbox("Selecione a chave para remover", options=list(
        credentials.keys()) if credentials else [])

    if st.button(" Excluir Chave"):
        if key_to_delete:
            logging.info(f"Tentando excluir chave: {key_to_delete}")
            if delete_api_key(key_to_delete):
                st.session_state.last_credentials_update = time.time()
                api_config = refresh_api_configurations()
                sms_api = api_config["sms_api"]
                PA_BASE_URL = api_config["pa_base_url"]
                HEADERS = api_config["pa_headers"]
                adspower_manager = api_config["adspower_manager"]
                st.success(f"[OK] Chave '{key_to_delete}' removida com sucesso!")
                logging.info(f"Chave '{key_to_delete}' removida com sucesso")
            else:
                st.error("[ERRO] Erro ao remover a chave. Verifique os logs.")
                logging.error(f"Erro ao remover a chave '{key_to_delete}'")
        else:
            st.warning("[AVISO] Nenhuma chave selecionada.")
            logging.warning("Tentativa de excluir chave sem selecionar uma")

    # Mostrar informações sobre as APIs configuradas
    st.subheader(" Status das APIs")

    # Status da API SMS
    sms_balance = None
    try:
        sms_balance = sms_api.get_balance()
        if sms_balance is not None:
            st.success(f"[OK] API SMS conectada. Saldo: {sms_balance} RUB")
            logging.info(f"API SMS conectada. Saldo: {sms_balance} RUB")
        else:
            st.error("[ERRO] API SMS não conectada. Verifique sua chave de API.")
            logging.error("API SMS não conectada")
    except Exception as e:
        st.error(f"[ERRO] Erro ao conectar à API SMS: {str(e)}")
        logging.error(f"Erro ao conectar à API SMS: {str(e)}")

    # Status da API AdsPower
    if HEADERS.get("Authorization"):
        try:
            # Tentar uma requisição simples para verificar conexão
            if adspower_manager:
                api_health = adspower_manager.check_api_health()
                if api_health:
                    profiles = adspower_manager.get_all_profiles()
                    st.success(
                        f"[OK] API AdsPower conectada. Total de perfis: {len(profiles)}")
                    logging.info(
                        f"API AdsPower conectada. Total de perfis: {len(profiles)}")
                else:
                    st.warning(
                        "[AVISO] API AdsPower não responde corretamente. Verifique a conexão.")
                    logging.warning("API AdsPower não responde corretamente")
            else:
                st.warning("[AVISO] Gerenciador AdsPower não inicializado.")
                logging.warning("Gerenciador AdsPower não inicializado")
        except Exception as e:
            st.error(f"[ERRO] Erro ao conectar à API AdsPower: {str(e)}")
            logging.error(f"Erro ao conectar à API AdsPower: {str(e)}")
    else:
        st.warning(
            "[AVISO] API AdsPower não configurada. Adicione a chave 'PA_API_KEY'.")
        logging.warning("API AdsPower não configurada")

# **ABA 2 - AUTOMAÇÃO GMAIL**
elif st.session_state.current_page == " Automação Gmail":
    # Verificar se é necessário recarregar as configurações das APIs
    api_config = refresh_api_configurations()
    sms_api = api_config["sms_api"]
    PA_BASE_URL = api_config["pa_base_url"]
    HEADERS = api_config["pa_headers"]
    adspower_manager = api_config["adspower_manager"]

    st.title(" Automação no Gmail - Criar Conta")
    logging.info("Acessando aba de Automação Gmail")

    # Listar perfis disponíveis no AdsPower
    profiles_list = []
    profile_options = {}

    # Botão para recarregar perfis
    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("[ATUALIZANDO] Recarregar Perfis"):
            logging.info("Recarregando perfis manualmente")
            profile_options = reload_profiles()
            st.success("[OK] Perfis recarregados com sucesso!")

    try:
        if adspower_manager:
            # Criar instância do ProfileManager
            profile_manager = ProfileManager(st.session_state)

            # Obter perfis ativos
            profiles = profile_manager.get_all_profiles()
            if profiles:
                profile_options = {p['name']: p['user_id'] for p in profiles}
                logging.info(
                    f"Carregados {len(profiles)} perfis ativos do AdsPower")
            else:
                profile_options = {}
        else:
            st.warning("[AVISO] Gerenciador AdsPower não inicializado.")
            logging.warning("Gerenciador AdsPower não inicializado")

    except Exception as e:
        profile_options = {}
        st.error(f"Erro ao carregar perfis: {e}")
        logging.error(f"Erro ao carregar perfis: {e}")

    # Exibir dropdown com perfis
    selected_profile = st.selectbox(
        "Selecione um perfil",
        options=list(profile_options.keys()) if profile_options else [
            "Nenhum perfil disponível"],
        key="profile_selector"
    )

    # Lógica para usar o perfil selecionado
    if selected_profile != "Nenhum perfil disponível":
        profile_id = profile_options[selected_profile]
        logging.info(
            f"Perfil selecionado: {selected_profile} (ID: {profile_id})")
    else:
        st.warning("[AVISO] Nenhum perfil disponível para seleção.")

    # UI para criação de contas
    if profile_options:
        # Configurações do navegador
        st.subheader(" Configurações do Navegador")
        browser_col1, browser_col2 = st.columns(2)

        with browser_col1:
            headless_mode = st.checkbox(" Modo Headless (navegador invisível)",
                                        help="Execute o navegador em segundo plano, sem interface gráfica")

            browser_wait_time = st.number_input("[TEMPO] Tempo máximo de espera (segundos)",
                                                min_value=10,
                                                max_value=120,
                                                value=60)

        with browser_col2:
            st.write("")

        # Botão para iniciar a automação do Gmail
        if st.button("[INICIO] Criar Conta Gmail"):
            try:
                profile_id = profile_options[selected_profile]
                logging.info(
                    f"Iniciando criação de conta Gmail para perfil: {profile_id}")

                # Gerar credenciais para a nova conta
                credentials = generate_gmail_credentials()

                # Configurar o browser manager
                browser_config = BrowserConfig(
                    headless=headless_mode,
                    max_wait_time=browser_wait_time
                )

                # Criar instância do BrowserManager
                browser_manager = BrowserManager(adspower_manager)
                browser_manager.set_config(browser_config)

                # Criar instância do GmailCreator
                gmail_creator = GmailCreator(
                    browser_manager=browser_manager,
                    credentials=credentials,
                    sms_api=sms_api,
                    profile_name=selected_profile
                )

                # Iniciar processo de criação
                with st.spinner("[ATUALIZANDO] Criando conta Gmail..."):
                    success, account_data = gmail_creator.create_account(
                        user_id=profile_id
                    )

                    if success:
                        # Adicionar data de criação
                        account_data["creation_date"] = datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S")

                        # Salvar conta no arquivo de credenciais
                        if os.path.exists(CREDENTIALS_PATH):
                            with open(CREDENTIALS_PATH, "r") as file:
                                try:
                                    accounts = json.load(file)
                                except json.JSONDecodeError:
                                    accounts = []
                        else:
                            accounts = []

                        accounts.append(account_data)

                        with open(CREDENTIALS_PATH, "w") as file:
                            json.dump(accounts, file, indent=4)

                        st.success("[OK] Conta Gmail criada com sucesso!")
                        st.json(account_data)
                        logging.info(
                            f"Conta criada com sucesso: {account_data['email']}")
                    else:
                        st.error("[ERRO] Falha ao criar conta Gmail")
                        logging.error("Falha ao criar conta Gmail")

            except Exception as e:
                st.error(f"[ERRO] Erro durante a criação da conta: {str(e)}")
                logging.error(f"Erro durante a criação da conta: {str(e)}")

            finally:
                # Tentar fechar o browser se ele existir
                try:
                    if 'browser_manager' in locals() and browser_manager:
                        browser_manager.close_browser(profile_id)
                except Exception as e:
                    logging.error(f"Erro ao fechar o browser: {str(e)}")

# **ABA 3 - CONTAS CRIADAS**
elif st.session_state.current_page == " Contas Criadas":
    st.title(" Contas Criadas")
    logging.info("Acessando aba de Contas Criadas")

    # Carregar a lista de contas
    credentials_list = []
    if os.path.exists(CREDENTIALS_PATH) and os.path.getsize(CREDENTIALS_PATH) > 0:
        with open(CREDENTIALS_PATH, "r") as file:
            try:
                credentials_list = json.load(file)
                logging.info(
                    f"Carregadas {len(credentials_list)} contas do arquivo")
            except json.JSONDecodeError:
                st.error(
                    "[ERRO] Erro ao carregar o arquivo de contas. O formato JSON pode estar corrompido.")
                logging.error(
                    "Erro ao carregar o arquivo de contas - JSON inválido")

    # Mostrar contagem e botão para limpar todas
    if credentials_list:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.info(f"Total de contas: {len(credentials_list)}")
        with col2:
            if st.button(" Limpar Todas", help="Apagar todas as contas"):
                if st.checkbox("Confirmar exclusão de todas as contas", key="confirm_clear"):
                    if clear_all_accounts():
                        st.success(
                            "Todas as contas foram removidas com sucesso!")
                        logging.info(
                            "Todas as contas foram removidas com sucesso")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Erro ao remover todas as contas.")
                        logging.error("Erro ao remover todas as contas")

        # Adicionar campo de busca
        search_term = st.text_input(
            "[BUSCA] Buscar conta", placeholder="Digite email, telefone ou data")

        # Mostrar contas da mais recente para a mais antiga
        reversed_list = list(reversed(credentials_list))

        # Filtrar contas baseado na busca
        filtered_list = reversed_list
        if search_term:
            filtered_list = [
                cred for cred in reversed_list
                if search_term.lower() in str(cred.get('email', '')).lower() or
                search_term.lower() in str(cred.get('phone', '')).lower() or
                search_term.lower() in str(cred.get('creation_date', '')).lower() or
                search_term.lower() in str(cred.get('profile', '')).lower()
            ]

            st.info(
                f"Encontradas {len(filtered_list)} contas contendo '{search_term}'")
            logging.info(
                f"Busca por '{search_term}' encontrou {len(filtered_list)} contas")

        # Mostrar as contas filtradas
        for idx, cred in enumerate(filtered_list):
            # Encontrar o índice original na lista completa
            original_idx = credentials_list.index(cred)

            creation_date = cred.get('creation_date', 'Data desconhecida')
            email = cred.get('email', 'N/A')
            telefone = cred.get('phone', 'N/A')
            profile = cred.get('profile', 'N/A')

            # Usar índice único para cada conta
            account_id = f"acc_{idx}"

            # Criar cabeçalho com botão de apagar
            col1, col2 = st.columns([5, 1])
            with col1:
                expander = st.expander(f"{email} - {creation_date}")
            with col2:
                if st.button("", key=f"delete_{account_id}", help="Apagar esta conta"):
                    success, message = delete_account(original_idx)
                    if success:
                        st.success(f"Conta {message} removida com sucesso!")
                        logging.info(f"Conta {message} removida com sucesso")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"Erro ao remover conta: {message}")
                        logging.error(f"Erro ao remover conta: {message}")

            # Conteúdo do expander
            with expander:
                # Informações da conta em um formato mais organizado
                st.markdown(f"""
                | Detalhes da Conta | |
                |----------------|--------------|
                | **Email:** | `{email}` |
                | **Senha:** | `{cred.get('password', 'N/A')}` |
                | **Telefone:** | `{telefone}` |
                | **País:** | `{cred.get('country_name', 'N/A')}` |
                | **ID de Ativação:** | `{cred.get('activation_id', 'N/A')}` |
                | **Nome:** | `{cred.get('first_name', 'N/A')} {cred.get('last_name', 'N/A')}` |
                | **Perfil:** | `{profile}` |
                | **Data de Criação:** | `{creation_date}` |
                """)

                # Adicionar botões para copiar email/senha com chaves únicas baseadas no índice
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"[CLIPBOARD] Copiar Email", key=f"copy_email_{account_id}"):
                        st.code(email, language=None)
                        st.info("Email copiado para a área de transferência")
                        logging.info(
                            f"Email {email} copiado para a área de transferência")
                with col2:
                    if st.button(f"[CLIPBOARD] Copiar Senha", key=f"copy_senha_{account_id}"):
                        st.code(cred.get('password', ''), language=None)
                        st.info("Senha copiada para a área de transferência")
                        logging.info(
                            f"Senha para {email} copiada para a área de transferência")
    else:
        st.warning("[AVISO] Nenhuma conta de Gmail encontrada.")
        logging.warning("Nenhuma conta de Gmail encontrada")

# **ABA 4 - GERENCIAR NÚMEROS**
elif st.session_state.current_page == "[TELEFONE] Gerenciar Números":
    st.title("[TELEFONE] Gerenciamento de Números de Telefone")
    logging.info("Acessando aba de Gerenciamento de Números")

    # Carregar todos os números disponíveis
    números = phone_manager._load_numbers()

    if not números:
        st.warning("[AVISO] Nenhum número de telefone disponível para gerenciamento.")
        logging.info("Nenhum número de telefone disponível para gerenciamento")
    else:
        # Mostrar estatísticas básicas
        st.subheader("[CLIPBOARD] Estatísticas de Números")
        stats = phone_manager.get_stats()
        logging.info(f"Estatísticas de números: {stats}")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total de Números", stats["total_numbers"])
        with col2:
            st.metric("Números Ativos", stats["active_numbers"])
        with col3:
            st.metric("Economia Estimada", stats["estimated_savings"])

        # Listar todos os números com detalhes
        st.subheader("[CLIPBOARD] Lista de Números")

        # Adicionar busca
        search_number = st.text_input(
            "[BUSCA] Filtrar por número", placeholder="Digite parte do número...")

        # Filtrar números
        filtered_numbers = números
        if search_number:
            filtered_numbers = [
                n for n in números if search_number in n.get("phone_number", "")]
            st.info(
                f"Encontrados {len(filtered_numbers)} números contendo '{search_number}'")
            logging.info(
                f"Busca por '{search_number}' encontrou {len(filtered_numbers)} números")

        # Mostrar os números disponíveis
        for i, número in enumerate(filtered_numbers):
            phone = número.get("phone_number", "N/A")
            country = número.get("country_code", "N/A")
            first_used = datetime.fromtimestamp(número.get("first_used", 0))
            last_used = datetime.fromtimestamp(número.get("last_used", 0))
            services = número.get("services", [])
            times_used = número.get("times_used", 0)

            # Verificar se o número ainda está ativo
            now = time.time()
            time_since_first_use = now - número.get("first_used", 0)
            is_active = time_since_first_use < phone_manager.reuse_window

            # Calcular tempo restante se estiver ativo
            time_left = ""
            if is_active:
                remaining_seconds = phone_manager.reuse_window - time_since_first_use
                minutes = int(remaining_seconds // 60)
                seconds = int(remaining_seconds % 60)
                time_left = f"{minutes}m {seconds}s"

            # Criar um card para o número
            status_color = "green" if is_active else "gray"
            status_text = "Ativo" if is_active else "Expirado"

            with st.expander(f" {phone} - {status_text} {'(' + time_left + ')' if time_left else ''}"):
                st.markdown(f"""
                | Detalhes do Número | |
                |----------------|--------------|
                | **Número:** | `{phone}` |
                | **País:** | `{country}` |
                | **Status:** | <span style='color:{status_color}'>{status_text}</span> |
                | **Tempo restante:** | {time_left if is_active else "Expirado"} |
                | **ID de Ativação:** | `{número.get('activation_id', 'N/A')}` |
                | **Primeira Utilização:** | {first_used.strftime('%Y-%m-%d %H:%M:%S')} |
                | **Última Utilização:** | {last_used.strftime('%Y-%m-%d %H:%M:%S')} |
                | **Serviços Utilizados:** | {', '.join(services)} |
                | **Vezes Utilizado:** | {times_used} |
                """, unsafe_allow_html=True)

                # Adicionar botão para remover número
                if st.button(" Remover Número", key=f"remove_number_{i}"):
                    try:
                        # Implementar lógica para remover o número
                        if phone_manager.remove_number(phone):
                            st.success(
                                f"[OK] Número {phone} removido com sucesso!")
                            logging.info(
                                f"Número {phone} removido com sucesso")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(
                                f"[ERRO] Erro ao remover número: {phone} não encontrado.")
                    except Exception as e:
                        st.error(f"[ERRO] Erro ao remover número: {str(e)}")
                        logging.error(
                            f"Erro ao remover número {phone}: {str(e)}")

                # Adicionar botão para cancelar número
                if st.button(" Cancelar Número", key=f"cancel_number_{i}"):
                    # Supondo que você tenha o ID do número
                    if phone_manager.cancel_number(número["id"]):
                        st.success(
                            f"[OK] Número {número['phone_number']} cancelado com sucesso!")
                    else:
                        st.error(
                            f"[ERRO] Erro ao cancelar o número {número['phone_number']}.")

# **ABA 5 - CONSULTA DE PREÇOS**
elif st.session_state.current_page == " Consulta de Preços":
    st.title(" Consulta de Preços da API SMS")
    logging.info("Acessando aba de Consulta de Preços")

    # Importar as funções do arquivo price.py
    try:
        from apis.price import teste_precos_multi_servico, teste_operadoras_brasil, teste_preco_maximo
    except ImportError as e:
        st.error(f"[ERRO] Erro ao importar módulo de preços: {str(e)}")
        logging.error(f"Erro ao importar módulo de preços: {str(e)}")

    # Mostrar saldo atual
    try:
        saldo = sms_api.get_balance()
        if saldo is not None:
            st.success(f" Saldo atual: {saldo:.2f} RUB")
        else:
            st.warning("[AVISO] Não foi possível obter o saldo da API SMS")
    except Exception as e:
        st.error(f"[ERRO] Erro ao obter saldo: {str(e)}")

    # Criar um layout com três seções (uma para cada tipo de consulta)
    st.info("Esta ferramenta realiza consultas de preços sem efetuar compras de números")

    # Tabs para organizar os diferentes tipos de consulta
    tab1, tab2, tab3 = st.tabs(
        ["[GRAFICO] Multi-serviço", " Operadoras Brasil", " Preço Máximo"])

    with tab1:
        st.subheader("[GRAFICO] Consulta de Preços Multi-serviço")
        st.write(
            "Esta consulta verifica os preços para diferentes combinações de serviços")

        # Botão para iniciar a consulta de preços multi-serviço
        if st.button("[BUSCA] Consultar Preços Multi-serviço"):
            with st.spinner("Consultando preços para múltiplos serviços..."):
                try:
                    resultados = teste_precos_multi_servico()

                    # Mostrar os resultados em formato de tabela
                    if "saldo" in resultados:
                        st.metric("Saldo Disponível",
                                  f"{resultados['saldo']:.2f} RUB")

                    # Criar DataFrame para visualização
                    data = []
                    for key, value in resultados.items():
                        if key != "saldo":
                            servicos_str = "+".join(value["servicos"])
                            soma_precos = value.get("soma_precos", 0)
                            data.append({
                                "Serviços": servicos_str,
                                "Preço Total (RUB)": soma_precos,
                                "Nº de Serviços": len(value["servicos"])
                            })

                    if data:
                        df = pd.DataFrame(data)
                        st.dataframe(df)

                        # Mostrar caminho do arquivo salvo
                        st.success(
                            "[OK] Resultados completos salvos em 'resultados_testes/precos_multi_servico.json'")
                    else:
                        st.warning("[AVISO] Nenhum resultado obtido")

                except Exception as e:
                    st.error(f"[ERRO] Erro durante a consulta: {str(e)}")
                    logging.error(
                        f"Erro durante a consulta de preços multi-serviço: {str(e)}")

    with tab2:
        st.subheader(" Consulta de Operadoras Brasil")
        st.write("Esta consulta simula verificações por operadoras no Brasil")

        # Botão para iniciar a consulta de operadoras
        if st.button("[BUSCA] Consultar Operadoras Brasil"):
            with st.spinner("Consultando disponibilidade por operadoras..."):
                try:
                    resultados = teste_operadoras_brasil()

                    # Mostrar resultados em formato de tabela
                    for servicos_str, dados in resultados.items():
                        st.subheader(f"Serviços: {servicos_str}")

                        # Disponibilidade geral
                        disp_data = []
                        for servico, disponibilidade in dados["disponibilidade_geral"].items():
                            disp_data.append({
                                "Serviço": servico,
                                "Números Disponíveis": disponibilidade
                            })

                        if disp_data:
                            st.write("Disponibilidade Geral:")
                            st.dataframe(pd.DataFrame(disp_data))

                        # Informações de operadoras (simulado)
                        st.write("Simulação por Operadoras:")
                        for operadora, info in dados["operadoras"].items():
                            status = "[OK] Disponível" if info["disponivel"] else "[ERRO] Indisponível"
                            st.info(f"**{operadora.upper()}**: {status}")

                    # Mostrar caminho do arquivo salvo
                    st.success(
                        "[OK] Resultados completos salvos em 'resultados_testes/operadoras_brasil.json'")

                except Exception as e:
                    st.error(f"[ERRO] Erro durante a consulta: {str(e)}")
                    logging.error(
                        f"Erro durante a consulta de operadoras Brasil: {str(e)}")

    with tab3:
        st.subheader(" Análise de Preço Máximo")
        st.write("Esta consulta analisa diferentes faixas de preço máximo")

        # Botão para iniciar a consulta de preço máximo
        if st.button("[BUSCA] Analisar Preços Máximos"):
            with st.spinner("Analisando faixas de preço máximo..."):
                try:
                    resultados = teste_preco_maximo()

                    # Mostrar preços atuais
                    if "precos_atuais" in resultados:
                        st.write("Preços Atuais por Serviço (Brasil):")
                        precos_data = []
                        for servico in resultados["precos_atuais"]:
                            precos_data.append({
                                "Serviço": servico["servico"],
                                "Preço (RUB)": servico["preco"],
                                "Números Disponíveis": servico["disponivel"]
                            })

                        if precos_data:
                            st.dataframe(pd.DataFrame(precos_data))

                        st.metric("Preço Total Atual",
                                  f"{resultados['preco_total_atual']:.2f} RUB")

                    # Mostrar análise de faixas
                    if "analise_faixas" in resultados:
                        st.write("Análise por Faixa de Preço:")
                        faixas_data = []
                        for preco, info in resultados["analise_faixas"].items():
                            faixas_data.append({
                                "Preço Máximo (RUB)": preco,
                                "Disponibilidade": "[OK] Possível" if info["seria_possivel"] else "[ERRO] Improvável",
                                "Observação": info["nota"]
                            })

                        if faixas_data:
                            st.dataframe(pd.DataFrame(faixas_data))

                    # Mostrar recomendação
                    if "recomendacao_geral" in resultados:
                        rec = resultados["recomendacao_geral"]
                        st.success(
                            f"[OK] Preço recomendado: **{rec['preco_recomendado']:.2f} RUB**")
                        st.info(rec["explicacao"])

                    # Mostrar caminho do arquivo salvo
                    st.success(
                        "[OK] Resultados completos salvos em 'resultados_testes/preco_maximo.json'")

                except Exception as e:
                    st.error(f"[ERRO] Erro durante a consulta: {str(e)}")
                    logging.error(
                        f"Erro durante a análise de preços máximos: {str(e)}")
