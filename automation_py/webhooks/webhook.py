from flask import Flask, request, jsonify, send_from_directory
from powerads_api.profiles import ProfileManager, get_profiles
from credentials.credentials_manager import get_credential
from flask_swagger_ui import get_swaggerui_blueprint
import logging
import json
import os
import sys
import time
import uuid
from threading import Thread
import requests
from datetime import datetime


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

app = Flask(__name__)

# Configuração do Swagger UI
SWAGGER_URL = '/api/docs'  # URL para acessar a documentação da API
API_URL = '/static/swagger.json'  # Arquivo de especificação da API

# Criar diretório para arquivos estáticos se não existir
static_dir = os.path.join(current_dir, 'static')
os.makedirs(static_dir, exist_ok=True)

# Criar a especificação Swagger
swagger_spec = {
    "swagger": "2.0",
    "info": {
        "title": "AdsPower RPA API",
        "description": "API para automação RPA com AdsPower",
        "version": "1.0.0"
    },
    "basePath": "/",
    "schemes": ["http", "https"],
    "consumes": ["application/json"],
    "produces": ["application/json"],
    "paths": {
        "/health": {
            "get": {
                "summary": "Verificação de saúde da API",
                "description": "Endpoint para verificar se o serviço está funcionando",
                "produces": ["application/json"],
                "responses": {
                    "200": {
                        "description": "Serviço funcionando corretamente",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "status": {"type": "string"}
                            }
                        }
                    }
                }
            }
        },
        "/sms-webhook": {
            "post": {
                "summary": "Receber notificações de SMS",
                "description": "Endpoint para receber notificações de SMS da API SMS-Activate",
                "produces": ["application/json"],
                "parameters": [
                    {
                        "name": "body",
                        "in": "body",
                        "description": "Dados do webhook SMS",
                        "required": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "phone": {"type": "string"},
                                "sms": {"type": "string"},
                                "status": {"type": "string"}
                            }
                        }
                    }
                ],
                "responses": {
                    "200": {
                        "description": "SMS recebido com sucesso",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "success": {"type": "boolean"},
                                "message": {"type": "string"}
                            }
                        }
                    },
                    "400": {
                        "description": "Dados incompletos",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "success": {"type": "boolean"},
                                "error": {"type": "string"}
                            }
                        }
                    }
                }
            }
        },
        "/sms-status/{activation_id}": {
            "get": {
                "summary": "Verificar status de SMS",
                "description": "Endpoint para verificar o status de um SMS pelo ID de ativação",
                "produces": ["application/json"],
                "parameters": [
                    {
                        "name": "activation_id",
                        "in": "path",
                        "description": "ID de ativação do SMS",
                        "required": True,
                        "type": "string"
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Status do SMS",
                        "schema": {
                            "type": "object"
                        }
                    },
                    "404": {
                        "description": "SMS não encontrado",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "success": {"type": "boolean"},
                                "error": {"type": "string"}
                            }
                        }
                    }
                }
            }
        },
        "/profiles": {
            "get": {
                "summary": "Listar perfis do AdsPower",
                "description": "Endpoint para listar todos os perfis do AdsPower",
                "produces": ["application/json"],
                "parameters": [
                    {
                        "name": "force_refresh",
                        "in": "query",
                        "description": "Forçar atualização dos perfis",
                        "required": False,
                        "type": "boolean",
                        "default": False
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Lista de perfis",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "success": {"type": "boolean"},
                                "count": {"type": "integer"},
                                "profiles": {
                                    "type": "array",
                                    "items": {"type": "object"}
                                }
                            }
                        }
                    },
                    "404": {
                        "description": "Nenhum perfil encontrado",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "success": {"type": "boolean"},
                                "error": {"type": "string"}
                            }
                        }
                    }
                }
            }
        },
        "/profiles/{user_id}": {
            "get": {
                "summary": "Obter detalhes de um perfil",
                "description": "Endpoint para obter detalhes de um perfil específico",
                "produces": ["application/json"],
                "parameters": [
                    {
                        "name": "user_id",
                        "in": "path",
                        "description": "ID do perfil",
                        "required": True,
                        "type": "string"
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Detalhes do perfil",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "success": {"type": "boolean"},
                                "profile": {"type": "object"}
                            }
                        }
                    },
                    "404": {
                        "description": "Perfil não encontrado",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "success": {"type": "boolean"},
                                "error": {"type": "string"}
                            }
                        }
                    }
                }
            }
        },
        "/gmail-job-status/{job_id}": {
            "get": {
                "summary": "Verificar status de job Gmail",
                "description": "Endpoint para verificar o status de um job de criação de Gmail",
                "produces": ["application/json"],
                "parameters": [
                    {
                        "name": "job_id",
                        "in": "path",
                        "description": "ID do job",
                        "required": True,
                        "type": "string"
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Status do job",
                        "schema": {
                            "type": "object"
                        }
                    }
                }
            }
        },
        "/gmail-accounts": {
            "get": {
                "summary": "Listar contas Gmail criadas",
                "description": "Endpoint para listar todas as contas Gmail criadas",
                "produces": ["application/json"],
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "description": "Número máximo de contas a retornar",
                        "required": False,
                        "type": "integer",
                        "default": 100
                    },
                    {
                        "name": "newest_first",
                        "in": "query",
                        "description": "Retornar contas mais recentes primeiro",
                        "required": False,
                        "type": "boolean",
                        "default": True
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Lista de contas Gmail",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "success": {"type": "boolean"},
                                "count": {"type": "integer"},
                                "accounts": {
                                    "type": "array",
                                    "items": {"type": "object"}
                                }
                            }
                        }
                    }
                }
            }
        },
        "/n8n/batch-gmail-creation": {
            "post": {
                "summary": "Criar contas Gmail em lote",
                "description": "Endpoint para criar múltiplas contas Gmail em lote",
                "produces": ["application/json"],
                "parameters": [
                    {
                        "name": "body",
                        "in": "body",
                        "description": "Dados para criação em lote",
                        "required": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "profiles": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "user_id": {"type": "string"},
                                            "phone_params": {"type": "object"},
                                            "headless": {"type": "boolean"}
                                        }
                                    }
                                },
                                "common_params": {"type": "object"},
                                "max_concurrent": {"type": "integer"},
                                "webhook_callback": {"type": "string"}
                            }
                        }
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Lote criado com sucesso",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "success": {"type": "boolean"},
                                "batch_id": {"type": "string"},
                                "total_jobs": {"type": "integer"},
                                "jobs": {"type": "array"},
                                "status_url": {"type": "string"}
                            }
                        }
                    }
                }
            }
        },
        "/n8n/batch-status/{batch_id}": {
            "get": {
                "summary": "Verificar status de lote",
                "description": "Endpoint para verificar o status de um lote de criação de contas Gmail",
                "produces": ["application/json"],
                "parameters": [
                    {
                        "name": "batch_id",
                        "in": "path",
                        "description": "ID do lote",
                        "required": True,
                        "type": "string"
                    },
                    {
                        "name": "include_jobs",
                        "in": "query",
                        "description": "Incluir detalhes de cada job",
                        "required": False,
                        "type": "boolean",
                        "default": False
                    },
                    {
                        "name": "include_accounts",
                        "in": "query",
                        "description": "Incluir detalhes das contas criadas",
                        "required": False,
                        "type": "boolean",
                        "default": False
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Status do lote",
                        "schema": {
                            "type": "object"
                        }
                    }
                }
            }
        },
        "/n8n/batch-cancel/{batch_id}": {
            "post": {
                "summary": "Cancelar lote",
                "description": "Endpoint para cancelar um lote de criação de contas Gmail",
                "produces": ["application/json"],
                "parameters": [
                    {
                        "name": "batch_id",
                        "in": "path",
                        "description": "ID do lote",
                        "required": True,
                        "type": "string"
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Lote cancelado",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "success": {"type": "boolean"},
                                "message": {"type": "string"},
                                "batch_id": {"type": "string"},
                                "status": {"type": "string"},
                                "cancelled_jobs": {"type": "integer"}
                            }
                        }
                    }
                }
            }
        },
        "/n8n-job-status/{job_id}": {
            "get": {
                "summary": "Verificar status de job",
                "description": "Endpoint para verificar o status de um job específico",
                "produces": ["application/json"],
                "parameters": [
                    {
                        "name": "job_id",
                        "in": "path",
                        "description": "ID do job",
                        "required": True,
                        "type": "string"
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Status do job",
                        "schema": {
                            "type": "object"
                        }
                    }
                }
            }
        },
        "/n8n/create-gmail/{user_id}": {
            "post": {
                "summary": "Criar conta Gmail assíncrona",
                "description": "Endpoint para criar uma única conta Gmail de forma assíncrona",
                "produces": ["application/json"],
                "parameters": [
                    {
                        "name": "user_id",
                        "in": "path",
                        "description": "ID do perfil",
                        "required": True,
                        "type": "string"
                    },
                    {
                        "name": "body",
                        "in": "body",
                        "description": "Parâmetros para a criação da conta",
                        "required": False,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "phone_params": {"type": "object"},
                                "headless": {"type": "boolean"},
                                "max_wait_time": {"type": "integer"},
                                "webhook_callback": {"type": "string"}
                            }
                        }
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Job criado com sucesso",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "success": {"type": "boolean"},
                                "message": {"type": "string"},
                                "job_id": {"type": "string"},
                                "user_id": {"type": "string"},
                                "status": {"type": "string"},
                                "status_url": {"type": "string"}
                            }
                        }
                    }
                }
            }
        },
        "/n8n/help": {
            "get": {
                "summary": "Ajuda da API",
                "description": "Endpoint de ajuda que lista todos os endpoints disponíveis para integração com n8n",
                "produces": ["application/json"],
                "responses": {
                    "200": {
                        "description": "Documentação da API",
                        "schema": {
                            "type": "object"
                        }
                    }
                }
            }
        }
    }
}

