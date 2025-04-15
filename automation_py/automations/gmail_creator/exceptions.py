class GmailCreatorException(Exception):
    """Exceção base para todas as exceções do GmailCreator."""
    pass

class AccountSetupError(GmailCreatorException):
    """Exceções relacionadas à configuração inicial da conta."""
    pass

class UsernameError(AccountSetupError):
    """Exceções relacionadas ao username."""
    def __init__(self, message="Erro ao configurar username", attempts=None):
        self.attempts = attempts
        if attempts:
            message = f"{message} após {attempts} tentativas"
        super().__init__(message)

class PhoneVerificationError(GmailCreatorException):
    """Exceções relacionadas à verificação de telefone."""
    pass

class SMSServiceError(PhoneVerificationError):
    """Erros específicos do serviço de SMS."""
    def __init__(self, message, country=None, service=None):
        self.country = country
        self.service = service
        details = f" (País: {country}, Serviço: {service})" if country and service else ""
        super().__init__(f"{message}{details}")

class InsufficientBalanceError(SMSServiceError):
    """Erro de saldo insuficiente na API de SMS."""
    def __init__(self, balance=None):
        message = f"Saldo insuficiente na API SMS. Saldo atual: {balance} RUB" if balance is not None else "Saldo insuficiente na API SMS"
        super().__init__(message)

class NoPhoneNumbersAvailable(SMSServiceError):
    """Erro quando não há números disponíveis."""
    pass

class SMSCodeError(PhoneVerificationError):
    """Erros relacionados ao código SMS."""
    def __init__(self, message, attempts=None):
        if attempts:
            message = f"{message} após {attempts} tentativas"
        super().__init__(message)

class TermsAcceptanceError(GmailCreatorException):
    """Erro ao aceitar os termos de uso."""
    pass

class NavigationError(GmailCreatorException):
    """Erros de navegação e timeout."""
    def __init__(self, url=None, element=None, timeout=None):
        details = []
        if url:
            details.append(f"URL: {url}")
        if element:
            details.append(f"Elemento: {element}")
        if timeout:
            details.append(f"Timeout: {timeout}s")
            
        message = "Erro de navegação"
        if details:
            message += f" ({', '.join(details)})"
        super().__init__(message)

class AccountCreationFailed(GmailCreatorException):
    """Erro final quando a conta não pode ser criada."""
    def __init__(self, stage=None, reason=None):
        message = "Falha na criação da conta"
        if stage:
            message += f" durante {stage}"
        if reason:
            message += f": {reason}"
        super().__init__(message)

class ElementInteractionError(GmailCreatorException):
    """Erros de interação com elementos da página."""
    def __init__(self, element_type, action, details=None):
        message = f"Erro ao {action} {element_type}"
        if details:
            message += f": {details}"
        super().__init__(message)

class GmailCreationError(Exception):
    """Erro genérico para falhas na criação de conta Gmail."""
    def __init__(self, message="Erro na criação da conta Gmail"):
        self.message = message
        super().__init__(self.message)

class AccountVerificationError(Exception):
    """Erro durante a verificação da conta."""
    def __init__(self, message="Erro ao verificar a conta"):
        self.message = message
        super().__init__(self.message)

