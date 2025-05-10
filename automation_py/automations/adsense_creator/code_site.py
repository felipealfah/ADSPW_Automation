import logging
import time
import os
import re
import glob
import shutil
from typing import Dict, Any, Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, ElementNotInteractableException,
    NoSuchElementException, StaleElementReferenceException
)
from selenium.webdriver.common.action_chains import ActionChains

from .exceptions import WebsiteVerificationError
from .config import timeouts

logger = logging.getLogger(__name__)

# Configuração para habilitar/desabilitar modo de debug com screenshots
DEBUG_MODE = False


class WebsiteCodeInjector:
    """
    Classe responsável por capturar o código de verificação do AdSense.
    Esta é a segunda parte da automação, após a criação da conta AdSense.
    """

    def __init__(self, driver, website_data: Dict[str, Any]):
        """
        Inicializa o injetor de código.

        Args:
            driver: WebDriver do Selenium
            website_data: Dicionário com informações do site
        """
        self.driver = driver
        self.website_data = website_data
        self.wait = WebDriverWait(driver, timeouts.DEFAULT_WAIT)
        self.verification_code = ""
        self.publisher_id = ""
        self.website_url = website_data.get("website_url", "")
        self.max_retries = 3
        self.retry_delay = 2
        # Lista para rastrear screenshots gerados nesta instância
        self.screenshot_files = []

    def capture_verification_code(self, export_data: bool = False) -> bool:
        """
        Processo para captura do código de verificação e publisher ID.

        Args:
            export_data: Se True, exporta os dados capturados para um arquivo

        Returns:
            bool: True se capturou o código com sucesso
        """
        try:
            logger.info(
                "[INICIO] Iniciando captura do código de verificação e publisher ID...")

            # Verificar se estamos na página de onboarding do AdSense
            current_url = self.driver.current_url
            logger.info(f"[INFO] URL atual: {current_url}")

            # Capturar screenshot para debug
            if DEBUG_MODE:
                self._save_screenshot("adsense_onboarding_page")

            # Extrair o publisher ID da URL
            pub_id = self._extract_publisher_id(current_url)
            if pub_id:
                self.publisher_id = pub_id
                logger.info(
                    f"[OK] Publisher ID capturado com sucesso: {pub_id}")
            else:
                logger.error(
                    "[ERRO] Não foi possível extrair o publisher ID da URL")
                if DEBUG_MODE:
                    self.clean_screenshots()
                return False

            # Aguardar carregamento completo da página
            self._wait_for_page_load()

            # Clicar no botão para ir para a próxima tela
            if not self._click_next_button():
                logger.error(
                    "[ERRO] Não foi possível clicar no botão para próxima tela")
                if DEBUG_MODE:
                    self.clean_screenshots()
                return False

            # Aguardar carregamento da nova página
            time.sleep(5)
            self._wait_for_page_load()

            # Capturar screenshot da nova página
            if DEBUG_MODE:
                self._save_screenshot("adsense_verification_page")

            # Clicar no radio button "Snippet do ads.txt"
            if self._click_ads_txt_radio_button():
                logger.info(
                    "[OK] Radio button 'Snippet do ads.txt' clicado com sucesso")

                # Aguardar um momento para que a interface atualize após o clique
                time.sleep(2)

                # Capturar screenshot após clicar no radio button
                if DEBUG_MODE:
                    self._save_screenshot("after_radio_button_click")

                # Tentar capturar especificamente o snippet do ads.txt
                if self._capture_ads_txt_snippet():
                    logger.info(
                        "[OK] Snippet do ads.txt capturado com sucesso após clicar no radio button")
                else:
                    logger.warning(
                        "[AVISO] Não foi possível capturar o snippet do ads.txt após clicar no radio button")
                    # Tentar o método genérico de captura
                    if self._capture_verification_code_from_page():
                        logger.info(
                            f"[OK] Código de verificação capturado com sucesso pelo método genérico: {self.verification_code}")
                    else:
                        logger.warning(
                            "[AVISO] Não foi possível capturar o código de verificação da página")
            else:
                logger.warning(
                    "[AVISO] Não foi possível clicar no radio button 'Snippet do ads.txt'")
                # Tentar capturar o código de verificação da página mesmo sem clicar no radio button
                if self._capture_verification_code_from_page():
                    logger.info(
                        f"[OK] Código de verificação capturado com sucesso: {self.verification_code}")
                else:
                    logger.warning(
                        "[AVISO] Não foi possível capturar o código de verificação da página")

            # Retornar os dados capturados
            self.website_data["publisher_id"] = self.publisher_id
            self.website_data["verification_code"] = self.verification_code

            # Verificar se capturamos pelo menos um dos códigos
            if not self.verification_code:
                logger.warning(
                    "[AVISO] Não foi possível capturar nenhum código de verificação")
                # Continuar mesmo sem o código de verificação, pois já temos o publisher ID

            # Exportar os dados capturados se solicitado (agora falso por padrão)
            if export_data:
                self.export_captured_data()

            logger.info("[OK] Códigos capturados com sucesso")

            # Limpar screenshots no final da execução bem-sucedida
            if DEBUG_MODE:
                self.clean_screenshots()

            return True

        except Exception as e:
            logger.error(
                f"[ERRO] Falha ao capturar o código de verificação: {str(e)}")
            if DEBUG_MODE:
                self._save_screenshot("verification_code_error")
                # Limpar screenshots mesmo em caso de erro
                self.clean_screenshots()
            return False

    def _click_ads_txt_radio_button(self) -> bool:
        """
        Clica no radio button "Snippet do ads.txt".

        Returns:
            bool: True se o clique foi bem-sucedido
        """
        try:
            logger.info(
                "[INFO] Tentando clicar no radio button 'Snippet do ads.txt'...")

            # XPath específico do radio button fornecido
            radio_xpath = "/html/body/div[1]/bruschetta-app/as-exception-handler/div[2]/div/div[2]/div/main/div[2]/site-management/as-exception-handler/sites/slidealog[4]/focus-trap/div[2]/material-drawer/div[2]/div[2]/div/paneled-detail/adsense-tagging/material-expansionpanel/div/div[2]/div/div[1]/div/div/material-radio-group/material-radio[2]"

            # Tentar diferentes abordagens para encontrar e clicar no radio button

            # Abordagem 1: Tentar com o XPath específico
            if self._check_element_exists(By.XPATH, radio_xpath, timeout=10):
                radio_button = self.driver.find_element(By.XPATH, radio_xpath)
                return self._click_safely(radio_button)

            # Abordagem 2: Tentar encontrar pelo texto da label
            label_text = "Snippet do ads.txt"
            label_xpath = f"//label[contains(text(), '{label_text}')]"

            if self._check_element_exists(By.XPATH, label_xpath, timeout=5):
                label_element = self.driver.find_element(By.XPATH, label_xpath)
                parent_radio = label_element.find_element(By.XPATH, "..")
                return self._click_safely(parent_radio)

            # Abordagem 3: Tentar encontrar pelo atributo debugid
            debug_id_xpath = "//material-radio[@debugid='ads-txt-snippet-type-radio']"
            if self._check_element_exists(By.XPATH, debug_id_xpath, timeout=5):
                debug_id_element = self.driver.find_element(
                    By.XPATH, debug_id_xpath)
                return self._click_safely(debug_id_element)

            # Abordagem 4: Tentar encontrar todos os radio buttons e clicar no segundo
            radio_group_xpath = "//material-radio-group/material-radio"
            if self._check_element_exists(By.XPATH, radio_group_xpath, timeout=5):
                radio_buttons = self.driver.find_elements(
                    By.XPATH, radio_group_xpath)
                if len(radio_buttons) >= 2:  # Garantir que há pelo menos 2 radio buttons
                    # Clicar no segundo (índice 1)
                    return self._click_safely(radio_buttons[1])

            logger.warning(
                "[AVISO] Não foi possível encontrar o radio button 'Snippet do ads.txt'")
            return False

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao clicar no radio button 'Snippet do ads.txt': {str(e)}")
            return False

    def _click_next_button(self) -> bool:
        """
        Clica no botão para ir para a próxima tela.

        Returns:
            bool: True se o clique foi bem-sucedido
        """
        try:
            logger.info("[INFO] Tentando clicar no botão para próxima tela...")

            # XPath específico do botão fornecido
            button_xpath = "/html/body/div[1]/bruschetta-app/as-exception-handler/div[2]/div/div[2]/div/main/div[1]/onboarding/as-exception-handler/onboarding-overview/div[2]/div/onboarding-card[3]/article/div[2]/button/material-ripple"

            # Tentar diferentes abordagens para encontrar e clicar no botão

            # Abordagem 1: Tentar com o XPath específico
            if self._check_element_exists(By.XPATH, button_xpath):
                button = self.driver.find_element(By.XPATH, button_xpath)
                return self._click_safely(button)

            # Abordagem 2: Tentar encontrar o botão pai
            parent_button_xpath = "/html/body/div[1]/bruschetta-app/as-exception-handler/div[2]/div/div[2]/div/main/div[1]/onboarding/as-exception-handler/onboarding-overview/div[2]/div/onboarding-card[3]/article/div[2]/button"
            if self._check_element_exists(By.XPATH, parent_button_xpath):
                parent_button = self.driver.find_element(
                    By.XPATH, parent_button_xpath)
                return self._click_safely(parent_button)

            # Abordagem 3: Tentar encontrar por seletores mais genéricos
            possible_button_selectors = [
                "//button[contains(@class, 'next')]",
                "//button[contains(@class, 'continue')]",
                "//button[contains(text(), 'Next')]",
                "//button[contains(text(), 'Continue')]",
                "//button[contains(text(), 'Próximo')]",
                "//button[contains(text(), 'Continuar')]",
                "//onboarding-card[3]//button",
                "//article//div[2]//button"
            ]

            for selector in possible_button_selectors:
                if self._check_element_exists(By.XPATH, selector):
                    button = self.driver.find_element(By.XPATH, selector)
                    if button.is_displayed() and button.is_enabled():
                        return self._click_safely(button)

            logger.warning(
                "[AVISO] Não foi possível encontrar o botão para próxima tela")
            return False

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao clicar no botão para próxima tela: {str(e)}")
            return False

    def _click_safely(self, element) -> bool:
        """
        Tenta clicar em um elemento de várias formas para garantir que o clique funcione.

        Args:
            element: Elemento a ser clicado

        Returns:
            bool: True se o clique foi bem-sucedido
        """
        try:
            # Rolar até o elemento para garantir que está visível
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(1)

            # Método 1: Clique normal
            try:
                element.click()
                logger.info("[OK] Clique normal bem-sucedido")
                return True
            except Exception as e1:
                logger.warning(f"[AVISO] Clique normal falhou: {str(e1)}")

            # Método 2: Clique via JavaScript
            try:
                self.driver.execute_script("arguments[0].click();", element)
                logger.info("[OK] Clique via JavaScript bem-sucedido")
                return True
            except Exception as e2:
                logger.warning(
                    f"[AVISO] Clique via JavaScript falhou: {str(e2)}")

            # Método 3: Clique via ActionChains
            try:
                actions = ActionChains(self.driver)
                actions.move_to_element(element).click().perform()
                logger.info("[OK] Clique via ActionChains bem-sucedido")
                return True
            except Exception as e3:
                logger.warning(
                    f"[AVISO] Clique via ActionChains falhou: {str(e3)}")

            logger.error("[ERRO] Todos os métodos de clique falharam")
            return False

        except Exception as e:
            logger.error(f"[ERRO] Erro ao tentar clicar no elemento: {str(e)}")
            return False

    def _check_element_exists(self, by, locator, timeout=3) -> bool:
        """
        Verifica se um elemento existe na página.

        Args:
            by: Tipo de localizador (By.XPATH, By.ID, etc.)
            locator: O localizador do elemento
            timeout: Tempo máximo de espera em segundos

        Returns:
            bool: True se o elemento existe
        """
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, locator))
            )
            return True
        except Exception:
            return False

    def _extract_publisher_id(self, url: str) -> str:
        """
        Extrai o publisher ID da URL de onboarding do AdSense.

        Args:
            url: URL da página de onboarding

        Returns:
            str: Publisher ID extraído ou string vazia se não encontrado
        """
        try:
            # Padrão para extrair o publisher ID (pub-XXXXXXXXXXXXXXXX)
            pattern = r'pub-\d{16}'
            match = re.search(pattern, url)

            if match:
                return match.group(0)

            # Se não encontrou com o padrão específico, tentar um padrão mais genérico
            pattern = r'pub-\d+'
            match = re.search(pattern, url)

            if match:
                return match.group(0)

            logger.warning(
                "[AVISO] Não foi possível encontrar o publisher ID na URL")
            return ""

        except Exception as e:
            logger.error(f"[ERRO] Erro ao extrair publisher ID: {str(e)}")
            return ""

    def _capture_verification_code_from_page(self) -> bool:
        """
        Tenta capturar o código de verificação da página de onboarding.

        Returns:
            bool: True se capturou o código com sucesso
        """
        try:
            # Tentar encontrar o código de verificação na página
            # Isso pode variar dependendo da estrutura da página, então vamos tentar diferentes abordagens

            # Abordagem 1: Procurar por elementos que possam conter o código
            possible_selectors = [
                "//textarea[contains(@class, 'verification')]",
                "//code[contains(text(), '<meta')]",
                "//pre[contains(text(), '<meta')]",
                "//div[contains(@class, 'code')]",
                "//span[contains(text(), 'content=')]",
                "//div[contains(text(), 'meta name=')]",
                "//div[contains(@class, 'verification-code')]",
                "//div[contains(@class, 'site-verification')]",
                "//div[contains(@class, 'ads-txt-snippet')]",
                "//textarea[contains(@class, 'snippet')]",
                "//pre[contains(@class, 'snippet')]"
            ]

            for selector in possible_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        text = element.text or element.get_attribute(
                            "textContent")
                        if text and ("content=" in text or "<meta" in text or "ads.txt" in text.lower()):
                            self.verification_code = text.strip()
                            return True
                except Exception:
                    continue

            # Abordagem 2: Procurar no código-fonte da página
            page_source = self.driver.page_source

            # Procurar por meta tag de verificação
            meta_tag_pattern = r'<meta\s+name=["\']google-site-verification["\']\s+content=["\']([^"\']+)["\']'
            match = re.search(meta_tag_pattern, page_source)

            if match:
                self.verification_code = f'<meta name="google-site-verification" content="{match.group(1)}">'
                return True

            # Procurar por snippet ads.txt
            ads_txt_pattern = r'google\.com, pub-\d+, DIRECT, [a-zA-Z0-9]+'
            match = re.search(ads_txt_pattern, page_source)

            if match:
                self.verification_code = match.group(0)
                return True

            logger.warning(
                "[AVISO] Não foi possível encontrar o código de verificação na página")
            return False

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao capturar código de verificação: {str(e)}")
            return False

    def _capture_ads_txt_snippet(self) -> bool:
        """
        Tenta capturar especificamente o snippet do ads.txt após clicar no radio button.

        Returns:
            bool: True se capturou o snippet com sucesso
        """
        try:
            logger.info("[INFO] Tentando capturar o snippet do ads.txt...")

            # Esperar um momento para garantir que o snippet foi carregado
            time.sleep(2)

            # Tentar encontrar o snippet do ads.txt na página
            possible_selectors = [
                "//textarea[contains(@class, 'snippet')]",
                "//pre[contains(text(), 'google.com, pub-')]",
                "//code[contains(text(), 'google.com, pub-')]",
                "//div[contains(@class, 'ads-txt-snippet')]",
                "//div[contains(text(), 'google.com, pub-')]",
                "//span[contains(text(), 'google.com, pub-')]"
            ]

            for selector in possible_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        text = element.text or element.get_attribute(
                            "textContent")
                        if text and "google.com, pub-" in text:
                            # Extrair apenas a linha relevante do ads.txt
                            lines = text.strip().split("\n")
                            for line in lines:
                                if "google.com, pub-" in line:
                                    self.verification_code = line.strip()
                                    logger.info(
                                        f"[OK] Snippet do ads.txt capturado: {self.verification_code}")
                                    return True
                except Exception:
                    continue

            # Se não encontrou pelos seletores, procurar no código-fonte da página
            page_source = self.driver.page_source
            ads_txt_pattern = r'google\.com, pub-\d+, DIRECT, [a-zA-Z0-9]+'
            match = re.search(ads_txt_pattern, page_source)

            if match:
                self.verification_code = match.group(0)
                logger.info(
                    f"[OK] Snippet do ads.txt capturado do código-fonte: {self.verification_code}")
                return True

            logger.warning(
                "[AVISO] Não foi possível capturar o snippet do ads.txt")
            return False

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao capturar snippet do ads.txt: {str(e)}")
            return False

    def get_captured_data(self) -> Dict[str, str]:
        """
        Retorna os dados capturados em formato processado.

        Returns:
            Dict[str, str]: Dicionário com dados processados
        """
        # Obter o ID do publisher sem o prefixo "pub-"
        pub_id = ""
        if self.publisher_id and self.publisher_id.startswith("pub-"):
            pub_id = self.publisher_id.replace("pub-", "")

        # Extrair o ID direto do código ads.txt (último campo após as vírgulas)
        direct_id = ""
        if self.verification_code:
            parts = self.verification_code.split(",")
            if len(parts) >= 4:
                direct_id = parts[3].strip()

        return {
            # Original completo (para compatibilidade)
            "publisher_id": self.publisher_id,
            # Original completo (para compatibilidade)
            "verification_code": self.verification_code,
            "pub": pub_id,  # Apenas o número, sem "pub-"
            "direct": direct_id  # Apenas o ID direto
        }

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

    def _save_screenshot(self, name):
        """Salva screenshot para debug se DEBUG_MODE estiver ativo."""
        if not DEBUG_MODE:
            return

        try:
            # Criar diretório de screenshots se não existir
            screenshots_dir = os.path.join(
                "screenshots", "website_verification")
            os.makedirs(screenshots_dir, exist_ok=True)

            # Gerar nome de arquivo com timestamp
            filename = f"{screenshots_dir}/verification_{name}_{time.strftime('%Y%m%d_%H%M%S')}.png"

            # Salvar screenshot
            self.driver.save_screenshot(filename)
            logger.info(f"[DEBUG] Screenshot salvo em {filename}")
            # Adicionar o caminho do screenshot à lista
            self.screenshot_files.append(filename)
            return filename
        except Exception as e:
            logger.error(f"[ERRO] Falha ao salvar screenshot: {str(e)}")
            return None

    def export_captured_data(self, output_file: str = None) -> bool:
        """
        Exporta os dados capturados para um arquivo.

        Args:
            output_file: Caminho para o arquivo de saída. Se não fornecido, 
                        será gerado um nome baseado no publisher ID.

        Returns:
            bool: True se os dados foram exportados com sucesso
        """
        try:
            # Se não foi fornecido um arquivo de saída, criar um baseado no publisher ID
            if not output_file:
                # Criar diretório para os dados se não existir
                data_dir = os.path.join("data", "adsense")
                os.makedirs(data_dir, exist_ok=True)

                # Gerar nome do arquivo baseado no publisher ID e timestamp
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                if self.publisher_id:
                    output_file = f"{data_dir}/{self.publisher_id}_{timestamp}.txt"
                else:
                    output_file = f"{data_dir}/adsense_data_{timestamp}.txt"

            # Preparar os dados para exportação
            export_data = {
                "publisher_id": self.publisher_id,
                "verification_code": self.verification_code,
                "website_url": self.website_url,
                "capture_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

            # Exportar os dados para o arquivo
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(
                    f"# AdSense Data Captured on {export_data['capture_time']}\n\n")
                f.write(f"Publisher ID: {export_data['publisher_id']}\n")
                f.write(f"Website URL: {export_data['website_url']}\n")
                f.write(
                    f"Verification Code: {export_data['verification_code']}\n")

            logger.info(
                f"[OK] Dados exportados com sucesso para: {output_file}")
            return True

        except Exception as e:
            logger.error(f"[ERRO] Falha ao exportar dados: {str(e)}")
            return False

    def clean_screenshots(self):
        """Limpa screenshots no final da execução."""
        try:
            # Remover cada arquivo de screenshot da lista
            count = 0
            for screenshot_file in self.screenshot_files:
                try:
                    if os.path.exists(screenshot_file):
                        os.remove(screenshot_file)
                        count += 1
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Falha ao remover screenshot {screenshot_file}: {str(e)}")

            # Limpar a lista após remover os arquivos
            self.screenshot_files = []

            if count > 0:
                logger.info(f"[OK] {count} screenshots limpos com sucesso")
            return True
        except Exception as e:
            logger.error(f"[ERRO] Falha ao limpar screenshots: {str(e)}")
            return False
