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

    # 🚀 Se proxy_config for None, usar um proxy fixo de teste
    if not proxy_config:
        proxy_config = {
            "proxy_type": "http",
            "proxy_host": "123.0.0.1",  # 🛑 Altere para um IP de proxy real
            "proxy_port": "8080",
            "proxy_user": "proxyuser",  # 🛑 Se necessário, altere para um usuário real
            "proxy_password": "proxypass",  # 🛑 Se necessário, altere para uma senha real
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
        **proxy_data  # 🚀 Sempre incluir um proxy válido!
    }

    # 🔍 Debug: Exibir JSON enviado para a API
    print("\n🔍 Dados enviados para a API (JSON):")
    print(json.dumps(profile_data, indent=4))

    # Enviar a requisição para criar o perfil
    url = f"{base_url}/api/v1/user/create"
    response = make_request("POST", url, headers, profile_data)

    # 🔍 Debug: Exibir resposta da API
    print("\n🔍 Resposta da API:")
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


def get_profiles(base_url, headers):
    """
    Obtém a lista completa de perfis ativos no AdsPower.
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
            # Filtrar apenas perfis ativos (com group_id diferente de '0' e group_name não vazio)
            active_profiles = [
                profile for profile in profiles
                if profile.get('group_id') != '0' and profile.get('group_name')
            ]
            all_profiles.extend(active_profiles)

            logging.info(f"Total de perfis encontrados: {len(profiles)}")
            logging.info(f"Perfis ativos: {len(active_profiles)}")

            # Log detalhado dos perfis inativos para debug
            inactive_profiles = [
                profile for profile in profiles
                if profile.get('group_id') == '0' or not profile.get('group_name')
            ]
            if inactive_profiles:
                logging.info("Perfis inativos encontrados:")
                for profile in inactive_profiles:
                    logging.info(f"Nome: {profile.get('name')}, ID: {profile.get('user_id')}, "
                                 f"Group ID: {profile.get('group_id')}, Group Name: {profile.get('group_name')}")

    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Erro ao buscar perfis: {e}")

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


def list_groups(base_url, headers, page=1, page_size=15):
    """
    Lista os grupos existentes no AdsPower.

    Args:
        base_url (str): URL base da API do AdsPower.
        headers (dict): Cabeçalhos da requisição.
        page (int): Página atual.
        page_size (int): Número de grupos por página.

    Returns:
        dict: Resposta da API.
    """
    url = f"{base_url}/api/v1/group/list?page={page}&page_size={page_size}"
    return make_request("GET", url, headers)


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


class ProfileManager:
    def __init__(self, cache):
        self.cache = cache

        # Obter as credenciais necessárias do cache ou de outra fonte
        from credentials.credentials_manager import get_credential

        # Definir base_url e headers
        self.base_url = get_credential(
            "PA_BASE_URL") or "http://local.adspower.net:50325"
        api_key = get_credential("PA_API_KEY")

        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        } if api_key else {}

        logging.info(
            f"ProfileManager inicializado com base_url: {self.base_url}")

    def get_all_profiles(self, force_refresh=False):
        """
        Obtém todos os perfis ativos da API.
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
                # Filtrar apenas perfis ativos
                active_profiles = [
                    profile for profile in data["data"]["list"]
                    if profile.get('group_id') != '0' and profile.get('group_name')
                ]
                logging.info(
                    f"Perfis ativos encontrados: {len(active_profiles)}")
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
