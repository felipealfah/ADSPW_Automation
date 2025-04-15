import time
import logging
from enum import Enum
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.webdriver import WebDriver

from powerads_api.browser_manager import BrowserManager
from .account_setup import AccountSetup
from .phone_verify import PhoneVerification
from .terms_handler import TermsHandler
from .account_verify import AccountVerify
from .exceptions import GmailCreationError
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

    def __init__(self, browser_manager, credentials, sms_api, profile_name="default_profile"):
        self.browser_manager = browser_manager
        self.credentials = credentials
        self.sms_api = sms_api
        self.profile_name = profile_name if profile_name else "default_profile"
        self.driver = None

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
            if not self.browser_manager.ensure_browser_ready(user_id):
                logger.error("❌ Falha ao garantir que o browser está pronto")
                return False

            self.driver = self.browser_manager.get_driver()
            if not self.driver:
                logger.error("❌ Driver não disponível")
                return False

            self.wait = WebDriverWait(self.driver, timeouts.DEFAULT_WAIT)
            logger.info("✅ Browser inicializado com sucesso")
            return True

        except Exception as e:
            logger.error(f"❌ Erro ao inicializar browser: {str(e)}")
            return False

    def create_account(self, user_id: str, phone_params=None):
        """
        Executa todo o fluxo de criação da conta Gmail.

        Args:
            user_id: ID do perfil do AdsPower
            phone_params (dict, optional): Parâmetros para reutilização de números

        Returns:
            tuple: (sucesso, dados_da_conta)
        """
        try:
            logger.info("🚀 Iniciando criação da conta Gmail...")

            # Inicializar o browser primeiro
            if not self.initialize_browser(user_id):
                raise GmailCreationError("❌ Falha ao inicializar o browser")

            # Contador para tentativas de criação completa da conta
            complete_attempts = 0
            max_complete_attempts = 2

            while complete_attempts < max_complete_attempts:
                complete_attempts += 1
                logger.info(
                    f"🔄 Tentativa {complete_attempts} de {max_complete_attempts} para criar conta completa")

                try:
                    # Passo 1: Configuração inicial da conta
                    self.state = GmailCreationState.ACCOUNT_SETUP
                    account_setup = AccountSetup(self.driver, self.credentials)
                    if not account_setup.start_setup():
                        raise GmailCreationError(
                            "❌ Falha na configuração inicial da conta.")

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
                            "📞 Tela de verificação de telefone detectada.")
                        # Se temos parâmetros de telefone para reutilização
                        if phone_params and isinstance(phone_params, dict) and phone_params.get('reuse_number'):
                            logger.info(
                                f"♻️ Configurando reutilização de número: {phone_params.get('phone_number')}")
                            phone_verify.reuse_number = True
                            phone_verify.predefined_number = phone_params.get(
                                'phone_number')
                            phone_verify.predefined_activation_id = phone_params.get(
                                'activation_id')
                            phone_verify.predefined_country_code = phone_params.get(
                                'country_code')

                        # Esta chamada inclui todo o processo de verificação por SMS
                        # Usar execute_with_retry para maior robustez
                        def verify_phone():
                            return phone_verify.handle_verification()

                        phone_verification_success = self.phone_manager.execute_with_retry(
                            verify_phone, max_retries=2, retry_delay=3)

                        if not phone_verification_success:
                            logger.warning(
                                "⚠️ Falha na verificação de telefone. Tentando reiniciar processo...")
                            # Recarregar a página de início e tentar novamente em uma nova iteração
                            self.driver.get(
                                "https://accounts.google.com/signup")
                            time.sleep(5)
                            continue  # Reinicia o processo completo

                        # Captura os dados do telefone verificado
                        phone_data = phone_verify.get_current_phone_data()
                        if not phone_data:
                            logger.error(
                                "❌ Falha ao obter dados do telefone após verificação")
                            continue  # Tenta novamente o processo completo
                    else:
                        logger.info(
                            "📞 Tela de verificação de telefone não detectada, pulando para aceitação dos termos.")
                        # Se não houver verificação de telefone, definimos valores padrão
                        phone_data = {
                            'phone_number': phone_params.get('phone_number') if phone_params else None,
                            'country_code': phone_params.get('country_code') if phone_params else None,
                            'activation_id': phone_params.get('activation_id') if phone_params else None,
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
                    # Inicializar terms_handler
                    terms_handler = TermsHandler(self.driver)

                    # Usar execute_with_retry para maior robustez
                    def accept_terms():
                        return terms_handler.handle_terms_acceptance()

                    terms_accepted = self.phone_manager.execute_with_retry(
                        accept_terms, max_retries=2, retry_delay=2)

                    if not terms_accepted:
                        logger.warning(
                            "⚠️ Falha na aceitação dos termos. Tentando reiniciar processo...")
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
                            "⚠️ Falha na verificação final da conta. Tentando reiniciar processo...")
                        # Recarregar a página de início e tentar novamente
                        self.driver.get("https://accounts.google.com/signup")
                        time.sleep(5)
                        continue  # Reinicia o processo completo

                    # Se chegou aqui, tudo deu certo!
                    self.state = GmailCreationState.COMPLETED

                    # 🔹 Retornar os dados completos da conta
                    account_data = {
                        "first_name": self.credentials["first_name"],
                        "last_name": self.credentials["last_name"],
                        "email": self.credentials["username"] + "@gmail.com",
                        "password": self.credentials["password"],
                        "phone": phone_number,
                        "country_code": country_code,
                        "country_name": country_name,
                        "activation_id": activation_id,
                        "profile": self.profile_name
                    }

                    logger.info(
                        f"✅ Conta criada com sucesso! Retornando os dados: {account_data}")
                    return True, account_data

                except Exception as inner_e:
                    logger.error(
                        f"❌ Erro durante a tentativa {complete_attempts}: {str(inner_e)}")
                    if complete_attempts < max_complete_attempts:
                        logger.info("🔄 Reiniciando processo completo...")
                        self.driver.get("https://accounts.google.com/signup")
                        time.sleep(5)
                    else:
                        logger.error(
                            f"❌ Todas as {max_complete_attempts} tentativas completas falharam")
                        raise GmailCreationError(
                            f"Falha após {max_complete_attempts} tentativas completas")

            # Se chegou aqui, todas as tentativas falharam
            return False, None

        except GmailCreationError as e:
            logger.error(f"🚨 Erro durante o processo: {str(e)}")
            return False, None

        except Exception as e:
            logger.error(f"❌ Erro inesperado: {str(e)}")
            return False, None
