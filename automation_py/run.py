import subprocess
import os
import sys
import time
import signal
import platform
import threading
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Saída para o console
        logging.FileHandler("sms_gateway.log")  # Arquivo de log
    ]
)
logger = logging.getLogger(__name__)

# Armazenar os processos para encerramento adequado
processes = []


def clear_screen():
    """Limpa a tela do terminal."""
    if platform.system() == "Windows":
        os.system("cls")
    else:
        os.system("clear")


def stream_output(process, prefix):
    """Lê a saída de um processo e a exibe no console com um prefixo."""
    for line in iter(process.stdout.readline, b''):
        print(f"{prefix}: {line.decode('utf-8', errors='replace').strip()}")


def shutdown_handler(signum=None, frame=None):
    """Manipulador para encerrar todos os processos."""
    print("\n[PARADA] Encerrando serviços...")

    for name, process in processes:
        if process.poll() is None:  # Se o processo ainda estiver em execução
            print(f"  - Encerrando {name}...")
            if platform.system() == "Windows":
                subprocess.call(
                    ['taskkill', '/F', '/T', '/PID', str(process.pid)])
            else:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()  # Força o encerramento se demorar demais

    print("[OK] Todos os serviços foram encerrados.")
    sys.exit(0)


def main():
    """Função principal para executar os serviços."""
    global processes

    clear_screen()
    print("=" * 60)
    print("[INICIO] INICIANDO SERVIÇOS API & UI [INICIO]")
    print("=" * 60)

    # Configurar tratamento de sinal para encerramento limpo
    try:
        if platform.system() != "Windows":
            signal.signal(signal.SIGINT, shutdown_handler)
            signal.signal(signal.SIGTERM, shutdown_handler)
    except (AttributeError, ValueError):
        pass  # Ignorar erros em sistemas que não suportam sinais

    # Iniciar o servidor FastAPI com uvicorn
    print(" Iniciando servidor FastAPI...")
    api_cmd = ["uvicorn", "webhooks.server:app",
               "--host", "0.0.0.0", "--port", "5001", "--reload"]

    try:
        api_process = subprocess.Popen(
            api_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=False,
            bufsize=1
        )
        processes.append(("api", api_process))

        # Criar thread para mostrar a saída da API
        api_thread = threading.Thread(
            target=stream_output,
            args=(api_process, "API"),
            daemon=True
        )
        api_thread.start()

        # Aguardar um pouco para a API iniciar
        print(" Aguardando inicialização da API...")
        time.sleep(3)

        # Iniciar o Streamlit
        print(" Iniciando aplicação Streamlit...")
        streamlit_app = os.path.join("ui", "app.py")
        streamlit_cmd = ["streamlit", "run", streamlit_app]

        streamlit_process = subprocess.Popen(
            streamlit_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=False,
            bufsize=1
        )
        processes.append(("streamlit", streamlit_process))

        # Criar thread para mostrar a saída do Streamlit
        streamlit_thread = threading.Thread(
            target=stream_output,
            args=(streamlit_process, "STREAMLIT"),
            daemon=True
        )
        streamlit_thread.start()

        print("\n[OK] Todos os serviços foram iniciados!")
        print("-" * 60)
        print("[CLIPBOARD] Instruções:")
        print("  - API FastAPI disponível em: http://localhost:5001")
        print("  - Documentação Swagger UI: http://localhost:5001/docs")
        print("  - Documentação ReDoc: http://localhost:5001/redoc")
        print("  - Os logs dos serviços são mostrados acima com prefixos")
        print("  - Pressione Ctrl+C para encerrar todos os serviços")
        print("-" * 60)

        try:
            # Manter o script principal em execução até Ctrl+C
            while all(process.poll() is None for name, process in processes):
                time.sleep(1)

            # Se chegou aqui, um dos processos terminou
            for name, process in processes:
                if process.poll() is not None:
                    print(
                        f"[AVISO] O serviço {name} foi encerrado inesperadamente.")

            # Encerrar os outros processos também
            shutdown_handler()

        except KeyboardInterrupt:
            # Encerrar processos ao receber Ctrl+C
            shutdown_handler()

    except Exception as e:
        logger.error(f"Erro ao iniciar os serviços: {str(e)}")
        print(f"[ERRO] Erro ao iniciar os serviços: {str(e)}")
        shutdown_handler()


if __name__ == "__main__":
    main()
