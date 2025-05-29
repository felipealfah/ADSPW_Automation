import requests
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver
from dataclasses import dataclass
from typing import Optional, Dict, Tuple, Set
import logging
import threading

logger = logging.getLogger(__name__)


@dataclass
class BrowserConfig:
    """Configurações do navegador."""
    headless: bool = False  # Por padrão, não usar modo headless
    max_wait_time: int = 180  # Tempo máximo de espera em segundos (aumentado para 3 minutos)
    user_agent: Optional[str] = None  # User agent personalizado (opcional)
    proxy: Optional[Dict] = None  # Configurações de proxy (opcional)


class BrowserPool:
    """Gerencia um pool de navegadores."""
    
    def __init__(self, max_browsers: int = 5):
        self.max_browsers = max_browsers
        self.active_browsers: Dict[str, Dict] = {}  # user_id -> browser_info
        self.last_used: Dict[str, float] = {}  # user_id -> timestamp
        self.lock = threading.Lock()
    
    def add_browser(self, user_id: str, browser_info: Dict) -> bool:
        """Adiciona um navegador ao pool."""
        with self.lock:
            if len(self.active_browsers) >= self.max_browsers:
                # Remover navegador menos usado se necessário
                self._cleanup_least_used()
            
            if user_id not in self.active_browsers:
                self.active_browsers[user_id] = browser_info
                self.last_used[user_id] = time.time()
                return True
            return False
    
    def get_browser(self, user_id: str) -> Optional[Dict]:
        """Obtém informações de um navegador do pool."""
        with self.lock:
            browser = self.active_browsers.get(user_id)
            if browser:
                self.last_used[user_id] = time.time()
            return browser
    
    def remove_browser(self, user_id: str) -> bool:
        """Remove um navegador do pool."""
        with self.lock:
            if user_id in self.active_browsers:
                del self.active_browsers[user_id]
                del self.last_used[user_id]
                return True
            return False
    
    def _cleanup_least_used(self) -> None:
        """Remove o navegador menos usado recentemente."""
        if not self.last_used:
            return
            
        oldest_user_id = min(self.last_used.items(), key=lambda x: x[1])[0]
        self.remove_browser(oldest_user_id)


