
import os
import sys
import time
import json
import logging
import uuid
from threading import Thread
import requests
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi import FastAPI, HTTPException, Request, Response

# Adicionando os diretórios necessários ao PYTHONPATH
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)  # automation_py
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Importações Locais
from powerads_api.ads_power_manager import AdsPowerManager
from powerads_api.browser_manager import BrowserManager, BrowserConfig
from apis.sms_api import SMSAPI
from powerads_api.profiles import ProfileManager, get_profiles
from credentials.credentials_manager import get_credential, load_credentials
from automations.adsense_creator.core import AdSenseCreator
from automations.gmail_creator.core import GmailCreator
from automations.data_generator import generate_gmail_credentials


# Criar a aplicação FastAPI
app = FastAPI(
    title="AdsPower RPA API",
    description="API para automação RPA com AdsPower",
    version="1.0.0"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Definir diretórios de dados
SMS_DATA_DIR = "sms_data"
os.makedirs(SMS_DATA_DIR, exist_ok=True)

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

# Modelos Pydantic para validação de dados


class SMSWebhookData(BaseModel):
    id: str
    phone: Optional[str] = None
    sms: str
    status: Optional[str] = None


class PhoneParams(BaseModel):
    country: Optional[str] = None
    service: Optional[str] = None
    operator: Optional[str] = None


class GmailCreationParams(BaseModel):
    headless: Optional[bool] = False
    max_wait_time: Optional[int] = 60
    recovery_email: Optional[str] = None
    webhook_callback: Optional[str] = None


class AdSenseCreationParams(BaseModel):
    website_url: str
    country: str
    headless: Optional[bool] = False
    max_wait_time: Optional[int] = 60
    webhook_callback: Optional[str] = None
    close_browser_on_finish: Optional[bool] = False


class BatchProfileConfig(BaseModel):
    user_id: str
    phone_params: Optional[PhoneParams] = None
    headless: Optional[bool] = None


class BatchCreationParams(BaseModel):
    profiles: List[BatchProfileConfig]
    common_params: Optional[Dict[str, Any]] = None
    max_concurrent: Optional[int] = 2
    webhook_callback: Optional[str] = None

# Modelos Pydantic adicionais


class SMSData(BaseModel):
    activation_id: str
    phone_number: Optional[str] = None
    sms_code: str
    status: Optional[str] = None


class ProfileResponse(BaseModel):
    user_id: str
    name: Optional[str] = None
    group_id: Optional[str] = None
    group_name: Optional[str] = None
    status: Optional[str] = "unknown"
    created_time: Optional[str] = None
    updated_time: Optional[str] = None


class ProfileListResponse(BaseModel):
    success: bool
    count: int
    profiles: List[ProfileResponse]

# Funções auxiliares


def save_sms_data(activation_id: str, data: dict) -> None:
    """Salva dados do SMS em arquivo para persistência."""
    try:
        file_path = os.path.join(SMS_DATA_DIR, f"{activation_id}.json")
        with open(file_path, 'w') as f:
            json.dump(data, f)
        logger.info(f"[OK] Dados do SMS {activation_id} salvos com sucesso")
    except Exception as e:
        logger.error(f"[ERRO] Erro ao salvar dados do SMS: {str(e)}")


def process_sms_code(activation_id: str, phone_number: str, sms_code: str, status: str) -> None:
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


def get_callback_url(activation_id: str) -> Optional[str]:
    """
    Recupera a URL de callback para uma ativação específica.
    Implementação simplificada - em um sistema real, isso buscaria de um banco de dados.
    """
    try:
        config_path = os.path.join(SMS_DATA_DIR, "callbacks.json")
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                callbacks = json.load(f)
                return callbacks.get(activation_id)
    except Exception:
        pass
    return None


def update_sms_status(activation_id: str, status: str, error: Optional[str] = None) -> None:
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


def process_gmail_creation(job_id: str, user_id: str, data: dict):
    """
    Processa a criação de uma conta Gmail em background.

    Args:
        job_id: ID do job
        user_id: ID do usuário solicitando a criação
        data: Dados adicionais para criação da conta
    """
    try:
        # Atualizar status para processando
        update_job_status(
            job_id=job_id,
            status="processing",
            message="Iniciando criação da conta"
        )

        # Validar parâmetros
        if not user_id:
            raise ValueError("user_id é obrigatório")

        # Extrair parâmetros do data
        headless = data.get('headless', False) if data else False
        max_wait_time = data.get('max_wait_time', 60) if data else 60
        recovery_email = data.get('recovery_email') if data else None

        # Gerar credenciais para o Gmail

        credentials = generate_gmail_credentials()
        if not credentials:
            raise ValueError("Falha ao gerar credenciais para o Gmail")

        # Adicionar recovery_email às credenciais se fornecido
        if recovery_email:
            credentials["recovery_email"] = recovery_email

        # Criar classe temporária de cache
        class TempCache:
            def __init__(self):
                self.profiles_cache = {}

        # Verificar se perfil existe
        profile_manager = ProfileManager(TempCache())
        profiles = profile_manager.get_all_profiles(force_refresh=True)
        profile = next(
            (p for p in profiles if p.get("user_id") == user_id), None)
        if not profile:
            raise ValueError(f"Perfil {user_id} não encontrado")

        # Importar as classes necessárias

        # Obter credenciais
        base_url = get_credential("PA_BASE_URL")
        api_key = get_credential("PA_API_KEY")
        sms_api_key = get_credential("SMS_ACTIVATE_API_KEY")

        # Configurar browser manager
        browser_config = BrowserConfig(
            headless=headless, max_wait_time=max_wait_time)
        adspower_manager = AdsPowerManager(base_url, api_key)
        browser_manager = BrowserManager(adspower_manager)
        browser_manager.set_config(browser_config)

        # Inicializar componentes
        sms_api = SMSAPI(sms_api_key) if sms_api_key else None
        gmail_creator = GmailCreator(
            browser_manager=browser_manager,
            credentials=credentials,
            sms_api=sms_api,
            profile_name=user_id
        )

        # Criar conta
        success, result = gmail_creator.create_account(user_id)

        if success:
            # Atualizar status com sucesso
            update_job_status(
                job_id=job_id,
                status="completed",
                message="Conta criada com sucesso",
                result=result
            )
        else:
            # Atualizar status com erro
            update_job_status(
                job_id=job_id,
                status="error",
                message="Falha ao criar conta Gmail",
                error_details="O processo de criação falhou. Verifique os logs para mais detalhes."
            )

    except Exception as e:
        logger.error(f"Erro ao processar job {job_id}: {str(e)}")

        # Atualizar status com erro
        update_job_status(
            job_id=job_id,
            status="error",
            message=f"Erro ao criar conta: {str(e)}",
            error_details=str(e)
        )


def update_job_status(job_id: str, status: str, message: str, result: dict = None, error_details: str = None):
    """
    Atualiza o status de um job e salva em arquivo.

    Args:
        job_id: ID do job
        status: Novo status (pending, processing, completed, error)
        message: Mensagem descritiva do status
        result: Resultado do job se completado com sucesso
        error_details: Detalhes do erro se falhou
    """
    try:
        # Carregar dados existentes do job
        job_file = os.path.join(JOBS_DIR, f"{job_id}.json")

        if os.path.exists(job_file):
            with open(job_file, "r") as f:
                job_data = json.load(f)
                logger.info(
                    f"[DEBUG] Job {job_id} lido do arquivo: website_url={job_data.get('website_url')}")
        else:
            job_data = {"id": job_id}
            logger.info(f"[DEBUG] Job {job_id} não encontrado, criando novo")

        # Atualizar dados
        job_data.update({
            "status": status,
            "message": message,
            "updated_at": datetime.now().isoformat()
        })

        if result:
            logger.info(
                f"[DEBUG] Atualizando job {job_id} com resultado: site_url={result.get('site_url')}")
            job_data["result"] = result

        if error_details:
            job_data["error"] = error_details

        # Log do job antes de salvar
        if "website_url" in job_data:
            logger.info(
                f"[DEBUG] Job {job_id} antes de salvar: website_url={job_data.get('website_url')}")
        if "result" in job_data and "site_url" in job_data.get("result", {}):
            logger.info(
                f"[DEBUG] Job {job_id} antes de salvar: result.site_url={job_data.get('result', {}).get('site_url')}")

        # Remover o campo website_url quando o job estiver completo e tiver o campo site_url no resultado
        if status == "completed" and result and "site_url" in result:
            if "website_url" in job_data:
                logger.info(
                    f"[DEBUG] Removendo website_url do job {job_id} ao finalizar com sucesso")
                job_data.pop("website_url", None)

        # Salvar arquivo atualizado
        with open(job_file, "w") as f:
            json.dump(job_data, f, indent=2)

        logger.info(
            f"Status do job {job_id} atualizado para {status}: {message}")

    except Exception as e:
        logger.error(f"Erro ao atualizar status do job {job_id}: {str(e)}")
        raise

# Rotas da API


@app.get("/health")
async def health_check():
    """
    Verifica a saúde do serviço e suas integrações
    """
    try:
        # Carrega credenciais usando o caminho correto
        credentials_path = os.path.join(os.path.dirname(
            __file__), "..", "credentials", "credentials.json")
        with open(credentials_path) as f:
            credentials = json.load(f)

        # Verifica AdsPower
        ads_manager = AdsPowerManager(
            base_url=credentials.get("PA_BASE_URL"),
            api_key=credentials.get("PA_API_KEY")
        )
        ads_health = ads_manager.check_api_health()

        # Verifica e cria diretórios se não existirem
        data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        jobs_dir = os.path.join(os.path.dirname(__file__), "..", "jobs")

        # Criar diretórios se não existirem
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(jobs_dir, exist_ok=True)

        # Testar permissões criando arquivo temporário
        storage_status = {}
        for dir_path, dir_name in [(data_dir, "data_dir"), (jobs_dir, "jobs_dir")]:
            try:
                test_file = os.path.join(dir_path, ".test_permissions")
                with open(test_file, "w") as f:
                    f.write("test")
                os.remove(test_file)
                storage_status[dir_name] = True
            except Exception as e:
                logger.error(
                    f"Erro ao testar permissões em {dir_path}: {str(e)}")
                storage_status[dir_name] = False

        # Monta resposta
        response = {
            "status": "healthy" if all([ads_health, all(storage_status.values())]) else "degraded",
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0",
            "components": {
                "server": {
                    "status": "online"
                },
                "adspower": {
                    "status": "online" if ads_health else "offline",
                    "message": "API respondendo normalmente" if ads_health else "Erro ao conectar com API"
                },
                "storage": {
                    "status": "ok" if all(storage_status.values()) else "error",
                    "details": storage_status
                }
            }
        }

        return JSONResponse(
            status_code=200 if response["status"] == "healthy" else 503,
            content=response
        )

    except Exception as e:
        logger.error(f"[ERRO] Erro ao verificar saúde do serviço: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e)
            }
        )


