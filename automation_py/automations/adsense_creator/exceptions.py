class AdSenseCreationError(Exception):
    """Erro geral durante a criação da conta AdSense."""
    pass


class AccountSetupError(AdSenseCreationError):
    """Erro durante a configuração inicial da conta."""
    pass


class LoginError(AdSenseCreationError):
    """Erro durante o login na conta Google."""
    pass


class WebsiteVerificationError(AdSenseCreationError):
    """Erro durante a verificação do site."""
    pass


class PaymentSetupError(AdSenseCreationError):
    """Erro durante a configuração do pagamento."""
    pass


class ElementInteractionError(AdSenseCreationError):
    """Erro durante interação com elementos da página."""
    pass


class NavigationError(AdSenseCreationError):
    """Erro durante navegação entre páginas."""
    pass


class TimeoutError(AdSenseCreationError):
    """Erro devido a timeout durante operação."""
    pass


class ValidationError(AdSenseCreationError):
    """Erro durante a validação de dados ou formulários."""
    pass


class AccountReviewError(AdSenseCreationError):
    """Erro durante o processo de revisão da conta."""
    pass
