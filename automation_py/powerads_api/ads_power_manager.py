from credentials.credentials_manager import get_credential
import requests
import time
import logging
from typing import Dict, List, Optional, Tuple
import json
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import sys
from datetime import datetime, timedelta

# Adicionar o diretório pai ao path para importar módulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

class RateLimiter:
    """Controla o rate limiting das requisições à API."""
    
    def __init__(self, requests_per_second=0.5):  # Reduzido para 1 requisição a cada 2 segundos
        self.requests_per_second = requests_per_second
        self.last_request = datetime.now() - timedelta(seconds=1)
    
    def wait_if_needed(self):
        """Aguarda se necessário para respeitar o rate limit."""
        now = datetime.now()
        time_since_last = (now - self.last_request).total_seconds()
        if time_since_last < (1.0 / self.requests_per_second):
            sleep_time = (1.0 / self.requests_per_second) - time_since_last
            time.sleep(sleep_time)
        self.last_request = datetime.now()

class AdsPowerManager:
    """
    Gerencia a integração com AdsPower, incluindo verificações de saúde
    e gerenciamento de múltiplos navegadores.
    """

    def __init__(self, base_url=None, api_key=None, local_cache_path="credentials/adspower_cache.json"):
        """
        Inicializa o gerenciador AdsPower.

        Args:
            base_url: URL base da API do AdsPower (opcional, se não fornecido, será obtido das credenciais)
            api_key: Chave da API do AdsPower (opcional, se não fornecido, será obtido das credenciais)
            local_cache_path: Caminho para o cache local
        """
        # Inicializar atributos básicos primeiro
        self.base_url = None
        self.api_key = None
        self.local_cache_path = local_cache_path
        self.active_browsers = {}
        
        # Inicializar cache após definir local_cache_path
        self.cache = self._load_cache()

        # Prioridade 1: Obter credenciais do arquivo de credenciais
        cred_base_url = get_credential("PA_BASE_URL")
        cred_api_key = get_credential("PA_API_KEY")

        # Definir base_url
        if cred_base_url:
            self.base_url = cred_base_url
            logger.info(f"Usando PA_BASE_URL das credenciais: {self.base_url}")
        elif base_url:
            self.base_url = base_url
            logger.info(f"Usando base_url do parâmetro: {self.base_url}")
        elif os.environ.get('ADSPOWER_API_URL'):
            self.base_url = os.environ.get('ADSPOWER_API_URL')
            logger.info(f"Usando base_url da variável de ambiente: {self.base_url}")
        else:
            logger.info("Base URL não fornecido, tentando detecção automática...")
            self._find_best_connection()

        # Definir api_key
        if cred_api_key:
            self.api_key = cred_api_key
            logger.info("Usando PA_API_KEY das credenciais")
        elif api_key:
            self.api_key = api_key
            logger.info("Usando api_key do parâmetro")
        elif os.environ.get('ADSPOWER_API_KEY'):
            self.api_key = os.environ.get('ADSPOWER_API_KEY')
            logger.info("Usando api_key da variável de ambiente")
        else:
            logger.warning("Nenhuma API key fornecida")

        # Verificar conexão com a URL configurada
        self._check_connection()

        self.rate_limiter = RateLimiter(requests_per_second=2)  # Limita a 2 requisições por segundo

    def _find_best_connection(self):
        """Testa múltiplos endereços para encontrar o melhor para conectar ao AdsPower."""
        possible_urls = [
            "http://local.adspower.net:50325",
            "http://localhost:50325",
            "http://127.0.0.1:50325"
        ]

        # Adiciona endereço IP do host se disponível (via variável de ambiente)
        if os.environ.get('HOST_IP'):
            possible_urls.insert(
                0, f"http://{os.environ.get('HOST_IP')}:50325")

        logger.info("Testando múltiplos endereços para conectar ao AdsPower...")

        # Tentativa com retries
        max_retries = 3  # Número máximo de tentativas para cada URL

        for url in possible_urls:
            for attempt in range(max_retries):
                try:
                    logger.info(
                        f"Testando conexão com: {url} (tentativa {attempt+1}/{max_retries})")
                    response = requests.get(f"{url}/status", timeout=10)
                    if response.status_code == 200:
                        self.base_url = url
                        logger.info(f"[OK] Conexão bem-sucedida com: {url}")
                        return
                    else:
                        logger.warning(
                            f"Resposta não-200 de {url}: {response.status_code}")
                        # Se não for a última tentativa, aguarde antes de tentar novamente
                        if attempt < max_retries - 1:
                            time.sleep(2)  # Espera 2 segundos entre tentativas
                except Exception as e:
                    logger.warning(f"[ERRO] Falha ao conectar em {url}: {str(e)}")
                    # Se não for a última tentativa, aguarde antes de tentar novamente
                    if attempt < max_retries - 1:
                        time.sleep(2)  # Espera 2 segundos entre tentativas

        # Se nenhum funcionou, use um padrão
        self.base_url = "http://local.adspower.net:50325"
        logger.warning(
            f"[AVISO] Nenhuma conexão bem-sucedida após {max_retries} tentativas para cada URL. Usando padrão: {self.base_url}")

    def _check_connection(self):
        """Verifica a conexão com o AdsPower."""
        try:
            # Tente uma requisição simples para verificar a conectividade
            response = requests.get(f"{self.base_url}/status", timeout=10)
            if response.status_code == 200:
                logger.info(f"[OK] Conectado ao AdsPower em {self.base_url}")
            else:
                logger.warning(
                    f"[AVISO] AdsPower respondeu com status {response.status_code}")

                # Se a conexão falhar, tente outros endereços
                if not self.base_url.startswith("http://local.adspower.net"):
                    # Tente local.adspower.net se ainda não tentou
                    try:
                        alt_url = "http://local.adspower.net:50325"
                        logger.info(
                            f"Tentando conexão alternativa com: {alt_url}")
                        alt_response = requests.get(
                            f"{alt_url}/status", timeout=10)
                        if alt_response.status_code == 200:
                            self.base_url = alt_url
                            logger.info(
                                f"[OK] Conexão alternativa bem-sucedida com: {alt_url}")
                    except Exception:
                        logger.warning("[ERRO] Conexão alternativa também falhou")

        except Exception as e:
            logger.error(f"[ERRO] Erro ao conectar ao AdsPower: {str(e)}")
            logger.error(f"   URL tentada: {self.base_url}")
            logger.error(
                "   Verifique se o AdsPower está instalado e em execução no sistema host.")

            # Se a conexão falhar, tente outros endereços
            if not self.base_url.startswith("http://local.adspower.net"):
                # Tente local.adspower.net se ainda não tentou
                try:
                    alt_url = "http://local.adspower.net:50325"
                    logger.info(f"Tentando conexão alternativa com: {alt_url}")
                    alt_response = requests.get(
                        f"{alt_url}/status", timeout=10)
                    if alt_response.status_code == 200:
                        self.base_url = alt_url
                        logger.info(
                            f"[OK] Conexão alternativa bem-sucedida com: {alt_url}")
                except Exception:
                    logger.warning("[ERRO] Conexão alternativa também falhou")

    def _load_cache(self) -> Dict:
        """Carrega o cache local de informações do AdsPower."""
        try:
            if os.path.exists(self.local_cache_path):
                with open(self.local_cache_path, 'r') as f:
                    return json.load(f)
            return {
                "profiles": {},
                "last_updated": 0,
                "service_status": {
                    "available": False,
                    "last_checked": 0
                }
            }
        except Exception as e:
            logger.warning(f"[AVISO] Erro ao carregar cache do AdsPower: {str(e)}")
            return {
                "profiles": {},
                "last_updated": 0,
                "service_status": {
                    "available": False,
                    "last_checked": 0
                }
            }

    def _save_cache(self):
        """Salva o cache local."""
        try:
            os.makedirs(os.path.dirname(self.local_cache_path), exist_ok=True)
            with open(self.local_cache_path, 'w') as f:
                json.dump(self.cache, f, indent=4)
        except Exception as e:
            logger.warning(f"[AVISO] Erro ao salvar cache do AdsPower: {str(e)}")

    def check_api_health(self, force_check=False) -> bool:
        """
        Verifica se a API do AdsPower está respondendo corretamente.

        Args:
            force_check: Se True, força uma nova verificação mesmo que tenha verificado recentemente

        Returns:
            bool: True se a API está saudável, False caso contrário
        """
        current_time = time.time()
        cache_time = 5 * 60  # 5 minutos

        # Usar cache se foi verificado recentemente
        if not force_check and (current_time - self.cache["service_status"]["last_checked"]) < cache_time:
            return self.cache["service_status"]["available"]

        try:
            # Realizar verificação simples - listar grupos
            url = f"{self.base_url}/api/v1/group/list"
            response = requests.get(
                url, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=20)

            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    # API está saudável
                    self.cache["service_status"]["available"] = True
                    self.cache["service_status"]["last_checked"] = current_time
                    self._save_cache()
                    logger.info("[OK] API do AdsPower está saudável")
                    return True

            # API não está saudável
            self.cache["service_status"]["available"] = False
            self.cache["service_status"]["last_checked"] = current_time
            self._save_cache()
            logger.warning(
                f"[AVISO] API do AdsPower não está respondendo corretamente: {response.status_code}")
            return False

        except Exception as e:
            # Erro na verificação
            self.cache["service_status"]["available"] = False
            self.cache["service_status"]["last_checked"] = current_time
            self._save_cache()
            logger.error(
                f"[ERRO] Erro ao verificar saúde da API do AdsPower: {str(e)}")
            return False

    def get_all_profiles(self, force_refresh=False, include_no_group=True, group_id=None, max_retries=3, retry_delay=2) -> List[Dict]:
        """
        Obtém todos os perfis do AdsPower.

        Args:
            force_refresh (bool): Se True, força uma atualização do cache
            include_no_group (bool): Se True, inclui perfis sem grupo
            group_id (str): ID do grupo específico para filtrar
            max_retries (int): Número máximo de tentativas para obter os perfis
            retry_delay (int): Tempo de espera entre tentativas em segundos

        Returns:
            List[Dict]: Lista de perfis
        """
        for attempt in range(max_retries):
            try:
                # Verificar cache primeiro
                cache_age = time.time() - self.cache.get("last_updated", 0)
                if not force_refresh and cache_age < 300:  # Cache válido por 5 minutos
                    cached_profiles = self.cache.get("profiles", {})
                    if cached_profiles:
                        logger.info(f"[INFO] Usando {len(cached_profiles)} perfis do cache")
                        return list(cached_profiles.values())

                # Respeitar rate limit
                self.rate_limiter.wait_if_needed()

                # Usar API v1 para listar perfis
                url = f"{self.base_url}/api/v1/user/list"
                params = {
                    "page": 1,
                    "page_size": 100
                }
                
                if group_id:
                    params["group_id"] = group_id

                logger.info(f"[INFO] Tentativa {attempt + 1}/{max_retries} de obter perfis")
                response = requests.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                if data.get("code") == 0 and "data" in data:
                    all_profiles = data["data"].get("list", [])
                    logger.info(f"[INFO] Total de perfis encontrados: {len(all_profiles)}")
                    
                    # Filtrar perfis baseado no parâmetro include_no_group
                    if not include_no_group:
                        profiles = [p for p in all_profiles if p.get('group_id') != '0' and p.get('group_name')]
                        logger.info(f"[INFO] Perfis com grupo: {len(profiles)}")
                    else:
                        profiles = all_profiles
                        logger.info("[INFO] Incluindo todos os perfis (com e sem grupo)")
                    
                    # Log detalhado dos perfis encontrados
                    profile_ids = [p.get("user_id") for p in profiles]
                    logger.info(f"[DEBUG] IDs dos perfis encontrados: {profile_ids}")

                    # Atualizar cache
                    self.cache["profiles"] = {p["user_id"]: p for p in profiles}
                    self.cache["last_updated"] = time.time()
                    self._save_cache()

                    return profiles
                else:
                    logger.error(f"[ERRO] Resposta inesperada da API: {data}")
                    if attempt < max_retries - 1:
                        logger.info(f"[INFO] Aguardando {retry_delay}s antes da próxima tentativa...")
                        time.sleep(retry_delay)
                        continue
                    return []

            except requests.exceptions.RequestException as e:
                logger.error(f"[ERRO] Erro ao buscar perfis (tentativa {attempt + 1}): {str(e)}")
                if attempt < max_retries - 1:
                    logger.info(f"[INFO] Aguardando {retry_delay}s antes da próxima tentativa...")
                    time.sleep(retry_delay)
                    continue
                # Se falhar todas as tentativas, tentar usar cache mesmo que expirado
                cached_profiles = self.cache.get("profiles", {})
                if cached_profiles:
                    logger.warning(f"[AVISO] Usando {len(cached_profiles)} perfis do cache expirado")
                    return list(cached_profiles.values())
                return []

        return []

    def get_profile_info(self, user_id: str) -> Optional[Dict]:
        """
        Obtém informações de um perfil específico.

        Args:
            user_id: ID do perfil

        Returns:
            Dict: Informações do perfil ou None se não encontrado
        """
        # Tentar usar cache primeiro
        if user_id in self.cache["profiles"]:
            return self.cache["profiles"][user_id]

        # Se não estiver no cache, buscar da API
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/user/info",
                headers={"Authorization": f"Bearer {self.api_key}"},
                params={"user_id": user_id},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0 and "data" in data:
                    # Atualizar cache
                    self.cache["profiles"][user_id] = data["data"]
                    self._save_cache()
                    return data["data"]

            logger.warning(f"[AVISO] Perfil {user_id} não encontrado na API")
            return None

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao buscar informações do perfil {user_id}: {str(e)}")
            return None

    def is_browser_running(self, user_id: str) -> bool:
        """
        Verifica se um navegador para o perfil está em execução.

        Args:
            user_id: ID do perfil

        Returns:
            bool: True se o navegador está em execução, False caso contrário
        """
        # Verificar cache local primeiro
        if user_id in self.active_browsers:
            return True

        # Verificar na API do AdsPower
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/browser/active",
                headers={"Authorization": f"Bearer {self.api_key}"},
                params={"user_id": user_id},
                timeout=20
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("data", {}).get("status") == "Active"

            return False

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao verificar status do navegador para {user_id}: {str(e)}")
            return False

    def start_browser(self, user_id: str, headless: bool = False, max_wait_time: int = 60) -> Tuple[bool, Optional[Dict]]:
        """
        Inicia o navegador para um perfil específico.

        Args:
            user_id (str): ID do perfil
            headless (bool): Se True, inicia em modo headless
            max_wait_time (int): Tempo máximo de espera em segundos

        Returns:
            Tuple[bool, Optional[Dict]]: (Sucesso, Informações do navegador)
        """
        try:
            # Verificar se o perfil é válido
            if not self.is_profile_valid(user_id):
                logger.error(f"[ERRO] Perfil {user_id} não é válido")
                return False, None

            # Verificar se o navegador já está rodando
            if self.is_browser_running(user_id):
                logger.info(f"[INFO] Navegador já está rodando para perfil {user_id}")
                browser_info = self.get_browser_info(user_id)
                if browser_info:
                    return True, browser_info
                else:
                    # Se não conseguiu obter as informações, tentar parar e reiniciar
                    logger.info(f"[INFO] Tentando parar e reiniciar o navegador para perfil {user_id}")
                    self.stop_browser(user_id)
                    time.sleep(5)  # Aguardar um pouco antes de reiniciar

            # Iniciar o navegador
            self.rate_limiter.wait_if_needed()
            url = f"{self.base_url}/api/v1/browser/start"
            params = {
                "user_id": user_id,
                "headless": "true" if headless else "false"
            }
            
            logger.info(f"[INFO] Enviando requisição para iniciar navegador: {url}")
            response = requests.get(url, params=params)
            if response.status_code != 200:
                logger.error(f"[ERRO] Falha ao iniciar navegador: HTTP {response.status_code}")
                return False, None

            data = response.json()
            if data.get("code") != 0:
                logger.error(f"[ERRO] Falha ao iniciar navegador: {data.get('msg', 'Erro desconhecido')}")
                return False, None

            # Aguardar o navegador iniciar com verificações periódicas
            start_time = time.time()
            check_interval = 5  # Verificar a cada 5 segundos
            last_check_time = start_time

            while time.time() - start_time < max_wait_time:
                current_time = time.time()
                
                # Verificar status apenas a cada check_interval segundos
                if current_time - last_check_time >= check_interval:
                    logger.info(f"[INFO] Verificando status do navegador... (Tempo decorrido: {int(current_time - start_time)}s)")
                    
                    # Tentar obter informações do browser
                    browser_info = self.get_browser_info(user_id)
                    
                    if browser_info:
                        selenium_ws = browser_info.get("selenium_ws")
                        webdriver_path = browser_info.get("webdriver_path")
                        
                        if selenium_ws and webdriver_path:
                            # Tentar uma conexão de teste com o Selenium
                            try:
                                service = Service(executable_path=webdriver_path)
                                options = Options()
                                options.add_experimental_option("debuggerAddress", selenium_ws)
                                test_driver = webdriver.Chrome(service=service, options=options)
                                
                                # Tentar acessar uma propriedade para verificar se está realmente conectado
                                _ = test_driver.current_url
                                
                                logger.info(f"[OK] Navegador iniciado e testado para perfil {user_id}")
                                logger.info(f"[DEBUG] selenium_ws: {selenium_ws}")
                                logger.info(f"[DEBUG] webdriver_path: {webdriver_path}")
                                return True, browser_info
                            except Exception as e:
                                logger.warning(f"[AVISO] Browser info encontrado mas conexão falhou: {str(e)}")
                        else:
                            logger.warning("[AVISO] Browser info incompleto, continuando a aguardar...")
                    
                    last_check_time = current_time
                
                time.sleep(1)  # Pequena pausa entre verificações

            logger.error(f"[ERRO] Timeout ao aguardar navegador iniciar para perfil {user_id}")
            logger.error(f"[DEBUG] Tempo máximo de espera ({max_wait_time}s) excedido")
            return False, None

        except Exception as e:
            logger.error(f"[ERRO] Erro ao iniciar navegador: {str(e)}")
            return False, None

    def stop_browser(self, user_id: str) -> bool:
        """
        Para o navegador de um perfil.

        Args:
            user_id: ID do perfil

        Returns:
            bool: True se o navegador foi parado com sucesso, False caso contrário
        """
        try:
            url_stop = f"{self.base_url}/api/v1/browser/stop?user_id={user_id}"
            response = requests.get(
                url_stop, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=20)

            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    # Remover do cache de navegadores ativos
                    if user_id in self.active_browsers:
                        del self.active_browsers[user_id]

                    logger.info(
                        f"[OK] Navegador para perfil {user_id} parado com sucesso")
                    return True

            logger.warning(
                f"[AVISO] Falha ao parar navegador para perfil {user_id}")
            return False

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao parar navegador para perfil {user_id}: {str(e)}")
            return False

    def close_browser(self, user_id: str) -> bool:
        """
        Fecha o navegador de um perfil.

        Args:
            user_id: ID do perfil

        Returns:
            bool: True se o navegador foi fechado com sucesso, False caso contrário
        """
        try:
            url_stop = f"{self.base_url}/api/v1/browser/stop?user_id={user_id}"
            response = requests.get(
                url_stop, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=20)

            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    # Remover do cache de navegadores ativos
                    if user_id in self.active_browsers:
                        del self.active_browsers[user_id]

                    logger.info(
                        f"[OK] Navegador para perfil {user_id} fechado com sucesso")
                    return True

            logger.warning(
                f"[AVISO] Falha ao fechar navegador para perfil {user_id}")
            return False

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao fechar navegador para perfil {user_id}: {str(e)}")
            return False

    def get_browser_info(self, user_id: str) -> Optional[Dict]:
        """
        Obtém informações do navegador para um perfil específico.

        Args:
            user_id (str): ID do perfil

        Returns:
            Optional[Dict]: Informações do navegador ou None se não encontrado
        """
        try:
            self.rate_limiter.wait_if_needed()
            
            # Primeiro tentar obter via API local (mais rápido e confiável)
            url = f"{self.base_url}/api/v1/browser/active"
            params = {"user_id": user_id}
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0 and data.get("data"):
                    browser_data = data["data"]
                    # Extrair informações do websocket e webdriver
                    if browser_data.get("ws"):
                        selenium_ws = browser_data["ws"].get("selenium")
                        webdriver_path = browser_data.get("webdriver")
                        
                        if selenium_ws and webdriver_path:
                            logger.info(f"[DEBUG] Browser info obtido via API local")
                            logger.info(f"[DEBUG] selenium_ws: {selenium_ws}")
                            logger.info(f"[DEBUG] webdriver_path: {webdriver_path}")
                            return {
                                "selenium_ws": selenium_ws,
                                "webdriver_path": webdriver_path,
                                "status": browser_data.get("status", "Unknown")
                            }
            
            # Se não conseguiu via API local, tentar via API de browser local
            url = f"{self.base_url}/api/v1/browser/local-active"
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0 and data.get("data", {}).get("list"):
                    # Procurar o browser específico na lista
                    for browser in data["data"]["list"]:
                        if browser.get("user_id") == user_id:
                            selenium_ws = browser.get("ws", {}).get("selenium")
                            webdriver_path = browser.get("webdriver")
                            
                            if selenium_ws and webdriver_path:
                                logger.info(f"[DEBUG] Browser info obtido via API local-active")
                                logger.info(f"[DEBUG] selenium_ws: {selenium_ws}")
                                logger.info(f"[DEBUG] webdriver_path: {webdriver_path}")
                                return {
                                    "selenium_ws": selenium_ws,
                                    "webdriver_path": webdriver_path,
                                    "status": browser.get("status", "Unknown")
                                }
            
            logger.warning(f"[AVISO] Não foi possível obter informações do browser para o perfil {user_id}")
            return None
            
        except Exception as e:
            logger.error(f"[ERRO] Erro ao obter informações do browser: {str(e)}")
            return None

    def connect_selenium(self, browser_info: Dict) -> Optional[webdriver.Chrome]:
        """
        Conecta ao WebDriver do AdsPower.

        Args:
            browser_info: Informações do navegador (obtidas de get_browser_info)

        Returns:
            Optional[webdriver.Chrome]: Instância do WebDriver ou None se falhar
        """
        selenium_ws = browser_info.get("selenium_ws")
        webdriver_path = browser_info.get("webdriver_path")

        if not selenium_ws or not webdriver_path:
            logger.error("[ERRO] Informações de WebDriver incompletas")
            return None

        try:
            service = Service(executable_path=webdriver_path)
            options = Options()
            options.add_experimental_option("debuggerAddress", selenium_ws)

            driver = webdriver.Chrome(service=service, options=options)
            logger.info("[OK] Conectado ao WebDriver Selenium do AdsPower")
            return driver

        except Exception as e:
            logger.error(f"[ERRO] Erro ao conectar ao WebDriver: {str(e)}")
            return None

    def get_create_profile_stats(self, user_id: str) -> Dict:
        """
        Obtém estatísticas de criação de perfil.

        Args:
            user_id: ID do perfil

        Returns:
            Dict: Estatísticas do perfil
        """
        profile_info = self.get_profile_info(user_id)

        if not profile_info:
            return {
                "name": "Desconhecido",
                "status": "Não encontrado",
                "created_at": "Desconhecido",
                "last_login": "Nunca",
                "group": "Desconhecido"
            }

        return {
            "name": profile_info.get("name", "Sem nome"),
            "status": profile_info.get("status", "Desconhecido"),
            "created_at": profile_info.get("created_time", "Desconhecido"),
            "last_login": profile_info.get("last_login_time", "Nunca"),
            "group": profile_info.get("group_name", "Sem grupo")
        }

    def is_profile_valid(self, user_id: str, max_retries=3, retry_delay=2) -> bool:
        """
        Verifica se um perfil é válido usando múltiplos métodos.

        Args:
            user_id (str): ID do perfil para verificar
            max_retries (int): Número máximo de tentativas
            retry_delay (int): Tempo de espera entre tentativas em segundos

        Returns:
            bool: True se o perfil é válido
        """
        logger.info(f"[INFO] Verificando validade do perfil {user_id}")
        
        # Verificar cache primeiro
        if user_id in self.cache.get("profiles", {}):
            logger.info(f"[INFO] Perfil {user_id} encontrado no cache")
            return True

        for attempt in range(max_retries):
            logger.info(f"[INFO] Tentativa {attempt + 1}/{max_retries} de validar perfil")
            
            # Método 1: Verificar via API v1 (prioridade)
            url_v1 = f"{self.base_url}/api/v1/user/info"
            try:
                response = requests.get(url_v1, params={"user_id": user_id})
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"[DEBUG] Resposta da API v1: {data}")
                    if data.get("code") == 0:
                        logger.info(f"[OK] Perfil {user_id} validado via API v1")
                        return True
            except Exception as e:
                logger.warning(f"[AVISO] Erro ao validar via API v1: {str(e)}")

            # Método 2: Verificar na lista de perfis
            profiles = self.get_all_profiles(force_refresh=True)
            
            # Log detalhado dos perfis
            logger.info(f"[DEBUG] Total de perfis retornados pela API: {len(profiles)}")
            profile_ids = [p.get("user_id") for p in profiles]
            logger.info(f"[DEBUG] IDs dos perfis disponíveis: {profile_ids}")
            
            # Verificar se o perfil está na lista
            target_profile = None
            for profile in profiles:
                if profile.get("user_id") == user_id:
                    target_profile = profile
                    break
            
            if target_profile:
                logger.info(f"[DEBUG] Detalhes do perfil encontrado: {target_profile}")
                
                # Se o perfil nunca foi aberto (novo perfil)
                if not target_profile.get("last_open_time") or target_profile.get("last_open_time") == "0":
                    logger.info(f"[INFO] Perfil {user_id} é novo e nunca foi aberto. Tentando inicializar...")
                    
                    # Tentar inicializar o perfil
                    try:
                        # Primeiro, tentar inicializar
                        init_url = f"{self.base_url}/api/v1/browser/init"
                        params = {"user_id": user_id}
                        response = requests.get(init_url, params=params)
                        
                        if response.status_code == 200:
                            data = response.json()
                            logger.info(f"[DEBUG] Resposta da inicialização: {data}")
                            
                            if data.get("code") == 0:
                                logger.info(f"[OK] Perfil {user_id} inicializado com sucesso")
                                return True
                            else:
                                logger.warning(f"[AVISO] Falha ao inicializar perfil: {data.get('msg', 'Erro desconhecido')}")
                    except Exception as e:
                        logger.error(f"[ERRO] Erro ao inicializar perfil: {str(e)}")
                else:
                    logger.info(f"[OK] Perfil {user_id} encontrado e já foi usado anteriormente")
                    return True
            
            # Se chegou aqui, o perfil não foi encontrado ou não está válido
            if attempt < max_retries - 1:
                logger.info(f"[INFO] Aguardando {retry_delay}s antes da próxima tentativa...")
                time.sleep(retry_delay)
                continue

        logger.error(f"[ERRO] Perfil {user_id} não encontrado ou não está válido após {max_retries} tentativas")
        return False

    def get_groups(self) -> List[Dict]:
        """
        Obtém a lista de grupos do AdsPower.

        Returns:
            List[Dict]: Lista de grupos com seus IDs e informações
        """
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/group/list",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=20
            )
            response.raise_for_status()
            data = response.json()

            if data.get("code") == 0 and "data" in data:
                groups = data["data"].get("list", [])
                logger.info(f"[INFO] Total de grupos encontrados: {len(groups)}")
                return groups

            error_msg = data.get("msg", "Erro desconhecido")
            logger.warning(f"[AVISO] Erro ao buscar grupos: {error_msg}")
            return []

        except Exception as e:
            logger.error(f"[ERRO] Erro ao buscar grupos: {str(e)}")
            return []

    def verify_and_connect_profile(self, user_id: str) -> Tuple[bool, Optional[Dict]]:
        """
        Verifica se um perfil existe e tenta conectar a ele.
        
        Args:
            user_id: ID do perfil do AdsPower
            
        Returns:
            Tuple[bool, Optional[Dict]]: (Sucesso, Informações do perfil)
        """
        try:
            # 1. Verificar se o perfil existe e está válido
            logger.info(f"[INFO] Iniciando verificação e conexão do perfil {user_id}")
            
            # Primeiro tentar inicializar o perfil (caso seja novo)
            try:
                init_url = f"{self.base_url}/api/v1/browser/init"
                params = {"user_id": user_id}
                init_response = requests.get(init_url, params=params)
                if init_response.status_code == 200:
                    init_data = init_response.json()
                    logger.info(f"[DEBUG] Resposta da inicialização: {init_data}")
                    if init_data.get("code") == 0:
                        logger.info(f"[OK] Perfil {user_id} inicializado com sucesso")
            except Exception as e:
                logger.warning(f"[AVISO] Erro ao tentar inicializar perfil: {str(e)}")
            
            # Agora validar o perfil
            if not self.is_profile_valid(user_id):
                logger.error(f"[ERRO] Perfil {user_id} não é válido ou não está pronto para uso")
                return False, None
                
            logger.info(f"[OK] Perfil {user_id} validado com sucesso")
            
            # 2. Verificar se o browser já está rodando
            self.rate_limiter.wait_if_needed()
            if self.is_browser_running(user_id):
                logger.info(f"[INFO] Browser já está rodando para o perfil {user_id}")
                # Tentar obter informações do browser existente
                browser_info = self.get_browser_info(user_id)
                if browser_info:
                    logger.info(f"[OK] Informações do browser obtidas com sucesso")
                    return True, browser_info
                else:
                    logger.warning(f"[AVISO] Browser está rodando mas não foi possível obter informações. Tentando reiniciar...")
                    self.stop_browser(user_id)
                    time.sleep(2)
            
            # 3. Se não está rodando ou precisou ser reiniciado, iniciar o browser
            logger.info(f"[INFO] Iniciando novo browser para o perfil {user_id}")
            
            # Tentar iniciar o browser com retries
            max_retries = 3
            retry_delay = 2
            
            for attempt in range(max_retries):
                logger.info(f"[INFO] Tentativa {attempt + 1}/{max_retries} de iniciar browser")
                
                self.rate_limiter.wait_if_needed()
                success, browser_info = self.start_browser(user_id)
                
                if success and browser_info:
                    # 4. Verificar informações do websocket
                    selenium_ws = browser_info.get("selenium_ws")
                    webdriver_path = browser_info.get("webdriver_path")
                    
                    if selenium_ws and webdriver_path:
                        logger.info(f"[OK] Conexão estabelecida com sucesso para o perfil {user_id}")
                        logger.info(f"[DEBUG] selenium_ws: {selenium_ws}")
                        logger.info(f"[DEBUG] webdriver_path: {webdriver_path}")
                        return True, browser_info
                
                if attempt < max_retries - 1:
                    logger.info(f"[INFO] Aguardando {retry_delay}s antes da próxima tentativa...")
                    time.sleep(retry_delay)
            
            logger.error(f"[ERRO] Falha ao iniciar browser para o perfil {user_id} após {max_retries} tentativas")
            return False, None
                
        except Exception as e:
            logger.error(f"[ERRO] Erro ao verificar e conectar ao perfil: {str(e)}")
            return False, None
