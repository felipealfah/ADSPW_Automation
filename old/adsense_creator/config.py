from dataclasses import dataclass, field
from typing import Dict, List
import logging
import os


@dataclass
class TimeoutConfig:
    """Configurações de timeout para diferentes operações."""
    DEFAULT_WAIT: int = 30
    LONG_WAIT: int = 60
    VERY_LONG_WAIT: int = 120
    INPUT_DELAY: float = 0.5
    ACTION_DELAY: float = 1.0
    PAGE_TRANSITION: float = 3.0
    CLICK_RETRY_DELAY: float = 2.0
    SESSION_CHECK_INTERVAL: float = 5.0
    BROWSER_STARTUP_EXTRA: float = 5.0
    WEBSITE_VERIFICATION_WAIT: int = 180  # Tempo de espera para verificação do site


@dataclass
class AccountConfig:
    """Configurações relacionadas à conta AdSense."""
    # URL específica para inscrição do AdSense
    ADSENSE_URL: str = "https://adsense.google.com/adsense/signup/create?subid=in-en-dr-dr-sa-a-dr&referer=https://adsense.google.com/start/&sac=true&pli=1&authuser=0"
    ADSENSE_DASHBOARD_URL: str = "https://www.google.com/adsense/new"
    MAX_RETRY_ATTEMPTS: int = 3

    # Categorias de site disponíveis para seleção
    WEBSITE_CATEGORIES: List[str] = field(default_factory=lambda: [
        "Arts & Entertainment",
        "Autos & Vehicles",
        "Beauty & Fitness",
        "Books & Literature",
        "Business & Industrial",
        "Computers & Electronics",
        "Finance",
        "Food & Drink",
        "Games",
        "Health",
        "Hobbies & Leisure",
        "Home & Garden",
        "Internet & Telecom",
        "Jobs & Education",
        "Law & Government",
        "News",
        "Online Communities",
        "People & Society",
        "Pets & Animals",
        "Real Estate",
        "Reference",
        "Science",
        "Shopping",
        "Sports",
        "Travel"
    ])

    # Idiomas disponíveis para seleção
    WEBSITE_LANGUAGES: List[str] = field(default_factory=lambda: [
        "English",
        "Portuguese",
        "Spanish",
        "French",
        "German",
        "Italian",
        "Dutch",
        "Russian",
        "Arabic",
        "Chinese",
        "Japanese",
        "Korean"
    ])

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
account_config = AccountConfig()
log_config = LogConfig()

# Configuração do log com timestamp
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
LOG_FILE = "logs/adsense_automation.log"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger(__name__)

# Garantir que o diretório de logs exista e adicionar handler específico
log_dir = os.path.dirname(LOG_FILE)
if log_dir and not os.path.exists(log_dir):
    os.makedirs(log_dir, exist_ok=True)
from logging import Formatter, FileHandler
# Cria e configura handler para o arquivo de log do AdSense
file_handler = FileHandler(LOG_FILE, mode='a')
file_handler.setLevel(log_config.LOG_LEVEL)
file_handler.setFormatter(Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
logging.getLogger().addHandler(file_handler)
