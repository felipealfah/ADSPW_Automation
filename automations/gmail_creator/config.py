from dataclasses import dataclass, field
from typing import Dict, List
import logging
from functools import partial

# Função que retorna o dicionário de opções de gênero


def get_gender_options():
    return {
        "neutral": [
            "Rather not say",       # Inglês
            "Prefiro não informar",  # Português
            "Prefiero no decirlo",  # Espanhol
            "Je préfère ne pas le dire",  # Francês
            "Lieber nicht sagen"    # Alemão
        ],
        "male": [
            "Male",      # Inglês
            "Masculino",  # Português
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
    DEFAULT_WAIT: int = 30
    LONG_WAIT: int = 60
    VERY_LONG_WAIT: int = 120
    SMS_CODE_WAIT: int = 180
    INPUT_DELAY: float = 0.5
    ACTION_DELAY: float = 1.0
    PAGE_TRANSITION: float = 3.0
    CLICK_RETRY_DELAY: float = 2.0
    SESSION_CHECK_INTERVAL: float = 5.0
    BROWSER_STARTUP_EXTRA: float = 5.0


@dataclass
class SMSConfig:
    """Configurações relacionadas à verificação SMS."""
    MAX_SMS_RETRIEVAL_ATTEMPTS: int = 10
    SMS_RETRY_DELAY: int = 5
    COUNTRIES_PRIORITY: List[str] = field(
        default_factory=lambda: ["Brazil", "United States", "Canada", "Mexico"])
    MAX_PHONE_TRIES: int = 3
    REUSE_NUMBERS: bool = True


@dataclass
class AccountConfig:
    """Configurações relacionadas à conta."""
    MAX_USERNAME_ATTEMPTS: int = 3
    GMAIL_SIGNUP_URL: str = "https://accounts.google.com/signup/v2/webcreateaccount"
    GMAIL_URL: str = "https://mail.google.com"
    USERNAME_LENGTH_MIN: int = 6
    USERNAME_LENGTH_MAX: int = 30
    PASSWORD_MIN_LENGTH: int = 8
    BIRTH_YEAR_MIN: int = 1980
    BIRTH_YEAR_MAX: int = 2000

    # Opções de gênero multilíngues usando default_factory
    GENDER_OPTIONS: Dict[str, List[str]] = field(
        default_factory=get_gender_options)

    # Valor padrão: usar a opção neutra
    GENDER_DEFAULT: str = "neutral"

    # Configurações de segurança e estabilidade
    RETRY_ATTEMPTS: int = 3
    SESSION_CHECK_ENABLED: bool = True
    ENABLE_JAVASCRIPT_FALLBACK: bool = True
    BROWSER_RECOVERY_MODE: bool = True

    # Configurações de navegador (AdsPower)
    BROWSER_SETTINGS: Dict[str, bool] = field(default_factory=lambda: {
        "disable_extensions": True,
        "disable_gpu": True,
        "no_sandbox": True,
        "disable_dev_shm_usage": True,
        "disable_infobars": True,
        "disable_notifications": True,
        "window_size": "1280,800"
    })


@dataclass
class LogConfig:
    """Configurações de logging."""
    ENABLE_FILE_LOGGING: bool = True
    LOG_LEVEL: str = "INFO"
    LOG_FILE_MAX_SIZE: int = 10 * 1024 * 1024  # 10 MB
    LOG_FILE_BACKUP_COUNT: int = 5


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
