from automations.gmail_creator.core import GmailCreator
from credentials.credentials_manager import get_credential
from powerads_api.profiles import ProfileManager, get_profiles
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
    phone_params: Optional[PhoneParams] = None
    headless: Optional[bool] = False
    max_wait_time: Optional[int] = 60
    webhook_callback: Optional[str] = None


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


def process_gmail_creation(job_id: str, user_id: str):
    """
    Processa a criação de uma conta Gmail em background.

    Args:
        job_id: ID do job
        user_id: ID do usuário solicitando a criação
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

        # Carregar credenciais
        credentials = load_credentials()
        if not credentials:
            raise ValueError("Credenciais não encontradas")

        # Verificar se perfil existe
        profile_manager = ProfileManager()
        profile = profile_manager.get_profile_by_id(user_id)
        if not profile:
            raise ValueError(f"Perfil {user_id} não encontrado")

        # Inicializar componentes
        gmail_creator = GmailCreator(
            profile_id=user_id,
            credentials=credentials
        )

        # Criar conta
        result = gmail_creator.create_account()

        # Atualizar status com sucesso
        update_job_status(
            job_id=job_id,
            status="completed",
            message="Conta criada com sucesso",
            result=result
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
        else:
            job_data = {"id": job_id}

        # Atualizar dados
        job_data.update({
            "status": status,
            "message": message,
            "updated_at": datetime.now().isoformat()
        })

        if result:
            job_data["result"] = result

        if error_details:
            job_data["error"] = error_details

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


class AdsPowerManager:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def check_api_health(self, force_check: bool = False) -> bool:
        """
        Verifica se a API do AdsPower está respondendo.

        Args:
            force_check: Se True, força uma nova verificação ignorando cache

        Returns:
            bool: True se a API está respondendo, False caso contrário
        """
        try:
            # Endpoint para listar grupos (endpoint leve para verificação)
            url = f"{self.base_url}/api/v1/group/list"

            response = requests.get(
                url,
                headers=self.headers,
                timeout=10
            )

            return response.status_code == 200

        except Exception as e:
            logger.error(
                f"[ERRO] Erro ao verificar saúde do AdsPower: {str(e)}")
            return False


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)