@app.post("/sms-webhook")
async def sms_webhook(data: SMSData):
    """Endpoint para receber notificações de SMS."""
    try:
        # Armazenar o código SMS
        sms_codes[data.activation_id] = {
            "phone_number": data.phone_number,
            "sms_code": data.sms_code,
            "status": data.status,
            "received_at": time.time()
        }

        # Salvar em arquivo para persistência
        save_sms_data(data.activation_id, sms_codes[data.activation_id])

        # Processar o código SMS em uma thread separada
        Thread(target=process_sms_code, args=(
            data.activation_id, data.phone_number, data.sms_code, data.status)).start()

        return {"success": True, "message": "SMS recebido e processado"}

    except Exception as e:
        logger.error(f"[ERRO] Erro ao processar webhook: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar webhook: {str(e)}"
        )


@app.get("/sms-status/{activation_id}")
async def get_sms_status(activation_id: str):
    """Endpoint para verificar o status de um SMS pelo ID de ativação."""
    if activation_id in sms_codes:
        return sms_codes[activation_id]

    # Tentar carregar do arquivo
    file_path = os.path.join(SMS_DATA_DIR, f"{activation_id}.json")
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            return data
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=str(e)
            )

    raise HTTPException(
        status_code=404,
        detail="Activation ID not found"
    )


