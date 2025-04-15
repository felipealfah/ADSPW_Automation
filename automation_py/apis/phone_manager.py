import json
import os
import time
import logging
from datetime import datetime, timedelta
import requests
from apis.sms_api import SMSAPI

logger = logging.getLogger(__name__)


class PhoneManager:
    """
    Gerencia números de telefone, permitindo reutilização de números recentes.
    Otimiza uso de créditos do serviço SMS guardando números que ainda podem ser usados.
    """

    def __init__(self, storage_path="credentials/phone_numbers.json"):
        """
        Inicializa o gerenciador de números de telefone.

        Args:
            storage_path: Caminho para o arquivo JSON de armazenamento
        """
        self.storage_path = storage_path
        self.numbers = self._load_numbers()
        self.reuse_window = 30 * 60  # 30 minutos em segundos - janela de reutilização
        self.api_key = self.load_api_key()

        # Definição dos países e suas prioridades
        self.selected_countries = {
            # Brasil como primeira opção (prioridade absoluta)
            "73": "Brasil",
            "151": "Chile",
            "16": "Reino Unido",  # Reino Unido
            "117": "Portugal",  # Portugal
            "40": "Canadá",     # Canadá
            "12": "Estados Unidos",  # Estados Unidos
            "52": "México",     # México
            "224": "Paraguai",  # Paraguai
            "156": "Peru",      # Peru
            "225": "Uruguai"   # Uruguai

        }

        # Ordem de prioridade para busca de países
        self.country_priority = ["73", "151",  "16", "117", "40", "12",
                                 "52", "224", "156", "225"]

        # Instanciar SMSAPI para usar seus métodos
        self.sms_api = SMSAPI(self.api_key)

    def _load_numbers(self):
        """Carrega os números do arquivo de armazenamento."""
        if not os.path.exists(self.storage_path):
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            return []

        try:
            with open(self.storage_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_numbers(self):
        """Salva os números no arquivo de armazenamento."""
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        with open(self.storage_path, 'w') as f:
            json.dump(self.numbers, f, indent=4)

    def add_number(self, phone_number, country_code, activation_id, service="go"):
        """
        Adiciona ou atualiza um número no gerenciador.
        """
        if not all([phone_number, country_code, activation_id]):
            logger.error("❌ Dados de telefone incompletos, não será salvo")
            return False

        current_time = time.time()

        # Verificar se o número já existe
        for number in self.numbers:
            if number["phone_number"] == phone_number:
                # Atualizar dados existentes
                number["last_used"] = current_time
                number["times_used"] += 1
                if service not in number["services"]:
                    number["services"].append(service)
                self._save_numbers()
                logger.info(
                    f"✅ Número {phone_number} atualizado no gerenciador")
                return True

        # Adicionar novo número
        new_number = {
            "phone_number": phone_number,
            "country_code": country_code,
            "activation_id": activation_id,
            "first_used": current_time,
            "last_used": current_time,
            "services": [service],
            "times_used": 1
        }

        self.numbers.append(new_number)
        self._save_numbers()
        logger.info(f"✅ Número {phone_number} adicionado ao gerenciador")
        return True

    def get_reusable_number(self, service="go"):
        """
        Obtém um número reutilizável que ainda está dentro da janela de validade.

        Args:
            service: Código do serviço para o qual o número será usado

        Returns:
            dict: Informações do número reutilizável ou None se não houver
        """
        current_time = time.time()
        valid_numbers = []

        # Limpar números expirados
        self._cleanup_expired_numbers()

        # Buscar números válidos
        for number in self.numbers:
            time_since_last_use = current_time - number["last_used"]

            # Verificar se está dentro da janela de reutilização
            if time_since_last_use < self.reuse_window:
                # Verificar se o número não foi usado para este serviço
                if service not in number["services"]:
                    valid_numbers.append(number)

            # Ordenar por menos utilizado primeiro
        valid_numbers.sort(key=lambda x: x["times_used"])

        if valid_numbers:
            # Atualizar o número selecionado
            selected = valid_numbers[0]
            selected["last_used"] = current_time
            selected["times_used"] += 1
            selected["services"].append(service)
            self._save_numbers()

            time_left = self.reuse_window - \
                (current_time - selected["first_used"])
            minutes_left = int(time_left / 60)

            logger.info(
                f"♻️ Reutilizando número {selected['phone_number']} ({minutes_left} minutos restantes)")
            return selected

        return None

    def _cleanup_expired_numbers(self):
        """Remove números que já expiraram da janela de reutilização."""
        current_time = time.time()
        self.numbers = [
            number for number in self.numbers
            if (current_time - number["first_used"]) < self.reuse_window
        ]
        self._save_numbers()

    def mark_number_used(self, phone_number, service="go"):
        """
        Marca um número como usado para um determinado serviço.

        Args:
            phone_number: Número de telefone
            service: Código do serviço
        """
        for number in self.numbers:
            if number["phone_number"] == phone_number:
                number["last_used"] = time.time()
                number["times_used"] += 1
                if service not in number["services"]:
                    number["services"].append(service)
                self._save_numbers()
                return True
        return False

    def get_stats(self):
        """
        Retorna estatísticas sobre os números gerenciados.

        Returns:
            dict: Estatísticas de uso dos números
        """
        total_numbers = len(self.numbers)
        total_uses = sum(number.get("times_used", 0)
                         for number in self.numbers)
        active_numbers = sum(
            1 for number in self.numbers if number.get("is_active", False))

        # Contar serviços utilizados
        total_services = sum(len(number.get("services", []))
                             for number in self.numbers)

        return {
            "total_numbers": total_numbers,
            "total_uses": total_uses,
            "active_numbers": active_numbers,
            "total_services": total_services,
            "estimated_savings": self.calculate_estimated_savings()
        }

    def calculate_estimated_savings(self):
        """Calcula a economia estimada com base no uso dos números."""
        total_savings = 0
        for number in self.numbers:
            # Supondo que você tenha um campo 'savings_per_use' em cada número
            savings_per_use = number.get("savings_per_use", 0)
            times_used = number.get("times_used", 0)
            total_savings += savings_per_use * times_used
        return total_savings

    def load_api_key(self):
        """Carrega a chave da API do arquivo de credenciais."""
        try:
            with open("credentials/credentials.json", "r") as file:
                credentials = json.load(file)
                return credentials.get("SMS_ACTIVATE_API_KEY", None)
        except Exception as e:
            logging.error(f"Erro ao carregar a chave da API: {str(e)}")
            return None

    def cancel_number(self, number_id):
        """
        Cancela um número na API do SMS Activate.

        Args:
            number_id (str): O ID do número a ser cancelado.

        Returns:
            bool: True se o cancelamento foi bem-sucedido, False caso contrário.
        """
        url = "https://sms-activate.guru/stubs/handler_api.php"
        params = {
            "api_key": self.api_key,  # Usar a chave de API carregada
            "action": "cancel",
            "id": number_id
        }

        try:
            response = requests.post(url, params=params)
            response_data = response.text

            if "STATUS_OK" in response_data:
                logging.info(f"Número {number_id} cancelado com sucesso.")
                return True
            else:
                logging.error(
                    f"Erro ao cancelar número {number_id}: {response_data}")
                return False
        except Exception as e:
            logging.error(
                f"Erro ao fazer requisição para cancelar número: {str(e)}")
            return False

    def remove_number(self, phone_number):
        """
        Remove um número do gerenciador.

        Args:
            phone_number (str): O número de telefone a ser removido.

        Returns:
            bool: True se a remoção foi bem-sucedida, False caso contrário.
        """
        for i, number in enumerate(self.numbers):
            if number["phone_number"] == phone_number:
                del self.numbers[i]  # Remove o número da lista
                self._save_numbers()  # Salva as alterações no arquivo
                logging.info(f"Número {phone_number} removido com sucesso.")
                return True
        logging.warning(f"Número {phone_number} não encontrado.")
        return False

    def execute_with_retry(self, func, max_retries=3, retry_delay=2):
        """
        Executa uma função com retry automático em caso de falhas.

        Args:
            func: Função a ser executada
            max_retries: Número máximo de tentativas
            retry_delay: Tempo de espera entre tentativas (segundos)

        Returns:
            O resultado da função ou False em caso de falha
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                result = func()
                return result
            except Exception as e:
                last_error = e
                logger.warning(
                    f"⚠️ Tentativa {attempt+1}/{max_retries} falhou: {str(e)}")

                # Somente faz o log e aguarda se não for a última tentativa
                if attempt < max_retries - 1:
                    logger.info(
                        f"🔄 Aguardando {retry_delay}s antes da próxima tentativa...")
                    time.sleep(retry_delay)
                else:
                    logger.error(
                        f"❌ Falha após {max_retries} tentativas: {str(e)}")

        # Se chegou aqui, todas as tentativas falharam
        logger.error(
            f"❌ Todas as tentativas falharam: {str(last_error) if last_error else 'Erro desconhecido'}")
        return False

    def get_number_status(self, country, service):
        """
        Verifica disponibilidade de números para um serviço em um país específico.

        Args:
            country (str): Código do país
            service (str): Código do serviço (ex: "go" para Gmail)

        Returns:
            int: Quantidade de números disponíveis ou 0 se não houver nenhum
        """
        try:
            # Chamar o método na API SMS
            status = self.sms_api.get_number_status(country, service)

            # Validar o retorno
            if not isinstance(status, int) and status is not None:
                logger.warning(
                    f"⚠️ Formato inválido de status: {type(status)}")
                return 0

            return status if status is not None else 0

        except Exception as e:
            logger.error(
                f"❌ Erro ao verificar disponibilidade de números: {str(e)}")
            return 0

    def check_google_numbers_availability(self):
        """
        Verifica a disponibilidade de números para Gmail (serviço "go") em todos os países.
        Gera um relatório detalhado com informações de disponibilidade e preço.

        Returns:
            dict: Um dicionário com informações detalhadas de disponibilidade e preço
        """
        service = "go"  # Serviço Gmail
        logger.info(
            f"⏳ Verificando disponibilidade de números para Gmail em todos os países...")

        # Verificar saldo
        balance = self.sms_api.get_balance()
        logger.info(f"💰 Saldo disponível: {balance} RUB")

        # Solicitar preços e disponibilidade à API
        countries_data = self.sms_api.compare_prices_in_selected_countries(
            service)

        if not countries_data:
            logger.error(
                "❌ Não foi possível obter dados de países para o serviço Gmail")
            return {}

        # Organizar por ordem de prioridade e disponibilidade
        priority_data = []

        # Primeiro adicionar países na ordem de prioridade
        for country_code in self.country_priority:
            # Buscar informações do país
            country_info = next(
                (item for item in countries_data if item["country_code"] == country_code), None)

            if country_info and country_info.get("available", 0) > 0:
                # Adicionar informação da prioridade
                position = self.country_priority.index(country_code) + 1
                country_info["priority"] = position
                priority_data.append(country_info)

                logger.info(
                    f"✅ {country_info['country_name']} (Prioridade {position}): {country_info['available']} números disponíveis, {country_info['price']} RUB")
            elif country_code in self.selected_countries:
                # País sem números disponíveis
                country_name = self.selected_countries[country_code]
                logger.warning(
                    f"⚠️ {country_name} (Prioridade {self.country_priority.index(country_code) + 1}): Sem números disponíveis")

        # Resumo
        total_available = sum(item.get("available", 0)
                              for item in priority_data)

        if total_available > 0:
            logger.info(
                f"✅ Total de {total_available} números disponíveis em {len(priority_data)} países")

            # Recomendar país baseado na prioridade e disponibilidade
            recommended = priority_data[0] if priority_data else None
            if recommended:
                logger.info(
                    f"🔍 País recomendado: {recommended['country_name']} (código {recommended['country_code']})")
                logger.info(
                    f"   - {recommended['available']} números disponíveis a {recommended['price']} RUB cada")
        else:
            logger.error("❌ Nenhum número disponível para Gmail")

        return {
            "available_countries": priority_data,
            "total_available": total_available,
            "balance": balance,
            "recommended": priority_data[0] if priority_data else None,
            "service": service
        }

    def buy_multi_service_number(self, services, country=None):
        """
        Compra um número para múltiplos serviços.

        Args:
            services (list): Lista de códigos de serviço (ex: ["go", "tk", "ig"])
            country (str, optional): Código do país. Se None, usa Brasil ou a ordem de prioridade.

        Returns:
            dict: Informações do número comprado ou None se falhou
        """
        if not self.sms_api:
            logger.error("❌ API SMS não inicializada")
            return None

        # Se country não for especificado, tenta Brasil primeiro e depois outros países em ordem de prioridade
        if not country:
            countries_to_try = self.country_priority
        else:
            countries_to_try = [country]

        for country_code in countries_to_try:
            if country_code not in self.selected_countries:
                continue

            country_name = self.selected_countries[country_code]
            logger.info(
                f"🔍 Tentando comprar número multi-serviço em: {country_name} ({country_code})")

            try:
                activation_id, phone_number = self.sms_api.buy_number_multi_service(
                    services, country_code)

                if activation_id and phone_number:
                    logger.info(
                        f"✅ Número multi-serviço obtido: {phone_number} (País: {country_name})")

                    # Salvar o número no gerenciador
                    number_data = {
                        "phone_number": phone_number,
                        "country_code": country_code,
                        "activation_id": activation_id,
                        "services": services,  # Lista dos serviços para os quais o número foi comprado
                        "first_used": time.time(),
                        "last_used": time.time(),
                        "times_used": 1
                    }

                    # Adicionar ao armazenamento interno
                    self.numbers.append(number_data)
                    self._save_numbers()

                    return number_data

            except Exception as e:
                logger.error(
                    f"❌ Erro ao comprar número em {country_name}: {str(e)}")
                continue

        logger.error(
            "❌ Não foi possível comprar número para os serviços especificados em nenhum país")
        return None

    def buy_multi_service_with_webhook(self, services, webhook_url, country=None):
        """
        Compra um número para múltiplos serviços com webhook configurado.

        Args:
            services (list): Lista de códigos de serviço (ex: ["go", "tk", "ig"])
            webhook_url (str): URL do webhook para receber notificações
            country (str, optional): Código do país. Se None, usa Brasil ou a ordem de prioridade.

        Returns:
            dict: Informações do número comprado ou None se falhou
        """
        if not self.sms_api:
            logger.error("❌ API SMS não inicializada")
            return None

        # Se country não for especificado, tenta Brasil primeiro e depois outros países em ordem de prioridade
        if not country:
            countries_to_try = self.country_priority
        else:
            countries_to_try = [country]

        for country_code in countries_to_try:
            if country_code not in self.selected_countries:
                continue

            country_name = self.selected_countries[country_code]
            logger.info(
                f"🔍 Tentando comprar número multi-serviço com webhook em: {country_name} ({country_code})")

            try:
                activation_id, phone_number = self.sms_api.buy_multi_service_with_webhook(
                    services, country_code, webhook_url)

                if activation_id and phone_number:
                    logger.info(
                        f"✅ Número multi-serviço com webhook obtido: {phone_number} (País: {country_name})")

                    # Salvar o número no gerenciador
                    number_data = {
                        "phone_number": phone_number,
                        "country_code": country_code,
                        "activation_id": activation_id,
                        "services": services,
                        "webhook_url": webhook_url,
                        "first_used": time.time(),
                        "last_used": time.time(),
                        "times_used": 1
                    }

                    # Adicionar ao armazenamento interno
                    self.numbers.append(number_data)
                    self._save_numbers()

                    return number_data

            except Exception as e:
                logger.error(
                    f"❌ Erro ao comprar número com webhook em {country_name}: {str(e)}")
                continue

        logger.error(
            "❌ Não foi possível comprar número com webhook para os serviços especificados em nenhum país")
        return None

    def buy_multi_service_number_br(self, services, operator=None, max_price=None):
        """
        Compra um número brasileiro específico para múltiplos serviços.
        Prioriza a qualidade e disponibilidade, mesmo que seja mais caro.

        Args:
            services (list): Lista de códigos de serviço (ex: ["go", "tk", "ig"])
            operator (str, optional): Operadora específica (claro, vivo, tim, oi)
            max_price (float, optional): Preço máximo aceitável em rublos

        Returns:
            dict: Informações do número comprado ou None se falhou
        """
        if not self.sms_api:
            logger.error("❌ API SMS não inicializada")
            return None

        # Código do Brasil
        country_code = "73"
        country_name = self.selected_countries.get(country_code, "Brasil")

        # Lista de operadoras brasileiras para tentar, se nenhuma operadora for especificada
        br_operators = ["claro", "vivo", "tim", "oi"]

        # Se uma operadora específica foi solicitada, tente apenas essa
        operators_to_try = [operator] if operator else br_operators

        # Verificar disponibilidade e preços para operadoras brasileiras
        logger.info(
            f"🔍 Verificando disponibilidade de números para serviços {services} no Brasil")

        for op in operators_to_try:
            try:
                logger.info(f"📱 Tentando operadora: {op.upper()}")

                # Tentar comprar o número com esta operadora
                activation_id, phone_number = self.sms_api.buy_number_multi_service(
                    services,
                    country_code,
                    operator=op,
                    max_price=max_price
                )

                if activation_id and phone_number:
                    logger.info(
                        f"✅ Número multi-serviço obtido: {phone_number} (Operadora: {op.upper()})")

                    # Salvar o número no gerenciador
                    number_data = {
                        "phone_number": phone_number,
                        "country_code": country_code,
                        "activation_id": activation_id,
                        "operator": op,
                        "services": services,
                        "first_used": time.time(),
                        "last_used": time.time(),
                        "times_used": 1
                    }

                    # Adicionar ao armazenamento interno
                    self.numbers.append(number_data)
                    self._save_numbers()

                    return number_data

            except Exception as e:
                logger.error(
                    f"❌ Erro ao comprar número com operadora {op}: {str(e)}")
                continue

        # Se não conseguiu com nenhuma operadora específica, tentar sem especificar operadora
        if operator is not None:  # Se já tentamos sem operadora, não tente novamente
            logger.info("📱 Tentando sem especificar operadora...")
            try:
                activation_id, phone_number = self.sms_api.buy_number_multi_service(
                    services,
                    country_code,
                    max_price=max_price
                )

                if activation_id and phone_number:
                    logger.info(
                        f"✅ Número multi-serviço obtido: {phone_number} (Operadora: não especificada)")

                    # Salvar o número no gerenciador
                    number_data = {
                        "phone_number": phone_number,
                        "country_code": country_code,
                        "activation_id": activation_id,
                        "services": services,
                        "first_used": time.time(),
                        "last_used": time.time(),
                        "times_used": 1
                    }

                    # Adicionar ao armazenamento interno
                    self.numbers.append(number_data)
                    self._save_numbers()

                    return number_data
            except Exception as e:
                logger.error(
                    f"❌ Erro ao comprar número sem operadora específica: {str(e)}")

        logger.error(
            "❌ Não foi possível comprar número brasileiro para os serviços especificados")
        return None

    def check_multi_service_availability_br(self, services):
        """
        Verifica a disponibilidade de números brasileiros para múltiplos serviços
        e retorna informações sobre preços e operadoras.

        Args:
            services (list): Lista de códigos de serviço (ex: ["go", "tk", "ig"])

        Returns:
            dict: Informações sobre disponibilidade, preços e operadoras
        """
        # Código do Brasil
        country_code = "73"
        country_name = "Brasil"

        # Lista de operadoras brasileiras
        br_operators = ["claro", "vivo", "tim", "oi"]

        result = {
            "services": services,
            "country": country_name,
            "country_code": country_code,
            "operators": {},
            "total_available": 0,
            "recommended_operator": None,
            "min_price": float("inf"),
            "max_price": 0
        }

        # Obter preços gerais para o serviço
        prices_data = self.sms_api.get_prices()
        services_str = ",".join(services)

        # Verificar disponibilidade para cada operadora
        for op in br_operators:
            try:
                # Este é um placeholder - a API atual não suporta verificação por operadora
                # Idealmente, chamaríamos algo como self.sms_api.get_number_status_by_operator
                # Como alternativa, podemos tentar comprar um número e cancelar imediatamente

                # Por enquanto, apenas simulamos a verificação
                is_available = True  # Placeholder
                price = 0  # Placeholder

                if is_available:
                    result["operators"][op] = {
                        "available": True,
                        "price": price
                    }
                    result["total_available"] += 1

                    # Atualizar min/max preço
                    if price < result["min_price"]:
                        result["min_price"] = price
                    if price > result["max_price"]:
                        result["max_price"] = price

                    # Se ainda não temos operadora recomendada, use esta
                    if not result["recommended_operator"]:
                        result["recommended_operator"] = op

            except Exception as e:
                logger.error(
                    f"❌ Erro ao verificar disponibilidade para operadora {op}: {str(e)}")
                result["operators"][op] = {
                    "available": False,
                    "error": str(e)
                }

        return result
