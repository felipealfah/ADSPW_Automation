# automations/adsense_creator/verify_account.py

import logging
import time
import re
from urllib.parse import urlparse, parse_qs
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

logger = logging.getLogger(__name__)

# Tentativa de importar o BrowserManager. Se não existir, usaremos o fallback.
try:
    from powerads_api.browser_manager import BrowserManager
    HAS_BROWSER_MANAGER = True
    logger.info("[INFO] BrowserManager importado com sucesso")
except ImportError:
    HAS_BROWSER_MANAGER = False
    logger.warning(
        "[AVISO] BrowserManager não encontrado, usando método alternativo")


class AdSenseAccountVerifier:
    def __init__(self, driver):
        self.driver = driver
        self.base_url_pattern = r"https://www\.google\.com/adsense/new/u/0/pub-\d+/sites/detail/url="

    def is_adsense_verification_page(self, pub_id=None, site_url=None):
        """
        Verifica se estamos na página correta de verificação do AdSense.

        Args:
            pub_id (str, optional): ID do publisher (sem 'pub-'). Ex: 5586201132431151
            site_url (str, optional): URL do site. Ex: fulled.com.br

        Returns:
            bool: True se estamos na página correta
        """
        try:
            current_url = self.driver.current_url
            logger.info(f"[INFO] Verificando URL atual: {current_url}")

            # Verificar se está na página do AdSense
            if not re.match(self.base_url_pattern, current_url):
                logger.warning(
                    f"[AVISO] URL atual não corresponde ao padrão esperado do AdSense")
                return False

            # Se recebemos parâmetros específicos, verificar se correspondem à URL atual
            if pub_id:
                if f"pub-{pub_id}" not in current_url:
                    logger.warning(
                        f"[AVISO] Publisher ID '{pub_id}' não corresponde à URL atual")
                    return False

            if site_url:
                # Remover protocolo se existir
                clean_site_url = site_url.replace(
                    "https://", "").replace("http://", "").rstrip("/")
                if clean_site_url not in current_url:
                    logger.warning(
                        f"[AVISO] Site URL '{site_url}' não corresponde à URL atual")
                    return False

            logger.info(
                "[OK] Estamos na página correta de verificação do AdSense")
            return True

        except Exception as e:
            logger.error(f"[ERRO] Falha ao verificar página atual: {str(e)}")
            return False

    def navigate_to_verification_page(self, pub_id, site_url):
        """
        Navega para a página específica de verificação do AdSense.

        Args:
            pub_id (str): ID do publisher (sem 'pub-'). Ex: 5586201132431151
            site_url (str): URL do site. Ex: fulled.com.br

        Returns:
            bool: True se navegou com sucesso
        """
        try:
            # Remover protocolo se existir
            clean_site_url = site_url.replace(
                "https://", "").replace("http://", "").rstrip("/")
            # Construir URL completa
            target_url = f"https://www.google.com/adsense/new/u/0/pub-{pub_id}/sites/detail/url={clean_site_url}"

            logger.info(f"[INFO] Navegando para: {target_url}")
            self.driver.get(target_url)

            # Aguardar carregamento da página
            time.sleep(5)

            # Verificar se chegamos à página correta
            if self.is_adsense_verification_page(pub_id, clean_site_url):
                logger.info(
                    "[OK] Navegação para página de verificação bem-sucedida")
                return True
            else:
                logger.error(
                    "[ERRO] Falha ao navegar para página de verificação")
                return False

        except Exception as e:
            logger.error(
                f"[ERRO] Falha ao navegar para página de verificação: {str(e)}")
            return False

    def select_ads_txt_snippet_radio(self, timeout=10):
        """
        Seleciona o radio button "Snippet do ads.txt" antes de clicar no botão de verificação.

        Args:
            timeout (int): Tempo máximo de espera em segundos

        Returns:
            bool: True se selecionou com sucesso
        """
        try:
            logger.info(
                "[INFO] Tentando selecionar o radio button 'Snippet do ads.txt'")

            # XPath para o radio button "Snippet do ads.txt"
            radio_xpath = "/html/body/div[1]/bruschetta-app/as-exception-handler/div[2]/div/div[2]/div/main/div/site-management/as-exception-handler/sites/slidealog[4]/focus-trap/div[2]/material-drawer/div[2]/div[2]/div/paneled-detail/adsense-tagging/material-expansionpanel/div/div[2]/div/div[1]/div/div/material-radio-group/material-radio[2]"

            # Alternativas de localização
            alternative_xpaths = [
                "//material-radio[@debugid='ads-txt-snippet-type-radio']",
                "//material-radio[contains(.,'Snippet do ads.txt')]",
                "//label[contains(text(),'Snippet do ads.txt')]/parent::div/parent::material-radio"
            ]

            # Tentar o XPath principal primeiro
            try:
                radio_button = WebDriverWait(self.driver, timeout).until(
                    EC.element_to_be_clickable((By.XPATH, radio_xpath))
                )
                logger.info(
                    "[OK] Radio button 'Snippet do ads.txt' encontrado pelo XPath principal")
            except TimeoutException:
                # Tentar XPaths alternativos
                radio_button = None
                for alt_xpath in alternative_xpaths:
                    try:
                        logger.info(
                            f"[INFO] Tentando XPath alternativo: {alt_xpath}")
                        radio_button = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.XPATH, alt_xpath))
                        )
                        if radio_button:
                            logger.info(
                                f"[OK] Radio button encontrado com XPath alternativo: {alt_xpath}")
                            break
                    except:
                        continue

                if not radio_button:
                    logger.warning(
                        "[AVISO] Não foi possível encontrar o radio button 'Snippet do ads.txt'")
                    return False

            # Clicar no radio button usando JavaScript
            self.driver.execute_script("arguments[0].click();", radio_button)
            logger.info(
                "[OK] Radio button 'Snippet do ads.txt' selecionado com sucesso")

            # Aguardar para garantir que a seleção foi processada
            time.sleep(1)
            return True

        except Exception as e:
            logger.error(
                f"[ERRO] Falha ao selecionar radio button 'Snippet do ads.txt': {str(e)}")
            return False

    def check_published_ads_txt_checkbox(self, timeout=10):
        """
        Marca o checkbox "Publiquei o arquivo ads.txt" antes de clicar no botão de verificação.

        Args:
            timeout (int): Tempo máximo de espera em segundos

        Returns:
            bool: True se marcou com sucesso
        """
        try:
            logger.info(
                "[INFO] Tentando marcar o checkbox 'Publiquei o arquivo ads.txt'")

            # XPath para o checkbox "Publiquei o arquivo ads.txt"
            checkbox_xpath = "/html/body/div[1]/bruschetta-app/as-exception-handler/div[2]/div/div[2]/div/main/div/site-management/as-exception-handler/sites/slidealog[4]/focus-trap/div[2]/material-drawer/div[2]/div[2]/div/paneled-detail/adsense-tagging/material-expansionpanel/div/div[2]/div/div[1]/div/form/span/material-checkbox"

            # Alternativas de localização
            alternative_xpaths = [
                "//material-checkbox[contains(@class, 'confirm-site-tagged-checkbox')]",
                "//material-checkbox[contains(.,'Publiquei o arquivo ads.txt')]",
                "//div[contains(text(), 'Publiquei o arquivo ads.txt')]/parent::material-checkbox"
            ]

            # Tentar o XPath principal primeiro
            try:
                checkbox = WebDriverWait(self.driver, timeout).until(
                    EC.element_to_be_clickable((By.XPATH, checkbox_xpath))
                )
                logger.info(
                    "[OK] Checkbox 'Publiquei o arquivo ads.txt' encontrado pelo XPath principal")
            except TimeoutException:
                # Tentar XPaths alternativos
                checkbox = None
                for alt_xpath in alternative_xpaths:
                    try:
                        logger.info(
                            f"[INFO] Tentando XPath alternativo: {alt_xpath}")
                        checkbox = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.XPATH, alt_xpath))
                        )
                        if checkbox:
                            logger.info(
                                f"[OK] Checkbox encontrado com XPath alternativo: {alt_xpath}")
                            break
                    except:
                        continue

                if not checkbox:
                    logger.warning(
                        "[AVISO] Não foi possível encontrar o checkbox 'Publiquei o arquivo ads.txt'")
                    return False

            # Verificar se o checkbox já está marcado
            is_checked = self.driver.execute_script(
                "return arguments[0].getAttribute('aria-checked') === 'true';", checkbox
            )

            if is_checked:
                logger.info(
                    "[INFO] Checkbox 'Publiquei o arquivo ads.txt' já está marcado")
                return True

            # Clicar no checkbox usando JavaScript
            self.driver.execute_script("arguments[0].click();", checkbox)
            logger.info(
                "[OK] Checkbox 'Publiquei o arquivo ads.txt' marcado com sucesso")

            # Aguardar para garantir que a ação foi processada
            time.sleep(1)

            # Verificar se o checkbox foi marcado corretamente
            is_checked_after = self.driver.execute_script(
                "return arguments[0].getAttribute('aria-checked') === 'true';", checkbox
            )

            if not is_checked_after:
                logger.warning(
                    "[AVISO] O checkbox não foi marcado corretamente. Tentando novamente.")
                self.driver.execute_script("arguments[0].click();", checkbox)
                time.sleep(1)

            return True

        except Exception as e:
            logger.error(
                f"[ERRO] Falha ao marcar checkbox 'Publiquei o arquivo ads.txt': {str(e)}")
            return False

    def handle_verification_popup(self, timeout=8):
        """
        Detecta e lida com o popup de erro de verificação do site.

        Args:
            timeout (int): Tempo máximo de espera pelo popup em segundos

        Returns:
            dict: Informações sobre o popup {'detected': bool, 'message': str, 'is_error': bool, 'handled': bool}
        """
        try:
            logger.info(
                "[INFO] Verificando se apareceu um popup de resultado da verificação")

            # XPaths específicos baseados nos dados fornecidos
            popup_xpath = "/html/body/div[3]/div[2]/material-dialog"
            title_xpath = "/html/body/div[3]/div[2]/material-dialog/focus-trap/div[2]/div/div[2]/h5"
            ok_button_xpath = "/html/body/div[3]/div[2]/material-dialog/focus-trap/div[2]/div/div[2]/button"

            # XPaths alternativos caso a estrutura mude ligeiramente
            alt_popup_xpaths = [
                "//material-dialog",
                "//div[contains(@class, 'material-dialog')]",
                "//div[@role='dialog']"
            ]

            alt_title_xpaths = [
                "//material-dialog//h5",
                "//div[@role='dialog']//h5",
                "//div[@role='dialog']//*[contains(@class, 'title')]"
            ]

            alt_ok_button_xpaths = [
                "//material-dialog//button",
                "//div[@role='dialog']//button",
                "//button[contains(.,'OK')]",
                "//button[contains(., 'Ok')]"
            ]

            # Tentar encontrar o popup principal
            try:
                popup = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.XPATH, popup_xpath))
                )
                logger.info("[INFO] Popup de verificação detectado")
            except TimeoutException:
                # Tentar XPaths alternativos
                popup = None
                for alt_xpath in alt_popup_xpaths:
                    try:
                        popup = WebDriverWait(self.driver, 2).until(
                            EC.presence_of_element_located(
                                (By.XPATH, alt_xpath))
                        )
                        if popup:
                            logger.info(
                                f"[INFO] Popup detectado com XPath alternativo: {alt_xpath}")
                            break
                    except:
                        continue

                if not popup:
                    logger.info("[INFO] Nenhum popup de verificação detectado")
                    return {"detected": False, "message": "", "is_error": False, "handled": False}

            # Tentar obter a mensagem do título
            try:
                title_element = WebDriverWait(self.driver, 3).until(
                    EC.presence_of_element_located((By.XPATH, title_xpath))
                )
                error_message = title_element.text
                logger.info(f"[INFO] Mensagem do popup: '{error_message}'")
            except:
                # Tentar XPaths alternativos para o título
                error_message = ""
                for alt_xpath in alt_title_xpaths:
                    try:
                        title_element = self.driver.find_element(
                            By.XPATH, alt_xpath)
                        error_message = title_element.text
                        logger.info(
                            f"[INFO] Mensagem do popup (alternativa): '{error_message}'")
                        break
                    except:
                        continue

                if not error_message:
                    # Se não encontrar título específico, obter todo o texto do popup
                    error_message = popup.text
                    logger.info(
                        f"[INFO] Texto completo do popup: '{error_message}'")

            # Verificar se é uma mensagem de erro
            error_keywords = [
                "não foi possível verificar", "not verified", "verification failed",
                "erro", "error", "falha", "failed", "problema", "problem"
            ]

            is_error = any(keyword.lower() in error_message.lower()
                           for keyword in error_keywords)

            # Tentar clicar no botão OK
            handled = False
            try:
                ok_button = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, ok_button_xpath))
                )

                # Clicar no botão OK com JavaScript
                self.driver.execute_script("arguments[0].click();", ok_button)
                logger.info("[INFO] Clicou no botão OK do popup")
                handled = True
            except:
                # Tentar XPaths alternativos para o botão OK
                for alt_xpath in alt_ok_button_xpaths:
                    try:
                        ok_button = self.driver.find_element(
                            By.XPATH, alt_xpath)
                        self.driver.execute_script(
                            "arguments[0].click();", ok_button)
                        logger.info(
                            f"[INFO] Clicou no botão OK (alternativo) do popup: {alt_xpath}")
                        handled = True
                        break
                    except:
                        continue

                if not handled:
                    logger.warning(
                        "[AVISO] Não foi possível clicar no botão OK do popup")

            # Aguardar o popup desaparecer se o botão foi clicado
            if handled:
                try:
                    WebDriverWait(self.driver, 3).until_not(
                        EC.presence_of_element_located((By.XPATH, popup_xpath))
                    )
                    logger.info("[INFO] Popup fechado com sucesso")
                except:
                    logger.warning(
                        "[AVISO] Popup pode não ter sido fechado corretamente")

            return {
                "detected": True,
                "message": error_message,
                "is_error": is_error,
                "handled": handled
            }

        except Exception as e:
            logger.error(
                f"[ERRO] Falha ao lidar com popup de verificação: {str(e)}")
            return {"detected": False, "message": str(e), "is_error": True, "handled": False}

    def click_verification_button(self, xpath=None, timeout=15):
        """
        Clica no botão de verificação na página do AdSense.

        Args:
            xpath (str, optional): XPath personalizado para o botão. Se None, usa o padrão.
            timeout (int): Tempo máximo de espera em segundos

        Returns:
            bool: True se o clique foi bem-sucedido
        """
        try:
            # Espera a página carregar
            time.sleep(3)

            # 1. Primeiro, seleciona o radio button "Snippet do ads.txt"
            if not self.select_ads_txt_snippet_radio():
                logger.warning(
                    "[AVISO] Não foi possível selecionar o radio button, mas continuando com a verificação")

            # 2. Em seguida, marca o checkbox "Publiquei o arquivo ads.txt"
            if not self.check_published_ads_txt_checkbox():
                logger.warning(
                    "[AVISO] Não foi possível marcar o checkbox, mas continuando com a verificação")

            # Usa o XPath fornecido ou o padrão
            if not xpath:
                # XPath para o botão "Verificar"
                xpath = "/html/body/div[1]/bruschetta-app/as-exception-handler/div[2]/div/div[2]/div/main/div/site-management/as-exception-handler/sites/slidealog[4]/focus-trap/div[2]/material-drawer/div[2]/div[2]/div/paneled-detail/adsense-tagging/material-expansionpanel/div/div[2]/div/div[1]/div/form/button/material-ripple"

            logger.info(
                f"[INFO] Tentando clicar no botão usando XPath: {xpath}")

            # Encontrar o botão
            try:
                # Tenta encontrar o elemento com espera explícita
                button = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.XPATH, xpath))
                )
            except TimeoutException:
                # Se falhar, tenta encontrar um elemento pai do botão
                logger.warning(
                    "[AVISO] Não encontrou o botão pelo XPath fornecido, tentando alternativas...")

                # Tentar localizar pelo texto do botão ("Verificar")
                try:
                    button = self.driver.find_element(
                        By.XPATH, "//button[contains(.,'Verificar')]")
                    logger.info("[OK] Encontrou botão 'Verificar' por texto")
                except NoSuchElementException:
                    # Tentar pelo seletor CSS
                    try:
                        button = self.driver.find_element(
                            By.CSS_SELECTOR, "material-expansionpanel button")
                        logger.info("[OK] Encontrou botão pelo CSS selector")
                    except NoSuchElementException:
                        logger.error(
                            "[ERRO] Não foi possível encontrar o botão de verificação")
                        return False

            # Clicar usando JavaScript (mais confiável)
            self.driver.execute_script("arguments[0].click();", button)
            logger.info("[OK] Botão de verificação clicado com sucesso!")

            # Aguardar feedback visual da ação
            time.sleep(3)

            # Verificar se há popup de resultado da verificação
            popup_result = self.handle_verification_popup()

            if popup_result["detected"]:
                if popup_result["is_error"]:
                    logger.warning(
                        f"[AVISO] Verificação falhou: {popup_result['message']}")
                    # Se detectou um erro no popup, retornamos False
                    return False
                else:
                    # Se não é um erro, pode ser um aviso ou confirmação
                    logger.info(
                        f"[INFO] Mensagem após verificação: {popup_result['message']}")
                    return True
            else:
                # Se não detectou popup, verificar se há outros indicadores de sucesso
                try:
                    success_element = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located(
                            (By.XPATH, "//*[contains(text(), 'verificação bem-sucedida') or contains(text(), 'verificado com sucesso')]"))
                    )
                    logger.info("[OK] Verificação concluída com sucesso!")
                    return True
                except TimeoutException:
                    # Sem confirmação clara, assumimos sucesso com aviso
                    logger.info(
                        "[INFO] Sem confirmação clara de sucesso ou falha, considerando bem-sucedido")
                    return True

        except Exception as e:
            logger.error(
                f"[ERRO] Falha ao clicar no botão de verificação: {str(e)}")
            return False

    def click_site_review_button(self, timeout=15):
        """
        Clica no botão de "Revisão do site" que aparece após a verificação ser concluída.

        Args:
            timeout (int): Tempo máximo de espera em segundos

        Returns:
            bool: True se o clique foi bem-sucedido
        """
        try:
            logger.info("[INFO] Tentando clicar no botão 'Revisão do site'...")

            # XPath para o botão "Revisão do site"
            review_button_xpath = "/html/body/div[1]/bruschetta-app/as-exception-handler/div[2]/div/div[2]/div/main/div[2]/site-management/as-exception-handler/sites/slidealog[4]/focus-trap/div[2]/material-drawer/div[2]/div[2]/div/paneled-detail/review-panel/material-expansionpanel/div/div[2]/div/div[1]/div/form/button/material-ripple"

            # XPaths alternativos para o botão "Revisão do site"
            alt_review_button_xpaths = [
                "//review-panel//button",
                "//button[contains(.,'Revisão')]",
                "//button[contains(.,'Review')]",
                "//material-expansionpanel[contains(.,'Revisão')]//button",
                "//material-expansionpanel[contains(.,'Review')]//button"
            ]

            # Aguardar o botão aparecer
            time.sleep(3)

            # Tenta encontrar o botão pelo XPath principal
            try:
                review_button = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located(
                        (By.XPATH, review_button_xpath))
                )
                logger.info(
                    "[OK] Botão 'Revisão do site' encontrado pelo XPath principal")
            except TimeoutException:
                # Tentar XPaths alternativos
                review_button = None
                for alt_xpath in alt_review_button_xpaths:
                    try:
                        logger.info(
                            f"[INFO] Tentando XPath alternativo: {alt_xpath}")
                        review_button = WebDriverWait(self.driver, 3).until(
                            EC.presence_of_element_located(
                                (By.XPATH, alt_xpath))
                        )
                        if review_button:
                            logger.info(
                                f"[OK] Botão encontrado com XPath alternativo: {alt_xpath}")
                            break
                    except:
                        continue

                if not review_button:
                    logger.warning(
                        "[AVISO] Não foi possível encontrar o botão 'Revisão do site'")
                    return False

            # Tentar clicar usando JavaScript (mais confiável)
            self.driver.execute_script("arguments[0].click();", review_button)
            logger.info("[OK] Botão 'Revisão do site' clicado com sucesso!")

            # Aguardar para que a ação seja processada
            time.sleep(3)

            # Lidar com a janela de consentimento
            if self.handle_consent_form():
                logger.info(
                    "[OK] Formulário de consentimento preenchido com sucesso!")
                return True
            else:
                logger.warning(
                    "[AVISO] Não foi possível preencher o formulário de consentimento")
                return False

        except Exception as e:
            logger.error(
                f"[ERRO] Falha ao clicar no botão 'Revisão do site': {str(e)}")
            return False

    def handle_consent_form(self, timeout=15):
        """
        Lida com o formulário de consentimento que aparece após clicar no botão de Revisão do site.
        Seleciona o radiobutton e clica no botão enviar.

        Args:
            timeout (int): Tempo máximo de espera em segundos

        Returns:
            bool: True se o preenchimento foi bem-sucedido
        """
        try:
            logger.info(
                "[INFO] Tentando preencher o formulário de consentimento...")

            # XPath para o radiobutton
            radio_xpath = "/html/body/div[1]/bruschetta-app/as-exception-handler/div[2]/div/div[2]/div/main/div[2]/site-management/as-exception-handler/sites/slidealog[4]/focus-trap/div[2]/material-drawer/div[2]/div[2]/div/paneled-detail/div[2]/site-consent/form/div/material-radio-group/div/div[1]/material-radio/div[1]/input"

            # XPath para o botão enviar
            submit_button_xpath = "/html/body/div[1]/bruschetta-app/as-exception-handler/div[2]/div/div[2]/div/main/div[2]/site-management/as-exception-handler/sites/slidealog[4]/focus-trap/div[2]/material-drawer/div[2]/div[2]/div/paneled-detail/div[2]/site-consent/form/div/div[2]/div/button[2]/material-ripple"

            # XPaths alternativos
            alt_radio_xpaths = [
                "//material-radio//input",
                "//material-radio-group//input",
                "//form//material-radio//input"
            ]

            alt_submit_button_xpaths = [
                "//button[contains(.,'Enviar')]",
                "//button[contains(.,'Submit')]",
                "//form//button[last()]",
                "//site-consent//button[last()]"
            ]

            # Esperar um momento para a janela aparecer
            time.sleep(3)

            # Tentar encontrar o radiobutton
            radio_button = None
            try:
                radio_button = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.XPATH, radio_xpath))
                )
                logger.info("[OK] Radiobutton encontrado pelo XPath principal")
            except TimeoutException:
                # Tentar XPaths alternativos
                for alt_xpath in alt_radio_xpaths:
                    try:
                        logger.info(
                            f"[INFO] Tentando XPath alternativo para radiobutton: {alt_xpath}")
                        radio_button = WebDriverWait(self.driver, 3).until(
                            EC.presence_of_element_located(
                                (By.XPATH, alt_xpath))
                        )
                        if radio_button:
                            logger.info(
                                f"[OK] Radiobutton encontrado com XPath alternativo: {alt_xpath}")
                            break
                    except:
                        continue

            # Se encontrou o radiobutton, clicar nele
            if radio_button:
                # Verificar se o radiobutton já está selecionado
                is_checked = self.driver.execute_script(
                    "return arguments[0].checked;", radio_button
                )

                if not is_checked:
                    # Clicar no radiobutton usando JavaScript
                    self.driver.execute_script(
                        "arguments[0].click();", radio_button)
                    logger.info("[OK] Radiobutton clicado com sucesso")

                    # Aguardar para garantir que a seleção foi processada
                    time.sleep(1)
                else:
                    logger.info("[INFO] Radiobutton já está selecionado")
            else:
                logger.warning(
                    "[AVISO] Não foi possível encontrar o radiobutton no formulário")
                # Continuar mesmo sem conseguir selecionar o radiobutton

            # Tentar encontrar o botão enviar
            submit_button = None
            try:
                submit_button = WebDriverWait(self.driver, timeout).until(
                    EC.element_to_be_clickable((By.XPATH, submit_button_xpath))
                )
                logger.info(
                    "[OK] Botão enviar encontrado pelo XPath principal")
            except TimeoutException:
                # Tentar XPaths alternativos
                for alt_xpath in alt_submit_button_xpaths:
                    try:
                        logger.info(
                            f"[INFO] Tentando XPath alternativo para botão enviar: {alt_xpath}")
                        submit_button = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.XPATH, alt_xpath))
                        )
                        if submit_button:
                            logger.info(
                                f"[OK] Botão enviar encontrado com XPath alternativo: {alt_xpath}")
                            break
                    except:
                        continue

            # Se encontrou o botão enviar, clicar nele
            if submit_button:
                # Clicar no botão usando JavaScript
                self.driver.execute_script(
                    "arguments[0].click();", submit_button)
                logger.info("[OK] Botão enviar clicado com sucesso!")

                # Aguardar para que a ação seja processada
                time.sleep(5)

                # Verificar se o envio foi bem-sucedido (mudança de URL ou elemento na página)
                try:
                    # Verificar algum indicador de sucesso
                    success_indicator = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located(
                            (By.XPATH,
                             "//*[contains(text(), 'sucesso') or contains(text(), 'success')]")
                        )
                    )
                    logger.info("[OK] Formulário enviado com sucesso!")
                except TimeoutException:
                    # Mesmo sem confirmação explícita, consideramos que foi enviado
                    logger.info(
                        "[INFO] Sem confirmação explícita, mas assumindo que o formulário foi enviado")

                return True
            else:
                logger.error(
                    "[ERRO] Não foi possível encontrar o botão enviar no formulário")
                return False

        except Exception as e:
            logger.error(
                f"[ERRO] Falha ao preencher formulário de consentimento: {str(e)}")
            return False

    def verify_site(self, pub_id=None, site_url=None):
        """
        Processo completo de verificação do site no AdSense.

        Args:
            pub_id (str, optional): ID do publisher (sem 'pub-'). Ex: 5586201132431151
            site_url (str, optional): URL do site. Ex: fulled.com.br

        Returns:
            bool: True se o processo foi concluído com sucesso
        """
        try:
            # Verificar se já estamos na página correta
            is_correct_page = self.is_adsense_verification_page(
                pub_id, site_url)

            # Se não estamos na página correta e temos os parâmetros, navegar para ela
            if not is_correct_page and pub_id and site_url:
                if not self.navigate_to_verification_page(pub_id, site_url):
                    logger.error(
                        "[ERRO] Falha ao navegar para a página de verificação")
                    return False
            elif not is_correct_page:
                logger.error(
                    "[ERRO] Não estamos na página correta e não temos parâmetros para navegação")
                return False

            # Clicar no botão de verificação
            verify_result = self.click_verification_button()
            if not verify_result:
                logger.error("[ERRO] Falha ao verificar o site")
                return False

            logger.info("[OK] Site verificado com sucesso!")

            # Aguardar um momento para a interface atualizar
            time.sleep(3)

            # Clicar no botão "Revisão do site" após a verificação bem-sucedida
            review_result = self.click_site_review_button()
            if review_result:
                logger.info(
                    "[OK] Processo de revisão do site concluído com sucesso!")
            else:
                logger.warning(
                    "[AVISO] Não foi possível completar o processo de revisão do site, mas a verificação foi concluída")

            return True

        except Exception as e:
            logger.error(f"[ERRO] Falha ao verificar site: {str(e)}")
            return False

    def close_browser(self):
        """
        Fecha o navegador após a conclusão de todo o processo.
        Tenta usar o BrowserManager se disponível, caso contrário usa driver.quit().

        Returns:
            bool: True se o navegador foi fechado com sucesso
        """
        try:
            logger.info(
                "[INFO] Finalizando o processo e fechando o navegador...")

            # Aguardar um momento antes de fechar (opcional)
            time.sleep(3)

            if not self.driver:
                logger.warning(
                    "[AVISO] Driver já está fechado ou não foi inicializado")
                return False

            # Tentar obter o user_id do AdsPower da URL, se disponível
            user_id = None
            try:
                # Verificar se há algum atributo que indique o user_id do AdsPower
                if hasattr(self.driver, "adspower_user_id"):
                    user_id = getattr(self.driver, "adspower_user_id")
                    logger.info(
                        f"[INFO] User ID do AdsPower encontrado: {user_id}")
            except Exception as e:
                logger.warning(
                    f"[AVISO] Não foi possível obter o user_id do AdsPower: {str(e)}")

            # Verificar se o BrowserManager está disponível e se temos um user_id
            if HAS_BROWSER_MANAGER and user_id:
                try:
                    from powerads_api.browser_manager import BrowserManager

                    # Se já tivermos uma instância do BrowserManager disponível no driver
                    if hasattr(self.driver, "browser_manager"):
                        browser_manager = getattr(
                            self.driver, "browser_manager")
                        success = browser_manager.close_browser(user_id)

                        if success:
                            logger.info(
                                "[OK] Navegador fechado com sucesso usando BrowserManager")
                            self.driver = None
                            return True
                        else:
                            logger.warning(
                                "[AVISO] Falha ao fechar navegador com BrowserManager, tentando método alternativo")
                    else:
                        logger.warning(
                            "[AVISO] BrowserManager não encontrado no driver, tentando método alternativo")
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro ao usar BrowserManager: {str(e)}, tentando método alternativo")

            # Se não conseguir usar o BrowserManager ou não tiver o user_id, tenta o método padrão
            try:
                # Método Selenium padrão
                current_url = self.driver.current_url  # Salvar URL atual antes de fechar
                self.driver.quit()
                logger.info(
                    "[OK] Navegador fechado com sucesso usando driver.quit()")

                # Importante: definir driver como None após fechar
                self.driver = None
                return True
            except Exception as e:
                logger.error(
                    f"[ERRO] Falha específica ao fechar o navegador com driver.quit(): {str(e)}")

                # Mesmo com erro, definir driver como None
                self.driver = None
                return False

        except Exception as e:
            logger.error(f"[ERRO] Falha geral ao fechar o navegador: {str(e)}")

            # Mesmo com erro, tentar definir driver como None
            try:
                self.driver = None
            except:
                pass

            return False

    def verify_site_and_close(self, pub_id=None, site_url=None):
        """
        Executa todo o processo de verificação do site e fecha o navegador ao final.

        Args:
            pub_id (str, optional): ID do publisher (sem 'pub-'). Ex: 5586201132431151
            site_url (str, optional): URL do site. Ex: fulled.com.br

        Returns:
            bool: True se todo o processo foi concluído com sucesso
        """
        try:
            # Executar o processo de verificação
            verify_result = self.verify_site(pub_id, site_url)

            # Fechar o navegador independente do resultado
            close_result = self.close_browser()

            if not close_result:
                logger.warning(
                    "[AVISO] O navegador pode não ter sido fechado corretamente")

            # Retornar o resultado da verificação
            return verify_result

        except Exception as e:
            logger.error(f"[ERRO] Falha no processo completo: {str(e)}")

            # Tentar fechar o navegador mesmo em caso de erro
            try:
                self.close_browser()
            except Exception as e2:
                logger.error(
                    f"[ERRO] Falha na tentativa de fechar navegador após erro: {str(e2)}")

            return False

    def verify_and_close(self):
        """Método mantido para compatibilidade com versões anteriores"""
        try:
            xpath = "/html/body/div[1]/bruschetta-app/as-exception-handler/div[2]/div/div[2]/div/main/div/site-management/as-exception-handler/sites/slidealog[4]/focus-trap/div[2]/material-drawer/div[2]/div[2]/div/paneled-detail/adsense-tagging/material-expansionpanel/div/div[2]/div/div[1]/div/form/button/material-ripple"
            verify_result = self.click_verification_button(xpath)

            if verify_result:
                # Também tentar clicar no botão de revisão
                review_result = self.click_site_review_button()
                if not review_result:
                    logger.warning(
                        "[AVISO] Não foi possível completar a revisão do site")

            # Fechar o navegador no final do processo, independente do resultado
            self.close_browser()

            return verify_result
        except Exception as e:
            logger.error(f"[ERRO] Falha em verify_and_close: {str(e)}")

            # Tentar fechar o navegador mesmo em caso de erro
            try:
                self.close_browser()
            except:
                pass

            return False
