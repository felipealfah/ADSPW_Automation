import requests
import logging
import time
from typing import Optional, Dict, Any

def make_request(method: str, url: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]] = None, max_retries: int = 3, retry_delay: int = 2, timeout: int = 20) -> Dict[str, Any]:
    """
    Função genérica para realizar requisições HTTP com retry mechanism.

    Args:
        method: Método HTTP (GET, POST, PUT, DELETE)
        url: URL da requisição
        headers: Headers da requisição
        payload: Dados da requisição (opcional)
        max_retries: Número máximo de tentativas
        retry_delay: Tempo de espera entre tentativas em segundos
        timeout: Timeout da requisição em segundos

    Returns:
        Dict[str, Any]: Resposta da requisição em formato JSON ou dicionário com erro
    """
    for attempt in range(max_retries):
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, params=payload, timeout=timeout)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=payload, timeout=timeout)
            elif method == "PUT":
                response = requests.put(url, headers=headers, json=payload, timeout=timeout)
            elif method == "DELETE":
                response = requests.delete(url, headers=headers, json=payload, timeout=timeout)
            else:
                raise ValueError(f"Método HTTP inválido: {method}")

            # Levantar exceções para status HTTP de erro
            response.raise_for_status()

            # Tentar converter resposta para JSON
            try:
                return response.json()
            except ValueError as e:
                logging.error(f"Erro ao converter resposta para JSON: {e}")
                return {"error": "Invalid JSON response", "details": str(e)}

        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                logging.warning(f"Tentativa {attempt + 1} falhou para {url}: {e}")
                time.sleep(retry_delay)
                continue
            else:
                logging.error(f"Todas as tentativas falharam para {url}: {e}")
                return {"error": str(e)}
        except ValueError as e:
            logging.error(f"Erro de valor: {e}")
            return {"error": str(e)}

    return {"error": f"Falha após {max_retries} tentativas"}
