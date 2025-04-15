import requests
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver
from dataclasses import dataclass
from typing import Optional, Dict, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class BrowserConfig:
    """Configurações do navegador."""
    headless: bool = False  # Por padrão, não usar modo headless
    max_wait_time: int = 30  # Tempo máximo de espera em segundos
    user_agent: Optional[str] = None  # User agent personalizado (opcional)
    proxy: Optional[Dict] = None  # Configurações de proxy (opcional)


class BrowserManager:
    """Gerencia as configurações e estados do navegador."""

    def __init__(self, ads_power_api):
        self.ads_power_api = ads_power_api
        self.browser_config = BrowserConfig()
        self.current_browser_info = None
        self.driver = None

    def set_config(self, config: BrowserConfig) -> None:
        """
        Define as configurações do navegador.

        Args:
            config: Instância de BrowserConfig com as configurações desejadas
        """
        self.browser_config = config
        logger.info(f"✅ Configurações do navegador atualizadas: {config}")

    def start_browser(self, user_id: str) -> Tuple[bool, Optional[Dict]]:
        """
        Inicia o navegador com as configurações definidas.

        Args:
            user_id: ID do perfil do AdsPower

        Returns:
            Tuple[bool, Optional[Dict]]: (Sucesso, Informações do navegador)
        """
        try:
            # Usar as configurações definidas
            success, browser_info = self.ads_power_api.start_browser(
                user_id=user_id,
                headless=self.browser_config.headless,
                max_wait_time=self.browser_config.max_wait_time
            )

            if success:
                self.current_browser_info = browser_info
                logger.info(
                    f"✅ Navegador iniciado com sucesso: {'(headless)' if self.browser_config.headless else '(normal)'}")
            else:
                logger.error("❌ Falha ao iniciar o navegador")

            return success, browser_info

        except Exception as e:
            logger.error(f"❌ Erro ao iniciar o navegador: {str(e)}")
            return False, None

    def close_browser(self, user_id: str) -> bool:
        """
        Fecha o navegador.

        Args:
            user_id: ID do perfil do AdsPower

        Returns:
            bool: True se o navegador foi fechado com sucesso
        """
        try:
            success = self.ads_power_api.close_browser(user_id)
            if success:
                self.current_browser_info = None
                logger.info("✅ Navegador fechado com sucesso")
            return success
        except Exception as e:
            logger.error(f"❌ Erro ao fechar o navegador: {str(e)}")
            return False

    def get_current_browser_info(self) -> Optional[Dict]:
        """
        Retorna as informações do navegador atual.

        Returns:
            Optional[Dict]: Informações do navegador ou None se não estiver em execução
        """
        return self.current_browser_info

    def is_browser_running(self) -> bool:
        """
        Verifica se o navegador está em execução.

        Returns:
            bool: True se o navegador estiver em execução
        """
        return self.current_browser_info is not None

    def ensure_browser_ready(self, user_id: str) -> bool:
        """
        Garante que o browser está pronto para uso.

        Args:
            user_id: ID do perfil do AdsPower

        Returns:
            bool: True se o browser está pronto para uso
        """
        try:
            if not self.is_browser_running():
                success, browser_info = self.start_browser(user_id)
                if not success:
                    logger.error("❌ Falha ao iniciar o browser")
                    return False

                # Tentar conectar ao Selenium
                selenium_ws = browser_info.get("selenium_ws")
                webdriver_path = browser_info.get("webdriver_path")

                if not selenium_ws or not webdriver_path:
                    logger.error("❌ Informações do WebDriver incompletas")
                    return False

                self.driver = connect_selenium(selenium_ws, webdriver_path)
                if not self.driver:
                    logger.error("❌ Falha ao conectar ao Selenium WebDriver")
                    return False

                logger.info("✅ Browser iniciado e conectado com sucesso")
                return True

            return True

        except Exception as e:
            logger.error(f"❌ Erro ao verificar estado do browser: {str(e)}")
            return False

    def get_driver(self) -> Optional[WebDriver]:
        """
        Retorna o driver do Selenium se disponível.

        Returns:
            Optional[WebDriver]: Driver do Selenium ou None se não estiver disponível
        """
        return self.driver


