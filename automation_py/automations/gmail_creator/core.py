import time
import logging
from enum import Enum
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By

from powerads_api.browser_manager import BrowserManager
from .account_setup import AccountSetup
from .phone_verify import PhoneVerification
from .terms_handler import TermsHandler
from .account_verify import AccountVerify
from .exceptions import GmailCreationError, TermsAcceptanceError
from .config import timeouts, account_config, sms_config, log_config

logger = logging.getLogger(__name__)


class GmailCreationState(Enum):
    """Estados possíveis durante a criação da conta."""
    INITIAL = "initial"
    ACCOUNT_SETUP = "account_setup"
    PHONE_VERIFICATION = "phone_verification"
    TERMS_ACCEPTANCE = "terms_acceptance"
    ACCOUNT_VERIFICATION = "account_verification"
    COMPLETED = "completed"
    FAILED = "failed"


class GmailCreator:
    """Classe principal que gerencia o fluxo de criação da conta Gmail."""

    def __init__(self, browser_manager, credentials, sms_api=None, profile_name="default_profile"):
        self.browser_manager = browser_manager
        self.credentials = credentials
        self.sms_api = sms_api
        self.profile_name = profile_name if profile_name else "default_profile"
        self.driver = None
        self.phone_params = {}  # Mantido para compatibilidade, mas não usado externamente

        # Adicionar inicialização do phone_manager
        from apis.phone_manager import PhoneManager
        self.phone_manager = PhoneManager()

        # Configuração geral
        self.config = {
            "timeouts": timeouts,
            "account_config": account_config,
            "sms_config": sms_config,
            "log_config": log_config
        }

        self.state = GmailCreationState.INITIAL

    def initialize_browser(self, user_id: str) -> bool:
        """
        Inicializa o browser e configura o driver.

        Args:
            user_id: ID do perfil do AdsPower

        Returns:
            bool: True se a inicialização foi bem sucedida
        """
        try:
            if not self.browser_manager.ensure_browser_ready(user_id):
                logger.error(
                    "[ERRO] Falha ao garantir que o browser está pronto")
                return False

            self.driver = self.browser_manager.get_driver()
            if not self.driver:
                logger.error("[ERRO] Driver não disponível")
                return False

            # Limpar cache e cookies antes de iniciar a automação
            self._clear_browser_cache()

            self.wait = WebDriverWait(self.driver, timeouts.DEFAULT_WAIT)
            logger.info("[OK] Browser inicializado com sucesso")
            return True

        except Exception as e:
            logger.error(f"[ERRO] Erro ao inicializar browser: {str(e)}")
            return False

    def _clear_browser_cache(self):
        """
        Limpa o cache, cookies e dados de sessão do navegador.
        """
        try:
            logger.info("[INICIO] Limpando cache e cookies do navegador...")

            if not self.driver:
                logger.warning(
                    "[AVISO] Driver não disponível para limpar cache")
                return False

            # Método 1: Limpar cookies
            self.driver.delete_all_cookies()
            logger.info("[OK] Cookies removidos com sucesso")

            # Método 2: Acessar página de limpeza de cache do Chrome
            try:
                self.driver.get('chrome://settings/clearBrowserData')
                time.sleep(2)

                # Usar JavaScript para clicar nos botões necessários (não funciona em todos os casos)
                clear_script = """
                // Tentar encontrar e clicar no botão de limpar dados
                var buttons = document.querySelectorAll('cr-button');
                for (var i = 0; i < buttons.length; i++) {
                    if (buttons[i].innerText.includes('LIMPAR') || 
                        buttons[i].innerText.includes('CLEAR') ||
                        buttons[i].innerText.includes('Limpar') ||
                        buttons[i].innerText.includes('Clear')) {
                        buttons[i].click();
                        return true;
                    }
                }
                return false;
                """

                result = self.driver.execute_script(clear_script)
                if result:
                    logger.info(
                        "[OK] Botão de limpar cache clicado via JavaScript")
                    time.sleep(2)
                else:
                    logger.warning(
                        "[AVISO] Não foi possível clicar no botão de limpar cache via JavaScript")
            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao tentar limpar cache via página de configurações: {str(e)}")

            # Método 3: Usar comandos do Chrome DevTools Protocol
            try:
                # Limpar cache de aplicação
                self.driver.execute_cdp_cmd('Network.clearBrowserCache', {})
                # Limpar cookies
                self.driver.execute_cdp_cmd('Network.clearBrowserCookies', {})
                logger.info(
                    "[OK] Cache e cookies limpos via Chrome DevTools Protocol")
            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao limpar cache via CDP: {str(e)}")

            # Método 4: Navegar para uma página em branco para garantir que tudo foi limpo
            self.driver.get('about:blank')
            time.sleep(1)

            logger.info("[OK] Limpeza de cache e cookies concluída")
            return True
        except Exception as e:
            logger.error(
                f"[ERRO] Falha ao limpar cache do navegador: {str(e)}")
            return False

    def create_account(self, user_id: str):
        """
        Executa todo o fluxo de criação da conta Gmail.

        Args:
            user_id: ID do perfil do AdsPower

        Returns:
            tuple: (sucesso, dados_da_conta)
        """
        try:
            logger.info("[INICIO] Iniciando criação da conta Gmail...")

            # Verificar e limpar o arquivo de credenciais
            self._clean_credentials_file()

            # Verificar estrutura das credenciais para diagnóstico
            logger.info(
                f"[DIAGNÓSTICO] Credenciais recebidas: {self.credentials}")
            # Verificar especificamente se 'username' está nas credenciais
            if 'username' not in self.credentials:
                logger.error(
                    "[ERRO] Campo 'username' não encontrado nas credenciais")
                logger.info(
                    f"[DIAGNÓSTICO] Campos disponíveis: {list(self.credentials.keys())}")

            # Inicializar o browser primeiro
            if not self.initialize_browser(user_id):
                raise GmailCreationError(
                    "[ERRO] Falha ao inicializar o browser")

            # Contador para tentativas de criação completa da conta
            complete_attempts = 0
            max_complete_attempts = 2

            while complete_attempts < max_complete_attempts:
                complete_attempts += 1
                logger.info(
                    f"[ATUALIZANDO] Tentativa {complete_attempts} de {max_complete_attempts} para criar conta completa")

                # Limpar cache antes de cada tentativa para garantir um estado limpo
                self._clear_browser_cache()

                try:
                    # Passo 1: Configuração inicial da conta
                    self.state = GmailCreationState.ACCOUNT_SETUP
                    account_setup = AccountSetup(self.driver, self.credentials)
                    if not account_setup.start_setup():
                        raise GmailCreationError(
                            "[ERRO] Falha na configuração inicial da conta.")

                    # Passo 2: Verificação de telefone
                    self.state = GmailCreationState.PHONE_VERIFICATION
                    phone_verify = PhoneVerification(self.driver, self.sms_api)

                    # Sempre fornecer a instância do phone_manager
                    phone_verify.phone_manager = self.phone_manager

                    # Variáveis para controle de fluxo
                    phone_verification_success = False
                    phone_data = None

                    # Verificar se a tela de verificação de telefone está presente
                    if phone_verify._check_phone_screen():
                        logger.info(
                            " Tela de verificação de telefone detectada.")
                        # Se temos parâmetros de telefone para reutilização
                        if self.phone_params and isinstance(self.phone_params, dict) and self.phone_params.get('reuse_number'):
                            logger.info(
                                f" Configurando reutilização de número: {self.phone_params.get('phone_number')}")
                            phone_verify.reuse_number = True
                            phone_verify.predefined_number = self.phone_params.get(
                                'phone_number')
                            phone_verify.predefined_activation_id = self.phone_params.get(
                                'activation_id')
                            phone_verify.predefined_country_code = self.phone_params.get(
                                'country_code')

                        # Esta chamada inclui todo o processo de verificação por SMS
                        # Usar execute_with_retry para maior robustez
                        def verify_phone():
                            return phone_verify.handle_verification()

                        phone_verification_success = self.phone_manager.execute_with_retry(
                            verify_phone, max_retries=2, retry_delay=3)

                        if not phone_verification_success:
                            logger.warning(
                                "[AVISO] Falha na verificação de telefone. Tentando reiniciar processo...")
                            # Recarregar a página de início e tentar novamente em uma nova iteração
                            self.driver.get(
                                "https://accounts.google.com/lifecycle/steps/signup/name?continue=https://mail.google.com/mail/&dsh=S-684862571:1747225782083306&ec=asw-gmail-globalnav-create&flowEntry=SignUp&flowName=GlifWebSignIn&service=mail&theme=glif&TL=AArrULSuexEtzK3xne4xZ1R55BK2JV85MTLQAXOsa0vHEkq859tMrB_ByuxzdQ4B")
                            time.sleep(5)
                            continue  # Reinicia o processo completo

                        # Captura os dados do telefone verificado
                        phone_data = phone_verify.get_current_phone_data()
                        if not phone_data:
                            logger.error(
                                "[ERRO] Falha ao obter dados do telefone após verificação")
                            continue  # Tenta novamente o processo completo
                    else:
                        logger.info(
                            " Tela de verificação de telefone não detectada, pulando para aceitação dos termos.")
                        # Se não houver verificação de telefone, definimos valores padrão
                        phone_data = {
                            'phone_number': self.phone_params.get('phone_number') if self.phone_params else None,
                            'country_code': self.phone_params.get('country_code') if self.phone_params else None,
                            'activation_id': self.phone_params.get('activation_id') if self.phone_params else None,
                            'country_name': "unknown"
                        }
                        phone_verification_success = True

                    # Extrair dados do telefone
                    phone_number = phone_data.get('phone_number')
                    country_code = phone_data.get('country_code')
                    activation_id = phone_data.get('activation_id')
                    country_name = phone_data.get('country_name')

                    # Passo 3: Aceitação dos Termos
                    self.state = GmailCreationState.TERMS_ACCEPTANCE
                    # Obter o email de recuperação das credenciais, se disponível
                    recovery_email = self.credentials.get('recovery_email')

                    # Inicializar terms_handler com o email de recuperação
                    terms_handler = TermsHandler(
                        self.driver, recovery_email=recovery_email)

                    # Usar execute_with_retry para maior robustez
                    def accept_terms():
                        return terms_handler.handle_terms_acceptance()

                    terms_accepted = self.phone_manager.execute_with_retry(
                        accept_terms, max_retries=2, retry_delay=2)

                    if not terms_accepted:
                        logger.warning(
                            "[AVISO] Falha na aceitação dos termos. Tentando reiniciar processo...")
                        # Recarregar a página de início e tentar novamente
                        self.driver.get("https://accounts.google.com/signup")
                        time.sleep(5)
                        continue  # Reinicia o processo completo

                    # Passo 4: Verificação final da conta
                    self.state = GmailCreationState.ACCOUNT_VERIFICATION
                    account_verify = AccountVerify(
                        self.driver,
                        self.credentials,
                        profile_name=self.profile_name,
                        phone_number=phone_number
                    )

                    # Usar execute_with_retry para maior robustez
                    def verify_account():
                        return account_verify.verify_account()

                    account_verified = self.phone_manager.execute_with_retry(
                        verify_account, max_retries=2, retry_delay=2)

                    if not account_verified:
                        logger.warning(
                            "[AVISO] Falha na verificação final da conta. Tentando reiniciar processo...")
                        # Recarregar a página de início e tentar novamente
                        self.driver.get("https://accounts.google.com/signup")
                        time.sleep(5)
                        continue  # Reinicia o processo completo

                    # Se chegou aqui, tudo deu certo!
                    self.state = GmailCreationState.COMPLETED

                    # VERIFICAÇÃO CRUCIAL: Verificar o email real que foi criado
                    real_email = self._get_actual_email_from_page()

                    # Se conseguimos obter o email real da página, usá-lo em vez do email das credenciais
                    email_to_use = real_email if real_email else self.credentials[
                        "username"] + "@gmail.com"

                    if real_email and real_email != (self.credentials["username"] + "@gmail.com"):
                        logger.warning(
                            f"[AVISO] Email real criado ({real_email}) é diferente do email nas credenciais ({self.credentials['username']}@gmail.com)")

                    #  Retornar os dados completos da conta
                    account_data = {
                        "first_name": self.credentials["first_name"],
                        "last_name": self.credentials["last_name"],
                        "email": email_to_use,
                        "password": self.credentials["password"],
                        "phone": phone_number,
                        "country_code": country_code,
                        "country_name": country_name,
                        "activation_id": activation_id,
                        "profile": self.profile_name,
                        "creation_date": time.strftime("%Y-%m-%d %H:%M:%S")
                    }

                    # Garantir que as credenciais sejam salvas corretamente
                    self._ensure_credentials_saved(account_data)

                    logger.info(
                        f"[OK] Conta criada com sucesso! Retornando os dados: {account_data}")
                    return True, account_data

                except Exception as inner_e:
                    logger.error(
                        f"[ERRO] Erro durante a tentativa {complete_attempts}: {str(inner_e)}")
                    if complete_attempts < max_complete_attempts:
                        logger.info(
                            "[ATUALIZANDO] Reiniciando processo completo...")
                        self.driver.get("https://accounts.google.com/signup")
                        time.sleep(5)
                    else:
                        logger.error(
                            f"[ERRO] Todas as {max_complete_attempts} tentativas completas falharam")
                        raise GmailCreationError(
                            f"Falha após {max_complete_attempts} tentativas completas")

            # Se chegou aqui, todas as tentativas falharam
            return False, None

        except GmailCreationError as e:
            logger.error(f"[ALERTA] Erro durante o processo: {str(e)}")
            return False, None

        except Exception as e:
            logger.error(f"[ERRO] Erro inesperado: {str(e)}")
            return False, None

    def _get_actual_email_from_page(self):
        """
        Obtém o email real que foi criado a partir da página atual.

        Returns:
            str: O email real ou None se não for possível obter
        """
        try:
            # Aguardar um pouco para garantir que a página carregou completamente
            time.sleep(2)

            # Tentar diferentes métodos para encontrar o email na página

            # Método 1: Verificar se estamos na página do Gmail e obter o email do perfil
            try:
                # Verificar se estamos na página do Gmail
                if "mail.google.com" in self.driver.current_url:
                    # Clicar no avatar para mostrar o email
                    avatar_selectors = [
                        "//a[contains(@aria-label, 'Conta')]",
                        "//a[contains(@aria-label, 'Account')]",
                        "//a[contains(@href, 'accounts.google.com')]",
                        "//img[contains(@alt, 'Foto do perfil')]",
                        "//img[contains(@alt, 'Profile picture')]"
                    ]

                    for selector in avatar_selectors:
                        try:
                            avatar = self.driver.find_element(
                                By.XPATH, selector)
                            avatar.click()
                            time.sleep(1)
                            break
                        except:
                            continue

                    # Tentar encontrar o email no popup
                    email_selectors = [
                        "//div[contains(@class, 'gb_yb')]",
                        "//div[contains(text(), '@gmail.com')]",
                        "//a[contains(text(), '@gmail.com')]",
                        "//span[contains(text(), '@gmail.com')]"
                    ]

                    for selector in email_selectors:
                        try:
                            email_element = self.driver.find_element(
                                By.XPATH, selector)
                            email = email_element.text.strip()
                            if "@gmail.com" in email:
                                logger.info(
                                    f"[OK] Email real encontrado na interface: {email}")
                                return email
                        except:
                            continue
            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao tentar obter email do perfil do Gmail: {str(e)}")

            # Método 2: Verificar na URL
            try:
                current_url = self.driver.current_url
                if "mail.google.com" in current_url and "authuser=" in current_url:
                    # Tentar extrair o email da URL
                    import re
                    email_match = re.search(r"authuser=([^&]+)", current_url)
                    if email_match:
                        email = email_match.group(1)
                        if "@" in email:
                            logger.info(
                                f"[OK] Email real encontrado na URL: {email}")
                            return email
            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao tentar obter email da URL: {str(e)}")

            # Método 3: Verificar no código fonte da página
            try:
                page_source = self.driver.page_source
                import re
                # Procurar padrões de email no código fonte
                email_patterns = [
                    r'([a-zA-Z0-9_.+-]+@gmail\.com)',
                    r'email:"([^"]+@gmail\.com)"',
                    r'user:"([^"]+@gmail\.com)"'
                ]

                for pattern in email_patterns:
                    matches = re.findall(pattern, page_source)
                    if matches:
                        for match in matches:
                            if "@gmail.com" in match:
                                logger.info(
                                    f"[OK] Email real encontrado no código fonte: {match}")
                                return match
            except Exception as e:
                logger.warning(
                    f"[AVISO] Erro ao tentar obter email do código fonte: {str(e)}")

            logger.warning(
                "[AVISO] Não foi possível obter o email real da página")
            return None

        except Exception as e:
            logger.error(f"[ERRO] Erro ao tentar obter o email real: {str(e)}")
            return None

    def _ensure_credentials_saved(self, account_data):
        """
        Garante que as credenciais sejam salvas corretamente no arquivo JSON.

        Args:
            account_data: Dados da conta a serem salvos
        """
        try:
            import json
            import os
            from datetime import datetime

            # Caminho para o arquivo de credenciais
            credentials_path = "credentials/gmail.json"

            # Garantir que o diretório existe
            os.makedirs(os.path.dirname(credentials_path), exist_ok=True)

            # Verificar se o arquivo existe e tem conteúdo válido
            existing_accounts = []
            if os.path.exists(credentials_path) and os.path.getsize(credentials_path) > 0:
                try:
                    with open(credentials_path, "r") as file:
                        content = file.read().strip()
                        if content:
                            existing_accounts = json.loads(content)

                            # Verificar se é uma lista
                            if not isinstance(existing_accounts, list):
                                logger.warning(
                                    "[AVISO] Arquivo de credenciais não contém uma lista válida. Recriando.")
                                existing_accounts = []
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro ao ler arquivo de credenciais: {str(e)}. Recriando.")
                    existing_accounts = []

            # Verificar se a conta já existe no arquivo
            email = account_data.get("email")
            account_exists = False

            for i, account in enumerate(existing_accounts):
                if account.get("email") == email:
                    account_exists = True
                    # Atualizar a conta existente com os novos dados
                    existing_accounts[i] = account_data
                    logger.info(
                        f"[OK] Conta {email} atualizada no arquivo de credenciais")
                    break

            # Se a conta não existe, adicionar
            if not account_exists:
                # Garantir que temos uma data de criação
                if "creation_date" not in account_data:
                    account_data["creation_date"] = datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S")

                existing_accounts.append(account_data)
                logger.info(
                    f"[OK] Conta {email} adicionada ao arquivo de credenciais")

            # Salvar o arquivo atualizado
            with open(credentials_path, "w") as file:
                json.dump(existing_accounts, file, indent=4)

            logger.info(
                f"[OK] Arquivo de credenciais salvo com sucesso: {credentials_path}")

            # Verificar se o arquivo foi salvo corretamente
            if os.path.exists(credentials_path) and os.path.getsize(credentials_path) > 0:
                logger.info(
                    f"[OK] Verificação: arquivo de credenciais existe e tem conteúdo")
            else:
                logger.error(
                    f"[ERRO] Verificação: problema ao salvar arquivo de credenciais")

        except Exception as e:
            logger.error(f"[ERRO] Falha ao salvar credenciais: {str(e)}")

    def _clean_credentials_file(self):
        """
        Verifica e limpa o arquivo de credenciais JSON, removendo entradas inválidas ou duplicadas.
        """
        try:
            import json
            import os
            from datetime import datetime

            logger.info(
                "[INICIO] Verificando e limpando arquivo de credenciais...")

            # Caminho para o arquivo de credenciais
            credentials_path = "credentials/gmail.json"

            # Verificar se o arquivo existe
            if not os.path.exists(credentials_path):
                logger.info(
                    "[INFO] Arquivo de credenciais não existe. Criando diretório...")
                os.makedirs(os.path.dirname(credentials_path), exist_ok=True)
                # Criar arquivo vazio com lista vazia
                with open(credentials_path, "w") as file:
                    json.dump([], file, indent=4)
                logger.info(
                    "[OK] Arquivo de credenciais criado com lista vazia")
                return True

            # Verificar se o arquivo está vazio
            if os.path.getsize(credentials_path) == 0:
                logger.warning(
                    "[AVISO] Arquivo de credenciais está vazio. Inicializando com lista vazia.")
                with open(credentials_path, "w") as file:
                    json.dump([], file, indent=4)
                logger.info(
                    "[OK] Arquivo de credenciais inicializado com lista vazia")
                return True

            # Ler o arquivo de credenciais
            try:
                with open(credentials_path, "r") as file:
                    content = file.read().strip()
                    if not content:
                        logger.warning(
                            "[AVISO] Arquivo de credenciais tem conteúdo vazio. Inicializando com lista vazia.")
                        with open(credentials_path, "w") as f:
                            json.dump([], f, indent=4)
                        return True

                    try:
                        accounts = json.loads(content)
                    except json.JSONDecodeError as e:
                        logger.error(
                            f"[ERRO] Arquivo de credenciais contém JSON inválido: {str(e)}. Recriando arquivo.")
                        with open(credentials_path, "w") as f:
                            json.dump([], f, indent=4)
                        return True

                    # Verificar se é uma lista
                    if not isinstance(accounts, list):
                        logger.warning(
                            "[AVISO] Arquivo de credenciais não contém uma lista. Recriando arquivo.")
                        with open(credentials_path, "w") as f:
                            json.dump([], f, indent=4)
                        return True

                    # Verificar e limpar entradas inválidas ou duplicadas
                    valid_accounts = []
                    email_set = set()

                    for account in accounts:
                        # Verificar se é um dicionário
                        if not isinstance(account, dict):
                            logger.warning(
                                f"[AVISO] Entrada inválida encontrada (não é um dicionário): {account}")
                            continue

                        # Verificar se tem email
                        email = account.get("email")
                        if not email or not isinstance(email, str) or "@" not in email:
                            logger.warning(
                                f"[AVISO] Conta sem email válido encontrada: {account}")
                            continue

                        # Verificar se é duplicado
                        if email in email_set:
                            logger.warning(
                                f"[AVISO] Email duplicado encontrado: {email}")
                            continue

                        # Adicionar à lista de contas válidas
                        email_set.add(email)
                        valid_accounts.append(account)

                    # Salvar arquivo limpo
                    if len(valid_accounts) != len(accounts):
                        logger.info(
                            f"[INFO] Removidas {len(accounts) - len(valid_accounts)} entradas inválidas ou duplicadas")
                        with open(credentials_path, "w") as file:
                            json.dump(valid_accounts, file, indent=4)
                        logger.info(
                            "[OK] Arquivo de credenciais limpo e salvo")

                    logger.info(
                        f"[OK] Verificação concluída. Arquivo contém {len(valid_accounts)} contas válidas")
                    return True

            except Exception as e:
                logger.error(
                    f"[ERRO] Erro ao verificar arquivo de credenciais: {str(e)}")
                # Em caso de erro, tentar recriar o arquivo
                try:
                    with open(credentials_path, "w") as file:
                        json.dump([], file, indent=4)
                    logger.info(
                        "[OK] Arquivo de credenciais recriado após erro")
                    return True
                except Exception as e2:
                    logger.error(
                        f"[ERRO] Falha ao recriar arquivo de credenciais: {str(e2)}")
                    return False

        except Exception as e:
            logger.error(
                f"[ERRO] Falha ao limpar arquivo de credenciais: {str(e)}")
            return False
