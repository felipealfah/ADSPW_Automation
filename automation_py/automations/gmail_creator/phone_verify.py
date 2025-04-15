from enum import Enum
from dataclasses import dataclass
from typing import Optional
import time
import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import requests

from .exceptions import (
    PhoneVerificationError,
    SMSServiceError,
    ElementInteractionError
)
from .config import timeouts
from .locators import phone_locators

logger = logging.getLogger(__name__)


class VerificationState(Enum):
    """Estados possíveis da verificação de número."""
    INITIAL = "initial"
    NUMBER_REQUESTED = "number_requested"
    NUMBER_RECEIVED = "number_received"
    NUMBER_SUBMITTED = "number_submitted"
    WAITING_SMS = "waiting_sms"
    SMS_RECEIVED = "sms_received"
    RESENDING_SMS = "resending_sms"
    FAILED_SMS = "failed_sms"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ActivationInfo:
    """Informações da ativação atual."""
    activation_id: str
    phone_number: str
    country_code: str
    start_time: float
    state: VerificationState
    attempts: int = 0
    max_lifetime: int = 1200  # 20 minutos

    def is_expired(self) -> bool:
        """Verifica se o número expirou."""
        return (time.time() - self.start_time) > self.max_lifetime


class PhoneVerification:
    MAX_PHONE_ATTEMPTS = 3  # 🔹 Máximo de tentativas por país

    def __init__(self, driver, sms_api):
        self.driver = driver
        self.sms_api = sms_api
        self.wait = WebDriverWait(driver, timeouts.DEFAULT_WAIT)
        self.current_activation: Optional[ActivationInfo] = None
        self.failed_numbers = set()
        self.used_countries = set()
        self.state = VerificationState.INITIAL
        self._available_numbers = {}
        self.phone_number = None
        self.phone_manager = None  # Inicialize o gerenciador de números
        self.predefined_number = None
        self.predefined_country_code = None
        self.predefined_activation_id = None

    def handle_verification(self) -> bool:
        """Processo principal de verificação de telefone com tratamento robusto de erro."""
        try:
            logger.info("📞 Iniciando processo de verificação de telefone...")

            if not self._check_phone_screen():
                logger.info(
                    "📌 Tela de verificação de telefone não encontrada. Tentando garantir tela de verificação...")
                if not self._ensure_phone_verification_screen(max_attempts=3):
                    logger.error(
                        "❌ Não foi possível acessar a tela de verificação de telefone.")
                    return False

            if not self._validate_initial_conditions():
                return False

            # Contador de tentativas explícito
            attempt_count = 0
            success = False

            while attempt_count < self.MAX_PHONE_ATTEMPTS:
                attempt_count += 1
                logger.info(
                    f"🔄 Tentativa {attempt_count} de {self.MAX_PHONE_ATTEMPTS} para verificação de telefone")

                # Garantir que estamos na tela correta antes de cada tentativa
                if attempt_count > 1:  # Não precisa na primeira tentativa pois já verificamos acima
                    if not self._ensure_phone_verification_screen():
                        logger.error(
                            "❌ Não foi possível acessar a tela de verificação de telefone.")
                        continue  # Tenta a próxima iteração

                try:
                    # Se conseguir concluir um ciclo completo, retorna sucesso
                    if self._try_verification_cycle():
                        logger.info(
                            f"✅ Verificação concluída com sucesso na tentativa {attempt_count}")
                        success = True
                        break

                    # Se chegou aqui, a tentativa falhou mas de forma controlada
                    logger.warning(
                        f"⚠️ Tentativa {attempt_count} falhou. {'Tentando novamente...' if attempt_count < self.MAX_PHONE_ATTEMPTS else 'Sem mais tentativas.'}")

                except Exception as e:
                    # Captura qualquer exceção não tratada durante o ciclo
                    logger.error(
                        f"❌ Erro na tentativa {attempt_count}: {str(e)}")
                    # Continua para a próxima tentativa se ainda houver tentativas restantes

                # Pequena pausa entre tentativas
                if attempt_count < self.MAX_PHONE_ATTEMPTS:
                    time.sleep(2)

            if not success:
                logger.error(
                    f"🚨 Todas as {self.MAX_PHONE_ATTEMPTS} tentativas de verificação falharam.")
                return False

            return success

        except Exception as e:
            logger.error(f"❌ Erro geral na verificação de telefone: {str(e)}")
            # Não cancelar o número aqui se a verificação foi bem-sucedida
            if self.state != VerificationState.COMPLETED:
                self._cancel_current_number()
            return False
        finally:
            self._ensure_final_cleanup()

    def _validate_initial_conditions(self) -> bool:
        """Valida condições antes de iniciar a verificação."""
        try:
            # Verificar se phone_manager está inicializado
            if not self.phone_manager:
                logger.error(
                    "❌ phone_manager não está inicializado. Verifique se foi corretamente configurado.")
                return False

            # Verificar saldo
            balance = self.sms_api.get_balance()
            if balance is None or balance <= 0:
                logger.error("⚠️ Saldo insuficiente para verificação.")
                return False

            if not self._check_number_availability():
                logger.error("⚠️ Nenhum número disponível.")
                return False

            return True
        except Exception as e:
            logger.error(f"❌ Erro na validação inicial: {str(e)}")
            return False

    def _check_phone_screen(self) -> bool:
        """Verifica se a tela de verificação de telefone está presente."""
        try:
            self.wait.until(EC.presence_of_element_located(
                (By.XPATH, phone_locators.PHONE_INPUT)))
            logger.info("✅ Tela de verificação de telefone detectada.")
            return True
        except TimeoutException:
            return False

    def _ensure_phone_verification_screen(self, max_attempts=2) -> bool:
        """Garante que estamos na tela de verificação de telefone."""
        for attempt in range(max_attempts):
            try:
                # Primeiro verificar se já estamos na tela correta usando o método existente
                if self._check_phone_screen():
                    logger.info(
                        "📱 Já estamos na tela de verificação de telefone. Continuando...")
                    return True

                # Se não estiver na tela correta, verificar URL atual
                current_url = self.driver.current_url
                logger.warning(f"⚠️ URL atual: {current_url}")

                # Tentar navegar para a URL correta - esta pode precisar ser ajustada
                # dependendo de como seu fluxo de criação de conta funciona
                self.driver.get(
                    "https://accounts.google.com/signup/v2/webgradsidvphone")
                time.sleep(5)

                # Verificar novamente se estamos na tela correta
                if self._check_phone_screen():
                    logger.info(
                        "📱 Navegação bem-sucedida para a tela de verificação de telefone.")
                    return True

                # Se ainda não estiver na tela correta, tentar outra abordagem
                logger.warning(
                    f"⚠️ Tentativa {attempt+1}: Ainda não estamos na tela de verificação de telefone.")

                # Verificar se há botões "Next" ou "Continue" que podem nos levar à próxima tela
                next_buttons = [
                    "//span[contains(text(),'Next')]",
                    "//span[contains(text(),'Continue')]",
                    "//button[contains(@class, 'VfPpkd-LgbsSe')]"
                ]

                for button_xpath in next_buttons:
                    try:
                        if self._element_exists(button_xpath, timeout=2):
                            logger.info(
                                f"🔍 Botão encontrado: {button_xpath}. Tentando clicar...")
                            self.driver.find_element(
                                By.XPATH, button_xpath).click()
                            time.sleep(3)
                            if self._check_phone_screen():
                                return True
                    except:
                        continue

                # Se ainda não conseguimos chegar à tela de verificação, tentar reiniciar o processo
                if attempt == max_attempts - 1:  # Na última tentativa
                    logger.warning(
                        "🔄 Tentando reiniciar o processo de criação de conta...")
                    try:
                        # Voltar para a URL inicial de cadastro
                        self.driver.get("https://accounts.google.com/signup")
                        time.sleep(5)

                        # Verificar elementos iniciais do formulário de cadastro
                        form_selectors = [
                            "//input[@name='firstName']",
                            "//input[@name='lastName']",
                            "//input[@name='Username']"
                        ]

                        for selector in form_selectors:
                            if self._element_exists(selector, timeout=2):
                                logger.info(
                                    "✅ Voltamos para o início do cadastro. Será necessário reiniciar o processo.")
                                # Retornar False para indicar que precisamos reiniciar o processo completo
                                return False

                    except Exception as e:
                        logger.error(
                            f"❌ Erro ao tentar reiniciar o processo: {str(e)}")

            except Exception as e:
                logger.warning(
                    f"⚠️ Erro ao tentar garantir tela de verificação: {str(e)}")
                if attempt < max_attempts - 1:
                    time.sleep(2)  # Pequena pausa antes da próxima tentativa

        logger.error(
            "❌ Não foi possível garantir que estamos na tela de verificação de telefone.")
        return False  # Falha após todas as tentativas

    def _check_number_availability(self) -> bool:
        """Verifica se há números disponíveis nos países selecionados."""
        try:
            available_numbers = {}

            # Validar se o phone_manager está disponível
            if not self.phone_manager:
                logger.error("❌ phone_manager não inicializado")
                return False

            for country_code, country_name in self.phone_manager.selected_countries.items():
                if country_code in self.used_countries:
                    continue

                status = self.sms_api.get_number_status(
                    country=country_code, service="go")
                available_count = status.get(
                    "go", 0) if isinstance(status, dict) else status

                if available_count > 0:
                    available_numbers[country_code] = {
                        'count': available_count, 'country_name': country_name}
                    logger.info(
                        f"{country_name}: {available_count} disponíveis.")

            if not available_numbers:
                return False

            self._available_numbers = available_numbers
            return True

        except Exception as e:
            logger.error(
                f"❌ Erro ao verificar disponibilidade de números: {str(e)}")
            return False

    def _get_new_number(self) -> Optional[ActivationInfo]:
        """Obtém um novo número de telefone, tentando vários países se necessário."""
        try:
            # Verificar se o phone_manager está disponível
            if not self.phone_manager:
                logger.error("❌ phone_manager não inicializado")
                return None

            # Filtrar países ainda disponíveis
            available_countries = [
                code for code in self.phone_manager.selected_countries.keys()
                if code not in self.used_countries
            ]

            if not available_countries:
                logger.error(
                    "🚨 Todos os países foram usados. Nenhum número disponível.")
                return None

            # Sempre tentar Brasil primeiro, independente do que aconteça
            brazil_code = "73"
            if brazil_code in available_countries:
                for brazil_attempt in range(1, 6):  # 5 tentativas iniciais
                    logger.info(
                        f"🇧🇷 Tentativa {brazil_attempt}/5 para número brasileiro...")

                    # Verificar disponibilidade no Brasil primeiro
                    try:
                        status = self.phone_manager.get_number_status(
                            brazil_code, "go")
                        if status <= 0:
                            logger.warning(
                                "⚠️ Sem números disponíveis no Brasil")
                            break  # Se não tem números disponíveis, não continua tentando

                        logger.info(f"🇧🇷 Brasil: {status} números disponíveis")
                    except Exception as e:
                        logger.error(
                            f"❌ Erro ao verificar disponibilidade no Brasil: {str(e)}")
                        time.sleep(1)
                        continue

                    # Comprar número diretamente via API
                    try:
                        # Chamar API diretamente (sem usar o PhoneManager)
                        result = self.sms_api.get_number("go", brazil_code)

                        if isinstance(result, tuple) and len(result) == 2:
                            activation_id, phone_number = result

                            # Validar resultados e converter para string
                            if activation_id and phone_number:
                                activation_id = str(activation_id)
                                phone_number = str(phone_number)

                                logger.info(
                                    f"✅ Número brasileiro obtido: {phone_number}")

                                # Armazenar no PhoneManager se disponível
                                if self.phone_manager:
                                    try:
                                        self.phone_manager.add_number(
                                            phone_number=phone_number,
                                            country_code=brazil_code,
                                            activation_id=activation_id,
                                            service="go"
                                        )
                                    except Exception as add_err:
                                        logger.warning(
                                            f"⚠️ Erro ao adicionar número ao PhoneManager: {str(add_err)}")

                                # Armazenar o número para uso na classe
                                self.phone_number = phone_number

                                # Retornar informação de ativação
                                return ActivationInfo(
                                    activation_id=activation_id,
                                    phone_number=phone_number,
                                    country_code=brazil_code,
                                    start_time=time.time(),
                                    state=VerificationState.NUMBER_RECEIVED
                                )
                    except Exception as e:
                        logger.error(
                            f"❌ Erro ao comprar número brasileiro: {str(e)}")

                    # Pequena pausa entre tentativas
                    time.sleep(2)

            # Se não conseguiu com Brasil, tentar países alternativos
            # Ordenar países por prioridade (usar a ordem definida no PhoneManager)
            priority_order = [code for code in self.phone_manager.country_priority
                              if code in available_countries and code != brazil_code]

            for country_code in priority_order:
                country_name = self.phone_manager.selected_countries.get(
                    country_code, "Desconhecido")
                logger.info(f"Tentando país alternativo: {country_name}")

                # Verificar disponibilidade
                try:
                    status = self.phone_manager.get_number_status(
                        country_code, "go")
                    if status <= 0:
                        logger.warning(
                            f"⚠️ Sem números disponíveis em {country_name}")
                        self.used_countries.add(country_code)
                        continue

                    logger.info(
                        f"{country_name}: {status} números disponíveis")
                except Exception as e:
                    logger.error(
                        f"❌ Erro ao verificar disponibilidade em {country_name}: {str(e)}")
                    self.used_countries.add(country_code)
                    continue

                # Comprar número diretamente via API
                try:
                    result = self.sms_api.get_number("go", country_code)

                    if isinstance(result, tuple) and len(result) == 2:
                        activation_id, phone_number = result

                        # Validar resultados e converter para string
                        if activation_id and phone_number:
                            activation_id = str(activation_id)
                            phone_number = str(phone_number)

                            logger.info(
                                f"✅ Número obtido em {country_name}: {phone_number}")

                            # Armazenar no PhoneManager se disponível
                            if self.phone_manager:
                                try:
                                    self.phone_manager.add_number(
                                        phone_number=phone_number,
                                        country_code=country_code,
                                        activation_id=activation_id,
                                        service="go"
                                    )
                                except Exception as add_err:
                                    logger.warning(
                                        f"⚠️ Erro ao adicionar número ao PhoneManager: {str(add_err)}")

                            # Armazenar o número para uso na classe
                            self.phone_number = phone_number

                            # Retornar informação de ativação
                            return ActivationInfo(
                                activation_id=activation_id,
                                phone_number=phone_number,
                                country_code=country_code,
                                start_time=time.time(),
                                state=VerificationState.NUMBER_RECEIVED
                            )
                except Exception as e:
                    logger.error(
                        f"❌ Erro ao comprar número em {country_name}: {str(e)}")

                # Marcar o país como usado
                self.used_countries.add(country_code)

            # Se chegou aqui, não conseguiu comprar número em nenhum país
            logger.error(
                "❌ Não foi possível obter número em nenhum dos países tentados.")
            return None

        except Exception as e:
            logger.error(f"Erro ao obter novo número: {str(e)}")
            return None

    def _ensure_final_cleanup(self):
        """Garante que qualquer número comprado e não utilizado seja cancelado."""
        if self.current_activation:
            logger.info("⚠️ Limpando ativação pendente...")
            self._cancel_number()

    def _cancel_number(self):
        """Cancela o número atual e adiciona o país à lista de rejeitados."""
        if self.current_activation:
            try:
                # Se a verificação foi concluída com sucesso, não cancela o número
                if self.state == VerificationState.COMPLETED:
                    logger.info(
                        "✅ Verificação concluída com sucesso, não cancelando o número.")
                    return

                logger.warning(
                    f"⚠️ Tentando cancelar número {self.current_activation.phone_number}...")

                # Verificar se o número já foi usado com sucesso
                if self.state == VerificationState.COMPLETED:
                    logger.info(
                        "✅ Número já usado com sucesso, não é necessário cancelar.")
                    self.current_activation = None
                    return

                # Tentar cancelar
                response = self.sms_api.set_status(
                    self.current_activation.activation_id, 6)

                # Registrar independentemente do resultado
                self.used_countries.add(self.current_activation.country_code)
                self.current_activation = None

                logger.info("✅ Status do número atualizado.")

            except Exception as e:
                logger.warning(
                    f"⚠️ Erro ao cancelar número, mas continuando: {str(e)}")
                self.current_activation = None

    def _element_exists(self, xpath, timeout=3):
        """Verifica se um elemento existe na página com tratamento de erro de seletor inválido."""
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            return True
        except Exception as e:
            # Verifica se é um erro de seletor inválido
            if "invalid selector" in str(e) or "SyntaxError" in str(e):
                logger.warning(f"⚠️ XPath inválido: {xpath}")
                return False  # Retorna falso, mas não quebra a execução
            elif isinstance(e, TimeoutException):
                return False  # Elemento não encontrado dentro do timeout
            else:
                logger.warning(
                    f"⚠️ Erro desconhecido ao verificar elemento: {e}")
                return False  # Qualquer outro erro, também retorna falso

    def _submit_phone_number(self) -> bool:
        """Submete o número de telefone no formulário com tratamento de erros aprimorado."""
        try:
            if not self.current_activation:
                return False

            # Verificar se a página está pronta
            self.wait.until(
                lambda driver: driver.execute_script(
                    "return document.readyState") == "complete"
            )

            # Localizar campo de telefone com retry
            for attempt in range(3):
                try:
                    phone_input = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable(
                            (By.XPATH, phone_locators.PHONE_INPUT))
                    )
                    break
                except TimeoutException:
                    if attempt == 2:
                        logger.error(
                            "❌ Campo de telefone não encontrado após 3 tentativas")
                        return False
                    logger.warning(
                        "⚠️ Campo de telefone não encontrado, tentando novamente...")
                    time.sleep(2)

            # Garantir que o campo está pronto para input
            self.driver.execute_script(
                "arguments[0].scrollIntoView(true);", phone_input)
            time.sleep(1)

            # Tentar apenas formatos simples para maior confiabilidade
            formats_to_try = [
                self.current_activation.phone_number,  # Formato básico
                # Com código de país
                f"+{self.current_activation.phone_number}"
            ]

            for attempt, phone_format in enumerate(formats_to_try):
                try:
                    # Limpar e preencher com JS para maior confiabilidade
                    self.driver.execute_script(
                        "arguments[0].value = '';", phone_input)
                    self.driver.execute_script(
                        f"arguments[0].value = '{phone_format}';", phone_input)
                    logger.info(
                        f"📲 Tentativa {attempt+1}: Formato de número: {phone_format}")

                    # Localizar e clicar no botão Next
                    try:
                        next_button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable(
                                (By.XPATH, phone_locators.NEXT_BUTTON))
                        )
                        # Tentar clicar com JS para maior confiabilidade
                        self.driver.execute_script(
                            "arguments[0].click();", next_button)
                        logger.info("✅ Clicado no botão Next com JavaScript")
                    except Exception as e:
                        logger.error(
                            f"❌ Erro ao clicar no botão Next: {str(e)}")
                        continue

                    # Aguardar resposta (mais tempo para processamento)
                    time.sleep(7)

                    # Verificar se avançamos para a próxima tela
                    try:
                        # Se encontrarmos o campo de código SMS, o número foi aceito
                        code_field = WebDriverWait(self.driver, 3).until(
                            EC.presence_of_element_located(
                                (By.XPATH, phone_locators.CODE_INPUT))
                        )
                        if code_field.is_displayed():
                            logger.info(
                                "✅ Número aceito! Campo de código SMS detectado.")
                            return True
                    except TimeoutException:
                        # Se não encontramos o campo de código, verificar erro
                        pass

                    # Verificar mensagens de erro específicas
                    error_xpath = "/html/body/div[1]/div[1]/div[2]/c-wiz/div/div[2]/div/div/div[1]/form/span/section/div/div/div[2]/div/div[2]/div[2]/div"
                    try:
                        if self._element_exists(error_xpath, timeout=1):
                            error_element = self.driver.find_element(
                                By.XPATH, error_xpath)
                            error_text = error_element.text
                            logger.warning(
                                f"⚠️ Erro detectado: '{error_text}'")
                            continue
                    except:
                        pass

                    # Ver se ainda estamos na tela de telefone
                    if self._element_exists(phone_locators.PHONE_INPUT, timeout=1):
                        logger.warning(
                            "⚠️ Ainda na tela de telefone. Número rejeitado.")
                        continue

                    # Se chegamos aqui e não detectamos erro ou campo de código, verificar a URL
                    current_url = self.driver.current_url
                    if "verifyphone" in current_url:
                        logger.info(
                            "✅ URL indica que avançamos para verificação de telefone")
                        return True

                    logger.info(
                        "✅ Nenhum erro detectado, assumindo que o número foi aceito")
                    return True

                except Exception as e:
                    logger.warning(
                        f"⚠️ Erro com formato {phone_format}: {str(e)}")

            # Se tentou todos os formatos e nenhum funcionou
            logger.error("❌ Todos os formatos de número foram rejeitados")
            self._cancel_number()
            return False

        except Exception as e:
            logger.error(f"❌ Erro ao submeter número: {str(e)}")
            return False

    # Melhoria no método _try_verification_cycle para melhor tratamento de erros e terceira tentativa

    def _try_verification_cycle(self) -> bool:
        """Executa um ciclo completo de verificação."""
        try:
            # Adicionar refresh da página se não for a primeira tentativa
            if self.used_countries:  # Se já usou algum país, não é a primeira tentativa
                logger.info(
                    "🔄 Recarregando a página antes de nova tentativa...")
                self.driver.refresh()
                time.sleep(5)  # Aguardar carregamento completo da página

                # Verificar se ainda estamos na tela de verificação de telefone
                if not self._check_phone_screen():
                    logger.warning(
                        "⚠️ Após refresh, não estamos na tela de verificação de telefone.")
                    # Tentar redirecionamento?

            # Resto do código original continua daqui
            self.current_activation = self._get_new_number()
            if not self.current_activation:
                logger.error("❌ Falha ao obter um número para verificação.")
                return False

            # Verificar explicitamente os valores antes de prosseguir
            if not hasattr(self.current_activation, 'phone_number') or not self.current_activation.phone_number:
                logger.error("❌ Número de telefone não definido ou inválido")
                return False

            if not hasattr(self.current_activation, 'activation_id') or not self.current_activation.activation_id:
                logger.error("❌ ID de ativação não definido ou inválido")
                return False

            logger.info(
                f"📞 Número comprado: {self.current_activation.phone_number} ({self.current_activation.country_code})")

            if not self._submit_phone_number():
                return False  # Se falhar, já cancela e tenta outro

            # 🔹 **Aguardar e inserir o código SMS**
            if not self._handle_sms_verification():
                logger.error("❌ Falha na verificação por SMS. Abortando.")
                return False

            return True

        except Exception as e:
            logger.error(f"❌ Erro no ciclo de verificação: {str(e)}")
            self._cancel_number()
        return False

    def _check_phone_error(self) -> bool:
        """Verifica se há erro ao inserir o número de telefone."""
        try:
            error_messages = [
                "This phone number format is not recognized",
                "This phone number has already been used too many times",
                "Please enter a valid phone number"
            ]
            for msg in error_messages:
                if self.wait.until(EC.presence_of_element_located((By.XPATH, f"//div[contains(text(), '{msg}')]"))):
                    logger.warning(f"⚠️ Número rejeitado: {msg}")
                    return True  # Erro detectado
        except TimeoutException:
            return False  # Nenhum erro detectado

    def _cancel_current_number(self):
        """Cancela o número rejeitado e marca o país como usado."""
        if not self.current_activation:
            return

        activation_id = self.current_activation.activation_id
        country_code = self.current_activation.country_code

        # 🔹 Adicionar o país à lista de usados ANTES de tentar outro número
        self.used_countries.add(country_code)
        logger.info(
            f"🚫 País {country_code} adicionado à lista de usados. Evitaremos esse país nas próximas tentativas.")

        # 🔹 Tentar cancelar o número com um pequeno delay
        time.sleep(1)
        try:
            logger.warning(
                f"⚠️ Cancelando número {self.current_activation.phone_number}...")
            # Status 6 = Cancelar número
            self.sms_api.set_status(activation_id, 6)
            logger.info("✅ Número cancelado com sucesso.")
        except Exception as e:
            if "BAD_STATUS" in str(e):
                logger.warning(
                    "⚠️ Não foi possível cancelar o número. Continuando...")
            else:
                logger.error(
                    f"❌ Erro ao cancelar o número {activation_id}: {str(e)}")

        self.current_activation = None  # Resetar ativação

    def _handle_sms_verification(self) -> bool:
        """Aguarda o SMS e insere o código de verificação com timeout global."""
        try:
            if not self.current_activation:
                return False

            self.state = VerificationState.WAITING_SMS
            activation_id = self.current_activation.activation_id

            # Definir timeout global para todo o processo de SMS
            sms_process_start = time.time()
            sms_global_timeout = 180  # 3 minutos como timeout total para todo o processo

            logger.info(f"📩 Aguardando SMS para ID {activation_id}...")

            # Aguarda até max_attempts para receber o SMS inicialmente
            sms_code = self.sms_api.get_sms_code(
                activation_id,
                max_attempts=6,  # Tenta 6 vezes primeiro (60 segundos)
                interval=10      # Verifica a cada 10 segundos
            )

            # Se não recebeu o SMS no período inicial, tenta solicitar novo código
            resent_attempt = 0
            max_resent_attempts = 2  # Máximo de tentativas de reenvio

            # Verifica se ainda está dentro do timeout global
            while (not sms_code and
                   resent_attempt < max_resent_attempts and
                   (time.time() - sms_process_start) < sms_global_timeout):

                resent_attempt += 1
                logger.warning(
                    f"⚠️ SMS não recebido após 60 segundos. Tentativa de reenvio #{resent_attempt}...")

                # Verifica se ainda temos tempo dentro do timeout global
                remaining_time = sms_global_timeout - \
                    (time.time() - sms_process_start)
                if remaining_time < 30:  # Se restam menos de 30 segundos, não vale a pena tentar reenvio
                    logger.warning(
                        f"⏱ Tempo restante insuficiente ({remaining_time:.1f}s) para nova tentativa. Abortando.")
                    break

                # Aguarda até que o botão esteja habilitado
                logger.info(
                    "🕒 Aguardando botão 'Get a new Code' ficar habilitado...")

                # Calcula tempo máximo de espera pelo botão baseado no tempo restante
                # Não espera mais que 25s ou metade do tempo restante
                wait_time = min(25, remaining_time / 2)
                time.sleep(wait_time)

                # Verifica se ainda temos tempo dentro do timeout global
                if (time.time() - sms_process_start) >= sms_global_timeout:
                    logger.warning(
                        "⏱ Timeout global atingido durante espera pelo botão. Abortando.")
                    break

                # Tentar múltiplos seletores para o botão de reenvio
                get_new_code_buttons = [
                    phone_locators.GET_NEW_CODE_BUTTON_ALT,
                    "//button[contains(., 'Get a new code')]",
                    "//button[contains(text(), 'Get a new code')]",
                    "//div[contains(@class, 'VfPpkd-RLmnJb')]//span[contains(text(), 'Get a new code')]/ancestor::button",
                    "//span[text()='Get a new code']/parent::button",
                    "//button[contains(@class, 'VfPpkd-LgbsSe') and contains(., 'new code')]"
                ]

                button_clicked = False
                for button_xpath in get_new_code_buttons:
                    try:
                        logger.info(
                            f"🔍 Tentando localizar botão usando seletor: {button_xpath}")

                        # Tentativa com wait mais curto para cada seletor
                        get_new_code_button = WebDriverWait(self.driver, 2).until(
                            EC.element_to_be_clickable(
                                (By.XPATH, button_xpath))
                        )

                        # Adiciona verificação de visibilidade e habilitação
                        if not get_new_code_button.is_displayed() or not get_new_code_button.is_enabled():
                            logger.warning(
                                f"⚠️ Botão encontrado mas não está visível ou habilitado ainda.")
                            continue

                        logger.info("✅ Botão 'Get a new Code' encontrado!")

                        # Rola para garantir visibilidade
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center'});", get_new_code_button)
                        time.sleep(1)

                        # Tenta várias estratégias de clique
                        # Tenta até 3 vezes com diferentes estratégias
                        for click_attempt in range(3):
                            try:
                                if click_attempt == 0:
                                    # Estratégia 1: Clique direto
                                    get_new_code_button.click()
                                    logger.info(
                                        "✅ Clicou no botão 'Get a new Code' usando .click()")
                                    button_clicked = True
                                    break
                                elif click_attempt == 1:
                                    # Estratégia 2: Clique JavaScript
                                    self.driver.execute_script(
                                        "arguments[0].click();", get_new_code_button)
                                    logger.info(
                                        "✅ Clicou no botão 'Get a new Code' usando JavaScript")
                                    button_clicked = True
                                    break
                                else:
                                    # Estratégia 3: Actions chain
                                    from selenium.webdriver.common.action_chains import ActionChains
                                    actions = ActionChains(self.driver)
                                    actions.move_to_element(
                                        get_new_code_button).click().perform()
                                    logger.info(
                                        "✅ Clicou no botão 'Get a new Code' usando ActionChains")
                                    button_clicked = True
                                    break
                            except Exception as click_error:
                                strategy_name = [
                                    "clique direto", "JavaScript", "ActionChains"][click_attempt]
                                logger.warning(
                                    f"⚠️ Estratégia {click_attempt+1} ({strategy_name}) falhou: {click_error}")
                                # Continua para a próxima estratégia

                        if button_clicked:
                            break  # Sai do loop de seletores se clicou com sucesso

                    except Exception as e:
                        logger.warning(
                            f"⚠️ Não encontrou botão com seletor {button_xpath}: {e}")

                # Verifica se ainda temos tempo dentro do timeout global
                if (time.time() - sms_process_start) >= sms_global_timeout:
                    logger.warning(
                        "⏱ Timeout global atingido após tentativas de clique. Abortando.")
                    break

                if not button_clicked:
                    logger.error(
                        "❌ Não foi possível encontrar ou clicar no botão 'Get a new Code'")

                    # Estratégia de último recurso: Tente recarregar a página
                    if resent_attempt == 1:  # Apenas na primeira tentativa de reenvio
                        try:
                            logger.warning(
                                "🔄 Tentando recarregar a página como último recurso...")
                            self.driver.refresh()
                            time.sleep(5)
                            continue  # Vai para a próxima tentativa
                        except:
                            logger.error("❌ Falha ao recarregar a página")
                else:
                    # Após clicar com sucesso
                    logger.info("🕒 Aguardando processamento após clique...")
                    time.sleep(3)

                    # Verifica se ainda temos tempo dentro do timeout global
                    if (time.time() - sms_process_start) >= sms_global_timeout:
                        logger.warning(
                            "⏱ Timeout global atingido após processamento de clique. Abortando.")
                        break

                    # Verificar se voltou para tela de telefone ou se ainda está na mesma tela
                    try:
                        if self._element_exists(phone_locators.PHONE_INPUT, timeout=3):
                            logger.info(
                                "📞 Retornando para tela de entrada de telefone...")

                            # Reenviar o mesmo número
                            if not self._submit_phone_number():
                                logger.error(
                                    "❌ Falha ao resubmeter o mesmo número.")
                                continue
                        elif self._element_exists(phone_locators.CODE_INPUT, timeout=3):
                            logger.info(
                                "📲 Ainda na tela de código, aguardando recebimento do SMS...")
                        else:
                            logger.warning(
                                "⚠️ Estado inesperado após clicar em reenviar.")
                    except Exception as e:
                        logger.error(
                            f"❌ Erro ao verificar estado após clique: {e}")

                    # Verifica se ainda temos tempo dentro do timeout global
                    remaining_time = sms_global_timeout - \
                        (time.time() - sms_process_start)
                    if remaining_time < 30:  # Não vale a pena esperar novo SMS se restar pouco tempo
                        logger.warning(
                            f"⏱ Tempo restante insuficiente ({remaining_time:.1f}s) para aguardar SMS. Abortando.")
                        break

                    # Calcula máximo de tentativas de SMS baseado no tempo restante
                    # Pelo menos 1, no máximo 6
                    max_sms_attempts = max(1, min(6, int(remaining_time / 15)))

                    # Esperar pelo SMS novamente
                    logger.info(
                        f"📩 Aguardando novo SMS para ID {activation_id} por {max_sms_attempts} tentativas...")
                    sms_code = self.sms_api.get_sms_code(
                        activation_id,
                        max_attempts=max_sms_attempts,
                        interval=10
                    )

            # Se ainda não recebeu o código após todas as tentativas
            if not sms_code:
                elapsed_time = time.time() - sms_process_start
                logger.error(
                    f"❌ Não foi possível obter código SMS após {elapsed_time:.1f}s e {resent_attempt} tentativas de reenvio.")
                self._cancel_current_number()
                return False

            logger.info(f"✅ Código recebido: {sms_code}")

            # Verifica se ainda temos tempo dentro do timeout global
            remaining_time = sms_global_timeout - \
                (time.time() - sms_process_start)
            if remaining_time < 10:  # Precisamos de pelo menos 10 segundos para submeter o código
                logger.warning(
                    f"⏱ Tempo restante insuficiente ({remaining_time:.1f}s) para submeter o código. Abortando.")
                self._cancel_current_number()
                return False

            # Verificar se o campo de código ainda está acessível
            try:
                # Localizar o campo de código com retry
                code_input = None
                for attempt in range(3):
                    try:
                        code_input = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located(
                                (By.XPATH, phone_locators.CODE_INPUT))
                        )
                        break
                    except:
                        if attempt == 2:
                            raise
                        logger.warning(
                            f"⚠️ Tentativa {attempt+1} de localizar campo de código falhou.")
                        time.sleep(2)

                if not code_input:
                    raise Exception(
                        "Campo de código não encontrado após múltiplas tentativas")

                # Limpar e inserir o código SEM o espaço adicional
                code_input.clear()
                self.driver.execute_script(
                    f"arguments[0].value = '{sms_code}';", code_input)
                logger.info("✅ Código inserido no campo.")

                # Clicar no botão "Next" para validar o código
                next_button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, phone_locators.NEXT_BUTTON))
                )

                # Scroll até o botão
                self.driver.execute_script(
                    "arguments[0].scrollIntoView(true);", next_button)
                time.sleep(1)

                # Tentar clicar
                try:
                    next_button.click()
                except:
                    self.driver.execute_script(
                        "arguments[0].click();", next_button)

                logger.info(
                    "✅ Cliquei no botão Next para validar o código SMS.")

                # Aguardar processamento
                time.sleep(5)

                # Verificar erros de código inválido com escape de aspas e múltiplas abordagens
                error_messages = [
                    "Wrong code. Try again.",
                    "Code is incorrect",
                    "That code didn't work"  # Este contém uma aspa simples que causa o erro XPath
                ]

                for error_msg in error_messages:
                    try:
                        # Método 1: Usando contains() com aspas duplas (escape para aspas simples)
                        error_msg_escaped = error_msg.replace("'", "\\'")
                        error_xpath = f"//div[contains(text(), \"{error_msg_escaped}\")]"

                        if self._element_exists(error_xpath, timeout=2):
                            logger.warning(
                                f"⚠️ Erro detectado: '{error_msg}'. Código inválido.")
                            self._cancel_current_number()
                            return False

                        # Método 2: Verificação parcial do texto (sem aspas)
                        if "didn't work" in error_msg:
                            alt_xpath = "//div[contains(text(), 'code') and contains(text(), 'work')]"
                            if self._element_exists(alt_xpath, timeout=1):
                                logger.warning(
                                    f"⚠️ Erro alternativo detectado para: '{error_msg}'")
                                self._cancel_current_number()
                                return False
                    except Exception as e:
                        logger.warning(
                            f"⚠️ Erro ao verificar mensagem de erro '{error_msg}': {e}")
                        # Continua com as outras verificações, não falha aqui

                try:
                    # Tenta atualizar o status antes de confirmação final
                    # Status 8 = Número utilizado com sucesso
                    self.sms_api.set_status(activation_id, 8)
                except Exception as e:
                    logger.warning(
                        f"⚠️ Erro ao atualizar status do número, mas continuando: {e}")

                self.state = VerificationState.COMPLETED
                logger.info("✅ Verificação de telefone concluída com sucesso!")

                # Armazenar o número após a verificação bem-sucedida
                try:
                    if self.phone_manager is not None:
                        self.phone_manager.add_number(
                            phone_number=self.phone_number,
                            country_code=self.current_activation.country_code,
                            activation_id=self.current_activation.activation_id,
                            service="gmail"  # ou outro serviço relevante
                        )
                        logger.info(
                            f"✅ Número {self.phone_number} armazenado para reutilização.")
                    else:
                        logger.warning(
                            "⚠️ phone_manager não está inicializado, não foi possível armazenar o número.")
                except Exception as e:
                    logger.warning(
                        f"⚠️ Erro ao armazenar o número, mas continuando: {e}")

                return True

            except Exception as e:
                logger.error(f"❌ Erro na verificação SMS: {str(e)}")
                self._cancel_current_number()
                return False

        except Exception as e:
            logger.error(f"❌ Erro na verificação SMS: {str(e)}")
            self._cancel_current_number()
            return False

    def get_current_phone_data(self):
        """Retorna os dados atuais do telefone em uso."""
        if self.current_activation:
            # Verificar se phone_manager está disponível
            if not self.phone_manager:
                country_name = "unknown"
            else:
                country_name = self.phone_manager.selected_countries.get(
                    self.current_activation.country_code,
                    "unknown"
                )

            return {
                'phone_number': self.current_activation.phone_number,
                'country_code': self.current_activation.country_code,
                'activation_id': self.current_activation.activation_id,
                'country_name': country_name
            }
        return None

    def _get_number_with_webhook(self, service="go"):
        webhook_url = "http://localhost:5001/sms-webhook"  # Adapte conforme necessário

        # Tentar obter número reutilizável
        reusable = self.phone_manager.get_reusable_number(service)
        if reusable:
            return reusable

        # Se não encontrar reutilizável, comprar com webhook
        number_data = self.phone_manager.buy_multi_service_with_webhook(
            [service], webhook_url)

        return number_data

    def _wait_for_webhook_notification(self, activation_id, max_wait=120):
        """Aguarda notificação do webhook para o código SMS."""
        logger.info(
            f"⏳ Aguardando notificação webhook para {activation_id}...")

        endpoint = f"http://localhost:5001/sms-status/{activation_id}"

        start_time = time.time()
        while time.time() - start_time < max_wait:
            try:
                response = requests.get(endpoint, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    sms_code = data.get("sms_code")
                    if sms_code:
                        logger.info(
                            f"✅ Código recebido via webhook: {sms_code}")
                        return sms_code
            except Exception as e:
                logger.warning(f"⚠️ Erro ao verificar webhook: {str(e)}")

            # Aguardar antes da próxima tentativa
            time.sleep(5)

        logger.error("❌ Timeout aguardando notificação webhook")
        return None
