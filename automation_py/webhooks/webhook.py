import logging
import json
import os
import sys
import time
from threading import Thread
import requests

# Adicionando os diretórios necessários ao PYTHONPATH
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)  # automation_py
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Importar módulos locais após configurar PYTHONPATH
from flask import Flask, request, jsonify
from powerads_api.profiles import ProfileManager, get_profiles
from credentials.credentials_manager import get_credential

app = Flask(__name__)

# Caminho para armazenar dados dos SMS recebidos
SMS_DATA_DIR = "sms_data"
os.makedirs(SMS_DATA_DIR, exist_ok=True)

# Armazenamento em memória para códigos SMS recebidos
sms_codes = {}


@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint para verificar se o serviço está funcionando."""
    return jsonify({"status": "ok"})

# --- Rotas para receber notificações de SMS da API SMS-Activate ---


@app.route('/sms-webhook', methods=['POST'])
def sms_webhook():
    """Endpoint para receber notificações de SMS da API SMS-Activate."""
    try:
        # Verificar se a requisição é um JSON
        if request.is_json:
            data = request.json
        else:
            # Se não for JSON, tentar processar como form data
            data = request.form.to_dict()

        logger.info(f"📩 Webhook recebido: {data}")

        # Extrair informações importantes
        activation_id = data.get('id')
        phone_number = data.get('phone')
        sms_code = data.get('sms')
        status = data.get('status')

        # Validar dados obrigatórios
        if not all([activation_id, sms_code]):
            logger.warning(f"⚠️ Dados incompletos no webhook: {data}")
            return jsonify({"success": False, "error": "Dados incompletos"}), 400

        # Armazenar o código SMS
        sms_codes[activation_id] = {
            "phone_number": phone_number,
            "sms_code": sms_code,
            "status": status,
            "received_at": time.time()
        }

        # Salvar em arquivo para persistência
        save_sms_data(activation_id, sms_codes[activation_id])

        # Processar o código SMS recebido em uma thread separada
        # para não bloquear a resposta ao webhook
        Thread(target=process_sms_code, args=(
            activation_id, phone_number, sms_code, status)).start()

        # Retornar sucesso imediatamente
        return jsonify({"success": True, "message": "SMS recebido e processado"})

    except Exception as e:
        logger.error(f"❌ Erro ao processar webhook: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


def save_sms_data(activation_id, data):
    """Salva dados do SMS em arquivo para persistência."""
    try:
        file_path = os.path.join(SMS_DATA_DIR, f"{activation_id}.json")
        with open(file_path, 'w') as f:
            json.dump(data, f)
        logger.info(f"✅ Dados do SMS {activation_id} salvos com sucesso")
    except Exception as e:
        logger.error(f"❌ Erro ao salvar dados do SMS: {str(e)}")


def process_sms_code(activation_id, phone_number, sms_code, status):
    """
    Processa um código SMS recebido via webhook.
    Esta função pode realizar ações como:
    - Notificar outro serviço
    - Atualizar status em banco de dados
    - Fazer callback para o sistema principal
    """
    try:
        logger.info(f"⚙️ Processando SMS para ativação {activation_id}")

        # Verificar se há uma URL de callback configurada para esta ativação
        # (isso seria configurado quando o número é comprado)
        callback_url = get_callback_url(activation_id)

        if callback_url:
            # Enviar o código SMS para o callback
            response = requests.post(callback_url, json={
                "activation_id": activation_id,
                "phone_number": phone_number,
                "sms_code": sms_code,
                "status": status
            }, timeout=10)

            if response.status_code == 200:
                logger.info(
                    f"✅ Código SMS enviado para callback: {callback_url}")
            else:
                logger.error(
                    f"❌ Erro ao enviar para callback: {response.status_code} - {response.text}")
        else:
            logger.info(
                f"ℹ️ Nenhum callback configurado para ativação {activation_id}")

        # Registrar processamento bem-sucedido
        update_sms_status(activation_id, "processed")

    except Exception as e:
        logger.error(f"❌ Erro ao processar código SMS: {str(e)}")
        update_sms_status(activation_id, "failed", str(e))


def get_callback_url(activation_id):
    """
    Recupera a URL de callback para uma ativação específica.
    Implementação simplificada - em um sistema real, isso buscaria de um banco de dados.
    """
    # Exemplo: buscar de um arquivo de configuração
    try:
        config_path = os.path.join(SMS_DATA_DIR, "callbacks.json")
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                callbacks = json.load(f)
                return callbacks.get(activation_id)
    except Exception:
        pass
    return None


def update_sms_status(activation_id, status, error=None):
    """Atualiza o status de processamento de um SMS."""
    try:
        if activation_id in sms_codes:
            sms_codes[activation_id]["processing_status"] = status
            if error:
                sms_codes[activation_id]["processing_error"] = error

            # Atualizar o arquivo
            save_sms_data(activation_id, sms_codes[activation_id])
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar status do SMS: {str(e)}")


@app.route('/sms-status/<activation_id>', methods=['GET'])
def get_sms_status(activation_id):
    """Endpoint para verificar o status de um SMS pelo ID de ativação."""
    if activation_id in sms_codes:
        return jsonify(sms_codes[activation_id])
    else:
        # Tentar carregar do arquivo
        file_path = os.path.join(SMS_DATA_DIR, f"{activation_id}.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                return jsonify(data)
            except Exception as e:
                return jsonify({"success": False, "error": str(e)}), 500

        return jsonify({"success": False, "error": "Activation ID not found"}), 404


# --- Rotas para perfis do AdsPower ---
@app.route('/profiles', methods=['GET'])
def list_profiles():
    """Endpoint para listar todos os perfis do AdsPower."""
    try:
        # Parâmetros da query
        force_refresh = request.args.get(
            'force_refresh', 'false').lower() == 'true'

        # Obter base_url e headers das credenciais
        base_url = get_credential("PA_BASE_URL")
        api_key = get_credential("PA_API_KEY")

        headers = {
            "Authorization": f"Bearer {api_key}" if api_key else "",
            "Content-Type": "application/json"
        }

        # Criar uma instância temporária do ProfileManager
        class TempCache:
            def __init__(self):
                self.profiles_cache = {}

        profile_manager = ProfileManager(TempCache())

        # Obter todos os perfis ativos
        profiles = profile_manager.get_all_profiles(
            force_refresh=force_refresh)

        if profiles:
            # Transformar a lista para incluir apenas informações relevantes
            simplified_profiles = []
            for profile in profiles:
                simplified_profiles.append({
                    "user_id": profile.get("user_id"),
                    "name": profile.get("name"),
                    "group_id": profile.get("group_id"),
                    "group_name": profile.get("group_name"),
                    "status": profile.get("status"),
                    "created_time": profile.get("created_time"),
                    "updated_time": profile.get("updated_time")
                })

            logger.info(
                f"[OK] Retornando {len(simplified_profiles)} perfis do AdsPower")
            return jsonify({
                "success": True,
                "count": len(simplified_profiles),
                "profiles": simplified_profiles
            })
        else:
            logger.warning("[ERRO] Nenhum perfil encontrado no AdsPower")
            return jsonify({
                "success": False,
                "error": "Nenhum perfil encontrado"
            }), 404

    except Exception as e:
        logger.error(f"[ERRO] Erro ao listar perfis do AdsPower: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# Endpoint para obter detalhes de um perfil específico
@app.route('/profiles/<user_id>', methods=['GET'])
def get_profile_details(user_id):
    """Endpoint para obter detalhes de um perfil específico."""
    try:
        # Obter base_url e headers das credenciais
        base_url = get_credential("PA_BASE_URL")
        api_key = get_credential("PA_API_KEY")

        headers = {
            "Authorization": f"Bearer {api_key}" if api_key else "",
            "Content-Type": "application/json"
        }

        # Criar uma instância temporária do ProfileManager
        class TempCache:
            def __init__(self):
                self.profiles_cache = {}

        profile_manager = ProfileManager(TempCache())

        # Obter todos os perfis
        profiles = profile_manager.get_all_profiles(force_refresh=True)

        # Encontrar o perfil específico
        profile = next(
            (p for p in profiles if p.get("user_id") == user_id), None)

        if profile:
            logger.info(f"[OK] Perfil {user_id} encontrado")
            return jsonify({
                "success": True,
                "profile": profile
            })
        else:
            logger.warning(f"[ERRO] Perfil {user_id} não encontrado")
            return jsonify({
                "success": False,
                "error": f"Perfil {user_id} não encontrado"
            }), 404

    except Exception as e:
        logger.error(
            f"[ERRO] Erro ao obter detalhes do perfil {user_id}: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# --- Rotas para criar contas Gmail ---


@app.route('/create-gmail/<user_id>', methods=['POST'])
def create_gmail_account(user_id):
    """
    Endpoint para criar uma conta Gmail usando um perfil específico do AdsPower.

    Respostas possíveis:
    1. 200 - Conta criada com sucesso (retorna os dados da conta)
    2. 400 - Perfil não encontrado
    3. 500 - Erro ao criar conta (com motivo detalhado)
    """
    try:
        # Verificar se o ID do perfil foi fornecido
        if not user_id:
            return jsonify({
                "success": False,
                "error": "ID do perfil não fornecido"
            }), 400

        # Recuperar parâmetros opcionais do corpo da requisição
        data = request.json or {}
        phone_params = data.get('phone_params')

        # Obter as credenciais necessárias
        from credentials.credentials_manager import get_credential
        from powerads_api.browser_manager import BrowserManager, BrowserConfig
        from powerads_api.ads_power_manager import AdsPowerManager
        from apis.sms_api import SMSAPI
        from automations.data_generator import generate_gmail_credentials
        from automations.gmail_creator.core import GmailCreator

        # Configurar dependências
        base_url = get_credential(
            "PA_BASE_URL")
        api_key = get_credential("PA_API_KEY")
        sms_api_key = get_credential("SMS_ACTIVATE_API_KEY")

        # Inicializar o gerenciador do AdsPower
        adspower_manager = AdsPowerManager(base_url, api_key)

        # Esperar um tempo para garantir que a conexão seja estabelecida
        time.sleep(2)

        # Verificar se o perfil existe
        profiles = get_profiles(base_url, {
            "Authorization": f"Bearer {api_key}" if api_key else "",
            "Content-Type": "application/json"
        })
        profile_exists = any(profile.get("user_id") ==
                             user_id for profile in profiles)

        if not profile_exists:
            return jsonify({
                "success": False,
                "error": "Perfil não encontrado",
                "error_code": "PROFILE_NOT_FOUND",
                "user_id": user_id
            }), 400

        # Inicializar componentes
        sms_api = SMSAPI(sms_api_key)

        # Gerar credenciais aleatórias
        credentials = generate_gmail_credentials()

        # Configurar browser manager
        browser_config = BrowserConfig(headless=False, max_wait_time=30)
        browser_manager = BrowserManager(adspower_manager)
        browser_manager.set_config(browser_config)

        # Inicializar GmailCreator
        gmail_creator = GmailCreator(
            browser_manager=browser_manager,
            credentials=credentials,
            sms_api=sms_api,
            profile_name=user_id
        )

        # Executar criação da conta
        logger.info(
            f"[INICIO] Iniciando criação de conta Gmail para perfil {user_id}")
        success, account_data = gmail_creator.create_account(
            user_id, phone_params)

        try:
            # Fechar o browser ao finalizar (independente do resultado)
            browser_manager.close_browser(user_id)
        except Exception as e:
            logger.error(f"[ERRO] Erro ao fechar o browser: {str(e)}")

        if success and account_data:
            # Adicionar timestamp de criação
            account_data["creation_time"] = time.time()

            # Salvar os dados da conta criada
            try:
                accounts_file = "sms_data/gmail_accounts.json"
                accounts = []

                if os.path.exists(accounts_file):
                    with open(accounts_file, "r") as file:
                        try:
                            accounts = json.load(file)
                        except json.JSONDecodeError:
                            accounts = []

                accounts.append(account_data)

                with open(accounts_file, "w") as file:
                    json.dump(accounts, file, indent=4)
            except Exception as e:
                logger.error(f"[ERRO] Erro ao salvar dados da conta: {str(e)}")

            # Retornar sucesso com os dados da conta
            logger.info(
                f"[OK] Conta criada com sucesso: {account_data['email']}")
            return jsonify({
                "success": True,
                "message": "Conta Gmail criada com sucesso",
                "account": account_data
            }), 200
        else:
            # Retornar erro com motivo
            error_message = "Falha ao criar conta Gmail. Verifique os logs para mais detalhes."
            logger.error(f"[ERRO] {error_message}")
            return jsonify({
                "success": False,
                "error": error_message,
                "error_code": "CREATION_FAILED",
                "user_id": user_id
            }), 500

    except Exception as e:
        logger.error(f"[ERRO] Erro ao criar conta Gmail: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "error_code": "UNEXPECTED_ERROR",
            "user_id": user_id
        }), 500


if __name__ == '__main__':
    # Iniciar o servidor em modo de produção
    # Em ambiente de produção, use um servidor WSGI como Gunicorn
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)
