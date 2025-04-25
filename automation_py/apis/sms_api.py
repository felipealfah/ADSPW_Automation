import os
import logging
import requests
import time
import json
from credentials.credentials_manager import load_credentials, get_credential

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# URL base da API SMS-Activate
BASE_URL = "https://api.sms-activate.org/stubs/handler_api.php"


class SMSAPI:
    def __init__(self, api_key=None):
        # Se api_key for fornecido, use-o. Caso contrário, carregue das credenciais
        self.api_key = api_key or get_credential("SMS_ACTIVATE_API_KEY")
        self.base_url = "https://api.sms-activate.org/stubs/handler_api.php"

        # Lista de países selecionados com seus códigos
        self.selected_countries = {
            "73": "Brasil",
            "151": "Chile",
            "12": "Estados Unidos",
            "40": "Canadá",
            "16": "Reino Unido",
            "117": "Portugal"
        }

    def refresh_credentials(self):
        """Atualiza a chave da API carregando as credenciais mais recentes."""
        self.api_key = get_credential("SMS_ACTIVATE_API_KEY")

        if not self.api_key:
            logger.error(
                "[ERRO] ERRO: A chave 'SMS_ACTIVATE_API_KEY' não foi encontrada em credentials.json.")
            return False
        return True

    def get_balance(self):
        """Obtém o saldo atual da conta."""
        # Sempre atualizar a chave antes de uma operação importante
        self.refresh_credentials()

        params = {'api_key': self.api_key, 'action': 'getBalance'}
        try:
            response = requests.get(BASE_URL, params=params)
            if response.status_code == 200 and 'ACCESS_BALANCE' in response.text:
                balance = float(response.text.split(':')[1])
                logger.info(f" Saldo disponível: {balance} RUB")
                return balance
            else:
                logger.error(f"Erro ao obter saldo: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Erro ao se conectar à API SMS: {str(e)}")
            return None

    def get_prices(self, service=None):
        """
        Obtém preços dos números de telefone por país e serviço.

        Args:
            service (str, optional): Código do serviço (ex: "go" para Gmail, "tk" para TikTok).
                                    Se None, retorna todos os serviços.

        Returns:
            dict: Dicionário estruturado com preços e quantidades disponíveis.
        """
        # Sempre atualizar a chave
        self.refresh_credentials()

        params = {'api_key': self.api_key, 'action': 'getPrices'}

        try:
            response = requests.get(BASE_URL, params=params, timeout=10)

            if response.status_code != 200:
                logger.error(f"Erro ao obter preços: {response.text}")
                return None

            data = response.json()
            prices = {}

            for country, services in data.items():
                if country in self.selected_countries:
                    for srv, details in services.items():
                        if service is None or srv == service:  # Filtra pelo serviço se especificado
                            prices.setdefault(country, {})[srv] = {
                                "cost": float(details["cost"]),
                                "count": int(details["count"])
                            }

            return prices
        except Exception as e:
            logger.error(f"Erro ao obter preços: {str(e)}")
            return None

    def get_number_status(self, country, service):
        """Verifica disponibilidade de números para um serviço em um país específico."""
        # Atualizar credenciais
        self.refresh_credentials()

        params = {
            'api_key': self.api_key,
            'action': 'getNumbersStatus',
            'country': country
        }

        try:
            response = requests.get(BASE_URL, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                # Retorna a quantidade disponível
                return int(data.get(service, 0))
            else:
                logger.error(
                    f"Erro ao verificar disponibilidade: {response.text}")
                return 0
        except Exception as e:
            logger.error(f"Erro ao verificar status dos números: {str(e)}")
            return 0

    def get_cheapest_country(self, service):
        """Encontra o país mais barato para um serviço dentro dos países selecionados."""
        prices = self.get_prices()
        if not prices:
            return None, None

        cheapest_country = None
        lowest_price = float('inf')

        for country_code in self.selected_countries.keys():
            if country_code in prices and service in prices[country_code]:
                price = float(prices[country_code][service]['cost'])
                available = int(prices[country_code][service]['count'])
                if price < lowest_price and available > 0:
                    lowest_price = price
                    cheapest_country = country_code

        if cheapest_country:
            logger.info(
                f" País mais barato para {service}: {self.selected_countries[cheapest_country]} - {lowest_price} RUB")
            return cheapest_country, lowest_price
        else:
            logger.warning(f"Nenhum país disponível para {service}")
            return None, None

    def buy_number(self, service, country):
        """Compra um número de telefone com validação melhorada."""
        self.refresh_credentials()

        params = {
            'api_key': self.api_key,
            'action': 'getNumber',
            'service': service,
            'country': country
        }

        try:
            response = requests.get(self.base_url, params=params, timeout=15)
            response_text = response.text

            if "ACCESS_NUMBER" in response_text:
                _, activation_id, phone_number = response_text.split(":")
                logger.info(
                    f"[OK] Número comprado com sucesso: {phone_number} (ID: {activation_id})")

                # Validar dados antes de retornar
                if not all([activation_id, phone_number]):
                    raise ValueError(
                        "Dados do número incompletos na resposta da API")

                return activation_id.strip(), phone_number.strip()

            # Tratamento de erros específicos
            error_messages = {
                "NO_NUMBERS": "Sem números disponíveis",
                "NO_BALANCE": "Saldo insuficiente",
                "BAD_SERVICE": "Serviço inválido",
                "BAD_KEY": "Chave de API inválida"
            }

            for error_code, message in error_messages.items():
                if error_code in response_text:
                    logger.error(
                        f"[ERRO] {message} para {service} no país {country}")
                    return None, None

            logger.error(f"[ERRO] Erro desconhecido: {response_text}")
            return None, None

        except Exception as e:
            logger.error(f"[ERRO] Erro ao comprar número: {str(e)}")
            return None, None

    def get_sms_code(self, activation_id, max_attempts=10, interval=10):
        """Verifica se o SMS foi recebido e retorna o código."""
        # Atualizar credenciais
        self.refresh_credentials()

        params = {'api_key': self.api_key,
                  'action': 'getStatus', 'id': activation_id}
        logger.info(f" Aguardando SMS para ID {activation_id}...")

        for attempt in range(max_attempts):
            try:
                response = requests.get(BASE_URL, params=params, timeout=15)
                if response.status_code == 200:
                    if 'STATUS_OK' in response.text:
                        _, code = response.text.split(':')
                        logger.info(f"[OK] Código recebido: {code}")
                        # Confirmação de código recebido
                        self.set_status(activation_id, 3)
                        return code
                    elif 'STATUS_CANCEL' in response.text:
                        logger.warning("[ALERTA] Ativação cancelada pelo sistema.")
                        return None
                else:
                    logger.error(f"Erro ao verificar SMS: {response.text}")
            except Exception as e:
                logger.error(f"Erro ao verificar código SMS: {str(e)}")

            time.sleep(interval)

        logger.warning(" Tempo esgotado, nenhum SMS recebido.")
        self.set_status(activation_id, 6)  # Cancelar ativação
        return None

    def set_status(self, activation_id, status):
        """
        Define o status da ativação:
            1 = Número recebido e aguardando SMS
            3 = Código SMS recebido e inserido
            6 = Cancelar número (caso não seja mais necessário)
            8 = Número confirmado com sucesso
        """
        # Atualizar credenciais
        self.refresh_credentials()

        params = {
            "api_key": self.api_key,
            "action": "setStatus",
            "id": activation_id,
            "status": status
        }

        try:
            response = requests.get(BASE_URL, params=params, timeout=10)

            if response.status_code == 200:
                if "ACCESS_CANCEL" in response.text:
                    logger.info(
                        f"[OK] Número {activation_id} cancelado com sucesso.")
                    return True
                elif "NO_ACTIVATION" in response.text:
                    logger.warning(
                        f"[AVISO] Não foi possível cancelar o número {activation_id}. Ele pode já estar expirado ou inválido.")
                else:
                    logger.error(
                        f"[ERRO] Erro ao cancelar o número {activation_id}: {response.text}")
            else:
                logger.error(
                    f"[ERRO] Erro de conexão ao tentar cancelar o número {activation_id}: {response.status_code}")
        except Exception as e:
            logger.error(f"Erro ao definir status da ativação: {str(e)}")

        return False  # Retorna False caso a operação não tenha sido bem-sucedida

    def reuse_number_for_service(self, activation_id, new_service):
        """
        Tenta reutilizar um número para um serviço diferente.

        Args:
            activation_id (str): ID da ativação original.
            new_service (str): Código do novo serviço (ex: "tk" para TikTok).

        Returns:
            bool: True se a reutilização for bem-sucedida, False caso contrário.
        """
        # Atualizar credenciais
        self.refresh_credentials()

        params = {
            "api_key": self.api_key,
            "action": "getExtraService",
            "id": activation_id,
            "service": new_service
        }

        try:
            response = requests.get(BASE_URL, params=params, timeout=10)
            if "ACCESS_EXTRA_SERVICE" in response.text:
                logger.info(
                    f"[OK] Número reutilizado com sucesso para {new_service} (ID: {activation_id})")
                return True
            else:
                logger.warning(
                    f"[ERRO] Falha ao reutilizar número para {new_service}: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Erro ao reutilizar número: {str(e)}")
            return False

    def compare_prices_in_selected_countries(self, service):
        """
        Compara os preços e disponibilidade de um serviço entre os países selecionados.

        Args:
            service (str): Código do serviço para verificar (ex: "go" para Gmail).

        Returns:
            list: Lista ordenada de dicionários com informações de cada país.
        """
        try:
            all_prices = self.get_prices()  # Obtém todos os preços disponíveis

            if not all_prices:
                logger.error(
                    f"[ERRO] Erro: Não foi possível obter os preços para o serviço {service}.")
                return []

            logger.info(f"[GRAFICO] [BUSCA] Dados brutos retornados pela API para {service}")
            service_prices = []

            # Filtrar apenas os países selecionados
            for country_code, country_name in self.selected_countries.items():
                if country_code in all_prices and service in all_prices[country_code]:
                    try:
                        #  Obtém o preço
                        price_rub = float(
                            all_prices[country_code][service]["cost"])
                        #  Obtém a quantidade disponível
                        available_count = int(
                            all_prices[country_code][service]["count"])

                        service_prices.append({
                            'country_code': country_code,
                            'country_name': country_name,
                            'price': price_rub,
                            'available': available_count
                        })

                        logger.info(
                            f"[OK] {country_name}: {price_rub} RUB ({available_count} disponíveis)")

                    except (ValueError, KeyError) as e:
                        logger.warning(
                            f"[AVISO] Erro ao processar preços para {service} no país {country_name}: {str(e)}")
                        continue

            # Ordenar os países por preço (do mais barato para o mais caro)
            sorted_prices = sorted(service_prices, key=lambda x: x['price'])

            if not sorted_prices:
                logger.warning(
                    f"[AVISO] Nenhum número disponível para {service} nos países selecionados.")

            return sorted_prices

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao comparar preços nos países selecionados para {service}: {str(e)}")
            return []

    # Alias para manter compatibilidade com código existente
    def get_number(self, service, country):
        """
        Alias para o método buy_number para compatibilidade com código existente.

        Args:
            service (str): Código do serviço (ex: "go" para Gmail)
            country (str): Código do país

        Returns:
            tuple: (activation_id, phone_number) ou (None, None) em caso de falha
        """
        return self.buy_number(service, country)

    def buy_number_multi_service(self, services, country, operator=None, max_price=None):
        """
        Compra um número compatível com múltiplos serviços simultaneamente.

        Args:
            services (list): Lista de códigos de serviço (ex: ["go", "tk", "ig"])
            country (str): Código do país
            operator (str, optional): Código da operadora (específico para Brasil: "claro", "vivo", "tim", "oi")
            max_price (float, optional): Preço máximo aceitável em rublos

        Returns:
            tuple: (activation_id, phone_number) ou (None, None) em caso de falha
        """
        self.refresh_credentials()

        # Converter lista de serviços para string separada por vírgulas
        services_str = ",".join(services)

        params = {
            'api_key': self.api_key,
            'action': 'getNumber',
            'service': services_str,
            'country': country,
            'multiService': '1'  # Parâmetro para indicar que queremos um número multi-serviço
        }

        # Adicionar parâmetros opcionais se fornecidos
        if operator:
            params['operator'] = operator

        if max_price:
            params['maxPrice'] = str(max_price)

        # Adicionar ID de referência para rastreamento (unix timestamp)
        params['ref'] = str(int(time.time()))

        try:
            logger.info(
                f"[BUSCA] Buscando número multi-serviço para {services_str} no país {country}...")
            if operator:
                logger.info(f"[TELEFONE] Operadora especificada: {operator}")
            if max_price:
                logger.info(f" Preço máximo: {max_price} RUB")

            response = requests.get(self.base_url, params=params, timeout=15)
            response_text = response.text

            if "ACCESS_NUMBER" in response_text:
                _, activation_id, phone_number = response_text.split(":")
                logger.info(
                    f"[OK] Número multi-serviço comprado com sucesso: {phone_number} (ID: {activation_id})")
                logger.info(f"[OK] Serviços habilitados: {services_str}")

                # Validar dados antes de retornar
                if not all([activation_id, phone_number]):
                    raise ValueError(
                        "Dados do número incompletos na resposta da API")

                return activation_id.strip(), phone_number.strip()

            # Tratamento de erros específicos
            error_messages = {
                "NO_NUMBERS": f"Sem números multi-serviço disponíveis para {services_str} no país {country}",
                "NO_BALANCE": "Saldo insuficiente",
                "BAD_SERVICE": "Um ou mais códigos de serviço inválidos",
                "BAD_KEY": "Chave de API inválida",
                "MAX_PRICE_LOWER": "Preço máximo definido é menor que o preço mínimo disponível"
            }

            for error_code, message in error_messages.items():
                if error_code in response_text:
                    logger.error(f"[ERRO] {message}")
                    return None, None

            logger.error(f"[ERRO] Erro desconhecido: {response_text}")
            return None, None

        except Exception as e:
            logger.error(f"[ERRO] Erro ao comprar número multi-serviço: {str(e)}")
            return None, None

    def buy_number_with_webhook(self, service, country, webhook_url):
        """
        Compra um número com configuração de webhook para receber notificações automáticas.

        Args:
            service (str): Código do serviço (ex: "go" para Gmail)
            country (str): Código do país
            webhook_url (str): URL completa do webhook para receber notificações

        Returns:
            tuple: (activation_id, phone_number) ou (None, None) em caso de falha
        """
        self.refresh_credentials()

        params = {
            'api_key': self.api_key,
            'action': 'getNumber',
            'service': service,
            'country': country,
            'webhook': webhook_url  # Parâmetro para configurar o webhook
        }

        try:
            response = requests.get(self.base_url, params=params, timeout=15)
            response_text = response.text

            if "ACCESS_NUMBER" in response_text:
                _, activation_id, phone_number = response_text.split(":")
                logger.info(
                    f"[OK] Número comprado com webhook: {phone_number} (ID: {activation_id})")

                # Registrar o webhook para este activation_id
                self._register_webhook_callback(activation_id, webhook_url)

                return activation_id.strip(), phone_number.strip()

            # Tratamento de erros específicos (similar ao método buy_number)
            error_messages = {
                "NO_NUMBERS": "Sem números disponíveis",
                "NO_BALANCE": "Saldo insuficiente",
                "BAD_SERVICE": "Serviço inválido",
                "BAD_KEY": "Chave de API inválida"
            }

            for error_code, message in error_messages.items():
                if error_code in response_text:
                    logger.error(
                        f"[ERRO] {message} para {service} no país {country}")
                    return None, None

            logger.error(f"[ERRO] Erro desconhecido: {response_text}")
            return None, None

        except Exception as e:
            logger.error(f"[ERRO] Erro ao comprar número com webhook: {str(e)}")
            return None, None

    def buy_multi_service_with_webhook(self, services, country, webhook_url):
        """
        Compra um número compatível com múltiplos serviços e configura webhook.

        Args:
            services (list): Lista de códigos de serviço (ex: ["go", "tk", "ig"])
            country (str): Código do país
            webhook_url (str): URL completa do webhook para receber notificações

        Returns:
            tuple: (activation_id, phone_number) ou (None, None) em caso de falha
        """
        self.refresh_credentials()

        # Converter lista de serviços para string separada por vírgulas
        services_str = ",".join(services)

        params = {
            'api_key': self.api_key,
            'action': 'getNumber',
            'service': services_str,
            'country': country,
            'multiService': '1',  # Indicar número multi-serviço
            'webhook': webhook_url  # Configurar webhook
        }

        try:
            response = requests.get(self.base_url, params=params, timeout=15)
            response_text = response.text

            if "ACCESS_NUMBER" in response_text:
                _, activation_id, phone_number = response_text.split(":")
                logger.info(
                    f"[OK] Número multi-serviço com webhook: {phone_number} (ID: {activation_id})")
                logger.info(f"[OK] Serviços habilitados: {services_str}")

                # Registrar o webhook para este activation_id
                self._register_webhook_callback(activation_id, webhook_url)

                return activation_id.strip(), phone_number.strip()

            # Tratamento de erros (similar aos métodos anteriores)
            error_messages = {
                "NO_NUMBERS": f"Sem números multi-serviço disponíveis para {services_str} no país {country}",
                "NO_BALANCE": "Saldo insuficiente",
                "BAD_SERVICE": "Um ou mais códigos de serviço inválidos",
                "BAD_KEY": "Chave de API inválida"
            }

            for error_code, message in error_messages.items():
                if error_code in response_text:
                    logger.error(f"[ERRO] {message}")
                    return None, None

            logger.error(f"[ERRO] Erro desconhecido: {response_text}")
            return None, None

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao comprar número multi-serviço com webhook: {str(e)}")
            return None, None

    def _register_webhook_callback(self, activation_id, webhook_url):
        """
        Registra a associação entre um activation_id e uma URL de webhook.
        Em um sistema real, isso seria armazenado em banco de dados.
        """
        try:
            # Diretório para armazenar callbacks
            sms_data_dir = "sms_data"
            os.makedirs(sms_data_dir, exist_ok=True)

            # Arquivo de configuração de callbacks
            config_path = os.path.join(sms_data_dir, "callbacks.json")

            # Carregar callbacks existentes ou criar novo
            callbacks = {}
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    callbacks = json.load(f)

            # Registrar novo callback
            callbacks[activation_id] = webhook_url

            # Salvar configuração atualizada
            with open(config_path, 'w') as f:
                json.dump(callbacks, f)

            logger.info(f"[OK] Webhook registrado para ativação {activation_id}")

        except Exception as e:
            logger.error(f"[ERRO] Erro ao registrar webhook: {str(e)}")
