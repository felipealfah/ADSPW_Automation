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

# Adicionar o diretório pai ao path para importar módulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


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
        self.active_browsers = {}
        self.cache = self._load_cache()
        self.local_cache_path = local_cache_path
        self.base_url = None
        self.api_key = None

        # Prioridade 1: Obter credenciais do arquivo de credenciais
        cred_base_url = get_credential("PA_BASE_URL")
        cred_api_key = get_credential("PA_API_KEY")

        # Prioridade 2: Parâmetros passados para o construtor
        # Prioridade 3: Variáveis de ambiente
        # Prioridade 4: Detecção automática

        # Definir base_url
        if cred_base_url:
            self.base_url = cred_base_url
            logger.info(f"Usando PA_BASE_URL das credenciais: {self.base_url}")
        elif base_url:
            self.base_url = base_url
            logger.info(f"Usando base_url do parâmetro: {self.base_url}")
        elif os.environ.get('ADSPOWER_API_URL'):
            self.base_url = os.environ.get('ADSPOWER_API_URL')
            logger.info(
                f"Usando base_url da variável de ambiente: {self.base_url}")
        else:
            logger.info(
                "Base URL não fornecido, tentando detecção automática...")
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

    def _find_best_connection(self):
        """Testa múltiplos endereços para encontrar o melhor para conectar ao AdsPower."""
        possible_urls = [
            "http://local.adspower.net:50325",
            "http://host.docker.internal:50325",
            "http://gateway.docker.internal:50325",
            "http://localhost:50325",
            "http://127.0.0.1:50325"
        ]

        logger.info("Testando múltiplos endereços para conectar ao AdsPower...")
        for url in possible_urls:
            try:
                logger.info(f"Testando conexão com: {url}")
                response = requests.get(f"{url}/status", timeout=2)
                if response.status_code == 200:
                    self.base_url = url
                    logger.info(f"✅ Conexão bem-sucedida com: {url}")
                    return
            except Exception as e:
                logger.warning(f"❌ Falha ao conectar em {url}: {str(e)}")

        # Se nenhum funcionou, use um padrão
        self.base_url = "http://local.adspower.net:50325"
        logger.warning(
            f"⚠️ Nenhuma conexão bem-sucedida. Usando padrão: {self.base_url}")

    def _check_connection(self):
        """Verifica a conexão com o AdsPower."""
        try:
            # Tente uma requisição simples para verificar a conectividade
            response = requests.get(f"{self.base_url}/status", timeout=5)
            if response.status_code == 200:
                logger.info(f"✅ Conectado ao AdsPower em {self.base_url}")
            else:
                logger.warning(
                    f"⚠️ AdsPower respondeu com status {response.status_code}")

                # Se a conexão falhar, tente outros endereços
                if not self.base_url.startswith("http://local.adspower.net"):
                    # Tente local.adspower.net se ainda não tentou
                    try:
                        alt_url = "http://local.adspower.net:50325"
                        logger.info(
                            f"Tentando conexão alternativa com: {alt_url}")
                        alt_response = requests.get(
                            f"{alt_url}/status", timeout=3)
                        if alt_response.status_code == 200:
                            self.base_url = alt_url
                            logger.info(
                                f"✅ Conexão alternativa bem-sucedida com: {alt_url}")
                    except Exception:
                        logger.warning("❌ Conexão alternativa também falhou")

        except Exception as e:
            logger.error(f"❌ Erro ao conectar ao AdsPower: {str(e)}")
            logger.error(f"   URL tentada: {self.base_url}")
            logger.error(
                "   Verifique se o AdsPower está instalado e em execução no sistema host.")

            # Se a conexão falhar, tente outros endereços
            if not self.base_url.startswith("http://local.adspower.net"):
                # Tente local.adspower.net se ainda não tentou
                try:
                    alt_url = "http://local.adspower.net:50325"
                    logger.info(f"Tentando conexão alternativa com: {alt_url}")
                    alt_response = requests.get(f"{alt_url}/status", timeout=3)
                    if alt_response.status_code == 200:
                        self.base_url = alt_url
                        logger.info(
                            f"✅ Conexão alternativa bem-sucedida com: {alt_url}")
                except Exception:
                    logger.warning("❌ Conexão alternativa também falhou")

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
            logger.warning(f"⚠️ Erro ao carregar cache do AdsPower: {str(e)}")
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
            logger.warning(f"⚠️ Erro ao salvar cache do AdsPower: {str(e)}")

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
                url, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    # API está saudável
                    self.cache["service_status"]["available"] = True
                    self.cache["service_status"]["last_checked"] = current_time
                    self._save_cache()
                    logger.info("✅ API do AdsPower está saudável")
                    return True

            # API não está saudável
            self.cache["service_status"]["available"] = False
            self.cache["service_status"]["last_checked"] = current_time
            self._save_cache()
            logger.warning(
                f"⚠️ API do AdsPower não está respondendo corretamente: {response.status_code}")
            return False

        except Exception as e:
            # Erro na verificação
            self.cache["service_status"]["available"] = False
            self.cache["service_status"]["last_checked"] = current_time
            self._save_cache()
            logger.error(
                f"❌ Erro ao verificar saúde da API do AdsPower: {str(e)}")
            return False

    def get_all_profiles(self, force_refresh=False) -> List[Dict]:
        """
        Obtém todos os perfis disponíveis no AdsPower.

        Args:
            force_refresh: Se True, força uma atualização do cache

        Returns:
            List[Dict]: Lista de perfis
        """
        current_time = time.time()
        cache_time = 15 * 60  # 15 minutos

        # Usar cache se não precisa atualizar
        if not force_refresh and (current_time - self.cache["last_updated"]) < cache_time:
            return list(self.cache["profiles"].values())

        all_profiles = []
        page = 1
        page_size = 100  # Aumentar para pegar mais perfis de uma vez

        while True:
            try:
                response = requests.get(
                    f"{self.base_url}/api/v1/user/list",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    params={"page": page, "page_size": page_size},
                    timeout=15
                )
                response.raise_for_status()  # Levanta um erro se a resposta não for 200
                data = response.json()

                # Adicione um log para verificar a resposta
                logger.info(f"Resposta da API: {data}")

                if "data" in data and "list" in data["data"]:
                    profiles = data["data"]["list"]
                    all_profiles.extend(profiles)

                    # Atualizar cache
                    for profile in profiles:
                        self.cache["profiles"][profile["user_id"]] = profile

                    # Verificar se há mais páginas
                    if len(profiles) < page_size:
                        break  # Última página
                    page += 1
                else:
                    logger.warning(
                        "⚠️ Nenhum perfil encontrado na resposta da API.")
                    break

            except Exception as e:
                logger.error(f"❌ Erro ao buscar perfis: {str(e)}")
                break

        # Atualizar timestamp do cache
        self.cache["last_updated"] = current_time
        self._save_cache()

        return all_profiles

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

            logger.warning(f"⚠️ Perfil {user_id} não encontrado na API")
            return None

        except Exception as e:
            logger.error(
                f"❌ Erro ao buscar informações do perfil {user_id}: {str(e)}")
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
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("data", {}).get("status") == "Active"

            return False

        except Exception as e:
            logger.error(
                f"❌ Erro ao verificar status do navegador para {user_id}: {str(e)}")
            return False

    def start_browser(self, user_id: str, headless: bool = False, max_wait_time: int = 30) -> Tuple[bool, Optional[Dict]]:
        """
        Inicia o navegador para um perfil e aguarda até estar pronto.

        Args:
            user_id: ID do perfil
            headless: Se True, inicia o navegador em modo headless
            max_wait_time: Tempo máximo de espera em segundos

        Returns:
            Tuple[bool, Optional[Dict]]: (Sucesso, Informações do navegador)
        """
        # Verificar se já está em execução
        if self.is_browser_running(user_id):
            logger.info(
                f"✅ Navegador para perfil {user_id} já está em execução")
            browser_info = self.get_browser_info(user_id)
            return True, browser_info

        # Iniciar navegador
        try:
            # Adicionar parâmetro headless na URL
            url_start = f"{self.base_url}/api/v1/browser/start?user_id={user_id}&headless={str(headless).lower()}"
            response = requests.get(
                url_start, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=15)

            if response.status_code != 200:
                logger.error(
                    f"❌ Erro ao iniciar navegador: HTTP {response.status_code}")
                return False, None

            data = response.json()
            if data.get("code") != 0:
                logger.error(f"❌ Erro ao iniciar navegador: {data.get('msg')}")
                return False, None

            logger.info(
                f"🚀 Iniciando navegador para perfil {user_id} {'(headless)' if headless else ''}")

            # Aguardar até o navegador estar pronto
            start_time = time.time()
            while (time.time() - start_time) < max_wait_time:
                time.sleep(2)  # Intervalo entre verificações

                browser_info = self.get_browser_info(user_id)
                if browser_info and browser_info.get("selenium_ws"):
                    # Navegador está pronto
                    self.active_browsers[user_id] = browser_info
                    logger.info(f"✅ Navegador pronto para perfil {user_id}")
                    return True, browser_info

            # Timeout - navegador não ficou pronto no tempo esperado
            logger.error(
                f"⏰ Timeout ao aguardar navegador para perfil {user_id}")
            return False, None

        except Exception as e:
            logger.error(
                f"❌ Erro ao iniciar navegador para perfil {user_id}: {str(e)}")
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
                url_stop, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    # Remover do cache de navegadores ativos
                    if user_id in self.active_browsers:
                        del self.active_browsers[user_id]

                    logger.info(
                        f"✅ Navegador para perfil {user_id} parado com sucesso")
                    return True

            logger.warning(
                f"⚠️ Falha ao parar navegador para perfil {user_id}")
            return False

        except Exception as e:
            logger.error(
                f"❌ Erro ao parar navegador para perfil {user_id}: {str(e)}")
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
                url_stop, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    # Remover do cache de navegadores ativos
                    if user_id in self.active_browsers:
                        del self.active_browsers[user_id]

                    logger.info(
                        f"✅ Navegador para perfil {user_id} fechado com sucesso")
                    return True

            logger.warning(
                f"⚠️ Falha ao fechar navegador para perfil {user_id}")
            return False

        except Exception as e:
            logger.error(
                f"❌ Erro ao fechar navegador para perfil {user_id}: {str(e)}")
            return False

    def get_browser_info(self, user_id: str) -> Optional[Dict]:
        """
        Obtém informações do navegador ativo para um perfil.

        Args:
            user_id: ID do perfil

        Returns:
            Optional[Dict]: Informações do navegador ou None se não encontrado
        """
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/browser/local-active",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10
            )

            if response.status_code != 200:
                return None

            data = response.json()
            if data.get("code") != 0:
                return None

            # Buscar o navegador correspondente ao user_id
            for browser in data.get("data", {}).get("list", []):
                if browser.get("user_id") == user_id:
                    result = {
                        "status": "success",
                        "selenium_ws": browser.get("ws", {}).get("selenium"),
                        "webdriver_path": browser.get("webdriver")
                    }
                    return result

            return None

        except Exception as e:
            logger.error(
                f"❌ Erro ao obter informações do navegador para {user_id}: {str(e)}")
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
            logger.error("❌ Informações de WebDriver incompletas")
            return None

        try:
            service = Service(executable_path=webdriver_path)
            options = Options()
            options.add_experimental_option("debuggerAddress", selenium_ws)

            driver = webdriver.Chrome(service=service, options=options)
            logger.info("✅ Conectado ao WebDriver Selenium do AdsPower")
            return driver

        except Exception as e:
            logger.error(f"❌ Erro ao conectar ao WebDriver: {str(e)}")
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

    def is_profile_valid(self, user_id):
        """Verifica se o perfil ainda existe no AdsPower."""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/user/info", headers={"Authorization": f"Bearer {self.api_key}"}, params={"user_id": user_id})
            if response.status_code == 200:
                data = response.json()
                return data.get("code") == 0  # Retorna True se o perfil existe
            return False
        except Exception as e:
            logger.error(f"Erro ao verificar perfil {user_id}: {str(e)}")
            return False
