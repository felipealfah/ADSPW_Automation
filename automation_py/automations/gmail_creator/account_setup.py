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
DEBUG_MODE = False  # Mudar para True apenas quando precisar diagnosticar problemas


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

    def start_setup(self) -> bool:
        """Inicia o processo de configuração da conta."""
        try:
            logger.info("[INICIO] Iniciando configuração da conta Gmail...")

            # Navegar para a página de signup
            if not self._execute_with_retry(self._navigate_to_signup):
                return False

            # Verificar e tratar a tela "Choose an account" se ela aparecer
            if self._check_and_handle_choose_account_screen():
                logger.info(
                    "[OK] Tela 'Choose an account' tratada com sucesso.")
            else:
                logger.info(
                    " Sem tela 'Choose an account', prosseguindo com fluxo normal.")

            # Continuar com os passos normais
            setup_steps = [
                (self._select_personal_account, SetupState.BASIC_INFO),
                (self._fill_basic_info, SetupState.BASIC_INFO),
                (self._handle_username_setup, SetupState.USERNAME_SETUP),
                (self._setup_password, SetupState.PASSWORD_SETUP)
            ]

            for step_func, new_state in setup_steps:
                self.state = new_state
                self.account_info.state = new_state

                if not self._execute_with_retry(step_func):
                    self.state = SetupState.FAILED
                    self.account_info.state = SetupState.FAILED
                    return False

            self.state = SetupState.COMPLETED
            self.account_info.state = SetupState.COMPLETED
            return True

        except Exception as e:
            logger.error(
                f"[ERRO] Erro durante configuração da conta: {str(e)}")
            self.state = SetupState.FAILED
            self.account_info.state = SetupState.FAILED
            raise AccountSetupError(
                f"Falha na configuração da conta: {str(e)}")

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
        """Navega para a página de cadastro."""
        try:
            logger.info(" Acessando página de criação de conta...")
            self.driver.get(account_config.GMAIL_SIGNUP_URL)
            self._wait_for_page_load()
        except Exception as e:
            raise NavigationError(
                url=account_config.GMAIL_SIGNUP_URL, reason=str(e))

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

    def _fill_basic_info(self):
        """Preenche informações básicas do usuário."""
        try:
            logger.info(" Preenchendo informações básicas...")

            first_name_input = self.wait.until(
                EC.presence_of_element_located((By.ID, account_locators.FIRST_NAME)))
            first_name_input.clear()
            first_name_input.send_keys(self.account_info.first_name)

            last_name_input = self.driver.find_element(
                By.ID, account_locators.LAST_NAME)
            last_name_input.clear()
            last_name_input.send_keys(self.account_info.last_name)

            self._click_next()
            time.sleep(2)

            logger.info(" Preenchendo data de nascimento e gênero...")

            # Verificar se o mês é um número
            month_value = self.account_info.birth_month
            if isinstance(month_value, str) and not month_value.isdigit():
                # Se for um nome de mês, converter para número
                month_map = {"January": "1", "February": "2", "March": "3", "April": "4",
                             "May": "5", "June": "6", "July": "7", "August": "8",
                             "September": "9", "October": "10", "November": "11", "December": "12",
                             "Janeiro": "1", "Fevereiro": "2", "Março": "3", "Abril": "4",
                             "Maio": "5", "Junho": "6", "Julho": "7", "Agosto": "8",
                             "Setembro": "9", "Outubro": "10", "Novembro": "11", "Dezembro": "12"}
                month_value = month_map.get(month_value, "1")

            # Primeiro preencher dia e ano sempre com JavaScript
            try:
                # Preencher dia com JavaScript
                self.driver.execute_script("""
                    document.getElementById('day').value = arguments[0];
                    document.getElementById('day').dispatchEvent(new Event('input'));
                    document.getElementById('day').dispatchEvent(new Event('change'));
                """, str(self.account_info.birth_day))

                # Preencher ano com JavaScript
                self.driver.execute_script("""
                    document.getElementById('year').value = arguments[0];
                    document.getElementById('year').dispatchEvent(new Event('input'));
                    document.getElementById('year').dispatchEvent(new Event('change'));
                """, str(self.account_info.birth_year))

                logger.info("[OK] Campos dia e ano preenchidos com JavaScript")
            except Exception as js_error:
                logger.error(
                    f"[ERRO] Falha ao preencher dia e ano: {str(js_error)}")

            # Para o mês
            month_success = self._select_month_by_value(month_value)
            if not month_success:
                logger.warning(
                    "[AVISO] Método avançado para mês falhou, tentando método alternativo")
                try:
                    # Tentar abrir o dropdown e selecionar usando Actions
                    month_elem = self.driver.find_element(
                        By.ID, account_locators.MONTH)
                    from selenium.webdriver.common.action_chains import ActionChains
                    actions = ActionChains(self.driver)
                    actions.move_to_element(month_elem).click().perform()
                    time.sleep(1)

                    # Tentar encontrar opção por XPath
                    month_option_xpath = f"//li[@data-value='{month_value}']"
                    option = self.wait.until(EC.element_to_be_clickable(
                        (By.XPATH, month_option_xpath)))
                    option.click()
                    logger.info("[OK] Mês selecionado com método alternativo")
                except Exception as alt_month_error:
                    logger.error(
                        f"[ERRO] Também falhou método alternativo para mês: {str(alt_month_error)}")

            # Para o gênero
            gender_success = self._select_gender_neutral()
            if not gender_success:
                logger.warning(
                    "[AVISO] Método avançado para gênero falhou, tentando método alternativo")
                try:
                    # Tentar encontrar o elemento de gênero por ID
                    gender_elem = self.driver.find_element(
                        By.ID, account_locators.GENDER)
                    gender_elem.click()
                    time.sleep(1)

                    # Tentar encontrar a opção neutra pela última opção
                    from selenium.webdriver.support.ui import Select
                    try:
                        select = Select(gender_elem)
                        options = select.options
                        if len(options) > 0:
                            select.select_by_index(len(options) - 1)
                            logger.info(
                                "[OK] Gênero selecionado com Select (última opção)")
                    except:
                        # Se não funcionar como select, tentar como dropdown material
                        neutral_options = self.driver.find_elements(By.XPATH,
                                                                    "//li[@role='option'] | //option[contains(text(), 'Prefiro não dizer')] | //option[contains(text(), 'Rather not say')]")
                        if neutral_options and len(neutral_options) > 0:
                            neutral_options[-1].click()
                            logger.info(
                                "[OK] Gênero selecionado com clique na última opção")
                except Exception as alt_gender_error:
                    logger.error(
                        f"[ERRO] Também falhou método alternativo para gênero: {str(alt_gender_error)}")

            # Concluir com botão próximo
            self._click_next()
            time.sleep(2)
            logger.info("[OK] Informações básicas preenchidas com sucesso!")

        except Exception as e:
            raise ElementInteractionError(
                "campos básicos", "preencher", str(e))

    def _remove_readonly_if_exists(self, by, locator):
        """Remove o atributo 'readonly' de um campo, se ele estiver presente."""
        try:
            element = self.driver.find_element(by, locator)
            self.driver.execute_script(
                "arguments[0].removeAttribute('readonly')", element)
        except Exception:
            pass

    def _handle_username_setup(self):
        """Gerencia o processo de configuração do username."""
        try:
            logger.info(" Iniciando configuração do username...")

            # Primeiro verificar se já avançamos para tela de senha (verificação robusta)
            try:
                # Método 1: Verificar diretamente por elementos da tela de senha
                password_elements = [
                    "//input[@type='password']",
                    "//div[contains(text(), 'Criar uma senha')]",
                    "//div[contains(text(), 'Create a password')]"
                ]

                for element in password_elements:
                    try:
                        if WebDriverWait(self.driver, 2).until(EC.presence_of_element_located((By.XPATH, element))):
                            logger.info(
                                "[OK] Já estamos na tela de senha! Username já foi configurado.")
                            return True
                    except:
                        continue

                # Método 2: Verificar com o método de detecção geral
                current_screen = self._check_current_screen()
                logger.info(
                    f"[DIAGNÓSTICO] Tela atual identificada: {current_screen}")

                if current_screen == "password_screen":
                    logger.info(
                        "[OK] Já na tela de senha, username configurado com sucesso!")
                    return True

                # Se estamos na tela de sugestões de username, tratá-la primeiro
                if current_screen == "username_suggestion_screen":
                    logger.info(
                        "[OK] Tela de sugestões de username detectada, tratando primeiro...")
                    self._handle_username_suggestions()
                    # Após tratar as sugestões, verificar se ainda estamos na tela de username
                    # Pequena pausa para garantir que a tela carregou
                    time.sleep(2)
                    current_screen = self._check_current_screen()
                    logger.info(
                        f"[DIAGNÓSTICO] Tela após tratar sugestões: {current_screen}")

            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao verificar tela atual: {str(e)}")
                # Tirar screenshot para diagnóstico
                self._save_screenshot("error_checking_screen")

            # Verificar se há tela de sugestões (método tradicional como fallback)
            try:
                if self._is_username_suggestion_screen():
                    logger.info(
                        "[OK] Tela de sugestões detectada pelo método fallback. Tentando selecionar 'Create your own Gmail address'...")
                    self._handle_username_suggestions()
                else:
                    logger.info(
                        "[OK] Tela de sugestões NÃO apareceu. Continuando normalmente...")
            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao verificar tela de sugestões (fallback): {e}")

            # Configurar o username com verificações robustas
            current_screen = self._check_current_screen()
            logger.info(
                f"[DIAGNÓSTICO] Tela antes de configurar username: {current_screen}")

            # Se já não estamos na tela de senha (caso raro mas possível)
            if current_screen == "password_screen":
                logger.info(
                    "[OK] Já na tela de senha, pulando configuração de username!")
                return True

            # Se estamos na tela correta, configurar username
            if current_screen == "username_screen" or current_screen == "unknown_screen":
                if not self._set_username():
                    raise UsernameError(
                        "[ERRO] Falha ao configurar um username válido.")
            else:
                logger.warning(
                    f"[AVISO] Tela inesperada para configuração de username: {current_screen}")
                # Tentamos mesmo assim, talvez consigamos continuar
                if not self._set_username():
                    raise UsernameError(
                        "[ERRO] Falha ao configurar um username válido em tela inesperada.")

            # Verificar novamente se avançamos para tela de senha
            try:
                current_screen = self._check_current_screen()
                logger.info(
                    f"[DIAGNÓSTICO] Tela após _set_username: {current_screen}")
                if current_screen == "password_screen":
                    logger.info(
                        "[OK] Username configurado com sucesso, estamos na tela de senha!")
                    return True
            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao verificar tela final: {str(e)}")

            logger.info("[OK] Username configurado com sucesso!")
            return True

        except UsernameError as e:
            logger.error(f"[ERRO] Erro ao configurar username: {e}")
            raise e

        except Exception as e:
            logger.error(
                f"[AVISO] Erro inesperado ao configurar username: {e}")
            raise UsernameError(
                f"Erro inesperado ao configurar username: {str(e)}")

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
                    # Pequeno delay para garantir que a nova tela carregue
                    time.sleep(2)
                else:
                    logger.error(
                        "[ERRO] O elemento 'Create your own Gmail address' não está visível ou interagível.")

            else:
                logger.info(
                    "[OK] Tela de sugestões de username NÃO apareceu. Continuando normalmente...")
        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao tentar selecionar a opção 'Create your own Gmail address': {e}")

    def _set_username(self) -> bool:
        """Configura o username e verifica disponibilidade. Se já existir, tenta outro automaticamente."""
        username_taken_xpath = username_locators.USERNAME_TAKEN_ERROR  # XPath da mensagem de erro
        max_attempts = account_config.MAX_USERNAME_ATTEMPTS  # Número máximo de tentativas

        for attempt in range(max_attempts):
            try:
                # Tirar screenshot do início da tentativa
                self._save_screenshot(f"username_attempt_{attempt}_start")

                # Verificar se já avançamos para a tela de senha
                current_screen = self._check_current_screen()
                if current_screen == "password_screen":
                    logger.info(
                        "[OK] Já na tela de senha! Username aceito com sucesso.")
                    self._save_screenshot("already_at_password_screen")
                    return True

                # Verificar se ainda estamos na tela de username
                if current_screen != "username_screen":
                    logger.warning(
                        f"[AVISO] Tela inesperada: {current_screen}. Tentando continuar...")
                    self._save_screenshot(
                        f"unexpected_screen_{current_screen}")

                    # Tentar detectar se estamos em uma parte posterior do fluxo
                    try:
                        # Se encontrarmos qualquer elemento relacionado à senha, consideramos sucesso
                        password_field = self.driver.find_element(
                            By.XPATH, password_locators.PASSWORD_FIELD)
                        if password_field:
                            logger.info(
                                "[OK] Detectado campo de senha. Username aceito!")
                            self._save_screenshot("password_field_detected")
                            return True
                    except:
                        pass

                #  1. Aguarda o campo de username estar visível e interativo
                username_field = self.wait.until(EC.presence_of_element_located(
                    (By.XPATH, username_locators.USERNAME_FIELD)))
                self.wait.until(EC.element_to_be_clickable(
                    (By.XPATH, username_locators.USERNAME_FIELD)))

                self.driver.execute_script(
                    "arguments[0].scrollIntoView();", username_field)
                self.driver.execute_script(
                    "arguments[0].click();", username_field)

                #  2. Gera novo username se não for a primeira tentativa
                if attempt > 0:
                    self.account_info.username = self._generate_new_username()
                    logger.warning(
                        f"[AVISO] Tentativa {attempt}: Username já estava em uso. Tentando {self.account_info.username}")

                #  3. Insere o username e clica em "Next"
                username_field.clear()
                username_field.send_keys(self.account_info.username)
                logger.info(
                    f"[OK] Tentativa {attempt}: Testando username {self.account_info.username}")
                self._save_screenshot(
                    f"username_field_filled_{self.account_info.username}")

                # Tirar screenshot antes de clicar em Next
                self._save_screenshot(f"before_next_click_attempt_{attempt}")
                self._click_next()
                time.sleep(2)  # Aguarda verificação
                self._save_screenshot(f"after_next_click_attempt_{attempt}")

                # 4. Verificar novamente se avançamos para a tela de senha
                current_screen = self._check_current_screen()
                if current_screen == "password_screen":
                    logger.info(
                        "[OK] Avançamos para tela de senha! Username aceito.")
                    self._save_screenshot("advanced_to_password_screen")
                    return True

                # Se ainda estamos na tela de username, realmente verificar se há mensagem de erro
                is_username_taken = self._check_username_taken()
                if is_username_taken:
                    logger.warning(
                        "[AVISO] Nome de usuário já está em uso. Tentando outro...")
                    self._save_screenshot(f"username_taken_attempt_{attempt}")
                    continue  # Tenta novamente com um novo username
                else:
                    # Esperar um pouco mais para garantir que qualquer redirecionamento ocorra
                    logger.info(
                        "[AVISO] Sem erro de username identificado, aguardando redirecionamento...")
                    time.sleep(3)

                    # Verificar uma última vez
                    current_screen = self._check_current_screen()
                    if current_screen == "password_screen":
                        logger.info(
                            "[OK] Redirecionado para tela de senha após espera!")
                        self._save_screenshot("redirected_to_password")
                        return True
                    elif current_screen == "username_screen":
                        # Ainda na tela de username - verificar HTML da página para presença de erro
                        page_source = self.driver.page_source.lower()
                        if "username is taken" in page_source or "nome de usuário já está em uso" in page_source:
                            logger.warning(
                                "[AVISO] Erro de username detectado no HTML da página")
                            self._save_screenshot("username_taken_in_html")
                            continue  # Tentar novamente
                        else:
                            # Talvez tenha um problema diferente, tentar clicar em Next novamente
                            logger.info(
                                "[AVISO] Tentando clicar em Next novamente...")
                            self._click_next()
                            time.sleep(2)

                            # Verificar se avançamos
                            if self._check_current_screen() == "password_screen":
                                logger.info(
                                    "[OK] Avançamos para senha após segundo clique!")
                                return True
                            else:
                                logger.warning(
                                    "[AVISO] Ainda na tela de username após segundo clique")
                    else:
                        # Avançamos para alguma outra tela
                        logger.info(
                            f"[OK] Avançamos para tela: {current_screen}")
                        return True

            except TimeoutException:
                # Verificar se já avançamos para outra tela
                self._save_screenshot(f"timeout_during_attempt_{attempt}")
                current_screen = self._check_current_screen()
                if current_screen == "password_screen":
                    logger.info("[OK] Já na tela de senha! Username aceito.")
                    return True

                logger.error("[ERRO] Erro: Campo de username não encontrado!")
                raise UsernameError(" Campo de username não apareceu na tela.")

            except Exception as e:
                self._save_screenshot(f"error_during_attempt_{attempt}")
                logger.warning(f"[AVISO] Erro ao preencher username: {str(e)}")

        self._save_screenshot("max_attempts_reached")
        raise UsernameError(
            "[ALERTA] Número máximo de tentativas atingido. Não foi possível encontrar um username disponível.")

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

    def _check_username_taken(self, timeout=3) -> bool:
        """Verifica se o username já está em uso pela presença da mensagem de erro."""
        try:
            # Capturar screenshot antes de verificar
            self._save_screenshot("check_username_taken_before")

            # Verificar mensagens de erro de username ocupado
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
                        # Capturar screenshot quando username está ocupado
                        self._save_screenshot("username_taken_confirmed")
                        return True  # Username está em uso
                except TimeoutException:
                    continue

            # Se não encontrou nenhuma mensagem de erro, verificar se ainda estamos na tela de username
            current_screen = self._check_current_screen()
            if current_screen != "username_screen":
                # Se não estamos mais na tela de username, provavelmente avançamos
                self._save_screenshot("likely_username_accepted")
                return False

            # Se ainda estamos na tela de username sem mensagem de erro, pode haver algum outro problema
            self._save_screenshot("username_screen_no_error")
            return False  # Assumimos que não há erro de username ocupado

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao verificar disponibilidade do username: {str(e)}")
            # Tirar screenshot do erro
            self._save_screenshot("username_check_error")
            return False  # Em caso de erro, assumimos que podemos continuar

    def _setup_password(self):
        """Configura a senha da conta."""
        try:
            logger.info(" Configurando senha...")

            self._fill_input_safely(
                By.XPATH,
                password_locators.PASSWORD_FIELD,
                self.account_info.password
            )

            self._fill_input_safely(
                By.XPATH,
                password_locators.CONFIRM_PASSWORD,
                self.account_info.password
            )

            self._click_next()
            logger.info("[OK] Senha configurada com sucesso")

        except Exception as e:
            raise ElementInteractionError(
                "campos de senha", "preencher", str(e))

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
            element = self.wait.until(
                EC.element_to_be_clickable((by, locator))
            )
            try:
                element.click()
            except Exception:
                # Adicionar scroll para garantir visibilidade
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(1)

                # Tentar JavaScript como fallback
                try:
                    self.driver.execute_script(
                        "arguments[0].click();", element)
                    logger.info(
                        f"[OK] Clicou em {element_name} via JavaScript")
                except Exception as js_error:
                    logger.error(
                        f"[ERRO] Falha ao clicar via JavaScript: {str(js_error)}")

                    # Última tentativa usando Actions
                    from selenium.webdriver.common.action_chains import ActionChains
                    actions = ActionChains(self.driver)
                    actions.move_to_element(element).click().perform()
                    logger.info(
                        f"[OK] Clicou em {element_name} via ActionChains")
        except Exception as e:
            raise ElementInteractionError(element_name, "clicar", str(e))

    def _fill_input_safely(self, by, locator, value):
        """Preenche um campo de input com verificações de segurança."""
        try:
            element = self.wait.until(
                EC.presence_of_element_located((by, locator))
            )
            element.clear()
            element.send_keys(value)
        except Exception as e:
            raise ElementInteractionError(
                f"campo {locator}", "preencher", str(e))

    def _generate_new_username(self):
        """Gera um novo username quando o atual não está disponível."""
        # Adicionar o dia de nascimento ao username atual
        try:
            original_username = self.account_info.username

            # Adicionar o dia de nascimento ao final
            new_username = f"{original_username}{self.account_info.birth_day}"

            logger.info(f"[OK] Gerando username alternativo: {new_username}")
            return new_username

        except Exception as e:
            # Fallback em caso de erro
            logger.error(
                f"[ERRO] Erro ao gerar username alternativo: {str(e)}")

            # Usar dados da conta atual para reconstruir o username
            try:
                import string
                import random
                import calendar

                first = self.account_info.first_name.lower()
                last = self.account_info.last_name.lower()
                year = str(self.account_info.birth_year)
                day = str(self.account_info.birth_day)

                # Username com componentes aleatórios para aumentar chance de ser único
                random_part = ''.join(random.choice(
                    string.ascii_lowercase) for _ in range(5))
                new_username = f"{first[:3]}{last[:3]}{random_part}{year[-2:]}{day}"

                logger.info(f"[OK] Gerado username fallback: {new_username}")
                return new_username

            except Exception as fallback_error:
                # Último recurso - gerar um username completamente aleatório
                import random
                import string
                random_part = ''.join(random.choice(
                    string.ascii_lowercase + string.digits) for _ in range(8))
                random_username = f"user_{random_part}_{random.randint(1900, 2010)}"
                logger.warning(
                    f"[AVISO] Gerado username aleatório: {random_username}")
                return random_username

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

    def _check_current_screen(self):
        """Verifica qual tela está sendo exibida atualmente."""
        try:
            # Verificar se estamos na tela de senha
            password_elements = [
                "//input[@type='password']",
                "//div[contains(text(), 'Criar uma senha')]",
                "//div[contains(text(), 'Create a password')]"
            ]

            for element in password_elements:
                try:
                    if WebDriverWait(self.driver, 2).until(EC.presence_of_element_located((By.XPATH, element))):
                        logger.info("[OK] Detectada tela de senha")
                        return "password_screen"
                except TimeoutException:
                    continue

            # Verificar se estamos na tela de username
            username_elements = [
                "//input[@name='username']",
                "//div[contains(text(), 'Criar um nome de usuário')]",
                "//div[contains(text(), 'Create a username')]"
            ]

            for element in username_elements:
                try:
                    if WebDriverWait(self.driver, 2).until(EC.presence_of_element_located((By.XPATH, element))):
                        logger.info("[OK] Detectada tela de username")
                        return "username_screen"
                except TimeoutException:
                    continue

            # Verificar tela de sugestões de username
            suggestion_elements = [
                username_locators.SUGGESTION_OPTION,
                "//div[contains(text(), 'Choose a Gmail address')]",
                "//div[contains(text(), 'Escolha um endereço Gmail')]",
                "//div[contains(@role, 'radiogroup')]",
                "//span[contains(text(), 'Create your own Gmail address')]",
                "//span[contains(text(), 'Criar seu próprio endereço Gmail')]",
                "//*[@id='yDmH0d']/c-wiz/div/div[2]/div/div/div/form/span/section/div/div/div[1]/div[1]/div/span/div[3]/div"
            ]

            for element in suggestion_elements:
                try:
                    if WebDriverWait(self.driver, 2).until(EC.presence_of_element_located((By.XPATH, element))):
                        logger.info(
                            "[OK] Detectada tela de sugestões de username")
                        return "username_suggestion_screen"
                except TimeoutException:
                    continue

            # Verificar se estamos na tela de informações básicas
            basic_info_elements = [
                "//input[@id='firstName']",
                "//input[@id='lastName']",
                "//input[@id='day']",
                "//input[@id='year']",
                "//select[@id='month']",
                "//select[@id='gender']"
            ]

            for element in basic_info_elements:
                try:
                    if WebDriverWait(self.driver, 2).until(EC.presence_of_element_located((By.XPATH, element))):
                        logger.info(
                            "[OK] Detectada tela de informações básicas")
                        return "basic_info_screen"
                except TimeoutException:
                    continue

            # Tirar screenshot da tela não identificada para diagnóstico
            self._save_screenshot("unknown_screen_detection")

            # Verificar URL atual para diagnóstico adicional
            try:
                current_url = self.driver.current_url
                logger.info(f"[DIAGNÓSTICO] URL atual: {current_url}")

                # Tentar identificar pelo URL
                if "signin/v2/challenge/selectchallenge" in current_url:
                    return "verification_challenge_screen"
                elif "signup/v2" in current_url:
                    return "signup_screen"
            except:
                pass

            logger.warning("[AVISO] Tela não identificada")
            return "unknown_screen"
        except Exception as e:
            logger.error(f"[ERRO] Erro ao verificar tela atual: {str(e)}")
            return "error_checking_screen"

    def _wait_for_element(self, by, locator, timeout=5, condition=EC.presence_of_element_located):
        """Espera mais eficiente por um elemento, retorna o elemento ou None."""
        try:
            element = WebDriverWait(self.driver, timeout).until(
                condition((by, locator))
            )
            return element
        except TimeoutException:
            return None