@app.get("/profiles")
async def list_profiles(force_refresh: bool = False):
    """Endpoint para listar todos os perfis do AdsPower."""
    try:
        # Obter credenciais
        base_url = get_credential("PA_BASE_URL")
        api_key = get_credential("PA_API_KEY")

        if not base_url or not api_key:
            raise HTTPException(
                status_code=400,
                detail="Credenciais do AdsPower não configuradas"
            )

        # Criar uma instância temporária do ProfileManager
        class TempCache:
            def __init__(self):
                self.profiles_cache = {}

        profile_manager = ProfileManager(TempCache())

        # Obter perfis
        profiles = profile_manager.get_all_profiles(
            force_refresh=force_refresh)

        if not profiles:
            raise HTTPException(
                status_code=404,
                detail="Nenhum perfil encontrado"
            )

        # Transformar a lista com validação de campos
        simplified_profiles = []
        for profile in profiles:
            try:
                profile_data = {
                    "user_id": profile.get("user_id", ""),
                    "name": profile.get("name"),
                    "group_id": profile.get("group_id"),
                    "group_name": profile.get("group_name"),
                    "status": profile.get("status", "unknown"),
                    "created_time": profile.get("created_time"),
                    "updated_time": profile.get("updated_time")
                }
                # Garantir que user_id não seja None ou vazio
                if not profile_data["user_id"]:
                    continue

                simplified_profiles.append(ProfileResponse(**profile_data))
            except Exception as e:
                logger.error(f"Erro ao processar perfil: {str(e)}")
                continue

        if not simplified_profiles:
            raise HTTPException(
                status_code=404,
                detail="Nenhum perfil válido encontrado"
            )

        logger.info(
            f"[OK] Retornando {len(simplified_profiles)} perfis do AdsPower")
        return ProfileListResponse(
            success=True,
            count=len(simplified_profiles),
            profiles=simplified_profiles
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERRO] Erro ao listar perfis do AdsPower: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get("/profiles/{user_id}")
async def get_profile_details(user_id: str):
    """Endpoint para obter detalhes de um perfil específico."""
    try:
        # Obter credenciais
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

        # Obter perfis
        profiles = profile_manager.get_all_profiles(force_refresh=True)

        # Encontrar o perfil específico
        profile = next(
            (p for p in profiles if p.get("user_id") == user_id), None)

        if not profile:
            raise HTTPException(
                status_code=404,
                detail=f"Perfil {user_id} não encontrado"
            )

        logger.info(f"[OK] Perfil {user_id} encontrado")
        return {
            "success": True,
            "profile": profile
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[ERRO] Erro ao obter detalhes do perfil {user_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.post("/create-gmail/{user_id}")
async def create_gmail_account(
    user_id: str,
    params: GmailCreationParams
):
    """Endpoint para criar uma conta Gmail."""
    try:
        # Gerar job_id
        job_id = str(uuid.uuid4())

        # Criar diretório de jobs se não existir
        os.makedirs(JOBS_DIR, exist_ok=True)

        # Salvar estado inicial do job
        update_job_status(
            job_id=job_id,
            status="pending",
            message="Job criado, aguardando processamento"
        )

        # Iniciar processamento em background
        Thread(
            target=process_gmail_creation,
            args=(job_id, user_id, params.dict()),
            daemon=True
        ).start()

        return {
            "success": True,
            "job_id": job_id,
            "status": "pending",
            "message": "Job iniciado com sucesso"
        }

    except Exception as e:
        logger.error(
            f"[ERRO] Erro ao criar job para usuário {user_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get("/gmail-job-status/{job_id}")
async def get_gmail_job_status(job_id: str):
    """Endpoint para verificar o status de um job."""
    try:
        # Normalizar job_id
        job_id = job_id.strip()

        # Construir caminho do arquivo
        job_file = os.path.join(JOBS_DIR, f"{job_id}.json")

        if not os.path.exists(job_file):
            raise HTTPException(
                status_code=404,
                detail=f"Job não encontrado: {job_id}"
            )

        # Carregar dados do job
        with open(job_file) as f:
            job_data = json.load(f)

        return job_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[ERRO] Erro ao verificar status do job {job_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.post("/adsense-creator/{user_id}")
async def create_adsense_account(user_id: str, data: dict = None):
    """
    Endpoint para iniciar a criação de uma conta AdSense.
    Recebe a URL do site e o país/território para a conta.

    Parâmetros:
    - user_id: ID do perfil do AdsPower a ser utilizado

    Corpo da requisição (JSON):
    {
        "website_url": "https://example.com",
        "country": "Brasil",
        "headless": false  # opcional
    }

    Resposta:
    {
        "success": true,
        "job_id": "job-uuid",
        "status": "pending",
        "message": "Processo de criação de conta AdSense iniciado"
    }
    """
    try:
        # Verificar se o perfil existe
        if not user_id:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "ID do perfil não fornecido",
                    "error_code": "MISSING_USER_ID"
                }
            )

        # Garantir que data seja um dicionário válido
        if data is None:
            data = {}

        # Validar dados obrigatórios
        if not data.get('website_url'):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "URL do site não fornecida",
                    "error_code": "MISSING_WEBSITE_URL"
                }
            )

        if not data.get('country'):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "País/território não fornecido",
                    "error_code": "MISSING_COUNTRY"
                }
            )

        # Gerar um job_id único
        job_id = str(uuid.uuid4())

        # Criar dados do job
        job_data = {
            "job_id": job_id,
            "user_id": user_id,
            "status": "pending",
            "created_at": time.time(),
            "website_url": data.get('website_url'),
            "country": data.get('country'),
            "headless": data.get('headless', False),
            "message": "Processo de criação de conta AdSense iniciado",
            "capture_codes": False  # Não capturar códigos neste endpoint
        }

        # Salvar dados do job em arquivo
        job_file = os.path.join(JOBS_DIR, f"{job_id}.json")
        with open(job_file, "w") as f:
            json.dump(job_data, f, indent=4)

        # Iniciar processo em uma thread separada
        Thread(
            target=process_adsense_creation,
            args=(job_id, user_id, data),
            daemon=True
        ).start()

        logger.info(
            f"[ADSENSE] Job {job_id} iniciado para criação de conta AdSense no perfil {user_id}")

        return {
            "success": True,
            "job_id": job_id,
            "user_id": user_id,
            "status": "pending",
            "message": "Processo de criação de conta AdSense iniciado",
            "status_url": f"/adsense-job-status/{job_id}"
        }

    except Exception as e:
        logger.error(
            f"[ERRO] Erro ao iniciar criação de conta AdSense: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "error_code": "ADSENSE_START_ERROR"
            }
        )


@app.post("/adsense-code-capture/{user_id}")
async def capture_adsense_codes(user_id: str, data: dict = None):
    """
    Endpoint para capturar os códigos de verificação do AdSense (pub-ID e snippet ads.txt).
    Este endpoint deve ser chamado após a criação da conta AdSense.

    Parâmetros:
    - user_id: ID do perfil do AdsPower a ser utilizado

    Corpo da requisição (JSON):
    {
        "website_url": "https://example.com",  # URL do site para associar aos códigos
        "headless": false,  # opcional
        "previous_job_id": "job-uuid"  # opcional - ID do job de criação da conta
    }

    Resposta:
    {
        "success": true,
        "job_id": "job-uuid",
        "status": "pending",
        "message": "Processo de captura de códigos iniciado"
    }
    """
    try:
        # Verificar se o perfil existe
        if not user_id:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "ID do perfil não fornecido",
                    "error_code": "MISSING_USER_ID"
                }
            )

        # Garantir que data seja um dicionário válido
        if data is None:
            data = {}

        # Validar dados obrigatórios
        if not data.get('website_url'):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "URL do site não fornecida",
                    "error_code": "MISSING_WEBSITE_URL"
                }
            )

        # Gerar um job_id único
        job_id = str(uuid.uuid4())

        # Criar dados do job
        job_data = {
            "job_id": job_id,
            "user_id": user_id,
            "status": "pending",
            "created_at": time.time(),
            "website_url": data.get('website_url'),
            "headless": data.get('headless', False),
            "message": "Processo de captura de códigos de verificação iniciado",
            "previous_job_id": data.get('previous_job_id')
        }

        # Salvar dados do job em arquivo
        job_file = os.path.join(JOBS_DIR, f"{job_id}.json")
        with open(job_file, "w") as f:
            json.dump(job_data, f, indent=4)

        # Iniciar processo em uma thread separada
        Thread(
            target=process_adsense_code_capture,
            args=(job_id, user_id, data),
            daemon=True
        ).start()

        logger.info(
            f"[ADSENSE] Job {job_id} iniciado para captura de códigos no perfil {user_id}")

        return {
            "success": True,
            "job_id": job_id,
            "user_id": user_id,
            "status": "pending",
            "message": "Processo de captura de códigos de verificação iniciado",
            "status_url": f"/adsense-job-status/{job_id}"
        }

    except Exception as e:
        logger.error(
            f"[ERRO] Erro ao iniciar captura de códigos: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "error_code": "ADSENSE_CODE_CAPTURE_ERROR"
            }
        )


