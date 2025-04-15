import time
import logging
import json
import os
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# ✅ Importações corrigidas
from .exceptions import AccountVerificationError
from .config import timeouts
from .locators import verification_locators, account_locators, phone_locators, terms_locators

logger = logging.getLogger(__name__)


class AccountVerify:
    def __init__(self, driver, credentials, profile_name, phone_number):
        self.driver = driver
        self.credentials = credentials
        self.profile_name = profile_name
        self.phone_number = phone_number
        self.wait = WebDriverWait(driver, timeouts.DEFAULT_WAIT)
        # Flag para controlar se os dados já foram salvos
        self.credentials_saved = False
        # Flag para indicar que a verificação foi concluída
        self.verification_completed = False

    def verify_account(self) -> bool:
        """Verifica se a conta foi criada com sucesso e retorna o status."""
        try:
            logger.info("🔍 Verificando se a conta foi criada com sucesso...")
            time.sleep(5)
            current_url = self.driver.current_url

            if "myaccount.google.com" in current_url:
                logger.info(
                    "✅ Conta criada com sucesso! Redirecionado para Google Account.")
                success = self._redirect_to_gmail()
                self.verification_completed = success
                return success

            logger.warning(
                "⚠️ Não foi detectado redirecionamento para Google Account. Verificando Gmail manualmente...")
            success = self._redirect_to_gmail()
            self.verification_completed = success
            return success

        except Exception as e:
            logger.error(f"❌ Erro na verificação da conta: {str(e)}")
            raise AccountVerificationError(
                f"Erro ao verificar conta: {str(e)}")

    def _redirect_to_gmail(self) -> bool:
        """Redireciona para o Gmail e verifica login."""
        try:
            logger.info(
                "📧 Redirecionando para o Gmail para confirmar login...")
            self.driver.get("https://mail.google.com/")
            time.sleep(5)

            if "mail.google.com" in self.driver.current_url:
                logger.info(
                    "✅ Gmail carregado com sucesso! Conta operacional.")
                # NÃO salva as credenciais aqui - isso será feito explicitamente pela classe GmailCreator
                return True

            logger.warning(
                "⚠️ O Gmail não abriu corretamente. Verifique manualmente.")
            return False

        except TimeoutException:
            logger.error("❌ Timeout ao tentar acessar o Gmail.")
            return False

    def get_account_data(self):
        """Retorna os dados da conta já formatados, sem salvar."""
        if not self.verification_completed:
            logger.warning(
                "⚠️ Tentando obter dados sem verificação concluída!")
            return None

        return {
            "email": self.credentials["username"] + "@gmail.com",
            "password": self.credentials["password"],
            "phone": self.phone_number if self.phone_number else "unknown",
            "profile": self.profile_name if self.profile_name else "default_profile"
        }

    def save_gmail_account(self) -> bool:
        """Salva as credenciais com validação de dados."""
        try:
            if not all([self.phone_number, self.profile_name]):
                logger.error("❌ Dados incompletos para salvar conta")
                return False

            account_data = self.get_account_data()
            if not account_data:
                logger.error("❌ Falha ao obter dados da conta")
                return False

            # Validar dados críticos
            if account_data["phone"] == "unknown" or account_data["email"] == "unknown":
                logger.error("❌ Dados críticos ausentes ou inválidos")
                return False

            # Verificação de flag para evitar salvamentos duplicados
            if self.credentials_saved:
                logger.info(
                    "⏭️ Credenciais já foram salvas anteriormente. Ignorando.")
                return False

            if not self.verification_completed:
                logger.warning(
                    "⚠️ Tentando salvar credenciais sem verificação concluída!")
                return False

            # Obter dados formatados da conta
            email = account_data["email"]

            # Salvar diretamente com verificações rigorosas de duplicação
            credentials_path = "credentials/gmail.json"

            # Verificação explícita de duplicidade baseada no conteúdo do arquivo
            if os.path.exists(credentials_path) and os.path.getsize(credentials_path) > 0:
                # Verificar manualmente se o email já existe no arquivo
                try:
                    with open(credentials_path, "r") as file:
                        file_content = file.read().strip()
                        if email in file_content:
                            logger.warning(
                                f"⚠️ Email {email} já existe no arquivo (verificação de string). Ignorando duplicação.")
                            self.credentials_saved = True
                            return False

                        # Verificar com análise JSON
                        if file_content:
                            existing_accounts = json.loads(file_content)

                            # Verificar se não é lista (acontece às vezes)
                            if not isinstance(existing_accounts, list):
                                logger.warning(
                                    "⚠️ Arquivo de credenciais não é uma lista. Recriando arquivo.")
                                existing_accounts = []

                            # Verificar se o email já existe
                            for account in existing_accounts:
                                if account.get("email") == email:
                                    logger.warning(
                                        f"⚠️ Email {email} já existe no arquivo (verificação JSON). Ignorando duplicação.")
                                    self.credentials_saved = True
                                    return False
                except Exception as e:
                    logger.warning(
                        f"⚠️ Erro ao verificar duplicação: {str(e)}. Criando novo arquivo.")
                    # Remove arquivo corrompido se houver erro
                    os.remove(credentials_path)
                    existing_accounts = []
            else:
                # Arquivo não existe ou está vazio
                existing_accounts = []

            # Se chegou aqui, precisa adicionar os dados
            try:
                with open(credentials_path, "a+") as file:
                    file.seek(0)  # Move para o início para ler conteúdo
                    content = file.read().strip()

                    if not content:
                        # Arquivo vazio, inicializa com lista
                        file.seek(0)
                        file.truncate()  # Limpa o arquivo
                        file.write(json.dumps([account_data], indent=4))
                    else:
                        # Arquivo existe, adiciona ao final
                        file.seek(0)  # Move para o início para ler novamente
                        existing_accounts = json.loads(content)

                        # Verificação final antes de adicionar
                        if any(account.get("email") == email for account in existing_accounts):
                            logger.warning(
                                f"⚠️ Email {email} já existe no arquivo (verificação final). Ignorando duplicação.")
                            self.credentials_saved = True
                            return False

                        existing_accounts.append(account_data)

                        # Reescreve todo o arquivo
                        file.seek(0)
                        file.truncate()  # Limpa o arquivo
                        file.write(json.dumps(existing_accounts, indent=4))

                logger.info(
                    f"✅ Credenciais salvas com sucesso em {credentials_path}")
                self.credentials_saved = True
                return True

            except Exception as e:
                logger.error(f"❌ Erro ao salvar credenciais: {str(e)}")
                return False

        except Exception as e:
            logger.error(f"❌ Erro ao salvar conta: {str(e)}")
            return False
