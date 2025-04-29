#!/usr/bin/env python3
# remove_emojis.py - Script para remover emojis de arquivos Python

import os
import re
import sys
from pathlib import Path

# Padrão regex para detectar emojis e outros caracteres não-ASCII
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # símbolos & pictogramas
    "\U0001F680-\U0001F6FF"  # transporte & símbolos de mapa
    "\U0001F700-\U0001F77F"  # símbolos alquímicos
    "\U0001F780-\U0001F7FF"  # símbolos geométricos
    "\U0001F800-\U0001F8FF"  # símbolos suplementares
    "\U0001F900-\U0001F9FF"  # símbolos suplementares
    "\U0001FA00-\U0001FA6F"  # símbolos de xadrez
    "\U0001FA70-\U0001FAFF"  # símbolos suplementares
    "\U00002702-\U000027B0"  # dingbats
    "\U000024C2-\U0001F251"
    "\u200d"  # ZWJ (zero width joiner)
    "\u200b"  # ZWSP (zero width space)
    "\u2B50"  # estrela
    "\u2728"  # brilho
    "\u274C"  # x
    "\u274E"  # x negativo
    "\u2705"  # check
    "\u2757"  # exclamação
    "\u2714"  # check
    "\u2716"  # x pesado
    "\u267B"  # reciclar
    "\u23F0"  # relógio
    "\u23F3"  # ampulheta
    "\u26A0"  # aviso
    "\u2139"  # informação
    "]+"
)

# Mapeamento de substituição para emojis comuns em código Python
EMOJI_REPLACEMENTS = {
    "[OK]": "[OK]",
    "[ERRO]": "[ERRO]",
    "[AVISO]": "[AVISO]",
    "[INICIO]": "[INICIO]",
    "[TELEFONE]": "[TELEFONE]",
    "[ATUALIZANDO]": "[ATUALIZANDO]",
    "[PARADA]": "[PARADA]",
    "[ALERTA]": "[ALERTA]",
    "[SALVO]": "[SALVO]",
    "[PROIBIDO]": "[PROIBIDO]",
    "[BUSCA]": "[BUSCA]",
    "[GRAFICO]": "[GRAFICO]",
    "[CLIPBOARD]": "[CLIPBOARD]",
    "[SEGURANCA]": "[SEGURANCA]",
    "[LINK]": "[LINK]",
    "[DOWNLOAD]": "[DOWNLOAD]",
    "[UPLOAD]": "[UPLOAD]",
    "[TEMPO]": "[TEMPO]",
    "[NOTIFICACAO]": "[NOTIFICACAO]",
    "[EMOJI]": ""
}


def should_process_file(path):
    """Verifica se o arquivo deve ser processado."""
    # Ignora diretórios de ambientes virtuais, __pycache__, e .git
    ignore_dirs = ['venv', 'env', '__pycache__', '.git', 'node_modules']
    for ignore_dir in ignore_dirs:
        if f'/{ignore_dir}/' in str(path) or str(path).startswith(f'{ignore_dir}/'):
            return False

    # Processa apenas arquivos Python e arquivos de configuração comuns
    extensions = ['.py', '.json', '.yml',
                  '.yaml', '.md', '.txt', '.bat', '.sh']
    return path.suffix in extensions


def replace_emoji_with_text(match):
    """Substitui um emoji encontrado pelo seu equivalente em texto."""
    emoji = match.group(0)
    return EMOJI_REPLACEMENTS.get(emoji, "")


def remove_emojis(content):
    """Remove emojis do conteúdo de um arquivo."""
    # Primeiro tenta substituir por equivalente em texto, se houver
    for emoji, text in EMOJI_REPLACEMENTS.items():
        content = content.replace(emoji, text)

    # Então remove quaisquer outros emojis restantes
    content = EMOJI_PATTERN.sub("", content)
    return content


def process_file(file_path):
    """Processa um arquivo, removendo emojis."""
    try:
        # Tentar ler o arquivo como UTF-8
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
    except UnicodeDecodeError:
        # Se falhar, tentar outras codificações comuns
        try:
            with open(file_path, 'r', encoding='latin-1') as file:
                content = file.read()
        except Exception as e:
            print(f"[AVISO] Não foi possível ler {file_path}: {e}")
            return False

    # Verificar se há emojis a serem removidos
    cleaned_content = remove_emojis(content)

    if content != cleaned_content:
        try:
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(cleaned_content)
            print(f" Emojis removidos de {file_path}")
            return True
        except Exception as e:
            print(f"[AVISO] Erro ao salvar {file_path}: {e}")
            return False
    return False


def main():
    """Função principal para processar todos os arquivos."""
    root_dir = '.'
    if len(sys.argv) > 1:
        root_dir = sys.argv[1]

    print(f"Processando arquivos em {os.path.abspath(root_dir)}...")

    total_files = 0
    cleaned_files = 0

    for root, dirs, files in os.walk(root_dir):
        for file in files:
            file_path = Path(os.path.join(root, file))
            if should_process_file(file_path):
                total_files += 1
                if process_file(file_path):
                    cleaned_files += 1

    print(f"\nProcessamento concluído!")
    print(f"Total de arquivos verificados: {total_files}")
    print(f"Arquivos com emojis removidos: {cleaned_files}")


if __name__ == "__main__":
    main()