@app.get("/adsense-job-status/{job_id}")
async def get_adsense_job_status(job_id: str):
    """Endpoint para verificar o status de um job de criação de conta AdSense."""
    try:
        # Normalizar job_id
        job_id = job_id.strip()

        # Construir caminho do arquivo
        job_file = os.path.join(JOBS_DIR, f"{job_id}.json")

        if not os.path.exists(job_file):
            logger.warning(f"[AVISO] Job não encontrado: {job_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Job não encontrado: {job_id}"
            )

        # Carregar dados do job
        with open(job_file) as f:
            job_data = json.load(f)

        # Adicionar logs para debug
        logger.info(f"[DEBUG-STATUS] Job {job_id} carregado com sucesso")
        if "website_url" in job_data:
            logger.info(
                f"[DEBUG-STATUS] Job {job_id} tem website_url: {job_data.get('website_url')}")
        if "result" in job_data and "site_url" in job_data.get("result", {}):
            logger.info(
                f"[DEBUG-STATUS] Job {job_id} tem result.site_url: {job_data.get('result', {}).get('site_url')}")

        # Remover o campo website_url quando o job estiver completo e tiver informações no result
        if job_data.get("status") == "completed" and "result" in job_data and job_data.get("result", {}).get("site_url"):
            if "website_url" in job_data:
                logger.info(
                    f"[DEBUG] Removendo website_url do job {job_id}")
                job_data.pop("website_url", None)

        # Garantir que a result.site_url corresponda à website_url original
        if "result" in job_data and "site_url" in job_data.get("result", {}) and "website_url" in job_data:
            original_url = job_data.get("website_url")
            result_url = job_data.get("result", {}).get("site_url")

            if original_url != result_url and "meusite.com.br" in result_url:
                logger.warning(
                    f"[AVISO] Corrigindo URL no resultado: {result_url} -> {original_url}")
                job_data["result"]["site_url"] = original_url

                # Salvar o arquivo atualizado
                with open(job_file, "w") as f:
                    json.dump(job_data, f, indent=2)

                logger.info(f"[DEBUG-STATUS] Job {job_id} corrigido e salvo")

        return job_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[ERRO] Erro ao verificar status do job de AdSense {job_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get("/adsense-verification-codes/{website_url:path}")
async def get_adsense_verification_codes(website_url: str):
    """
    Endpoint para obter os códigos de verificação mais recentes para um determinado site.

    Parâmetros:
    - website_url: URL do site para o qual buscar os códigos

    Resposta:
    {
        "success": true,
        "site_url": "https://example.com",
        "pub": "1234567890123456",
        "direct": "f08c47fec0942fa0",
        "capture_time": "YYYY-MM-DD HH:MM:SS",
        "job_id": "job-uuid"
    }
    """
    try:
        # Normalizar a URL
        if not website_url.startswith(('http://', 'https://')):
            website_url = 'https://' + website_url

        # Remover barra no final se existir
        website_url = website_url.rstrip('/')

        # Listar todos os arquivos de job
        job_files = []
        for filename in os.listdir(JOBS_DIR):
            if filename.endswith('.json'):
                file_path = os.path.join(JOBS_DIR, filename)
                try:
                    with open(file_path, 'r') as f:
                        job_data = json.load(f)

                    # Verificar se é um job completado de captura de códigos que contém os dados relevantes
                    if (job_data.get('status') == 'completed' and
                        ((job_data.get('result') and job_data.get('result').get('website_url')) or
                         job_data.get('website_url'))):

                        # Obter a URL do site a partir do resultado ou dos dados do job
                        job_website_url = None
                        if job_data.get('result') and job_data.get('result').get('website_url'):
                            job_website_url = job_data['result']['website_url']
                        elif job_data.get('website_url'):
                            job_website_url = job_data['website_url']

                        # Normalizar a URL do job
                        if job_website_url:
                            if not job_website_url.startswith(('http://', 'https://')):
                                job_website_url = 'https://' + job_website_url
                            job_website_url = job_website_url.rstrip('/')

                            # Se a URL corresponder, adicionar à lista
                            if job_website_url == website_url:
                                # Adicionar timestamp para ordenação
                                timestamp = job_data.get(
                                    'updated_at', job_data.get('created_at', 0))
                                job_files.append((timestamp, job_data))
                except Exception as e:
                    logger.warning(
                        f"Erro ao processar arquivo de job {filename}: {str(e)}")
                    continue

        # Se não encontrou nenhum job para o site
        if not job_files:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": f"Nenhum código de verificação encontrado para {website_url}",
                    "error_code": "NO_VERIFICATION_CODES"
                }
            )

        # Ordenar por timestamp decrescente (mais recente primeiro)
        job_files.sort(key=lambda x: x[0], reverse=True)
        latest_job = job_files[0][1]

        # Extrair códigos de verificação
        pub_id = ""
        direct_id = ""
        verification_code = ""
        site_url = website_url
        capture_time = ""

        # Obter do resultado
        if latest_job.get('result'):
            # Tentar obter os novos campos formatados
            pub_id = latest_job['result'].get('pub', '')
            direct_id = latest_job['result'].get('direct', '')

            # Se não encontrar, tentar extrair do formato antigo
            if not pub_id and latest_job['result'].get('publisher_id'):
                publisher_id = latest_job['result'].get('publisher_id', '')
                if publisher_id.startswith('pub-'):
                    pub_id = publisher_id.replace('pub-', '')

            if not direct_id and latest_job['result'].get('verification_code'):
                verification_code = latest_job['result'].get(
                    'verification_code', '')
                parts = verification_code.split(',')
                if len(parts) >= 4:
                    direct_id = parts[3].strip()

            # Site URL e capture_time
            site_url = latest_job['result'].get(
                'site_url', latest_job['result'].get('website_url', website_url))
            capture_time = latest_job['result'].get('capture_time', '')

        # Retornar os códigos no formato solicitado
        return {
            "success": True,
            "site_url": site_url,
            "pub": pub_id,
            "direct": direct_id,
            "capture_time": capture_time,
            "job_id": latest_job.get('job_id', '')
        }

    except Exception as e:
        logger.error(
            f"[ERRO] Erro ao buscar códigos de verificação para {website_url}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"Erro ao buscar códigos de verificação: {str(e)}",
                "error_code": "VERIFICATION_CODES_ERROR"
            }
        )