# Salvar a especificação Swagger em um arquivo JSON
with open(os.path.join(static_dir, 'swagger.json'), 'w') as f:
    json.dump(swagger_spec, f, indent=2)

# Registrar o blueprint do Swagger UI
swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "AdsPower RPA API"
    }
)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

# Rota para servir arquivos estáticos (swagger.json)


@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory(static_dir, path)


# Caminho para armazenar dados dos SMS recebidos
SMS_DATA_DIR = "sms_data"
os.makedirs(SMS_DATA_DIR, exist_ok=True)

# Caminho para armazenar jobs de criação de Gmail
JOBS_DIR = os.path.join(SMS_DATA_DIR, "jobs")
os.makedirs(JOBS_DIR, exist_ok=True)

# Verificar permissões dos diretórios
try:
    # Testar permissões de escrita nos diretórios críticos
    test_file_sms = os.path.join(SMS_DATA_DIR, ".test_permissions")
    test_file_jobs = os.path.join(JOBS_DIR, ".test_permissions")

    with open(test_file_sms, "w") as f:
        f.write("test")
    os.remove(test_file_sms)

    with open(test_file_jobs, "w") as f:
        f.write("test")
    os.remove(test_file_jobs)

    logger.info(
        f"[INICIALIZAÇÃO] Diretórios de dados criados e com permissões de escrita: {SMS_DATA_DIR}, {JOBS_DIR}")
except Exception as e:
    logger.error(
        f"[ERRO CRÍTICO] Problema com permissões nos diretórios de dados: {str(e)}")
    logger.error(
        f"[ERRO CRÍTICO] SMS_DATA_DIR={SMS_DATA_DIR}, JOBS_DIR={JOBS_DIR}")
    logger.error(f"[ERRO CRÍTICO] Diretório atual: {os.getcwd()}")
    logger.error(
        f"[ERRO CRÍTICO] O aplicativo pode não funcionar corretamente sem acesso de escrita a esses diretórios")

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

        logger.info(f" Webhook recebido: {data}")

        # Extrair informações importantes
        activation_id = data.get('id')
        phone_number = data.get('phone')
        sms_code = data.get('sms')
        status = data.get('status')

        # Validar dados obrigatórios
        if not all([activation_id, sms_code]):
            logger.warning(f"[AVISO] Dados incompletos no webhook: {data}")
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
        logger.error(f"[ERRO] Erro ao processar webhook: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


def save_sms_data(activation_id, data):
    """Salva dados do SMS em arquivo para persistência."""
    try:
        file_path = os.path.join(SMS_DATA_DIR, f"{activation_id}.json")
        with open(file_path, 'w') as f:
            json.dump(data, f)
        logger.info(f"[OK] Dados do SMS {activation_id} salvos com sucesso")
    except Exception as e:
        logger.error(f"[ERRO] Erro ao salvar dados do SMS: {str(e)}")


def process_sms_code(activation_id, phone_number, sms_code, status):
    """
    Processa um código SMS recebido via webhook.
    Esta função pode realizar ações como:
    - Notificar outro serviço
    - Atualizar status em banco de dados
    - Fazer callback para o sistema principal
    """
    try:
        logger.info(f" Processando SMS para ativação {activation_id}")

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
                    f"[OK] Código SMS enviado para callback: {callback_url}")
            else:
                logger.error(
                    f"[ERRO] Erro ao enviar para callback: {response.status_code} - {response.text}")
        else:
            logger.info(
                f" Nenhum callback configurado para ativação {activation_id}")

        # Registrar processamento bem-sucedido
        update_sms_status(activation_id, "processed")

    except Exception as e:
        logger.error(f"[ERRO] Erro ao processar código SMS: {str(e)}")
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
        logger.error(f"[ERRO] Erro ao atualizar status do SMS: {str(e)}")


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

# Remover /create-gmail-async/<user_id>
# Remover /create-gmail/<user_id>
# Remover /create-gmail-and-wait/<user_id>
# Manter as funções de apoio que são utilizadas pelos endpoints do n8n


