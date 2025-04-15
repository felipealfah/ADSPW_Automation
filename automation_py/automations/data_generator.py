import random
import json
import os
from faker import Faker
import calendar

# Criar instância do Faker para dados fictícios
fake = Faker()

# Caminho do arquivo JSON para armazenar credenciais
CREDENTIALS_PATH = "credentials/gmail.json"

# Criar pasta credenciais se não existir
os.makedirs(os.path.dirname(CREDENTIALS_PATH), exist_ok=True)

def generate_first_name():
    """Gera um primeiro nome aleatório"""
    return fake.first_name()

def generate_last_name():
    """Gera um sobrenome aleatório"""
    return fake.last_name()

def generate_birth_date():
    """Gera uma data de nascimento aleatória"""
    birth_month = random.choice(["January", "February", "March", "April", "May", "June",
                                 "July", "August", "September", "October", "November", "December"])
    birth_day = random.randint(1, 28)  # Evita problemas com fevereiro
    birth_year = random.randint(1985, 2005)  # Faixa de idade válida para Gmail
    return birth_month, birth_day, birth_year

def generate_username(first_name, last_name, birth_month, birth_year):
    """Gera um nome de usuário baseado no nome, sobrenome e ano de nascimento"""
    month_number = str(list(calendar.month_name).index(birth_month)).zfill(2)
    username = f"{first_name.lower()}{last_name.lower()}{month_number}{birth_year}"
    return username

def generate_password():
    """Gera uma senha aleatória segura"""
    return fake.password(length=12, special_chars=True, digits=True, upper_case=True, lower_case=True)

def save_credentials(credentials):
    """Salva as credenciais em um arquivo JSON"""
    try:
        if os.path.exists(CREDENTIALS_PATH):
            with open(CREDENTIALS_PATH, "r") as file:
                existing_data = json.load(file)
        else:
            existing_data = []

        existing_data.append(credentials)

        with open(CREDENTIALS_PATH, "w") as file:
            json.dump(existing_data, file, indent=4)
    except Exception as e:
        print(f"❌ Erro ao salvar credenciais: {e}")

def generate_gmail_credentials():
    """Gera todas as credenciais para criar uma conta no Gmail"""
    first_name = generate_first_name()
    last_name = generate_last_name()
    birth_month, birth_day, birth_year = generate_birth_date()
    username = generate_username(first_name, last_name, birth_month, birth_year)
    password = generate_password()

    credentials = {
        "first_name": first_name,
        "last_name": last_name,
        "birth_month": birth_month,
        "birth_day": birth_day,
        "birth_year": birth_year,
        "username": username,
        "password": password
    }
    
    return credentials

def save_gmail_account(email, password, phone_number, profile_name, account_data=None):
    """
    Salva as credenciais de uma conta Gmail no JSON evitando duplicações.
    Esta função só deve ser chamada após a verificação bem-sucedida do SMS.
    
    Args:
        email (str): Email da conta
        password (str): Senha da conta
        phone_number (str): Número de telefone verificado via SMS
        profile_name (str): Nome do perfil no AdsPower
        account_data (dict, optional): Dados adicionais da conta, incluindo 
                                       country_code, country_name e activation_id
    
    Returns:
        bool: True se as credenciais foram salvas, False caso contrário
    """
    credentials_path = "credentials/gmail.json"
    
    try:
        # Verifica se o arquivo já existe e carrega os dados
        existing_data = []
        if os.path.exists(credentials_path):
            with open(credentials_path, "r") as file:
                try:
                    existing_data = json.load(file)
                    if not isinstance(existing_data, list):
                        existing_data = []
                except json.JSONDecodeError:
                    # Se o arquivo estiver corrompido, começamos com lista vazia
                    existing_data = []
        
        # Criar nova entrada de credenciais com dados básicos
        new_entry = {
            "email": email,
            "password": password,
            "phone": phone_number,
            "profile": profile_name
        }
        
        # Adicionar dados complementares se disponíveis
        if account_data and isinstance(account_data, dict):
            # Adicionar todos os campos extras que possam existir
            for key, value in account_data.items():
                if key not in new_entry:  # Não sobrescrever campos existentes
                    new_entry[key] = value
        
        # Verificar se o email já existe na lista
        # Usamos uma lista de índices a serem removidos para não modificar a lista durante iteração
        indices_to_remove = []
        
        for i, entry in enumerate(existing_data):
            if entry.get("email") == email:
                indices_to_remove.append(i)
                logging.info(f"Encontrada entrada duplicada para {email}. Será substituída.")
        
        # Remover as entradas duplicadas (do final para o começo para não afetar índices)
        for index in sorted(indices_to_remove, reverse=True):
            existing_data.pop(index)
        
        # Adicionar nova entrada
        existing_data.append(new_entry)
        
        # Salvar lista atualizada no arquivo JSON
        with open(credentials_path, "w") as file:
            json.dump(existing_data, file, indent=4)
        
        logging.info(f"Credenciais para {email} salvas com sucesso em {credentials_path}")
        return True
    
    except Exception as e:
        logging.error(f"Erro ao salvar credenciais: {e}")
        return False