def process_adsense_creation(job_id, user_id, data):
    """
    Processa a criação de uma conta AdSense em background.

    Args:
        job_id: ID do job
        user_id: ID do perfil do AdsPower
        data: Dados para criação da conta
    """
    try:
        # Atualizar status do job
        update_job_status(
            job_id=job_id,
            status="processing",
            message="Iniciando processo de criação de conta AdSense"
        )

        # Importar classes necessárias
        try:
            from automations.adsense_creator.core import AdSenseCreator
            from powerads_api.browser_manager import BrowserManager, BrowserConfig
            from powerads_api.ads_power_manager import AdsPowerManager
            import requests
        except ImportError as e:
            update_job_status(
                job_id=job_id,
                status="failed",
                message=f"Erro ao importar dependências: {str(e)}",
                error_details=f"Módulo não encontrado: {str(e)}. Verifique se o pacote adsense_creator está instalado."
            )
            logger.error(
                f"[ERRO] Erro ao importar módulos para AdSense Creator: {str(e)}")
            return

        # Obter credenciais
        base_url = get_credential("PA_BASE_URL")
        api_key = get_credential("PA_API_KEY")

        if not base_url or not api_key:
            update_job_status(
                job_id=job_id,
                status="failed",
                message="Credenciais do AdsPower não configuradas",
                error_details="As credenciais do AdsPower (PA_BASE_URL e/ou PA_API_KEY) não estão configuradas."
            )
            return

        # Verificar diretamente se o perfil existe através de uma chamada API direta
        try:
            headers = {"Authorization": f"Bearer {api_key}"}
            response = requests.get(
                f"{base_url}/api/v1/user/list", headers=headers, timeout=30)

            if response.status_code == 200:
                api_data = response.json()
                if api_data.get("code") == 0 and "list" in api_data.get("data", {}):
                    profiles = api_data["data"]["list"]
                    profile_exists = any(profile.get(
                        "user_id") == user_id for profile in profiles)

                    if not profile_exists:
                        logger.warning(
                            f"Perfil {user_id} não encontrado na lista de perfis. Perfis disponíveis: {[p.get('user_id') for p in profiles]}")
                        update_job_status(
                            job_id=job_id,
                            status="failed",
                            message=f"Perfil {user_id} não encontrado",
                            error_details=f"O perfil com ID {user_id} não foi encontrado na lista de perfis do AdsPower. Verifique se o perfil existe e está ativo."
                        )
                        return
                    else:
                        logger.info(
                            f"Perfil {user_id} encontrado. Continuando com a criação da conta.")
                else:
                    logger.error(
                        f"Resposta inválida da API ao listar perfis: {api_data}")
                    update_job_status(
                        job_id=job_id,
                        status="failed",
                        message="Falha ao verificar se o perfil existe",
                        error_details=f"Resposta inválida da API AdsPower: {api_data}"
                    )
                    return
            else:
                logger.error(
                    f"Falha ao consultar API do AdsPower: Status code {response.status_code}")
                update_job_status(
                    job_id=job_id,
                    status="failed",
                    message=f"Falha ao verificar perfil: Status code {response.status_code}",
                    error_details=f"A API do AdsPower retornou status code {response.status_code} ao tentar listar perfis."
                )
                return
        except Exception as e:
            logger.error(f"Erro na requisição ao verificar perfil: {str(e)}")
            update_job_status(
                job_id=job_id,
                status="failed",
                message=f"Erro ao verificar perfil: {str(e)}",
                error_details=f"Ocorreu um erro ao tentar verificar se o perfil existe: {str(e)}"
            )
            return

        # Configurar browser manager
        browser_config = BrowserConfig(
            headless=data.get('headless', False),
            max_wait_time=data.get('max_wait_time', 60)
        )

        try:
            adspower_manager = AdsPowerManager(base_url, api_key)
            browser_manager = BrowserManager(adspower_manager)
            browser_manager.set_config(browser_config)

            # Verificar se o AdsPower está acessível
            if not adspower_manager.check_api_health(force_check=True):
                update_job_status(
                    job_id=job_id,
                    status="failed",
                    message="Não foi possível conectar ao AdsPower",
                    error_details="Falha na conexão com a API do AdsPower. Verifique se o serviço está em execução."
                )
                return

            # Criar objeto de conta com os dados recebidos
            account_data = {
                "website_url": data.get('website_url'),
                "country": data.get('country'),
                "capture_codes": False  # Desativar a captura de códigos neste endpoint
            }

            # Inicializar o criador de AdSense
            adsense_creator = AdSenseCreator(
                browser_manager=browser_manager,
                account_data=account_data,
                profile_name=user_id
            )

            # Executar criação da conta
            update_job_status(
                job_id=job_id,
                status="processing",
                message="Iniciando browser e criação da conta AdSense"
            )

            success, result = adsense_creator.create_account(user_id)

            # Atualizar status final
            if success:
                update_job_status(
                    job_id=job_id,
                    status="completed",
                    message="Conta AdSense criada com sucesso",
                    result=result
                )
                logger.info(
                    f"[ADSENSE] Conta AdSense criada com sucesso para o job {job_id}")
            else:
                update_job_status(
                    job_id=job_id,
                    status="failed",
                    message="Falha ao criar conta AdSense",
                    error_details="O processo de criação falhou. Verifique os logs para mais detalhes."
                )
                logger.error(
                    f"[ADSENSE] Falha ao criar conta AdSense para o job {job_id}")

        except Exception as e:
            update_job_status(
                job_id=job_id,
                status="failed",
                message=f"Erro durante criação da conta: {str(e)}",
                error_details=f"Exceção: {type(e).__name__}: {str(e)}"
            )
            logger.error(f"[ERRO] Erro ao criar conta AdSense: {str(e)}")

    except Exception as e:
        logger.error(
            f"[ERRO] Erro geral no processamento do job {job_id}: {str(e)}")
        try:
            update_job_status(
                job_id=job_id,
                status="failed",
                message=f"Erro não tratado: {str(e)}",
                error_details=f"Exceção não tratada: {type(e).__name__}: {str(e)}"
            )
        except:
            pass


