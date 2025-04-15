from dataclasses import dataclass, field
from typing import Dict, List
import logging
from functools import partial

# Função que retorna o dicionário de opções de gênero
def get_gender_options():
    return {
        "neutral": [
            "Rather not say",       # Inglês
            "Prefiro não informar", # Português
            "Prefiero no decirlo",  # Espanhol
            "Je préfère ne pas le dire", # Francês
            "Lieber nicht sagen"    # Alemão
        ],
        "male": [
            "Male",      # Inglês
            "Masculino", # Português
            "Hombre",    # Espanhol
            "Homme",     # Francês
            "Männlich"   # Alemão
        ],
        "female": [
            "Female",    # Inglês
            "Feminino",  # Português
            "Mujer",     # Espanhol
            "Femme",     # Francês
            "Weiblich"   # Alemão
        ]
    }

@dataclass
class TimeoutConfig:
    """Configurações de timeout para diferentes operações."""
    DEFAULT_WAIT: int = 20
    ELEMENT_WAIT: int = 10
    PAGE_LOAD_WAIT: int = 30
    SMS_WAIT: int = 120
    RETRY_INTERVAL: int = 10

@dataclass
class SMSConfig:
    """Configurações relacionadas à verificação SMS."""
    MAX_SMS_ATTEMPTS: int = 3
    MAX_RETRY_ATTEMPTS: int = 12
    SERVICE_NAME: str = "go"
    RETRY_INTERVAL: int = 10

@dataclass
class AccountConfig:
    """Configurações relacionadas à conta."""
    MAX_USERNAME_ATTEMPTS: int = 5
    GMAIL_SIGNUP_URL: str = "https://accounts.google.com/signup/v2/webcreateaccount"
    GMAIL_URL: str = "https://mail.google.com"
    
    # Opções de gênero multilíngues usando default_factory
    GENDER_OPTIONS: Dict[str, List[str]] = field(default_factory=get_gender_options)
    
    # Valor padrão: usar a opção neutra
    GENDER_DEFAULT: str = "neutral"

@dataclass
class LogConfig:
    """Configurações de logging."""
    LOG_FILE: str = "credentials/automation_logs.log"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_LEVEL: str = "INFO"

# Instâncias das configurações para uso fácil
timeouts = TimeoutConfig()
sms_config = SMSConfig()
account_config = AccountConfig()
log_config = LogConfig()

# Configuração do log com timestamp e separação por conta criada
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
LOG_FILE = "logs/gmail_automation.log"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger(__name__)