from enum import Enum
from dataclasses import dataclass
from typing import Optional
import time
import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from .exceptions import (
    AccountSetupError,
    UsernameError,
    ElementInteractionError,
    NavigationError
)
from .config import timeouts, account_config
from .locators import account_locators, username_locators, password_locators

logger = logging.getLogger(__name__)

# Configuração para habilitar/desabilitar modo de debug com screenshots
DEBUG_MODE = True  # Habilitado para capturar screenshots e diagnosticar problemas


class SetupState(Enum):
    """Estados possíveis da configuração da conta."""
    INITIAL = "initial"
    NAVIGATING = "navigating"
    BASIC_INFO = "basic_info"
    USERNAME_SETUP = "username_setup"
    PASSWORD_SETUP = "password_setup"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AccountInfo:
    """Armazena informações da conta durante o setup."""
    username: str
    password: str
    first_name: str
    last_name: str
    birth_month: str
    birth_day: int
    birth_year: int
    attempts: int = 0
    state: SetupState = SetupState.INITIAL


class AccountSetup:
    """
    Gerencia o processo de configuração inicial da conta Gmail.
    Responsável por preencher informações básicas, username e senha.
    """

    def __init__(self, driver, credentials):
        self.driver = driver
        self.credentials = credentials
        self.wait = WebDriverWait(driver, timeouts.DEFAULT_WAIT)
        self.state = SetupState.INITIAL
        self.account_info = self._create_account_info()
        self.max_retries = 3
        self.retry_delay = 2

    def _create_account_info(self) -> AccountInfo:
        """Cria objeto AccountInfo com as credenciais fornecidas."""
        return AccountInfo(
            username=self.credentials["username"],
            password=self.credentials["password"],
            first_name=self.credentials["first_name"],
            last_name=self.credentials["last_name"],
            birth_month=self.credentials["birth_month"],
            birth_day=self.credentials["birth_day"],
            birth_year=self.credentials["birth_year"]
        )

    def start_setup(self):
        """Inicia o processo de configuração da conta."""
        try:
            logger.info("[INICIO] Iniciando configuração da conta Gmail...")
            
            # Salvar screenshot do estado inicial
            self._save_screenshot("estado_inicial_pagina")
            logger.info(f"[DIAGNÓSTICO] URL inicial: {self.driver.current_url}")

            # Definir sequência de etapas
            setup_steps = [
                (self._fill_basic_info, "informações básicas"),
                (self._fill_birth_and_gender, "data de nascimento e gênero"),
                (self._handle_username_setup, "configuração de username"),
                (self._setup_password, "configuração de senha")
            ]

            # Executar cada etapa em sequência
            for step_func, step_name in setup_steps:
                logger.info(f"[INICIO] Iniciando etapa: {step_name}")
                try:
                    if not step_func():
                        logger.error(f"[ERRO] Falha na etapa: {step_name}")
                        return False
                    logger.info(f"[OK] Etapa concluída com sucesso: {step_name}")
                    
                    # Aguardar um momento entre as etapas
                    time.sleep(2)
                    
                    # Verificar estado atual
                    current_screen = self._check_current_screen()
                    logger.info(f"[DIAGNÓSTICO] Tela atual após {step_name}: {current_screen}")
                    
                    # Salvar screenshot após cada etapa
                    self._save_screenshot(f"apos_{step_name.replace(' ', '_')}")
                except Exception as step_error:
                    logger.error(f"[ERRO] Exceção na etapa {step_name}: {str(step_error)}")
                    return False

            # Verificação final
            final_screen = self._check_current_screen()
            logger.info(f"[DIAGNÓSTICO] Tela final após todas as etapas: {final_screen}")
            
            if final_screen == "unknown_screen":
                # Verificar se estamos em alguma das telas esperadas
                expected_elements = [
                    "//div[contains(text(), 'Verify your phone number')]",
                    "//div[contains(text(), 'Verifique seu número de telefone')]",
                    "//div[contains(text(), 'Add recovery email')]",
                    "//div[contains(text(), 'Adicionar e-mail de recuperação')]"
                ]
                
                for element in expected_elements:
                    try:
                        if self.wait.until(EC.presence_of_element_located((By.XPATH, element))):
                            logger.info("[OK] Setup completo, encontrada tela esperada")
                            return True
                    except:
                        continue
                
                logger.warning("[AVISO] Tela final não identificada, mas continuando...")
            
            logger.info("[OK] Setup completo com sucesso")
            return True

        except Exception as e:
            logger.error(f"[ERRO] Falha ao executar setup: {str(e)}")
            self._save_screenshot("erro_setup")
            return False

    def _fill_basic_info(self):
        """
        Preenche as informações básicas (nome e sobrenome).
        """
        try:
            logger.info("[INICIO] Preenchendo informações básicas...")

            # Preencher primeiro nome
            first_name_field = self.wait.until(
                EC.presence_of_element_located((By.NAME, "firstName"))
            )
            first_name_field.clear()
            first_name_field.send_keys(self.credentials["first_name"])
            logger.info(f"[OK] Nome preenchido: {self.credentials['first_name']}")

            # Preencher sobrenome
            last_name_field = self.wait.until(
                EC.presence_of_element_located((By.NAME, "lastName"))
            )
            last_name_field.clear()
            last_name_field.send_keys(self.credentials["last_name"])
            logger.info(f"[OK] Sobrenome preenchido: {self.credentials['last_name']}")

            # Tentar clicar no botão Next/Avançar/Próximo com diferentes abordagens
            logger.info("[INICIO] Tentando clicar no botão Next/Avançar...")
            
            # Lista de possíveis XPaths para o botão
            next_button_xpaths = [
                "//span[text()='Next' or text()='Avançar' or text()='Próximo']",
                "//button[contains(@class, 'VfPpkd-LgbsSe')]//span[text()='Next' or text()='Avançar' or text()='Próximo']",
                "//*[@jsname='LgbsSe']//span[contains(@class, 'VfPpkd-vQzf8d')]",
                "//button[@type='button']//span[text()='Next' or text()='Avançar' or text()='Próximo']"
            ]

            clicked = False
            for xpath in next_button_xpaths:
                try:
                    # Primeiro, tentar clicar usando Selenium padrão
                    next_button = self.wait.until(
                        EC.element_to_be_clickable((By.XPATH, xpath))
                    )
                    try:
                        next_button.click()
                        clicked = True
                        logger.info(f"[OK] Botão clicado com sucesso usando XPath: {xpath}")
                        break
                    except Exception as click_error:
                        logger.info(f"[AVISO] Clique padrão falhou, tentando JavaScript para XPath: {xpath}")
                        try:
                            # Tentar via JavaScript
                            self.driver.execute_script("arguments[0].click();", next_button)
                            clicked = True
                            logger.info("[OK] Botão clicado com sucesso via JavaScript")
                            break
                        except Exception as js_error:
                            logger.warning(f"[AVISO] Clique via JavaScript também falhou: {str(js_error)}")
                            continue
                except Exception as e:
                    logger.warning(f"[AVISO] Não foi possível encontrar/clicar no botão com XPath {xpath}: {str(e)}")
                    continue

            if not clicked:
                # Última tentativa: tentar clicar diretamente no botão pelo XPath completo
                try:
                    full_xpath = "/html/body/div[1]/div[1]/div[2]/c-wiz/div/div[3]/div/div/div/div/button"
                    next_button = self.wait.until(
                        EC.presence_of_element_located((By.XPATH, full_xpath))
                    )
                    self.driver.execute_script("arguments[0].click();", next_button)
                    clicked = True
                    logger.info("[OK] Botão clicado com sucesso usando XPath completo via JavaScript")
                except Exception as final_error:
                    logger.error(f"[ERRO] Todas as tentativas de clicar no botão falharam: {str(final_error)}")
                    return False

            # Aguardar transição de página
            time.sleep(2)
            
            if clicked:
                logger.info("[OK] Informações básicas preenchidas e botão Next clicado com sucesso")
                return True
            else:
                logger.error("[ERRO] Não foi possível clicar no botão Next após várias tentativas")
                return False

        except Exception as e:
            logger.error(f"[ERRO] Falha ao preencher informações básicas: {str(e)}")
            return False

    def _check_if_already_on_name_screen(self) -> bool:
        """Verifica se já estamos na tela que pede nome e sobrenome."""
        try:
            # Capturar screenshot da tela inicial para diagnóstico
            self._save_screenshot("tela_inicial_verificacao")

            # Registrar URL atual para diagnóstico
            current_url = self.driver.current_url
            logger.info(f"[DIAGNÓSTICO] URL atual ao verificar tela: {current_url}")

            # Verificar elementos específicos da tela de nome/sobrenome
            name_elements = [
                (By.ID, account_locators.FIRST_NAME),
                (By.ID, account_locators.LAST_NAME),
                (By.XPATH, "//span[contains(text(), 'First name')]"),
                (By.XPATH, "//span[contains(text(), 'Last name')]")
            ]

            for by, locator in name_elements:
                try:
                    if WebDriverWait(self.driver, 3).until(EC.presence_of_element_located((by, locator))):
                        logger.info(f"[OK] Elemento encontrado: {locator}")
                        # Capturar screenshot quando encontrar a tela de nome/sobrenome
                        self._save_screenshot("tela_nome_sobrenome_encontrada")
                        return True
                except TimeoutException:
                    logger.info(f"[BUSCA] Elemento não encontrado: {locator}")
                    continue

            # Se não encontrou os elementos, verificar se há algum texto indicativo
            page_source = self.driver.page_source.lower()
            indicative_texts = ["create your google account", "basic information", "first name", "last name"]
            
            for text in indicative_texts:
                if text in page_source:
                    logger.info(f"[OK] Texto indicativo encontrado: {text}")
                    return True

            # Capturar screenshot quando não encontrar a tela esperada
            self._save_screenshot("tela_nome_sobrenome_nao_encontrada")
            logger.info("[INFO] Nenhum elemento ou texto indicativo da tela de nome/sobrenome encontrado")
            return False

        except Exception as e:
            logger.warning(f"[AVISO] Erro ao verificar tela inicial: {str(e)}")
            # Capturar screenshot em caso de erro
            self._save_screenshot("erro_verificacao_tela_inicial")
            return False

    def _check_and_handle_choose_account_screen(self) -> bool:
        """Verifica se estamos na tela 'Choose an account' e clica em 'Use another account' se necessário."""
        try:
            # Verificar se a tela "Choose an account" está presente
            choose_account_present = False
            try:
                choose_account_element = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located(
                        (By.XPATH, account_locators.CHOOSE_ACCOUNT_SCREEN))
                )
                choose_account_present = True
                logger.info("[BUSCA] Tela 'Choose an account' detectada.")
            except TimeoutException:
                logger.info(
                    " Tela 'Choose an account' não detectada, seguindo fluxo normal.")
                return False

            if not choose_account_present:
                return False

            # Tentar localizar e clicar no botão "Use another account"
            try:
                # Tentar com o XPath completo primeiro
                use_another_button = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, account_locators.USE_ANOTHER_ACCOUNT_BUTTON))
                )
                use_another_button.click()
                logger.info(
                    "[OK] Clicado em 'Use another account' com XPath completo.")
                time.sleep(2)  # Aguardar carregamento da próxima tela
                return True
            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao clicar com XPath completo: {str(e)}")

                # Tentar com alternativa mais robusta
                try:
                    use_another_button_alt = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable(
                            (By.XPATH, account_locators.USE_ANOTHER_ACCOUNT_ALT))
                    )
                    use_another_button_alt.click()
                    logger.info(
                        "[OK] Clicado em 'Use another account' com XPath alternativo.")
                    time.sleep(2)  # Aguardar carregamento da próxima tela
                    return True
                except Exception as e2:
                    logger.error(
                        f"[ERRO] Não foi possível clicar em 'Use another account': {str(e2)}")

                    # Tentar uma abordagem JavaScript como último recurso
                    try:
                        self.driver.execute_script(
                            f"document.evaluate('{account_locators.USE_ANOTHER_ACCOUNT_BUTTON}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue.click();")
                        logger.info(
                            "[OK] Clicado em 'Use another account' usando JavaScript.")
                        time.sleep(2)
                        return True
                    except Exception as e3:
                        logger.error(
                            f"[ERRO] Todas as tentativas de clicar em 'Use another account' falharam: {str(e3)}")
                        return False

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao verificar tela 'Choose an account': {str(e)}")
            return False

    def _element_exists(self, by, locator, timeout=3):
        """Verifica se um elemento existe na página dentro de um tempo limite."""
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, locator)))
            return True
        except TimeoutException:
            return False

    def _execute_with_retry(self, func) -> bool:
        """Executa uma função com sistema de retry."""
        for attempt in range(self.max_retries):
            try:
                func()
                return True
            except Exception as e:
                logger.warning(
                    f"[AVISO] Tentativa {attempt + 1} falhou: {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    continue
                return False

    def _navigate_to_signup(self):
        """Navega para a página de signup do Gmail."""
        try:
            logger.info("[NAVEGAÇÃO] Verificando página atual...")
            current_url = self.driver.current_url
            logger.info(f"[DIAGNÓSTICO] URL atual: {current_url}")

            # Se já estiver na página de signup, não precisa navegar
            if "accounts.google.com/signup" in current_url:
                logger.info("[OK] Já estamos na página de signup")
                return True

            # Se não estiver, navegar para a página de signup
            logger.info("[NAVEGAÇÃO] Redirecionando para página de signup...")
            self.driver.get("https://accounts.google.com/signup/v2/createaccount?service=mail&continue=https://mail.google.com/mail/&flowName=GlifWebSignIn&flowEntry=SignUp")
            time.sleep(3)  # Aguardar carregamento inicial

            # Verificar se chegamos à página correta
            if not "accounts.google.com/signup" in self.driver.current_url:
                logger.error("[ERRO] Falha ao navegar para página de signup")
                return False

            logger.info("[OK] Navegação para página de signup concluída")
            return True

        except Exception as e:
            logger.error(f"[ERRO] Erro durante navegação: {str(e)}")
            return False

    def _wait_for_page_load(self, timeout=10):
        """Aguarda o carregamento completo da página."""
        try:
            self.wait.until(
                lambda driver: driver.execute_script(
                    "return document.readyState") == "complete"
            )
        except TimeoutException:
            logger.warning("[AVISO] Timeout aguardando carregamento da página")

    def _select_personal_account(self):
        """Seleciona a opção de conta pessoal."""
        try:
            logger.info(" Selecionando conta pessoal...")

            # Tenta clicar no primeiro botão com retry
            self._click_element_safely(
                By.XPATH,
                account_locators.FIRST_BUTTON,
                "botão inicial"
            )
            time.sleep(1)

            # Tenta selecionar opção de conta pessoal
            self._click_element_safely(
                By.XPATH,
                account_locators.PERSONAL_USE_OPTION,
                "opção de conta pessoal"
            )

            logger.info("[OK] Conta pessoal selecionada com sucesso")

        except TimeoutException:
            logger.info(
                "[AVISO] Botão de seleção de conta não encontrado, continuando...")
        except Exception as e:
            raise ElementInteractionError(
                "botão de conta pessoal", "clicar", str(e))

    def _remove_readonly_if_exists(self, by, locator):
        """Remove o atributo 'readonly' de um campo, se ele estiver presente."""
        try:
            element = self.driver.find_element(by, locator)
            self.driver.execute_script(
                "arguments[0].removeAttribute('readonly')", element)
        except Exception:
            pass

    def _handle_username_setup(self):
        """
        Configura o username da conta, incluindo tratamento de sugestões e retentativas.
        """
        logger.info("[INICIO] Iniciando configuração de username...")
        
        try:
            # Verificar se estamos na tela correta
            if not self._execute_with_retry(lambda: self._check_current_screen() == "username_screen"):
                logger.error("[ERRO] Não foi possível identificar a tela de username")
                self._save_screenshot("erro_tela_username")
                raise NavigationError("Tela de username não encontrada")

            # Tentar configurar o username
            if not self._execute_with_retry(self._set_username):
                logger.error("[ERRO] Falha ao configurar username")
                self._save_screenshot("erro_configuracao_username")
                raise UsernameError("Falha ao configurar username")

            # Verificar se há sugestões de username
            if self._is_username_suggestion_screen():
                logger.info("[INFO] Detectada tela de sugestões de username")
                if not self._execute_with_retry(self._handle_username_suggestions):
                    logger.error("[ERRO] Falha ao tratar sugestões de username")
                    self._save_screenshot("erro_sugestoes_username")
                    raise UsernameError("Falha ao tratar sugestões de username")

            logger.info("[OK] Username configurado com sucesso")
            return True

        except (NavigationError, UsernameError) as e:
            logger.error(f"[ERRO] {str(e)}")
            self._save_screenshot("erro_handle_username")
            return False
        except Exception as e:
            logger.error(f"[ERRO] Erro inesperado na configuração do username: {str(e)}")
            self._save_screenshot("erro_inesperado_username")
            return False

    def _set_username(self) -> bool:
        """
        Tenta configurar o username com retentativas.
        """
        try:
            logger.info(f"[INICIO] Tentando configurar username: {self.credentials['username']}")
            max_attempts = 3
            
            for attempt in range(max_attempts):
                current_username = self.credentials["username"] if attempt == 0 else self._generate_new_username()
                
                # Aguardar e preencher o campo de username
                username_field = self.wait.until(
                    EC.presence_of_element_located((By.NAME, "Username"))
                )
                username_field.clear()
                username_field.send_keys(current_username)
                logger.info(f"[OK] Campo de username preenchido com: {current_username}")

                # Tentar clicar no botão Next para verificar disponibilidade
                logger.info("[INICIO] Tentando clicar no botão Next para verificar disponibilidade...")
                
                # Lista de possíveis XPaths para o botão
                next_button_xpaths = [
                    "//span[text()='Next' or text()='Avançar' or text()='Próximo']",
                    "//button[contains(@class, 'VfPpkd-LgbsSe')]//span[text()='Next' or text()='Avançar' or text()='Próximo']",
                    "//*[@jsname='LgbsSe']//span[contains(@class, 'VfPpkd-vQzf8d')]",
                    "//button[@type='button']//span[text()='Next' or text()='Avançar' or text()='Próximo']",
                    "//button[contains(@class, 'VfPpkd-LgbsSe')]",
                    "//*[@jsname='LgbsSe']"
                ]

                clicked = False
                for xpath in next_button_xpaths:
                    try:
                        next_button = self.wait.until(
                            EC.element_to_be_clickable((By.XPATH, xpath))
                        )
                        try:
                            next_button.click()
                            clicked = True
                            logger.info(f"[OK] Botão Next clicado com sucesso usando XPath: {xpath}")
                            break
                        except Exception as click_error:
                            logger.info(f"[AVISO] Clique padrão falhou, tentando JavaScript para XPath: {xpath}")
                            try:
                                self.driver.execute_script("arguments[0].click();", next_button)
                                clicked = True
                                logger.info("[OK] Botão Next clicado com sucesso via JavaScript")
                                break
                            except Exception as js_error:
                                logger.warning(f"[AVISO] Clique via JavaScript também falhou: {str(js_error)}")
                                continue
                    except Exception as e:
                        logger.warning(f"[AVISO] Não foi possível encontrar/clicar no botão com XPath {xpath}: {str(e)}")
                        continue

                if not clicked:
                    # Última tentativa: tentar clicar diretamente no botão pelo XPath completo
                    try:
                        full_xpath = "/html/body/div[1]/div[1]/div[2]/div/div[2]/div/div/div[2]/div/div[2]/div/div[1]/div/div/button"
                        next_button = self.wait.until(
                            EC.presence_of_element_located((By.XPATH, full_xpath))
                        )
                        self.driver.execute_script("arguments[0].click();", next_button)
                        clicked = True
                        logger.info("[OK] Botão Next clicado com sucesso usando XPath completo via JavaScript")
                    except Exception as final_error:
                        logger.error(f"[ERRO] Todas as tentativas de clicar no botão Next falharam: {str(final_error)}")
                        if attempt == max_attempts - 1:
                            return False
                        continue

                # Aguardar um momento para verificar disponibilidade
                time.sleep(2)

                # Verificar se o username está disponível
                if self._check_username_taken():
                    logger.warning(f"[AVISO] Username '{current_username}' já está em uso")
                    if attempt == max_attempts - 1:
                        logger.error("[ERRO] Todas as tentativas de username falharam")
                        return False
                    continue
                
                # Username está disponível, verificar se avançamos para a tela de senha
                current_screen = self._check_current_screen()
                if current_screen == "password_screen":
                    logger.info(f"[OK] Username '{current_username}' configurado com sucesso")
                    return True
                else:
                    # Se não avançamos, tentar clicar no botão Next novamente
                    logger.info("[AVISO] Não avançamos para a tela de senha, tentando clicar no Next novamente...")
                    if not clicked:
                        logger.error("[ERRO] Não foi possível clicar no botão Next novamente")
                        if attempt == max_attempts - 1:
                            return False
                        continue

            logger.error("[ERRO] Todas as tentativas de configurar username falharam")
            return False

        except Exception as e:
            logger.error(f"[ERRO] Falha ao configurar username: {str(e)}")
            return False

    def _check_username_taken(self, timeout=3) -> bool:
        """Verifica se o username já está em uso."""
        try:
            error_xpaths = [
                username_locators.USERNAME_TAKEN_ERROR,
                "//div[contains(text(), 'That username is taken')]",
                "//div[contains(text(), 'Este nome de usuário já está em uso')]",
                "//span[contains(text(), 'That username is taken')]",
                "//span[contains(text(), 'Este nome de usuário já está em uso')]"
            ]

            for xpath in error_xpaths:
                try:
                    if WebDriverWait(self.driver, timeout).until(
                        EC.presence_of_element_located((By.XPATH, xpath))
                    ):
                        logger.info("[AVISO] Mensagem de erro detectada: username já está em uso")
                        return True
                except TimeoutException:
                    continue

            page_source = self.driver.page_source.lower()
            if "username is taken" in page_source or "nome de usuário já está em uso" in page_source:
                logger.info("[AVISO] Mensagem de erro detectada no HTML da página")
                return True

            return False

        except Exception as e:
            logger.error(f"[ERRO] Erro ao verificar disponibilidade do username: {str(e)}")
            return False

    def _generate_new_username(self):
        """Gera um novo username quando o atual não está disponível."""
        try:
            original_username = self.account_info.username
            new_username = f"{original_username}{self.account_info.birth_day}"
            logger.info(f"[OK] Gerando username alternativo: {new_username}")
            return new_username

        except Exception as e:
            logger.error(f"[ERRO] Erro ao gerar username alternativo: {str(e)}")
            try:
                import string
                import random
                first = self.account_info.first_name.lower()
                last = self.account_info.last_name.lower()
                year = str(self.account_info.birth_year)
                day = str(self.account_info.birth_day)
                random_part = ''.join(random.choice(string.ascii_lowercase) for _ in range(5))
                new_username = f"{first[:3]}{last[:3]}{random_part}{year[-2:]}{day}"
                logger.info(f"[OK] Gerado username fallback: {new_username}")
                return new_username

            except Exception as fallback_error:
                random_part = ''.join(random.choice(
                    string.ascii_lowercase + string.digits) for _ in range(8))
                random_username = f"user_{random_part}_{random.randint(1900, 2010)}"
                logger.warning(f"[AVISO] Gerado username aleatório: {random_username}")
                return random_username

    def _check_current_screen(self):
        """Detecta em qual tela estamos atualmente."""
        try:
            # Detectar tela de senha
            password_elements = [
                password_locators.PASSWORD_FIELD,
                "//div[contains(text(), 'Create a password')]",
                "//div[contains(text(), 'Criar uma senha')]"
            ]
            for element in password_elements:
                try:
                    if WebDriverWait(self.driver, 1).until(EC.presence_of_element_located((By.XPATH, element))):
                        return "password_screen"
                except:
                    continue

            # Detectar tela de username
            username_elements = [
                username_locators.USERNAME_FIELD,
                "//div[contains(text(), 'Choose your Gmail address')]",
                "//div[contains(text(), 'Escolha seu endereço do Gmail')]"
            ]
            for element in username_elements:
                try:
                    if WebDriverWait(self.driver, 1).until(EC.presence_of_element_located((By.XPATH, element))):
                        return "username_screen"
                except:
                    continue

            # Detectar tela de sugestões de username
            suggestion_elements = [
                username_locators.CREATE_OWN_USERNAME,
                "//div[contains(text(), 'Create your own Gmail address')]",
                "//div[contains(text(), 'Crie seu próprio endereço do Gmail')]"
            ]
            for element in suggestion_elements:
                try:
                    if WebDriverWait(self.driver, 1).until(EC.presence_of_element_located((By.XPATH, element))):
                        return "username_suggestion_screen"
                except:
                    continue

            return "unknown_screen"

        except Exception as e:
            logger.error(f"[ERRO] Erro ao verificar a tela atual: {e}")
            return "error_screen"

    def _save_screenshot(self, name):
        """Salva um screenshot apenas se o modo debug estiver ativado."""
        if not DEBUG_MODE:
            return

        try:
            import os
            screenshot_dir = "logs/screenshots"
            os.makedirs(screenshot_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            filename = f"{screenshot_dir}/{name}_{timestamp}.png"
            self.driver.save_screenshot(filename)
            logger.info(f"[DEBUG] Screenshot salvo: {filename}")
        except Exception as e:
            logger.error(f"[ERRO] Erro ao salvar screenshot: {str(e)}")

    def _is_username_suggestion_screen(self) -> bool:
        """Verifica se a tela de sugestões de username foi carregada."""
        try:
            # Usar explicitamente By.XPATH para compatibilidade com a nova assinatura do método
            return self._element_exists(By.XPATH, username_locators.SUGGESTION_OPTION)
        except TimeoutException:
            return False  # Se não apareceu, seguimos direto para a digitação do username

    def _handle_username_suggestions(self):
        """Trata a tela de sugestões de username e seleciona 'Create your own Gmail address'."""
        try:
            suggestion_option_xpath = "//*[@id='yDmH0d']/c-wiz/div/div[2]/div/div/div/form/span/section/div/div/div[1]/div[1]/div/span/div[3]/div"

            logger.info(" Verificando tela de sugestões de username...")

            # Aguarda até 5 segundos para detectar se a tela de sugestões está visível
            if self._element_exists(By.XPATH, suggestion_option_xpath, timeout=5):
                logger.info(
                    "[OK] Tela de sugestões detectada. Tentando selecionar 'Create your own Gmail address'...")

                suggestion_option = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, suggestion_option_xpath)))

                #  Verifica se o elemento está visível e interagível
                if suggestion_option.is_displayed() and suggestion_option.is_enabled():
                    try:
                        #  Tenta clicar normalmente
                        suggestion_option.click()
                    except:
                        #  Se falhar, tenta clicar via JavaScript
                        logger.warning(
                            "[AVISO] Clique padrão falhou, tentando via JavaScript...")
                        self.driver.execute_script(
                            "arguments[0].click();", suggestion_option)

                    logger.info(
                        "[OK] Opção 'Create your own Gmail address' selecionada.")
                    
                    # Aguardar um momento para a interface atualizar
                    time.sleep(2)
                    
                    # Tentar clicar no botão Next após selecionar a opção
                    logger.info("[INICIO] Tentando clicar no botão Next após selecionar opção...")
                    
                    # Lista de possíveis XPaths para o botão
                    next_button_xpaths = [
                        "//span[text()='Next' or text()='Avançar' or text()='Próximo']",
                        "//button[contains(@class, 'VfPpkd-LgbsSe')]//span[text()='Next' or text()='Avançar' or text()='Próximo']",
                        "//*[@jsname='LgbsSe']//span[contains(@class, 'VfPpkd-vQzf8d')]",
                        "//button[@type='button']//span[text()='Next' or text()='Avançar' or text()='Próximo']",
                        "//button[contains(@class, 'VfPpkd-LgbsSe')]",
                        "//*[@jsname='LgbsSe']"
                    ]

                    clicked = False
                    for xpath in next_button_xpaths:
                        try:
                            next_button = self.wait.until(
                                EC.element_to_be_clickable((By.XPATH, xpath))
                            )
                            try:
                                next_button.click()
                                clicked = True
                                logger.info(f"[OK] Botão Next clicado com sucesso usando XPath: {xpath}")
                                break
                            except Exception as click_error:
                                logger.info(f"[AVISO] Clique padrão falhou, tentando JavaScript para XPath: {xpath}")
                                try:
                                    self.driver.execute_script("arguments[0].click();", next_button)
                                    clicked = True
                                    logger.info("[OK] Botão Next clicado com sucesso via JavaScript")
                                    break
                                except Exception as js_error:
                                    logger.warning(f"[AVISO] Clique via JavaScript também falhou: {str(js_error)}")
                                    continue
                        except Exception as e:
                            logger.warning(f"[AVISO] Não foi possível encontrar/clicar no botão com XPath {xpath}: {str(e)}")
                            continue

                    if not clicked:
                        # Última tentativa: tentar clicar diretamente no botão pelo XPath completo
                        try:
                            full_xpath = "/html/body/div[1]/div[1]/div[2]/div/div[2]/div/div/div[2]/div/div[2]/div/div[1]/div/div/button"
                            next_button = self.wait.until(
                                EC.presence_of_element_located((By.XPATH, full_xpath))
                            )
                            self.driver.execute_script("arguments[0].click();", next_button)
                            clicked = True
                            logger.info("[OK] Botão Next clicado com sucesso usando XPath completo via JavaScript")
                        except Exception as final_error:
                            logger.error(f"[ERRO] Todas as tentativas de clicar no botão Next falharam: {str(final_error)}")
                            return False

                    # Aguardar e verificar se avançamos para a próxima tela
                    time.sleep(2)
                    current_screen = self._check_current_screen()
                    if current_screen == "password_screen":
                        logger.info("[OK] Avançamos para a tela de senha com sucesso")
                        return True
                    else:
                        logger.error(f"[ERRO] Não avançamos para a tela de senha. Tela atual: {current_screen}")
                        return False
                else:
                    logger.error(
                        "[ERRO] O elemento 'Create your own Gmail address' não está visível ou interagível.")
                    return False

            else:
                logger.info(
                    "[OK] Tela de sugestões de username NÃO apareceu. Continuando normalmente...")
                return True

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao tentar selecionar a opção 'Create your own Gmail address': {e}")
            return False

    def _setup_password(self):
        """
        Configura a senha da conta com sistema de retentativas.
        """
        logger.info("[INICIO] Iniciando configuração de senha...")
        
        try:
            # Verificar se estamos na tela correta
            if not self._execute_with_retry(lambda: self._check_current_screen() == "password_screen"):
                logger.error("[ERRO] Não foi possível identificar a tela de senha")
                self._save_screenshot("erro_tela_senha")
                raise NavigationError("Tela de senha não encontrada")

            # Tentar configurar a senha
            if not self._execute_with_retry(self._set_password):
                logger.error("[ERRO] Falha ao configurar senha")
                self._save_screenshot("erro_configuracao_senha")
                raise AccountSetupError("Falha ao configurar senha")

            logger.info("[OK] Senha configurada com sucesso")
            return True

        except (NavigationError, AccountSetupError) as e:
            logger.error(f"[ERRO] {str(e)}")
            self._save_screenshot("erro_setup_senha")
            return False
        except Exception as e:
            logger.error(f"[ERRO] Erro inesperado na configuração da senha: {str(e)}")
            self._save_screenshot("erro_inesperado_senha")
            return False

    def _set_password(self) -> bool:
        """
        Tenta configurar a senha com retentativas.
        """
        try:
            logger.info("[INICIO] Configurando senha...")
            
            # Seletores para os campos de senha
            password_selectors = [
                (By.NAME, "Passwd"),
                (By.XPATH, "//input[@name='Passwd']"),
                (By.XPATH, "/html/body/div[1]/div[1]/div[2]/c-wiz/div/div[2]/div/div/div/form/span/section/div/div/div/div[1]/div/div/div[1]/div/div[1]/div/div[1]/input")
            ]
            
            # Seletores para o campo de confirmação de senha
            confirm_password_selectors = [
                (By.NAME, "PasswdAgain"),
                (By.XPATH, "//input[@name='PasswdAgain']"),
                (By.XPATH, "/html/body/div[1]/div[1]/div[2]/c-wiz/div/div[2]/div/div/div/form/span/section/div/div/div/div[1]/div/div/div[2]/div/div[1]/div/div[1]/input")
            ]

            # Tentar preencher o campo de senha
            password_field = None
            for by, selector in password_selectors:
                try:
                    password_field = self.wait.until(
                        EC.presence_of_element_located((by, selector))
                    )
                    if password_field.is_displayed() and password_field.is_enabled():
                        break
                except:
                    continue

            if not password_field:
                logger.error("[ERRO] Campo de senha não encontrado")
                return False

            # Preencher senha
            password_field.clear()
            password_field.send_keys(self.credentials["password"])
            logger.info("[OK] Senha preenchida")

            # Tentar preencher o campo de confirmação de senha
            confirm_field = None
            for by, selector in confirm_password_selectors:
                try:
                    confirm_field = self.wait.until(
                        EC.presence_of_element_located((by, selector))
                    )
                    if confirm_field.is_displayed() and confirm_field.is_enabled():
                        break
                except:
                    continue

            if not confirm_field:
                logger.error("[ERRO] Campo de confirmação de senha não encontrado")
                return False

            # Preencher confirmação de senha
            confirm_field.clear()
            confirm_field.send_keys(self.credentials["password"])
            logger.info("[OK] Confirmação de senha preenchida")

            # Tentar clicar no botão Next/Avançar
            logger.info("[INICIO] Tentando clicar no botão Next após preencher senha...")
            
            # Lista de possíveis XPaths para o botão
            next_button_xpaths = [
                "//span[text()='Next' or text()='Avançar' or text()='Próximo']",
                "//button[contains(@class, 'VfPpkd-LgbsSe')]//span[text()='Next' or text()='Avançar' or text()='Próximo']",
                "//*[@jsname='LgbsSe']//span[contains(@class, 'VfPpkd-vQzf8d')]",
                "//button[@type='button']//span[text()='Next' or text()='Avançar' or text()='Próximo']",
                "//button[contains(@class, 'VfPpkd-LgbsSe')]",
                "//*[@jsname='LgbsSe']"
            ]

            clicked = False
            for xpath in next_button_xpaths:
                try:
                    next_button = self.wait.until(
                        EC.element_to_be_clickable((By.XPATH, xpath))
                    )
                    try:
                        next_button.click()
                        clicked = True
                        logger.info(f"[OK] Botão Next clicado com sucesso usando XPath: {xpath}")
                        break
                    except Exception as click_error:
                        logger.info(f"[AVISO] Clique padrão falhou, tentando JavaScript para XPath: {xpath}")
                        try:
                            self.driver.execute_script("arguments[0].click();", next_button)
                            clicked = True
                            logger.info("[OK] Botão Next clicado com sucesso via JavaScript")
                            break
                        except Exception as js_error:
                            logger.warning(f"[AVISO] Clique via JavaScript também falhou: {str(js_error)}")
                            continue
                except Exception as e:
                    logger.warning(f"[AVISO] Não foi possível encontrar/clicar no botão com XPath {xpath}: {str(e)}")
                    continue

            if not clicked:
                # Última tentativa: tentar clicar diretamente no botão pelo XPath completo
                try:
                    full_xpath = "/html/body/div[1]/div[1]/div[2]/div/div[2]/div/div/div[2]/div/div[2]/div/div[1]/div/div/button"
                    next_button = self.wait.until(
                        EC.presence_of_element_located((By.XPATH, full_xpath))
                    )
                    self.driver.execute_script("arguments[0].click();", next_button)
                    clicked = True
                    logger.info("[OK] Botão Next clicado com sucesso usando XPath completo via JavaScript")
                except Exception as final_error:
                    logger.error(f"[ERRO] Todas as tentativas de clicar no botão Next falharam: {str(final_error)}")
                    return False

            # Verificar se avançamos para a próxima tela
            time.sleep(2)
            current_screen = self._check_current_screen()
            if current_screen in ["phone_verification_screen", "recovery_email_screen"]:
                logger.info("[OK] Avançamos para a próxima etapa após configuração de senha")
                return True
            
            logger.error(f"[ERRO] Tela inesperada após configuração de senha: {current_screen}")
            return False

        except Exception as e:
            logger.error(f"[ERRO] Falha ao configurar senha: {str(e)}")
            return False

    def _click_next(self):
        """Utilitário para clicar no botão Next."""
        self._click_element_safely(
            By.XPATH,
            account_locators.NEXT_BUTTON,
            "botão Next"
        )

    def _click_element_safely(self, by, locator, element_name, timeout=None):
        """Clica em um elemento com verificações de segurança."""
        try:
            element = self.wait.until(EC.element_to_be_clickable((by, locator)))
            try:
                element.click()
            except Exception:
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(1)

                try:
                    self.driver.execute_script("arguments[0].click();", element)
                    logger.info(f"[OK] Clicou em {element_name} via JavaScript")
                except Exception as js_error:
                    logger.error(f"[ERRO] Falha ao clicar via JavaScript: {str(js_error)}")

                    from selenium.webdriver.common.action_chains import ActionChains
                    actions = ActionChains(self.driver)
                    actions.move_to_element(element).click().perform()
                    logger.info(f"[OK] Clicou em {element_name} via ActionChains")
        except Exception as e:
            raise ElementInteractionError(element_name, "clicar", str(e))

    def _fill_input_safely(self, by, locator, value):
        """Preenche um campo de input com verificações de segurança."""
        try:
            element = self.wait.until(EC.presence_of_element_located((by, locator)))
            element.clear()
            element.send_keys(value)
        except Exception as e:
            raise ElementInteractionError(f"campo {locator}", "preencher", str(e))

    def _select_month_by_value(self, month_value):
        """Seleciona um mês pelo valor numérico usando JavaScript robusto."""
        try:
            # Script JavaScript avançado para interagir com o dropdown de mês do Material Design
            js_script = """
                // Função para abrir o dropdown
                function openDropdown() {
                    // Encontrar o componente do mês
                    const monthElem = document.getElementById('month');
                    if (!monthElem) return false;
                    
                    // Encontrar o componente clicável dentro do dropdown
                    const clickable = monthElem.querySelector('[role="combobox"]') || 
                                     monthElem.querySelector('.VfPpkd-TkwUic') || 
                                     monthElem;
                                     
                    // Clicar para abrir
                    clickable.click();
                    return true;
                }
                
                // Função para selecionar a opção pelo valor
                function selectOption(value) {
                    // Esperar dropdown abrir
                    setTimeout(() => {
                        // Tentar selecionar pelo data-value
                        const options = document.querySelectorAll('li[data-value]');
                        for (const option of options) {
                            if (option.getAttribute('data-value') === value) {
                                option.click();
                                return true;
                            }
                        }
                        
                        // Fallback: tentar selecionar pela posição (janeiro=1, fevereiro=2, etc)
                        const allOptions = document.querySelectorAll('li[role="option"]');
                        const index = parseInt(value) - 1;
                        if (index >= 0 && index < allOptions.length) {
                            allOptions[index].click();
                            return true;
                        }
                        
                        return false;
                    }, 500);
                }
                
                // Executar a sequência
                const opened = openDropdown();
                if (opened) {
                    return selectOption(arguments[0]);
                }
                return false;
            """

            # Executar o script
            self.driver.execute_script(js_script, str(month_value))
            logger.info(
                f"[OK] Tentativa de selecionar mês {month_value} via JavaScript melhorado")
            time.sleep(1.5)  # Dar tempo para a seleção completar
            return True

        except Exception as e:
            logger.error(f"[ERRO] Erro na seleção de mês avançada: {str(e)}")
            return False

    def _select_gender_neutral(self):
        """Seleciona a opção neutra de gênero."""
        try:
            # Script JavaScript avançado para interagir com o dropdown de gênero
            js_script = """
                // Função para abrir o dropdown
                function openGenderDropdown() {
                    // Encontrar o componente do gênero
                    const genderElem = document.getElementById('gender');
                    if (!genderElem) {
                        // Tentar alternativas
                        const possibleSelectors = [
                            'select[name="gender"]',
                            'div[aria-label*="Gênero"]',
                            'div[aria-label*="Gender"]'
                        ];
                        
                        for (const selector of possibleSelectors) {
                            const elem = document.querySelector(selector);
                            if (elem) {
                                elem.click();
                                return true;
                            }
                        }
                        return false;
                    }
                    
                    // Clicar para abrir
                    genderElem.click();
                    return true;
                }
                
                // Função para selecionar opção neutra
                function selectNeutralOption() {
                    setTimeout(() => {
                        // Opções de texto para identificar a opção neutra
                        const neutralTexts = [
                            'Prefiro não dizer', 'Prefiro não informar',
                            'Rather not say', 'Prefer not to say',
                            'neutral', 'não binário', 'não específico'
                        ];
                        
                        // Tentar por texto
                        const allOptions = Array.from(document.querySelectorAll('li[role="option"], option'));
                        
                        // Primeiro procurar por texto similar
                        for (const option of allOptions) {
                            const text = option.textContent.toLowerCase();
                            if (neutralTexts.some(neutral => text.includes(neutral.toLowerCase()))) {
                                option.click();
                                console.log('Encontrou opção neutra por texto');
                                return true;
                            }
                        }
                        
                        // Se não encontrar, pegar a última opção (geralmente é "prefiro não dizer")
                        if (allOptions.length > 0) {
                            allOptions[allOptions.length - 1].click();
                            console.log('Selecionada última opção');
                            return true;
                        }
                        
                        return false;
                    }, 500);
                }
                
                // Executar a sequência
                const opened = openGenderDropdown();
                if (opened) {
                    return selectNeutralOption();
                }
                return false;
            """

            # Executar o script
            self.driver.execute_script(js_script)
            logger.info(
                "[OK] Tentativa de selecionar gênero neutro via JavaScript melhorado")
            time.sleep(1.5)  # Dar tempo para a seleção completar
            return True

        except Exception as e:
            logger.error(
                f"[ERRO] Erro na seleção de gênero avançada: {str(e)}")
            return False

    def _fill_birth_and_gender(self):
        """
        Preenche as informações de data de nascimento e gênero.
        """
        try:
            logger.info("[INICIO] Preenchendo data de nascimento e gênero...")

            # Aguardar elementos da página carregarem
            try:
                # Verificar se os campos de data estão presentes
                day_field = self.wait.until(
                    EC.presence_of_element_located((By.NAME, "day"))
                )
                month_field = self.wait.until(
                    EC.presence_of_element_located((By.ID, "month"))
                )
                year_field = self.wait.until(
                    EC.presence_of_element_located((By.NAME, "year"))
                )
                
                logger.info("[OK] Campos de data encontrados")
            except Exception as e:
                logger.error(f"[ERRO] Campos de data não encontrados: {str(e)}")
                return False

            # Preencher dia
            try:
                day_field.clear()
                day_field.send_keys(str(self.credentials["birth_day"]))
                logger.info(f"[OK] Dia preenchido: {self.credentials['birth_day']}")
            except Exception as e:
                logger.error(f"[ERRO] Falha ao preencher dia: {str(e)}")
                return False

            # Preencher mês (usando o método existente)
            try:
                month_value = self.credentials["birth_month"]
                if isinstance(month_value, str) and not month_value.isdigit():
                    month_map = {
                        "January": "1", "February": "2", "March": "3", "April": "4",
                        "May": "5", "June": "6", "July": "7", "August": "8",
                        "September": "9", "October": "10", "November": "11", "December": "12"
                    }
                    month_value = month_map.get(month_value, "1")
                
                if not self._select_month_by_value(month_value):
                    logger.error("[ERRO] Falha ao selecionar mês")
                    return False
                
                logger.info(f"[OK] Mês selecionado: {month_value}")
            except Exception as e:
                logger.error(f"[ERRO] Falha ao selecionar mês: {str(e)}")
                return False

            # Preencher ano
            try:
                year_field.clear()
                year_field.send_keys(str(self.credentials["birth_year"]))
                logger.info(f"[OK] Ano preenchido: {self.credentials['birth_year']}")
            except Exception as e:
                logger.error(f"[ERRO] Falha ao preencher ano: {str(e)}")
                return False

            # Selecionar gênero (usando o método existente)
            try:
                if not self._select_gender_neutral():
                    logger.error("[ERRO] Falha ao selecionar gênero")
                    return False
                logger.info("[OK] Gênero selecionado com sucesso")
            except Exception as e:
                logger.error(f"[ERRO] Falha ao selecionar gênero: {str(e)}")
                return False

            # Clicar no botão Next
            logger.info("[INICIO] Tentando clicar no botão Next após data de nascimento...")
            next_button_xpaths = [
                "//span[text()='Next' or text()='Avançar' or text()='Próximo']",
                "//button[contains(@class, 'VfPpkd-LgbsSe')]//span[text()='Next' or text()='Avançar' or text()='Próximo']",
                "//*[@jsname='LgbsSe']//span[contains(@class, 'VfPpkd-vQzf8d')]",
                "//button[@type='button']//span[text()='Next' or text()='Avançar' or text()='Próximo']"
            ]

            clicked = False
            for xpath in next_button_xpaths:
                try:
                    next_button = self.wait.until(
                        EC.element_to_be_clickable((By.XPATH, xpath))
                    )
                    try:
                        next_button.click()
                        clicked = True
                        logger.info(f"[OK] Botão Next clicado com sucesso após data de nascimento usando XPath: {xpath}")
                        break
                    except Exception as click_error:
                        logger.info(f"[AVISO] Clique padrão falhou, tentando JavaScript")
                        try:
                            self.driver.execute_script("arguments[0].click();", next_button)
                            clicked = True
                            logger.info("[OK] Botão Next clicado com sucesso via JavaScript")
                            break
                        except Exception as js_error:
                            logger.warning(f"[AVISO] Clique via JavaScript também falhou: {str(js_error)}")
                            continue
                except Exception as e:
                    logger.warning(f"[AVISO] Não foi possível encontrar/clicar no botão com XPath {xpath}: {str(e)}")
                    continue

            if not clicked:
                logger.error("[ERRO] Não foi possível clicar no botão Next após data de nascimento")
                return False

            # Aguardar transição de página
            time.sleep(2)
            logger.info("[OK] Data de nascimento e gênero preenchidos com sucesso")
            return True

        except Exception as e:
            logger.error(f"[ERRO] Falha ao preencher data de nascimento e gênero: {str(e)}")
            return False