def process_adsense_code_capture(job_id, user_id, data):
    """
    Processa a captura dos códigos de verificação do AdSense em background.

    Args:
        job_id: ID do job
        user_id: ID do perfil do AdsPower
        data: Dados para a captura dos códigos
    """
    try:
        # Atualizar status do job
        update_job_status(
            job_id=job_id,
            status="processing",
            message="Iniciando processo de captura de códigos do AdSense"
        )

        # Importar classes necessárias
        try:
            from automations.adsense_creator.code_site import WebsiteCodeInjector
            from powerads_api.browser_manager import BrowserManager, BrowserConfig
            from powerads_api.ads_power_manager import AdsPowerManager
            import requests
        except ImportError as e:
            update_job_status(
                job_id=job_id,
                status="failed",
                message=f"Erro ao importar dependências: {str(e)}",
                error_details=f"Módulo não encontrado: {str(e)}. Verifique se o pacote adsense_creator está instalado."
            )
            logger.error(
                f"[ERRO] Erro ao importar módulos para captura de códigos: {str(e)}")
            return

        # Obter credenciais
        base_url = get_credential("PA_BASE_URL")
        api_key = get_credential("PA_API_KEY")

        if not base_url or not api_key:
            update_job_status(
                job_id=job_id,
                status="failed",
                message="Credenciais do AdsPower não configuradas",
                error_details="As credenciais do AdsPower (PA_BASE_URL e/ou PA_API_KEY) não estão configuradas."
            )
            return

        # Verificar diretamente se o perfil existe através de uma chamada API direta
        try:
            headers = {"Authorization": f"Bearer {api_key}"}
            response = requests.get(
                f"{base_url}/api/v1/user/list", headers=headers, timeout=30)

            if response.status_code == 200:
                api_data = response.json()
                if api_data.get("code") == 0 and "list" in api_data.get("data", {}):
                    profiles = api_data["data"]["list"]
                    profile_exists = any(profile.get(
                        "user_id") == user_id for profile in profiles)

                    if not profile_exists:
                        logger.warning(
                            f"Perfil {user_id} não encontrado na lista de perfis. Perfis disponíveis: {[p.get('user_id') for p in profiles]}")
                        update_job_status(
                            job_id=job_id,
                            status="failed",
                            message=f"Perfil {user_id} não encontrado",
                            error_details=f"O perfil com ID {user_id} não foi encontrado na lista de perfis do AdsPower. Verifique se o perfil existe e está ativo."
                        )
                        return
                    else:
                        logger.info(
                            f"Perfil {user_id} encontrado. Continuando com a captura de códigos.")
                else:
                    logger.error(
                        f"Resposta inválida da API ao listar perfis: {api_data}")
                    update_job_status(
                        job_id=job_id,
                        status="failed",
                        message="Falha ao verificar se o perfil existe",
                        error_details=f"Resposta inválida da API AdsPower: {api_data}"
                    )
                    return
            else:
                logger.error(
                    f"Falha ao consultar API do AdsPower: Status code {response.status_code}")
                update_job_status(
                    job_id=job_id,
                    status="failed",
                    message=f"Falha ao verificar perfil: Status code {response.status_code}",
                    error_details=f"A API do AdsPower retornou status code {response.status_code} ao tentar listar perfis."
                )
                return
        except Exception as e:
            logger.error(f"Erro na requisição ao verificar perfil: {str(e)}")
            update_job_status(
                job_id=job_id,
                status="failed",
                message=f"Erro ao verificar perfil: {str(e)}",
                error_details=f"Ocorreu um erro ao tentar verificar se o perfil existe: {str(e)}"
            )
            return

        # Configurar browser manager
        browser_config = BrowserConfig(
            headless=data.get('headless', False),
            max_wait_time=data.get('max_wait_time', 60)
        )

        try:
            adspower_manager = AdsPowerManager(base_url, api_key)
            browser_manager = BrowserManager(adspower_manager)
            browser_manager.set_config(browser_config)

            # Verificar se o AdsPower está acessível
            if not adspower_manager.check_api_health(force_check=True):
                update_job_status(
                    job_id=job_id,
                    status="failed",
                    message="Não foi possível conectar ao AdsPower",
                    error_details="Falha na conexão com a API do AdsPower. Verifique se o serviço está em execução."
                )
                return

            # Inicializar o browser
            update_job_status(
                job_id=job_id,
                status="processing",
                message="Inicializando o navegador para captura de códigos"
            )

            if not browser_manager.ensure_browser_ready(user_id):
                update_job_status(
                    job_id=job_id,
                    status="failed",
                    message="Falha ao inicializar o navegador",
                    error_details="Não foi possível inicializar o navegador para o perfil especificado."
                )
                return

            driver = browser_manager.get_driver()
            if not driver:
                update_job_status(
                    job_id=job_id,
                    status="failed",
                    message="Driver do navegador não disponível",
                    error_details="Não foi possível obter o driver do navegador após inicialização."
                )
                return

            # Criar objeto de website com os dados recebidos
            website_url = data.get('website_url')
            logger.info(
                f"[DEBUG] URL do site recebida na requisição: {website_url}")

            website_data = {
                "website_url": website_url
            }

            # Inicializar o capturador de códigos
            code_injector = WebsiteCodeInjector(driver, website_data)

            # Executar a captura de códigos
            update_job_status(
                job_id=job_id,
                status="processing",
                message="Capturando códigos de verificação do AdSense"
            )

            # Capturar os códigos
            success = code_injector.capture_verification_code(
                export_data=False)

            if success:
                # Obter os dados capturados
                captured_data = code_injector.get_captured_data()
                logger.info(f"[DEBUG] Dados capturados: {captured_data}")

                # Obter a URL do site com prioridade para a URL real capturada da página
                # Usar URL capturada da página
                site_url = captured_data.get("website_url")
                if not site_url:
                    # Fallback para URL da requisição
                    site_url = data.get("website_url")

                logger.info(f"[DEBUG] URL final escolhida: {site_url}")

                # Criar resposta formatada conforme solicitado
                result_data = {
                    "site_url": site_url,  # Usar URL real capturada
                    "pub": captured_data.get("pub", ""),
                    "direct": captured_data.get("direct", ""),
                    # Manter campos originais para compatibilidade
                    "publisher_id": captured_data.get("publisher_id", ""),
                    "verification_code": captured_data.get("verification_code", ""),
                    "capture_time": time.strftime("%Y-%m-%d %H:%M:%S")
                }

                logger.info(f"[DEBUG] Resultado final: {result_data}")

                update_job_status(
                    job_id=job_id,
                    status="completed",
                    message="Códigos de verificação capturados com sucesso",
                    result=result_data
                )
                logger.info(
                    f"[ADSENSE] Códigos de verificação capturados com sucesso para o job {job_id}")
            else:
                update_job_status(
                    job_id=job_id,
                    status="failed",
                    message="Falha ao capturar códigos de verificação",
                    error_details="O processo de captura falhou. Verifique os logs para mais detalhes."
                )
                logger.error(
                    f"[ADSENSE] Falha ao capturar códigos para o job {job_id}")

            # Fechar o navegador se close_browser for True (padrão)
            close_browser = data.get('close_browser', True)
            if close_browser:
                close_browser_safely(adspower_manager, user_id, driver, job_id)
            else:
                logger.info(
                    f"[ADSENSE] Navegador mantido aberto para operações adicionais (close_browser={close_browser})")

        except Exception as e:
            update_job_status(
                job_id=job_id,
                status="failed",
                message=f"Erro durante captura de códigos: {str(e)}",
                error_details=f"Exceção: {type(e).__name__}: {str(e)}"
            )
            logger.error(
                f"[ERRO] Erro ao capturar códigos do AdSense: {str(e)}")

            # Tentar fechar o navegador se close_browser for True (mesmo em caso de erro)
            if close_browser and 'user_id' in locals() and 'adspower_manager' in locals():
                close_browser_safely(adspower_manager, user_id, driver if 'driver' in locals(
                ) else None, job_id, "após erro")

    except Exception as e:
        logger.error(
            f"[ERRO] Erro geral no processamento do job {job_id}: {str(e)}")
        try:
            update_job_status(
                job_id=job_id,
                status="failed",
                message=f"Erro não tratado: {str(e)}",
                error_details=f"Exceção não tratada: {type(e).__name__}: {str(e)}"
            )
        except:
            pass