def process_gmail_creation(job_id, user_id, data):
    """
    Processa a criação de conta Gmail em background.

    Esta função é executada em uma thread separada para não bloquear
    a resposta HTTP, permitindo que operações longas sejam executadas
    sem exceder o timeout do Cloudflare.
    """
    job_file = os.path.join(JOBS_DIR, f"{job_id}.json")

    try:
        # Atualizar status para "processing"
        update_job_status(job_id, "processing",
                          "Iniciando processo de criação")

        # Recuperar parâmetros do corpo da requisição
        phone_params = data.get('phone_params', {})

        # Validar phone_params se fornecido
        if phone_params and not isinstance(phone_params, dict):
            update_job_status(job_id, "failed",
                              "O parâmetro phone_params deve ser um objeto",
                              error_details="O parâmetro phone_params foi fornecido em formato inválido. Deve ser um objeto JSON.")
            return

        # Obtendo as credenciais necessárias
        base_url = get_credential("PA_BASE_URL")
        api_key = get_credential("PA_API_KEY")
        sms_api_key = get_credential("SMS_ACTIVATE_API_KEY")

        # Verificar se as credenciais estão disponíveis
        if not base_url or not api_key:
            update_job_status(job_id, "failed",
                              "Credenciais do AdsPower não configuradas",
                              error_details="As credenciais do AdsPower (PA_BASE_URL e/ou PA_API_KEY) não estão configuradas. Verifique as configurações e tente novamente.")
            return

        if not sms_api_key:
            logger.warning(
                "API de SMS não configurada, podem ocorrer falhas na verificação")

        # Importar as classes necessárias
        from automations.gmail_creator.core import GmailCreator
        from automations.data_generator import generate_gmail_credentials
        from apis.sms_api import SMSAPI
        from apis.phone_manager import PhoneManager
        from powerads_api.browser_manager import BrowserManager, BrowserConfig
        from powerads_api.ads_power_manager import AdsPowerManager

        # Verificar se o perfil existe
        profiles = get_profiles(base_url, {
            "Authorization": f"Bearer {api_key}" if api_key else "",
            "Content-Type": "application/json"
        })
        profile_exists = any(profile.get("user_id") ==
                             user_id for profile in profiles)

        if not profile_exists:
            update_job_status(job_id, "failed",
                              f"Perfil {user_id} não encontrado",
                              error_details=f"O perfil com ID {user_id} não foi encontrado no AdsPower. Verifique se o perfil existe e está ativo.")
            return

        # Atualizar status
        update_job_status(job_id, "processing",
                          "Preparando componentes para criação")

        # Configurações vindas da requisição ou padrões
        headless = data.get('headless', False)
        max_wait_time = data.get('max_wait_time', 60)

        # Inicializar componentes
        sms_api = SMSAPI(sms_api_key)
        adspower_manager = AdsPowerManager(base_url, api_key)

        # Garantir que o AdsPower Manager está conectado
        adspower_health = adspower_manager.check_api_health(force_check=True)
        if not adspower_health:
            update_job_status(
                job_id, "failed", "Não foi possível conectar ao AdsPower. Verifique se está em execução.",
                error_details="Falha na conexão com a API do AdsPower. Verifique se o serviço está em execução e se a API está habilitada no endereço correto.")
            return

        # Gerar credenciais aleatórias
        credentials = generate_gmail_credentials()

        # Configurar browser manager
        browser_config = BrowserConfig(
            headless=headless, max_wait_time=max_wait_time)
        browser_manager = BrowserManager(adspower_manager)
        browser_manager.set_config(browser_config)

        # Atualizar status
        update_job_status(job_id, "processing",
                          "Iniciando browser e criação da conta")

        # Inicializar o criador de Gmail
        gmail_creator = GmailCreator(
            browser_manager=browser_manager,
            credentials=credentials,
            sms_api=sms_api,
            profile_name=user_id
        )

        # Tentar iniciar o browser com tratamento de erros específicos
        try:
            # Executar criação da conta
            success, account_data = gmail_creator.create_account(
                user_id, phone_params)
        except ConnectionError as e:
            error_msg = "Erro de conexão ao iniciar o navegador"
            error_details = f"Falha ao conectar com o AdsPower para iniciar o navegador: {str(e)}. " \
                            f"Verifique se o serviço AdsPower está em execução e acessível no endereço {base_url}."
            logger.error(f"[ERRO] {error_msg}: {str(e)}")
            update_job_status(job_id, "failed", error_msg,
                              error_details=error_details)
            return
        except TimeoutError as e:
            error_msg = "Timeout ao iniciar o navegador"
            error_details = f"O navegador demorou muito para iniciar: {str(e)}. " \
                            f"Verifique a carga do sistema e se o AdsPower está respondendo normalmente."
            logger.error(f"[ERRO] {error_msg}: {str(e)}")
            update_job_status(job_id, "failed", error_msg,
                              error_details=error_details)
            return
        except Exception as e:
            error_msg = "Erro ao iniciar o navegador"
            error_details = f"Falha ao iniciar o navegador para o perfil {user_id}: {str(e)}. " \
                            f"Tipo de erro: {type(e).__name__}"
            logger.error(f"[ERRO] {error_msg}: {str(e)}")
            update_job_status(job_id, "failed", error_msg,
                              error_details=error_details)
            return

        try:
            # Fechar o browser ao finalizar (independente do resultado)
            browser_manager.close_browser(user_id)
        except Exception as e:
            logger.warning(
                f"[AVISO] Falha ao fechar navegador para perfil {user_id}: {str(e)}")

        if success and account_data:
            # Adicionar timestamp de criação
            account_data["creation_time"] = time.time()

            # Salvar os dados da conta criada
            try:
                accounts_file = os.path.join(
                    SMS_DATA_DIR, "gmail_accounts.json")
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

            # Atualizar status para concluído
            update_job_status(
                job_id,
                "completed",
                f"Conta Gmail criada com sucesso: {account_data['email']}",
                account_data
            )
            logger.info(
                f"[OK] Conta criada com sucesso: {account_data['email']}")
        else:
            # Atualizar status para falha
            error_message = "Falha ao criar conta Gmail. Verifique os logs para mais detalhes."
            error_details = "O processo de criação da conta Gmail falhou sem retornar uma mensagem de erro específica. " \
                "Isso pode ocorrer devido a problemas com o navegador, verificação do número de telefone, ou bloqueio pelo Google."
            update_job_status(job_id, "failed", error_message,
                              error_details=error_details)
            logger.error(f"[ERRO] {error_message}")

    except Exception as e:
        # Capturar detalhes do erro para logging e resposta
        import traceback
        error_traceback = traceback.format_exc()
        error_type = type(e).__name__
        error_message = f"Erro durante processo de criação: {str(e)}"

        # Criar detalhes de erro formatados
        error_details = {
            "error_type": error_type,
            "error_message": str(e),
            "traceback": error_traceback.split("\n")
        }

        # Converter para string para ficar consistente com outros erros
        error_details_str = f"Tipo de erro: {error_type}\nMensagem: {str(e)}\nDetalhes técnicos:\n{error_traceback}"

        logger.error(f"[ERRO] {error_message}\n{error_traceback}")
        update_job_status(job_id, "failed", error_message,
                          error_details=error_details_str)


def update_job_status(job_id, status, message=None, result=None, error_details=None, batch_id=None):
    """
    Atualiza o status de um job e salva no arquivo.

    Args:
        job_id (str): ID do job
        status (str): Status do job (pending, processing, completed, error)
        message (str, optional): Mensagem sobre o status. Defaults to None.
        result (dict, optional): Resultado do job quando completado. Defaults to None.
        error_details (dict, optional): Detalhes do erro quando falha. Defaults to None.
        batch_id (str, optional): ID do batch, se aplicável. Defaults to None.

    Returns:
        dict: Dados atualizados do job
    """
    # Garantir que o ID do job não tenha espaços extras
    original_job_id = job_id
    job_id = job_id.strip() if job_id else job_id

    if original_job_id != job_id:
        logger.info(
            f"Job ID tinha espaços extras e foi normalizado: '{original_job_id}' -> '{job_id}'")

    # Normalizar batch_id se fornecido
    if batch_id:
        original_batch_id = batch_id
        batch_id = batch_id.strip() if batch_id else batch_id
        if original_batch_id != batch_id:
            logger.info(
                f"Batch ID tinha espaços extras e foi normalizado: '{original_batch_id}' -> '{batch_id}'")

    # Criar o diretório de jobs se não existir
    if not os.path.exists(JOBS_DIR):
        os.makedirs(JOBS_DIR, exist_ok=True)
        logger.info(f"Diretório de jobs criado: {JOBS_DIR}")

    # Determinar o caminho do arquivo
    if batch_id:
        batch_dir = os.path.join(JOBS_DIR, batch_id)
        if not os.path.exists(batch_dir):
            os.makedirs(batch_dir, exist_ok=True)
            logger.info(f"Diretório de batch criado: {batch_dir}")

        job_file = os.path.join(batch_dir, f"{job_id}.json")
    else:
        job_file = os.path.join(JOBS_DIR, f"{job_id}.json")

    # Carregar dados existentes ou criar novos
    job_data = {}
    try:
        if os.path.exists(job_file):
            with open(job_file, "r") as f:
                job_data = json.load(f)
    except Exception as e:
        logger.error(f"Erro ao carregar dados do job {job_id}: {str(e)}")

    # Verificar se existe um arquivo alternativo com o ID original (caso tenha sido normalizado)
    if original_job_id != job_id and not os.path.exists(job_file):
        original_job_file = os.path.join(JOBS_DIR, f"{original_job_id}.json")
        if os.path.exists(original_job_file):
            try:
                with open(original_job_file, "r") as f:
                    job_data = json.load(f)
                logger.info(
                    f"Dados carregados do arquivo original: {original_job_file}")
                # Remover o arquivo com ID não normalizado
                os.remove(original_job_file)
                logger.info(
                    f"Arquivo com ID não normalizado removido: {original_job_file}")
            except Exception as e:
                logger.error(
                    f"Erro ao migrar do ID original para normalizado: {str(e)}")

    # Atualizar dados
    job_data.update({
        "job_id": job_id,
        "status": status,
        "updated_at": time.time(),
    })

    if batch_id:
        job_data["batch_id"] = batch_id

    if message:
        job_data["message"] = message

    if status == "completed" and result:
        job_data["result"] = result

    if status == "error" and error_details:
        job_data["error"] = error_details

    # Salvar dados atualizados
    try:
        with open(job_file, "w") as f:
            json.dump(job_data, f, indent=2)
        logger.info(f"Status do job {job_id} atualizado para: {status}")
    except Exception as e:
        logger.error(f"Erro ao salvar status do job {job_id}: {str(e)}")

    return job_data


