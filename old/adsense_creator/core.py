import time
import logging
from enum import Enum
import functools
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.common.exceptions import (
    TimeoutException,
    ElementNotInteractableException,
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException
)

from powerads_api.browser_manager import BrowserManager
from .account_setup import AccountSetup
from .code_site import WebsiteCodeInjector
from .exceptions import AdSenseCreationError
from .config import timeouts, account_config, log_config

logger = logging.getLogger(__name__)

# Decorator para retry de funções


def retry_on_exception(max_attempts=3, delay=2, backoff=2, exceptions=(Exception,)):
    """
    Decorator para tentar executar uma função várias vezes em caso de exceção.

    Args:
        max_attempts: Número máximo de tentativas
        delay: Tempo de espera inicial entre tentativas (segundos)
        backoff: Fator multiplicador para o tempo de espera entre tentativas
        exceptions: Tuple de exceções que devem ser capturadas para retry

    Returns:
        O resultado da função se bem-sucedida
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            mtries, mdelay = max_attempts, delay
            last_exception = None

            while mtries > 0:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    mtries -= 1
                    if mtries == 0:
                        logger.error(
                            f"[ERRO] Todas as {max_attempts} tentativas falharam na função {func.__name__}: {str(e)}")
                        raise

                    logger.warning(
                        f"[AVISO] Tentativa {max_attempts - mtries + 1}/{max_attempts} falhou na função {func.__name__}: {str(e)}. Tentando novamente em {mdelay}s...")
                    time.sleep(mdelay)
                    mdelay *= backoff  # Aumentar o tempo de espera para a próxima tentativa

            return None  # Nunca deve chegar aqui
        return wrapper
    return decorator


class AdSenseCreationState(Enum):
    """Estados possíveis durante a criação da conta do AdSense."""
    INITIAL = "initial"
    ACCOUNT_SETUP = "account_setup"
    WEBSITE_VERIFICATION = "website_verification"
    CODE_CAPTURE = "code_capture"
    PAYMENT_SETUP = "payment_setup"
    REVIEW_WAITING = "review_waiting"
    COMPLETED = "completed"
    FAILED = "failed"


class AdSenseCreator:
    """Classe principal que gerencia o fluxo de criação da conta AdSense."""

    def __init__(self, browser_manager, account_data, profile_name="default_profile"):
        self.browser_manager = browser_manager
        self.account_data = account_data
        self.profile_name = profile_name if profile_name else "default_profile"
        self.driver = None

        # Configuração geral
        self.config = {
            "timeouts": timeouts,
            "account_config": account_config,
            "log_config": log_config
        }

        self.state = AdSenseCreationState.INITIAL
        self.selenium_exceptions = (
            TimeoutException,
            ElementNotInteractableException,
            NoSuchElementException,
            StaleElementReferenceException,
            WebDriverException
        )

    @retry_on_exception(max_attempts=3, delay=3, exceptions=(WebDriverException,))
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
                logger.error(
                    "[ERRO] Falha ao garantir que o browser está pronto")
                return False

            self.driver = self.browser_manager.get_driver()
            if not self.driver:
                logger.error("[ERRO] Driver não disponível")
                return False

            self.wait = WebDriverWait(self.driver, timeouts.DEFAULT_WAIT)
            logger.info("[OK] Browser inicializado com sucesso")

            # Configurar o tamanho da janela para melhor visualização
            try:
                self.driver.set_window_size(1366, 768)
                logger.info(
                    "[INFO] Tamanho da janela configurado para 1366x768")
            except Exception as e:
                logger.warning(
                    f"[AVISO] Não foi possível configurar o tamanho da janela: {str(e)}")

            return True

        except Exception as e:
            logger.error(f"[ERRO] Erro ao inicializar browser: {str(e)}")
            return False

    def create_account(self, user_id: str):
        """
        Executa todo o fluxo de criação da conta AdSense.

        Args:
            user_id: ID do perfil do AdsPower

        Returns:
            tuple: (sucesso, dados_da_conta)
        """
        try:
            logger.info("[INICIO] Iniciando criação da conta AdSense...")

            # Verificar e limpar o arquivo de credenciais
            self._clean_credentials_file()

            # Inicializar o browser primeiro
            if not self.initialize_browser(user_id):
                raise AdSenseCreationError(
                    "[ERRO] Falha ao inicializar o browser")

            # Contador para tentativas de criação completa da conta
            complete_attempts = 0
            max_complete_attempts = 2

            while complete_attempts < max_complete_attempts:
                complete_attempts += 1
                logger.info(
                    f"[ATUALIZANDO] Tentativa {complete_attempts} de {max_complete_attempts} para criar conta completa")

                try:
                    # Passo 1: Configuração inicial da conta
                    self.state = AdSenseCreationState.ACCOUNT_SETUP
                    account_setup = AccountSetup(
                        self.driver, self.account_data)
                    if not account_setup.start_setup():
                        raise AdSenseCreationError(
                            "[ERRO] Falha na configuração inicial da conta AdSense.")

                    # Passo 2: Capturar códigos de verificação (publisher ID e código ads.txt)
                    if self.account_data.get("capture_codes", True):
                        self.state = AdSenseCreationState.CODE_CAPTURE
                        code_injector = WebsiteCodeInjector(
                            self.driver, self.account_data)
                        if code_injector.capture_verification_code():
                            # Atualizar os dados da conta com os códigos capturados
                            captured_data = code_injector.get_captured_data()
                            self.account_data.update(captured_data)
                            logger.info(
                                "[OK] Códigos de verificação capturados com sucesso")
                        else:
                            logger.warning(
                                "[AVISO] Falha ao capturar códigos de verificação, continuando mesmo assim")

                    # Passo 3: Verificação do website (se necessário)
                    if self.account_data.get("verify_website", False):
                        self.state = AdSenseCreationState.WEBSITE_VERIFICATION
                        # Implementar lógica de verificação de website aqui
                        logger.info(
                            "[INFO] Verificação do website não implementada ainda")
                        pass

                    # Passo 4: Configuração de pagamento (opcional)
                    if self.account_data.get("setup_payment", False):
                        self.state = AdSenseCreationState.PAYMENT_SETUP
                        # Implementar lógica de configuração de pagamento aqui
                        logger.info(
                            "[INFO] Configuração de pagamento não implementada ainda")
                        pass

                    # Passo 5: Aguardar revisão (opcional)
                    if self.account_data.get("wait_for_review", False):
                        self.state = AdSenseCreationState.REVIEW_WAITING
                        # Implementar lógica de espera pela revisão (ou simplesmente logar o status)
                        logger.info(
                            "[INFO] Conta AdSense criada e aguardando revisão.")

                    # Se chegou aqui, tudo deu certo!
                    self.state = AdSenseCreationState.COMPLETED

                    # Retornar os dados da conta AdSense, incluindo informações relevantes
                    adsense_account_data = {
                        "email": self.account_data.get("email"),
                        "website": self.account_data.get("website_url"),
                        "publisher_id": self.account_data.get("publisher_id", ""),
                        "verification_code": self.account_data.get("verification_code", ""),
                        "status": "review_pending",  # Ou outro status relevante
                        "creation_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "profile": self.profile_name
                    }

                    logger.info(
                        f"[OK] Conta AdSense criada com sucesso! Retornando os dados: {adsense_account_data}")
                    return True, adsense_account_data

                except Exception as inner_e:
                    logger.error(
                        f"[ERRO] Erro na tentativa {complete_attempts}: {str(inner_e)}")
                    if complete_attempts >= max_complete_attempts:
                        logger.error(
                            "[ERRO] Todas as tentativas de criação falharam.")
                        raise AdSenseCreationError(
                            f"Falha nas tentativas de criação da conta: {str(inner_e)}")

                    # Pequeno delay antes de tentar novamente
                    time.sleep(5)
                    self.driver.refresh()
                    time.sleep(3)

        except Exception as e:
            self.state = AdSenseCreationState.FAILED
            logger.error(f"[ERRO] Falha na criação da conta AdSense: {str(e)}")
            return False, {"error": str(e)}

        finally:
            # Opcional: fechar o navegador ao finalizar (ou deixar aberto para inspeção)
            # Definindo como False para manter o navegador aberto conforme solicitado
            if self.account_data.get("close_browser_on_finish", False) and self.driver:
                try:
                    self.browser_manager.close_browser()
                    logger.info("[OK] Navegador fechado com sucesso")
                except Exception as close_e:
                    logger.warning(
                        f"[AVISO] Erro ao fechar navegador: {str(close_e)}")

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