def close_browser_safely(adspower_manager, user_id, driver, job_id, step=""):
    """
    Fecha o navegador de forma segura, tentando diferentes métodos.

    Args:
        adspower_manager: Instância do AdsPowerManager
        user_id: ID do perfil do AdsPower
        driver: Driver do Selenium (pode ser None)
        job_id: ID do job para logs
        step: Texto adicional para os logs (ex: "após erro")

    Returns:
        bool: True se o navegador foi fechado com sucesso
    """
    success = False
    try:
        logger.info(
            f"[ADSENSE] Tentando fechar o navegador {step} para o job {job_id}")

        # Primeira tentativa: usar o AdsPowerManager
        if adspower_manager and user_id:
            if adspower_manager.close_browser(user_id):
                logger.info(
                    f"[ADSENSE] Navegador fechado com sucesso {step} para o job {job_id}")
                success = True
            else:
                logger.warning(
                    f"[AVISO] AdsPowerManager não conseguiu fechar o navegador, tentando alternativa...")

        # Segunda tentativa: usar driver.quit()
        if not success and driver:
            driver.quit()
            logger.info(
                f"[ADSENSE] Navegador fechado usando driver.quit() {step}")
            success = True

    except Exception as e:
        logger.warning(f"[AVISO] Erro ao fechar navegador {step}: {str(e)}")
        # Última tentativa
        try:
            if driver:
                driver.quit()
                logger.info(
                    f"[ADSENSE] Navegador fechado com driver.quit() após erro {step}")
                success = True
        except Exception as e2:
            logger.error(
                f"[ERRO] Não foi possível fechar o navegador {step}: {str(e2)}")

    return success


def process_adsense_verify_account(job_id, user_id, data):
    """
    Processa a verificação de uma conta AdSense.

    Args:
        job_id: ID único do job
        user_id: ID do perfil do AdsPower a ser utilizado
        data: Dados adicionais para o processo
    """
    try:
        # Configurar o log
        logger.info(f"[ADSENSE] Iniciando verificação para o job {job_id}")

        # Configurações do navegador
        headless = data.get('headless', False)
        max_wait_time = data.get('max_wait_time', 60)
        # Parâmetro para fechar o navegador (padrão: True)
        close_browser = data.get('close_browser', True)

        try:
            # Iniciar o navegador
            update_job_status(
                job_id=job_id,
                status="processing",
                message="Iniciando navegador"
            )

            # Importar as dependências com tratamento de erros
            try:
                from powerads_api.browser_manager import BrowserManager, BrowserConfig
                from powerads_api.ads_power_manager import AdsPowerManager
                from automations.adsense_creator.verify_account import AdSenseAccountVerifier
                logger.info(
                    "[OK] Todas as dependências importadas com sucesso")
            except ImportError as ie:
                error_msg = f"[ERRO] Falha ao importar dependências: {str(ie)}"
                logger.error(error_msg)
                update_job_status(
                    job_id=job_id,
                    status="failed",
                    message=f"Erro ao importar dependências: {str(ie)}",
                    error_details=f"Módulo não encontrado. Verifique se todos os módulos necessários estão instalados e acessíveis."
                )
                return

            # Carregar credenciais
            try:
                # Carregar de credentials.json
                credentials_path = os.path.join(os.path.dirname(
                    os.path.dirname(__file__)), "credentials", "credentials.json")
                if os.path.exists(credentials_path):
                    with open(credentials_path, 'r') as f:
                        credentials = json.load(f)

                    base_url = credentials.get("PA_BASE_URL")
                    api_key = credentials.get("PA_API_KEY")

                    if not base_url or not api_key:
                        update_job_status(
                            job_id=job_id,
                            status="failed",
                            message="Credenciais do AdsPower não encontradas",
                            error_details="As credenciais PA_BASE_URL e/ou PA_API_KEY não foram encontradas."
                        )
                        return

                    logger.info("[OK] Credenciais carregadas com sucesso")
                else:
                    update_job_status(
                        job_id=job_id,
                        status="failed",
                        message="Arquivo de credenciais não encontrado",
                        error_details="O arquivo credentials.json não existe."
                    )
                    return
            except Exception as e:
                update_job_status(
                    job_id=job_id,
                    status="failed",
                    message=f"Erro ao carregar credenciais: {str(e)}",
                    error_details=f"Ocorreu um erro ao carregar as credenciais: {str(e)}"
                )
                return

            # Inicializar o AdsPower e o navegador
            try:
                # Inicializar AdsPowerManager
                adspower_manager = AdsPowerManager(
                    base_url=base_url, api_key=api_key)
                logger.info("[OK] AdsPowerManager inicializado com sucesso")

                # Inicializar BrowserManager e configurar
                browser_manager = BrowserManager(adspower_manager)
                browser_config = BrowserConfig(
                    headless=headless,
                    max_wait_time=max_wait_time
                )
                browser_manager.set_config(browser_config)

                # Verificar se o navegador já está aberto
                browser_info = adspower_manager.get_browser_info(user_id)

                if browser_info and browser_info.get("selenium_ws"):
                    logger.info(
                        f"[INFO] Navegador para perfil {user_id} já está em execução, conectando ao mesmo")
                    # Conectar diretamente ao navegador existente usando AdsPowerManager
                    driver = adspower_manager.connect_selenium(browser_info)
                else:
                    # Se não estiver aberto, iniciar um novo
                    logger.info(
                        f"[INFO] Iniciando um novo navegador para o perfil {user_id}")
                    success, browser_info = browser_manager.start_browser(
                        user_id)

                    if not success or not browser_info:
                        update_job_status(
                            job_id=job_id,
                            status="failed",
                            message="Falha ao iniciar o navegador",
                            error_details="Não foi possível iniciar o navegador. Verifique se o AdsPower está em execução."
                        )
                        return

                    # Conectar ao driver do Selenium usando AdsPowerManager
                    driver = adspower_manager.connect_selenium(browser_info)

                # Verificar se conseguimos obter o driver
                if not driver:
                    update_job_status(
                        job_id=job_id,
                        status="failed",
                        message="Driver do navegador não disponível",
                        error_details="Não foi possível conectar ao driver do navegador. Verifique se o AdsPower está em execução."
                    )
                    return

                # Armazenar informações para fechamento posterior
                driver.adspower_user_id = user_id
                driver.browser_manager = browser_manager

                logger.info("[OK] Conectado ao navegador com sucesso")
            except Exception as e:
                update_job_status(
                    job_id=job_id,
                    status="failed",
                    message=f"Erro ao inicializar navegador: {str(e)}",
                    error_details=f"Erro: {str(e)}"
                )
                return

            # Inicializar o verificador de conta
            verifier = AdSenseAccountVerifier(driver)

            # Obter os parâmetros da requisição
            pub_id = data.get('pub_id')
            site_url = data.get('site_url')

            # Log dos parâmetros recebidos
            logger.info(
                f"[INFO] Parâmetros para verificação - pub_id: {pub_id}, site_url: {site_url}")

            # Executar a verificação
            update_job_status(
                job_id=job_id,
                status="processing",
                message="Executando verificação da conta AdSense"
            )

            # Usar o novo método verify_site com os parâmetros fornecidos
            if pub_id and site_url:
                logger.info(
                    f"[INFO] Iniciando verificação com navegação específica para URL do site {site_url}")
                success = verifier.verify_site(
                    pub_id=pub_id, site_url=site_url)
            else:
                # Possibilitar usar um XPath personalizado como fallback
                xpath = data.get('verification_xpath')
                if xpath:
                    logger.info(f"[INFO] Usando XPath personalizado: {xpath}")
                    success = verifier.click_verification_button(xpath)
                else:
                    # Usar o método padrão que já inclui o XPath
                    logger.info("[INFO] Usando método padrão de verificação")
                    success = verifier.verify_and_close()

            if success:
                update_job_status(
                    job_id=job_id,
                    status="completed",
                    message="Conta AdSense verificada com sucesso",
                    result={
                        "verified": True,
                        "verification_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "pub_id": pub_id,
                        "site_url": site_url
                    }
                )
                logger.info(
                    f"[ADSENSE] Conta verificada com sucesso para o job {job_id}")
            else:
                update_job_status(
                    job_id=job_id,
                    status="failed",
                    message="Falha ao verificar conta AdSense",
                    error_details="O processo de verificação falhou. Verifique os logs para mais detalhes."
                )
                logger.error(
                    f"[ADSENSE] Falha ao verificar conta para o job {job_id}")

            # Fechar o navegador se close_browser for True (padrão)
            if close_browser:
                close_browser_safely(adspower_manager, user_id, driver, job_id)
            else:
                logger.info(
                    f"[ADSENSE] Navegador mantido aberto para operações adicionais (close_browser={close_browser})")

        except Exception as e:
            update_job_status(
                job_id=job_id,
                status="failed",
                message=f"Erro durante verificação da conta: {str(e)}",
                error_details=f"Exceção: {type(e).__name__}: {str(e)}"
            )
            logger.error(f"[ERRO] Erro ao verificar conta AdSense: {str(e)}")

            # Tentar fechar o navegador se close_browser for True (mesmo em caso de erro)
            if close_browser and 'user_id' in locals() and 'adspower_manager' in locals():
                close_browser_safely(adspower_manager, user_id, driver if 'driver' in locals(
                ) else None, job_id, "após erro")

    except Exception as e:
        logger.error(
            f"[ERRO] Erro geral no processamento do job {job_id}: {str(e)}")
        try:
            update_job_status(
                job_id=job_id,
                status="failed",
                message=f"Erro não tratado: {str(e)}",
                error_details=f"Exceção não tratada: {type(e).__name__}: {str(e)}"
            )
        except:
            pass