@app.route('/gmail-job-status/<job_id>', methods=['GET'])
def gmail_job_status(job_id):
    """
    Endpoint para verificar o status de um job de criação de Gmail.

    Retorna o status atual e, se concluído, os dados da conta criada.
    """
    # Remover espaços extras no início e fim do ID do job
    original_job_id = job_id
    job_id = job_id.strip()
    if original_job_id != job_id:
        logger.info(
            f"[INFO] ID do job continha espaços extras. Original: '{original_job_id}', Corrigido: '{job_id}'")

    # Verificar se o diretório de jobs existe
    if not os.path.exists(JOBS_DIR):
        os.makedirs(JOBS_DIR, exist_ok=True)
        logger.warning(
            f"[AVISO] Diretório de jobs não existia e foi criado: {JOBS_DIR}")
        # Retornar uma resposta padronizada para job não encontrado
        return jsonify({
            "success": False,
            "error": "Diretório de jobs não existia e foi criado agora",
            "job_id": job_id,
            "status": "pending",
            "message": "Aguarde alguns momentos e tente novamente"
        })

    job_file = os.path.join(JOBS_DIR, f"{job_id}.json")

    # Se o arquivo exato não existir, tentar encontrar um arquivo similar (sem espaços ou com variações de espaço)
    if not os.path.exists(job_file):
        # Verificar se existem outros arquivos que possam corresponder ao mesmo job (com/sem espaços)
        try:
            all_job_files = os.listdir(JOBS_DIR)
            # Procurar por arquivos que sem espaços correspondam ao job_id
            possible_matches = [f for f in all_job_files if f.replace(
                " ", "") == f"{job_id}.json".replace(" ", "")]

            if possible_matches:
                logger.info(
                    f"[INFO] Encontrado arquivo de job alternativo: {possible_matches[0]}")
                # Usar o primeiro arquivo correspondente encontrado
                job_file = os.path.join(JOBS_DIR, possible_matches[0])
                # Atualizar o job_id para corresponder ao arquivo encontrado
                job_id = possible_matches[0].replace(".json", "")
        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao procurar arquivos alternativos: {str(e)}")

    if not os.path.exists(job_file):
        # Log detalhado sobre o arquivo não encontrado
        logger.warning(
            f"[AVISO] Job não encontrado: {job_id}. Arquivo esperado: {job_file}")

        # Listar arquivos no diretório para diagnóstico
        try:
            existing_files = os.listdir(JOBS_DIR)
            logger.info(
                f"[INFO] Arquivos existentes no diretório {JOBS_DIR}: {', '.join(existing_files[:10])}{'...' if len(existing_files) > 10 else ''}")
        except Exception as e:
            logger.error(
                f"[ERRO] Não foi possível listar arquivos em {JOBS_DIR}: {str(e)}")

        # Para n8n, retornar um objeto JSON estruturado com informações úteis
        response = {
            "success": False,
            "error": "Job não encontrado",
            "error_code": "JOB_NOT_FOUND",
            "job_id": job_id,
            "details": {
                "searched_path": job_file,
                "jobs_dir": JOBS_DIR,
                "timestamp": time.time()
            },
            "status": "unknown",
            "message": "O job solicitado não foi encontrado. Verifique se o ID está correto."
        }
        return jsonify(response)

    try:
        with open(job_file, "r") as f:
            job_data = json.load(f)

        # Adicionar campos de controle para facilitar o uso no n8n
        job_data["success"] = job_data.get("status") == "completed"

        # Garantir que o job tenha um campo de status
        if "status" not in job_data:
            job_data["status"] = "pending"
            job_data["message"] = "Status não encontrado, assumindo pendente"

        # Adicionar o job_id ao resultado para facilitar o uso no n8n
        if "job_id" not in job_data:
            job_data["job_id"] = job_id

        logger.info(
            f"[OK] Status do job {job_id} retornado: {job_data.get('status')}")
        return jsonify(job_data)
    except Exception as e:
        error_message = f"Erro ao ler status do job {job_id}: {str(e)}"
        logger.error(f"[ERRO] {error_message}")

        # Tentar verificar se o arquivo existe mas está corrompido
        try:
            file_size = os.path.getsize(
                job_file) if os.path.exists(job_file) else 0
            file_status = "existe" if os.path.exists(
                job_file) else "não existe"
            error_details = f"Arquivo {file_status}, tamanho: {file_size} bytes"
        except Exception as file_error:
            error_details = f"Erro ao verificar arquivo: {str(file_error)}"

        return jsonify({
            "success": False,
            "error": error_message,
            "error_code": "FILE_READ_ERROR",
            "job_id": job_id,
            "status": "error",
            "details": error_details
        })


@app.route('/gmail-accounts', methods=['GET'])
def list_gmail_accounts():
    """
    Endpoint para listar todas as contas Gmail criadas.

    Parâmetros de query aceitos:
    - limit: número máximo de contas a retornar (padrão: 100)
    - newest_first: se true, retorna as contas mais recentes primeiro (padrão: true)
    """
    try:
        # Parâmetros da query
        limit = min(int(request.args.get('limit', 100)),
                    1000)  # Máximo de 1000 contas
        newest_first = request.args.get(
            'newest_first', 'true').lower() == 'true'

        # Verificar se o arquivo de contas existe
        accounts_file = os.path.join(SMS_DATA_DIR, "gmail_accounts.json")
        if not os.path.exists(accounts_file):
            return jsonify({
                "success": True,
                "count": 0,
                "accounts": []
            })

        # Carregar as contas
        with open(accounts_file, "r") as file:
            try:
                accounts = json.load(file)
            except json.JSONDecodeError:
                accounts = []

        # Ordenar por data de criação (mais recente primeiro, se solicitado)
        if newest_first:
            accounts.sort(key=lambda x: x.get(
                "creation_time", 0), reverse=True)
        else:
            accounts.sort(key=lambda x: x.get("creation_time", 0))

        # Limitar o número de contas
        accounts = accounts[:limit]

        return jsonify({
            "success": True,
            "count": len(accounts),
            "accounts": accounts
        })

    except Exception as e:
        logger.error(f"[ERRO] Erro ao listar contas Gmail: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        })


# --- Rotas para integração com n8n ---
@app.route('/n8n/batch-gmail-creation', methods=['POST'])
def n8n_batch_gmail_creation():
    """
    Endpoint otimizado para n8n criar múltiplas contas Gmail em lote.

    Inicia a criação de contas Gmail para múltiplos perfis e retorna imediatamente
    com um batch_id que pode ser usado para verificar o status de todo o lote.

    Corpo da requisição (JSON):
    {
        "profiles": [
            {
                "user_id": "profile_id1",
                "phone_params": {},  # opcional
                "headless": true     # opcional
            },
            {
                "user_id": "profile_id2"
            }
        ],
        "common_params": {           # parâmetros aplicados a todos os perfis (opcional)
            "headless": true,
            "max_wait_time": 60
        },
        "max_concurrent": 2,         # número máximo de criações simultâneas (opcional, padrão: 2)
        "webhook_callback": "https://n8n.example.com/webhook/callback"  # URL para callback (opcional)
    }

    Resposta:
    {
        "success": true,
        "batch_id": "batch-123456",
        "total_jobs": 2,
        "jobs": [
            {
                "job_id": "job-1",
                "user_id": "profile_id1",
                "status": "pending"
            },
            {
                "job_id": "job-2",
                "user_id": "profile_id2",
                "status": "pending"
            }
        ],
        "status_url": "/n8n/batch-status/batch-123456"
    }
    """
    try:
        data = request.json or {}

        # Validar dados de entrada
        profiles = data.get('profiles', [])
        if not profiles:
            return jsonify({
                "success": False,
                "error": "Nenhum perfil fornecido para criação em lote",
                "error_code": "NO_PROFILES"
            })

        # Parâmetros comuns a todos os perfis
        common_params = data.get('common_params', {})

        # Limite de processamento simultâneo
        # Máximo 5 simultâneos
        max_concurrent = min(int(data.get('max_concurrent', 2)), 5)

        # URL de callback (opcional)
        webhook_callback = data.get('webhook_callback')

        # Gerar ID para o lote
        batch_id = f"batch-{str(uuid.uuid4())}"

        # Diretório para armazenar informações do lote
        batch_dir = os.path.join(JOBS_DIR, batch_id)
        os.makedirs(batch_dir, exist_ok=True)

        # Informações do lote
        batch_info = {
            "batch_id": batch_id,
            "created_at": time.time(),
            "total_jobs": len(profiles),
            "completed_jobs": 0,
            "successful_jobs": 0,
            "failed_jobs": 0,
            "pending_jobs": len(profiles),
            "status": "pending",
            "max_concurrent": max_concurrent,
            "webhook_callback": webhook_callback,
            "jobs": []
        }

        # Criar jobs para cada perfil
        jobs = []
        for profile in profiles:
            # Validar perfil
            user_id = profile.get('user_id')
            if not user_id:
                continue

            # Mesclar parâmetros comuns com específicos
            job_params = common_params.copy()

            # Parâmetros específicos do perfil sobrescrevem os comuns
            for key, value in profile.items():
                if key != 'user_id':
                    job_params[key] = value

            # Gerar job_id
            job_id = str(uuid.uuid4())

            # Criar job
            job_data = {
                "job_id": job_id,
                "user_id": user_id,
                "status": "pending",
                "created_at": time.time(),
                "params": job_params,
                "batch_id": batch_id,
                "message": "Job aguardando processamento"
            }

            # Salvar dados do job
            job_file = os.path.join(JOBS_DIR, f"{job_id}.json")
            with open(job_file, "w") as f:
                json.dump(job_data, f, indent=4)

            jobs.append(job_data)
            batch_info["jobs"].append({
                "job_id": job_id,
                "user_id": user_id,
                "status": "pending"
            })

        # Salvar informações do lote
        batch_file = os.path.join(batch_dir, "info.json")
        with open(batch_file, "w") as f:
            json.dump(batch_info, f, indent=4)

        # Iniciar o processador de lote em uma thread separada
        Thread(target=process_batch, args=(
            batch_id, jobs, max_concurrent)).start()

        # Retornar informações do lote
        return jsonify({
            "success": True,
            "batch_id": batch_id,
            "total_jobs": len(jobs),
            "jobs": batch_info["jobs"],
            "status_url": f"/n8n/batch-status/{batch_id}"
        })

    except Exception as e:
        logger.error(f"[ERRO] Erro ao iniciar criação em lote: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "error_code": "BATCH_CREATION_ERROR"
        })


