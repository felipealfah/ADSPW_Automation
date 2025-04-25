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
                logger.info("[OK] Tela 'Choose an account' tratada com sucesso.")
            else:
                logger.info(" Sem tela 'Choose an account', prosseguindo com fluxo normal.")
            
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
            logger.error(f"[ERRO] Erro durante configuração da conta: {str(e)}")
            self.state = SetupState.FAILED
            self.account_info.state = SetupState.FAILED
            raise AccountSetupError(f"Falha na configuração da conta: {str(e)}")

    def _check_and_handle_choose_account_screen(self) -> bool:
        """Verifica se estamos na tela 'Choose an account' e clica em 'Use another account' se necessário."""
        try:
            # Verificar se a tela "Choose an account" está presente
            choose_account_present = False
            try:
                choose_account_element = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, account_locators.CHOOSE_ACCOUNT_SCREEN))
                )
                choose_account_present = True
                logger.info("[BUSCA] Tela 'Choose an account' detectada.")
            except TimeoutException:
                logger.info(" Tela 'Choose an account' não detectada, seguindo fluxo normal.")
                return False
            
            if not choose_account_present:
                return False
                
            # Tentar localizar e clicar no botão "Use another account"
            try:
                # Tentar com o XPath completo primeiro
                use_another_button = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, account_locators.USE_ANOTHER_ACCOUNT_BUTTON))
                )
                use_another_button.click()
                logger.info("[OK] Clicado em 'Use another account' com XPath completo.")
                time.sleep(2)  # Aguardar carregamento da próxima tela
                return True
            except Exception as e:
                logger.warning(f"[AVISO] Erro ao clicar com XPath completo: {str(e)}")
                
                # Tentar com alternativa mais robusta
                try:
                    use_another_button_alt = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, account_locators.USE_ANOTHER_ACCOUNT_ALT))
                    )
                    use_another_button_alt.click()
                    logger.info("[OK] Clicado em 'Use another account' com XPath alternativo.")
                    time.sleep(2)  # Aguardar carregamento da próxima tela
                    return True
                except Exception as e2:
                    logger.error(f"[ERRO] Não foi possível clicar em 'Use another account': {str(e2)}")
                    
                    # Tentar uma abordagem JavaScript como último recurso
                    try:
                        self.driver.execute_script(f"document.evaluate('{account_locators.USE_ANOTHER_ACCOUNT_BUTTON}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue.click();")
                        logger.info("[OK] Clicado em 'Use another account' usando JavaScript.")
                        time.sleep(2)
                        return True
                    except Exception as e3:
                        logger.error(f"[ERRO] Todas as tentativas de clicar em 'Use another account' falharam: {str(e3)}")
                        return False
        
        except Exception as e:
            logger.error(f"[ERRO] Erro ao verificar tela 'Choose an account': {str(e)}")
            return False
        
    def _element_exists(self, xpath, timeout=3):
        """Verifica se um elemento existe na página dentro de um tempo limite."""
        try:
            self.wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
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
                logger.warning(f"[AVISO] Tentativa {attempt + 1} falhou: {str(e)}")
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
            raise NavigationError(url=account_config.GMAIL_SIGNUP_URL, reason=str(e))

    def _wait_for_page_load(self, timeout=10):
        """Aguarda o carregamento completo da página."""
        try:
            self.wait.until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
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
            logger.info("[AVISO] Botão de seleção de conta não encontrado, continuando...")
        except Exception as e:
            raise ElementInteractionError("botão de conta pessoal", "clicar", str(e))

    def _fill_basic_info(self):
        """Preenche informações básicas do usuário."""
        try:
            logger.info(" Preenchendo informações básicas...")

            first_name_input = self.wait.until(EC.presence_of_element_located((By.ID, account_locators.FIRST_NAME)))
            first_name_input.clear()
            first_name_input.send_keys(self.account_info.first_name)

            last_name_input = self.driver.find_element(By.ID, account_locators.LAST_NAME)
            last_name_input.clear()
            last_name_input.send_keys(self.account_info.last_name)

            self._click_next()
            time.sleep(2)

            logger.info(" Preenchendo data de nascimento e gênero...")

            self._remove_readonly_if_exists(By.ID, account_locators.MONTH)
            self._remove_readonly_if_exists(By.ID, account_locators.DAY)
            self._remove_readonly_if_exists(By.ID, account_locators.YEAR)

            self.driver.find_element(By.ID, account_locators.MONTH).send_keys(self.account_info.birth_month)
            self.driver.find_element(By.ID, account_locators.DAY).send_keys(str(self.account_info.birth_day))
            self.driver.find_element(By.ID, account_locators.YEAR).send_keys(str(self.account_info.birth_year))
            
            # Trecho de seleção de gênero usando XPath exato

            try:
                # Selecionar o dropdown de gênero
                gender_dropdown = self.driver.find_element(By.ID, account_locators.GENDER)
                gender_dropdown.click()
                time.sleep(1)  # Pequena pausa para garantir que o dropdown está aberto
                
                try:
                    # Tentar encontrar e clicar na opção usando o XPath definido no locators.py
                    rather_not_say_option = self.driver.find_element(By.XPATH, account_locators.GENDER_NEUTRAL_OPTION)
                    logger.info(f"[OK] Opção 'Prefiro não dizer' encontrada: {rather_not_say_option.text}")
                    
                    # Usar JavaScript para garantir a seleção
                    self.driver.execute_script("arguments[0].selected = true;", rather_not_say_option)
                    self.driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", gender_dropdown)
                    logger.info("[OK] Opção 'Prefiro não dizer' selecionada com sucesso via XPath exato")
                except Exception as xpath_error:
                    logger.warning(f"[AVISO] Não foi possível selecionar usando XPath exato: {str(xpath_error)}")
                    
                    # Tentar usar Select como fallback
                    try:
                        from selenium.webdriver.support.ui import Select
                        select = Select(gender_dropdown)
                        
                        # Obter todas as opções e logging
                        options = select.options
                        logger.info(f"Opções disponíveis: {[opt.text for opt in options]}")
                        
                        # Tentar encontrar "Prefiro não dizer" (ou equivalente) nas opções
                        for i, option in enumerate(options):
                            option_text = option.text.strip().lower()
                            if ("prefiro não dizer" in option_text or 
                                "prefiro não informar" in option_text or 
                                "rather not say" in option_text or 
                                "prefer not to say" in option_text):
                                # Selecionar por índice
                                select.select_by_index(i)
                                logger.info(f"[OK] Opção selecionada via texto: {option.text}")
                                break
                        else:
                            # Se não encontrou por texto, tentar última opção (geralmente é a correta)
                            # Mas apenas se não for "Personalizar"
                            last_option = options[-1].text.lower()
                            if not ("personalizar" in last_option or "custom" in last_option):
                                select.select_by_index(len(options) - 1)
                                logger.info(f"[OK] Selecionada última opção: {options[-1].text}")
                            else:
                                # Tentar encontrar a opção correta por exclusão
                                for i, option in enumerate(options):
                                    if ("personalizar" not in option.text.lower() and 
                                        "custom" not in option.text.lower()):
                                        select.select_by_index(i)
                                        logger.info(f"[OK] Opção selecionada por exclusão: {option.text}")
                                        break
                    except Exception as select_error:
                        logger.error(f"[ERRO] Erro ao usar Select como fallback: {str(select_error)}")

            except Exception as e:
                logger.error(f"[ERRO] Erro ao selecionar gênero: {str(e)}")
            self._click_next()
            time.sleep(2)

            logger.info("[OK] Informações básicas preenchidas com sucesso!")

        except Exception as e:
            raise ElementInteractionError("campos básicos", "preencher", str(e))

    def _remove_readonly_if_exists(self, by, locator):
        """Remove o atributo 'readonly' de um campo, se ele estiver presente."""
        try:
            element = self.driver.find_element(by, locator)
            self.driver.execute_script("arguments[0].removeAttribute('readonly')", element)
        except Exception:
            pass


    def _handle_username_setup(self):
        """Gerencia o processo de configuração do username."""
        try:
            logger.info(" Iniciando configuração do username...")

            #  Verificar se há tela de sugestões
            try:
                if self._is_username_suggestion_screen():
                    logger.info("[OK] Tela de sugestões detectada. Tentando selecionar 'Create your own Gmail address'...")
                    self._handle_username_suggestions()
                else:
                    logger.info("[OK] Tela de sugestões NÃO apareceu. Continuando normalmente...")
            except Exception as e:
                logger.warning(f"[AVISO] Erro ao verificar tela de sugestões: {e}")

            #  Configurar o username
            if not self._set_username():
                raise UsernameError("[ERRO] Falha ao configurar um username válido.")

            logger.info("[OK] Username configurado com sucesso!")

        except UsernameError as e:
            logger.error(f"[ERRO] Erro ao configurar username: {e}")
            raise e

        except Exception as e:
            logger.error(f"[AVISO] Erro inesperado ao configurar username: {e}")
            raise UsernameError(f"Erro inesperado ao configurar username: {str(e)}")

    
    def _is_username_suggestion_screen(self) -> bool:
        """Verifica se a tela de sugestões de username foi carregada."""
        try:
            self.wait.until(
                EC.presence_of_element_located((By.XPATH, username_locators.SUGGESTION_OPTION))
            )
            return True
        except TimeoutException:
            return False  # Se não apareceu, seguimos direto para a digitação do username


    def _handle_username_suggestions(self):
        """Trata a tela de sugestões de username e seleciona 'Create your own Gmail address'."""
        try:
            suggestion_option_xpath = "//*[@id='yDmH0d']/c-wiz/div/div[2]/div/div/div/form/span/section/div/div/div[1]/div[1]/div/span/div[3]/div"
            
            logger.info(" Verificando tela de sugestões de username...")

            # Aguarda até 5 segundos para detectar se a tela de sugestões está visível
            if self._element_exists(suggestion_option_xpath, timeout=5):
                logger.info("[OK] Tela de sugestões detectada. Tentando selecionar 'Create your own Gmail address'...")

                suggestion_option = self.wait.until(EC.element_to_be_clickable((By.XPATH, suggestion_option_xpath)))

                #  Verifica se o elemento está visível e interagível
                if suggestion_option.is_displayed() and suggestion_option.is_enabled():
                    try:
                        #  Tenta clicar normalmente
                        suggestion_option.click()
                    except:
                        #  Se falhar, tenta clicar via JavaScript
                        logger.warning("[AVISO] Clique padrão falhou, tentando via JavaScript...")
                        self.driver.execute_script("arguments[0].click();", suggestion_option)

                    logger.info("[OK] Opção 'Create your own Gmail address' selecionada.")
                    time.sleep(2)  # Pequeno delay para garantir que a nova tela carregue
                else:
                    logger.error("[ERRO] O elemento 'Create your own Gmail address' não está visível ou interagível.")

            else:
                logger.info("[OK] Tela de sugestões de username NÃO apareceu. Continuando normalmente...")
        except Exception as e:
            logger.error(f"[ERRO] Erro ao tentar selecionar a opção 'Create your own Gmail address': {e}")




    def _set_username(self) -> bool:
        """Configura o username e verifica disponibilidade. Se já existir, tenta outro automaticamente."""
        username_taken_xpath = username_locators.USERNAME_TAKEN_ERROR  # XPath da mensagem de erro
        max_attempts = account_config.MAX_USERNAME_ATTEMPTS  # Número máximo de tentativas
        
        for attempt in range(max_attempts):
            try:
                #  1. Aguarda o campo de username estar visível e interativo
                username_field = self.wait.until(EC.presence_of_element_located((By.XPATH, username_locators.USERNAME_FIELD)))
                self.wait.until(EC.element_to_be_clickable((By.XPATH, username_locators.USERNAME_FIELD)))

                self.driver.execute_script("arguments[0].scrollIntoView();", username_field)
                self.driver.execute_script("arguments[0].click();", username_field)

                #  2. Gera novo username se não for a primeira tentativa
                if attempt > 0:
                    self.account_info.username = self._generate_new_username()
                    logger.warning(f"[AVISO] Tentativa {attempt}: Username já estava em uso. Tentando {self.account_info.username}")

                #  3. Insere o username e clica em "Next"
                username_field.clear()
                username_field.send_keys(self.account_info.username)
                logger.info(f"[OK] Tentativa {attempt}: Testando username {self.account_info.username}")

                self._click_next()
                time.sleep(2)  # Aguarda verificação

                #  4. Verifica se a mensagem "That username is taken" aparece
                try:
                    self.wait.until(EC.presence_of_element_located((By.XPATH, username_taken_xpath)))
                    logger.warning("[AVISO] Nome de usuário já está em uso. Tentando outro...")
                    continue  # Tenta novamente com um novo username
                except TimeoutException:
                    logger.info("[OK] Username aceito!")
                    return True  # Adicionado return True explícito aqui

            except TimeoutException:
                logger.error("[ERRO] Erro: Campo de username não encontrado!")
                raise UsernameError(" Campo de username não apareceu na tela.")

            except Exception as e:
                logger.warning(f"[AVISO] Erro ao preencher username: {str(e)}")

        raise UsernameError("[ALERTA] Número máximo de tentativas atingido. Não foi possível encontrar um username disponível.")



    def _check_username_taken(self, timeout=3) -> bool:
        """Verifica se o username já está em uso."""
        try:
            self.wait.until(
                EC.presence_of_element_located((By.XPATH, username_locators.USERNAME_TAKEN_ERROR))
            )
            return True  # Username está em uso
        except TimeoutException:
            return False  # Username está disponível

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
            raise ElementInteractionError("campos de senha", "preencher", str(e))

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
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(1)
                
                # Tentar JavaScript como fallback
                try:
                    self.driver.execute_script("arguments[0].click();", element)
                    logger.info(f"[OK] Clicou em {element_name} via JavaScript")
                except Exception as js_error:
                    logger.error(f"[ERRO] Falha ao clicar via JavaScript: {str(js_error)}")
                    
                    # Última tentativa usando Actions
                    from selenium.webdriver.common.action_chains import ActionChains
                    actions = ActionChains(self.driver)
                    actions.move_to_element(element).click().perform()
                    logger.info(f"[OK] Clicou em {element_name} via ActionChains")
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
            raise ElementInteractionError(f"campo {locator}", "preencher", str(e))

    def _generate_new_username(self):
        """Gera um novo username quando o atual não está disponível."""
        from automations.gmail_creator.data_generator import generate_gmail_credentials
        return generate_gmail_credentials()["username"]