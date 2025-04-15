import json
import os
import logging
import time

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Caminho do arquivo de credenciais
CREDENTIALS_PATH = "credentials/credentials.json"
# Variável para acompanhar a última modificação do arquivo
_last_modified_time = 0
# Cache de credenciais
_credentials_cache = None

def ensure_credentials_dir():
    """Garante que o diretório de credenciais existe."""
    os.makedirs(os.path.dirname(CREDENTIALS_PATH), exist_ok=True)

def load_credentials(force_reload=False):
    """
    Carrega as credenciais do arquivo JSON com suporte a atualização automática.
    
    Args:
        force_reload (bool): Se True, força um recarregamento do arquivo.
        
    Returns:
        dict: Dicionário com as credenciais ou um dicionário vazio se não encontrado.
    """
    global _last_modified_time, _credentials_cache
    
    try:
        # Verificar se o arquivo existe
        if not os.path.exists(CREDENTIALS_PATH):
            ensure_credentials_dir()
            return {}
        
        # Obter o timestamp de modificação do arquivo
        current_mtime = os.path.getmtime(CREDENTIALS_PATH)
        
        # Recarregar apenas se necessário (primeira carga, modificação ou força)
        if force_reload or _credentials_cache is None or current_mtime > _last_modified_time:
            with open(CREDENTIALS_PATH, "r") as file:
                _credentials_cache = json.load(file)
                _last_modified_time = current_mtime
                logger.info(f"Credenciais carregadas com sucesso. Última modificação: {time.ctime(current_mtime)}")
        
        return _credentials_cache
        
    except json.JSONDecodeError:
        logger.error(f"Erro ao decodificar o arquivo de credenciais. O formato JSON pode estar inválido.")
        return {}
    except Exception as e:
        logger.error(f"Erro ao carregar credenciais: {str(e)}")
        return {}

def add_or_update_api_key(key_name, key_value):
    """
    Adiciona ou atualiza uma chave de API no arquivo de credenciais.
    
    Args:
        key_name (str): Nome da chave.
        key_value (str): Valor da chave.
        
    Returns:
        bool: True se a operação foi bem-sucedida, False caso contrário.
    """
    try:
        # Carregar credenciais existentes
        credentials = load_credentials(force_reload=True)
        
        # Adicionar/atualizar a chave
        credentials[key_name] = key_value
        
        # Salvar de volta no arquivo
        ensure_credentials_dir()
        with open(CREDENTIALS_PATH, "w") as file:
            json.dump(credentials, file, indent=4)
        
        # Atualizar o cache e o timestamp
        global _last_modified_time, _credentials_cache
        _credentials_cache = credentials
        _last_modified_time = os.path.getmtime(CREDENTIALS_PATH)
        
        logger.info(f"Chave '{key_name}' adicionada/atualizada com sucesso.")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao adicionar/atualizar chave: {str(e)}")
        return False

def delete_api_key(key_name):
    """
    Exclui uma chave de API do arquivo de credenciais.
    
    Args:
        key_name (str): Nome da chave a ser excluída.
        
    Returns:
        bool: True se a operação foi bem-sucedida, False caso contrário.
    """
    try:
        # Carregar credenciais existentes
        credentials = load_credentials(force_reload=True)
        
        # Verificar se a chave existe
        if key_name not in credentials:
            logger.warning(f"Chave '{key_name}' não encontrada. Nenhuma ação realizada.")
            return False
        
        # Remover a chave
        del credentials[key_name]
        
        # Salvar de volta no arquivo
        with open(CREDENTIALS_PATH, "w") as file:
            json.dump(credentials, file, indent=4)
        
        # Atualizar o cache e o timestamp
        global _last_modified_time, _credentials_cache
        _credentials_cache = credentials
        _last_modified_time = os.path.getmtime(CREDENTIALS_PATH)
        
        logger.info(f"Chave '{key_name}' removida com sucesso.")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao remover chave: {str(e)}")
        return False

def get_credential(key_name, default=None):
    """
    Obtém uma credencial específica pelo nome.
    
    Args:
        key_name (str): Nome da chave.
        default: Valor padrão caso a chave não exista.
        
    Returns:
        O valor da chave ou o valor padrão.
    """
    credentials = load_credentials()
    return credentials.get(key_name, default)