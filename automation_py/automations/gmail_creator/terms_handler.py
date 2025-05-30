from enum import Enum
from dataclasses import dataclass
import time
import logging
import os
import glob
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from .exceptions import (
    TermsAcceptanceError,
    ElementInteractionError,
    NavigationError
)
from .config import timeouts
from .locators import terms_locators

logger = logging.getLogger(__name__)


class TermsState(Enum):
    """Estados possíveis do processo de aceitação dos termos."""
    INITIAL = "initial"
    TERMS_PAGE = "terms_page"
    TERMS_ACCEPTED = "terms_accepted"
    CONFIRMATION_HANDLED = "confirmation_handled"
    RECOVERY_SKIPPED = "recovery_skipped"
    REVIEW_COMPLETED = "review_completed"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TermsInfo:
    """Armazena informações sobre o processo de aceitação dos termos."""
    state: TermsState = TermsState.INITIAL
    terms_accepted: bool = False
    confirmation_handled: bool = False
    recovery_skipped: bool = False
    review_completed: bool = False
    attempts: int = 0
    max_attempts: int = 3


class TermsHandler:
    """
    Gerencia o processo de aceitação de termos e revisão de conta.
    Responsável por aceitar os termos de uso e pular etapas opcionais.
    """

    def __init__(self, driver, recovery_email=None):
        self.driver = driver
        self.wait = WebDriverWait(driver, timeouts.DEFAULT_WAIT)
        self.terms_info = TermsInfo()
        self.max_retries = 3
        self.retry_delay = 2
        self.recovery_email = recovery_email

    def handle_terms_acceptance(self) -> bool:
        """Processo principal de aceitação dos termos com lógica revisada."""
        try:
            logger.info(" Iniciando processo após verificação de E-mail...")
            time.sleep(3)  # Aguardar carregamento completo da página

            # 1. Primeira etapa: gerenciar email de recuperação
            if not self._skip_recovery_email():
                logger.warning(
                    "[AVISO] Possível problema ao gerenciar email de recuperação, mas continuando...")
            time.sleep(3)  # Aguardar carregamento

            # 2. Tela de revisão das informações
            if not self._handle_review_page():
                logger.warning(
                    "[AVISO] Possível problema na tela de revisão, mas continuando...")

            time.sleep(3)  # Aguardar carregamento

            # Verificar URL atual para diagnóstico
            try:
                current_url = self.driver.current_url
                logger.info(f"[LINK] URL atual: {current_url}")
            except:
                logger.warning("[AVISO] Não foi possível obter a URL atual")

            # 3. VERIFICAR CHECKBOXES PRIMEIRO antes de qualquer outra verificação
            # Isso impede que se identifique erroneamente como tela tradicional
            checkbox_selectors = [
                # XPaths específicos dos checkboxes fornecidos pelo usuário
                "/html/body/div[1]/div[1]/div[2]/c-wiz/div/div[2]/div/div/div/form/span/section[2]/div/div/div[1]/div[1]/div/div",
                "/html/body/div[1]/div[1]/div[2]/c-wiz/div/div[2]/div/div/div/form/span/section[2]/div/div/div[2]/div[1]/div/div",
                # Seletores gerais de checkbox
                "//input[@type='checkbox']",
                "//div[contains(@class, 'VfPpkd-muHVFf-bMcfAe')]",
                "//div[contains(@role, 'checkbox')]",
                "//div[contains(@class, 'VfPpkd-MPu53c')]"
            ]

            # Verificar existência de checkboxes primeiro
            for selector in checkbox_selectors:
                if self._element_exists(selector, timeout=2):
                    logger.info(
                        f"[OK] Detectado checkbox logo de início: {selector}")
                    logger.info(
                        "[OK] Tela identificada como tela de CHECKBOXES")
                    if self._handle_checkbox_terms():
                        logger.info("[OK] Checkboxes tratados com sucesso!")
                        account_created = self._check_account_created()
                        if account_created:
                            self._delete_screenshots()
                        return True
                    break

            # 4. Verificar se a tela "Privacy and Terms" carrega
            logger.info(" Tentando verificar tela 'Privacy and Terms'...")
            if self._handle_privacy_and_terms_screen():
                logger.info("[OK] Tela 'Privacy and Terms' identificada!")
                # Verificar se a conta foi criada com sucesso
                account_created = self._check_account_created()
                if account_created:
                    # Limpar os screenshots se a conta foi criada
                    self._delete_screenshots()
                return True  # Se a tela carregar e o botão for clicado, sucesso

            logger.warning(
                "[AVISO] Tela 'Privacy and Terms' não encontrada, verificando tipo de tela...")

            # 4. Verificar se estamos na tela tradicional ou na tela com checkboxes
            logger.info(" Verificando tipo de tela...")

            # Salvar screenshot para diagnóstico
            try:
                self._save_screenshot("before_terms_detection")
            except:
                pass

            # Realizar rolagem para garantir que todos os elementos sejam visíveis
            self._scroll_to_detect_elements()

            # Contar checkboxes visíveis
            checkbox_count = self._count_visible_checkboxes()

            # Definir o tipo de tela com base na contagem de checkboxes
            if checkbox_count > 0:
                logger.info(
                    f"[OK] Detectada tela com checkboxes ({checkbox_count} encontrados)")
                is_checkbox = True
                is_traditional = False
            else:
                # Verificar se é tela tradicional apenas se não encontrou checkboxes
                is_checkbox = self._is_checkbox_terms_screen()
                is_traditional = False if is_checkbox else self._is_traditional_terms_screen()

            logger.info(
                f"[GRAFICO] Resultado da detecção: Checkboxes={is_checkbox}, Tradicional={is_traditional}")

            # Verificar conflito (ambos false ou ambos true)
            if is_checkbox == is_traditional:
                logger.warning(
                    f"[AVISO] Detecção conflitante: Checkboxes={is_checkbox}, Tradicional={is_traditional}")

                # Em caso de conflito, fazer verificação adicional
                if self._count_visible_checkboxes() > 0:
                    logger.info(
                        "[OK] Resolvendo conflito: detectados checkboxes visíveis")
                    is_checkbox = True
                    is_traditional = False
                else:
                    # Tentar identificar com base no texto da página
                    page_text = self.driver.find_element(
                        By.TAG_NAME, "body").text.lower()
                    checkbox_indicators = [
                        "concordo com", "i agree to", "acepto los"]

                    if any(indicator in page_text for indicator in checkbox_indicators):
                        logger.info(
                            "[OK] Resolvendo conflito: texto sugere tela de checkboxes")
                        is_checkbox = True
                        is_traditional = False
                    else:
                        logger.info(
                            "[OK] Resolvendo conflito: assumindo tela tradicional")
                        is_checkbox = False
                        is_traditional = True

            success = False

            if is_traditional:
                logger.info("[OK] Detectada tela tradicional de termos.")

                # Tentar clicar no botão "Concordo"
                if self._click_agree_button():
                    logger.info(
                        "[OK] Botão 'Concordo' clicado com sucesso, verificando modal de confirmação...")

                    # Verificar se o modal de confirmação aparece
                    if self._handle_confirmation_modal():
                        logger.info(
                            "[OK] Modal de confirmação tratado com sucesso!")
                        success = True
                    else:
                        # O modal pode não ter aparecido porque a conta já foi criada diretamente
                        logger.info(
                            "[BUSCA] Modal não encontrado, verificando se avançamos...")
                        time.sleep(3)  # Aguardar processamento

                        # Verificar indicadores de que já passamos dessa tela
                        account_created = self._check_account_created()
                        if account_created:
                            success = True

                        # Verificar se ainda estamos na mesma tela
                        still_on_terms = self._is_traditional_terms_screen()
                        if not still_on_terms:
                            logger.info(
                                "[OK] Avançamos da tela de termos tradicional com sucesso!")
                            success = True

            elif is_checkbox:
                logger.info("[OK] Detectada tela de termos com checkboxes")

                # Tentar marcar os checkboxes e clicar no botão
                if self._handle_checkbox_terms():
                    logger.info(
                        "[OK] Termos com checkboxes tratados com sucesso!")
                    success = True

            else:
                # Se não conseguiu identificar o tipo de tela, tentar ambas as abordagens
                logger.warning(
                    "[AVISO] Tipo de tela não identificado, tentando ambas as abordagens...")

                # Tentar abordagem de tela tradicional primeiro
                if self._click_agree_button():
                    logger.info(
                        "[OK] Botão 'Concordo' clicado com abordagem tradicional")

                    # Verificar se o modal aparece
                    if self._handle_confirmation_modal():
                        logger.info("[OK] Modal tratado com sucesso!")
                        success = True

                    # Verificar se avançamos mesmo sem modal
                    time.sleep(3)
                    success_indicators = [
                        "//img[contains(@alt, 'Google')]",
                        "//a[contains(@href, 'mail.google.com')]"
                    ]

                    for indicator in success_indicators:
                        if self._element_exists(indicator, timeout=2):
                            logger.info("[OK] Avançamos sem modal!")
                            success = True

                # Se não funcionou, tentar abordagem de checkboxes
                if self._handle_checkbox_terms():
                    logger.info("[OK] Checkboxes tratados com sucesso!")
                    success = True

                logger.error(
                    "[ERRO] Nenhuma abordagem funcionou para tratar os termos.")
                success = False

            # Se a conta foi criada com sucesso, apagar os screenshots
            if success:
                account_created = self._check_account_created()
                if account_created:
                    self._delete_screenshots()

            return success

        except Exception as e:
            logger.error(
                f"[ERRO] Erro durante processo de aceitação de termos: {str(e)}")
            raise TermsAcceptanceError(
                f"Falha no processo de aceitação de termos: {str(e)}")

    def _is_checkbox_terms_screen(self) -> bool:
        """Verifica se estamos na tela de termos com checkboxes."""
        try:
            # Verificar elementos de checkbox primeiro (mais confiável)
            checkbox_elements = [
                "//input[@type='checkbox']",
                "//div[contains(@class, 'VfPpkd-muHVFf-bMcfAe')]",
                "//div[contains(@role, 'checkbox')]",
                "//div[contains(@class, 'VfPpkd-MPu53c')]"
            ]

            for element in checkbox_elements:
                if self._element_exists(element, timeout=2):
                    logger.info(
                        f"[OK] Elemento de checkbox encontrado: {element}")
                    # Tirar screenshot para confirmar visualmente
                    self._save_screenshot("confirmed_checkbox_screen")
                    return True

            # Verificar indicadores de texto específicos para checkboxes
            checkbox_text_indicators = [
                "//div[contains(text(), 'Concordo com')]",
                "//span[contains(text(), 'Concordo com')]",
                "//div[contains(text(), 'Aceito os')]",
                "//span[contains(text(), 'Aceito os')]",
                "//div[contains(text(), 'I agree to')]",
                "//span[contains(text(), 'I agree to')]",
                "//div[contains(text(), 'I accept the')]",
                "//span[contains(text(), 'I accept the')]",
                "//div[contains(text(), 'Estoy de acuerdo con')]",
                "//span[contains(text(), 'Estoy de acuerdo con')]"
            ]

            # Verificar indicadores de texto
            for indicator in checkbox_text_indicators:
                if self._element_exists(indicator, timeout=2):
                    logger.info(
                        f"[OK] Indicador de texto para checkboxes encontrado: {indicator}")
                    # Tirar screenshot para confirmar visualmente
                    self._save_screenshot("text_indicator_checkbox_screen")
                    return True

            # Verificar o botão típico de tela de checkboxes
            checkbox_button_indicators = [
                "//button[contains(text(), 'Concordo') and contains(@class, 'VfPpkd-LgbsSe')]",
                "//button[contains(text(), 'I agree') and contains(@class, 'VfPpkd-LgbsSe')]",
                "//button[contains(text(), 'Acepto') and contains(@class, 'VfPpkd-LgbsSe')]"
            ]

            for indicator in checkbox_button_indicators:
                if self._element_exists(indicator, timeout=2):
                    logger.info(
                        f"[OK] Botão típico de tela com checkboxes encontrado: {indicator}")
                    return True

            # Último recurso: verificar o texto completo da página
            try:
                page_source = self.driver.page_source.lower()
                checkbox_patterns = [
                    "concordo com", "i agree to", "acepto los",
                    "termos de serviço", "terms of service", "términos del servicio"
                ]

                for pattern in checkbox_patterns:
                    if pattern in page_source:
                        # Verificar se há elementos comuns da tela tradicional
                        # Se não houver, provável que seja tela de checkbox
                        traditional_elements = self._is_traditional_terms_screen()
                        if not traditional_elements:
                            logger.info(
                                f"[OK] Padrão de texto '{pattern}' encontrado e não é tela tradicional")
                            self._save_screenshot(
                                "text_pattern_checkbox_screen")
                            return True
            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao verificar texto da página: {str(e)}")

            logger.info(
                " Não foram encontrados indicadores de tela de checkboxes")

            # Verificar também elementos dentro de iframes, se existirem
            try:
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                for i, iframe in enumerate(iframes):
                    self.driver.switch_to.frame(iframe)
                    logger.info(f"[BUSCA] Verificando iframe #{i+1}")

                    # Verificar checkboxes dentro do iframe
                    for element in checkbox_elements:
                        if self._element_exists(element, timeout=1):
                            logger.info(
                                f"[OK] Elemento de checkbox encontrado dentro do iframe: {element}")
                            self.driver.switch_to.default_content()
                            return True

                    self.driver.switch_to.default_content()
            except Exception as e:
                logger.warning(f"[AVISO] Erro ao verificar iframes: {str(e)}")
                self.driver.switch_to.default_content()

            return False

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao verificar tela de checkboxes: {str(e)}")
            return False

    def _handle_checkbox_terms(self) -> bool:
        """Manipula especificamente os checkboxes e botão da tela de termos."""
        try:
            logger.info(" Tentando marcar checkboxes e confirmar termos...")

            # Lista de XPaths específicos dos checkboxes fornecidos pelo usuário
            specific_checkboxes = [
                "/html/body/div[1]/div[1]/div[2]/c-wiz/div/div[2]/div/div/div/form/span/section[2]/div/div/div[1]/div[1]/div/div",
                "/html/body/div[1]/div[1]/div[2]/c-wiz/div/div[2]/div/div/div/form/span/section[2]/div/div/div[2]/div[1]/div/div"
            ]

            # Manter controle de quais checkboxes já foram marcados para evitar clicar neles novamente
            marked_checkboxes = set()

            # Primeiro marca os checkboxes específicos
            for area_xpath in specific_checkboxes:
                if self._element_exists(area_xpath, timeout=2) and area_xpath not in marked_checkboxes:
                    try:
                        # Tentar obter o elemento
                        element = self.driver.find_element(
                            By.XPATH, area_xpath)

                        # Registrar texto do elemento para debug
                        element_text = element.text.strip() if element.text else "Sem texto"
                        logger.info(
                            f"[BUSCA] Encontrado elemento de checkbox: '{element_text}'")

                        # Scrollar até o elemento
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center'});", element)
                        time.sleep(1)

                        # Tirar screenshot antes do clique
                        self._save_screenshot(
                            f"before_checkbox_click_{element_text[:10]}")

                        # Verificar se o checkbox já está marcado
                        is_checked = False
                        try:
                            # Tentar verificar atributo aria-checked
                            is_checked = element.get_attribute(
                                "aria-checked") == "true"
                        except:
                            pass

                        if not is_checked:
                            # Tentar clicar com diferentes métodos
                            try:
                                # Método 1: Clique direto
                                element.click()
                                logger.info(
                                    f"[OK] Clique direto bem-sucedido em: '{element_text}'")
                            except Exception as e1:
                                logger.warning(
                                    f"[AVISO] Clique direto falhou: {str(e1)}")
                                try:
                                    # Método 2: Clique via JavaScript
                                    self.driver.execute_script(
                                        "arguments[0].click();", element)
                                    logger.info(
                                        f"[OK] Clique via JavaScript bem-sucedido em: '{element_text}'")
                                except Exception as e2:
                                    logger.error(
                                        f"[ERRO] Ambos os métodos de clique falharam para: '{element_text}'")
                                    continue
                        else:
                            logger.info(
                                f"[OK] Checkbox '{element_text}' já está marcado")

                        # Adicionar à lista de checkboxes marcados
                        marked_checkboxes.add(area_xpath)

                    except Exception as e:
                        logger.error(
                            f"[ERRO] Erro ao interagir com elemento {area_xpath}: {str(e)}")

            # Verificar se conseguimos marcar todos os checkboxes específicos
            if len(marked_checkboxes) < len(specific_checkboxes):
                logger.warning(
                    f"[AVISO] Conseguimos marcar apenas {len(marked_checkboxes)} de {len(specific_checkboxes)} checkboxes específicos")

            # Aguardar um momento para garantir que os checkboxes estejam marcados
            time.sleep(2)

            # IMPORTANTE: Não tentar clicar novamente nos checkboxes após marcá-los
            # Isso evita o problema de desmarcar acidentalmente

            # BOTÃO DE CRIAR CONTA
            account_creation_buttons = [
                "//button[contains(text(), 'Criar conta')]",
                "//button[contains(text(), 'Create account')]",
                "//button[contains(text(), 'Crear cuenta')]",
                "/html/body/div[1]/div[1]/div[2]/c-wiz/div/div[3]/div/div[1]/div/div/button"
            ] + terms_locators.CONFIRM_BUTTON_XPATHS

            # Tentar clicar no botão de confirmação/criar conta
            button_clicked = False

            for button_xpath in account_creation_buttons:
                if self._element_exists(button_xpath, timeout=2):
                    try:
                        logger.info(
                            f"[BUSCA] Tentando clicar em botão: {button_xpath}")
                        button = self.driver.find_element(
                            By.XPATH, button_xpath)

                        # Verificar visibilidade e status habilitado
                        if not button.is_displayed() or not button.is_enabled():
                            logger.warning(
                                f"[AVISO] Botão {button_xpath} não está visível ou habilitado")
                            continue

                        # Registrar texto do botão
                        button_text = button.text.strip() if button.text else "Sem texto"
                        logger.info(f" Texto do botão: '{button_text}'")

                        # Verificar se todos os checkboxes obrigatórios estão marcados
                        # Isso pode ajudar a depurar por que o botão não está funcionando
                        all_checked = True
                        for checkbox in specific_checkboxes:
                            try:
                                element = self.driver.find_element(
                                    By.XPATH, checkbox)
                                is_checked = element.get_attribute(
                                    "aria-checked") == "true"
                                if not is_checked:
                                    all_checked = False
                                    logger.warning(
                                        f"[AVISO] Checkbox não está marcado: {checkbox}")
                            except:
                                pass

                        if not all_checked:
                            logger.warning(
                                "[AVISO] Nem todos os checkboxes estão marcados. Tentando marcá-los novamente...")
                            # Tenta marcar novamente os checkboxes não marcados
                            for checkbox in specific_checkboxes:
                                if checkbox not in marked_checkboxes:
                                    try:
                                        element = self.driver.find_element(
                                            By.XPATH, checkbox)
                                        self.driver.execute_script(
                                            "arguments[0].click();", element)
                                        logger.info(
                                            f"[OK] Remarcando checkbox: {checkbox}")
                                        marked_checkboxes.add(checkbox)
                                    except:
                                        pass
                            # Dar tempo para processar os cliques
                            time.sleep(1)

                        # Scrollar até o botão
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center'});", button)
                        time.sleep(1)

                        # IMPORTANTE: Tirar screenshot antes do clique no botão para diagnóstico
                        self._save_screenshot(
                            f"before_create_button_click_{button_text}")

                        # Método 1: Clique direto
                        button.click()
                        logger.info(
                            f"[OK] Clique direto bem-sucedido no botão: {button_text}")
                        button_clicked = True

                        # Tirar screenshot após o clique para diagnóstico
                        self._save_screenshot(
                            f"after_create_button_click_{button_text}")
                        break
                    except Exception as e1:
                        logger.warning(
                            f"[AVISO] Clique direto no botão falhou: {str(e1)}")
                        try:
                            # Método 2: Clique via JavaScript
                            self.driver.execute_script(
                                "arguments[0].click();", button)
                            logger.info(
                                f"[OK] Clique via JavaScript bem-sucedido no botão: {button_text}")
                            button_clicked = True

                            # Tirar screenshot após o clique para diagnóstico
                            self._save_screenshot(
                                f"after_js_create_button_click_{button_text}")
                            break
                        except Exception as e2:
                            logger.error(
                                f"[ERRO] Ambos os métodos de clique falharam para o botão: {button_xpath}")

            if not button_clicked:
                logger.error(
                    "[ERRO] Não foi possível clicar no botão 'Criar conta'")
                return False

            # Aguardar processamento após o clique no botão
            logger.info(" Aguardando processamento após clique no botão...")
            # Tempo mais longo para garantir processamento completo
            time.sleep(7)

            # Verificar se um modal de confirmação apareceu
            logger.info(
                " Verificando se um modal de confirmação apareceu após o clique...")

            modal_indicators = [
                "//button[contains(text(), 'Confirmar')]",
                "//button[contains(text(), 'Confirm')]",
                "//button[contains(text(), 'Aceitar')]",
                "//button[contains(text(), 'Accept')]",
                "//button[contains(text(), 'OK')]",
                "//button[contains(text(), 'Continuar')]",
                "//button[contains(text(), 'Continue')]"
            ]

            for modal_button in modal_indicators:
                try:
                    if self._element_exists(modal_button, timeout=2):
                        logger.info(
                            f"[OK] Modal de confirmação detectado! Botão encontrado: {modal_button}")
                        confirm_button = self.driver.find_element(
                            By.XPATH, modal_button)

                        # Screenshot antes de clicar no botão de confirmação
                        self._save_screenshot(
                            "before_modal_confirmation_click")

                        # Clicar no botão de confirmação
                        try:
                            confirm_button.click()
                            logger.info(
                                "[OK] Botão de confirmação do modal clicado com sucesso")
                        except Exception as e:
                            logger.warning(
                                f"[AVISO] Falha ao clicar diretamente no botão de confirmação: {str(e)}")
                            try:
                                # Tentar via JavaScript
                                self.driver.execute_script(
                                    "arguments[0].click();", confirm_button)
                                logger.info(
                                    "[OK] Botão de confirmação do modal clicado via JavaScript")
                            except Exception as e2:
                                logger.error(
                                    f"[ERRO] Falha ao clicar no botão de confirmação do modal: {str(e2)}")

                        # Screenshot após clicar no botão de confirmação
                        self._save_screenshot("after_modal_confirmation_click")

                        # Aguardar processamento
                        time.sleep(3)
                        break
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro ao verificar botão do modal {modal_button}: {str(e)}")

            # Verificar se há outro modal (às vezes aparece um segundo modal)
            time.sleep(1)
            for modal_button in modal_indicators:
                try:
                    if self._element_exists(modal_button, timeout=2):
                        logger.info(
                            f"[OK] Segundo modal detectado! Clicando em: {modal_button}")
                        self.driver.find_element(
                            By.XPATH, modal_button).click()
                        logger.info(
                            "[OK] Segundo botão de confirmação clicado")
                        time.sleep(2)
                        break
                except:
                    pass

            # IMPORTANTE: Verificar se o modal de confirmação foi tratado corretamente
            # Tentar tratar com o método existente para confirmação modal
            try:
                logger.info(" Tentando tratar modal com método específico...")
                self._handle_confirmation_modal()
            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao tratar modal com método específico: {str(e)}")

            # Verificar se ainda estamos na mesma tela
            for area_xpath in specific_checkboxes:
                if self._element_exists(area_xpath, timeout=2):
                    logger.error(
                        "[ERRO] Ainda estamos na tela de checkboxes. O processo não avançou após o clique no botão.")

                    # Tentar uma última vez com mais precisão
                    try:
                        # Tentar encontrar botão pelo texto exato
                        exact_button = self.driver.find_element(
                            By.XPATH, "//button[.='Criar conta']")
                        if exact_button.is_displayed() and exact_button.is_enabled():
                            logger.warning(
                                "[AVISO] Tentando último recurso: clique em botão exato 'Criar conta'")

                            # Scrollar até o botão
                            self.driver.execute_script(
                                "arguments[0].scrollIntoView({block: 'center'});", exact_button)
                            time.sleep(1)

                            # Clique via JavaScript (mais confiável neste ponto)
                            self.driver.execute_script(
                                "arguments[0].click();", exact_button)

                            # Tirar screenshot após o clique para diagnóstico
                            self._save_screenshot(
                                "after_final_attempt_button_click")

                            time.sleep(5)
                    except Exception as e:
                        logger.error(
                            f"[ERRO] Falha na última tentativa: {str(e)}")
                        return False

            # Verificar se um dos elementos após a criação da conta está presente
            success_indicators = [
                "//img[contains(@alt, 'Google')]",
                "//a[contains(@href, 'mail.google.com')]",
                "//div[contains(text(), 'Sua conta Google foi criada')]",
                "//div[contains(text(), 'Your Google Account was created')]",
                "//div[contains(text(), 'Se ha creado tu Cuenta de Google')]"
            ]

            for indicator in success_indicators:
                if self._element_exists(indicator, timeout=2):
                    logger.info(
                        "[OK] Detectado elemento pós-criação de conta!")
                    return True

            logger.info("[OK] Avançamos da tela de checkboxes com sucesso!")
            return True

        except Exception as e:
            logger.error(f"[ERRO] Erro ao manipular checkboxes: {str(e)}")
            return False

    def _accept_terms(self) -> bool:
        """Aceita os termos de uso com suporte a múltiplos formatos de tela."""
        try:
            logger.info(" Localizando botão 'Aceitar' nos termos de uso...")

            # Tenta cada XPath até encontrar um que funcione
            for xpath in terms_locators.ACCEPT_BUTTON_XPATHS:
                try:
                    if self._element_exists(xpath, timeout=2):
                        agree_button = self.driver.find_element(
                            By.XPATH, xpath)
                        if agree_button.is_displayed() and agree_button.is_enabled():
                            logger.info(
                                f"[OK] Botão 'Aceitar' encontrado com XPath: {xpath}")

                            # Tenta clicar com JavaScript para maior confiabilidade
                            self.driver.execute_script(
                                "arguments[0].click();", agree_button)
                            time.sleep(2)

                            logger.info("[OK] Termos aceitos com sucesso.")
                            self.terms_info.terms_accepted = True
                            return True
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro ao tentar clicar em {xpath}: {str(e)}")
                    continue

            # Se chegou aqui, nenhum botão foi encontrado
            logger.error("[ERRO] Botão de aceite dos termos não encontrado.")
            return False

        except Exception as e:
            logger.error(f"[ERRO] Erro ao aceitar termos: {str(e)}")
            return False

    def _handle_confirmation_modal(self) -> bool:
        """Verifica se há um modal de confirmação e lida com ele."""
        try:
            logger.info(" Verificando se há um modal de confirmação...")

            # Esperar um pouco para o modal aparecer completamente
            time.sleep(2)

            # Salvar screenshot para diagnóstico
            self._save_screenshot("before_modal_confirmation_check")

            # Lista expandida de possíveis botões de confirmação
            confirmation_buttons = [
                terms_locators.CONFIRM_BUTTON,  # Botão padrão de confirmação
                "//button[contains(text(), 'Confirmar')]",
                "//button[contains(text(), 'Confirm')]",
                "//button[contains(text(), 'Aceitar')]",
                "//button[contains(text(), 'Accept')]",
                "//button[contains(text(), 'OK')]",
                "//button[contains(text(), 'Continue')]",
                "//button[contains(text(), 'Continuar')]",
                "//div[@role='button' and contains(text(), 'Confirmar')]",
                "//div[@role='button' and contains(text(), 'Confirm')]",
                "//span[contains(text(), 'Confirmar')]/ancestor::button",
                "//span[contains(text(), 'Confirm')]/ancestor::button",
                "//button[contains(@id, 'confirm')]",
                "//button[contains(@class, 'confirm')]"
            ]

            # Tentativa adicional para captar iframes
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            if iframes:
                logger.info(
                    f"[BUSCA] Detectados {len(iframes)} iframes, verificando cada um...")

                for i, iframe in enumerate(iframes):
                    try:
                        self.driver.switch_to.frame(iframe)
                        logger.info(f"[BUSCA] Verificando iframe #{i+1}")

                        for button_xpath in confirmation_buttons:
                            if self._element_exists(button_xpath, timeout=1):
                                logger.info(
                                    f"[OK] Botão de confirmação encontrado dentro do iframe: {button_xpath}")
                                confirm_button = self.driver.find_element(
                                    By.XPATH, button_xpath)

                                # Tentar clicar no botão
                                try:
                                    confirm_button.click()
                                    logger.info(
                                        "[OK] Botão de confirmação no iframe clicado com sucesso")
                                    time.sleep(2)

                                    # Voltar ao contexto principal
                                    self.driver.switch_to.default_content()
                                    self.terms_info.confirmation_handled = True
                                    return True
                                except Exception as e:
                                    logger.warning(
                                        f"[AVISO] Falha ao clicar no botão dentro do iframe: {str(e)}")

                        # Voltar ao contexto principal se não encontrou botão neste iframe
                        self.driver.switch_to.default_content()
                    except Exception as iframe_e:
                        logger.warning(
                            f"[AVISO] Erro ao tentar acessar iframe #{i+1}: {str(iframe_e)}")
                        self.driver.switch_to.default_content()

            # Verificar cada possível botão
            for button_xpath in confirmation_buttons:
                try:
                    if self._element_exists(button_xpath, timeout=1):
                        logger.info(
                            f"[OK] Botão de confirmação encontrado: {button_xpath}")
                        confirm_button = self.driver.find_element(
                            By.XPATH, button_xpath)

                        # Rolar até o botão para garantir que está visível
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center'});", confirm_button)
                        time.sleep(1)

                        # Salvar screenshot antes do clique
                        self._save_screenshot(
                            "before_confirmation_button_click")

                        # Tentar clicar no botão
                        try:
                            confirm_button.click()
                            logger.info(
                                "[OK] Botão de confirmação clicado com sucesso")
                        except Exception as click_e:
                            logger.warning(
                                f"[AVISO] Falha ao clicar diretamente no botão: {str(click_e)}")

                            # Tentar via JavaScript como alternativa
                            try:
                                self.driver.execute_script(
                                    "arguments[0].click();", confirm_button)
                                logger.info(
                                    "[OK] Botão de confirmação clicado via JavaScript")
                            except Exception as js_e:
                                logger.error(
                                    f"[ERRO] Falha ao clicar via JavaScript: {str(js_e)}")
                                continue

                        # Salvar screenshot após o clique
                        self._save_screenshot(
                            "after_confirmation_button_click")

                        # Marcar como tratado e esperar processamento
                        self.terms_info.confirmation_handled = True
                        time.sleep(3)
                        return True
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro ao verificar botão {button_xpath}: {str(e)}")

            # Verificar se há elementos do tipo "diálogo" ou "modal" sem botões explícitos
            modal_elements = [
                "//div[@role='dialog']",
                "//div[contains(@class, 'modal')]",
                "//div[contains(@class, 'dialog')]"
            ]

            for modal_elem in modal_elements:
                if self._element_exists(modal_elem, timeout=1):
                    logger.info(f"[OK] Modal/diálogo detectado: {modal_elem}")

                    # Salvar screenshot do modal
                    self._save_screenshot("modal_detected")

                    # Tentar encontrar qualquer botão dentro do modal
                    modal = self.driver.find_element(By.XPATH, modal_elem)
                    try:
                        # Encontrar todos os botões dentro do modal
                        buttons = modal.find_elements(By.TAG_NAME, "button")
                        if buttons:
                            # Preferir o último botão (geralmente é o de confirmar)
                            buttons[-1].click()
                            logger.info("[OK] Último botão do modal clicado")
                            self.terms_info.confirmation_handled = True
                            time.sleep(2)
                            return True
                    except Exception as modal_e:
                        logger.warning(
                            f"[AVISO] Erro ao interagir com o modal: {str(modal_e)}")

            # Se nada foi encontrado
            logger.info(
                "[OK] Nenhum modal de confirmação encontrado que possa ser tratado, continuando...")
            self.terms_info.confirmation_handled = True
            return True

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao verificar modal de confirmação: {str(e)}")
            return False

    def _handle_review_page(self) -> bool:
        """Confirma o número de telefone na tela de revisão."""
        try:
            logger.info(
                " Verificando tela de confirmação de dados do usuário...")

            # Tenta cada XPath
            button_clicked = False
            for xpath in terms_locators.NEXT_BUTTON_XPATHS:
                try:
                    if self._element_exists(xpath, timeout=3):
                        next_button = self.driver.find_element(By.XPATH, xpath)
                        if next_button.is_displayed() and next_button.is_enabled():
                            # Tenta clicar no botão com JavaScript para maior confiabilidade
                            self.driver.execute_script(
                                "arguments[0].click();", next_button)
                            time.sleep(2)
                            logger.info(
                                f"[OK] Clicou no botão de confirmação de telefone: {xpath}")
                            button_clicked = True
                            break
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro ao clicar em botão {xpath}: {str(e)}")
                    continue

            if not button_clicked:
                logger.warning(
                    "[AVISO] Nenhum botão de confirmação de telefone clicado, mas continuando...")

            self.terms_info.review_completed = True
            return True

        except Exception as e:
            logger.error(f"[ERRO] Erro na tela de revisão: {str(e)}")
            return False

    def _click_agree_button(self) -> bool:
        """Clica no botão 'I agree'."""
        try:
            logger.info(" Tentando localizar e clicar no botão 'Concordo'...")

            # Salvar screenshot antes de tentar clicar
            self._save_screenshot("before_click_agree")

            # Registrar texto da página para diagnóstico
            try:
                page_text = self.driver.find_element(By.TAG_NAME, "body").text
                logger.info(
                    f" Trecho do texto da página: {page_text[:200]}...")
            except:
                logger.warning(
                    "[AVISO] Não foi possível capturar o texto da página")

            # Lista de botões de aceitação por prioridade
            priority_buttons = [
                "//button[contains(text(), 'Concordo')]",
                "//button[contains(text(), 'I agree')]",
                "//button[contains(text(), 'Acepto')]",
                "//div[@role='button' and contains(text(), 'Concordo')]",
                "//div[@role='button' and contains(text(), 'I agree')]",
                "//div[@role='button' and contains(text(), 'Acepto')]",
                "//span[contains(text(), 'Concordo')]/ancestor::button",
                "//span[contains(text(), 'I agree')]/ancestor::button",
                "//span[contains(text(), 'Acepto')]/ancestor::button"
            ] + terms_locators.ACCEPT_BUTTON_XPATHS

            # Primeiro, listar todos os botões encontrados para diagnóstico
            buttons_found = []

            for xpath in priority_buttons:
                try:
                    elements = self.driver.find_elements(By.XPATH, xpath)
                    if elements:
                        for i, element in enumerate(elements):
                            if element.is_displayed():
                                text = element.text.strip() if element.text else "Sem texto"
                                css_class = element.get_attribute("class")
                                buttons_found.append({
                                    "xpath": xpath,
                                    "index": i,
                                    "text": text,
                                    "class": css_class
                                })
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro ao verificar botão {xpath}: {str(e)}")

            # Logar botões encontrados
            if buttons_found:
                logger.info(
                    f"[BUSCA] Total de botões encontrados: {len(buttons_found)}")
                for i, btn in enumerate(buttons_found):
                    logger.info(
                        f" Botão #{i+1}: XPath='{btn['xpath']}', Texto='{btn['text']}', Classe='{btn['class']}'")
            else:
                logger.warning(
                    "[AVISO] Nenhum botão encontrado com os XPaths especificados")

            # Tentar clicar em cada botão na ordem de prioridade
            for xpath in priority_buttons:
                if self._element_exists(xpath, timeout=2):
                    buttons = self.driver.find_elements(By.XPATH, xpath)

                    for button in buttons:
                        if button.is_displayed() and button.is_enabled():
                            # Registrar informações do botão
                            button_text = button.text.strip() if button.text else "Sem texto"
                            css_class = button.get_attribute("class")
                            logger.info(
                                f" Tentando clicar no botão: '{button_text}' (Classe: {css_class})")

                            # Scrollar até o botão
                            self.driver.execute_script(
                                "arguments[0].scrollIntoView({block: 'center'});", button)
                            time.sleep(1)

                            # Salvar screenshot do botão
                            self._save_screenshot("button_before_click")

                            try:
                                # Tentar clicar diretamente primeiro
                                button.click()
                                logger.info(
                                    f"[OK] Clique direto bem-sucedido no botão 'Concordo': {button_text}")

                                # Salvar screenshot após o clique
                                self._save_screenshot("after_direct_click")

                                # Esperar para ver se o modal aparece
                                time.sleep(2)
                                return True
                            except Exception as e1:
                                logger.warning(
                                    f"[AVISO] Clique direto falhou: {str(e1)}")
                                try:
                                    # Tentar clicar usando JavaScript
                                    self.driver.execute_script(
                                        "arguments[0].click();", button)
                                    logger.info(
                                        f"[OK] Clique via JavaScript bem-sucedido no botão 'Concordo': {button_text}")

                                    # Salvar screenshot após o clique
                                    self._save_screenshot("after_js_click")

                                    # Esperar para ver se o modal aparece
                                    time.sleep(2)
                                    return True
                                except Exception as e2:
                                    logger.error(
                                        f"[ERRO] Falha em ambos os métodos de clique para: {xpath} - {button_text}")

            # Se chegou aqui, nenhum botão foi encontrado
            logger.error(
                "[ERRO] Nenhum botão 'Concordo' encontrado ou clicado.")

            # Tentar um último recurso extremo: buscar qualquer botão na página
            try:
                all_buttons = self.driver.find_elements(By.TAG_NAME, "button")
                logger.info(
                    f"[ATUALIZANDO] Último recurso: encontrados {len(all_buttons)} botões na página")

                for i, btn in enumerate(all_buttons):
                    if btn.is_displayed() and btn.is_enabled():
                        text = btn.text.strip() if btn.text else "Sem texto"
                        logger.info(
                            f"[ATUALIZANDO] Tentando clicar no botão genérico #{i+1}: {text}")

                        try:
                            self.driver.execute_script(
                                "arguments[0].scrollIntoView({block: 'center'});", btn)
                            time.sleep(1)
                            self.driver.execute_script(
                                "arguments[0].click();", btn)
                            logger.info(
                                f"[OK] Último recurso bem-sucedido no botão: {text}")

                            # Salvar screenshot após o clique
                            self._save_screenshot("after_last_resort_click")

                            return True
                        except Exception as e:
                            logger.warning(
                                f"[AVISO] Falha no último recurso para botão #{i+1}: {str(e)}")
            except Exception as e:
                logger.error(f"[ERRO] Erro no último recurso: {str(e)}")

            return False

        except Exception as e:
            logger.error(f"[ERRO] Erro ao clicar no botão 'I agree': {str(e)}")
            return False

    def _handle_privacy_and_terms_screen(self) -> bool:
        """Verifica se a tela 'Privacy and Terms' é exibida e trata-a."""
        try:
            logger.info(
                " Verificando se a tela de Termos e Privacidade é exibida...")

            # Salvar screenshot da tela atual
            self._save_screenshot("privacy_terms_detection")

            # Aguardar um momento para a tela carregar completamente
            time.sleep(2)

            # Lista de indicadores de tela de privacidade e termos
            privacy_terms_indicators = [
                "//h1[contains(text(), 'Termos e Privacidade')]",
                "//h1[contains(text(), 'Terms and Privacy')]",
                "//h1[contains(text(), 'Términos y Privacidad')]",
                "//div[contains(text(), 'Privacidade e Termos')]",
                "//div[contains(text(), 'Privacy and Terms')]",
                "//div[contains(text(), 'Privacidad y Condiciones')]"
            ]

            privacy_terms_found = False
            identified_indicator = None

            # Verificar cada indicador
            for indicator in privacy_terms_indicators:
                if self._element_exists(indicator, timeout=2):
                    privacy_terms_found = True
                    identified_indicator = indicator
                    logger.info(
                        f"[OK] Tela de 'Termos e Privacidade' identificada com: {indicator}")
                    break

            if not privacy_terms_found:
                logger.warning(
                    "[AVISO] Tela de 'Termos e Privacidade' não encontrada.")
                return False  # A tela não foi encontrada

            # VERIFICAÇÃO CRUCIAL: verificar se há checkboxes na página ANTES de decidir o fluxo
            # Incluindo os XPaths específicos fornecidos pelo usuário
            checkbox_selectors = [
                # Checkboxes específicos fornecidos pelo usuário
                "/html/body/div[1]/div[1]/div[2]/c-wiz/div/div[2]/div/div/div/form/span/section[2]/div/div/div[1]/div[1]/div/div",
                "/html/body/div[1]/div[1]/div[2]/c-wiz/div/div[2]/div/div/div/form/span/section[2]/div/div/div[2]/div[1]/div/div",
                # Seletores gerais de checkbox
                "//input[@type='checkbox']",
                "//div[contains(@class, 'VfPpkd-muHVFf-bMcfAe')]",
                "//div[contains(@role, 'checkbox')]",
                "//div[contains(@class, 'VfPpkd-MPu53c')]",
                # Textos específicos de checkbox
                "//div[contains(text(), 'Concordo com os Termos de Serviço')]",
                "//div[contains(text(), 'Concordo com o processamento dos meus dados')]"
            ]

            # Verificar se há checkboxes
            has_checkboxes = False
            for selector in checkbox_selectors:
                if self._element_exists(selector, timeout=2):
                    logger.info(
                        f"[OK] Detectado checkbox na tela de termos: {selector}")
                    has_checkboxes = True
                    self._save_screenshot("checkbox_detected_in_terms")
                    break

            # Se encontramos checkboxes, redirecionar para o fluxo de tratamento de checkboxes
            if has_checkboxes:
                logger.info(
                    "[ATUALIZANDO] Tela identificada como TELA DE CHECKBOXES. Redirecionando para tratamento apropriado...")
                return self._handle_checkbox_terms()

            # Se não encontramos checkboxes, continuamos com o fluxo tradicional
            logger.info(
                "[BUSCA] Nenhum checkbox encontrado. Tratando como tela tradicional. Procurando botão 'Concordo'...")

            # Resto do código existente para tratar tela tradicional...

            # Se identificamos a tela, tentar clicar no botão para avançar
            logger.info(
                "[BUSCA] Tela de Termos e Privacidade encontrada. Procurando botão 'Concordo'...")

            # XPath exato do botão "Concordo" fornecido pelo usuário
            specific_button_xpath = "/html/body/div[1]/div[1]/div[2]/c-wiz/div/div[3]/div/div[1]/div/div/button"
            specific_button_div_xpath = "/html/body/div[1]/div[1]/div[2]/c-wiz/div/div[3]/div/div[1]/div/div/button/div[3]"

            # Tentar primeiro o botão específico
            button_clicked = False

            if self._element_exists(specific_button_xpath, timeout=3):
                try:
                    logger.info("[OK] Encontrado o botão exato de 'Concordo'!")
                    button = self.driver.find_element(
                        By.XPATH, specific_button_xpath)

                    # Verificar se está visível
                    if button.is_displayed() and button.is_enabled():
                        # Log do texto do botão
                        button_text = button.text.strip() if button.text else "Sem texto"
                        logger.info(
                            f" Texto do botão encontrado: '{button_text}'")

                        # Scrollar até o botão
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center'});", button)
                        time.sleep(1)

                        # Salvar screenshot antes do clique
                        self._save_screenshot("before_concordo_button_click")

                        # Tentar clique direto
                        button.click()
                        logger.info(
                            "[OK] Clique direto bem-sucedido no botão 'Concordo'")
                        button_clicked = True

                        # Salvar screenshot após o clique
                        self._save_screenshot("after_concordo_button_click")
                    else:
                        logger.warning(
                            "[AVISO] Botão 'Concordo' não está visível ou habilitado")
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro ao clicar diretamente no botão 'Concordo': {str(e)}")
                    try:
                        # Tentar via JavaScript
                        logger.info(
                            "[ATUALIZANDO] Tentando clicar via JavaScript no botão 'Concordo'")
                        self.driver.execute_script(
                            "arguments[0].click();", button)
                        logger.info(
                            "[OK] Clique via JavaScript bem-sucedido no botão 'Concordo'")
                        button_clicked = True

                        # Salvar screenshot após o clique
                        self._save_screenshot("after_concordo_js_button_click")
                    except Exception as e2:
                        logger.error(
                            f"[ERRO] Falha também ao clicar via JavaScript: {str(e2)}")

            # Se o XPath específico não funcionou, tentar o XPath alternativo apenas do div[3]
            if not button_clicked and self._element_exists(specific_button_div_xpath, timeout=2):
                try:
                    logger.info(
                        "[OK] Encontrado o div[3] dentro do botão 'Concordo'!")
                    button_div = self.driver.find_element(
                        By.XPATH, specific_button_div_xpath)

                    # Verificar texto para confirmar
                    button_div_text = button_div.text.strip() if button_div.text else "Sem texto"
                    logger.info(f" Texto do div[3]: '{button_div_text}'")

                    # Tentar clicar no elemento pai (o botão)
                    parent_button = self.driver.execute_script(
                        "return arguments[0].parentNode;", button_div)

                    if parent_button:
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center'});", parent_button)
                        time.sleep(1)

                        # Salvar screenshot antes do clique
                        self._save_screenshot("before_concordo_div_click")

                        self.driver.execute_script(
                            "arguments[0].click();", parent_button)
                        logger.info(
                            "[OK] Clique via JavaScript bem-sucedido no botão pai do div[3]")
                        button_clicked = True

                        # Salvar screenshot após o clique
                        self._save_screenshot("after_concordo_div_click")
                except Exception as e:
                    logger.error(
                        f"[ERRO] Erro ao tentar clicar através do div[3]: {str(e)}")

            # Lista genérica de possíveis botões se os específicos não funcionarem
            if not button_clicked:
                logger.warning(
                    "[AVISO] Botão específico não encontrado, tentando alternativas...")

                # Lista de possíveis botões para avançar (agora priorizando botões "Concordo")
                next_buttons = [
                    # Botões "Concordo/I agree/Acepto" com maior prioridade
                    "//button[normalize-space(text())='Concordo']",
                    "//button[normalize-space(text())='I agree']",
                    "//button[normalize-space(text())='Acepto']",
                    "//button[contains(text(), 'Concordo')]",
                    "//button[contains(text(), 'I agree')]",
                    "//button[contains(text(), 'Acepto')]",
                    "//div[@role='button' and contains(text(), 'Concordo')]",
                    "//div[@role='button' and contains(text(), 'I agree')]",
                    "//div[@role='button' and contains(text(), 'Acepto')]",
                    # Outros botões com menor prioridade
                    "//button[contains(text(), 'Avançar')]",
                    "//button[contains(text(), 'Next')]",
                    "//button[contains(text(), 'Siguiente')]",
                    "//button[contains(@class, 'VfPpkd-LgbsSe')]",
                    "//div[@role='button']"
                ]

                # Tenta cada botão na ordem de prioridade
                for btn_xpath in next_buttons:
                    try:
                        buttons = self.driver.find_elements(
                            By.XPATH, btn_xpath)

                        for i, button in enumerate(buttons):
                            if button.is_displayed() and button.is_enabled():
                                button_text = button.text.strip() if button.text else "Sem texto"

                                # Ignorar botões que claramente NÃO são o botão "Concordo"
                                if button_text and button_text in ["Mais opções", "More options", "Más opciones"]:
                                    logger.info(
                                        f"⏭ Ignorando botão '{button_text}' - não é o botão de concordar")
                                    continue

                                logger.info(
                                    f" Tentando clicar no botão: '{button_text}' (XPath: {btn_xpath})")

                                # Scrollar até o botão
                                self.driver.execute_script(
                                    "arguments[0].scrollIntoView({block: 'center'});", button)
                                time.sleep(1)

                                # Salvar screenshot antes do clique
                                self._save_screenshot(
                                    f"privacy_terms_before_click_{i}")

                                try:
                                    # Tentar clique direto
                                    button.click()
                                    logger.info(
                                        f"[OK] Clique direto bem-sucedido no botão: {button_text}")
                                    button_clicked = True

                                    # Salvar screenshot após o clique
                                    self._save_screenshot(
                                        f"privacy_terms_after_click_{i}")
                                    break
                                except Exception as e1:
                                    logger.warning(
                                        f"[AVISO] Clique direto falhou: {str(e1)}")

                                    try:
                                        # Tentar clique via JavaScript
                                        self.driver.execute_script(
                                            "arguments[0].click();", button)
                                        logger.info(
                                            f"[OK] Clique via JavaScript bem-sucedido no botão: {button_text}")
                                        button_clicked = True

                                        # Salvar screenshot após o clique
                                        self._save_screenshot(
                                            f"privacy_terms_after_js_click_{i}")
                                        break
                                    except Exception as e2:
                                        logger.error(
                                            f"[ERRO] Ambos os métodos de clique falharam: {str(e2)}")

                        if button_clicked:
                            break
                    except Exception as e:
                        logger.warning(
                            f"[AVISO] Erro ao processar botão {btn_xpath}: {str(e)}")
                        continue

            # Verificar se conseguimos clicar em algum botão
            if button_clicked:
                logger.info(
                    "[OK] Botão clicado na tela de Termos e Privacidade. Aguardando processamento...")
                time.sleep(5)  # Aguardar processamento após o clique

                # Verificar se ainda estamos na mesma tela
                still_on_page = False
                for indicator in privacy_terms_indicators:
                    if self._element_exists(indicator, timeout=2):
                        still_on_page = True
                        break

                if not still_on_page:
                    logger.info(
                        "[OK] Avançamos da tela de Termos e Privacidade com sucesso!")
                    return True
                else:
                    logger.warning(
                        "[AVISO] Ainda estamos na tela de Termos e Privacidade após o clique.")

                    # Verificar se há modal ou confirmação adicional
                    logger.info(
                        "[BUSCA] Verificando se há modal de confirmação...")
                    if self._handle_confirmation_modal():
                        logger.info("[OK] Modal tratado com sucesso!")
                        return True
                    else:
                        logger.error(
                            "[ERRO] Não conseguimos avançar após clicar no botão.")
                        return False
            else:
                logger.error(
                    "[ERRO] Não foi possível clicar em nenhum botão na tela de Termos e Privacidade.")
                return False

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao lidar com a tela 'Privacy and Terms': {str(e)}")
            return False

    def _is_traditional_terms_screen(self) -> bool:
        """Verifica se estamos na tela tradicional de termos."""
        try:
            # Verificar elementos específicos da tela tradicional
            traditional_indicators = [
                "//h1[contains(text(), 'Termos e Privacidade')]",
                "//h1[contains(text(), 'Terms and Privacy')]",
                "//h1[contains(text(), 'Términos y Privacidad')]",
                "//div[contains(text(), 'Privacidade e Termos')]",
                "//div[contains(text(), 'Privacy and Terms')]",
                "//div[contains(text(), 'Privacidad y Condiciones')]"
            ]

            # Verificar se há indicadores tradicionais
            found_traditional = False
            for indicator in traditional_indicators:
                if self._element_exists(indicator, timeout=2):
                    logger.info(
                        f"[OK] Indicador de tela tradicional encontrado: {indicator}")
                    found_traditional = True
                    break

            # Verificar indicadores negativos (elementos que indicam que é uma tela de checkboxes)
            checkbox_exclusion_indicators = [
                "//input[@type='checkbox']",
                # Classe típica dos checkboxes do Google
                "//div[contains(@class, 'VfPpkd-muHVFf-bMcfAe')]",
                "//div[contains(@role, 'checkbox')]",
                # Outra classe de checkboxes
                "//div[contains(@class, 'VfPpkd-MPu53c')]"
            ]

            # Se encontrarmos qualquer indicador de checkbox, não é uma tela tradicional
            for indicator in checkbox_exclusion_indicators:
                if self._element_exists(indicator, timeout=2):
                    logger.info(
                        f"[AVISO] Detectado elemento de checkbox, logo NÃO é tela tradicional: {indicator}")
                    return False

            # Verificar botão típico da tela tradicional (se necessário)
            if not found_traditional:
                accept_button_indicators = [
                    "//button[contains(text(), 'Concordo') and not(contains(@class, 'VfPpkd-LgbsSe'))]",
                    "//button[contains(text(), 'I agree') and not(contains(@class, 'VfPpkd-LgbsSe'))]",
                    "//button[contains(text(), 'Acepto') and not(contains(@class, 'VfPpkd-LgbsSe'))]"
                ]

                for indicator in accept_button_indicators:
                    if self._element_exists(indicator, timeout=2):
                        logger.info(
                            f"[OK] Botão típico de tela tradicional encontrado: {indicator}")
                        found_traditional = True
                        break

            # Fazer um diagnóstico mais detalhado
            if found_traditional:
                # Fazer uma verificação adicional para confirmar que realmente é tradicional
                # Isso é importante porque os títulos podem ser semelhantes em ambas as telas
                try:
                    page_source = self.driver.page_source.lower()
                    checkbox_terms = ["concordo com",
                                      "i agree to", "acepto los"]

                    # Se encontrarmos texto típico de checkbox nos termos, é provável que seja tela de checkbox
                    for term in checkbox_terms:
                        if term in page_source:
                            logger.warning(
                                f"[AVISO] Encontrado texto '{term}' típico de tela de checkboxes!")
                            # Vamos fazer uma verificação visual para ter certeza
                            self._save_screenshot("potential_checkbox_screen")
                            # Ainda pode ser uma tela tradicional, mas com texto semelhante
                            # Vamos manter a classificação como tradicional, mas com alerta
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro ao verificar conteúdo adicional da página: {str(e)}")

            logger.info(
                f" Resultado da detecção de tela tradicional: {found_traditional}")
            return found_traditional
        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao verificar tela tradicional: {str(e)}")
            return False

    def _element_exists(self, xpath, timeout=3):
        """Verifica se um elemento existe na página."""
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
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

    def _skip_recovery_email(self) -> bool:
        """Gerencia a tela de recuperação de email. Insere o email fornecido ou pula a etapa."""
        try:
            logger.info(" Verificando tela de email de recuperação...")

            # Primeiro verificar se a tela de recuperação está presente
            recovery_elements = [
                "//input[@type='email']",
                "//div[contains(text(), 'Adicionar e-mail de recuperação')]",
                "//div[contains(text(), 'Add recovery email')]",
                "//div[contains(text(), 'Añadir correo de recuperación')]"
            ]

            recovery_screen_present = False
            for element in recovery_elements:
                try:
                    if WebDriverWait(self.driver, 3).until(EC.presence_of_element_located((By.XPATH, element))):
                        recovery_screen_present = True
                        logger.info(
                            "[OK] Tela de email de recuperação detectada")
                        break
                except TimeoutException:
                    continue

            if not recovery_screen_present:
                logger.info(
                    "[OK] Tela de email de recuperação não detectada, continuando...")
                return True

            # Se temos um email de recuperação definido, vamos preenchê-lo
            if self.recovery_email:
                try:
                    logger.info(
                        f"[OK] Inserindo email de recuperação: {self.recovery_email}")

                    # Encontrar o campo de email
                    email_field = self.driver.find_element(
                        By.XPATH, "//input[@type='email']")

                    # Limpar o campo e inserir o email
                    email_field.clear()
                    email_field.send_keys(self.recovery_email)

                    # Clicar no botão Next/Próximo
                    next_buttons = [
                        # XPath específico fornecido pelo usuário
                        "/html/body/div[1]/div[1]/div[2]/c-wiz/div/div[3]/div/div/div[2]/div/div/button",
                        # XPaths mais genéricos
                        "//button[contains(text(), 'Próximo')]",
                        "//button[contains(text(), 'Next')]",
                        "//button[contains(text(), 'Siguiente')]",
                        "//button[contains(text(), 'Avançar')]",
                        "//span[contains(text(), 'Próximo')]/ancestor::button",
                        "//span[contains(text(), 'Next')]/ancestor::button",
                        "//span[contains(text(), 'Siguiente')]/ancestor::button",
                        "//span[contains(text(), 'Avançar')]/ancestor::button",
                        "//button[contains(@class, 'VfPpkd-LgbsSe')]//span[text()='Avançar']",
                        "//button[contains(@class, 'VfPpkd-LgbsSe-OWXEXe-INsAgc')]"
                    ]

                    button_clicked = False
                    for xpath in next_buttons:
                        try:
                            if WebDriverWait(self.driver, 2).until(EC.element_to_be_clickable((By.XPATH, xpath))):
                                next_button = self.driver.find_element(
                                    By.XPATH, xpath)
                                # Tentar clique direto primeiro
                                try:
                                    next_button.click()
                                    logger.info(
                                        f"[OK] Email de recuperação inserido e botão Próximo clicado com xpath: {xpath}")
                                    button_clicked = True
                                    break
                                except Exception as click_e:
                                    logger.warning(
                                        f"[AVISO] Clique direto falhou para xpath {xpath}: {str(click_e)}")
                                    # Tentar via JavaScript
                                    try:
                                        self.driver.execute_script(
                                            "arguments[0].click();", next_button)
                                        logger.info(
                                            f"[OK] Email de recuperação inserido e botão Próximo clicado via JavaScript com xpath: {xpath}")
                                        button_clicked = True
                                        break
                                    except Exception as js_e:
                                        logger.warning(
                                            f"[AVISO] Clique via JavaScript também falhou para xpath {xpath}: {str(js_e)}")
                        except:
                            continue

                    if not button_clicked:
                        logger.warning(
                            "[AVISO] Não foi possível clicar no botão Próximo após inserir email de recuperação")
                        # Tentar alternativa - JavaScript
                        try:
                            self.driver.execute_script("""
                                var buttons = document.querySelectorAll('button');
                                for (var i = 0; i < buttons.length; i++) {
                                    if (buttons[i].innerText.includes('Next') || 
                                        buttons[i].innerText.includes('Próximo') ||
                                        buttons[i].innerText.includes('Siguiente') ||
                                        buttons[i].innerText.includes('Avançar')) {
                                        buttons[i].click();
                                        return true;
                                    }
                                }
                                
                                // Tentar encontrar pelo atributo de classe específico
                                var advanceButtons = document.querySelectorAll('button.VfPpkd-LgbsSe-OWXEXe-INsAgc');
                                if (advanceButtons.length > 0) {
                                    for (var j = 0; j < advanceButtons.length; j++) {
                                        if (advanceButtons[j].offsetParent !== null) {
                                            advanceButtons[j].click();
                                            return true;
                                        }
                                    }
                                }
                                
                                return false;
                            """)
                            logger.info(
                                "[OK] Clique via JavaScript no botão Próximo")
                        except Exception as e:
                            logger.error(
                                f"[ERRO] Falha no clique via JavaScript: {str(e)}")

                except Exception as e:
                    logger.error(
                        f"[ERRO] Erro ao inserir email de recuperação: {str(e)}")
                    # Se falhar ao inserir o email, tentar pular
                    try:
                        skip_button = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable(
                                (By.XPATH, terms_locators.RECOVERY_EMAIL_SKIP))
                        )
                        skip_button.click()
                        logger.info(
                            "[OK] Botão 'Skip' clicado após falha ao inserir email")
                    except:
                        logger.error(
                            "[ERRO] Não foi possível pular após falha ao inserir email")
                        return False
            else:
                # Se não temos um email de recuperação, vamos pular esta etapa
                try:
                    logger.info(
                        "[OK] Nenhum email de recuperação fornecido, pulando etapa...")
                    skip_button = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable(
                            (By.XPATH, terms_locators.RECOVERY_EMAIL_SKIP))
                    )
                    skip_button.click()
                    logger.info("[OK] Botão 'Skip' clicado com sucesso")
                except Exception as e:
                    logger.error(
                        f"[ERRO] Erro ao clicar no botão Skip: {str(e)}")
                    return False

            time.sleep(2)  # Pequena pausa para processamento
            return True

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao gerenciar tela de email de recuperação: {str(e)}")
            return False

    def _save_screenshot(self, name):
        """Salva um screenshot para fins de depuração."""
        try:
            import os
            screenshot_dir = "logs/screenshots"
            os.makedirs(screenshot_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            filename = f"{screenshot_dir}/{name}_{timestamp}.png"
            self.driver.save_screenshot(filename)
            logger.info(f" Screenshot salvo: {filename}")
        except Exception as e:
            logger.error(f"[ERRO] Erro ao salvar screenshot: {str(e)}")
            # Continuar o fluxo mesmo se não conseguir salvar o screenshot

    def _check_account_created(self) -> bool:
        """Verifica se a conta foi criada com sucesso."""
        try:
            logger.info(
                "[BUSCA] Verificando se a conta foi criada com sucesso...")

            # Indicadores de criação bem-sucedida
            success_indicators = [
                # Logo do Google
                "//img[contains(@alt, 'Google')]",
                # Link para Gmail
                "//a[contains(@href, 'mail.google.com')]",
                "//div[contains(text(), 'conta Google foi criada')]",
                "//div[contains(text(), 'Google Account was created')]",
                "//div[contains(text(), 'Cuenta de Google')]",
                # Elemento principal da página após criação
                "//div[@role='main']"
            ]

            for indicator in success_indicators:
                if self._element_exists(indicator, timeout=2):
                    logger.info(
                        "[OK] Conta criada com sucesso! Indicador encontrado: " + indicator)
                    return True

            # Verificar URL atual
            try:
                current_url = self.driver.current_url
                if "myaccount.google.com" in current_url or "accounts.google.com/signin" in current_url:
                    logger.info(
                        f"[OK] Conta criada com sucesso! URL confirma: {current_url}")
                    return True
            except:
                pass

            logger.info(
                "[AVISO] Não foram encontrados indicadores de criação bem-sucedida da conta")
            return False

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao verificar criação da conta: {str(e)}")
            return False

    def _delete_screenshots(self) -> None:
        """Apaga todos os screenshots após a confirmação da criação da conta."""
        try:
            logger.info(" Iniciando limpeza dos screenshots...")
            screenshot_dir = "logs/screenshots"

            if not os.path.exists(screenshot_dir):
                logger.info(
                    "[OK] Nenhum diretório de screenshots encontrado para limpar")
                return

            # Obtém todos os arquivos PNG no diretório de screenshots
            files = glob.glob(f"{screenshot_dir}/*.png")

            if not files:
                logger.info("[OK] Nenhum screenshot encontrado para apagar")
                return

            count = 0
            for file in files:
                try:
                    os.remove(file)
                    count += 1
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Não foi possível apagar o arquivo {file}: {str(e)}")

            logger.info(f"[OK] {count} screenshots apagados com sucesso")

        except Exception as e:
            logger.error(f"[ERRO] Erro ao apagar screenshots: {str(e)}")

    def _scroll_to_detect_elements(self):
        """Rola a página para detectar elementos que possam estar fora da área visível."""
        try:
            logger.info(
                " Rolando a página para detectar todos os elementos...")

            # Rolar até o final
            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            # Rolar de volta para o topo
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)

            self._save_screenshot("after_scroll_detection")
        except Exception as e:
            logger.warning(f"[AVISO] Erro ao rolar a página: {str(e)}")

    def _count_visible_checkboxes(self):
        """Conta o número de checkboxes visíveis na página."""
        try:
            checkbox_selectors = [
                "//input[@type='checkbox']",
                "//div[contains(@class, 'VfPpkd-muHVFf-bMcfAe')]",
                "//div[contains(@role, 'checkbox')]",
                "//div[contains(@class, 'VfPpkd-MPu53c')]"
            ]

            count = 0
            for selector in checkbox_selectors:
                elements = self.driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed():
                        count += 1

            logger.info(
                f"[BUSCA] Encontrados {count} checkboxes visíveis na página")
            return count
        except Exception as e:
            logger.error(f"[ERRO] Erro ao contar checkboxes: {str(e)}")
            return 0