def start_browser(base_url, headers, user_id):
    """
    Inicia o navegador do AdsPower para um perfil específico e obtém o WebSocket do Selenium.

    Args:
        base_url (str): URL base da API do AdsPower.
        headers (dict): Cabeçalhos da requisição, incluindo autorização.
        user_id (str): ID do perfil no AdsPower.

    Returns:
        dict: Contém `selenium_ws` e `webdriver_path` se bem-sucedido, ou `None` em caso de erro.
    """
    # 1️⃣ Iniciar o navegador do perfil
    url_start = f"{base_url}/api/v1/browser/start?user_id={user_id}"
    response = requests.get(url_start, headers=headers)

    if response.status_code != 200:
        print(
            f"❌ Erro ao iniciar o navegador: {response.status_code} - {response.text}")
        return None

    try:
        response_json = response.json()
        if response_json.get("code") != 0:
            print(f"❌ Erro ao iniciar o navegador: {response_json.get('msg')}")
            return None
    except requests.exceptions.JSONDecodeError:
        print(f"❌ Erro ao converter resposta em JSON: {response.text}")
        return None

    print(
        f"🚀 Navegador iniciado para o perfil {user_id}. Aguardando WebDriver...")

    # 2️⃣ Aguardar até 15 segundos para obter WebSocket Selenium
    for tentativa in range(15):
        time.sleep(1.5)

        # Obter informações do navegador ativo
        browser_info = get_active_browser_info(base_url, headers, user_id)

        if browser_info["status"] == "success" and browser_info["selenium_ws"]:
            print(
                f"✅ WebSocket Selenium obtido: {browser_info['selenium_ws']}")
            print(f"✅ Caminho do WebDriver: {browser_info['webdriver_path']}")
            return browser_info  # Retorna WebSocket Selenium e caminho do WebDriver

        print(
            f"⚠️ Tentativa {tentativa + 1}: WebDriver ainda não disponível...")

    print("❌ Não foi possível obter o WebSocket do Selenium.")
    return None


def stop_browser(base_url, headers, user_id):
    """
    Fecha o navegador do AdsPower para um perfil específico.

    Args:
        base_url (str): URL base da API do AdsPower.
        headers (dict): Cabeçalhos da requisição, incluindo autorização.
        user_id (str): ID do perfil no AdsPower.

    Returns:
        bool: True se o navegador foi fechado com sucesso, False caso contrário.

    url_stop = f"{base_url}/api/v1/browser/stop?user_id={user_id}"
    response = requests.get(url_stop, headers=headers)

    if response.status_code != 200:
        print(f"❌ Erro ao fechar o navegador: {response.status_code} - {response.text}")
        return False

    try:
        response_json = response.json()
        if response_json.get("code") != 0:
            print(f"❌ Erro ao fechar o navegador: {response_json.get('msg')}")
            return False
    except requests.exceptions.JSONDecodeError:
        print(f"❌ Erro ao converter resposta em JSON: {response.text}")
        return False

    print(f"✅ Navegador do perfil {user_id} fechado com sucesso!")
    return True
    """


def get_active_browser_info(base_url, headers, user_id):
    """
    Obtém informações do navegador ativo no AdsPower para um perfil específico.

    Args:
        base_url (str): URL base da API do AdsPower.
        headers (dict): Cabeçalhos da requisição.
        user_id (str): ID do perfil no AdsPower.

    Returns:
        dict: Contém `selenium_ws` e `webdriver_path`, ou `None` se não encontrado.
    """
    url = f"{base_url}/api/v1/browser/local-active"
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return {"status": "error", "message": f"Erro ao verificar navegadores ativos: {response.status_code} - {response.text}"}

    try:
        response_json = response.json()
    except requests.exceptions.JSONDecodeError:
        return {"status": "error", "message": "Erro ao converter resposta para JSON."}

    if response_json.get("code") != 0:
        return {"status": "error", "message": response_json.get("msg", "Erro desconhecido.")}

    # 🔍 Buscar o navegador correspondente ao user_id
    for browser in response_json.get("data", {}).get("list", []):
        if browser.get("user_id") == user_id:
            return {
                "status": "success",
                "selenium_ws": browser.get("ws", {}).get("selenium"),
                "webdriver_path": browser.get("webdriver")
            }

    return {"status": "error", "message": "Nenhum navegador ativo encontrado para este perfil."}


def connect_selenium(selenium_ws, webdriver_path):
    """
    Conecta ao WebDriver do AdsPower.

    Args:
        selenium_ws (str): Endereço WebSocket do Selenium.
        webdriver_path (str): Caminho do WebDriver.

    Returns:
        WebDriver: Instância do Selenium WebDriver conectada.
    """
    try:
        service = Service(executable_path=webdriver_path)
        options = webdriver.ChromeOptions()
        options.add_experimental_option("debuggerAddress", selenium_ws)

        driver = webdriver.Chrome(service=service, options=options)
        print("✅ Conectado ao WebDriver Selenium do AdsPower!")
        return driver
    except Exception as e:
        print(f"❌ Erro ao conectar ao WebDriver: {e}")
        return None
