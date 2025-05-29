from .api_handler import make_request
import json
import requests
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Estruturas de Fingerprint
FINGERPRINTS = {
    "MACos": {
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "resolution": "2560x1600",
        "timezone": "UTC-5",
    },
    "IOS": {
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_2_3)",
        "resolution": "2880x1800",
        "timezone": "UTC-4",
    },
    "Windows": {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "resolution": "1920x1080",
        "timezone": "UTC+1",
    },
    "Android": {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "resolution": "1366x768",
        "timezone": "UTC",
    },
}


def create_profile_with_fingerprint(base_url, headers, name, fingerprint_choice, group_id, proxy_config=None):
    """
    Cria um novo perfil no AdsPower com a estrutura de fingerprint escolhida.

    Args:
        base_url (str): URL base da API do AdsPower.
        headers (dict): Cabeçalhos da requisição, incluindo autorização.
        name (str): Nome do perfil.
        fingerprint_choice (str): Nome da estrutura de fingerprint (ex.: MACos01, Win01).
        group_id (str): ID do grupo ao qual o perfil será associado.
        proxy_config (dict, optional): Configuração de proxy. Se None, será usado um proxy de teste.

    Returns:
        dict: Resposta da API em formato JSON.
    """
    # Validar a escolha do fingerprint
    if fingerprint_choice not in FINGERPRINTS:
        raise ValueError(f"Fingerprint inválido: {fingerprint_choice}")

    # [INICIO] Se proxy_config for None, usar um proxy fixo de teste
    if not proxy_config:
        proxy_config = {
            "proxy_type": "http",
            "proxy_host": "123.0.0.1",  # [PARADA] Altere para um IP de proxy real
            "proxy_port": "8080",
            "proxy_user": "proxyuser",  # [PARADA] Se necessário, altere para um usuário real
            "proxy_password": "proxypass",  # [PARADA] Se necessário, altere para uma senha real
            "proxy_soft": "luminati"
        }

    # Validar se proxy_config contém os campos obrigatórios
    required_fields = ["proxy_type", "proxy_host", "proxy_port",
                       "proxy_user", "proxy_password", "proxy_soft"]
    missing_fields = [
        field for field in required_fields if field not in proxy_config]

    if missing_fields:
        raise ValueError(
            f"Faltando campos obrigatórios no proxy_config: {missing_fields}")

    # Construir user_proxy_config corretamente
    proxy_data = {
        "user_proxy_config": {
            "proxy_type": proxy_config["proxy_type"],
            "proxy_host": proxy_config["proxy_host"],
            "proxy_port": str(proxy_config["proxy_port"]),
            "proxy_user": proxy_config["proxy_user"],
            "proxy_password": proxy_config["proxy_password"],
            "proxy_soft": proxy_config["proxy_soft"]
        }
    }

    # Configurar os dados do perfil
    profile_data = {
        "name": name,
        "group_id": group_id,
        "fingerprint_config": FINGERPRINTS[fingerprint_choice],
        **proxy_data  # [INICIO] Sempre incluir um proxy válido!
    }

    # [BUSCA] Debug: Exibir JSON enviado para a API
    print("\n[BUSCA] Dados enviados para a API (JSON):")
    print(json.dumps(profile_data, indent=4))

    # Enviar a requisição para criar o perfil
    url = f"{base_url}/api/v1/user/create"
    response = make_request("POST", url, headers, profile_data)

    # [BUSCA] Debug: Exibir resposta da API
    print("\n[BUSCA] Resposta da API:")
    print(response)

    return response


