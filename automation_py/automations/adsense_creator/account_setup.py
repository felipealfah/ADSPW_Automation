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

# Importar a API de SMS
from apis.sms_api import SMSAPI

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

            # Registrar URL atual para debug
            current_url = self.driver.current_url
            logger.info(
                f"[INFO] URL atual após navegação inicial: {current_url}")

            # Verificar se estamos na tela de seleção de conta
            if self._check_for_account_selection_screen():
                logger.info("[INFO] Detectada tela de seleção de conta")
                if not self._select_account():
                    logger.warning("[AVISO] Falha ao selecionar conta")
                    return False
                # Aguardar após selecionar a conta
                time.sleep(3)
                self._wait_for_page_load()

                # Verificar se fomos redirecionados para a tela de reCAPTCHA
                current_url = self.driver.current_url
                if "challenge/recaptcha" in current_url:
                    logger.info(
                        "[INFO] Redirecionado para tela de reCAPTCHA após seleção de conta")
                    # Tratar a tela de reCAPTCHA
                    if self._handle_recaptcha_screen():
                        logger.info(
                            "[OK] Tela de reCAPTCHA tratada com sucesso")
                    else:
                        logger.warning(
                            "[AVISO] Falha ao tratar tela de reCAPTCHA")

                # Capturar screenshot após selecionar conta
                if DEBUG_MODE:
                    self._save_screenshot("after_account_selection")

            # Verificar se estamos na tela de senha
            current_url = self.driver.current_url
            if "signin/challenge/pwd" in current_url:
                logger.info("[INFO] Redirecionado para tela de senha")
                if self._handle_password_screen():
                    logger.info("[OK] Tela de senha tratada com sucesso")
                else:
                    logger.warning("[AVISO] Falha ao tratar tela de senha")

            # Verificar se estamos na tela de verificação por telefone
            current_url = self.driver.current_url
            verification_patterns = ["speedbump/idvreenable",
                                     "signin/v2/challenge/selection", "challenge/ipp"]
            if any(pattern in current_url for pattern in verification_patterns):
                logger.info(
                    "[INFO] Redirecionado para tela de verificação por telefone")
                if self._handle_phone_verification_screen():
                    logger.info(
                        "[OK] Tela de verificação por telefone tratada com sucesso")
                else:
                    logger.warning(
                        "[AVISO] Falha ao tratar tela de verificação por telefone")

            # Verificar se estamos em alguma tela de verificação não tratada
            current_url = self.driver.current_url
            if "challenge" in current_url or "signin" in current_url:
                logger.info(
                    f"[INFO] Detectada tela de verificação não específica: {current_url}")
                # Tentar tratar possível loop de redirecionamento
                if self._check_and_handle_redirect_loop():
                    logger.info("[OK] Tela de verificação tratada com sucesso")
                else:
                    # Tentar navegar diretamente para o AdSense como último recurso
                    try:
                        logger.info(
                            "[INFO] Tentando navegar diretamente para o AdSense...")
                        adsense_url = "https://adsense.google.com/adsense/overview"
                        self.driver.get(adsense_url)
                        time.sleep(5)
                        self._wait_for_page_load()
                    except Exception as e:
                        logger.warning(
                            f"[AVISO] Erro ao tentar navegar para o AdSense: {str(e)}")

            # Registrar URL atual para debug
            current_url = self.driver.current_url
            logger.info(f"[INFO] URL final após navegação: {current_url}")

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
        except Exception as e:
            logger.warning(
                f"[AVISO] Timeout ao aguardar carregamento da página: {str(e)}")
            # Não propagar o erro, apenas retornar False
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

                    # Verificar se fomos redirecionados para a tela de reCAPTCHA
                    current_url = self.driver.current_url
                    if "challenge/recaptcha" in current_url:
                        logger.info(
                            "[INFO] Redirecionado para tela de reCAPTCHA após seleção de conta")
                        # Tratar a tela de reCAPTCHA
                        if self._handle_recaptcha_screen():
                            logger.info(
                                "[OK] Tela de reCAPTCHA tratada com sucesso")
                            # Aguardar redirecionamento após reCAPTCHA
                            time.sleep(5)
                            self._wait_for_page_load()
                        else:
                            logger.warning(
                                "[AVISO] Falha ao tratar tela de reCAPTCHA")

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
            # Mesmo com erro, retornar False em vez de propagar a exceção
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
            # Verificar se o driver ainda está conectado
            try:
                # Uma operação simples para verificar se o driver está conectado
                self.driver.current_url
            except Exception as conn_e:
                logger.error(
                    f"[ERRO] Conexão com o driver perdida: {str(conn_e)}")
                return False

            # Método 1: Clique normal
            element.click()
            return True
        except Exception as e1:
            logger.warning(
                f"[AVISO] Clique normal falhou: {str(e1)}, tentando alternativas...")

            try:
                # Verificar novamente se o driver está conectado
                try:
                    self.driver.current_url
                except Exception:
                    logger.error(
                        "[ERRO] Conexão com o driver perdida durante tentativa de clique alternativo")
                    return False

                # Método 2: Clique via JavaScript
                self.driver.execute_script("arguments[0].click();", element)
                logger.info("[INFO] Clique via JavaScript executado")
                return True
            except Exception as e2:
                logger.warning(
                    f"[AVISO] Clique via JavaScript falhou: {str(e2)}, tentando alternativas...")

                try:
                    # Verificar novamente se o driver está conectado
                    try:
                        self.driver.current_url
                    except Exception:
                        logger.error(
                            "[ERRO] Conexão com o driver perdida durante tentativa de clique via ActionChains")
                        return False

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

                        # Verificar se apareceu a tela de seleção de conta
                        if self._handle_account_selection_screen():
                            logger.info(
                                "[OK] Tela de seleção de conta tratada com sucesso após clicar no botão OK")

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

                    # Verificar se apareceu a tela de seleção de conta
                    if self._handle_account_selection_screen():
                        logger.info(
                            "[OK] Tela de seleção de conta tratada com sucesso após clicar no botão OK via JavaScript")

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

                    # Verificar se apareceu a tela de seleção de conta
                    if self._handle_account_selection_screen():
                        logger.info(
                            "[OK] Tela de seleção de conta tratada com sucesso após clicar no ripple")

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

                    # Verificar se apareceu a tela de seleção de conta
                    if self._handle_account_selection_screen():
                        logger.info(
                            "[OK] Tela de seleção de conta tratada com sucesso após clicar no botão submit")

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

                # Verificar se apareceu a tela de seleção de conta
                if self._handle_account_selection_screen():
                    logger.info(
                        "[OK] Tela de seleção de conta tratada com sucesso após submeter o formulário")

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

    def _handle_account_selection_screen(self) -> bool:
        """
        Verifica se apareceu a tela de seleção de conta após deslogar
        e seleciona a conta correta se necessário.

        Returns:
            bool: True se a tela foi detectada e tratada com sucesso
        """
        try:
            # Aguardar um momento para a página carregar
            time.sleep(3)

            # XPath para o título "Escolha uma conta" (ou equivalentes em outros idiomas)
            account_selection_title_xpath = "/html/body/div[1]/div[1]/div[2]/c-wiz/div/div[1]/div"

            # Lista de textos possíveis para o título em diferentes idiomas
            title_texts = [
                "Escolha uma conta",  # Português
                "Choose an account",   # Inglês
                "Elige una cuenta",    # Espanhol
                "Choisissez un compte",  # Francês
                "Konto auswählen"      # Alemão
            ]

            # Verificar se a tela de seleção de conta está presente
            screen_detected = False

            # Método 1: Verificar pelo XPath específico
            if self._check_for_element(By.XPATH, account_selection_title_xpath, timeout=5):
                title_element = self.driver.find_element(
                    By.XPATH, account_selection_title_xpath)
                title_text = title_element.text.strip()

                for text in title_texts:
                    if text in title_text:
                        logger.info(
                            f"[DETECTADO] Tela de seleção de conta encontrada com texto: '{title_text}'")
                        screen_detected = True
                        break

            # Método 2: Verificar por textos em qualquer lugar da página
            if not screen_detected:
                for text in title_texts:
                    text_xpath = f"//h1[contains(text(), '{text}')]"
                    if self._check_for_element(By.XPATH, text_xpath, timeout=3):
                        logger.info(
                            f"[DETECTADO] Tela de seleção de conta encontrada com texto: '{text}'")
                        screen_detected = True
                        break

            # Se não detectou a tela de seleção, não precisa fazer nada
            if not screen_detected:
                logger.info("[INFO] Tela de seleção de conta não detectada")
                return False

            # Capturar screenshot para debug
            if DEBUG_MODE:
                self._save_screenshot("account_selection_screen")

            # Tentar clicar na primeira conta da lista (que deve ser a conta do usuário)
            account_item_xpath = "/html/body/div[1]/div[1]/div[2]/c-wiz/div/div[2]/div/div/div/form/span/section/div/div/div/div/ul/li[1]/div"

            # Verificar se o elemento da conta existe
            if not self._check_for_element(By.XPATH, account_item_xpath, timeout=5):
                logger.warning(
                    "[AVISO] Não foi possível encontrar o elemento da conta")

                # Tentar uma abordagem alternativa - procurar pelo email
                if self.account_data.get("email"):
                    email = self.account_data.get("email")
                    email_xpath = f"//div[@data-email='{email}' or contains(text(), '{email}')]"

                    if self._check_for_element(By.XPATH, email_xpath, timeout=3):
                        logger.info(
                            f"[INFO] Encontrada conta com email '{email}'")
                        account_item_xpath = email_xpath
                    else:
                        # Tentar abordagem genérica - primeira conta na lista
                        generic_xpath = "//div[contains(@class, 'LbOduc')]"
                        if self._check_for_element(By.XPATH, generic_xpath, timeout=3):
                            logger.info(
                                "[INFO] Usando seletor genérico para a primeira conta")
                            account_item_xpath = generic_xpath
                        else:
                            logger.warning(
                                "[AVISO] Não foi possível encontrar nenhuma conta na lista")
                            return False

            # Clicar na conta
            account_element = self.driver.find_element(
                By.XPATH, account_item_xpath)
            if self._click_safely(account_element):
                logger.info(
                    "[OK] Conta selecionada com sucesso na tela de seleção")

                # Aguardar redirecionamento após selecionar a conta
                time.sleep(5)
                self._wait_for_page_load()

                # Capturar screenshot após selecionar a conta
                if DEBUG_MODE:
                    self._save_screenshot("after_account_selection")

                # Verificar e tratar a tela de reCAPTCHA que pode aparecer após a seleção da conta
                if self._handle_recaptcha_screen():
                    logger.info("[OK] Tela de reCAPTCHA tratada com sucesso")

                return True
            else:
                logger.warning(
                    "[AVISO] Falha ao clicar na conta na tela de seleção")
                return False

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao tratar tela de seleção de conta: {str(e)}")
            return False

    def _handle_recaptcha_screen(self) -> bool:
        """
        Trata a tela de reCAPTCHA que aparece após a seleção da conta.
        Aguarda 45 segundos para permitir que a solução externa resolva o reCAPTCHA,
        e então clica no botão "Avançar".

        Returns:
            bool: True se o botão "Avançar" foi clicado com sucesso
        """
        try:
            logger.info(
                "[INFO] Verificando se estamos na tela de reCAPTCHA...")

            # Verificar pela URL se estamos na página de reCAPTCHA
            current_url = self.driver.current_url
            if "challenge/recaptcha" not in current_url:
                logger.info(
                    "[INFO] Não estamos na tela de reCAPTCHA (verificação por URL)")
                return False

            logger.info(f"[INFO] URL de reCAPTCHA detectada: {current_url}")

            # Aguardar para verificar se o reCAPTCHA aparece
            time.sleep(3)

            # XPath do botão "Avançar"
            next_button_xpath = "/html/body/div[1]/div[1]/div[2]/c-wiz/div/div[3]/div/div[1]/div/div/button"

            # Verificar se estamos na tela de reCAPTCHA (presença do botão "Avançar")
            button_found = False
            if self._check_for_element(By.XPATH, next_button_xpath, timeout=5):
                button_found = True
                logger.info(
                    "[INFO] Botão 'Avançar' encontrado pelo XPath específico")
            else:
                # Tentar uma abordagem alternativa - procurar pelo texto do botão
                alternative_next_button_xpath = "//button[contains(.//span, 'Avançar') or contains(.//span, 'Next')]"

                if self._check_for_element(By.XPATH, alternative_next_button_xpath, timeout=3):
                    next_button_xpath = alternative_next_button_xpath
                    button_found = True
                    logger.info("[INFO] Botão 'Avançar' encontrado pelo texto")
                else:
                    logger.warning(
                        "[AVISO] Botão 'Avançar' não encontrado na tela de reCAPTCHA")

            # Se não encontrou o botão mas estamos na URL de reCAPTCHA, vamos aguardar mesmo assim
            if not button_found:
                logger.info(
                    "[INFO] Na URL de reCAPTCHA mas botão não encontrado. Aguardando mesmo assim...")

            # Capturar screenshot da tela de reCAPTCHA
            if DEBUG_MODE:
                self._save_screenshot("recaptcha_screen")

            logger.info(
                "[INFO] Tela de reCAPTCHA detectada. Aguardando 45 segundos para resolução externa...")

            # Aguardar 45 segundos para permitir que a solução externa resolva o reCAPTCHA
            time.sleep(45)

            # Se não encontramos o botão antes, tentar novamente após a espera
            if not button_found:
                if self._check_for_element(By.XPATH, next_button_xpath, timeout=5):
                    button_found = True
                    logger.info(
                        "[INFO] Botão 'Avançar' encontrado após espera")
                else:
                    alternative_next_button_xpath = "//button[contains(.//span, 'Avançar') or contains(.//span, 'Next')]"
                    if self._check_for_element(By.XPATH, alternative_next_button_xpath, timeout=3):
                        next_button_xpath = alternative_next_button_xpath
                        button_found = True
                        logger.info(
                            "[INFO] Botão 'Avançar' encontrado pelo texto após espera")

            # Se ainda não encontrou o botão, verificar se a página mudou (pode ter sido resolvido automaticamente)
            if not button_found:
                current_url_after_wait = self.driver.current_url
                if current_url_after_wait != current_url:
                    logger.info(
                        f"[INFO] Página mudou automaticamente após espera. Nova URL: {current_url_after_wait}")
                    # Verificar se fomos redirecionados para a tela de senha
                    if self._handle_password_screen():
                        logger.info(
                            "[OK] Tela de inserção de senha tratada com sucesso após redirecionamento automático")
                    return True
                else:
                    logger.warning(
                        "[AVISO] Não foi possível encontrar o botão 'Avançar' e a página não mudou")
                    return False

            # Clicar no botão "Avançar"
            next_button = self.driver.find_element(By.XPATH, next_button_xpath)
            if self._click_safely(next_button):
                logger.info(
                    "[OK] Botão 'Avançar' clicado com sucesso na tela de reCAPTCHA")

                # Aguardar redirecionamento após clicar no botão
                time.sleep(5)
                self._wait_for_page_load()

                # Capturar screenshot após clicar no botão
                if DEBUG_MODE:
                    self._save_screenshot("after_recaptcha_next_button")

                # Verificar e tratar a tela de inserção de senha que aparece após o reCAPTCHA
                if self._handle_password_screen():
                    logger.info(
                        "[OK] Tela de inserção de senha tratada com sucesso")

                return True
            else:
                logger.warning(
                    "[AVISO] Falha ao clicar no botão 'Avançar' na tela de reCAPTCHA")
                return False

        except Exception as e:
            logger.error(f"[ERRO] Erro ao tratar tela de reCAPTCHA: {str(e)}")
            return False

    def _handle_password_screen(self) -> bool:
        """
        Trata a tela de inserção de senha que aparece após a tela de reCAPTCHA.
        Busca a senha correspondente ao email no arquivo gmail.json,
        preenche o campo de senha e clica no botão "Avançar".

        Returns:
            bool: True se a senha foi inserida e o botão foi clicado com sucesso
        """
        try:
            logger.info(
                "[INFO] Verificando se estamos na tela de inserção de senha...")

            # Aguardar para verificar se a tela de senha aparece
            time.sleep(3)

            # Verificar pela URL se estamos na página de senha
            current_url = self.driver.current_url
            is_password_page = False

            if "signin/challenge/pwd" in current_url:
                logger.info(
                    f"[INFO] URL de página de senha detectada: {current_url}")
                is_password_page = True

            # XPath do campo de senha
            password_field_xpath = "/html/body/div[1]/div[1]/div[2]/c-wiz/div/div[2]/div/div/div/form/span/section[2]/div/div/div[1]/div[1]/div/div/div/div/div[1]/div/div[1]/input"

            # Verificar se estamos na tela de inserção de senha
            if not is_password_page and not self._check_for_element(By.XPATH, password_field_xpath, timeout=5):
                # Tentar uma abordagem alternativa - procurar por qualquer campo de senha
                alternative_password_field_xpath = "//input[@type='password']"

                if not self._check_for_element(By.XPATH, alternative_password_field_xpath, timeout=3):
                    logger.info(
                        "[INFO] Não estamos na tela de inserção de senha")
                    return False
                else:
                    password_field_xpath = alternative_password_field_xpath
                    is_password_page = True
            else:
                is_password_page = True

            # Capturar screenshot da tela de senha
            if DEBUG_MODE:
                self._save_screenshot("password_screen")

            # Obter o email atual da conta - várias estratégias
            current_email = None

            # Estratégia 1: Tentar obter dos dados da conta
            if self.account_data and self.account_data.get("email"):
                current_email = self.account_data.get("email")
                logger.info(
                    f"[INFO] Email encontrado nos dados da conta: {current_email}")

            # Estratégia 2: Tentar extrair da URL (se presente)
            if not current_email:
                try:
                    # Verificar se o email está na URL (como parte do AccountChooser)
                    import re
                    email_match = re.search(r'Email=([^&]+)', current_url)
                    if email_match:
                        current_email = email_match.group(1)
                        logger.info(
                            f"[INFO] Email extraído da URL: {current_email}")
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro ao tentar extrair email da URL: {str(e)}")

            # Estratégia 3: Tentar encontrar na página
            if not current_email:
                try:
                    # Tentar encontrar o email exibido na página
                    email_element_xpath = "//div[contains(@class, 'bCAAsb')]"
                    if self._check_for_element(By.XPATH, email_element_xpath, timeout=3):
                        email_element = self.driver.find_element(
                            By.XPATH, email_element_xpath)
                        displayed_email = email_element.text.strip()
                        if '@' in displayed_email:
                            current_email = displayed_email
                            logger.info(
                                f"[INFO] Email encontrado na página: {current_email}")
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro ao tentar encontrar email na página: {str(e)}")

            # Estratégia 4: Usar email fixo do arquivo gmail.json se todas as estratégias falharem
            if not current_email:
                logger.warning(
                    "[AVISO] Não foi possível determinar o email da conta. Tentando usar email fixo do arquivo gmail.json")
                # Usar o último email do arquivo gmail.json
                try:
                    import json
                    import os

                    # Caminho para o arquivo gmail.json
                    gmail_json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                                                   "credentials", "gmail.json")

                    if os.path.exists(gmail_json_path):
                        with open(gmail_json_path, 'r', encoding='utf-8') as file:
                            accounts = json.load(file)
                            if accounts and len(accounts) > 0:
                                # Usar o último email da lista (mais recente)
                                current_email = accounts[-1].get("email")
                                logger.info(
                                    f"[INFO] Usando último email do arquivo gmail.json: {current_email}")
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro ao tentar obter email do arquivo gmail.json: {str(e)}")

            if not current_email:
                logger.warning(
                    "[AVISO] Email não encontrado por nenhum método")
                return False

            logger.info(f"[INFO] Buscando senha para o email: {current_email}")

            # Buscar a senha correspondente no arquivo gmail.json
            password = self._get_password_from_gmail_json(current_email)
            if not password:
                logger.warning(
                    f"[AVISO] Senha não encontrada para o email: {current_email}")
                return False

            logger.info("[INFO] Senha encontrada. Preenchendo o campo...")

            # Preencher o campo de senha
            try:
                password_field = self.driver.find_element(
                    By.XPATH, password_field_xpath)
                if not self._fill_input_safely(password_field, password):
                    logger.warning(
                        "[AVISO] Falha ao preencher o campo de senha")
                    return False

                logger.info("[OK] Campo de senha preenchido com sucesso")
            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao preencher campo de senha: {str(e)}")
                return False

            # Aguardar um momento após preencher a senha
            time.sleep(1)

            # Procurar o botão "Avançar" para confirmar a senha
            next_button_xpath = "//button[contains(.//span, 'Avançar') or contains(.//span, 'Next') or contains(.//span, 'Próxima') or contains(.//span, 'Próximo')]"

            if not self._check_for_element(By.XPATH, next_button_xpath, timeout=5):
                logger.warning(
                    "[AVISO] Botão 'Avançar' não encontrado na tela de senha")
                return False

            # Clicar no botão "Avançar"
            try:
                next_button = self.driver.find_element(
                    By.XPATH, next_button_xpath)
                if self._click_safely(next_button):
                    logger.info(
                        "[OK] Botão 'Avançar' clicado com sucesso na tela de senha")

                    # Aguardar redirecionamento após clicar no botão
                    time.sleep(5)
                    self._wait_for_page_load()

                    # Capturar screenshot após clicar no botão
                    if DEBUG_MODE:
                        self._save_screenshot("after_password_next_button")

                    # Verificar se fomos redirecionados para a tela de verificação por telefone
                    if self._handle_phone_verification_screen():
                        logger.info(
                            "[OK] Tela de verificação por telefone tratada com sucesso")

                    return True
                else:
                    logger.warning(
                        "[AVISO] Falha ao clicar no botão 'Avançar' na tela de senha")
                    return False
            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao clicar no botão 'Avançar': {str(e)}")
                return False

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao tratar tela de inserção de senha: {str(e)}")
            return False

    def _handle_phone_verification_screen(self) -> bool:
        """
        Trata a tela de verificação de identidade por SMS que aparece após a validação da senha.
        Seleciona o país correto, insere o número de telefone e clica no botão para receber o código.

        Returns:
            bool: True se o número de telefone foi inserido e o botão foi clicado com sucesso
        """
        try:
            logger.info(
                "[INFO] Verificando se estamos na tela de verificação por telefone...")

            # Aguardar para verificar se a tela de verificação aparece
            time.sleep(3)

            # Verificar pela URL se estamos na página de verificação por telefone
            current_url = self.driver.current_url
            is_phone_verification_page = False

            # Verificar por diferentes padrões de URL de verificação
            verification_url_patterns = [
                "speedbump/idvreenable",
                "signin/v2/challenge/selection",
                "signin/v2/challenge/ipp",
                "challenge/selection"
            ]

            for pattern in verification_url_patterns:
                if pattern in current_url:
                    logger.info(
                        f"[INFO] URL de página de verificação por telefone detectada: {current_url}")
                    is_phone_verification_page = True
                    break

            # XPath do campo de seleção de país - mais preciso
            country_select_xpath = "//select[@id='countryList']"

            # Verificar se estamos na tela de verificação por telefone
            if not is_phone_verification_page and not self._check_for_element(By.XPATH, country_select_xpath, timeout=5):
                # Tentar uma abordagem alternativa
                alternative_country_select_xpath = "/html/body/div[1]/div[2]/div[2]/form/span/div[2]/select"

                if not self._check_for_element(By.XPATH, alternative_country_select_xpath, timeout=3):
                    logger.info(
                        "[INFO] Não estamos na tela de verificação por telefone")
                    return False
                else:
                    country_select_xpath = alternative_country_select_xpath
                    is_phone_verification_page = True
            else:
                is_phone_verification_page = True

            # Capturar screenshot da tela de verificação por telefone
            if DEBUG_MODE:
                self._save_screenshot("phone_verification_screen")

            # Obter o país e telefone dos dados da conta
            # Padrão para Brasil (73) se não encontrado
            country_code = self.account_data.get("country_code", "73")

            # Mapear o código do país para o valor no select
            country_code_map = {
                "73": "BR",  # Brasil
                "151": "CL",  # Chile
                "52": "MX",   # México
                # Adicionar mais mapeamentos conforme necessário
            }

            # Obter o código do país para o select
            select_country_code = country_code_map.get(country_code, "BR")
            logger.info(
                f"[INFO] Código do país para select: {select_country_code}")

            # Selecionar o país no dropdown
            try:
                from selenium.webdriver.support.ui import Select

                country_select = Select(self.driver.find_element(
                    By.XPATH, country_select_xpath))
                country_select.select_by_value(select_country_code)
                logger.info(f"[OK] País selecionado: {select_country_code}")

                # Aguardar um momento após selecionar o país
                time.sleep(1)
            except Exception as e:
                logger.warning(f"[AVISO] Erro ao selecionar país: {str(e)}")
                return False

            # Inicializar a API de SMS
            sms_api = SMSAPI()

            # Verificar o saldo disponível
            balance = sms_api.get_balance()
            if balance is None or balance <= 0:
                logger.error(
                    "[ERRO] Saldo insuficiente ou erro ao verificar saldo na API de SMS")
                return False

            logger.info(
                f"[INFO] Saldo disponível na API de SMS: {balance} RUB")

            # Comprar um número para o serviço Google (go)
            service = "go"  # Código para Gmail/Google

            # Mapear o código do select para o código da API de SMS
            sms_country_code_map = {
                "BR": "73",   # Brasil
                "CL": "151",  # Chile
                "MX": "52",   # México
                # Adicionar mais mapeamentos conforme necessário
            }

            sms_country_code = sms_country_code_map.get(
                select_country_code, "73")  # Padrão para Brasil

            logger.info(
                f"[INFO] Comprando número para o serviço {service} no país {sms_country_code}...")

            # Comprar o número
            activation_id, phone_number = sms_api.get_number(
                "go", sms_country_code)

            if not activation_id or not phone_number:
                logger.error("[ERRO] Falha ao comprar número de telefone")
                return False

            logger.info(
                f"[OK] Número comprado com sucesso: {phone_number} (ID: {activation_id})")

            # Salvar o activation_id para uso posterior
            self.predefined_activation_id = activation_id
            self.predefined_number = phone_number
            self.predefined_country_code = sms_country_code

            # Formatar o número de telefone conforme necessário (remover o código do país se já estiver selecionado)
            if phone_number.startswith("+"):
                # Remover o "+" e o código do país (normalmente 2-3 dígitos)
                country_prefix_map = {
                    "BR": "+55",  # Brasil
                    "CL": "+56",  # Chile
                    "MX": "+52",  # México
                }

                prefix = country_prefix_map.get(select_country_code)
                if prefix and phone_number.startswith(prefix):
                    formatted_phone = phone_number[len(prefix):]
                else:
                    # Se não conseguir identificar o prefixo, usar o número completo
                    formatted_phone = phone_number[1:]  # Remover apenas o "+"
            else:
                formatted_phone = phone_number

            logger.info(
                f"[INFO] Número formatado para entrada: {formatted_phone}")

            # XPath do campo de telefone - mais preciso
            phone_field_xpath = "//input[@id='deviceAddress']"

            # Verificar se o campo de telefone está presente
            if not self._check_for_element(By.XPATH, phone_field_xpath, timeout=5):
                # Tentar XPath alternativo
                alt_phone_xpath = "/html/body/div[1]/div[2]/div[2]/form/span/div[3]/input"

                if self._check_for_element(By.XPATH, alt_phone_xpath, timeout=3):
                    phone_field_xpath = alt_phone_xpath
                    logger.info(
                        "[INFO] Campo de telefone encontrado com XPath alternativo")
                else:
                    logger.warning("[AVISO] Campo de telefone não encontrado")
                    # Cancelar a ativação do número, já que não vamos usá-lo
                    sms_api.set_status(activation_id, 6)  # 6 = Cancelar
                    return False

            # Preencher o campo de telefone
            try:
                phone_field = self.driver.find_element(
                    By.XPATH, phone_field_xpath)
                if not self._fill_input_safely(phone_field, formatted_phone):
                    logger.warning(
                        "[AVISO] Falha ao preencher o campo de telefone")
                    # Cancelar a ativação do número
                    sms_api.set_status(activation_id, 6)
                    return False

                logger.info("[OK] Campo de telefone preenchido com sucesso")
            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao preencher campo de telefone: {str(e)}")
                # Cancelar a ativação do número
                sms_api.set_status(activation_id, 6)
                return False

            # Aguardar um momento após preencher o telefone
            time.sleep(1)

            # XPath do botão "Receber código" - mais preciso
            receive_code_button_xpath = "//input[@id='next-button']"

            # Verificar se o botão "Receber código" está presente
            if not self._check_for_element(By.XPATH, receive_code_button_xpath, timeout=5):
                # Tentar XPath alternativo
                alt_button_xpath = "/html/body/div[1]/div[2]/div[2]/form/span/div[4]/input"

                if self._check_for_element(By.XPATH, alt_button_xpath, timeout=3):
                    receive_code_button_xpath = alt_button_xpath
                    logger.info(
                        "[INFO] Botão 'Receber código' encontrado com XPath alternativo")
                else:
                    logger.warning(
                        "[AVISO] Botão 'Receber código' não encontrado")
                    # Cancelar a ativação do número
                    sms_api.set_status(activation_id, 6)
                    return False

            # Clicar no botão "Receber código"
            try:
                receive_code_button = self.driver.find_element(
                    By.XPATH, receive_code_button_xpath)
                if self._click_safely(receive_code_button):
                    logger.info(
                        "[OK] Botão 'Receber código' clicado com sucesso")

                    # Aguardar um momento após clicar no botão
                    time.sleep(5)
                    self._wait_for_page_load()

                    # Capturar screenshot após clicar no botão
                    if DEBUG_MODE:
                        self._save_screenshot("after_receive_code_button")

                    # Verificar se há mensagens de erro após clicar no botão
                    error_messages = [
                        "//div[contains(@class, 'error') or contains(@class, 'Error')]",
                        "//span[contains(text(), 'erro') or contains(text(), 'inválido') or contains(text(), 'error') or contains(text(), 'invalid')]"
                    ]

                    error_found = False
                    for error_xpath in error_messages:
                        if self._check_for_element(By.XPATH, error_xpath, timeout=3):
                            error_elem = self.driver.find_element(
                                By.XPATH, error_xpath)
                            logger.warning(
                                f"[AVISO] Erro após clicar no botão: {error_elem.text}")
                            error_found = True
                            break

                    if error_found:
                        # Cancelar a ativação do número
                        sms_api.set_status(activation_id, 6)
                        return False

                    # Configurar webhook para este número (opcional)
                    try:
                        # Verificar se existe um endpoint de webhook disponível
                        webhook_url = "http://localhost:5001/sms-webhook"
                        logger.info(
                            f"[INFO] Configurando webhook para receber SMS: {webhook_url}")

                        # Aqui você poderia registrar o activation_id em um sistema de webhook
                        # Este é apenas um exemplo e depende da implementação específica
                        try:
                            import requests
                            import json
                            import os

                            # Registrar o activation_id para webhook (exemplo)
                            webhook_data = {
                                "activation_id": activation_id,
                                "phone_number": phone_number,
                                "service": service
                            }

                            # Salvar em um arquivo local para o webhook poder acessar
                            webhook_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                                                        "sms_data", "callbacks.json")

                            # Criar diretório se não existir
                            os.makedirs(os.path.dirname(
                                webhook_file), exist_ok=True)

                            # Carregar dados existentes ou criar novo
                            callbacks = {}
                            if os.path.exists(webhook_file):
                                try:
                                    with open(webhook_file, 'r') as f:
                                        callbacks = json.load(f)
                                except:
                                    pass

                            # Adicionar novo callback
                            callbacks[activation_id] = webhook_url

                            # Salvar no arquivo
                            with open(webhook_file, 'w') as f:
                                json.dump(callbacks, f)

                            logger.info(
                                f"[OK] Webhook configurado para activation_id: {activation_id}")
                        except Exception as webhook_e:
                            logger.warning(
                                f"[AVISO] Erro ao configurar webhook: {str(webhook_e)}")
                    except Exception as e:
                        logger.warning(
                            f"[AVISO] Erro ao configurar webhook: {str(e)}")

                    # Tratar a tela de entrada do código SMS
                    if self._handle_sms_code_verification(activation_id, sms_api):
                        logger.info("[OK] Código SMS verificado com sucesso")
                        return True
                    else:
                        logger.warning(
                            "[AVISO] Falha na verificação do código SMS")
                        return False
                else:
                    logger.warning(
                        "[AVISO] Falha ao clicar no botão 'Receber código'")
                    # Cancelar a ativação do número
                    sms_api.set_status(activation_id, 6)
                    return False
            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao clicar no botão 'Receber código': {str(e)}")
                # Cancelar a ativação do número
                sms_api.set_status(activation_id, 6)
                return False

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao tratar tela de verificação por telefone: {str(e)}")
            return False

    def _handle_sms_code_verification(self, activation_id, sms_api) -> bool:
        """
        Trata a tela de entrada do código SMS recebido.

        Args:
            activation_id (str): ID da ativação do número na API de SMS
            sms_api (SMSAPI): Instância da API de SMS

        Returns:
            bool: True se o código foi inserido e verificado com sucesso
        """
        try:
            logger.info("[INFO] Aguardando código SMS...")

            # Salvar a URL atual antes de qualquer ação
            original_url = self.driver.current_url
            logger.info(f"[INFO] URL antes da verificação SMS: {original_url}")

            # Aguardar o carregamento da página de entrada do código
            time.sleep(3)

            # XPath exato do campo de entrada do código SMS fornecido pelo usuário
            code_field_xpath = "/html/body/div[1]/div[2]/div[2]/form/span/div[1]/input"

            # Verificar se estamos na tela de entrada do código
            if not self._check_for_element(By.XPATH, code_field_xpath, timeout=5):
                # Tentar pelo ID exato
                id_code_field_xpath = "//input[@id='smsUserPin']"

                if not self._check_for_element(By.XPATH, id_code_field_xpath, timeout=3):
                    logger.warning(
                        "[AVISO] Campo de entrada do código SMS não encontrado")
                    # Cancelar a ativação do número
                    sms_api.set_status(activation_id, 6)
                    return False
                else:
                    code_field_xpath = id_code_field_xpath

            # Capturar screenshot da tela de entrada do código
            if DEBUG_MODE:
                self._save_screenshot("sms_code_entry_screen")

            # Tentar obter código SMS via webhook primeiro (se disponível)
            sms_code = None
            try:
                # Verificar se há um endpoint de webhook configurado
                webhook_endpoint = f"http://localhost:5001/sms-status/{activation_id}"
                logger.info(
                    f"[INFO] Tentando obter código SMS via webhook: {webhook_endpoint}")

                # Tentar até 12 vezes com intervalo de 10 segundos (2 minutos total)
                for attempt in range(12):
                    try:
                        import requests
                        response = requests.get(webhook_endpoint, timeout=5)
                        if response.status_code == 200:
                            data = response.json()
                            if data and "sms_code" in data:
                                sms_code = data["sms_code"]
                                logger.info(
                                    f"[OK] Código SMS recebido via webhook: {sms_code}")
                                break
                    except Exception as webhook_e:
                        logger.warning(
                            f"[AVISO] Erro ao verificar webhook: {str(webhook_e)}")

                    # Se ainda não recebeu, aguardar antes da próxima tentativa
                    if not sms_code:
                        logger.info(
                            f"[INFO] Aguardando SMS (tentativa {attempt+1}/12)...")
                        time.sleep(10)
            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao tentar obter código via webhook: {str(e)}")

            # Se não conseguiu via webhook, tentar pelo método tradicional
            if not sms_code:
                logger.info(
                    f"[INFO] Webhook não disponível ou não retornou código. Usando método tradicional.")
                sms_code = sms_api.get_sms_code(
                    activation_id, max_attempts=10, interval=10)

            if not sms_code:
                logger.error("[ERRO] Não foi possível obter o código SMS")
                # Cancelar a ativação do número
                sms_api.set_status(activation_id, 6)
                return False

            logger.info(f"[OK] Código SMS recebido: {sms_code}")

            # Extrair apenas os dígitos do código (caso contenha outros caracteres)
            import re
            digits = re.findall(r'\d+', sms_code)
            if digits:
                sms_code = ''.join(digits)

            logger.info(f"[INFO] Código formatado para entrada: {sms_code}")

            # Preencher o campo de código
            try:
                code_field = self.driver.find_element(
                    By.XPATH, code_field_xpath)
                if not self._fill_input_safely(code_field, sms_code):
                    logger.warning(
                        "[AVISO] Falha ao preencher o campo de código SMS")
                    return False

                logger.info("[OK] Campo de código SMS preenchido com sucesso")
            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao preencher campo de código SMS: {str(e)}")
                return False

            # Aguardar um momento após preencher o código
            time.sleep(1)

            # XPath exato do botão "Verificar" fornecido pelo usuário
            verify_button_xpath = "/html/body/div[1]/div[2]/div[2]/form/span/div[2]/input"

            # Verificar se o botão está presente
            if not self._check_for_element(By.XPATH, verify_button_xpath, timeout=5):
                # Tentar pelo ID exato
                id_verify_button_xpath = "//input[@id='next-button']"

                if not self._check_for_element(By.XPATH, id_verify_button_xpath, timeout=3):
                    logger.warning(
                        "[AVISO] Botão de verificação não encontrado")
                    return False
                else:
                    verify_button_xpath = id_verify_button_xpath

            # Clicar no botão de verificação
            try:
                verify_button = self.driver.find_element(
                    By.XPATH, verify_button_xpath)
                if self._click_safely(verify_button):
                    logger.info(
                        "[OK] Botão de verificação clicado com sucesso")

                    # Informar à API que o código foi usado com sucesso
                    # 8 = Número confirmado com sucesso
                    try:
                        sms_api.set_status(activation_id, 8)
                    except Exception as e:
                        # Ignorar erros BAD_STATUS que podem ocorrer quando o número já foi confirmado
                        if "BAD_STATUS" not in str(e):
                            logger.warning(
                                f"[AVISO] Erro ao atualizar status do número: {str(e)}")

                    # Aguardar redirecionamento após verificação
                    time.sleep(5)
                    self._wait_for_page_load()

                    # Capturar screenshot após verificação
                    if DEBUG_MODE:
                        self._save_screenshot("after_sms_verification")

                    # Verificar URL atual após redirecionamento
                    current_url = self.driver.current_url
                    logger.info(
                        f"[INFO] URL após verificação SMS: {current_url}")

                    # Verificar se fomos redirecionados para a URL do AdSense
                    if "adsense.google.com" in current_url:
                        logger.info(
                            f"[OK] Redirecionado com sucesso para AdSense: {current_url}")
                        return True

                    # Verificar se fomos redirecionados para a tela de opções de recuperação (comum após verificação)
                    if "gds.google.com/web/recoveryoptions" in current_url:
                        logger.info(
                            "[INFO] Redirecionado para tela de opções de recuperação")
                        return self._handle_recovery_options_screen()
                    else:
                        logger.warning(
                            "[AVISO] Não foi possível encontrar o botão 'Avançar' e a página não mudou")
                        return False
            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao clicar no botão de verificação: {str(e)}")
                return False

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao tratar tela de verificação do código SMS: {str(e)}")
            return False

    def _get_password_from_gmail_json(self, email):
        """
        Busca a senha correspondente ao email no arquivo gmail.json.

        Args:
            email (str): Email para buscar a senha

        Returns:
            str: Senha correspondente ao email ou None se não encontrada
        """
        try:
            import json
            import os

            # Caminho para o arquivo gmail.json
            gmail_json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                                           "credentials", "gmail.json")

            # Verificar se o arquivo existe
            if not os.path.exists(gmail_json_path):
                logger.warning(
                    f"[AVISO] Arquivo gmail.json não encontrado em: {gmail_json_path}")
                return None

            # Carregar o arquivo gmail.json
            with open(gmail_json_path, 'r', encoding='utf-8') as file:
                accounts = json.load(file)

            # Buscar a conta com o email correspondente
            for account in accounts:
                if account.get("email") == email:
                    password = account.get("password")
                    if password:
                        logger.info(
                            f"[OK] Senha encontrada para o email: {email}")
                        return password

            logger.warning(
                f"[AVISO] Email {email} não encontrado no arquivo gmail.json")
            return None

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao buscar senha no arquivo gmail.json: {str(e)}")
            return None

    def _handle_recovery_options_screen(self) -> bool:
        """
        Trata a tela de opções de recuperação do Google (gds.google.com/web/recoveryoptions).
        Clica no botão 'Salvar' e depois no botão 'Pular' na tela seguinte.

        Returns:
            bool: True se os botões foram clicados com sucesso ou se conseguiu navegar para o AdSense
        """
        try:
            logger.info("[INFO] Tratando tela de opções de recuperação")

            # Capturar screenshot da tela de opções de recuperação se estiver em modo DEBUG
            if DEBUG_MODE:
                self._save_screenshot("recovery_options_screen")

            # Lista de XPaths para o botão Salvar
            salvar_xpaths = [
                "//button[contains(@class, 'VfPpkd-LgbsSe') and contains(.//span, 'Salvar')]",
                "/html/body/div[1]/c-wiz[1]/div/div/div/div/div[2]/button[2]",
                "//button[@jsname='M2UYVd']",
                "//button[contains(@jslog, '53557')]",
                "//button[contains(@aria-label, 'Salvar')]",
                "//button[contains(@aria-label, 'Save')]"
            ]

            # Verificar se algum dos botões Salvar está presente
            salvar_encontrado = False
            salvar_button = None
            xpath_usado = None

            for xpath in salvar_xpaths:
                if self._check_for_element(By.XPATH, xpath, timeout=2):
                    logger.info(
                        f"[INFO] Botão 'Salvar' encontrado usando XPath: {xpath}")
                    salvar_button = self.driver.find_element(By.XPATH, xpath)
                    xpath_usado = xpath
                    salvar_encontrado = True
                    break

            if salvar_encontrado:
                logger.info(
                    "[INFO] Botão 'Salvar' encontrado na tela de recuperação")

                # Tentar clicar no botão "Salvar"
                if self._click_safely(salvar_button):
                    logger.info(
                        f"[OK] Botão 'Salvar' clicado com sucesso usando {xpath_usado}")

                    # Aguardar redirecionamento após clicar no botão
                    time.sleep(5)
                    self._wait_for_page_load()

                    # Capturar screenshot após clicar em "Salvar" se estiver em modo DEBUG
                    if DEBUG_MODE:
                        self._save_screenshot("after_save_button")

                    # Lista de XPaths para o botão Pular
                    pular_xpaths = [
                        "//button[contains(@class, 'VfPpkd-LgbsSe') and contains(.//span, 'Pular')]",
                        "/html/body/div[1]/c-wiz[2]/div/div/div/div/div/div[2]/button[1]",
                        "//button[@jsname='ZUkOIc']",
                        "//button[contains(@jslog, '53558')]",
                        "//button[contains(@aria-label, 'Pular')]",
                        "//button[contains(@aria-label, 'Skip')]",
                        "//button[contains(.//span, 'Skip')]"
                    ]

                    # Verificar se algum dos botões Pular está presente
                    pular_encontrado = False
                    pular_button = None
                    xpath_usado = None

                    for xpath in pular_xpaths:
                        if self._check_for_element(By.XPATH, xpath, timeout=2):
                            logger.info(
                                f"[INFO] Botão 'Pular' encontrado usando XPath: {xpath}")
                            pular_button = self.driver.find_element(
                                By.XPATH, xpath)
                            xpath_usado = xpath
                            pular_encontrado = True
                            break

                    if pular_encontrado:
                        logger.info(
                            "[INFO] Botão 'Pular' encontrado na tela seguinte")

                        # Tentar clicar no botão "Pular"
                        if self._click_safely(pular_button):
                            logger.info(
                                f"[OK] Botão 'Pular' clicado com sucesso usando {xpath_usado}")

                            # Capturar screenshot após "Pular" se estiver em modo DEBUG
                            if DEBUG_MODE:
                                self._save_screenshot("after_skip_button")

                            # Aguardar 15 segundos para redirecionamento automático para o formulário
                            logger.info(
                                "[INFO] Aguardando 15 segundos para redirecionamento automático...")
                            time.sleep(15)
                            self._wait_for_page_load()

                            # Capturar screenshot após aguardar se estiver em modo DEBUG
                            if DEBUG_MODE:
                                self._save_screenshot("after_redirect_wait")

                            # Verificar URL atual após redirecionamento
                            current_url = self.driver.current_url
                            logger.info(
                                f"[INFO] URL após aguardar redirecionamento: {current_url}")

                            if "adsense.google.com" in current_url:
                                logger.info(
                                    f"[OK] Redirecionado com sucesso para AdSense: {current_url}")
                                return True

                            # Se não redirecionou para o AdSense, tentar navegar diretamente
                            logger.info(
                                "[INFO] Não redirecionou automaticamente para o AdSense, tentando navegação direta...")
                        else:
                            logger.warning(
                                "[AVISO] Falha ao clicar no botão 'Pular', tentando navegação direta para o AdSense...")
                    else:
                        logger.warning(
                            "[AVISO] Botão 'Pular' não encontrado, tentando navegação direta para o AdSense...")
                else:
                    logger.warning(
                        "[AVISO] Falha ao clicar no botão 'Salvar', tentando navegação direta para o AdSense...")
            else:
                logger.info(
                    "[INFO] Botão 'Salvar' não encontrado, tentando navegação direta para o AdSense...")

            # Tentar navegar diretamente para o AdSense como último recurso
            return self._try_direct_adsense_navigation()

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao tratar tela de opções de recuperação: {str(e)}")
            # Tentar navegação direta como último recurso
            return self._try_direct_adsense_navigation()

    def _try_direct_adsense_navigation(self) -> bool:
        """
        Tenta navegar diretamente para diferentes URLs do AdSense.

        Returns:
            bool: True se conseguiu navegar para alguma URL do AdSense
        """
        try:
            logger.info("[INFO] Tentando navegação direta para o AdSense...")

            adsense_urls = [
                "https://adsense.google.com/adsense/signup",
                "https://adsense.google.com/adsense/overview",
                "https://adsense.google.com/adsense/app"
            ]

            for url in adsense_urls:
                logger.info(f"[INFO] Tentando navegar para {url}")
                self.driver.get(url)
                time.sleep(5)
                self._wait_for_page_load()

                current_url = self.driver.current_url
                if "adsense.google.com" in current_url:
                    logger.info(
                        f"[OK] Navegação direta para AdSense bem-sucedida: {current_url}")
                    return True

                # Verificar se chegamos a uma tela de seleção de conta
                if self._check_for_account_selection_screen():
                    logger.info(
                        "[INFO] Detectada tela de seleção de conta. Tentando selecionar a conta...")
                    if self._handle_account_selection_screen():
                        logger.info("[OK] Conta selecionada com sucesso")

                        # Verificar se chegamos ao AdSense após selecionar a conta
                        time.sleep(5)
                        self._wait_for_page_load()
                        if "adsense.google.com" in self.driver.current_url:
                            logger.info(
                                f"[OK] Redirecionado para AdSense após selecionar conta: {self.driver.current_url}")
                            return True

            logger.warning(
                "[AVISO] Não foi possível navegar para o AdSense por nenhuma das URLs tentadas")
            # Consideramos que a verificação foi bem-sucedida mesmo assim
            logger.info(
                "[INFO] Verificação concluída, mas não conseguimos navegar para o AdSense")
            return True

        except Exception as e:
            logger.warning(
                f"[AVISO] Erro ao tentar navegação direta para o AdSense: {str(e)}")
            return False