class BrowserManager:
    """Gerencia as configurações e estados do navegador."""

    def __init__(self, ads_power_api):
        """
        Inicializa o gerenciador de browser.

        Args:
            ads_power_api: Instância do AdsPowerManager
        """
        self.ads_power_api = ads_power_api
        self.browser_config = BrowserConfig(max_wait_time=180)  # Definir timeout de 3 minutos por padrão
        self.current_browser_info = None
        self.driver = None
        self.browser_pool = BrowserPool()  # Adicionar pool de navegadores

    def set_config(self, config: BrowserConfig) -> None:
        """
        Define as configurações do navegador.

        Args:
            config: Instância de BrowserConfig com as configurações desejadas
        """
        self.browser_config = config
        logger.info(f"[OK] Configurações do navegador atualizadas: {config}")

    def start_browser(self, user_id: str) -> Tuple[bool, Optional[Dict]]:
        """
        Inicia o navegador com as configurações definidas.

        Args:
            user_id: ID do perfil do AdsPower

        Returns:
            Tuple[bool, Optional[Dict]]: (Sucesso, Informações do navegador)
        """
        try:
            # Verificar se já existe no pool
            browser_info = self.browser_pool.get_browser(user_id)
            if browser_info:
                self.current_browser_info = browser_info
                logger.info(f"[OK] Navegador recuperado do pool para perfil {user_id}")
                return True, browser_info

            # Usar as configurações definidas
            logger.info(f"[DEBUG] Iniciando browser com timeout de {self.browser_config.max_wait_time}s")
            success, browser_info = self.ads_power_api.start_browser(
                user_id=user_id,
                headless=self.browser_config.headless,
                max_wait_time=self.browser_config.max_wait_time
            )

            if success:
                self.current_browser_info = browser_info
                # Adicionar ao pool
                self.browser_pool.add_browser(user_id, browser_info)
                logger.info(f"[OK] Navegador iniciado e adicionado ao pool: {'(headless)' if self.browser_config.headless else '(normal)'}")
            else:
                logger.error("[ERRO] Falha ao iniciar o navegador")

            return success, browser_info

        except Exception as e:
            logger.error(f"[ERRO] Erro ao iniciar o navegador: {str(e)}")
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
                # Remover do pool
                self.browser_pool.remove_browser(user_id)
                logger.info("[OK] Navegador fechado e removido do pool")
            return success
        except Exception as e:
            logger.error(f"[ERRO] Erro ao fechar o navegador: {str(e)}")
            return False

    def get_current_browser_info(self) -> Optional[Dict]:
        """
        Retorna as informações do navegador atual.

        Returns:
            Optional[Dict]: Informações do navegador ou None se não estiver em execução
        """
        try:
            if not self.current_browser_info:
                logger.warning("[AVISO] Nenhuma informação de browser disponível")
                return None

            # Verificar se temos as informações necessárias
            selenium_ws = self.current_browser_info.get("selenium_ws")
            webdriver_path = self.current_browser_info.get("webdriver_path")

            if not selenium_ws or not webdriver_path:
                logger.warning("[AVISO] Informações de websocket ou webdriver ausentes no browser_info")
                logger.debug(f"browser_info atual: {self.current_browser_info}")
                return None

            logger.info("[OK] Informações do browser recuperadas com sucesso")
            return self.current_browser_info

        except Exception as e:
            logger.error(f"[ERRO] Erro ao obter informações do browser: {str(e)}")
            return None

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
            logger.info(f"[DEBUG] Verificando se o browser está pronto para o perfil {user_id}")
            
            # Verificar se o perfil existe antes de tentar iniciar o browser
            if not self.ads_power_api.is_profile_valid(user_id):
                logger.error(f"[ERRO] Perfil {user_id} não existe ou não está disponível no AdsPower")
                return False
            
            # Se o browser já estiver rodando, verificar se está realmente acessível
            if self.is_browser_running():
                logger.info(f"[DEBUG] Browser parece estar rodando, verificando se está realmente acessível")
                
                # Tentar obter o driver atual
                current_driver = self.get_driver()
                if current_driver:
                    try:
                        # Tentar uma operação simples para verificar se o driver está responsivo
                        current_driver.current_url
                        logger.info(f"[OK] Browser está rodando e acessível para o perfil {user_id}")
                        return True
                    except Exception as e:
                        logger.warning(f"[AVISO] Browser parece estar rodando mas não está acessível: {str(e)}")
                        # Limpar o driver atual
                        self.driver = None
                        self.current_browser_info = None
                
            # Se chegou aqui, precisamos iniciar um novo browser
            logger.info(f"[DEBUG] Browser não está em execução, iniciando para o perfil {user_id}")
            success, browser_info = self.start_browser(user_id)
            
            if not success:
                logger.error("[ERRO] Falha ao iniciar o browser")
                return False

            # Tentar conectar ao Selenium
            selenium_ws = browser_info.get("selenium_ws")
            webdriver_path = browser_info.get("webdriver_path")

            if not selenium_ws or not webdriver_path:
                logger.error("[ERRO] Informações do browser incompletas")
                return False

            # Tentar conectar ao WebDriver
            max_retries = 3
            retry_delay = 5
            
            for attempt in range(max_retries):
                try:
                    logger.info(f"[DEBUG] Tentativa {attempt + 1} de conectar ao WebDriver")
                    service = Service(executable_path=webdriver_path)
                    options = Options()
                    options.add_experimental_option("debuggerAddress", selenium_ws)
                    
                    self.driver = webdriver.Chrome(service=service, options=options)
                    
                    # Verificar se o driver está funcionando
                    self.driver.current_url
                    logger.info("[OK] WebDriver conectado e funcionando")
                    return True
                    
                except Exception as e:
                    logger.warning(f"[AVISO] Tentativa {attempt + 1} falhou: {str(e)}")
                    if attempt < max_retries - 1:
                        logger.info(f"[INFO] Aguardando {retry_delay}s antes da próxima tentativa...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        logger.error("[ERRO] Todas as tentativas de conectar ao WebDriver falharam")
                        return False

            return False

        except Exception as e:
            logger.error(f"[ERRO] Erro ao garantir que o browser está pronto: {str(e)}")
            return False

    def get_driver(self) -> Optional[WebDriver]:
        """
        Retorna o driver do Selenium se disponível e funcional.

        Returns:
            Optional[WebDriver]: Driver do Selenium ou None se não estiver disponível ou funcional
        """
        try:
            if not self.driver:
                logger.warning("[AVISO] Driver não está inicializado")
                return None

            # Tentar uma operação simples para verificar se o driver está responsivo
            try:
                # Tentar acessar uma propriedade do driver para verificar se está funcional
                _ = self.driver.current_url
                return self.driver
            except Exception as e:
                logger.warning(f"[AVISO] Driver não está respondendo: {str(e)}")
                # Limpar o driver que não está funcionando
                self.driver = None
                return None

        except Exception as e:
            logger.error(f"[ERRO] Erro ao verificar estado do driver: {str(e)}")
            return None


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
    # 1⃣ Iniciar o navegador do perfil
    url_start = f"{base_url}/api/v1/browser/start?user_id={user_id}"
    response = requests.get(url_start, headers=headers)

    if response.status_code != 200:
        print(
            f"[ERRO] Erro ao iniciar o navegador: {response.status_code} - {response.text}")
        return None

    try:
        response_json = response.json()
        if response_json.get("code") != 0:
            print(
                f"[ERRO] Erro ao iniciar o navegador: {response_json.get('msg')}")
            return None
    except requests.exceptions.JSONDecodeError:
        print(f"[ERRO] Erro ao converter resposta em JSON: {response.text}")
        return None

    print(
        f"[INICIO] Navegador iniciado para o perfil {user_id}. Aguardando WebDriver...")

    # 2⃣ Aguardar até 15 segundos para obter WebSocket Selenium
    for tentativa in range(15):
        time.sleep(1.5)

        # Obter informações do navegador ativo
        browser_info = get_active_browser_info(base_url, headers, user_id)

        if browser_info["status"] == "success" and browser_info["selenium_ws"]:
            print(
                f"[OK] WebSocket Selenium obtido: {browser_info['selenium_ws']}")
            print(
                f"[OK] Caminho do WebDriver: {browser_info['webdriver_path']}")
            return browser_info  # Retorna WebSocket Selenium e caminho do WebDriver

        print(
            f"[AVISO] Tentativa {tentativa + 1}: WebDriver ainda não disponível...")

    print("[ERRO] Não foi possível obter o WebSocket do Selenium.")
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
        print(f"[ERRO] Erro ao fechar o navegador: {response.status_code} - {response.text}")
        return False

    try:
        response_json = response.json()
        if response_json.get("code") != 0:
            print(f"[ERRO] Erro ao fechar o navegador: {response_json.get('msg')}")
            return False
    except requests.exceptions.JSONDecodeError:
        print(f"[ERRO] Erro ao converter resposta em JSON: {response.text}")
        return False

    print(f"[OK] Navegador do perfil {user_id} fechado com sucesso!")
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

    # [BUSCA] Buscar o navegador correspondente ao user_id
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
        print("[OK] Conectado ao WebDriver Selenium do AdsPower!")
        return driver
    except Exception as e:
        print(f"[ERRO] Erro ao conectar ao WebDriver: {e}")
        return None