def list_groups(base_url, headers, page=1, page_size=10):
    """
    Lista todos os grupos disponíveis no AdsPower.

    Args:
        base_url (str): URL base da API do AdsPower.
        headers (dict): Cabeçalhos da requisição, incluindo autorização.
        page (int): Número da página para consulta (paginação).
        page_size (int): Número de resultados por página.

    Returns:
        list: Lista de grupos (cada grupo é um dicionário com 'group_id' e 'group_name').

    Raises:
        ValueError: Se a resposta da API contiver erros ou não puder ser processada.
    """
    url = f"{base_url}/api/v1/group/list"
    # Parâmetros opcionais de consulta
    params = {"page": page, "page_size": page_size}

    # Fazer a requisição GET
    response = make_request("GET", url, headers, payload=params)

    # Validar o formato da resposta
    if response and isinstance(response, dict):
        if response.get("code") == 0:  # Verificar sucesso na resposta
            group_list = response.get("data", {}).get("list", [])
            return group_list  # Retornar a lista de grupos
        else:
            # Erro retornado pela API
            raise ValueError(
                f"Erro ao listar grupos: {response.get('msg', 'Erro desconhecido')}")
    else:
        raise ValueError("Resposta inválida ou não decodificável da API")


def get_profiles(base_url, headers, only_in_groups=True):
    """
    Obtém a lista de perfis no AdsPower.

    Args:
        base_url (str): URL base da API do AdsPower
        headers (dict): Headers para autenticação
        only_in_groups (bool): Se True, retorna apenas perfis que estão em grupos.
                             Se False, retorna todos os perfis.
    """
    all_profiles = []
    try:
        response = requests.get(
            f"{base_url}/api/v1/user/list",
            headers=headers,
            params={"page": 1, "page_size": 100}
        )
        response.raise_for_status()
        data = response.json()

        if "data" in data and "list" in data["data"]:
            profiles = data["data"]["list"]

            if only_in_groups:
                # Filtrar apenas perfis em grupos
                filtered_profiles = [
                    profile for profile in profiles
                    if profile.get('group_id') != '0' and profile.get('group_name')
                ]
            else:
                # Retornar todos os perfis
                filtered_profiles = profiles

            all_profiles.extend(filtered_profiles)

            logging.info(f"Total de perfis encontrados: {len(profiles)}")
            logging.info(f"Perfis filtrados: {len(filtered_profiles)}")

            # Log detalhado dos perfis excluídos do filtro para debug
            if only_in_groups:
                excluded_profiles = [
                    profile for profile in profiles
                    if profile.get('group_id') == '0' or not profile.get('group_name')
                ]
                if excluded_profiles:
                    logging.info("Perfis fora de grupos encontrados:")
                    for profile in excluded_profiles:
                        logging.info(f"Nome: {profile.get('name')}, ID: {profile.get('user_id')}, "
                                   f"Group ID: {profile.get('group_id')}, Group Name: {profile.get('group_name')}")

    except requests.exceptions.RequestException as e:
        logging.error(f"[ERRO] Erro ao buscar perfis: {e}")

    return all_profiles


def create_group(base_url, headers, group_name):
    """
    Cria um novo grupo no AdsPower.

    Args:
        base_url (str): URL base da API do AdsPower.
        headers (dict): Cabeçalhos da requisição.
        group_name (str): Nome do grupo a ser criado.

    Returns:
        dict: Resposta da API.
    """
    url = f"{base_url}/api/v1/group/create"
    payload = {"group_name": group_name}
    return make_request("POST", url, headers, payload)


def check_profile_status(base_url, headers, user_id):
    """
    Verifica se um perfil está ativo no AdsPower.

    Args:
        base_url (str): URL base da API do AdsPower.
        headers (dict): Cabeçalhos da requisição.
        user_id (str): ID do perfil.

    Returns:
        dict: Resposta da API.
    """
    url = f"{base_url}/api/v1/browser/active?user_id={user_id}"
    return make_request("GET", url, headers)


def delete_profile(base_url, headers, user_id):
    """
    Deleta um perfil do AdsPower.

    Args:
        base_url (str): URL base da API do AdsPower.
        headers (dict): Cabeçalhos da requisição.
        user_id (str): ID do perfil.

    Returns:
        dict: Resposta da API.
    """
    url = f"{base_url}/api/v1/user/delete"
    payload = {"user_ids": [user_id]}
    return make_request("POST", url, headers, payload)