def process_batch(batch_id, jobs, max_concurrent):
    """
    Processa um lote de jobs de criação de Gmail.

    Esta função executa até max_concurrent jobs simultaneamente
    e atualiza o status do lote conforme os jobs são concluídos.
    """
    try:
        logger.info(
            f"[BATCH] Iniciando processamento do lote {batch_id} com {len(jobs)} jobs")

        # Diretório para armazenar informações do lote
        batch_dir = os.path.join(JOBS_DIR, batch_id)
        batch_file = os.path.join(batch_dir, "info.json")

        # Carregar informações do lote
        with open(batch_file, "r") as f:
            batch_info = json.load(f)

        # Atualizar status do lote
        batch_info["status"] = "processing"
        with open(batch_file, "w") as f:
            json.dump(batch_info, f, indent=4)

        # Dividir os jobs em grupos de max_concurrent
        job_groups = [jobs[i:i + max_concurrent]
                      for i in range(0, len(jobs), max_concurrent)]

        # Processar cada grupo de jobs
        for group_index, job_group in enumerate(job_groups):
            active_threads = []

            logger.info(
                f"[BATCH] Processando grupo {group_index+1}/{len(job_groups)} do lote {batch_id}")

            # Iniciar threads para cada job no grupo
            for job in job_group:
                job_id = job["job_id"]
                user_id = job["user_id"]
                params = job["params"]

                # Atualizar status do job
                update_job_status(job_id, "queued",
                                  "Job na fila para processamento")

                # Iniciar thread para o job
                thread = Thread(target=process_gmail_creation,
                                args=(job_id, user_id, params))
                thread.start()
                active_threads.append((thread, job_id))

                # Pequeno delay para evitar sobrecarga
                time.sleep(1)

            # Aguardar todas as threads do grupo terminarem
            for thread, job_id in active_threads:
                thread.join()

                # Atualizar contadores do lote
                with open(batch_file, "r") as f:
                    batch_info = json.load(f)

                # Obter status do job
                job_file = os.path.join(JOBS_DIR, f"{job_id}.json")
                with open(job_file, "r") as f:
                    job_data = json.load(f)

                # Atualizar contadores
                batch_info["completed_jobs"] += 1
                batch_info["pending_jobs"] -= 1

                if job_data.get("status") == "completed":
                    batch_info["successful_jobs"] += 1
                elif job_data.get("status") == "failed":
                    batch_info["failed_jobs"] += 1

                # Atualizar status de job na lista
                for job in batch_info["jobs"]:
                    if job["job_id"] == job_id:
                        job["status"] = job_data.get("status")
                        break

                # Salvar informações atualizadas
                with open(batch_file, "w") as f:
                    json.dump(batch_info, f, indent=4)

        # Todos os jobs foram processados
        with open(batch_file, "r") as f:
            batch_info = json.load(f)

        batch_info["status"] = "completed"
        batch_info["completed_at"] = time.time()

        with open(batch_file, "w") as f:
            json.dump(batch_info, f, indent=4)

        logger.info(
            f"[BATCH] Lote {batch_id} concluído: {batch_info['successful_jobs']} sucesso, {batch_info['failed_jobs']} falhas")

        # Realizar callback se configurado
        if batch_info.get("webhook_callback"):
            try:
                # Enviar callback com informações do lote
                requests.post(batch_info["webhook_callback"], json={
                    "batch_id": batch_id,
                    "status": "completed",
                    "total_jobs": batch_info["total_jobs"],
                    "successful_jobs": batch_info["successful_jobs"],
                    "failed_jobs": batch_info["failed_jobs"],
                    "jobs": batch_info["jobs"]
                }, timeout=10)
                logger.info(
                    f"[BATCH] Callback enviado para {batch_info['webhook_callback']}")
            except Exception as e:
                logger.error(f"[ERRO] Falha ao enviar callback: {str(e)}")

    except Exception as e:
        logger.error(
            f"[ERRO] Erro no processamento do lote {batch_id}: {str(e)}")

        try:
            # Tentar atualizar o status do lote para indicar erro
            batch_file = os.path.join(batch_dir, "info.json")
            if os.path.exists(batch_file):
                with open(batch_file, "r") as f:
                    batch_info = json.load(f)

                batch_info["status"] = "error"
                batch_info["error"] = str(e)

                with open(batch_file, "w") as f:
                    json.dump(batch_info, f, indent=4)
        except:
            pass


