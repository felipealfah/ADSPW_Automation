from automations.adsense_creator import AdSenseCreator
from powerads_api.browser_manager import BrowserManager
import logging
import time
import sys
import os
import json

# Configurar o logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/adsense_automation.log")
    ]
)

# Adicionar o diretório raiz ao path para importação
sys.path.append(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../..")))

# Importar as classes necessárias


def main():
    """Função principal para demonstrar o uso da automação completa."""
    try:
        # Configurar o gerenciador de browser
        browser_manager = BrowserManager()

        # Dados da conta para a automação
        account_data = {
            "email": "seu.email@gmail.com",  # Email da conta Google
            "website_url": "https://seusite.com",  # URL do site para AdSense
            "country": "Brasil",  # País/território
            "capture_codes": True,  # Capturar códigos de verificação
            "verify_website": False,  # Não implementar verificação do site ainda
            "setup_payment": False,  # Não configurar pagamento ainda
            "wait_for_review": False,  # Não aguardar revisão
            "close_browser_on_finish": False  # Manter o navegador aberto ao finalizar
        }

        # ID do perfil do AdsPower
        user_id = "seu_id_do_adspower"  # Substitua pelo ID real

        # Criar instância do AdSenseCreator
        adsense_creator = AdSenseCreator(browser_manager, account_data)

        # Executar a automação
        success, result_data = adsense_creator.create_account(user_id)

        # Verificar o resultado
        if success:
            print("\n=== AUTOMAÇÃO CONCLUÍDA COM SUCESSO ===")
            print(
                f"Publisher ID: {result_data.get('publisher_id', 'Não capturado')}")
            print(
                f"Código de Verificação: {result_data.get('verification_code', 'Não capturado')}")

            # Salvar os resultados em um arquivo JSON
            with open("data/adsense_result.json", "w", encoding="utf-8") as f:
                json.dump(result_data, f, ensure_ascii=False, indent=2)
                print(f"\nResultados salvos em: data/adsense_result.json")
        else:
            print("\n=== FALHA NA AUTOMAÇÃO ===")
            print(f"Erro: {result_data.get('error', 'Erro desconhecido')}")

    except Exception as e:
        print(f"\n=== ERRO INESPERADO ===\n{str(e)}")
        return False

    return True


if __name__ == "__main__":
    # Criar diretórios necessários
    os.makedirs("logs", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    os.makedirs("screenshots", exist_ok=True)

    # Executar a automação
    main()