def delete_profile_cache(base_url, headers, user_id):
    """
    Deleta o cache de um perfil no AdsPower.

    Args:
        base_url (str): URL base da API do AdsPower.
        headers (dict): Cabeçalhos da requisição.
        user_id (str): ID do perfil.

    Returns:
        dict: Resposta da API.
    """
    url = f"{base_url}/api/v1/user/delete-cache"
    payload = {"user_id": user_id}
    return make_request("POST", url, headers, payload)


def update_profile(base_url, headers, user_id, update_data):
    """
    Atualiza informações de um perfil no AdsPower.

    Args:
        base_url (str): URL base da API do AdsPower.
        headers (dict): Cabeçalhos da requisição.
        user_id (str): ID do perfil.
        update_data (dict): Dados a serem atualizados.

    Returns:
        dict: Resposta da API.
    """
    url = f"{base_url}/api/v1/user/update"
    update_data["user_id"] = user_id  # Adiciona o user_id ao payload
    return make_request("POST", url, headers, update_data)


def create_profile_v2(base_url, headers, config):
    """
    Cria um novo perfil usando a API v2 do AdsPower.

    Args:
        base_url (str): URL base da API do AdsPower
        headers (dict): Headers para autenticação
        config (dict): Configuração do perfil contendo:
            - name (str, opcional): Nome do perfil
            - group_id (str): ID do grupo
            - user_proxy_config (dict, opcional): Configuração de proxy
            - fingerprint_config (dict): Configuração de fingerprint
            - platform (str, opcional): Plataforma (ex: facebook.com)
            - username (str, opcional): Username da plataforma
            - password (str, opcional): Senha da plataforma
            - remark (str, opcional): Observações sobre o perfil

    Returns:
        dict: Resposta da API contendo profile_id e profile_no se sucesso
    """
    try:
        url = f"{base_url}/api/v2/browser-profile/create"
        
        # Configuração padrão de fingerprint se não fornecida
        if "fingerprint_config" not in config:
            config["fingerprint_config"] = {
                "os": "Windows",
                "browser": "chrome",
                "version": "117",
                "webrtc": "disabled",
                "flash": "block",
                "timezone": {
                    "timezone": "UTC-3"
                },
                "language": ["pt-BR", "pt"],
                "fonts": ["all"],
                "hardware_concurrency": 4,
                "resolution": "1920x1080",
                "audio_context": True
            }

        # Configuração padrão de proxy se não fornecida
        if "user_proxy_config" not in config and "proxyid" not in config:
            config["user_proxy_config"] = {
                "proxy_type": "http",
                "proxy_host": "123.0.0.1",
                "proxy_port": "8080",
                "proxy_user": "proxyuser",
                "proxy_password": "proxypass",
                "proxy_soft": "luminati"
            }

        # Garantir que group_id está presente
        if "group_id" not in config:
            raise ValueError("group_id é obrigatório")

        # Log dos dados que serão enviados
        logger.info(f"[CRIAR PERFIL] Enviando configuração: {json.dumps(config, indent=2)}")

        # Fazer a requisição
        response = requests.post(url, headers=headers, json=config, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("code") == 0:
            logger.info(f"[OK] Perfil criado com sucesso: {data.get('data')}")
            return data.get("data")
        else:
            error_msg = data.get("msg", "Erro desconhecido")
            logger.error(f"[ERRO] Falha ao criar perfil: {error_msg}")
            raise ValueError(f"Erro ao criar perfil: {error_msg}")

    except requests.exceptions.RequestException as e:
        logger.error(f"[ERRO] Erro de requisição ao criar perfil: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"[ERRO] Erro ao criar perfil: {str(e)}")
        raise


class ProfileManager:
    def __init__(self, cache):
        self.cache = cache

        # Obter as credenciais necessárias do cache ou de outra fonte
        from credentials.credentials_manager import get_credential

        # Definir base_url e headers
        self.base_url = get_credential("PA_BASE_URL") or "http://local.adspower.net:50325"
        api_key = get_credential("PA_API_KEY")

        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        } if api_key else {}

        logging.info(f"ProfileManager inicializado com base_url: {self.base_url}")

    def get_all_profiles(self, force_refresh=False, include_no_group=False):
        """
        Obtém todos os perfis ativos da API.

        Args:
            force_refresh (bool): Se True, força uma atualização do cache
            include_no_group (bool): Se True, inclui perfis sem grupo

        Returns:
            list: Lista de perfis ativos
        """
        try:
            logging.info(
                f"Obtendo perfis do AdsPower usando base_url: {self.base_url}")

            response = requests.get(
                f"{self.base_url}/api/v1/user/list",
                headers=self.headers,
                params={"page": 1, "page_size": 100}
            )
            response.raise_for_status()
            data = response.json()

            logging.info(f"Resposta da API: {data}")

            if data.get("code") == 0 and "data" in data and "list" in data["data"]:
                profiles = data["data"]["list"]
                
                # Filtrar perfis baseado no parâmetro include_no_group
                if not include_no_group:
                    # Filtrar apenas perfis em grupos
                    active_profiles = [
                        profile for profile in profiles
                        if profile.get('group_id') != '0' and profile.get('group_name')
                    ]
                else:
                    # Incluir todos os perfis
                    active_profiles = profiles

                logging.info(f"Perfis ativos encontrados: {len(active_profiles)}")
                return active_profiles
            else:
                logging.warning(f"Resposta da API não contém perfis: {data}")
                return []
        except Exception as e:
            logging.error(f"Erro ao obter perfis: {e}")
            return []

    def find_deleted_profiles(self):
        """
        Compara os perfis armazenados no cache com os retornados pela API
        para identificar quais perfis foram apagados.
        """
        try:
            # Verificar se temos perfis no cache
            if not hasattr(self.cache, 'profiles_cache') or not self.cache.profiles_cache:
                logger.info("Cache de perfis vazio ou não inicializado")
                return set()

            # Buscar os perfis ativos mais recentes da API
            active_profiles = self.get_all_profiles(force_refresh=True)
            if not active_profiles:
                logger.warning("Não foi possível obter perfis ativos da API")
                return set()

            active_ids = {profile["user_id"] for profile in active_profiles}

            # Obter perfis do cache (certificando-se de que é um dicionário)
            cached_profiles = self.cache.profiles_cache
            if not isinstance(cached_profiles, dict):
                logger.warning(
                    f"Cache de perfis não é um dicionário: {type(cached_profiles)}")
                return set()

            cached_ids = set(cached_profiles.keys())

            # Perfis deletados = aqueles que estavam no cache mas não aparecem mais na API
            deleted_profiles = cached_ids - active_ids

            if deleted_profiles:
                logger.info(f"Perfis deletados detectados: {deleted_profiles}")
            else:
                logger.info("Nenhum perfil deletado identificado.")

            return deleted_profiles
        except Exception as e:
            logger.error(f"Erro ao verificar perfis deletados: {str(e)}")
            return set()

    def create_new_profile(self, config):
        """
        Cria um novo perfil usando a API v2.
        
        Args:
            config (dict): Configuração do perfil
            
        Returns:
            dict: Informações do perfil criado
        """
        return create_profile_v2(self.base_url, self.headers, config)

    def connect_profile(self, user_id, debug_port=None):
        """
        Conecta a um perfil específico.
        
        Args:
            user_id (str): ID do perfil para conectar
            debug_port (int, optional): Porta específica para debugging
            
        Returns:
            dict: Informações de conexão do perfil
        """
        # Primeiro verifica se o perfil é válido
        if not is_profile_valid(self.base_url, self.headers, user_id):
            raise ValueError(f"Perfil {user_id} não é válido ou não foi encontrado")
            
        return connect_to_profile(self.base_url, self.headers, user_id, debug_port)


def process_reusable_number(reusable_number):
    if reusable_number:
        first_used = reusable_number.get("first_used", None)
        if first_used is not None:
            first_used_datetime = datetime.fromtimestamp(first_used)
        else:
            first_used_datetime = "N/A"
    else:
        first_used_datetime = "N/A"
    return first_used_datetime


def connect_to_profile(base_url, headers, user_id, debug_port=None):
    """
    Conecta a um perfil existente do AdsPower.

    Args:
        base_url (str): URL base da API do AdsPower
        headers (dict): Headers para autenticação
        user_id (str): ID do perfil para conectar
        debug_port (int, optional): Porta específica para debugging

    Returns:
        dict: Informações de conexão incluindo selenium_port, debug_port e ws_address
    """
    try:
        # Primeiro tenta a API v1 (mais estável)
        logger.info(f"[CONECTAR] Tentando conectar ao perfil {user_id} via API v1")
        url_v1 = f"{base_url}/api/v1/browser/start"
        payload = {
            "user_id": user_id,
            "debug_port": debug_port
        }
        
        response = requests.post(url_v1, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                logger.info(f"[OK] Conexão estabelecida via API v1: {data.get('data')}")
                return data.get("data")
        
        # Se falhar, tenta a API v2 como fallback
        logger.info(f"[CONECTAR] API v1 falhou, tentando API v2")
        url_v2 = f"{base_url}/api/v2/browser-profile/start"
        payload = {
            "profile_id": user_id,
            "debug_port": debug_port
        }
        
        response = requests.post(url_v2, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                logger.info(f"[OK] Conexão estabelecida via API v2: {data.get('data')}")
                return data.get("data")
        
        error_msg = "Falha ao conectar usando ambas APIs v1 e v2"
        logger.error(f"[ERRO] {error_msg}")
        raise ValueError(error_msg)

    except requests.exceptions.RequestException as e:
        logger.error(f"[ERRO] Erro de requisição ao conectar ao perfil: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"[ERRO] Erro ao conectar ao perfil: {str(e)}")
        raise


def is_profile_valid(base_url, headers, user_id):
    """
    Verifica se um perfil é válido usando múltiplos métodos.

    Args:
        base_url (str): URL base da API do AdsPower
        headers (dict): Headers para autenticação
        user_id (str): ID do perfil para verificar

    Returns:
        bool: True se o perfil é válido, False caso contrário
    """
    try:
        # Método 1: Verificar via API v1 (prioridade)
        url_v1 = f"{base_url}/api/v1/user/info"
        response = requests.get(url_v1, headers=headers, params={"user_id": user_id})
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                logger.info(f"[OK] Perfil {user_id} validado via API v1")
                return True

        # Método 2: Verificar na lista de perfis
        url_list = f"{base_url}/api/v1/user/list"
        response = requests.get(url_list, headers=headers, params={"page": 1, "page_size": 100})
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                profiles = data.get("data", {}).get("list", [])
                if any(p.get("user_id") == user_id for p in profiles):
                    logger.info(f"[OK] Perfil {user_id} encontrado na lista de perfis")
                    return True

        # Método 3: Verificar via API v2 (último recurso)
        url_v2 = f"{base_url}/api/v2/browser-profile/info"
        response = requests.get(url_v2, headers=headers, params={"profile_id": user_id})
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                logger.info(f"[OK] Perfil {user_id} validado via API v2")
                return True

        logger.warning(f"[AVISO] Perfil {user_id} não encontrado em nenhum método de validação")
        return False

    except Exception as e:
        logger.error(f"[ERRO] Erro ao verificar perfil {user_id}: {str(e)}")
        return False
