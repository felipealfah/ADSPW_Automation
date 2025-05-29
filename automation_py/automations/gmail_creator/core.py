import time
import logging
from enum import Enum
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium import webdriver

from powerads_api.browser_manager import BrowserManager
from .account_setup import AccountSetup
from .phone_verify import PhoneVerification
from .terms_handler import TermsHandler
from .account_verify import AccountVerify
from .exceptions import GmailCreationError, TermsAcceptanceError
from .config import timeouts, account_config, sms_config, log_config

logger = logging.getLogger(__name__)


class GmailCreationState(Enum):
    """Estados possíveis durante a criação da conta."""
    INITIAL = "initial"
    ACCOUNT_SETUP = "account_setup"
    PHONE_VERIFICATION = "phone_verification"
    TERMS_ACCEPTANCE = "terms_acceptance"
    ACCOUNT_VERIFICATION = "account_verification"
    COMPLETED = "completed"
    FAILED = "failed"


class GmailCreator:
    """Classe principal que gerencia o fluxo de criação da conta Gmail."""

    def __init__(self, browser_manager, credentials, sms_api=None, profile_name="default_profile", close_browser=False):
        self.browser_manager = browser_manager
        self.credentials = credentials
        self.sms_api = sms_api
        self.profile_name = profile_name if profile_name else "default_profile"
        self.driver = None
        self.phone_params = {}  # Mantido para compatibilidade, mas não usado externamente
        self.close_browser = close_browser  # Novo parâmetro para controlar fechamento do browser

        # Adicionar inicialização do phone_manager
        from apis.phone_manager import PhoneManager
        self.phone_manager = PhoneManager()

        # Configuração geral
        self.config = {
            "timeouts": timeouts,
            "account_config": account_config,
            "sms_config": sms_config,
            "log_config": log_config
        }

        self.state = GmailCreationState.INITIAL

    def initialize_browser(self, user_id: str) -> bool:
        """
        Inicializa o browser e configura o driver.

        Args:
            user_id: ID do perfil do AdsPower

        Returns:
            bool: True se a inicialização foi bem sucedida
        """
        try:
            logger.info("[INICIO] Iniciando browser para automação...")
            
            # 1. Verificar perfis do AdsPower
            logger.info("[PASSO 1] Verificando perfis do AdsPower...")
            profiles = self.browser_manager.adspower_manager.get_all_profiles(include_no_group=True)
            if not profiles:
                logger.error("[ERRO] Nenhum perfil encontrado no AdsPower")
                return False
            
            # Verificar se o perfil solicitado existe
            profile_exists = any(p.get("user_id") == user_id for p in profiles)
            if not profile_exists:
                logger.error(f"[ERRO] Perfil {user_id} não encontrado na lista de perfis")
                return False
            
            logger.info(f"[OK] Perfil {user_id} encontrado na lista de perfis")

            # 2. Tentar conectar ao perfil
            logger.info("[PASSO 2] Tentando conectar ao perfil...")
            success, browser_info = self.browser_manager.adspower_manager.verify_and_connect_profile(user_id)
            if not success or not browser_info:
                logger.error("[ERRO] Falha ao conectar ao perfil")
                return False
            
            logger.info("[OK] Conexão com o perfil estabelecida")

            # 3. Verificar informações do browser e websocket
            logger.info("[PASSO 3] Verificando informações do browser e websocket...")
            selenium_ws = browser_info.get("selenium_ws")
            webdriver_path = browser_info.get("webdriver_path")
            
            if not selenium_ws or not webdriver_path:
                logger.error("[ERRO] Informações do websocket ou webdriver ausentes")
                return False
            
            logger.info(f"[OK] Informações do browser obtidas: selenium_ws={selenium_ws}, webdriver_path={webdriver_path}")

            # 4. Tentar conectar ao websocket do browser
            logger.info("[PASSO 4] Tentando conectar ao websocket do browser...")
            try:
                from selenium.webdriver.chrome.service import Service
                from selenium.webdriver.chrome.options import Options

                service = Service(executable_path=webdriver_path)
                options = Options()
                options.add_experimental_option("debuggerAddress", selenium_ws)

                self.driver = webdriver.Chrome(service=service, options=options)
                
                # Verificar se o driver está funcionando
                _ = self.driver.current_url
                logger.info("[OK] Conexão com websocket estabelecida com sucesso")

                # 5. Configurar wait para o processo do Gmail Creator
                self.wait = WebDriverWait(self.driver, timeouts.DEFAULT_WAIT)
                logger.info("[OK] Browser inicializado e pronto para automação")
                return True

            except Exception as e:
                logger.error(f"[ERRO] Falha ao conectar ao websocket: {str(e)}")
                return False

        except Exception as e:
            logger.error(f"[ERRO] Erro ao inicializar browser: {str(e)}")
            return False

    def create_account(self, user_id: str) -> tuple[bool, dict]:
        """
        Cria uma nova conta Gmail.
        
        Returns:
            tuple: (sucesso, dados_da_conta)
                - sucesso (bool): True se a conta foi criada com sucesso
                - dados_da_conta (dict): Dicionário com informações da conta criada
        """
        try:
            logger.info("[INICIO] Iniciando criação da conta Gmail...")

            # Verificar e limpar o arquivo de credenciais
            self._clean_credentials_file()

            # Verificar estrutura das credenciais para diagnóstico
            logger.info(f"[DIAGNÓSTICO] Credenciais recebidas: {self.credentials}")
            
            # Verificar especificamente se 'username' está nas credenciais
            if 'username' not in self.credentials:
                logger.error("[ERRO] Campo 'username' não encontrado nas credenciais")
                logger.info(f"[DIAGNÓSTICO] Campos disponíveis: {list(self.credentials.keys())}")
                return False, {"error": "Campo 'username' não encontrado nas credenciais"}

            # 1. Abrir o Browser via API do AdsPower
            logger.info("[PASSO 1] Abrindo browser do AdsPower...")
            success, browser_info = self.browser_manager.start_browser(
                user_id=user_id,
                headless=False,
                max_wait_time=60
            )
            
            if not success or not browser_info:
                raise GmailCreationError("[ERRO] Falha ao abrir o browser do AdsPower")
            
            logger.info("[OK] Browser do AdsPower aberto com sucesso")
            logger.info(f"[DEBUG] Informações do browser: {browser_info}")

            # 2. Conectar ao websocket do browser
            logger.info("[PASSO 2] Conectando ao websocket do browser...")
            try:
                from selenium.webdriver.chrome.service import Service
                from selenium.webdriver.chrome.options import Options

                selenium_ws = browser_info.get("selenium_ws")
                webdriver_path = browser_info.get("webdriver_path")
                
                if not selenium_ws or not webdriver_path:
                    raise GmailCreationError("[ERRO] Informações do websocket ausentes")

                logger.info(f"[DEBUG] Conectando ao websocket: {selenium_ws}")
                logger.info(f"[DEBUG] Usando webdriver: {webdriver_path}")

                service = Service(executable_path=webdriver_path)
                options = Options()
                options.add_experimental_option("debuggerAddress", selenium_ws)
                self.driver = webdriver.Chrome(service=service, options=options)
                
                # Verificar conexão tentando acessar a URL atual
                try:
                    current_url = self.driver.current_url
                    logger.info(f"[DEBUG] Conexão estabelecida. URL atual: {current_url}")
                except Exception as e:
                    raise GmailCreationError(f"[ERRO] Falha ao verificar conexão com o browser: {str(e)}")
                
                # Configurar wait
                self.wait = WebDriverWait(self.driver, timeouts.DEFAULT_WAIT)
                logger.info("[OK] Conexão com websocket estabelecida com sucesso")
            
            except Exception as e:
                raise GmailCreationError(f"[ERRO] Falha ao conectar ao websocket: {str(e)}")

            # 3. Iniciar processo do Gmail Creator
            logger.info("[PASSO 3] Iniciando processo de criação do Gmail...")
            
            # URL atualizada que já direciona para a tela de nome/sobrenome
            gmail_signup_url = "https://accounts.google.com/signup/v2/createaccount?service=mail&continue=https://mail.google.com/mail/&flowName=GlifWebSignIn&flowEntry=SignUp&ec=asw-gmail-globalnav-create&theme=glif"
            
            logger.info("[DEBUG] Acessando URL de criação de conta atualizada...")
            self.driver.get(gmail_signup_url)
            
            # Pequena pausa para garantir carregamento da página
            time.sleep(2)
            
            # Verificar se estamos na página correta
            try:
                current_url = self.driver.current_url
                if "signup" in current_url and "createaccount" in current_url:
                    logger.info("[OK] Página de criação de conta carregada com sucesso")
                else:
                    logger.warning(f"[AVISO] URL atual pode não ser a página de criação de conta: {current_url}")
            except Exception as e:
                logger.error(f"[ERRO] Falha ao verificar URL atual: {str(e)}")
            
            # Contador para tentativas de criação completa da conta
            complete_attempts = 0
            max_complete_attempts = 2

            while complete_attempts < max_complete_attempts:
                complete_attempts += 1
                logger.info(f"[ATUALIZANDO] Tentativa {complete_attempts} de {max_complete_attempts} para criar conta completa")

                try:
                    # Passo 1: Configuração inicial da conta
                    self.state = GmailCreationState.ACCOUNT_SETUP
                    account_setup = AccountSetup(self.driver, self.credentials)
                    if not account_setup.start_setup():
                        raise GmailCreationError("[ERRO] Falha na configuração inicial da conta.")

                    # Passo 2: Verificação de telefone
                    self.state = GmailCreationState.PHONE_VERIFICATION
                    phone_verify = PhoneVerification(self.driver, self.sms_api)

                    # Sempre fornecer a instância do phone_manager
                    phone_verify.phone_manager = self.phone_manager

                    # Variáveis para controle de fluxo
                    phone_verification_success = False
                    phone_data = None

                    # Verificar se a tela de verificação de telefone está presente
                    if phone_verify._check_phone_screen():
                        logger.info(
                            " Tela de verificação de telefone detectada.")
                        # Se temos parâmetros de telefone para reutilização
                        if self.phone_params and isinstance(self.phone_params, dict) and self.phone_params.get('reuse_number'):
                            logger.info(
                                f" Configurando reutilização de número: {self.phone_params.get('phone_number')}")
                            phone_verify.reuse_number = True
                            phone_verify.predefined_number = self.phone_params.get(
                                'phone_number')
                            phone_verify.predefined_activation_id = self.phone_params.get(
                                'activation_id')
                            phone_verify.predefined_country_code = self.phone_params.get(
                                'country_code')

                        # Esta chamada inclui todo o processo de verificação por SMS
                        # Usar execute_with_retry para maior robustez
                        def verify_phone():
                            return phone_verify.handle_verification()

                        phone_verification_success = self.phone_manager.execute_with_retry(
                            verify_phone, max_retries=2, retry_delay=3)

                        if not phone_verification_success:
                            logger.warning(
                                "[AVISO] Falha na verificação de telefone. Tentando reiniciar processo...")
                            # Recarregar a página de início e tentar novamente em uma nova iteração
                            self.driver.get(
                                "https://accounts.google.com/lifecycle/steps/signup/name?continue=https://mail.google.com/mail/&dsh=S-684862571:1747225782083306&ec=asw-gmail-globalnav-create&flowEntry=SignUp&flowName=GlifWebSignIn&service=mail&theme=glif&TL=AArrULSuexEtzK3xne4xZ1R55BK2JV85MTLQAXOsa0vHEkq859tMrB_ByuxzdQ4B")
                            time.sleep(5)
                            continue  # Reinicia o processo completo

                        # Captura os dados do telefone verificado
                        phone_data = phone_verify.get_current_phone_data()
                        if not phone_data:
                            logger.error(
                                "[ERRO] Falha ao obter dados do telefone após verificação")
                            continue  # Tenta novamente o processo completo
                    else:
                        logger.info(
                            " Tela de verificação de telefone não detectada, pulando para aceitação dos termos.")
                        # Se não houver verificação de telefone, definimos valores padrão
                        phone_data = {
                            'phone_number': self.phone_params.get('phone_number') if self.phone_params else None,
                            'country_code': self.phone_params.get('country_code') if self.phone_params else None,
                            'activation_id': self.phone_params.get('activation_id') if self.phone_params else None,
                            'country_name': "unknown"
                        }
                        phone_verification_success = True

                    # Extrair dados do telefone
                    phone_number = phone_data.get('phone_number')
                    country_code = phone_data.get('country_code')
                    activation_id = phone_data.get('activation_id')
                    country_name = phone_data.get('country_name')

                    # Passo 3: Aceitação dos Termos
                    self.state = GmailCreationState.TERMS_ACCEPTANCE
                    # Obter o email de recuperação das credenciais, se disponível
                    recovery_email = self.credentials.get('recovery_email')

                    # Inicializar terms_handler com o email de recuperação
                    terms_handler = TermsHandler(
                        self.driver, recovery_email=recovery_email)

                    # Usar execute_with_retry para maior robustez
                    def accept_terms():
                        return terms_handler.handle_terms_acceptance()

                    terms_accepted = self.phone_manager.execute_with_retry(
                        accept_terms, max_retries=2, retry_delay=2)

                    if not terms_accepted:
                        logger.warning(
                            "[AVISO] Falha na aceitação dos termos. Tentando reiniciar processo...")
                        # Recarregar a página de início e tentar novamente
                        self.driver.get("https://accounts.google.com/signup")
                        time.sleep(5)
                        continue  # Reinicia o processo completo

                    # Passo 4: Verificação final da conta
                    self.state = GmailCreationState.ACCOUNT_VERIFICATION
                    account_verify = AccountVerify(
                        self.driver,
                        self.credentials,
                        profile_name=self.profile_name,
                        phone_number=phone_number
                    )

                    # Usar execute_with_retry para maior robustez
                    def verify_account():
                        return account_verify.verify_account()

                    account_verified = self.phone_manager.execute_with_retry(
                        verify_account, max_retries=2, retry_delay=2)

                    if not account_verified:
                        logger.warning(
                            "[AVISO] Falha na verificação final da conta. Tentando reiniciar processo...")
                        # Recarregar a página de início e tentar novamente
                        self.driver.get("https://accounts.google.com/signup")
                        time.sleep(5)
                        continue  # Reinicia o processo completo

                    # Se chegou aqui, tudo deu certo!
                    self.state = GmailCreationState.COMPLETED

                    # VERIFICAÇÃO CRUCIAL: Verificar o email real que foi criado
                    real_email = self._get_actual_email_from_page()

                    # Se conseguimos obter o email real da página, usá-lo em vez do email das credenciais
                    email_to_use = real_email if real_email else self.credentials[
                        "username"] + "@gmail.com"

                    if real_email and real_email != (self.credentials["username"] + "@gmail.com"):
                        logger.warning(
                            f"[AVISO] Email real criado ({real_email}) é diferente do email nas credenciais ({self.credentials['username']}@gmail.com)")

                    #  Retornar os dados completos da conta
                    account_data = {
                        "first_name": self.credentials["first_name"],
                        "last_name": self.credentials["last_name"],
                        "email": email_to_use,
                        "password": self.credentials["password"],
                        "phone": phone_number,
                        "country_code": country_code,
                        "country_name": country_name,
                        "activation_id": activation_id,
                        "profile": self.profile_name,
                        "creation_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "recovery_email": recovery_email,
                        "phone_data": phone_data if 'phone_data' in locals() else None
                    }

                    # Garantir que as credenciais sejam salvas corretamente
                    self._ensure_credentials_saved(account_data)

                    # Fechar o browser apenas se solicitado
                    if self.close_browser:
                        logger.info(f"[INFO] Fechando browser conforme solicitado para o perfil {user_id}")
                        self.browser_manager.close_browser(user_id)
                    else:
                        logger.info(f"[INFO] Mantendo browser aberto para o perfil {user_id}")

                    # Preparar dados detalhados da conta
                    account_details = {
                        "email": self.credentials["username"] + "@gmail.com",
                        "password": self.credentials["password"],
                        "first_name": self.credentials["first_name"],
                        "last_name": self.credentials["last_name"],
                        "recovery_email": self.credentials.get("recovery_email"),
                        "birth_info": {
                            "day": self.credentials["birth_day"],
                            "month": self.credentials["birth_month"],
                            "year": self.credentials["birth_year"]
                        },
                        "profile_id": user_id,
                        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "status": "active"
                    }
                    
                    # Salvar as credenciais no arquivo
                    self._save_credentials(account_details)
                    
                    return True, account_details

                except Exception as inner_e:
                    logger.error(
                        f"[ERRO] Erro durante a tentativa {complete_attempts}: {str(inner_e)}")
                    if complete_attempts < max_complete_attempts:
                        logger.info(
                            "[ATUALIZANDO] Reiniciando processo completo...")
                        self.driver.get("https://accounts.google.com/signup")
                        time.sleep(5)
                    else:
                        logger.error(
                            f"[ERRO] Todas as {max_complete_attempts} tentativas completas falharam")
                        raise

            # Se chegou aqui, todas as tentativas falharam
            return False, {"error": "Todas as tentativas falharam ao criar a conta"}

        except GmailCreationError as e:
            logger.error(f"[ALERTA] Erro durante o processo: {str(e)}")
            self.state = GmailCreationState.FAILED
            
            # Fechar o browser em caso de erro apenas se solicitado
            if self.close_browser and hasattr(self, 'browser_manager'):
                try:
                    self.browser_manager.close_browser(user_id)
                except Exception as close_error:
                    logger.error(f"[ERRO] Falha ao fechar browser após erro: {str(close_error)}")
            
            return False, {"error": str(e)}

        except Exception as e:
            logger.error(f"[ERRO] Erro inesperado: {str(e)}")
            self.state = GmailCreationState.FAILED
            
            # Fechar o browser em caso de erro apenas se solicitado
            if self.close_browser and hasattr(self, 'browser_manager'):
                try:
                    self.browser_manager.close_browser(user_id)
                except Exception as close_error:
                    logger.error(f"[ERRO] Falha ao fechar browser após erro: {str(close_error)}")
            
            return False, {"error": str(e)}

    def _get_actual_email_from_page(self):
        """
        Obtém o email real que foi criado a partir da página atual.

        Returns:
            str: O email real ou None se não for possível obter
        """
        try:
            # Aguardar um pouco para garantir que a página carregou completamente
            time.sleep(2)

            # Tentar diferentes métodos para encontrar o email na página

            # Método 1: Verificar se estamos na página do Gmail e obter o email do perfil
            try:
                # Verificar se estamos na página do Gmail
                if "mail.google.com" in self.driver.current_url:
                    # Clicar no avatar para mostrar o email
                    avatar_selectors = [
                        "//a[contains(@aria-label, 'Conta')]",
                        "//a[contains(@aria-label, 'Account')]",
                        "//a[contains(@href, 'accounts.google.com')]",
                        "//img[contains(@alt, 'Foto do perfil')]",
                        "//img[contains(@alt, 'Profile picture')]"
                    ]

                    for selector in avatar_selectors:
                        try:
                            avatar = self.driver.find_element(
                                By.XPATH, selector)
                            avatar.click()
                            time.sleep(1)
                            break
                        except:
                            continue

                    # Tentar encontrar o email no popup
                    email_selectors = [
                        "//div[contains(@class, 'gb_yb')]",
                        "//div[contains(text(), '@gmail.com')]",
                        "//a[contains(text(), '@gmail.com')]",
                        "//span[contains(text(), '@gmail.com')]"
                    ]

                    for selector in email_selectors:
                        try:
                            email_element = self.driver.find_element(
                                By.XPATH, selector)
                            email = email_element.text.strip()
                            if "@gmail.com" in email:
                                logger.info(
                                    f"[OK] Email real encontrado na interface: {email}")
                                return email
                        except:
                            continue
            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao tentar obter email do perfil do Gmail: {str(e)}")

            # Método 2: Verificar na URL
            try:
                current_url = self.driver.current_url
                if "mail.google.com" in current_url and "authuser=" in current_url:
                    # Tentar extrair o email da URL
                    import re
                    email_match = re.search(r"authuser=([^&]+)", current_url)
                    if email_match:
                        email = email_match.group(1)
                        if "@" in email:
                            logger.info(
                                f"[OK] Email real encontrado na URL: {email}")
                            return email
            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao tentar obter email da URL: {str(e)}")

            # Método 3: Verificar no código fonte da página
            try:
                page_source = self.driver.page_source
                import re
                # Procurar padrões de email no código fonte
                email_patterns = [
                    r'([a-zA-Z0-9_.+-]+@gmail\.com)',
                    r'email:"([^"]+@gmail\.com)"',
                    r'user:"([^"]+@gmail\.com)"'
                ]

                for pattern in email_patterns:
                    matches = re.findall(pattern, page_source)
                    if matches:
                        for match in matches:
                            if "@gmail.com" in match:
                                logger.info(
                                    f"[OK] Email real encontrado no código fonte: {match}")
                                return match
            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao tentar obter email do código fonte: {str(e)}")

            logger.warning(
                "[AVISO] Não foi possível obter o email real da página")
            return None

        except Exception as e:
            logger.error(f"[ERRO] Erro ao tentar obter o email real: {str(e)}")
            return None

    def _ensure_credentials_saved(self, account_data):
        """
        Garante que as credenciais sejam salvas corretamente no arquivo JSON.

        Args:
            account_data: Dados da conta a serem salvos
        """
        try:
            import json
            import os
            from datetime import datetime

            # Caminho para o arquivo de credenciais
            credentials_path = "credentials/gmail.json"

            # Garantir que o diretório existe
            os.makedirs(os.path.dirname(credentials_path), exist_ok=True)

            # Verificar se o arquivo existe e tem conteúdo válido
            existing_accounts = []
            if os.path.exists(credentials_path) and os.path.getsize(credentials_path) > 0:
                try:
                    with open(credentials_path, "r") as file:
                        content = file.read().strip()
                        if content:
                            existing_accounts = json.loads(content)

                            # Verificar se é uma lista
                            if not isinstance(existing_accounts, list):
                                logger.warning(
                                    "[AVISO] Arquivo de credenciais não contém uma lista válida. Recriando.")
                                existing_accounts = []
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro ao ler arquivo de credenciais: {str(e)}. Recriando.")
                    existing_accounts = []

            # Verificar se a conta já existe no arquivo
            email = account_data.get("email")
            account_exists = False

            for i, account in enumerate(existing_accounts):
                if account.get("email") == email:
                    account_exists = True
                    # Atualizar a conta existente com os novos dados
                    existing_accounts[i] = account_data
                    logger.info(
                        f"[OK] Conta {email} atualizada no arquivo de credenciais")
                    break

            # Se a conta não existe, adicionar
            if not account_exists:
                # Garantir que temos uma data de criação
                if "creation_date" not in account_data:
                    account_data["creation_date"] = datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S")

                existing_accounts.append(account_data)
                logger.info(
                    f"[OK] Conta {email} adicionada ao arquivo de credenciais")

            # Salvar o arquivo atualizado
            with open(credentials_path, "w") as file:
                json.dump(existing_accounts, file, indent=4)

            logger.info(
                f"[OK] Arquivo de credenciais salvo com sucesso: {credentials_path}")

            # Verificar se o arquivo foi salvo corretamente
            if os.path.exists(credentials_path) and os.path.getsize(credentials_path) > 0:
                logger.info(
                    f"[OK] Verificação: arquivo de credenciais existe e tem conteúdo")
            else:
                logger.error(
                    f"[ERRO] Verificação: problema ao salvar arquivo de credenciais")

        except Exception as e:
            logger.error(f"[ERRO] Falha ao salvar credenciais: {str(e)}")

    def _clean_credentials_file(self):
        """
        Verifica e limpa o arquivo de credenciais JSON, removendo entradas inválidas ou duplicadas.
        """
        try:
            import json
            import os
            from datetime import datetime

            logger.info(
                "[INICIO] Verificando e limpando arquivo de credenciais...")

            # Caminho para o arquivo de credenciais
            credentials_path = "credentials/gmail.json"

            # Verificar se o arquivo existe
            if not os.path.exists(credentials_path):
                logger.info(
                    "[INFO] Arquivo de credenciais não existe. Criando diretório...")
                os.makedirs(os.path.dirname(credentials_path), exist_ok=True)
                # Criar arquivo vazio com lista vazia
                with open(credentials_path, "w") as file:
                    json.dump([], file, indent=4)
                logger.info(
                    "[OK] Arquivo de credenciais criado com lista vazia")
                return True

            # Verificar se o arquivo está vazio
            if os.path.getsize(credentials_path) == 0:
                logger.warning(
                    "[AVISO] Arquivo de credenciais está vazio. Inicializando com lista vazia.")
                with open(credentials_path, "w") as file:
                    json.dump([], file, indent=4)
                logger.info(
                    "[OK] Arquivo de credenciais inicializado com lista vazia")
                return True

            # Ler o arquivo de credenciais
            try:
                with open(credentials_path, "r") as file:
                    content = file.read().strip()
                    if not content:
                        logger.warning(
                            "[AVISO] Arquivo de credenciais tem conteúdo vazio. Inicializando com lista vazia.")
                        with open(credentials_path, "w") as f:
                            json.dump([], f, indent=4)
                        return True

                    try:
                        accounts = json.loads(content)
                    except json.JSONDecodeError as e:
                        logger.error(
                            f"[ERRO] Arquivo de credenciais contém JSON inválido: {str(e)}. Recriando arquivo.")
                        with open(credentials_path, "w") as f:
                            json.dump([], f, indent=4)
                        return True

                    # Verificar se é uma lista
                    if not isinstance(accounts, list):
                        logger.warning(
                            "[AVISO] Arquivo de credenciais não contém uma lista. Recriando arquivo.")
                        with open(credentials_path, "w") as f:
                            json.dump([], f, indent=4)
                        return True

                    # Verificar e limpar entradas inválidas ou duplicadas
                    valid_accounts = []
                    email_set = set()

                    for account in accounts:
                        # Verificar se é um dicionário
                        if not isinstance(account, dict):
                            logger.warning(
                                f"[AVISO] Entrada inválida encontrada (não é um dicionário): {account}")
                            continue

                        # Verificar se tem email
                        email = account.get("email")
                        if not email or not isinstance(email, str) or "@" not in email:
                            logger.warning(
                                f"[AVISO] Conta sem email válido encontrada: {account}")
                            continue

                        # Verificar se é duplicado
                        if email in email_set:
                            logger.warning(
                                f"[AVISO] Email duplicado encontrado: {email}")
                            continue

                        # Adicionar à lista de contas válidas
                        email_set.add(email)
                        valid_accounts.append(account)

                    # Salvar arquivo limpo
                    if len(valid_accounts) != len(accounts):
                        logger.info(
                            f"[INFO] Removidas {len(accounts) - len(valid_accounts)} entradas inválidas ou duplicadas")
                        with open(credentials_path, "w") as file:
                            json.dump(valid_accounts, file, indent=4)
                        logger.info(
                            "[OK] Arquivo de credenciais limpo e salvo")

                    logger.info(
                        f"[OK] Verificação concluída. Arquivo contém {len(valid_accounts)} contas válidas")
                    return True

            except Exception as e:
                logger.error(
                    f"[ERRO] Erro ao verificar arquivo de credenciais: {str(e)}")
                # Em caso de erro, tentar recriar o arquivo
                try:
                    with open(credentials_path, "w") as file:
                        json.dump([], file, indent=4)
                    logger.info(
                        "[OK] Arquivo de credenciais recriado após erro")
                    return True
                except Exception as e2:
                    logger.error(
                        f"[ERRO] Falha ao recriar arquivo de credenciais: {str(e2)}")
                    return False

        except Exception as e:
            logger.error(
                f"[ERRO] Falha ao limpar arquivo de credenciais: {str(e)}")
            return False

    def _save_credentials(self, account_data):
        """
        Salva as credenciais no arquivo JSON.

        Args:
            account_data: Dados da conta a serem salvos
        """
        try:
            import json
            import os
            from datetime import datetime

            # Caminho para o arquivo de credenciais
            credentials_path = "credentials/gmail.json"

            # Garantir que o diretório existe
            os.makedirs(os.path.dirname(credentials_path), exist_ok=True)

            # Verificar se o arquivo existe e tem conteúdo válido
            existing_accounts = []
            if os.path.exists(credentials_path) and os.path.getsize(credentials_path) > 0:
                try:
                    with open(credentials_path, "r") as file:
                        content = file.read().strip()
                        if content:
                            existing_accounts = json.loads(content)

                            # Verificar se é uma lista
                            if not isinstance(existing_accounts, list):
                                logger.warning(
                                    "[AVISO] Arquivo de credenciais não contém uma lista válida. Recriando.")
                                existing_accounts = []
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro ao ler arquivo de credenciais: {str(e)}. Recriando.")
                    existing_accounts = []

            # Verificar se a conta já existe no arquivo
            email = account_data.get("email")
            account_exists = False

            for i, account in enumerate(existing_accounts):
                if account.get("email") == email:
                    account_exists = True
                    # Atualizar a conta existente com os novos dados
                    existing_accounts[i] = account_data
                    logger.info(
                        f"[OK] Conta {email} atualizada no arquivo de credenciais")
                    break

            # Se a conta não existe, adicionar
            if not account_exists:
                # Garantir que temos uma data de criação
                if "created_at" not in account_data:
                    account_data["created_at"] = datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S")

                existing_accounts.append(account_data)
                logger.info(
                    f"[OK] Conta {email} adicionada ao arquivo de credenciais")

            # Salvar o arquivo atualizado
            with open(credentials_path, "w") as file:
                json.dump(existing_accounts, file, indent=4)

            logger.info(
                f"[OK] Arquivo de credenciais salvo com sucesso: {credentials_path}")

            # Verificar se o arquivo foi salvo corretamente
            if os.path.exists(credentials_path) and os.path.getsize(credentials_path) > 0:
                logger.info(
                    f"[OK] Verificação: arquivo de credenciais existe e tem conteúdo")
            else:
                logger.error(
                    f"[ERRO] Verificação: problema ao salvar arquivo de credenciais")

        except Exception as e:
            logger.error(f"[ERRO] Falha ao salvar credenciais: {str(e)}")
