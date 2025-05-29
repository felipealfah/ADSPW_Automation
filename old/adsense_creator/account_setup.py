from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any
import time
import logging
import random
import os
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, ElementNotInteractableException,
    NoSuchElementException, StaleElementReferenceException
)
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

from .exceptions import (
    AccountSetupError,
    LoginError,
    ElementInteractionError,
    NavigationError,
    ValidationError
)
from .config import timeouts, account_config
from .locators import login_locators, signup_locators

logger = logging.getLogger(__name__)

# Configuração para habilitar/desabilitar modo de debug com screenshots
DEBUG_MODE = False  # Habilitado para diagnóstico de problemas


class SetupState(Enum):
    """Estados possíveis da configuração da conta AdSense."""
    INITIAL = "initial"
    SIGNUP_FORM = "signup_form"
    WEBSITE_INFO = "website_info"
    ACCOUNT_INFO = "account_info"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AdSenseAccountInfo:
    """Armazena informações da conta durante o setup."""
    email: Optional[str] = None
    website_url: Optional[str] = None
    website_category: Optional[str] = None
    website_language: Optional[str] = None
    country: Optional[str] = None
    state: SetupState = SetupState.INITIAL


class AccountSetup:
    """
    Gerencia o processo de configuração inicial da conta AdSense.
    Responsável pelo login, preenchimento do formulário de inscrição e informações do site.
    """

    def __init__(self, driver, account_data):
        self.driver = driver
        self.account_data = account_data
        self.wait = WebDriverWait(driver, timeouts.DEFAULT_WAIT)
        self.state = SetupState.INITIAL
        self.adsense_info = self._create_account_info()
        self.max_retries = 3
        self.retry_delay = 2

        # Verificar se temos os dados necessários e, se não, tentar buscar do arquivo JSON
        if not self.account_data.get("password"):
            self._load_account_data_from_json()

    def _load_account_data_from_json(self):
        """Carrega dados da conta do arquivo JSON se necessário."""
        try:
            import json
            import os

            # Verificar se temos pelo menos o email para fazer a correspondência
            email = self.account_data.get("email")
            if not email:
                logger.warning(
                    "[AVISO] Email não fornecido, não é possível buscar dados do JSON")
                return

            # Caminho para o arquivo de credenciais
            credentials_path = "credentials/gmail.json"

            if os.path.exists(credentials_path):
                with open(credentials_path, "r") as file:
                    gmail_accounts = json.load(file)

                    # Buscar a conta pelo email
                    for account in gmail_accounts:
                        if account.get("email") == email:
                            # Atualizar os dados da conta com os dados do JSON
                            for key, value in account.items():
                                if key not in self.account_data or not self.account_data[key]:
                                    self.account_data[key] = value

                            logger.info(
                                f"[OK] Dados da conta atualizados a partir do arquivo JSON para o email: {email}")
                            return

                    logger.warning(
                        f"[AVISO] Email {email} não encontrado no arquivo JSON")
            else:
                logger.warning(
                    f"[AVISO] Arquivo de credenciais {credentials_path} não encontrado")

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao carregar dados da conta do arquivo JSON: {str(e)}")

    def _create_account_info(self) -> AdSenseAccountInfo:
        """Cria objeto AdSenseAccountInfo com os dados fornecidos."""
        country = self.account_data.get("country", "")
        logger.info(f"[INFO] País recebido nos parâmetros: {country}")

        return AdSenseAccountInfo(
            email=self.account_data.get("email", ""),
            website_url=self.account_data.get("website_url", ""),
            website_category=self.account_data.get("website_category", ""),
            website_language=self.account_data.get("website_language", ""),
            country=country,
        )

    def start_setup(self) -> bool:
        """Inicia o processo de configuração da conta AdSense."""
        try:
            logger.info("[INICIO] Iniciando configuração da conta AdSense...")

            # Verificar arquivo de credenciais para diagnóstico
            self._check_credentials_file()

            # Navegar para a página de inscrição do AdSense
            if not self._execute_with_retry(self._navigate_to_adsense_signup):
                return False

            # Verificar o estado atual após a navegação inicial
            # Se estamos em WEBSITE_INFO, significa que a conta já estava validada e fomos redirecionados
            if self.state == SetupState.WEBSITE_INFO:
                logger.info(
                    "[INFO] Conta já validada, pulando diretamente para o preenchimento das informações do site")

                # Pulando verificações de senha e telefone, indo direto para o preenchimento do site
                if not self._execute_with_retry(self._fill_website_info):
                    return False

            else:
                # Fluxo normal para contas novas
                # Verificar se estamos na tela de senha após navegação inicial
                self._execute_with_retry(self._handle_password_screen)
                logger.info(
                    "[INFO] Verificação de tela de senha após navegação inicial concluída")

                # Verificar se estamos na tela de verificação de telefone
                if self._check_for_phone_verification():
                    logger.info(
                        "[INFO] Tela de verificação de telefone detectada após navegação inicial")
                    if not self._handle_phone_verification():
                        logger.error(
                            "[ERRO] Falha na verificação de telefone após navegação inicial")
                        return False

                # Preencher o formulário de inscrição
                self.state = SetupState.SIGNUP_FORM
                if not self._execute_with_retry(self._complete_signup_form):
                    return False

                # Verificar se estamos na tela de senha após o formulário de inscrição
                self._execute_with_retry(self._handle_password_screen)
                logger.info(
                    "[INFO] Verificação de tela de senha após formulário de inscrição concluída")

                # Verificar novamente se estamos na tela de verificação de telefone
                if self._check_for_phone_verification():
                    logger.info(
                        "[INFO] Tela de verificação de telefone detectada após formulário de inscrição")
                    if not self._handle_phone_verification():
                        logger.error(
                            "[ERRO] Falha na verificação de telefone após formulário de inscrição")
                        return False

                # Preencher informações do site
                self.state = SetupState.WEBSITE_INFO
                if not self._execute_with_retry(self._fill_website_info):
                    return False

                # Verificar mais uma vez se estamos na tela de verificação de telefone
                if self._check_for_phone_verification():
                    logger.info(
                        "[INFO] Tela de verificação de telefone detectada após preenchimento de informações do site")
                    if not self._handle_phone_verification():
                        logger.error(
                            "[ERRO] Falha na verificação de telefone após preenchimento de informações do site")
                        return False

            # Parar aqui conforme solicitado - não prosseguir com as etapas seguintes
            logger.info(
                "[INFO] Automação pausada após preencher o campo de URL do site, conforme solicitado")
            self.state = SetupState.COMPLETED

            # Atualizar o arquivo de credenciais com as informações do AdSense
            self._update_credentials_file()

            return True

        except Exception as e:
            logger.error(
                f"[ERRO] Erro durante configuração da conta AdSense: {str(e)}")
            self.state = SetupState.FAILED
            raise AccountSetupError(
                f"Falha na configuração da conta: {str(e)}")

    def _check_credentials_file(self):
        """Verifica e registra informações sobre o arquivo de credenciais para diagnóstico."""
        try:
            import json
            import os

            credentials_path = "credentials/gmail.json"

            if not os.path.exists(credentials_path):
                logger.warning(
                    f"[DIAGNÓSTICO] Arquivo de credenciais {credentials_path} não encontrado")
                return

            if os.path.getsize(credentials_path) == 0:
                logger.warning(
                    f"[DIAGNÓSTICO] Arquivo de credenciais {credentials_path} está vazio")
                return

            with open(credentials_path, "r") as file:
                try:
                    gmail_accounts = json.load(file)

                    if not isinstance(gmail_accounts, list):
                        logger.warning(
                            f"[DIAGNÓSTICO] Arquivo de credenciais não contém uma lista válida")
                        return

                    account_count = len(gmail_accounts)
                    logger.info(
                        f"[DIAGNÓSTICO] Arquivo de credenciais contém {account_count} contas")

                    # Verificar se temos o email atual nas credenciais
                    email = self.account_data.get("email")
                    if email:
                        found = False
                        for account in gmail_accounts:
                            if account.get("email") == email:
                                found = True
                                has_password = bool(account.get("password"))
                                logger.info(
                                    f"[DIAGNÓSTICO] Email {email} encontrado no arquivo JSON. Tem senha: {has_password}")
                                break

                        if not found:
                            logger.warning(
                                f"[DIAGNÓSTICO] Email {email} NÃO encontrado no arquivo JSON")

                    # Verificar a primeira conta como exemplo
                    if account_count > 0:
                        first_account = gmail_accounts[0]
                        keys = list(first_account.keys())
                        logger.info(
                            f"[DIAGNÓSTICO] Campos disponíveis na primeira conta: {keys}")

                except json.JSONDecodeError:
                    logger.error(
                        f"[DIAGNÓSTICO] Arquivo de credenciais contém JSON inválido")

        except Exception as e:
            logger.error(
                f"[DIAGNÓSTICO] Erro ao verificar arquivo de credenciais: {str(e)}")

    def _execute_with_retry(self, func) -> bool:
        """Executa uma função com tentativas em caso de falha."""
        for attempt in range(1, self.max_retries + 1):
            try:
                return func()
            except (TimeoutException, ElementNotInteractableException,
                    NoSuchElementException, StaleElementReferenceException) as e:
                if attempt < self.max_retries:
                    logger.warning(
                        f"[AVISO] Tentativa {attempt} falhou: {str(e)}. Tentando novamente...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error(
                        f"[ERRO] Todas as {self.max_retries} tentativas falharam: {str(e)}")
                    return False
        return False

    def _navigate_to_adsense_signup(self) -> bool:
        """Navega para a página de inscrição do AdSense."""
        try:
            # Navegar para a URL específica de inscrição
            adsense_url = "https://adsense.google.com/adsense/signup?subid=in-en-dr-dr-sa-a-dr"
            logger.info(f"[INFO] Navegando para URL do AdSense: {adsense_url}")
            self.driver.get(adsense_url)

            # Aguardar carregamento da página
            time.sleep(5)
            self._wait_for_page_load()

            # Capturar screenshot para debug
            if DEBUG_MODE:
                self._save_screenshot("adsense_signup_page")

            # Verificar se estamos na tela de seleção de conta
            if self._check_for_account_selection_screen():
                logger.info("[INFO] Detectada tela de seleção de conta")
                if not self._select_account():
                    logger.warning("[AVISO] Falha ao selecionar conta")
                    return False
                # Aguardar após selecionar a conta
                time.sleep(3)
                self._wait_for_page_load()

                # Capturar screenshot após selecionar conta
                if DEBUG_MODE:
                    self._save_screenshot("after_account_selection")

                # Se estamos na página de criação de conta, pular recaptcha; senão, tratar
                current_url = self.driver.current_url
                if "/adsense/signup/create" in current_url:
                    logger.info("[INFO] Tela de criação do AdSense detectada, pulando recaptcha")
                else:
                    self._check_and_handle_recaptcha()

                # Verificar se após selecionar a conta fomos redirecionados diretamente para a tela principal do AdSense
                current_url = self.driver.current_url
                logger.info(f"[INFO] URL após seleção de conta: {current_url}")

                # Se estiver na página de criação (preenchimento de URL) ou já validada
                if "/adsense/signup/create" in current_url or ("adsense.google.com/adsense" in current_url and "signup" not in current_url):
                    logger.info(
                        "[INFO] Detectado redirecionamento direto para a tela de criação/prenchimento do AdSense (conta já está validada)")
                    # Indicar que a conta já está validada e pular inscrição
                    self.state = SetupState.WEBSITE_INFO
                    logger.info(
                        "[INFO] Pulando tela de inscrição inicial, conta já está validada")
                    return True

            # Registrar URL atual para debug
            current_url = self.driver.current_url
            logger.info(f"[INFO] URL atual após navegação: {current_url}")

            logger.info(
                "[OK] Navegação para página de inscrição do AdSense concluída")
            return True

        except Exception as e:
            logger.error(f"[ERRO] Falha na navegação para AdSense: {str(e)}")
            raise NavigationError(
                f"Falha ao navegar para a página do AdSense: {str(e)}")

    def _wait_for_page_load(self, timeout=10):
        """Aguarda o carregamento da página."""
        try:
            # Esperar até que o readyState do documento seja "complete"
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script(
                    "return document.readyState") == "complete"
            )
            return True
        except Exception:
            logger.warning(
                "[AVISO] Timeout ao aguardar carregamento da página")
            return False

    def _complete_signup_form(self) -> bool:
        """Preenche o formulário inicial de inscrição no AdSense."""
        try:
            # Verificar se estamos na página de inscrição correta
            if "adsense/signup" not in self.driver.current_url:
                logger.info(
                    "[AVISO] Não estamos na página de inscrição, redirecionando...")
                adsense_url = "https://adsense.google.com/adsense/signup?subid=in-en-dr-dr-sa-a-dr"
                self.driver.get(adsense_url)
                self._wait_for_page_load()
                time.sleep(3)

                # Verificar se estamos na tela de seleção de conta após redirecionamento
                if self._check_for_account_selection_screen():
                    logger.info(
                        "[INFO] Detectada tela de seleção de conta após redirecionamento")
                    if not self._select_account():
                        logger.warning("[AVISO] Falha ao selecionar conta")
                        return False
                    # Aguardar após selecionar a conta
                    time.sleep(3)
                    self._wait_for_page_load()

                    # Verificar e tratar recaptcha se necessário
                    self._check_and_handle_recaptcha()

            # Verificar e tratar recaptcha novamente se necessário
            self._check_and_handle_recaptcha()

            # Capturar screenshot para debug
            if DEBUG_MODE:
                self._save_screenshot("signup_form_initial")

            # Não verificamos termos nem clicamos em botões - vamos direto para o preenchimento do site
            logger.info(
                "[OK] Formulário inicial de inscrição processado com sucesso")
            return True

        except Exception as e:
            logger.error(
                f"[ERRO] Falha ao preencher formulário de inscrição: {str(e)}")
            raise AccountSetupError(
                f"Falha ao preencher formulário de inscrição: {str(e)}")

    def _fill_website_info(self) -> bool:
        """Preenche as informações do site no formulário do AdSense."""
        try:
            # Esperar o formulário carregar
            time.sleep(5)

            # Verificar status de recaptcha somente se não estivermos na tela de criação (URL)
            current_url = self.driver.current_url
            if "/adsense/signup/create" not in current_url:
                self._check_and_handle_recaptcha()

            logger.info("[INFO] Preenchendo o campo de URL do site...")

            # Capturar URL atual para debug
            current_url = self.driver.current_url
            logger.info(f"[INFO] URL atual: {current_url}")

            # Capturar screenshot para debug
            if DEBUG_MODE:
                self._save_screenshot("website_info_form")

            # Usar o localizador específico para o campo de URL do site
            site_url_xpath = signup_locators.WEBSITE_URL_FIELD_SPECIFIC

            # Preencher URL do site
            try:
                website_url_field = self.driver.find_element(
                    By.XPATH, site_url_xpath)
                website_url_field.clear()
                self._fill_input_safely(
                    website_url_field, self.adsense_info.website_url)
                logger.info(
                    f"[OK] URL do site preenchida: {self.adsense_info.website_url}")

                # Capturar screenshot após preencher
                if DEBUG_MODE:
                    self._save_screenshot("website_url_filled")

                # Selecionar a opção "Não quero receber ajuda personalizada e sugestões de desempenho"
                disable_emails_xpath = signup_locators.EMAIL_PREFERENCES_DISABLE_RADIO

                try:
                    # Aguardar um pouco para garantir que o elemento esteja visível
                    time.sleep(2)

                    # Método 1: Tentar com XPath específico
                    if self._check_for_element(By.XPATH, disable_emails_xpath, timeout=5):
                        # Clicar na opção para desabilitar emails
                        disable_emails_radio = self.driver.find_element(
                            By.XPATH, disable_emails_xpath)
                        if self._click_safely(disable_emails_radio):
                            logger.info(
                                "[OK] Opção 'Não quero receber ajuda personalizada' selecionada via XPath específico")
                        else:
                            logger.warning(
                                "[AVISO] Falha ao clicar na opção via XPath específico")
                    else:
                        # Método 2: Tentar encontrar pelo texto da label
                        label_text = "Não quero receber ajuda personalizada"
                        label_xpath = f"//label[contains(text(), '{label_text}')]"

                        if self._check_for_element(By.XPATH, label_xpath, timeout=3):
                            label_element = self.driver.find_element(
                                By.XPATH, label_xpath)
                            # Clicar na label para selecionar o radio
                            if self._click_safely(label_element):
                                logger.info(
                                    f"[OK] Opção '{label_text}' selecionada via texto da label")
                            else:
                                logger.warning(
                                    f"[AVISO] Falha ao clicar na opção via texto da label")
                        else:
                            # Método 3: Tentar encontrar pelo atributo trackclick
                            disable_emails_attr = signup_locators.EMAIL_PREFERENCES_DISABLE_BY_ATTR

                            if self._check_for_element(By.XPATH, disable_emails_attr, timeout=3):
                                disable_attr_element = self.driver.find_element(
                                    By.XPATH, disable_emails_attr)
                                if self._click_safely(disable_attr_element):
                                    logger.info(
                                        "[OK] Opção para desabilitar emails selecionada via atributo trackclick")
                                else:
                                    logger.warning(
                                        "[AVISO] Falha ao clicar na opção via atributo trackclick")
                            else:
                                # Método 4: Tentar encontrar pela classe
                                class_selector = signup_locators.EMAIL_PREFERENCES_DISABLE_BY_CLASS

                                if self._check_for_element(By.XPATH, class_selector, timeout=3):
                                    class_element = self.driver.find_element(
                                        By.XPATH, class_selector)
                                    if self._click_safely(class_element):
                                        logger.info(
                                            "[OK] Opção para desabilitar emails selecionada via classe")
                                    else:
                                        logger.warning(
                                            "[AVISO] Falha ao clicar na opção via classe")
                                else:
                                    logger.warning(
                                        "[AVISO] Não foi possível encontrar a opção de preferência de email por nenhum método")

                    # Capturar screenshot após tentar selecionar a opção
                    if DEBUG_MODE:
                        self._save_screenshot("email_preference_selected")
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro ao selecionar preferência de email: {str(e)}")
                    # Não interromper o fluxo se falhar aqui

                # Selecionar país/território no dropdown
                try:
                    # Verificar se temos o país definido nos parâmetros
                    country = self.adsense_info.country
                    if country:
                        # Usar o método auxiliar para selecionar o país
                        if self._select_country_from_dropdown(country):
                            logger.info(
                                f"[OK] País '{country}' selecionado com sucesso")
                        else:
                            logger.warning(
                                f"[AVISO] Não foi possível selecionar o país '{country}'")
                    else:
                        logger.info(
                            "[INFO] Parâmetro de país não fornecido, pulando seleção")

                    # Capturar screenshot após tentar selecionar o país
                    if DEBUG_MODE:
                        self._save_screenshot("country_selection")
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro ao selecionar país/território: {str(e)}")
                    # Não interromper o fluxo se falhar aqui

                # Marcar o checkbox de aceitação dos termos
                try:
                    # Pequena pausa para garantir que a página foi atualizada após selecionar o país
                    time.sleep(2)

                    # Marcar o checkbox usando o método auxiliar
                    if self._check_terms_checkbox():
                        logger.info(
                            "[OK] Checkbox de aceitação dos termos marcado com sucesso")
                    else:
                        logger.warning(
                            "[AVISO] Não foi possível marcar o checkbox de aceitação dos termos")

                    # Capturar screenshot após tentar marcar o checkbox
                    if DEBUG_MODE:
                        self._save_screenshot("terms_checkbox_checked")
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro ao marcar checkbox de aceitação dos termos: {str(e)}")
                    # Não interromper o fluxo se falhar aqui

                # Clicar no botão de OK para criar a conta
                try:
                    # Pequena pausa para garantir que a página foi atualizada após marcar o checkbox
                    time.sleep(2)

                    # Clicar no botão de OK usando o método auxiliar
                    if self._click_ok_button():
                        logger.info(
                            "[OK] Botão de OK clicado com sucesso para criar a conta")
                    else:
                        logger.warning(
                            "[AVISO] Não foi possível clicar no botão de OK")

                    # Capturar screenshot após tentar clicar no botão
                    if DEBUG_MODE:
                        self._save_screenshot("after_ok_button_click")
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro ao clicar no botão de OK: {str(e)}")
                    # Não interromper o fluxo se falhar aqui

                # Parar a automação aqui, sem fechar o navegador
                logger.info(
                    "[INFO] Automação pausada após preencher o formulário")
                return True
            except Exception as e:
                logger.error(
                    f"[ERRO] Falha ao preencher campo de URL do site: {str(e)}")
                if DEBUG_MODE:
                    self._save_screenshot("website_url_field_error")
                return False

        except Exception as e:
            logger.error(
                f"[ERRO] Falha ao preencher informações do site: {str(e)}")
            if DEBUG_MODE:
                self._save_screenshot("website_info_error")
            return False

    def _check_for_additional_account_fields(self):
        """Verifica e preenche campos adicionais que possam existir no formulário de conta."""
        # Lista de possíveis campos adicionais (nome:xpath:valor_padrão)
        additional_fields = {
            "company_name": ("//input[contains(@aria-labelledby, 'company') or contains(@placeholder, 'company')]",
                             "My Company"),
            "tax_id": ("//input[contains(@aria-labelledby, 'tax') or contains(@placeholder, 'tax')]",
                       "123456789"),
            "timezone": ("//div[contains(@role, 'combobox') and contains(@aria-labelledby, 'timezone')]",
                         None)  # Será tratado separadamente
        }

        for field_name, (xpath, default_value) in additional_fields.items():
            try:
                if field_name == "timezone" and default_value is None:
                    # Tratamento especial para dropdown de timezone
                    if self._check_for_element(By.XPATH, xpath):
                        self._select_random_option(
                            xpath, "//li[@role='option']")
                        logger.info(
                            f"[OK] Campo adicional '{field_name}' preenchido com opção aleatória")
                else:
                    # Campos de texto normais
                    field = self._check_and_find_element(By.XPATH, xpath)
                    if field and not field.get_attribute("value") and default_value:
                        self._fill_input_safely(field, default_value)
                        logger.info(
                            f"[OK] Campo adicional '{field_name}' preenchido com: {default_value}")
            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao verificar/preencher campo adicional '{field_name}': {str(e)}")

    # Métodos auxiliares

    def _check_for_element(self, by, locator, timeout=5) -> bool:
        """Verifica se um elemento existe na página."""
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, locator)))
            return True
        except (TimeoutException, NoSuchElementException):
            return False

    def _check_and_find_element(self, by, locator, timeout=5):
        """Verifica se um elemento existe e retorna-o se encontrado."""
        if self._check_for_element(by, locator, timeout):
            return self.driver.find_element(by, locator)
        return None

    def _get_next_or_continue_button(self):
        """Localiza e retorna o botão Next ou Continue na página atual."""
        # Tentar Next
        next_button = self._check_and_find_element(
            By.XPATH, signup_locators.NEXT_BUTTON)
        if next_button:
            return next_button

        # Tentar Continue
        continue_button = self._check_and_find_element(
            By.XPATH, signup_locators.CONTINUE_BUTTON)
        if continue_button:
            return continue_button

        # Tentar Save
        save_button = self._check_and_find_element(
            By.XPATH, signup_locators.SAVE_BUTTON)
        if save_button:
            return save_button

        # Última tentativa - qualquer botão tipo submit
        submit_button = self._check_and_find_element(
            By.XPATH, "//button[@type='submit']")
        return submit_button

    def _fill_input_safely(self, element, text):
        """Preenche um campo de entrada com texto de forma segura e realista."""
        try:
            element.clear()
            # Digite caractere por caractere com pequenas pausas para simular digitação humana
            for char in text:
                element.send_keys(char)
                # Pausa aleatória entre caracteres
                time.sleep(random.uniform(0.05, 0.15))

            # Pequena pausa após terminar de digitar
            time.sleep(0.3)
            return True
        except Exception as e:
            logger.error(f"[ERRO] Falha ao preencher campo: {str(e)}")
            raise ElementInteractionError(
                f"Falha ao preencher campo: {str(e)}")

    def _select_from_dropdown(self, dropdown_locator, options_locator, target_value):
        """Seleciona uma opção específica em um dropdown."""
        try:
            # Clicar no dropdown para abrir
            dropdown = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, dropdown_locator)))
            dropdown.click()
            time.sleep(1)

            # Encontrar todas as opções
            options = self.driver.find_elements(By.XPATH, options_locator)

            # Procurar a opção desejada
            for option in options:
                if target_value.lower() in option.text.lower():
                    option.click()
                    time.sleep(1)
                    return True

            # Se não encontrou a opção exata, selecionar a primeira
            if options:
                options[0].click()
                time.sleep(1)
                return True

            logger.warning(
                f"[AVISO] Opção '{target_value}' não encontrada no dropdown")
            return False

        except Exception as e:
            logger.error(
                f"[ERRO] Falha ao selecionar opção no dropdown: {str(e)}")
            raise ElementInteractionError(
                f"Falha ao selecionar opção no dropdown: {str(e)}")

    def _select_random_option(self, dropdown_locator, options_locator):
        """Seleciona uma opção aleatória em um dropdown."""
        try:
            # Clicar no dropdown para abrir
            dropdown = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, dropdown_locator)))
            dropdown.click()
            time.sleep(1)

            # Encontrar todas as opções
            options = self.driver.find_elements(By.XPATH, options_locator)

            # Selecionar uma opção aleatória
            if options:
                random_option = random.choice(options)
                random_option.click()
                time.sleep(1)
                return True

            logger.warning("[AVISO] Nenhuma opção encontrada no dropdown")
            return False

        except Exception as e:
            logger.error(
                f"[ERRO] Falha ao selecionar opção aleatória no dropdown: {str(e)}")
            raise ElementInteractionError(
                f"Falha ao selecionar opção aleatória no dropdown: {str(e)}")

    def _select_preferred_option(self, dropdown_locator, options_locator, preferred_values):
        """Seleciona uma das opções preferidas se disponível, ou uma aleatória."""
        try:
            # Clicar no dropdown para abrir
            dropdown = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, dropdown_locator)))
            dropdown.click()
            time.sleep(1)

            # Encontrar todas as opções
            options = self.driver.find_elements(By.XPATH, options_locator)

            # Procurar as opções preferidas na ordem
            for preferred in preferred_values:
                for option in options:
                    if preferred.lower() in option.text.lower():
                        option.click()
                        time.sleep(1)
                        return True

            # Se não encontrou nenhuma das preferidas, selecionar uma aleatória
            if options:
                random_option = random.choice(options)
                random_option.click()
                time.sleep(1)
                return True

            logger.warning("[AVISO] Nenhuma opção encontrada no dropdown")
            return False

        except Exception as e:
            logger.error(
                f"[ERRO] Falha ao selecionar opção preferida no dropdown: {str(e)}")
            raise ElementInteractionError(
                f"Falha ao selecionar opção preferida no dropdown: {str(e)}")

    def _save_screenshot(self, name):
        """Salva screenshot para debug se DEBUG_MODE estiver ativo."""
        if DEBUG_MODE:
            try:
                # Criar diretório de screenshots se não existir
                screenshots_dir = "screenshots"
                if not os.path.exists(screenshots_dir):
                    os.makedirs(screenshots_dir)
                    logger.info(
                        f"[DEBUG] Diretório de screenshots criado: {screenshots_dir}")

                # Gerar nome de arquivo com timestamp
                filename = f"{screenshots_dir}/adsense_{name}_{time.strftime('%Y%m%d_%H%M%S')}.png"

                # Salvar screenshot
                self.driver.save_screenshot(filename)
                logger.info(f"[DEBUG] Screenshot salvo em {filename}")

                # Registrar resolução e tamanho da janela para diagnóstico
                window_size = self.driver.get_window_size()
                logger.info(f"[DEBUG] Tamanho da janela: {window_size}")

                return filename
            except Exception as e:
                logger.error(f"[ERRO] Falha ao salvar screenshot: {str(e)}")
                # Não lançar exceção para não interromper o fluxo principal
                return None

    def _check_for_account_selection_screen(self) -> bool:
        """Verifica se estamos na tela de seleção de conta."""
        try:
            # Lista de possíveis textos para "Escolha uma conta" em diferentes idiomas
            account_selection_texts = [
                "Escolha uma conta",  # Português
                "Choose an account",  # Inglês
                "Elige una cuenta",   # Espanhol
                "Choisissez un compte",  # Francês
                "Konto auswählen"     # Alemão
            ]

            # Verificar pelo título da página
            for text in account_selection_texts:
                xpath = f"//div[contains(text(), '{text}')]"
                if self._check_for_element(By.XPATH, xpath, timeout=3):
                    logger.info(
                        f"[INFO] Detectada tela de seleção de conta com texto: '{text}'")
                    return True

            # Verificar pela estrutura da página (lista de contas)
            account_list_xpath = "//div[contains(@class, 'LbOduc')]"
            if self._check_for_element(By.XPATH, account_list_xpath, timeout=3):
                logger.info("[INFO] Detectada lista de contas para seleção")
                return True

            return False
        except Exception as e:
            logger.warning(
                f"[AVISO] Erro ao verificar tela de seleção de conta: {str(e)}")
            return False

    def _select_account(self) -> bool:
        """Seleciona a conta na tela de seleção de contas."""
        try:
            # Tentar o XPath específico fornecido
            specific_xpath = signup_locators.ACCOUNT_SELECTION_FIRST
            if self._check_for_element(By.XPATH, specific_xpath, timeout=5):
                account_element = self.driver.find_element(
                    By.XPATH, specific_xpath)
                if self._click_safely(account_element):
                    logger.info(
                        "[OK] Conta selecionada usando XPath específico")
                    return True
                else:
                    logger.warning(
                        "[AVISO] Falha ao clicar na conta usando XPath específico")

            # Se o XPath específico falhar, tentar abordagens mais genéricas

            # Tentar encontrar pelo email (se tivermos um email específico para selecionar)
            if self.account_data.get("email"):
                email = self.account_data.get("email")
                email_xpath = f"//div[@data-email='{email}' or contains(text(), '{email}')]"
                if self._check_for_element(By.XPATH, email_xpath, timeout=3):
                    email_element = self.driver.find_element(
                        By.XPATH, email_xpath)
                    # Clicar no elemento pai que contém o email
                    parent = email_element.find_element(By.XPATH, "..")
                    if self._click_safely(parent):
                        logger.info(
                            f"[OK] Conta com email '{email}' selecionada")
                        return True
                    else:
                        logger.warning(
                            f"[AVISO] Falha ao clicar na conta com email '{email}'")

            # Tentar selecionar a primeira conta da lista (fallback)
            accounts_xpath = signup_locators.ACCOUNT_SELECTION_CONTAINER
            if self._check_for_element(By.XPATH, accounts_xpath, timeout=3):
                accounts = self.driver.find_elements(By.XPATH, accounts_xpath)
                if accounts:
                    if self._click_safely(accounts[0]):
                        logger.info("[OK] Primeira conta da lista selecionada")
                        return True
                    else:
                        logger.warning(
                            "[AVISO] Falha ao clicar na primeira conta da lista")

            # Se ainda não conseguiu, tentar um XPath mais genérico para o primeiro item da lista
            first_account_xpath = "//ul/li[1]/div"
            if self._check_for_element(By.XPATH, first_account_xpath, timeout=3):
                first_account = self.driver.find_element(
                    By.XPATH, first_account_xpath)
                if self._click_safely(first_account):
                    logger.info(
                        "[OK] Primeira conta selecionada usando XPath genérico")
                    return True
                else:
                    logger.warning(
                        "[AVISO] Falha ao clicar na primeira conta usando XPath genérico")

            logger.warning("[AVISO] Não foi possível selecionar uma conta")
            return False
        except Exception as e:
            logger.error(f"[ERRO] Falha ao selecionar conta: {str(e)}")
            if DEBUG_MODE:
                self._save_screenshot("account_selection_error")
            return False

    def _click_safely(self, element):
        """Tenta clicar em um elemento de várias formas para garantir que o clique funcione."""
        try:
            # Método 1: Clique normal
            element.click()
            return True
        except Exception as e1:
            logger.warning(
                f"[AVISO] Clique normal falhou: {str(e1)}, tentando alternativas...")

            try:
                # Método 2: Clique via JavaScript
                self.driver.execute_script("arguments[0].click();", element)
                logger.info("[INFO] Clique via JavaScript executado")
                return True
            except Exception as e2:
                logger.warning(
                    f"[AVISO] Clique via JavaScript falhou: {str(e2)}, tentando alternativas...")

                try:
                    # Método 3: Mover para o elemento e clicar
                    actions = ActionChains(self.driver)
                    actions.move_to_element(element).click().perform()
                    logger.info("[INFO] Clique via ActionChains executado")
                    return True
                except Exception as e3:
                    logger.error(
                        f"[ERRO] Todos os métodos de clique falharam: {str(e3)}")
                    return False

    def _select_country_from_dropdown(self, country: str) -> bool:
        """
        Seleciona um país específico no dropdown de país/território.

        Args:
            country: Nome do país a ser selecionado

        Returns:
            bool: True se o país foi selecionado com sucesso
        """
        if not country:
            logger.info("[INFO] Nenhum país especificado para seleção")
            return False

        try:
            logger.info(
                f"[INFO] Tentando selecionar país/território: {country}")

            # Aguardar um pouco para garantir que o elemento esteja visível
            time.sleep(2)

            # Usar o localizador do dropdown de país/território
            country_dropdown_xpath = signup_locators.COUNTRY_DROPDOWN

            # Verificar se o dropdown está presente
            if not self._check_for_element(By.XPATH, country_dropdown_xpath, timeout=5):
                logger.warning(
                    "[AVISO] Dropdown de país/território não encontrado")
                return False

            # Clicar no dropdown para abri-lo
            country_dropdown = self.driver.find_element(
                By.XPATH, country_dropdown_xpath)
            if not self._click_safely(country_dropdown):
                logger.warning(
                    "[AVISO] Falha ao clicar no dropdown de país/território")
                return False

            logger.info("[OK] Dropdown de país/território aberto")

            # Aguardar a lista de países aparecer
            time.sleep(2)

            # Tentar diferentes estratégias para encontrar o país
            country_found = False

            # Estratégia 1: Procurar pelo texto exato
            country_item_xpath = f"//material-select-dropdown-item/span[contains(text(), '{country}')]"
            if self._check_for_element(By.XPATH, country_item_xpath, timeout=3):
                country_item = self.driver.find_element(
                    By.XPATH, country_item_xpath)
                if self._click_safely(country_item):
                    logger.info(
                        f"[OK] País '{country}' selecionado pelo texto exato")
                    return True
                else:
                    logger.warning(
                        f"[AVISO] Falha ao clicar no país '{country}'")

            # Estratégia 2: Procurar por texto parcial (case insensitive)
            items_xpath = signup_locators.COUNTRY_OPTIONS
            if self._check_for_element(By.XPATH, items_xpath, timeout=3):
                items = self.driver.find_elements(By.XPATH, items_xpath)
                for item in items:
                    try:
                        item_text = item.text.strip().lower()
                        if country.lower() in item_text or item_text in country.lower():
                            if self._click_safely(item):
                                logger.info(
                                    f"[OK] País '{item_text}' selecionado por correspondência parcial")
                                return True
                    except Exception:
                        continue

            # Estratégia 3: Selecionar o primeiro país da lista se não encontrou o especificado
            first_item_xpath = signup_locators.COUNTRY_FIRST_OPTION
            if self._check_for_element(By.XPATH, first_item_xpath, timeout=3):
                first_item = self.driver.find_element(
                    By.XPATH, first_item_xpath)
                first_country = first_item.text.strip()
                if self._click_safely(first_item):
                    logger.info(
                        f"[OK] Primeiro país da lista '{first_country}' selecionado como fallback")
                    return True
                else:
                    logger.warning(
                        "[AVISO] Falha ao clicar no primeiro país da lista")

            # Se chegou aqui, não conseguiu selecionar nenhum país
            logger.warning("[AVISO] Não foi possível selecionar nenhum país")

            # Tentar fechar o dropdown clicando fora dele
            try:
                body = self.driver.find_element(By.TAG_NAME, "body")
                body.click()
                logger.info("[INFO] Dropdown fechado após falha na seleção")
            except Exception:
                pass

            return False
        except Exception as e:
            logger.warning(
                f"[AVISO] Erro ao selecionar país/território: {str(e)}")
            return False

    def _check_terms_checkbox(self) -> bool:
        """
        Marca o checkbox de aceitação dos termos do contrato.

        Returns:
            bool: True se o checkbox foi marcado com sucesso
        """
        try:
            logger.info(
                "[INFO] Tentando marcar o checkbox de aceitação dos termos")

            # Aguardar um pouco para garantir que o elemento esteja visível
            time.sleep(2)

            # Usar o localizador específico do checkbox
            checkbox_xpath = signup_locators.TERMS_CHECKBOX

            # Verificar se o checkbox está presente
            if not self._check_for_element(By.XPATH, checkbox_xpath, timeout=5):
                logger.warning(
                    "[AVISO] Checkbox de aceitação dos termos não encontrado pelo XPath específico")

                # Tentar abordagens alternativas
                # Método 2: Procurar por qualquer checkbox na página
                alt_xpath = signup_locators.ACCEPT_TERMS_CHECKBOX
                if not self._check_for_element(By.XPATH, alt_xpath, timeout=3):
                    logger.warning(
                        "[AVISO] Nenhum checkbox encontrado na página")
                    return False
                else:
                    checkbox_xpath = alt_xpath
                    logger.info(
                        "[INFO] Checkbox encontrado usando seletor alternativo")

            # Obter o elemento do checkbox
            checkbox = self.driver.find_element(By.XPATH, checkbox_xpath)

            # Estratégia 1: Tentar clicar diretamente no checkbox
            if self._click_safely(checkbox):
                logger.info(
                    "[OK] Checkbox marcado com sucesso usando clique direto")

                # Verificar se o checkbox foi realmente marcado
                try:
                    # Aguardar um momento para que a UI atualize
                    time.sleep(1)

                    # Capturar screenshot para verificação
                    if DEBUG_MODE:
                        self._save_screenshot("checkbox_checked")

                    return True
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro ao verificar se o checkbox foi marcado: {str(e)}")

            # Estratégia 2: Tentar clicar usando JavaScript diretamente
            try:
                self.driver.execute_script("arguments[0].click();", checkbox)
                logger.info(
                    "[OK] Checkbox marcado com sucesso usando JavaScript direto")
                time.sleep(1)
                return True
            except Exception as e:
                logger.warning(
                    f"[AVISO] Falha ao clicar no checkbox usando JavaScript direto: {str(e)}")

            # Estratégia 3: Tentar clicar no input dentro do checkbox
            try:
                input_xpath = signup_locators.TERMS_CHECKBOX_INPUT
                if self._check_for_element(By.XPATH, input_xpath, timeout=3):
                    input_element = self.driver.find_element(
                        By.XPATH, input_xpath)
                    self.driver.execute_script(
                        "arguments[0].click();", input_element)
                    logger.info(
                        "[OK] Checkbox marcado com sucesso clicando no input interno")
                    time.sleep(1)
                    return True
            except Exception as e:
                logger.warning(
                    f"[AVISO] Falha ao clicar no input do checkbox: {str(e)}")

            # Estratégia 4: Tentar usar send_keys com espaço
            try:
                checkbox.send_keys(Keys.SPACE)
                logger.info(
                    "[OK] Checkbox marcado com sucesso usando send_keys com espaço")
                time.sleep(1)
                return True
            except Exception as e:
                logger.warning(
                    f"[AVISO] Falha ao marcar checkbox usando send_keys: {str(e)}")

            # Estratégia 5: Tentar usar ActionChains
            try:
                actions = ActionChains(self.driver)
                actions.move_to_element(checkbox).click().perform()
                logger.info(
                    "[OK] Checkbox marcado com sucesso usando ActionChains")
                time.sleep(1)
                return True
            except Exception as e:
                logger.warning(
                    f"[AVISO] Falha ao marcar checkbox usando ActionChains: {str(e)}")

            logger.warning(
                "[AVISO] Todas as tentativas de marcar o checkbox falharam")
            return False
        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao tentar marcar o checkbox de aceitação dos termos: {str(e)}")
            return False

    def _click_ok_button(self) -> bool:
        """
        Clica no botão de OK que cria a conta.

        Returns:
            bool: True se o botão foi clicado com sucesso
        """
        try:
            logger.info(
                "[INFO] Tentando clicar no botão de OK para criar a conta")

            # Aguardar um pouco para garantir que o elemento esteja visível
            time.sleep(2)

            # Usar os localizadores para o botão de OK
            ripple_xpath = signup_locators.OK_BUTTON_RIPPLE
            button_xpath = signup_locators.OK_BUTTON

            # Estratégia 1: Tentar clicar no botão pai
            if self._check_for_element(By.XPATH, button_xpath, timeout=5):
                button = self.driver.find_element(By.XPATH, button_xpath)

                # Verificar se o botão está habilitado
                if not button.is_enabled():
                    logger.warning(
                        "[AVISO] Botão de OK encontrado, mas está desabilitado")
                    # Tentar clicar mesmo assim usando JavaScript
                else:
                    # Tentar clicar normalmente
                    if self._click_safely(button):
                        logger.info("[OK] Botão de OK clicado com sucesso")

                        # Aguardar um momento para que a ação seja processada
                        time.sleep(3)
                        self._wait_for_page_load()

                        # Capturar screenshot após clicar no botão
                        if DEBUG_MODE:
                            self._save_screenshot("after_ok_button")

                        return True

                # Se o clique normal falhou ou o botão está desabilitado, tentar com JavaScript
                try:
                    self.driver.execute_script("arguments[0].click();", button)
                    logger.info(
                        "[OK] Botão de OK clicado com sucesso usando JavaScript")
                    time.sleep(3)
                    self._wait_for_page_load()

                    if DEBUG_MODE:
                        self._save_screenshot("after_ok_button_js")

                    return True
                except Exception as js_e:
                    logger.warning(
                        f"[AVISO] Falha ao clicar no botão de OK usando JavaScript: {str(js_e)}")

            # Estratégia 2: Tentar clicar no material-ripple
            elif self._check_for_element(By.XPATH, ripple_xpath, timeout=3):
                ripple = self.driver.find_element(By.XPATH, ripple_xpath)

                # Tentar clicar usando JavaScript diretamente no ripple
                try:
                    self.driver.execute_script("arguments[0].click();", ripple)
                    logger.info(
                        "[OK] Botão de OK (ripple) clicado com sucesso usando JavaScript")
                    time.sleep(3)
                    self._wait_for_page_load()

                    if DEBUG_MODE:
                        self._save_screenshot("after_ripple_button_js")

                    return True
                except Exception as ripple_e:
                    logger.warning(
                        f"[AVISO] Falha ao clicar no ripple usando JavaScript: {str(ripple_e)}")

            # Estratégia 3: Procurar por qualquer botão de submit no formulário
            submit_xpath = signup_locators.SUBMIT_BUTTON
            if self._check_for_element(By.XPATH, submit_xpath, timeout=3):
                submit_button = self.driver.find_element(
                    By.XPATH, submit_xpath)

                # Tentar clicar usando JavaScript
                try:
                    self.driver.execute_script(
                        "arguments[0].click();", submit_button)
                    logger.info(
                        "[OK] Botão de submit clicado com sucesso usando JavaScript")
                    time.sleep(3)
                    self._wait_for_page_load()

                    if DEBUG_MODE:
                        self._save_screenshot("after_submit_button_js")

                    return True
                except Exception as submit_e:
                    logger.warning(
                        f"[AVISO] Falha ao clicar no botão de submit usando JavaScript: {str(submit_e)}")

            # Estratégia 4: Tentar submeter o formulário diretamente via JavaScript
            try:
                self.driver.execute_script(
                    "document.querySelector('form').submit();")
                logger.info(
                    "[OK] Formulário submetido com sucesso usando JavaScript")
                time.sleep(3)
                self._wait_for_page_load()

                if DEBUG_MODE:
                    self._save_screenshot("after_form_submit_js")

                return True
            except Exception as form_e:
                logger.warning(
                    f"[AVISO] Falha ao submeter o formulário usando JavaScript: {str(form_e)}")

            # Se chegou aqui, não conseguiu clicar no botão
            logger.warning(
                "[AVISO] Não foi possível clicar no botão de OK por nenhum método")
            return False
        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao tentar clicar no botão de OK: {str(e)}")
            return False

    def _check_and_handle_recaptcha(self) -> bool:
        """
        Verifica se há um recaptcha na página e aguarda sua resolução automática.
        Evita falsos positivos verificando também elementos da tela de criação do AdSense.

        Returns:
            bool: True se o recaptcha foi detectado e tratado, False caso contrário
        """
        try:
            # Verificar a URL atual
            current_url = self.driver.current_url
            logger.info(f"[INFO] Verificando URL atual: {current_url}")

            # Verificar se estamos na URL de criação do AdSense
            if "adsense.google.com/adsense/signup/create" in current_url:
                logger.info(
                    f"[INFO] Na tela de criação do AdSense, detectado pela URL: {current_url}")
                return False  # Não é recaptcha, já estamos na tela certa

            # Verificar primeiro se já estamos na tela de criação do AdSense
            adsense_indicators = [
                "//input[@aria-label='URL']",
                "//input[contains(@placeholder, 'website')]",
                "//input[contains(@placeholder, 'site')]",
                "//div[contains(text(), 'site URL')]",
                "//div[contains(text(), 'URL do site')]",
                "//div[contains(text(), 'Vamos começar')]",
                "//div[contains(text(), 'Seu site')]",
                "//form[contains(@action, 'adsense/signup/create')]",
                "//div[contains(@class, 'freebirdFormviewerViewItemsItemItem')]",
                "//div[contains(@role, 'listitem')]"
            ]

            for indicator in adsense_indicators:
                if self._check_for_element(By.XPATH, indicator, timeout=2):
                    logger.info(
                        f"[INFO] Já na tela de criação do AdSense, detectado pelo elemento: {indicator}")
                    return False  # Não é recaptcha, já estamos na tela certa

            # Verificar se há textos comuns na página de criação do AdSense
            try:
                adsense_texts = ["Vamos começar",
                                 "Seu site", "URL do site", "AdSense"]
                for text in adsense_texts:
                    if self.driver.execute_script(f"return document.body.innerText.includes('{text}')"):
                        logger.info(
                            f"[INFO] Na tela de criação do AdSense, detectado pelo texto: '{text}'")
                        return False  # Não é recaptcha
            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao verificar textos na página: {str(e)}")

            # Verificações para recaptcha
            is_recaptcha = False

            # Verificar pela URL se é recaptcha
            if "recaptcha" in current_url or "challenge" in current_url:
                is_recaptcha = True
                logger.info(
                    f"[INFO] Detectada tela de recaptcha via URL: {current_url}")

            # Verificação com elementos específicos de recaptcha
            recaptcha_elements = [
                "//iframe[contains(@src, 'recaptcha') and contains(@title, 'reCAPTCHA')]",
                "//div[@id='recaptcha' and contains(@class, 'recaptcha')]",
                "//div[contains(@class, 'recaptcha-checkbox-border') and not(ancestor::*[contains(@style,'display: none')])]",
                "//div[contains(@class, 'g-recaptcha')]"
            ]

            for element in recaptcha_elements:
                if not is_recaptcha and self._check_for_element(By.XPATH, element, timeout=2):
                    # Verificação adicional - confirmar visualmente
                    is_element_visible = self.driver.execute_script("""
                        var el = document.evaluate(arguments[0], document, null, 
                                  XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                        if (!el) return false;
                        
                        var rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0 && 
                              rect.top >= 0 && rect.left >= 0 &&
                              el.style.display !== 'none' && el.style.visibility !== 'hidden';
                    """, element)

                    if is_element_visible:
                        is_recaptcha = True
                        logger.info(
                            f"[INFO] Detectada tela de recaptcha via elemento visível: {element}")
                        break

            # Se detectou recaptcha, tratar
            if is_recaptcha:
                logger.info(
                    "[INFO] Aguardando 45 segundos para resolução automática do recaptcha...")

                # Aguardar 45 segundos para a resolução automática do recaptcha
                time.sleep(45)

                # Verificar se o recaptcha foi resolvido
                new_url = self.driver.current_url
                logger.info(
                    f"[INFO] URL após aguardar resolução do recaptcha: {new_url}")

                # Tentar clicar no botão "Avançar" ou "Submit" usando múltiplos seletores
                recaptcha_button_xpaths = [
                    login_locators.NEXT_BUTTON,
                    "//input[@type='submit']",
                    "//button[contains(text(), 'Next') or contains(text(), 'Próximo') or contains(text(), 'Avançar')]"
                ]
                button_clicked = False
                for xpath in recaptcha_button_xpaths:
                    if self._check_for_element(By.XPATH, xpath, timeout=5):
                        btn = self.driver.find_element(By.XPATH, xpath)
                        if self._click_safely(btn):
                            logger.info(f"[OK] Botão Avançar clicado após recaptcha usando XPath: {xpath}")
                            button_clicked = True
                            time.sleep(3)
                            self._wait_for_page_load()
                            break
                if not button_clicked:
                    logger.warning("[AVISO] Botão Avançar/Submit não encontrado após recaptcha")
                return True

            logger.info("[INFO] Nenhum recaptcha detectado na página")
            return False

        except Exception as e:
            logger.warning(f"[AVISO] Erro ao verificar recaptcha: {str(e)}")
            return False

    def _handle_password_screen(self) -> bool:
        """
        Lida com a tela de senha que aparece após resolver o captcha.
        Insere a senha da conta e clica no botão Avançar.

        Returns:
            bool: True se a senha foi inserida com sucesso e o botão foi clicado
        """
        try:
            logger.info("[INFO] Verificando tela de senha após captcha...")

            # Aguardar um pouco para garantir que a página carregou
            time.sleep(3)

            # Lista de possíveis XPaths para o campo de senha
            password_field_xpaths = [
                login_locators.PASSWORD_FIELD,  # XPath principal
                "//input[@type='password']",  # Genérico por tipo
                "//input[contains(@name, 'password')]",  # Por nome
                "//input[contains(@id, 'password')]",  # Por ID
                # Por aria-label
                "//input[contains(@aria-label, 'senha') or contains(@aria-label, 'password')]"
            ]

            # Verificar se estamos na tela de senha tentando encontrar o campo de senha
            password_field = None
            password_field_found = False

            for xpath in password_field_xpaths:
                if self._check_for_element(By.XPATH, xpath, timeout=2):
                    password_field = self.driver.find_element(By.XPATH, xpath)
                    password_field_found = True
                    logger.info(
                        f"[INFO] Campo de senha encontrado com XPath: {xpath}")
                    break

            if not password_field_found:
                logger.info(
                    "[INFO] Tela de senha não detectada, continuando fluxo normal")
                return True

            # Capturar screenshot para debug
            if DEBUG_MODE:
                self._save_screenshot("password_screen")

            # Detectar o email atual na página
            current_email = self._get_current_email_from_page()
            if current_email:
                logger.info(
                    f"[INFO] Email detectado na página: {current_email}")
                # Se o email detectado for diferente do email nos dados da conta, atualizar
                if self.account_data.get("email") != current_email:
                    logger.warning(
                        f"[AVISO] Email detectado ({current_email}) é diferente do email nos dados da conta ({self.account_data.get('email')})")
                    self.account_data["email"] = current_email

            # Obter a senha do account_data
            password = self.account_data.get("password", "")
            email = self.account_data.get("email", "")

            # Se a senha não estiver disponível no account_data, tentar buscar do arquivo JSON
            if not password:
                logger.info(
                    "[INFO] Senha não encontrada nos dados da conta, tentando buscar do arquivo JSON...")
                try:
                    import json
                    import os

                    # Caminho para o arquivo de credenciais
                    credentials_path = "credentials/gmail.json"

                    if os.path.exists(credentials_path):
                        with open(credentials_path, "r") as file:
                            gmail_accounts = json.load(file)

                            # Verificar se temos o email para fazer a correspondência
                            if email:
                                # Buscar a conta pelo email
                                for account in gmail_accounts:
                                    if account.get("email") == email:
                                        password = account.get("password", "")
                                        logger.info(
                                            f"[OK] Senha encontrada no arquivo JSON para o email: {email}")
                                        break

                            # Se não encontrou pelo email ou não temos o email, usar a primeira conta disponível
                            if not password and gmail_accounts:
                                password = gmail_accounts[0].get(
                                    "password", "")
                                logger.info(
                                    "[OK] Usando senha da primeira conta disponível no arquivo JSON")
                except Exception as e:
                    logger.error(
                        f"[ERRO] Erro ao tentar buscar senha do arquivo JSON: {str(e)}")

            if not password:
                logger.error(
                    "[ERRO] Senha não encontrada nos dados da conta nem no arquivo JSON")
                return False

            logger.info(
                f"[INFO] Inserindo senha para a conta {email if email else 'atual'}")

            # Preencher o campo de senha
            self._fill_input_safely(password_field, password)

            # Capturar screenshot após preencher a senha
            if DEBUG_MODE:
                self._save_screenshot("password_filled")

            logger.info("[INFO] Senha inserida, procurando botão Avançar...")

            # Lista de possíveis XPaths para o botão Avançar/Próximo/Next
            next_button_xpaths = [
                login_locators.NEXT_BUTTON,  # XPath principal
                # Texto do botão
                "//button[contains(., 'Next') or contains(., 'Próximo') or contains(., 'Avançar')]",
                # Classe comum do botão
                "//button[contains(@class, 'VfPpkd-LgbsSe')]",
                # Div com role=button
                "//div[contains(@role, 'button') and (contains(., 'Next') or contains(., 'Próximo') or contains(., 'Avançar'))]",
                "//button[@type='submit']"  # Botão de tipo submit
            ]

            # Tentar clicar no botão Avançar usando diferentes XPaths
            button_clicked = False

            for xpath in next_button_xpaths:
                if button_clicked:
                    break

                if self._check_for_element(By.XPATH, xpath, timeout=2):
                    next_button = self.driver.find_element(By.XPATH, xpath)

                    # Tentar clicar no botão
                    if self._click_safely(next_button):
                        logger.info(
                            f"[OK] Botão Avançar clicado com sucesso usando XPath: {xpath}")
                        button_clicked = True

                        # Aguardar carregamento da página
                        time.sleep(3)
                        self._wait_for_page_load()

                        # Capturar screenshot após clicar no botão
                        if DEBUG_MODE:
                            self._save_screenshot("after_password_next_button")
                    else:
                        logger.warning(
                            f"[AVISO] Falha ao clicar no botão usando XPath: {xpath}")

            # Se não conseguiu clicar em nenhum botão, tentar com JavaScript
            if not button_clicked:
                logger.info(
                    "[INFO] Tentando clicar no botão Avançar com JavaScript genérico...")

                try:
                    success = self.driver.execute_script("""
                        // Tentar encontrar botão pelo texto
                        var buttons = document.querySelectorAll('button');
                        for (var i = 0; i < buttons.length; i++) {
                            if (buttons[i].innerText.includes('Avançar') || 
                                buttons[i].innerText.includes('Próximo') || 
                                buttons[i].innerText.includes('Next')) {
                                buttons[i].click();
                                return true;
                            }
                        }
                        
                        // Tentar por spans dentro de botões
                        var spans = document.querySelectorAll('button span');
                        for (var i = 0; i < spans.length; i++) {
                            if (spans[i].innerText.includes('Avançar') || 
                                spans[i].innerText.includes('Próximo') || 
                                spans[i].innerText.includes('Next')) {
                                spans[i].closest('button').click();
                                return true;
                            }
                        }
                        
                        // Tentar qualquer botão de submit
                        var submitButton = document.querySelector('button[type="submit"]');
                        if (submitButton) {
                            submitButton.click();
                            return true;
                        }
                        
                        return false;
                    """)

                    if success:
                        logger.info(
                            "[OK] Botão Avançar clicado com sucesso via JavaScript genérico")
                        button_clicked = True

                        # Aguardar carregamento da página
                        time.sleep(3)
                        self._wait_for_page_load()

                        # Capturar screenshot após clicar no botão
                        if DEBUG_MODE:
                            self._save_screenshot(
                                "after_password_next_button_js")
                    else:
                        logger.warning(
                            "[AVISO] Método JavaScript genérico não encontrou o botão Avançar")
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro no método JavaScript genérico: {str(e)}")

            # Verificar se após o login apareceu a tela de verificação de telefone
            if button_clicked:
                time.sleep(3)  # Aguardar carregamento completo
                if self._check_for_phone_verification():
                    logger.info(
                        "[INFO] Tela de verificação de telefone detectada após login")
                    return self._handle_phone_verification()

            return button_clicked

        except Exception as e:
            logger.error(
                f"[ERRO] Falha ao lidar com a tela de senha: {str(e)}")
            return False

    def _get_current_email_from_page(self):
        """
        Detecta o email atual mostrado na página.

        Returns:
            str: O email detectado ou None se não for possível detectar
        """
        try:
            # Aguardar um pouco para garantir que a página carregou completamente
            time.sleep(2)

            # Lista de possíveis XPaths para encontrar o email na página
            email_xpaths = [
                "//div[contains(@class, 'email') and contains(text(), '@')]",
                "//div[contains(text(), '@gmail.com')]",
                "//span[contains(text(), '@gmail.com')]",
                "//p[contains(text(), '@gmail.com')]",
                "//h1[contains(text(), '@gmail.com')]",
                "//h2[contains(text(), '@gmail.com')]",
                "//input[@type='email' and @value]",
                "//div[contains(@class, 'account-email')]"
            ]

            # Tentar encontrar o email usando os XPaths
            for xpath in email_xpaths:
                try:
                    if self._check_for_element(By.XPATH, xpath, timeout=1):
                        email_element = self.driver.find_element(
                            By.XPATH, xpath)
                        text = email_element.text.strip(
                        ) if email_element.text else email_element.get_attribute("value")

                        if text and "@" in text:
                            # Extrair apenas o email se houver texto adicional
                            import re
                            email_match = re.search(
                                r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
                            if email_match:
                                email = email_match.group(0)
                                logger.info(
                                    f"[OK] Email detectado na página: {email}")
                                return email
                except Exception:
                    continue

            # Se não encontrou pelos XPaths, tentar pelo título da página ou URL
            try:
                page_title = self.driver.title
                current_url = self.driver.current_url

                # Verificar no título da página
                if "@" in page_title:
                    import re
                    email_match = re.search(
                        r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', page_title)
                    if email_match:
                        email = email_match.group(0)
                        logger.info(
                            f"[OK] Email detectado no título da página: {email}")
                        return email

                # Verificar na URL
                if "authuser=" in current_url:
                    import re
                    email_match = re.search(r'authuser=([^&]+)', current_url)
                    if email_match:
                        email = email_match.group(1)
                        if "@" in email:
                            logger.info(
                                f"[OK] Email detectado na URL: {email}")
                            return email
            except Exception:
                pass

            # Se não encontrou por métodos diretos, tentar com JavaScript
            try:
                email = self.driver.execute_script("""
                    // Tentar encontrar elementos com email
                    var elements = document.querySelectorAll('*');
                    for (var i = 0; i < elements.length; i++) {
                        var text = elements[i].textContent || elements[i].innerText;
                        if (text && text.includes('@gmail.com')) {
                            // Extrair email com regex
                            var match = text.match(/[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+/);
                            if (match) return match[0];
                        }
                    }
                    
                    // Tentar encontrar no código fonte
                    var html = document.documentElement.outerHTML;
                    var match = html.match(/[a-zA-Z0-9_.+-]+@gmail\\.com/);
                    if (match) return match[0];
                    
                    return null;
                """)

                if email:
                    logger.info(
                        f"[OK] Email detectado via JavaScript: {email}")
                    return email
            except Exception:
                pass

            logger.info("[INFO] Não foi possível detectar o email na página")
            return None
        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao tentar detectar o email na página: {str(e)}")
            return None

    def _update_credentials_file(self):
        """Atualiza o arquivo de credenciais com os dados da conta AdSense."""
        try:
            import json
            import os

            # Verificar se temos os dados necessários
            email = self.account_data.get("email")
            if not email:
                logger.warning(
                    "[AVISO] Email não fornecido, não é possível atualizar o arquivo de credenciais")
                return False

            # Tentar detectar o email real na página
            real_email = self._get_current_email_from_page()
            if real_email and real_email != email:
                logger.warning(
                    f"[AVISO] Email detectado na página ({real_email}) é diferente do email nos dados da conta ({email})")
                # Atualizar o email nos dados da conta
                self.account_data["email"] = real_email
                email = real_email

            # Caminho para o arquivo de credenciais
            credentials_path = "credentials/gmail.json"

            if not os.path.exists(credentials_path):
                logger.warning(
                    f"[AVISO] Arquivo de credenciais {credentials_path} não encontrado")
                return False

            # Ler o arquivo de credenciais
            try:
                with open(credentials_path, "r") as file:
                    content = file.read().strip()
                    if not content:
                        logger.warning(
                            "[AVISO] Arquivo de credenciais está vazio")
                        return False

                    gmail_accounts = json.loads(content)

                    # Verificar se é uma lista
                    if not isinstance(gmail_accounts, list):
                        logger.warning(
                            "[AVISO] Arquivo de credenciais não contém uma lista válida")
                        return False

                    # Buscar a conta pelo email
                    account_found = False
                    for i, account in enumerate(gmail_accounts):
                        if account.get("email") == email:
                            account_found = True

                            # Atualizar os dados da conta com informações do AdSense
                            gmail_accounts[i]["adsense_setup_completed"] = True
                            gmail_accounts[i]["adsense_setup_date"] = time.strftime(
                                "%Y-%m-%d %H:%M:%S")

                            # Adicionar informações do site se disponíveis
                            if hasattr(self, "adsense_info") and self.adsense_info:
                                if hasattr(self.adsense_info, "website_url") and self.adsense_info.website_url:
                                    gmail_accounts[i]["adsense_website"] = self.adsense_info.website_url

                            logger.info(
                                f"[OK] Dados da conta {email} atualizados no arquivo de credenciais com informações do AdSense")
                            break

                    if not account_found:
                        logger.warning(
                            f"[AVISO] Email {email} não encontrado no arquivo de credenciais")
                        return False

                    # Salvar o arquivo atualizado
                    with open(credentials_path, "w") as file:
                        json.dump(gmail_accounts, file, indent=4)

                    logger.info(
                        f"[OK] Arquivo de credenciais atualizado com sucesso: {credentials_path}")
                    return True

            except Exception as e:
                logger.error(
                    f"[ERRO] Erro ao atualizar arquivo de credenciais: {str(e)}")
                return False

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao atualizar arquivo de credenciais: {str(e)}")
            return False

    def _check_for_phone_verification(self) -> bool:
        """
        Verifica se estamos na tela de verificação de telefone.

        Returns:
            bool: True se estamos na tela de verificação de telefone
        """
        try:
            # Usar o método auxiliar para identificar o tipo de tela
            screen_type = self._identify_phone_verification_screen_type()

            # Se identificou qualquer tipo de tela de verificação (alternativa ou padrão), retornar True
            if screen_type != "unknown":
                logger.info(
                    f"[INFO] Tela de verificação de telefone detectada: {screen_type}")
                return True

            # Verificar por textos que indicam verificação de telefone (backup)
            phone_verification_texts = [
                "//div[contains(text(), 'Verify your phone number')]",
                "//div[contains(text(), 'Verifique seu número de telefone')]",
                "//span[contains(text(), 'phone verification')]",
                "//span[contains(text(), 'verificação de telefone')]"
            ]

            for xpath in phone_verification_texts:
                if self._check_for_element(By.XPATH, xpath, timeout=2):
                    logger.info(
                        f"[INFO] Texto de verificação de telefone encontrado com XPath: {xpath}")
                    return True

            logger.info("[INFO] Tela de verificação de telefone não detectada")
            return False

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao verificar tela de verificação de telefone: {str(e)}")
            return False

    def _handle_phone_verification(self) -> bool:
        """
        Lida com a verificação de telefone usando a classe PhoneVerification do módulo gmail_creator.

        Returns:
            bool: True se a verificação foi bem-sucedida
        """
        try:
            logger.info(
                "[INICIO] Iniciando processo de verificação de telefone para AdSense...")

            # Importar a classe PhoneVerification e inicializar o phone_manager
            from automations.gmail_creator.phone_verify import PhoneVerification
            from apis.phone_manager import PhoneManager
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            import time

            # Inicializar o phone_manager
            phone_manager = PhoneManager()

            # Obter a instância do sms_api diretamente do phone_manager
            sms_api = phone_manager.sms_api

            if not sms_api:
                logger.error("[ERRO] Não foi possível obter a API de SMS")
                return False

            # Criar instância de PhoneVerification
            phone_verify = PhoneVerification(self.driver, sms_api)

            # Configurar o phone_manager
            phone_verify.phone_manager = phone_manager

            # Verificar se temos um número de telefone nos dados da conta para reutilizar
            if self.account_data.get("phone"):
                logger.info(
                    f"[INFO] Tentando reutilizar número de telefone: {self.account_data.get('phone')}")
                phone_verify.predefined_number = self.account_data.get("phone")
                phone_verify.predefined_country_code = self.account_data.get(
                    "country_code")
                phone_verify.predefined_activation_id = self.account_data.get(
                    "activation_id")
                phone_verify.reuse_number = True

            # Identificar qual tipo de tela de verificação de telefone estamos
            screen_type = self._identify_phone_verification_screen_type()
            is_alternative_screen = (screen_type == "alternative")

            if is_alternative_screen:
                logger.info(
                    "[INFO] Usando fluxo para tela alternativa de verificação de telefone")
            else:
                logger.info(
                    "[INFO] Usando fluxo para tela padrão de verificação de telefone")

            # Implementar fluxo direto de verificação de telefone conforme o tipo de tela
            try:
                # Definir contador de tentativas para números de telefone
                phone_attempts = 0
                max_phone_attempts = 3

                while phone_attempts < max_phone_attempts:
                    phone_attempts += 1
                    logger.info(
                        f"[ATUALIZANDO] Tentativa {phone_attempts} de {max_phone_attempts} para verificação de telefone")

                    # 1. Obter um novo número de telefone
                    logger.info(
                        "[INFO] Obtendo número de telefone para verificação...")
                    phone_verify.current_activation = phone_verify._get_new_number()

                    if not phone_verify.current_activation:
                        logger.error(
                            "[ERRO] Falha ao obter número de telefone")
                        if phone_attempts < max_phone_attempts:
                            logger.info(
                                "[INFO] Tentando novamente com outro número...")
                            continue
                        return False

                    logger.info(
                        f"[OK] Número obtido: {phone_verify.current_activation.phone_number}")

                    # 2. Submeter o número de telefone no formulário
                    logger.info(
                        "[INFO] Inserindo número de telefone no formulário...")

                    if is_alternative_screen:
                        # Tratar a tela alternativa com select de país
                        try:
                            # Selecionar o país correto no dropdown
                            country_select = self.driver.find_element(
                                By.XPATH, "//select[@id='countryList']")

                            # Extrair o código do país do número de telefone
                            phone_number = phone_verify.current_activation.phone_number

                            # Determinar o país com base no código do país
                            country_to_select = "Brasil"  # Valor padrão para números brasileiros

                            # Identificar o país com base no prefixo do número
                            if phone_number.startswith("55") or phone_number.startswith("+55"):
                                country_to_select = "Brasil"
                                country_code = "BR"
                            elif phone_number.startswith("1") or phone_number.startswith("+1"):
                                country_to_select = "Estados Unidos"
                                country_code = "US"
                            elif phone_number.startswith("44") or phone_number.startswith("+44"):
                                country_to_select = "Reino Unido"
                                country_code = "GB"
                            elif phone_number.startswith("33") or phone_number.startswith("+33"):
                                country_to_select = "França"
                                country_code = "FR"
                            else:
                                # Para outros países, tentar extrair o código do telefone
                                if "+" in phone_number:
                                    parts = phone_number.split("+")
                                    if len(parts) > 1:
                                        prefix = parts[1].split(" ")[0]
                                        if prefix.isdigit():
                                            if prefix == "55":
                                                country_to_select = "Brasil"
                                                country_code = "BR"
                                            elif prefix == "1":
                                                country_to_select = "Estados Unidos"
                                                country_code = "US"

                            logger.info(
                                f"[INFO] Tentando selecionar país: {country_to_select} para número: {phone_number}")

                            # Selecionar o país com base no código ou usar EUA como padrão
                            try:
                                from selenium.webdriver.support.ui import Select
                                select = Select(country_select)

                                # Tentar encontrar o país pelo nome ou código
                                country_found = False

                                # Primeiro tentar pelo nome
                                for option in select.options:
                                    option_text = option.text
                                    if country_to_select in option_text:
                                        select.select_by_value(
                                            option.get_attribute("value"))
                                        logger.info(
                                            f"[OK] País selecionado: {option_text}")
                                        country_found = True
                                        break

                                # Se não encontrou pelo nome, tentar pelo código
                                if not country_found and country_code:
                                    select.select_by_value(country_code)
                                    selected_option = select.first_selected_option
                                    logger.info(
                                        f"[OK] País selecionado pelo código {country_code}: {selected_option.text}")
                                    country_found = True

                                # Se ainda não encontrou, para números brasileiros tentar BR explicitamente
                                if not country_found and (phone_number.startswith("55") or phone_number.startswith("+55")):
                                    select.select_by_value("BR")
                                    selected_option = select.first_selected_option
                                    logger.info(
                                        f"[OK] País Brasil selecionado explicitamente: {selected_option.text}")
                                    country_found = True

                                # Se não encontrou, usar o Brasil como padrão para números com DDD 55
                                if not country_found and (phone_number.startswith("55") or phone_number.startswith("+55")):
                                    # Procurar qualquer opção com "Brasil" ou "Brazil" no texto
                                    for option in select.options:
                                        option_text = option.text.lower()
                                        if "brasil" in option_text or "brazil" in option_text:
                                            select.select_by_value(
                                                option.get_attribute("value"))
                                            logger.info(
                                                f"[OK] País Brasil selecionado: {option.text}")
                                            country_found = True
                                            break

                                # Se ainda não encontrou, usar o primeiro país como último recurso
                                if not country_found:
                                    logger.warning(
                                        f"[AVISO] País não encontrado para {country_to_select}, selecionando Brasil manualmente")
                                    try:
                                        select.select_by_value("BR")
                                        logger.info(
                                            "[OK] Brasil selecionado como última opção")
                                    except:
                                        select.select_by_index(0)
                                        logger.info(
                                            f"[OK] Primeiro país da lista selecionado: {select.first_selected_option.text}")
                            except Exception as e:
                                logger.warning(
                                    f"[AVISO] Erro ao selecionar país: {str(e)}")

                            # Aguardar um momento após selecionar o país
                            time.sleep(1)

                            # Inserir o número de telefone no campo apropriado
                            phone_input_xpath = "//input[@id='deviceAddress']"
                            phone_input = self.driver.find_element(
                                By.XPATH, phone_input_xpath)

                            # Limpar o campo
                            phone_input.clear()

                            # Formatar o número sem o código do país (que já foi selecionado no dropdown)
                            formatted_number = phone_number

                            # Para números brasileiros (começando com 55)
                            if phone_number.startswith("55") or phone_number.startswith("+55"):
                                # Remover código do país (55)
                                if phone_number.startswith("+"):
                                    # Remove +55
                                    formatted_number = phone_number[3:]
                                else:
                                    # Remove 55
                                    formatted_number = phone_number[2:]

                                # Se o número começar com 0, remover o 0
                                if formatted_number.startswith("0"):
                                    formatted_number = formatted_number[1:]

                                # Para números brasileiros, garantir que tenham o formato correto
                                # Remover qualquer caractere não numérico
                                formatted_number = ''.join(
                                    filter(str.isdigit, formatted_number))

                                logger.info(
                                    f"[INFO] Número brasileiro formatado para: {formatted_number}")
                            else:
                                # Para outros países
                                if " " in formatted_number:
                                    formatted_number = formatted_number.split(" ", 1)[
                                        1]
                                if formatted_number.startswith("+"):
                                    formatted_number = formatted_number[1:]

                                # Se o número começar com o código do país, remover
                                if country_code and formatted_number.startswith(country_code):
                                    formatted_number = formatted_number[len(
                                        country_code):]

                                # Remover qualquer caractere não numérico
                                formatted_number = ''.join(
                                    filter(str.isdigit, formatted_number))

                            logger.info(
                                f"[INFO] Número formatado para envio: {formatted_number}")

                            # Preencher o número com pequenas pausas para simular digitação humana
                            for char in formatted_number:
                                phone_input.send_keys(char)
                                time.sleep(0.1)

                            logger.info(
                                f"[OK] Número {formatted_number} inserido no campo")

                            # Clicar no botão "Receber código"
                            receive_code_button_xpath = "//input[@id='next-button']"
                            receive_code_button = self.driver.find_element(
                                By.XPATH, receive_code_button_xpath)
                            if not self._click_safely(receive_code_button):
                                logger.warning(
                                    "[AVISO] Falha ao clicar no botão 'Receber código'")
                                phone_verify._cancel_current_number()
                                if phone_attempts < max_phone_attempts:
                                    logger.info(
                                        "[INFO] Tentando novamente com outro número...")
                                    continue
                                return False

                            logger.info("[OK] Botão 'Receber código' clicado")
                        except Exception as e:
                            logger.error(
                                f"[ERRO] Falha ao interagir com a tela alternativa: {str(e)}")
                            phone_verify._cancel_current_number()
                            if phone_attempts < max_phone_attempts:
                                logger.info(
                                    "[INFO] Tentando novamente com outro número...")
                                continue
                            return False
                    else:
                        # Tela original de verificação de telefone
                        # XPath específico para o campo de telefone
                        phone_input_xpath = "/html/body/div[1]/div[1]/div[2]/c-wiz/div/div[2]/div/div/div/form/span/section[3]/div/div/div/div/div[2]/div[1]//input[@type='tel']"

                        try:
                            # Aguardar até que o campo de telefone esteja visível e clicável
                            wait = WebDriverWait(self.driver, 10)
                            phone_input = wait.until(
                                EC.element_to_be_clickable(
                                    (By.XPATH, phone_input_xpath))
                            )

                            # Garantir que o campo está visível
                            self.driver.execute_script(
                                "arguments[0].scrollIntoView(true);", phone_input)
                            time.sleep(1)

                            # Limpar o campo
                            phone_input.clear()

                            # Inserir o número de telefone com o formato correto (+DDI)
                            phone_number = phone_verify.current_activation.phone_number

                            # Garantir que o número tenha o formato correto com + na frente
                            if not phone_number.startswith('+'):
                                phone_number = '+' + phone_number

                            logger.info(
                                f"[INFO] Formatando número para: {phone_number}")

                            # Preencher o número com pequenas pausas para simular digitação humana
                            for char in phone_number:
                                phone_input.send_keys(char)
                                time.sleep(0.1)

                            logger.info(
                                f"[OK] Número {phone_number} inserido no campo")

                            # Aguardar um momento antes de clicar no botão
                            time.sleep(1)

                            # Procurar o botão "Next" ou "Avançar" ou "Próximo"
                            next_button_xpaths = [
                                "//button[contains(., 'Next') or contains(., 'Próximo') or contains(., 'Avançar')]",
                                "//button[contains(@class, 'VfPpkd-LgbsSe')]",
                                "//button[@type='submit']",
                                "/html/body/div[1]/div[1]/div[2]/c-wiz/div/div[2]/div/div/div/form/div/div/div/button"
                            ]

                            button_clicked = False
                            for xpath in next_button_xpaths:
                                try:
                                    next_button = wait.until(
                                        EC.element_to_be_clickable(
                                            (By.XPATH, xpath))
                                    )
                                    next_button.click()
                                    logger.info(
                                        f"[OK] Botão Next clicado usando XPath: {xpath}")
                                    button_clicked = True
                                    break
                                except Exception as e:
                                    logger.warning(
                                        f"[AVISO] Não foi possível clicar no botão com XPath {xpath}: {str(e)}")

                            if not button_clicked:
                                # Tentar clicar com JavaScript
                                try:
                                    self.driver.execute_script("""
                                        var buttons = document.querySelectorAll('button');
                                        for (var i = 0; i < buttons.length; i++) {
                                            if (buttons[i].innerText.includes('Avançar') || 
                                                buttons[i].innerText.includes('Próximo') || 
                                                buttons[i].innerText.includes('Next')) {
                                                buttons[i].click();
                                                return true;
                                            }
                                        }
                                        return false;
                                    """)
                                    logger.info(
                                        "[OK] Botão Next clicado via JavaScript")
                                    button_clicked = True
                                except Exception as e:
                                    logger.warning(
                                        f"[AVISO] Não foi possível clicar no botão via JavaScript: {str(e)}")

                            if not button_clicked:
                                logger.error(
                                    "[ERRO] Não foi possível clicar no botão Next")
                                phone_verify._cancel_current_number()
                                if phone_attempts < max_phone_attempts:
                                    logger.info(
                                        "[INFO] Tentando novamente com outro número...")
                                    continue
                                return False
                        except Exception as e:
                            logger.error(
                                f"[ERRO] Falha ao inserir número de telefone: {str(e)}")
                            phone_verify._cancel_current_number()
                            if phone_attempts < max_phone_attempts:
                                logger.info(
                                    "[INFO] Tentando novamente com outro número...")
                                continue
                            return False

                    # Aguardar processamento
                    time.sleep(5)

                    # Verificar se há mensagens de erro após inserir o número
                    error_xpaths = [
                        "//div[contains(text(), 'This phone number format is not recognized')]",
                        "//div[contains(text(), 'This phone number has already been used too many times')]",
                        "//div[contains(text(), 'Please enter a valid phone number')]",
                        "//div[contains(@class, 'error') and string-length(text()) > 0]"
                    ]

                    error_found = False
                    for xpath in error_xpaths:
                        try:
                            error_element = self.driver.find_element(
                                By.XPATH, xpath)
                            error_text = error_element.text.strip()
                            if error_text:
                                logger.warning(
                                    f"[AVISO] Erro detectado após inserir número: '{error_text}'")
                                error_found = True
                                break
                        except:
                            pass

                    if error_found:
                        logger.warning(
                            "[AVISO] Número rejeitado devido a erro")
                        phone_verify._cancel_current_number()
                        if phone_attempts < max_phone_attempts:
                            logger.info(
                                "[INFO] Tentando novamente com outro número...")
                            continue
                        return False

                    # Verificar se apareceu o campo de código
                    code_input_xpath = "//input[contains(@aria-label, 'code') or contains(@aria-label, 'código') or @type='number']"

                    # Para a tela alternativa, usar o XPath específico
                    if is_alternative_screen:
                        code_input_xpath = "//input[@id='smsUserPin']"

                        # XPaths alternativos para a tela alternativa
                        alternative_code_inputs = [
                            "//input[@id='smsUserPin']",
                            "//input[@name='smsUserPin']",
                            "//form[@id='challenge']//input[@type='tel']",
                            "//form[@id='challenge']//input[@type='text']",
                            "//input[@type='tel' and @pattern='[0-9]*']"
                        ]

                        # Tentar todos os XPaths alternativos
                        for alt_xpath in alternative_code_inputs:
                            if self._check_for_element(By.XPATH, alt_xpath, timeout=2):
                                code_input_xpath = alt_xpath
                                logger.info(
                                    f"[INFO] Campo de código SMS alternativo encontrado: {alt_xpath}")
                                break

                    code_input_found = False
                    try:
                        # Aumentar o timeout para 15 segundos
                        wait = WebDriverWait(self.driver, 15)
                        wait.until(EC.presence_of_element_located(
                            (By.XPATH, code_input_xpath)))
                        logger.info("[OK] Campo de código SMS detectado")
                        code_input_found = True
                    except Exception as e:
                        logger.warning(
                            f"[AVISO] Campo de código SMS não detectado: {str(e)}")

                    if not code_input_found:
                        # Para a tela alternativa, verificar se há mensagem de sucesso ou redirecionamento
                        if is_alternative_screen:
                            # Verificar se houve redirecionamento (isso pode indicar sucesso)
                            current_url = self.driver.current_url
                            if "myaccount.google.com" in current_url or "adsense.google.com" in current_url:
                                logger.info(
                                    f"[OK] Redirecionado para {current_url}, assumindo que a verificação foi bem-sucedida")

                                # Marcar número como usado com sucesso
                                try:
                                    activation_id = phone_verify.current_activation.activation_id
                                    phone_verify.sms_api.set_status(
                                        activation_id, 8)  # 8 = usado com sucesso
                                    logger.info(
                                        "[OK] Status do número atualizado para 'usado com sucesso'")

                                    # Obter os dados do telefone verificado
                                    phone_data = phone_verify.get_current_phone_data()
                                    if phone_data:
                                        # Atualizar os dados da conta
                                        self.account_data["phone"] = phone_data.get(
                                            "phone_number")
                                        self.account_data["country_code"] = phone_data.get(
                                            "country_code")
                                        self.account_data["activation_id"] = phone_data.get(
                                            "activation_id")
                                        self.account_data["country_name"] = phone_data.get(
                                            "country_name")

                                        # Atualizar o arquivo de credenciais
                                        self._update_credentials_file()
                                except Exception as e:
                                    logger.warning(
                                        f"[AVISO] Erro ao atualizar status do número: {str(e)}")

                                return True

                            # Tentar novamente com um pequeno delay adicional
                            logger.info(
                                "[INFO] Aguardando mais 5 segundos e tentando detectar o campo de código novamente...")
                            time.sleep(5)

                            for alt_xpath in alternative_code_inputs:
                                if self._check_for_element(By.XPATH, alt_xpath, timeout=2):
                                    code_input_xpath = alt_xpath
                                    logger.info(
                                        f"[INFO] Campo de código SMS encontrado após espera adicional: {alt_xpath}")
                                    code_input_found = True
                                    break

                            if not code_input_found:
                                logger.warning(
                                    "[AVISO] Campo de código SMS não encontrado mesmo após espera adicional")

                        # Verificar se ainda estamos na tela de telefone (número rejeitado)
                        if is_alternative_screen:
                            try:
                                if self.driver.find_element(By.XPATH, "//input[@id='deviceAddress']").is_displayed():
                                    logger.warning(
                                        "[AVISO] Ainda na tela alternativa de telefone. Número rejeitado.")
                                    phone_verify._cancel_current_number()
                                    if phone_attempts < max_phone_attempts:
                                        logger.info(
                                            "[INFO] Tentando novamente com outro número...")
                                        continue
                                    return False
                            except:
                                pass
                        else:
                            try:
                                if self.driver.find_element(By.XPATH, phone_input_xpath).is_displayed():
                                    logger.warning(
                                        "[AVISO] Ainda na tela de telefone. Número rejeitado.")
                                    phone_verify._cancel_current_number()
                                    if phone_attempts < max_phone_attempts:
                                        logger.info(
                                            "[INFO] Tentando novamente com outro número...")
                                        continue
                                    return False
                            except:
                                pass

                        # Se chegou aqui e não encontrou o campo de código nem está na tela de telefone,
                        # pode ser que tenha sido redirecionado ou a verificação foi bem-sucedida de outra forma
                        if not code_input_found:
                            logger.info(
                                "[INFO] Não foi detectado campo de código nem tela de telefone. Verificando URL atual...")
                            current_url = self.driver.current_url
                            logger.info(f"[INFO] URL atual: {current_url}")

                            # Se foi redirecionado para o AdSense ou Google Account, considerar sucesso
                            if "myaccount.google.com" in current_url or "adsense.google.com" in current_url:
                                logger.info(
                                    "[OK] Redirecionado para uma página do Google. Assumindo verificação bem-sucedida.")
                                return True
                            else:
                                # Se não encontrou o campo de código e não consegue identificar a situação, tentar outra vez
                                if phone_attempts < max_phone_attempts:
                                    logger.info(
                                        "[INFO] Situação não identificada claramente. Tentando com outro número...")
                                    phone_verify._cancel_current_number()
                                    continue
                                else:
                                    logger.error(
                                        "[ERRO] Não foi possível completar a verificação de telefone após todas as tentativas.")
                                    return False

                    # 3. Aguardar e inserir o código SMS
                    logger.info("[INFO] Aguardando código SMS...")

                    # Obter o código SMS
                    activation_id = phone_verify.current_activation.activation_id
                    sms_code = phone_verify.sms_api.get_sms_code(
                        activation_id,
                        # Tentar por 2 minutos (12 * 10 segundos)
                        max_attempts=12,
                        interval=10       # Verificar a cada 10 segundos
                    )

                    if not sms_code:
                        logger.error(
                            "[ERRO] Não foi possível obter o código SMS")
                        phone_verify._cancel_current_number()
                        if phone_attempts < max_phone_attempts:
                            logger.info(
                                "[INFO] Tentando novamente com outro número...")
                            continue
                        return False

                    logger.info(f"[OK] Código SMS recebido: {sms_code}")

                    # Inserir o código SMS
                    try:
                        # Encontrar o campo de código
                        wait = WebDriverWait(self.driver, 10)
                        code_input = wait.until(
                            EC.element_to_be_clickable(
                                (By.XPATH, code_input_xpath))
                        )

                        # Limpar o campo
                        code_input.clear()

                        # Inserir o código
                        for char in sms_code:
                            code_input.send_keys(char)
                            time.sleep(0.1)

                        logger.info(
                            f"[OK] Código {sms_code} inserido no campo")

                        # Clicar no botão "Verify" ou "Verificar"
                        verify_button_xpaths = [
                            "//button[contains(., 'Verify') or contains(., 'Verificar')]",
                            "//button[contains(@class, 'VfPpkd-LgbsSe')]",
                            "//button[@type='submit']"
                        ]

                        # Para a tela alternativa, usar o XPath específico
                        if is_alternative_screen:
                            verify_button_xpaths.insert(
                                0, "//input[@id='submit']")
                            verify_button_xpaths.insert(
                                0, "//input[@id='next-button']")
                            verify_button_xpaths.insert(
                                0, "//input[@name='VerifyPhone']")
                            verify_button_xpaths.insert(
                                0, "/html/body/div[1]/div[2]/div[2]/form/span/div[2]/input")
                            verify_button_xpaths.insert(
                                0, "//input[@type='submit' and @value='Verificar']")

                        button_clicked = False
                        for xpath in verify_button_xpaths:
                            try:
                                verify_button = wait.until(
                                    EC.element_to_be_clickable(
                                        (By.XPATH, xpath))
                                )
                                verify_button.click()
                                logger.info(
                                    f"[OK] Botão Verify clicado usando XPath: {xpath}")
                                button_clicked = True
                                break
                            except Exception as e:
                                logger.warning(
                                    f"[AVISO] Não foi possível clicar no botão com XPath {xpath}: {str(e)}")

                        if not button_clicked:
                            # Tentar clicar com JavaScript
                            try:
                                self.driver.execute_script("""
                                    var buttons = document.querySelectorAll('button');
                                    for (var i = 0; i < buttons.length; i++) {
                                        if (buttons[i].innerText.includes('Verify') || 
                                            buttons[i].innerText.includes('Verificar') || 
                                            buttons[i].innerText.includes('Next') ||
                                            buttons[i].innerText.includes('Próximo')) {
                                            buttons[i].click();
                                            return true;
                                        }
                                    }
                                    
                                    // Tentar com inputs do tipo submit
                                    var inputs = document.querySelectorAll('input[type="submit"]');
                                    for (var i = 0; i < inputs.length; i++) {
                                        inputs[i].click();
                                        return true;
                                    }
                                    
                                    return false;
                                """)
                                logger.info(
                                    "[OK] Botão Verify clicado via JavaScript")
                                button_clicked = True
                            except Exception as e:
                                logger.warning(
                                    f"[AVISO] Não foi possível clicar no botão via JavaScript: {str(e)}")

                        # Aguardar processamento
                        time.sleep(5)
                        self._wait_for_page_load()

                        # Verificar URL atual para possível redirecionamento após verificação bem-sucedida
                        current_url = self.driver.current_url
                        logger.info(
                            f"[INFO] URL após enviar código SMS: {current_url}")

                        # Verificar possível redirecionamento para uma página de sucesso
                        if "myaccount.google.com" in current_url or "adsense.google.com" in current_url or "gds.google.com" in current_url:
                            logger.info(
                                "[OK] Redirecionado após verificação do código SMS. Sucesso detectado.")

                            # Verificar se estamos na tela de confirmação de informações de recuperação
                            if "recoveryoptions" in current_url or "gds.google.com" in current_url:
                                if self._check_and_handle_recovery_options_screen():
                                    logger.info(
                                        "[OK] Tela de recuperação tratada com sucesso")

                            # Verificar se estamos na tela de definição de endereço residencial
                            if self._check_and_handle_address_screen():
                                logger.info(
                                    "[OK] Tela de definição de endereço residencial tratada com sucesso")

                        # Verificar a presença de elementos de confirmação de verificação bem-sucedida
                        success_indicators = [
                            "//div[contains(text(), 'verificação concluída')]",
                            "//div[contains(text(), 'verification complete')]",
                            "//div[contains(text(), 'verified successfully')]"
                        ]

                        for indicator in success_indicators:
                            if self._check_for_element(By.XPATH, indicator, timeout=2):
                                logger.info(
                                    f"[OK] Indicador de sucesso encontrado: {indicator}")

                                # Atualizar o status do número para "usado com sucesso"
                                try:
                                    phone_verify.sms_api.set_status(
                                        activation_id, 8)  # 8 = usado com sucesso
                                    logger.info(
                                        "[OK] Status do número atualizado para 'usado com sucesso'")
                                except Exception as e:
                                    logger.warning(
                                        f"[AVISO] Erro ao atualizar status do número: {str(e)}")

                                return True

                        # Verificar se há mensagens de erro após inserir o código
                        code_error_xpaths = [
                            "//div[contains(text(), 'Wrong code')]",
                            "//div[contains(text(), 'Code is incorrect')]",
                            "//div[contains(text(), 'That code didn')]",
                            "//div[contains(@class, 'error') and string-length(text()) > 0]"
                        ]

                        error_found = False
                        for xpath in code_error_xpaths:
                            try:
                                error_element = self.driver.find_element(
                                    By.XPATH, xpath)
                                error_text = error_element.text.strip()
                                if error_text:
                                    logger.warning(
                                        f"[AVISO] Erro detectado após inserir código: '{error_text}'")
                                    error_found = True
                                    break
                            except:
                                pass

                        if error_found:
                            logger.warning(
                                "[AVISO] Código rejeitado devido a erro")
                            phone_verify._cancel_current_number()
                            if phone_attempts < max_phone_attempts:
                                logger.info(
                                    "[INFO] Tentando novamente com outro número...")
                                continue
                            return False

                        # Verificar se ainda estamos na tela de código (código rejeitado)
                        try:
                            if code_input.is_displayed():
                                logger.warning(
                                    "[AVISO] Ainda na tela de código. Código rejeitado.")
                                phone_verify._cancel_current_number()
                                if phone_attempts < max_phone_attempts:
                                    logger.info(
                                        "[INFO] Tentando novamente com outro número...")
                                    continue
                                return False
                        except:
                            pass

                        # Se chegou aqui e não encontrou erros, é provável que a verificação tenha sido bem-sucedida
                        logger.info(
                            "[OK] Verificação de telefone concluída com sucesso")

                        # Verificar se estamos na tela de confirmação de informações de recuperação
                        if self._check_and_handle_recovery_options_screen():
                            logger.info(
                                "[OK] Tela de confirmação de informações de recuperação tratada com sucesso")

                        # Verificar se estamos na tela de definição de endereço residencial
                        if self._check_and_handle_address_screen():
                            logger.info(
                                "[OK] Tela de definição de endereço residencial tratada com sucesso")

                        # Atualizar o status do número para "usado com sucesso"
                        try:
                            phone_verify.sms_api.set_status(
                                activation_id, 8)  # 8 = usado com sucesso
                            logger.info(
                                "[OK] Status do número atualizado para 'usado com sucesso'")
                        except Exception as e:
                            logger.warning(
                                f"[AVISO] Erro ao atualizar status do número: {str(e)}")

                        # Obter os dados do telefone verificado
                        phone_data = phone_verify.get_current_phone_data()
                        if phone_data:
                            # Atualizar os dados da conta com as informações do telefone
                            self.account_data["phone"] = phone_data.get(
                                "phone_number")
                            self.account_data["country_code"] = phone_data.get(
                                "country_code")
                            self.account_data["activation_id"] = phone_data.get(
                                "activation_id")
                            self.account_data["country_name"] = phone_data.get(
                                "country_name")

                            # Atualizar o arquivo de credenciais com os novos dados
                            self._update_credentials_file()

                            logger.info(
                                f"[OK] Dados de telefone atualizados: {phone_data.get('phone_number')}")

                        return True

                    except Exception as e:
                        logger.error(
                            f"[ERRO] Falha ao inserir código SMS: {str(e)}")
                        phone_verify._cancel_current_number()
                        if phone_attempts < max_phone_attempts:
                            logger.info(
                                "[INFO] Tentando novamente com outro número...")
                            continue
                        return False

                # Se chegou aqui, todas as tentativas falharam
                logger.error(
                    f"[ERRO] Todas as {max_phone_attempts} tentativas de verificação de telefone falharam")
                return False

            except Exception as e:
                logger.error(
                    f"[ERRO] Erro no fluxo direto de verificação: {str(e)}")
                # Tentar cancelar o número se houver falha
                if hasattr(phone_verify, 'current_activation') and phone_verify.current_activation:
                    phone_verify._cancel_current_number()
                return False

        except Exception as e:
            logger.error(
                f"[ERRO] Erro durante verificação de telefone: {str(e)}")
            return False

    def _check_and_handle_recovery_options_screen(self) -> bool:
        """
        Verifica e trata a tela de confirmação de informações de recuperação após verificação de telefone.
        Clica no botão "Salvar" para continuar. Depois verifica se aparece a tela de endereço.

        Returns:
            bool: True se a tela foi detectada e tratada com sucesso
        """
        try:
            # Aguardar um pouco para garantir que a página carregou completamente
            time.sleep(3)

            # Verificar URL atual para confirmar que estamos na página de opções de recuperação
            current_url = self.driver.current_url
            if "recoveryoptions" in current_url or "gds.google.com" in current_url:
                logger.info(
                    "[INFO] Detectada tela de confirmação de informações de recuperação")

                # Capturar screenshot para debug
                if DEBUG_MODE:
                    self._save_screenshot("recovery_options_screen")

                # Tentar localizar o botão "Salvar" usando vários XPaths
                save_button_xpaths = [
                    # XPath específico fornecido
                    "/html/body/div[1]/c-wiz[2]/div/div/div/div/div[2]/button[2]",
                    "//button[@aria-label='Salvar']",
                    "//button[contains(., 'Salvar')]",
                    "//button[contains(@class, 'VfPpkd-LgbsSe') and contains(., 'Salvar')]",
                    "//span[text()='Salvar']/ancestor::button",
                    # XPath específico fornecido pelo usuário
                    "//button[@jsname='M2UYVd' and contains(@class, 'VfPpkd-LgbsSe')]",
                    "//button[.//span[contains(text(), 'Salvar')]]"
                ]

                button_clicked = False
                for xpath in save_button_xpaths:
                    try:
                        if self._check_for_element(By.XPATH, xpath, timeout=3):
                            save_button = self.driver.find_element(
                                By.XPATH, xpath)

                            # Garantir que o botão está visível
                            self.driver.execute_script(
                                "arguments[0].scrollIntoView(true);", save_button)
                            time.sleep(1)

                            # Tentar clicar no botão
                            if self._click_safely(save_button):
                                logger.info(
                                    f"[OK] Botão 'Salvar' clicado com sucesso usando XPath: {xpath}")
                                button_clicked = True

                                # Aguardar o processamento após clicar no botão
                                time.sleep(5)
                                self._wait_for_page_load()
                                break
                    except Exception as e:
                        logger.warning(
                            f"[AVISO] Erro ao tentar clicar no botão 'Salvar' com XPath {xpath}: {str(e)}")

                # Se não conseguiu clicar em nenhum botão, tentar com JavaScript
                if not button_clicked:
                    try:
                        logger.info(
                            "[INFO] Tentando clicar no botão 'Salvar' com JavaScript")
                        success = self.driver.execute_script("""
                            // Tentar encontrar botão pelo texto
                            var buttons = document.querySelectorAll('button');
                            for (var i = 0; i < buttons.length; i++) {
                                if (buttons[i].innerText.includes('Salvar')) {
                                    buttons[i].click();
                                    return true;
                                }
                            }
                            
                            // Tentar por spans dentro de botões
                            var spans = document.querySelectorAll('button span');
                            for (var i = 0; i < spans.length; i++) {
                                if (spans[i].innerText.includes('Salvar')) {
                                    spans[i].closest('button').click();
                                    return true;
                                }
                            }
                            
                            // Tentar pelo jsname específico
                            var jsButton = document.querySelector('button[jsname="M2UYVd"]');
                            if (jsButton) {
                                jsButton.click();
                                return true;
                            }
                            
                            // Tentar pelo XPath específico
                            var xpathResult = document.evaluate(
                                "/html/body/div[1]/c-wiz[2]/div/div/div/div/div[2]/button[2]", 
                                document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null
                            );
                            
                            if (xpathResult && xpathResult.singleNodeValue) {
                                xpathResult.singleNodeValue.click();
                                return true;
                            }
                            
                            return false;
                        """)

                        if success:
                            logger.info(
                                "[OK] Botão 'Salvar' clicado com sucesso via JavaScript")
                            button_clicked = True

                            # Aguardar o processamento após clicar no botão
                            time.sleep(5)
                            self._wait_for_page_load()
                        else:
                            logger.warning(
                                "[AVISO] Não foi possível encontrar o botão 'Salvar' via JavaScript")
                    except Exception as e:
                        logger.warning(
                            f"[AVISO] Erro ao tentar clicar no botão 'Salvar' via JavaScript: {str(e)}")

                # Capturar screenshot após tentar clicar no botão
                if DEBUG_MODE:
                    self._save_screenshot("after_save_button_click")

                # Após salvar, verificar se fomos direcionados para a tela de definição de endereço
                if button_clicked:
                    time.sleep(3)  # Aguardar redirecionamento
                    if self._check_and_handle_address_screen():
                        logger.info(
                            "[OK] Tela de definição de endereço residencial tratada com sucesso após tela de recuperação")

                return button_clicked

            return False  # Não estamos na tela de confirmação

        except Exception as e:
            logger.warning(
                f"[AVISO] Erro ao verificar/tratar tela de confirmação de recuperação: {str(e)}")
            return False

    def _identify_phone_verification_screen_type(self) -> str:
        """
        Identifica qual tipo de tela de verificação de telefone está sendo exibida.

        Existem dois tipos principais de telas de verificação:
        1. Tela alternativa: contém um select para escolha do país e um campo para o número
        2. Tela padrão: contém apenas um campo para o número completo com código do país

        Returns:
            str: 'alternative' para a tela com select de país, 'standard' para a tela padrão,
                 'unknown' se não for possível identificar
        """
        try:
            # Verificar pela presença do select de país (tela alternativa)
            country_select_xpaths = [
                "//select[@id='countryList']",
                "/html/body/div[1]/div[2]/div[2]/form/span/div[2]/select"
            ]

            for xpath in country_select_xpaths:
                if self._check_for_element(By.XPATH, xpath, timeout=2):
                    logger.info(
                        f"[INFO] Tela alternativa de verificação de telefone detectada com select de país: {xpath}")
                    return "alternative"

            # Verificar pela presença do campo de telefone padrão
            standard_phone_xpaths = [
                "/html/body/div[1]/div[1]/div[2]/c-wiz/div/div[2]/div/div/div/form/span/section[3]/div/div/div/div/div[2]/div[1]//input[@type='tel']",
                "//input[@type='tel' and contains(@aria-label, 'phone')]"
            ]

            for xpath in standard_phone_xpaths:
                if self._check_for_element(By.XPATH, xpath, timeout=2):
                    logger.info(
                        f"[INFO] Tela padrão de verificação de telefone detectada: {xpath}")
                    return "standard"

            logger.warning(
                "[AVISO] Não foi possível identificar o tipo de tela de verificação de telefone")
            return "unknown"

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao identificar tipo de tela de verificação de telefone: {str(e)}")
            return "unknown"

    def _check_and_handle_address_screen(self) -> bool:
        """
        Verifica e trata a tela de definição de endereço residencial.
        Clica no botão "Pular" para continuar.

        Returns:
            bool: True se a tela foi detectada e tratada com sucesso
        """
        try:
            # Aguardar um pouco para garantir que a página carregou completamente
            time.sleep(3)

            # Verificar elementos que indicam que estamos na tela de endereço
            address_indicators = [
                "//div[contains(text(), 'endereço de casa')]",
                "//div[contains(text(), 'home address')]",
                "//h1[contains(text(), 'endereço')]",
                "//span[contains(text(), 'definir seu endereço')]"
            ]

            is_address_screen = False
            for indicator in address_indicators:
                if self._check_for_element(By.XPATH, indicator, timeout=2):
                    logger.info(
                        f"[INFO] Tela de definição de endereço detectada: {indicator}")
                    is_address_screen = True
                    break

            if not is_address_screen:
                return False

            # Capturar screenshot para debug
            if DEBUG_MODE:
                self._save_screenshot("address_screen")

            # Tentar localizar o botão "Pular" usando vários XPaths
            skip_button_xpaths = [
                # XPath específico fornecido
                "/html/body/div[1]/c-wiz[3]/div/div/div/div/div/div[2]/button[1]",
                "//button[@aria-label='Pular']",
                "//button[contains(., 'Pular')]",
                "//button[contains(@class, 'VfPpkd-LgbsSe') and contains(., 'Pular')]",
                "//span[text()='Pular']/ancestor::button",
                "//button[@jsname='ZUkOIc']"
            ]

            button_clicked = False
            for xpath in skip_button_xpaths:
                try:
                    if self._check_for_element(By.XPATH, xpath, timeout=3):
                        skip_button = self.driver.find_element(
                            By.XPATH, xpath)

                        # Garantir que o botão está visível
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView(true);", skip_button)
                        time.sleep(1)

                        # Tentar clicar no botão
                        if self._click_safely(skip_button):
                            logger.info(
                                f"[OK] Botão 'Pular' clicado com sucesso usando XPath: {xpath}")
                            button_clicked = True

                            # Aguardar o processamento após clicar no botão
                            time.sleep(5)
                            self._wait_for_page_load()
                            break
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro ao tentar clicar no botão 'Pular' com XPath {xpath}: {str(e)}")

            # Se não conseguiu clicar em nenhum botão, tentar com JavaScript
            if not button_clicked:
                try:
                    logger.info(
                        "[INFO] Tentando clicar no botão 'Pular' com JavaScript")
                    success = self.driver.execute_script("""
                        // Tentar encontrar botão pelo texto
                        var buttons = document.querySelectorAll('button');
                        for (var i = 0; i < buttons.length; i++) {
                            if (buttons[i].innerText.includes('Pular')) {
                                buttons[i].click();
                                return true;
                            }
                        }
                        
                        // Tentar por spans dentro de botões
                        var spans = document.querySelectorAll('button span');
                        for (var i = 0; i < spans.length; i++) {
                            if (spans[i].innerText.includes('Pular')) {
                                spans[i].closest('button').click();
                                return true;
                            }
                        }
                        
                        // Tentar pelo jsname específico
                        var jsButton = document.querySelector('button[jsname="ZUkOIc"]');
                        if (jsButton) {
                            jsButton.click();
                            return true;
                        }
                        
                        // Tentar pelo XPath específico
                        var xpathResult = document.evaluate(
                            "/html/body/div[1]/c-wiz[3]/div/div/div/div/div/div[2]/button[1]", 
                            document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null
                        );
                        
                        if (xpathResult && xpathResult.singleNodeValue) {
                            xpathResult.singleNodeValue.click();
                            return true;
                        }
                        
                        return false;
                    """)

                    if success:
                        logger.info(
                            "[OK] Botão 'Pular' clicado com sucesso via JavaScript")
                        button_clicked = True

                        # Aguardar o processamento após clicar no botão
                        time.sleep(5)
                        self._wait_for_page_load()
                    else:
                        logger.warning(
                            "[AVISO] Não foi possível encontrar o botão 'Pular' via JavaScript")
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro ao tentar clicar no botão 'Pular' via JavaScript: {str(e)}")

            # Capturar screenshot após tentar clicar no botão
            if DEBUG_MODE:
                self._save_screenshot("after_skip_button_click")

            return button_clicked

        except Exception as e:
            logger.warning(
                f"[AVISO] Erro ao verificar/tratar tela de definição de endereço: {str(e)}")
            return False