@app.route('/n8n/batch-status/<batch_id>', methods=['GET'])
def n8n_batch_status(batch_id):
    """
    Endpoint para verificar o status de um lote de criação de contas Gmail.

    Parâmetros de query:
    - include_jobs: se true, inclui detalhes de cada job (padrão: false)
    - include_accounts: se true, inclui detalhes das contas criadas (padrão: false)
    """
    try:
        # Parâmetros da query
        include_jobs = request.args.get(
            'include_jobs', 'false').lower() == 'true'
        include_accounts = request.args.get(
            'include_accounts', 'false').lower() == 'true'

        # Verificar se o lote existe
        batch_dir = os.path.join(JOBS_DIR, batch_id)
        batch_file = os.path.join(batch_dir, "info.json")

        if not os.path.exists(batch_file):
            return jsonify({
                "success": False,
                "error": "Lote não encontrado",
                "batch_id": batch_id
            })

        # Carregar informações do lote
        with open(batch_file, "r") as f:
            batch_info = json.load(f)

        # Adicionar flag de sucesso baseado no status
        batch_info["success"] = batch_info.get(
            "status") in ["completed", "processing"]

        # Se solicitado, incluir detalhes completos dos jobs
        if include_jobs:
            detailed_jobs = []

            for job in batch_info.get("jobs", []):
                job_id = job.get("job_id")
                job_file = os.path.join(JOBS_DIR, f"{job_id}.json")

                if os.path.exists(job_file):
                    with open(job_file, "r") as f:
                        job_data = json.load(f)

                    # Limpar dados sensíveis e informações redundantes
                    if "params" in job_data:
                        job_data.pop("params", None)

                    detailed_jobs.append(job_data)
                else:
                    # Job não encontrado
                    detailed_jobs.append({
                        "job_id": job_id,
                        "status": "unknown",
                        "message": "Dados do job não encontrados"
                    })

            batch_info["detailed_jobs"] = detailed_jobs

        # Se solicitado e batch concluído, incluir detalhes das contas criadas
        if include_accounts and batch_info.get("status") == "completed":
            successful_accounts = []

            for job in batch_info.get("jobs", []):
                job_id = job.get("job_id")
                job_file = os.path.join(JOBS_DIR, f"{job_id}.json")

                if os.path.exists(job_file):
                    with open(job_file, "r") as f:
                        job_data = json.load(f)

                    if job_data.get("status") == "completed" and "result" in job_data:
                        account = job_data["result"]
                        account["job_id"] = job_id
                        account["user_id"] = job_data.get("user_id")
                        successful_accounts.append(account)

            batch_info["accounts"] = successful_accounts

        return jsonify(batch_info)

    except Exception as e:
        logger.error(
            f"[ERRO] Erro ao verificar status do lote {batch_id}: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "batch_id": batch_id
        })


@app.route('/n8n/batch-cancel/<batch_id>', methods=['POST'])
def n8n_batch_cancel(batch_id):
    """
    Endpoint para cancelar um lote de criação de contas Gmail.

    Cancela todos os jobs pendentes e retorna o status atualizado do lote.
    Os jobs em execução continuarão até a conclusão.
    """
    try:
        # Verificar se o lote existe
        batch_dir = os.path.join(JOBS_DIR, batch_id)
        batch_file = os.path.join(batch_dir, "info.json")

        if not os.path.exists(batch_file):
            return jsonify({
                "success": False,
                "error": "Lote não encontrado",
                "batch_id": batch_id
            })

        # Carregar informações do lote
        with open(batch_file, "r") as f:
            batch_info = json.load(f)

        # Verificar se o lote já foi concluído
        if batch_info.get("status") in ["completed", "cancelled", "error"]:
            return jsonify({
                "success": False,
                "error": f"Lote já está no estado: {batch_info.get('status')}",
                "batch_id": batch_id,
                "status": batch_info.get("status")
            })

        # Cancelar todos os jobs pendentes
        cancelled_count = 0
        for job in batch_info.get("jobs", []):
            job_id = job.get("job_id")
            job_file = os.path.join(JOBS_DIR, f"{job_id}.json")

            if os.path.exists(job_file):
                with open(job_file, "r") as f:
                    job_data = json.load(f)

                # Só pode cancelar jobs pendentes ou na fila
                if job_data.get("status") in ["pending", "queued"]:
                    job_data["status"] = "cancelled"
                    job_data["message"] = "Job cancelado pelo usuário"

                    with open(job_file, "w") as f:
                        json.dump(job_data, f, indent=4)

                    cancelled_count += 1

                    # Atualizar status na lista de jobs
                    job["status"] = "cancelled"

        # Atualizar contadores do lote
        batch_info["pending_jobs"] -= cancelled_count
        batch_info["cancelled_jobs"] = cancelled_count

        # Se não há jobs pendentes ou em processamento, marcar como cancelado
        active_jobs = sum(1 for job in batch_info.get("jobs", [])
                          if job.get("status") in ["pending", "queued", "processing"])

        if active_jobs == 0:
            batch_info["status"] = "cancelled"
            batch_info["completed_at"] = time.time()
        else:
            batch_info["status"] = "cancelling"

        # Salvar informações atualizadas
        with open(batch_file, "w") as f:
            json.dump(batch_info, f, indent=4)

        return jsonify({
            "success": True,
            "message": f"Cancelados {cancelled_count} jobs pendentes",
            "batch_id": batch_id,
            "status": batch_info["status"],
            "cancelled_jobs": cancelled_count,
            "remaining_active_jobs": active_jobs
        })

    except Exception as e:
        logger.error(f"[ERRO] Erro ao cancelar lote {batch_id}: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "batch_id": batch_id
        })


@app.route('/n8n-job-status/<job_id>', methods=['GET'])
@app.route('/n8n-job-status/<job_id>/<batch_id>', methods=['GET'])
def n8n_job_status(job_id, batch_id=None):
    """
    Endpoint para verificar o status de um job do N8N.
    Retorna o status atual do job solicitado.

    Args:
        job_id (str): ID do job a ser verificado
        batch_id (str, optional): ID do lote, se aplicável. Defaults to None.
    """
    try:
        # Remover espaços extras no início e fim
        original_job_id = job_id
        job_id = job_id.strip() if job_id else job_id

        if original_job_id != job_id:
            logger.info(
                f"[N8N] Job ID tinha espaços extras e foi normalizado: '{original_job_id}' -> '{job_id}'")

        # Normalizar batch_id se fornecido
        original_batch_id = None
        if batch_id:
            original_batch_id = batch_id
            batch_id = batch_id.strip() if batch_id else batch_id
            if original_batch_id != batch_id:
                logger.info(
                    f"[N8N] Batch ID tinha espaços extras e foi normalizado: '{original_batch_id}' -> '{batch_id}'")

        # Verificar se o diretório de jobs existe
        if not os.path.exists(JOBS_DIR):
            os.makedirs(JOBS_DIR, exist_ok=True)
            logger.warning(
                f"[N8N] Diretório de jobs não existia e foi criado: {JOBS_DIR}")

        # Determinar o caminho do arquivo
        if batch_id:
            batch_dir = os.path.join(JOBS_DIR, batch_id)
            job_file = os.path.join(batch_dir, f"{job_id}.json")
        else:
            job_file = os.path.join(JOBS_DIR, f"{job_id}.json")

        # Verificar se o arquivo existe
        if not os.path.exists(job_file):
            # Tenta encontrar o arquivo com outros formatos de nomes devido aos espaços
            possible_files = []

            # Listar todos os arquivos no diretório
            if batch_id:
                if os.path.exists(os.path.join(JOBS_DIR, batch_id)):
                    dir_files = os.listdir(os.path.join(JOBS_DIR, batch_id))
                    dir_files = [os.path.join(JOBS_DIR, batch_id, f)
                                 for f in dir_files]
                else:
                    dir_files = []
            else:
                dir_files = [os.path.join(JOBS_DIR, f) for f in os.listdir(
                    JOBS_DIR) if os.path.isfile(os.path.join(JOBS_DIR, f))]

            # Normalizar os nomes dos arquivos (remover espaços e extensão) para comparação
            normalized_job_id = job_id.replace(' ', '')
            for file_path in dir_files:
                file_name = os.path.basename(file_path)
                file_name_no_ext = os.path.splitext(file_name)[0]
                normalized_file_name = file_name_no_ext.replace(' ', '')

                if normalized_file_name == normalized_job_id:
                    possible_files.append(file_path)

            if possible_files:
                # Usa o primeiro arquivo encontrado
                job_file = possible_files[0]
                logger.info(
                    f"[N8N] Encontrado arquivo alternativo para job {job_id}: {job_file}")
            else:
                # Criar uma resposta temporária
                logger.warning(
                    f"[N8N] Job {job_id} não encontrado no caminho {job_file}. Criando resposta temporária.")

                # Listar os arquivos disponíveis para diagnóstico
                available_files = os.listdir(
                    JOBS_DIR) if os.path.exists(JOBS_DIR) else []
                logger.info(
                    f"[N8N] Arquivos disponíveis no diretório de jobs: {available_files}")

                # Retornar resposta temporária
                return jsonify({
                    "job_id": job_id,
                    "status": "pending",
                    "message": "Job em processamento ou ainda não iniciado",
                    "batch_id": batch_id
                })

        # Ler os dados do arquivo
        with open(job_file, "r") as f:
            job_data = json.load(f)

        # Se o arquivo foi encontrado com ID não normalizado, atualizar para usar o ID normalizado
        if job_data.get("job_id") != job_id and job_id:
            # Cria uma cópia com o ID normalizado
            normalized_job_file = os.path.join(JOBS_DIR, f"{job_id}.json")
            job_data["job_id"] = job_id
            with open(normalized_job_file, "w") as f:
                json.dump(job_data, f, indent=2)
            logger.info(
                f"[N8N] Criado arquivo com ID normalizado: {normalized_job_file}")

        # Adicionar compatibilidade com processos existentes
        response_data = {
            "job_id": job_id,
            "status": job_data.get("status", "pending"),
            "message": job_data.get("message", ""),
        }

        # Adicionar campos opcionais se existirem
        if "result" in job_data:
            response_data["result"] = job_data["result"]

        if "error" in job_data:
            response_data["error"] = job_data["error"]

        if batch_id:
            response_data["batch_id"] = batch_id

        return jsonify(response_data)

    except Exception as e:
        logger.error(
            f"[N8N] Erro ao verificar status do job {job_id}: {str(e)}")
        return jsonify({
            "job_id": job_id,
            "status": "error",
            "message": f"Erro ao verificar status: {str(e)}",
            "batch_id": batch_id if batch_id else None
        })

