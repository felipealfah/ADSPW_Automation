import time
import logging
import json
import os
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# [OK] Importações corrigidas
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
            logger.info(
                "[BUSCA] Verificando se a conta foi criada com sucesso...")
            time.sleep(5)
            current_url = self.driver.current_url

            if "myaccount.google.com" in current_url:
                logger.info(
                    "[OK] Conta criada com sucesso! Redirecionado para Google Account.")
                success = self._redirect_to_gmail()
                self.verification_completed = success
                return success

            logger.warning(
                "[AVISO] Não foi detectado redirecionamento para Google Account. Verificando Gmail manualmente...")
            success = self._redirect_to_gmail()
            self.verification_completed = success
            return success

        except Exception as e:
            logger.error(f"[ERRO] Erro na verificação da conta: {str(e)}")
            raise AccountVerificationError(
                f"Erro ao verificar conta: {str(e)}")

    def _redirect_to_gmail(self) -> bool:
        """Redireciona para o Gmail e verifica login."""
        try:
            logger.info(
                " Redirecionando para o Gmail para confirmar login...")
            self.driver.get("https://mail.google.com/")
            time.sleep(5)

            if "mail.google.com" in self.driver.current_url:
                logger.info(
                    "[OK] Gmail carregado com sucesso! Conta operacional.")
                # NÃO salva as credenciais aqui - isso será feito explicitamente pela classe GmailCreator
                return True

            logger.warning(
                "[AVISO] O Gmail não abriu corretamente. Verifique manualmente.")
            return False

        except TimeoutException:
            logger.error("[ERRO] Timeout ao tentar acessar o Gmail.")
            return False

    def get_account_data(self):
        """Retorna os dados da conta já formatados, sem salvar."""
        if not self.verification_completed:
            logger.warning(
                "[AVISO] Tentando obter dados sem verificação concluída!")
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
                logger.error("[ERRO] Dados incompletos para salvar conta")
                return False

            account_data = self.get_account_data()
            if not account_data:
                logger.error("[ERRO] Falha ao obter dados da conta")
                return False

            # Validar dados críticos
            if account_data["phone"] == "unknown" or account_data["email"] == "unknown":
                logger.error("[ERRO] Dados críticos ausentes ou inválidos")
                return False

            # Verificação de flag para evitar salvamentos duplicados
            if self.credentials_saved:
                logger.info(
                    "⏭ Credenciais já foram salvas anteriormente. Ignorando.")
                return False

            if not self.verification_completed:
                logger.warning(
                    "[AVISO] Tentando salvar credenciais sem verificação concluída!")
                return False

            # Obter dados formatados da conta
            email = account_data["email"]

            # Salvar diretamente com verificações rigorosas de duplicação
            credentials_path = "credentials/gmail.json"

            # Garantir que o diretório existe
            os.makedirs(os.path.dirname(credentials_path), exist_ok=True)

            # Verificar explícita de duplicidade baseada no conteúdo do arquivo
            existing_accounts = []

            if os.path.exists(credentials_path) and os.path.getsize(credentials_path) > 0:
                # Verificar manualmente se o email já existe no arquivo
                try:
                    with open(credentials_path, "r") as file:
                        file_content = file.read().strip()
                        if email in file_content:
                            logger.warning(
                                f"[AVISO] Email {email} já existe no arquivo (verificação de string). Ignorando duplicação.")
                            self.credentials_saved = True
                            return False

                        # Verificar com análise JSON
                        if file_content:
                            existing_accounts = json.loads(file_content)

                            # Verificar se não é lista (acontece às vezes)
                            if not isinstance(existing_accounts, list):
                                logger.warning(
                                    "[AVISO] Arquivo de credenciais não é uma lista. Recriando arquivo.")
                                existing_accounts = []

                            # Verificar se o email já existe
                            for account in existing_accounts:
                                if account.get("email") == email:
                                    logger.warning(
                                        f"[AVISO] Email {email} já existe no arquivo (verificação JSON). Ignorando duplicação.")
                                    self.credentials_saved = True
                                    return False
                except Exception as e:
                    logger.warning(
                        f"[AVISO] Erro ao verificar duplicação: {str(e)}. Criando novo arquivo.")
                    # Remove arquivo corrompido se houver erro
                    os.remove(credentials_path)
                    existing_accounts = []

            # Adicionar informações adicionais ao account_data
            from datetime import datetime
            account_data["creation_date"] = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S")

            # Adicionar dados do perfil completos
            account_data["profile_name"] = self.profile_name

            # Adicionar nome e sobrenome se disponíveis nas credenciais
            if "first_name" in self.credentials:
                account_data["first_name"] = self.credentials["first_name"]
            if "last_name" in self.credentials:
                account_data["last_name"] = self.credentials["last_name"]

            # Adicionar país se disponível
            if "country_name" not in account_data and "country_name" in self.credentials:
                account_data["country_name"] = self.credentials["country_name"]

            # Se chegou aqui, precisa adicionar os dados
            try:
                # Adicionar a nova conta à lista
                existing_accounts.append(account_data)

                # Salvar o arquivo atualizado
                with open(credentials_path, "w") as file:
                    json.dump(existing_accounts, file, indent=4)

                logger.info(
                    f"[OK] Credenciais salvas com sucesso em {credentials_path}")

                # Verificar se o arquivo foi salvo corretamente
                if os.path.exists(credentials_path) and os.path.getsize(credentials_path) > 0:
                    logger.info(
                        f"[OK] Verificação: arquivo de credenciais existe e tem conteúdo")
                else:
                    logger.error(
                        f"[ERRO] Verificação: problema ao salvar arquivo de credenciais")

                self.credentials_saved = True
                return True

            except Exception as e:
                logger.error(f"[ERRO] Erro ao salvar credenciais: {str(e)}")
                return False

        except Exception as e:
            logger.error(f"[ERRO] Erro ao salvar conta: {str(e)}")
            return False
