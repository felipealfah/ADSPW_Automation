# teste.py - Script para testar a API SMS e PhoneManager sem efetuar compras

import sys
import os
import logging
import json
from apis.sms_api import SMSAPI
from apis.phone_manager import PhoneManager

# Configurar logging para o terminal
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def salvar_resultado(nome_teste, resultado):
    """Salva o resultado de um teste em arquivo JSON para análise posterior"""
    os.makedirs("resultados_testes", exist_ok=True)
    caminho = f"resultados_testes/{nome_teste}.json"
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)
    logger.info(f"✅ Resultado salvo em {caminho}")

def teste_precos_multi_servico():
    """Testa preços para múltiplos serviços sem comprar número"""
    logger.info("🔍 TESTE 1: Consultando preços para serviços múltiplos")
    
    sms_api = SMSAPI()
    
    # Lista de serviços para testar
    combinacoes_servicos = [
        ["go"],                  # Apenas Gmail
        ["go", "tk"],            # Gmail + TikTok
        ["go", "ig"],            # Gmail + Instagram
        ["go", "tk", "ig"],      # Gmail + TikTok + Instagram
        ["go", "vk", "ig", "fb"] # Gmail + VK + Instagram + Facebook
    ]
    
    resultados = {}
    
    # Verificar saldo
    saldo = sms_api.get_balance()
    resultados["saldo"] = saldo
    
    # Testar cada combinação de serviços
    for servicos in combinacoes_servicos:
        servicos_str = "+".join(servicos)
        logger.info(f"\n📱 Testando combinação: {servicos_str}")
        
        # Obter preços para cada serviço individualmente para comparação
        precos_individuais = {}
        for servico in servicos:
            precos_paises = sms_api.compare_prices_in_selected_countries(servico)
            # Filtrar apenas Brasil
            brasil_info = next((p for p in precos_paises if p.get("country_code") == "73"), None)
            if brasil_info:
                precos_individuais[servico] = brasil_info
        
        # Armazenar resultados
        resultados[servicos_str] = {
            "servicos": servicos,
            "precos_individuais": precos_individuais,
            # Soma dos preços individuais para comparação
            "soma_precos": sum(p.get("price", 0) for p in precos_individuais.values())
        }
    
    # Salvar resultados
    salvar_resultado("precos_multi_servico", resultados)
    logger.info("✅ Teste de preços multi-serviço concluído")
    return resultados

def teste_operadoras_brasil():
    """Simula verificação de disponibilidade por operadoras no Brasil"""
    logger.info("\n🔍 TESTE 2: Simulando verificação de operadoras no Brasil")
    
    phone_manager = PhoneManager()
    
    # Combinações de serviços para testar
    combinacoes = [
        ["go"],
        ["go", "tk"],
        ["go", "ig"]
    ]
    
    # Operadoras brasileiras
    operadoras = ["claro", "vivo", "tim", "oi"]
    
    resultados = {}
    
    for servicos in combinacoes:
        servicos_str = "+".join(servicos)
        logger.info(f"\n📱 Testando combinação de serviços: {servicos_str}")
        
        # Verificar disponibilidade geral no Brasil
        disponibilidade_geral = {}
        for servico in servicos:
            disponibilidade = phone_manager.get_number_status("73", servico)
            disponibilidade_geral[servico] = disponibilidade
            logger.info(f"  - {servico}: {disponibilidade} números disponíveis")
        
        # Simular verificação por operadora (como a API não suporta, apenas emulamos)
        info_operadoras = {}
        for operadora in operadoras:
            logger.info(f"  📡 Operadora {operadora.upper()}: Simulando verificação")
            # Aqui poderia fazer uma chamada real se a API permitisse
            info_operadoras[operadora] = {
                "disponivel": disponibilidade_geral.get(servicos[0], 0) > 0,
                "nota": "Informação simulada pois a API não suporta verificação por operadora"
            }
        
        resultados[servicos_str] = {
            "servicos": servicos,
            "disponibilidade_geral": disponibilidade_geral,
            "operadoras": info_operadoras
        }
    
    # Salvar resultados
    salvar_resultado("operadoras_brasil", resultados)
    logger.info("✅ Teste de operadoras concluído")
    return resultados

def teste_preco_maximo():
    """Testa diferentes faixas de preço máximo para avaliar disponibilidade"""
    logger.info("\n🔍 TESTE 3: Avaliando diferentes faixas de preço máximo")
    
    sms_api = SMSAPI()
    
    # Combinação fixa de serviços para teste
    servicos = ["go", "ig"]
    servicos_str = "+".join(servicos)
    
    # Faixas de preço para testar
    faixas_preco = [5, 10, 15, 20, 25, 30]
    
    resultados = {}
    
    # Obter preços atuais do Brasil para referência
    precos_brasil = []
    for servico in servicos:
        precos_paises = sms_api.compare_prices_in_selected_countries(servico)
        brasil_info = next((p for p in precos_paises if p.get("country_code") == "73"), None)
        if brasil_info:
            precos_brasil.append({
                "servico": servico,
                "preco": brasil_info.get("price", 0),
                "disponivel": brasil_info.get("available", 0)
            })
    
    resultados["precos_atuais"] = precos_brasil
    resultados["preco_total_atual"] = sum(p.get("preco", 0) for p in precos_brasil)
    
    # Analisar diferentes faixas de preço
    analise_faixas = {}
    for preco_max in faixas_preco:
        logger.info(f"  💰 Avaliando preço máximo: {preco_max} RUB")
        # Aqui faríamos uma verificação real se a API permitisse consulta por preço máximo
        # Como não podemos sem comprar, apenas simulamos a lógica
        
        seria_possivel = preco_max >= resultados["preco_total_atual"]
        analise_faixas[preco_max] = {
            "preco_maximo": preco_max,
            "seria_possivel": seria_possivel,
            "nota": f"{'Provavelmente disponível' if seria_possivel else 'Provavelmente indisponível'} baseado nos preços individuais",
            "recomendacao": "Para maior chance de sucesso, defina um preço máximo pelo menos 20% acima da soma dos preços individuais."
        }
    
    resultados["analise_faixas"] = analise_faixas
    resultados["recomendacao_geral"] = {
        "preco_recomendado": round(resultados["preco_total_atual"] * 1.2, 2),
        "explicacao": "Preço 20% acima da soma dos preços individuais para garantir disponibilidade"
    }
    
    # Salvar resultados
    salvar_resultado("preco_maximo", resultados)
    logger.info("✅ Teste de preço máximo concluído")
    return resultados

def main():
    logger.info("🚀 Iniciando testes da API SMS-Activate (apenas consultas, sem compras)")
    
    try:
        # Executar todos os testes
        teste_precos_multi_servico()
        teste_operadoras_brasil()
        teste_preco_maximo()
        
        logger.info("\n✅ Todos os testes foram concluídos com sucesso!")
        logger.info("📊 Os resultados foram salvos na pasta 'resultados_testes'")
        
    except Exception as e:
        logger.error(f"❌ Erro durante os testes: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())