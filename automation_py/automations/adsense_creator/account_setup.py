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

            # Navegar para a página de inscrição do AdSense
            if not self._execute_with_retry(self._navigate_to_adsense_signup):
                return False

            # Preencher o formulário de inscrição
            self.state = SetupState.SIGNUP_FORM
            if not self._execute_with_retry(self._complete_signup_form):
                return False

            # Preencher informações do site
            self.state = SetupState.WEBSITE_INFO
            if not self._execute_with_retry(self._fill_website_info):
                return False

            # Parar aqui conforme solicitado - não prosseguir com as etapas seguintes
            logger.info(
                "[INFO] Automação pausada após preencher o campo de URL do site, conforme solicitado")
            self.state = SetupState.COMPLETED
            return True

        except Exception as e:
            logger.error(
                f"[ERRO] Erro durante configuração da conta AdSense: {str(e)}")
            self.state = SetupState.FAILED
            raise AccountSetupError(
                f"Falha na configuração da conta: {str(e)}")

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