# Função para documentação dos endpoints do n8n


@app.route('/n8n/help', methods=['GET'])
def n8n_help():
    """
    Endpoint de ajuda que lista todos os endpoints disponíveis para integração com n8n.
    """
    return jsonify({
        "success": True,
        "description": "API para criação de contas Gmail com AdsPower",
        "version": "1.0.0",
        "endpoints": [
            {
                "path": "/n8n/create-gmail/<user_id>",
                "method": "POST",
                "description": "Cria uma única conta Gmail de forma assíncrona",
                "documentation": "Endpoint recomendado para n8n - inicia a criação e retorna um job_id para consultar o status depois"
            },
            {
                "path": "/n8n/batch-gmail-creation",
                "method": "POST",
                "description": "Cria múltiplas contas Gmail em lote",
                "documentation": "Envia múltiplos perfis para criação de contas em lote, processados em paralelo"
            },
            {
                "path": "/n8n/batch-status/<batch_id>",
                "method": "GET",
                "description": "Verifica o status de um lote",
                "parameters": "include_jobs=true/false, include_accounts=true/false"
            },
            {
                "path": "/n8n/batch-cancel/<batch_id>",
                "method": "POST",
                "description": "Cancela um lote em processamento"
            },
            {
                "path": "/n8n/job-status",
                "method": "GET",
                "description": "Endpoint unificado para verificar o status de jobs ou lotes",
                "parameters": "job_id=XXX ou batch_id=XXX"
            },
            {
                "path": "/gmail-job-status/<job_id>",
                "method": "GET",
                "description": "Verifica o status de um job específico"
            },
            {
                "path": "/gmail-accounts",
                "method": "GET",
                "description": "Lista todas as contas Gmail criadas",
                "parameters": "limit=100, newest_first=true/false"
            },
            {
                "path": "/create-gmail-async/<user_id>",
                "method": "POST",
                "description": "Endpoint de compatibilidade - redireciona para /n8n/create-gmail",
                "documentation": "Mantido para compatibilidade com sistemas existentes"
            },
            {
                "path": "/create-gmail/<user_id>",
                "method": "POST",
                "description": "Endpoint de compatibilidade - usa /n8n/create-gmail e aguarda resultado",
                "documentation": "Mantido para compatibilidade com sistemas existentes"
            }
        ],
        "exemplos_n8n": {
            "criacao_individual": [
                "1. Enviar requisição para /n8n/create-gmail/<user_id>",
                "2. Receber job_id na resposta",
                "3. Configurar loop que consulta /n8n/job-status?job_id=XXX periodicamente",
                "4. Aguardar até que status seja 'completed'",
                "5. Obter os dados da conta criada no campo 'result'"
            ],
            "criacao_em_lote": [
                "1. Enviar lote de perfis para /n8n/batch-gmail-creation",
                "2. Receber batch_id na resposta",
                "3. Configurar loop que consulta /n8n/batch-status/<batch_id> periodicamente",
                "4. Aguardar até que status seja 'completed'",
                "5. Consultar /n8n/batch-status/<batch_id>?include_accounts=true para obter as contas"
            ],
            "com_webhook": [
                "1. Criar um endpoint webhook no n8n",
                "2. Enviar requisição para /n8n/create-gmail/<user_id> com webhook_callback",
                "3. O sistema notificará automaticamente o n8n quando a conta for criada"
            ]
        }
    })


@app.route('/n8n/create-gmail/<user_id>', methods=['POST'])
def n8n_create_gmail(user_id):
    """
    Endpoint assíncrono específico para n8n criar uma única conta Gmail.

    Inicia a criação de uma conta Gmail e retorna imediatamente com um job_id,
    evitando o timeout do Cloudflare. Projetado para integrar facilmente com 
    fluxos de trabalho do n8n.

    Corpo da requisição (JSON):
    {
        "phone_params": {},     # Parâmetros do telefone (opcional)
        "headless": true,       # Executar em modo headless (opcional)
        "max_wait_time": 60,    # Tempo máximo de espera (opcional)
        "webhook_callback": ""  # URL para callback quando concluído (opcional)
    }

    Resposta:
    {
        "success": true,
        "job_id": "123e4567-e89b-12d3-a456-426614174000",
        "user_id": "profile123",
        "status": "pending",
        "status_url": "/n8n/job-status?job_id=123e4567-e89b-12d3-a456-426614174000"
    }
    """
    try:
        # Verificar se o ID do perfil foi fornecido
        if not user_id:
            return jsonify({
                "success": False,
                "error": "ID do perfil não fornecido",
                "error_code": "MISSING_USER_ID"
            })

        # Verificar se o diretório de jobs existe
        if not os.path.exists(JOBS_DIR):
            os.makedirs(JOBS_DIR, exist_ok=True)
            logger.info(f"[N8N] Diretório de jobs criado: {JOBS_DIR}")

        # Recuperar parâmetros do corpo da requisição
        data = request.json or {}

        # Verificar se há URL de callback
        webhook_callback = data.pop('webhook_callback', None)

        # Gerar um job_id único
        job_id = str(uuid.uuid4())
        logger.info(
            f"[N8N] Iniciando criação de job para {user_id} com ID {job_id}")

        # Criar dados do job
        job_data = {
            "job_id": job_id,
            "status": "pending",
            "started_at": time.time(),
            "user_id": user_id,
            "params": data,
            "webhook_callback": webhook_callback,
            "message": "Processo iniciado e executando em background",
            "n8n": True  # Flag para identificar que foi iniciado pelo n8n
        }

        # Salvar em arquivo para persistência
        job_file = os.path.join(JOBS_DIR, f"{job_id}.json")

        # Garantir que o arquivo seja criado corretamente
        try:
            with open(job_file, "w") as f:
                json.dump(job_data, f, indent=4)

            # Verificar se o arquivo foi realmente criado
            if os.path.exists(job_file):
                logger.info(
                    f"[N8N] Arquivo de job {job_id} criado com sucesso em {job_file}")
            else:
                logger.error(
                    f"[N8N] Falha ao criar arquivo de job {job_id}. Arquivo não existe após criação.")
                return jsonify({
                    "success": False,
                    "error": "Falha ao criar arquivo de job",
                    "error_code": "FILE_CREATE_ERROR",
                    "job_id": job_id
                })
        except Exception as file_error:
            logger.error(
                f"[N8N] Erro ao salvar arquivo de job {job_id}: {str(file_error)}")
            return jsonify({
                "success": False,
                "error": f"Erro ao salvar arquivo de job: {str(file_error)}",
                "error_code": "FILE_WRITE_ERROR",
                "job_id": job_id
            })

        # Iniciar thread para processar em background
        try:
            thread = Thread(target=process_gmail_creation_with_callback,
                            args=(job_id, user_id, data, webhook_callback))
            # Para garantir que a thread termine quando o processo principal terminar
            thread.daemon = True
            thread.start()
            logger.info(
                f"[N8N] Thread iniciada para processamento do job {job_id}")
        except Exception as thread_error:
            logger.error(
                f"[N8N] Erro ao iniciar thread para job {job_id}: {str(thread_error)}")
            # Atualizar status do job para refletir o erro
            update_job_status(
                job_id, "failed", f"Erro ao iniciar processamento: {str(thread_error)}")
            return jsonify({
                "success": False,
                "error": f"Erro ao iniciar processamento: {str(thread_error)}",
                "error_code": "THREAD_START_ERROR",
                "job_id": job_id
            })

        logger.info(
            f"[N8N] Job {job_id} iniciado para criação de Gmail no perfil {user_id}")

        # Retornar imediatamente com o job_id
        return jsonify({
            "success": True,
            "message": "Processo de criação iniciado em background",
            "job_id": job_id,
            "user_id": user_id,
            "status": "pending",
            "status_url": f"/n8n/job-status?job_id={job_id}"
        })

    except Exception as e:
        logger.error(f"[ERRO] Erro ao iniciar job n8n: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "error_code": "N8N_START_ERROR"
        })

