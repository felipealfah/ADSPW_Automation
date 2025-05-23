#!/usr/bin/env bash
set -e

# Caminho para o diretório da aplicação
cd "$(dirname "$0")/automation_py"

# Limpar caches e logs
echo "Clearing caches and logs..."
rm -f credentials/adspower_cache.json
rm -f server.log
rm -f logs/*.log
find . -type d -name "__pycache__" -exec rm -rf {} +

# Iniciar o projeto
echo "Starting project..."
if [ -f .venv/bin/activate ]; then
    echo "Activating virtual environment"
    source .venv/bin/activate
fi
exec python3 run.py 