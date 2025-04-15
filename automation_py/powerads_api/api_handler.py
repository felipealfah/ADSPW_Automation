import requests
import logging

def make_request(method, url, headers, payload=None):
    """Função genérica para realizar requisições HTTP."""
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, params=payload)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=payload)
        elif method == "PUT":
            response = requests.put(url, headers=headers, json=payload)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers, json=payload)
        else:
            raise ValueError(f"Método HTTP inválido: {method}")

        # Levantar exceções para status HTTP de erro
        response.raise_for_status()

        # Retornar JSON da resposta
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Erro ao fazer requisição para {url}: {e}")
        return {"error": str(e)}  # Retornar erro em formato de dicionário
    except ValueError as e:
        logging.error(f"Erro de valor: {e}")
        return {"error": str(e)}