# Adicionar rotas de compatibilidade para redirecionamento para os endpoints do n8n


@app.route('/create-gmail-async/<user_id>', methods=['POST'])
def create_gmail_async(user_id):
    """
    Endpoint de compatibilidade - redireciona para o endpoint do n8n
    """
    logger.info(
        f"[COMPATIBILIDADE] Redirecionando solicitação para endpoint n8n")
    return n8n_create_gmail(user_id)


@app.route('/create-gmail/<user_id>', methods=['POST'])
def create_gmail_account(user_id):
    """
    Endpoint de compatibilidade - redireciona para o endpoint do n8n com espera pelo resultado
    """
    try:
        # Iniciar o processo no n8n
        response = n8n_create_gmail(user_id)
        result = response.get_json()

        if not result.get("success"):
            # Se houver erro ao iniciar, retornar o erro
            return jsonify(result), 200

        job_id = result.get("job_id")
        # Máximo de segundos para aguardar (abaixo do timeout do Cloudflare)
        max_wait = 90
        wait_interval = 2  # Intervalo entre verificações em segundos

        logger.info(
            f"[COMPATIBILIDADE] Aguardando resultado do job {job_id} (máx {max_wait}s)")

        # Aguardar até que o job seja concluído ou timeout
        start_time = time.time()
        while time.time() - start_time < max_wait:
            # Verificar status do job
            status_response = gmail_job_status(job_id)
            status_data = status_response.get_json()

            # Se o job foi concluído (com sucesso ou falha)
            if status_data.get("status") in ["completed", "failed"]:
                # Construir resposta compatível com o formato antigo
                if status_data.get("status") == "completed":
                    return jsonify({  # <- CORRIGIDO: Agora está corretamente indentado
                        "success": True,
                        "message": "Conta Gmail criada com sucesso",
                        "account": status_data.get("result")
                    }), 200
                else:
                    return jsonify({
                        "success": False,
                        "error": status_data.get("message"),
                        "error_code": "CREATION_FAILED",
                        "user_id": user_id,
                        "n8n_friendly": True
                    }), 200

            # Aguardar antes da próxima verificação
            time.sleep(wait_interval)

        # Se atingiu o timeout
        logger.warning(
            f"[AVISO] Timeout ao aguardar job {job_id}. Operação continua em background.")
        return jsonify({
            "success": False,
            "error": "Timeout ao aguardar conclusão. A operação continua em background.",
            "error_code": "TIMEOUT",
            "job_id": job_id,
            "user_id": user_id,
            "message": f"Verifique o status em /gmail-job-status/{job_id}",
            "n8n_friendly": True
        }), 200

    except Exception as e:
        logger.error(f"[ERRO] Erro no endpoint compatível: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "error_code": "UNEXPECTED_ERROR",
            "user_id": user_id,
            "n8n_friendly": True
        }), 200


def process_gmail_creation_with_callback(job_id, user_id, data, webhook_callback=None):
    """
    Processa a criação de conta Gmail em background e realiza callback se configurado.

    Similar ao process_gmail_creation, mas com suporte a webhook de callback para n8n.
    """
    try:
        # Verificar se o job existe
        job_file = os.path.join(JOBS_DIR, f"{job_id}.json")
        if not os.path.exists(job_file):
            logger.error(
                f"[ERRO] Job {job_id} não encontrado no início do processamento")
            return

        # Primeiro chama o processador regular
        logger.info(
            f"[N8N] Iniciando processamento do job {job_id} para o usuário {user_id}")
        process_gmail_creation(job_id, user_id, data)
        logger.info(f"[N8N] Processamento do job {job_id} concluído")

        # Se um webhook de callback foi configurado, envia os resultados
        if webhook_callback:
            try:
                # Carregar o status atual do job após processamento
                if os.path.exists(job_file):
                    with open(job_file, "r") as f:
                        job_data = json.load(f)

                    # Preparar dados para o callback
                    callback_data = {
                        "job_id": job_id,
                        "user_id": user_id,
                        "status": job_data.get("status", "unknown"),
                        "success": job_data.get("status") == "completed",
                        "message": job_data.get("message", "Sem mensagem disponível"),
                        "result": job_data.get("result"),
                        "timestamp": time.time()
                    }

                    # Adicionar detalhes de erro se disponíveis
                    if job_data.get("status") == "failed" and "error_details" in job_data:
                        callback_data["error_details"] = job_data["error_details"]

                    # Enviar callback com o status final
                    logger.info(
                        f"[N8N] Enviando callback para {webhook_callback}")
                    response = requests.post(
                        webhook_callback, json=callback_data, timeout=10)

                    # Registrar resultado do callback
                    if response.status_code == 200:
                        logger.info(
                            f"[N8N] Callback enviado com sucesso para {webhook_callback}")

                        # Atualizar o job para registrar que o callback foi enviado
                        job_data["callback_sent"] = True
                        job_data["callback_time"] = time.time()
                        job_data["callback_status_code"] = response.status_code

                        with open(job_file, "w") as f:
                            json.dump(job_data, f, indent=4)
                    else:
                        logger.warning(
                            f"[N8N] Callback falhou: {response.status_code} - {response.text}")

                        # Atualizar o job para registrar que o callback falhou
                        job_data["callback_sent"] = False
                        job_data["callback_error"] = f"Status code: {response.status_code}, Resposta: {response.text}"
                        job_data["callback_time"] = time.time()

                        with open(job_file, "w") as f:
                            json.dump(job_data, f, indent=4)
                else:
                    logger.error(
                        f"[ERRO] Arquivo de job {job_id} não encontrado após processamento")
            except Exception as e:
                logger.error(
                    f"[ERRO] Falha ao enviar callback para {webhook_callback}: {str(e)}")

                # Tentar atualizar o job para registrar o erro no callback
                try:
                    if os.path.exists(job_file):
                        with open(job_file, "r") as f:
                            job_data = json.load(f)

                        job_data["callback_sent"] = False
                        job_data["callback_error"] = str(e)
                        job_data["callback_time"] = time.time()

                        with open(job_file, "w") as f:
                            json.dump(job_data, f, indent=4)
                except Exception as update_error:
                    logger.error(
                        f"[ERRO] Falha ao atualizar job com erro de callback: {str(update_error)}")
    except Exception as e:
        logger.error(
            f"[ERRO] Erro geral no processo de criação com callback: {str(e)}")

        # Tentar atualizar o status do job para refletir o erro
        try:
            update_job_status(job_id, "failed", f"Erro no processamento: {str(e)}",
                              error_details=f"Ocorreu um erro inesperado durante o processamento: {str(e)}")
        except Exception as update_error:
            logger.error(
                f"[ERRO] Não foi possível atualizar o status do job após erro: {str(update_error)}")


if __name__ == '__main__':
    # Iniciar o servidor em modo de produção
    # Em ambiente de produção, use um servidor WSGI como Gunicorn
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)