@app.post("/adsense-verify-account/{user_id}")
async def verify_adsense_account(user_id: str, data: dict = None):
    """
    Endpoint para verificar uma conta AdSense, clicando no botão de verificação.
    Este endpoint deve ser chamado após a criação e configuração da conta AdSense.

    Parâmetros:
    - user_id: ID do perfil do AdsPower a ser utilizado

    Corpo da requisição (JSON):
    {
        "pub_id": "5586201132431151",        # ID do publisher (sem 'pub-')
        "site_url": "fulled.com.br",         # URL do site a ser verificado
        "headless": false,                    # opcional - executar em modo headless
        "verification_xpath": "xpath_string", # opcional - XPath personalizado para o botão de verificação (usado apenas se pub_id e site_url não forem fornecidos)
        "max_wait_time": 60,                  # opcional - tempo máximo de espera em segundos
        "close_browser": false                # opcional - fechar o navegador após a operação (padrão: true)
    }

    Resposta:
    {
        "success": true,
        "job_id": "job-uuid",
        "status": "pending",
        "message": "Processo de verificação de conta iniciado"
    }
    """
    try:
        # Verificar se o perfil existe
        if not user_id:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "ID do perfil não fornecido",
                    "error_code": "MISSING_USER_ID"
                }
            )

        # Garantir que data seja um dicionário válido
        if data is None:
            data = {}

        # Gerar um job_id único
        job_id = str(uuid.uuid4())

        # Criar dados do job
        job_data = {
            "job_id": job_id,
            "user_id": user_id,
            "status": "pending",
            "created_at": time.time(),
            "pub_id": data.get('pub_id'),  # Novo campo
            "site_url": data.get('site_url'),  # Novo campo
            "headless": data.get('headless', False),
            "verification_xpath": data.get('verification_xpath'),
            "max_wait_time": data.get('max_wait_time', 60),
            # Novo campo para controlar o fechamento do navegador (padrão: true)
            "close_browser": data.get('close_browser', True),
            "message": "Processo de verificação de conta AdSense iniciado"
        }

        # Adicionar um log para verificar os dados recebidos
        logger.info(
            f"[ADSENSE] Dados recebidos para verificação de conta: pub_id={data.get('pub_id')}, site_url={data.get('site_url')}, close_browser={data.get('close_browser', True)}")

        # Salvar dados do job em arquivo
        job_file = os.path.join(JOBS_DIR, f"{job_id}.json")
        with open(job_file, "w") as f:
            json.dump(job_data, f, indent=4)

        # Iniciar processo em uma thread separada
        Thread(
            target=process_adsense_verify_account,
            args=(job_id, user_id, data),
            daemon=True
        ).start()

        logger.info(
            f"[ADSENSE] Job {job_id} iniciado para verificação de conta AdSense no perfil {user_id}")

        return {
            "success": True,
            "job_id": job_id,
            "user_id": user_id,
            "status": "pending",
            "message": "Processo de verificação de conta AdSense iniciado",
            "status_url": f"/adsense-job-status/{job_id}"
        }

    except Exception as e:
        logger.error(
            f"[ERRO] Erro ao iniciar verificação de conta AdSense: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "error_code": "ADSENSE_VERIFY_ACCOUNT_ERROR"
            }
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)
