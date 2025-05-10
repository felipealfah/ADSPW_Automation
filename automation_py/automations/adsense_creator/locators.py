from dataclasses import dataclass, field
from typing import List


@dataclass
class LoginLocators:
    """XPaths para os elementos da tela de login do Google."""
    EMAIL_FIELD = "//input[@type='email']"
    PASSWORD_FIELD = "//input[@type='password']"
    NEXT_BUTTON = "//button[contains(., 'Next') or contains(., 'Próximo') or contains(., 'Avançar')]"
    USE_ANOTHER_ACCOUNT_BUTTON = "//div[contains(text(), 'Use another account') or contains(text(), 'Usar outra conta')]"
    CHOOSE_ACCOUNT_SCREEN = "//div[contains(text(), 'Choose an account') or contains(text(), 'Escolha uma conta')]"
    LOGIN_ERROR: str = "//div[contains(@class, 'error')]"


@dataclass
class AdSenseSignupLocators:
    """Localizadores para o processo de inscrição no AdSense."""
    # Tela inicial de inscrição
    GET_STARTED_BUTTON: str = "//button[contains(text(), 'Get started') or contains(text(), 'Começar') or contains(text(), 'Empezar')]"
    ACCEPT_TERMS_CHECKBOX: str = "//div[contains(@class, 'checkbox')]"

    # Formulário de site
    WEBSITE_URL_FIELD: str = "//input[contains(@placeholder, 'http')]"
    WEBSITE_URL_FIELD_SPECIFIC: str = "/html/body/div[1]/signup-with-publisher-chooser/as-exception-handler/signup/div/account-creation/div/article/form/div[1]/site-url/section/div/div/div/material-input/label/input"
    SITE_CATEGORY_DROPDOWN: str = "//div[contains(@role, 'combobox') and contains(@aria-labelledby, 'category')]"
    SITE_CATEGORY_OPTIONS: str = "//li[@role='option']"
    SITE_LANGUAGE_DROPDOWN: str = "//div[contains(@role, 'combobox') and contains(@aria-labelledby, 'language')]"
    SITE_LANGUAGE_OPTIONS: str = "//li[@role='option']"

    # Opções de preferência de email
    EMAIL_PREFERENCES_RADIO_GROUP: str = "//material-radio-group"
    EMAIL_PREFERENCES_DISABLE_RADIO: str = "/html/body/div[1]/signup-with-publisher-chooser/as-exception-handler/signup/div/account-creation/div/article/form/div[3]/email-preferences/section/div/div/material-radio-group/material-radio[2]"
    EMAIL_PREFERENCES_DISABLE_BY_ATTR: str = "//material-radio[@trackclick='disable-email-marketing-click']"
    EMAIL_PREFERENCES_DISABLE_BY_CLASS: str = "//material-radio[contains(@class, 'disable-emails-radio')]"

    # País/Território
    COUNTRY_DROPDOWN: str = "/html/body/div[1]/signup-with-publisher-chooser/as-exception-handler/signup/div/account-creation/div/article/form/terms-and-conditions/section/div/div/material-dropdown-select/dropdown-button"
    COUNTRY_OPTIONS: str = "//material-select-dropdown-item/span"
    COUNTRY_FIRST_OPTION: str = "//material-select-dropdown-item[1]/span"

    # Checkbox de aceitação dos termos
    TERMS_CHECKBOX: str = "/html/body/div[1]/signup-with-publisher-chooser/as-exception-handler/signup/div/account-creation/div/article/form/terms-and-conditions/product-agreement/section/div/div/material-checkbox/div[1]"
    TERMS_CHECKBOX_INPUT: str = "/html/body/div[1]/signup-with-publisher-chooser/as-exception-handler/signup/div/account-creation/div/article/form/terms-and-conditions/product-agreement/section/div/div/material-checkbox/div[1]/input"

    # Botão OK para criar conta
    OK_BUTTON: str = "/html/body/div[1]/signup-with-publisher-chooser/as-exception-handler/signup/div/account-creation/div/article/form/footer/div/button"
    OK_BUTTON_RIPPLE: str = "/html/body/div[1]/signup-with-publisher-chooser/as-exception-handler/signup/div/account-creation/div/article/form/footer/div/button/material-ripple"

    # Seleção de conta
    ACCOUNT_SELECTION_CONTAINER: str = "//div[contains(@class, 'LbOduc')]"
    ACCOUNT_SELECTION_FIRST: str = "/html/body/div[1]/div[1]/div[2]/c-wiz/div/div[2]/div/div/div/form/span/section/div/div/div/div/ul/li[1]/div/div[1]/div"

    # Formulário de informações da conta
    COUNTRY_DROPDOWN_ALT: str = "//div[contains(@role, 'combobox') and contains(@aria-labelledby, 'country')]"
    TIMEZONE_DROPDOWN: str = "//div[contains(@role, 'combobox') and contains(@aria-labelledby, 'timezone')]"
    TIMEZONE_OPTIONS: str = "//li[@role='option']"

    # Formulário de endereço
    NAME_FIELD: str = "//input[contains(@aria-labelledby, 'name')]"
    STREET_ADDRESS_FIELD: str = "//input[contains(@aria-labelledby, 'street')]"
    CITY_FIELD: str = "//input[contains(@aria-labelledby, 'city')]"
    STATE_FIELD: str = "//input[contains(@aria-labelledby, 'state')]"
    ZIP_CODE_FIELD: str = "//input[contains(@aria-labelledby, 'zip') or contains(@aria-labelledby, 'postal')]"
    PHONE_FIELD: str = "//input[contains(@aria-labelledby, 'phone')]"

    # Botões de navegação
    SUBMIT_BUTTON: str = "//button[@type='submit' or contains(text(), 'Submit') or contains(text(), 'Enviar') or contains(text(), 'Enviar')]"
    NEXT_BUTTON: str = "//button[contains(text(), 'Next') or contains(text(), 'Próximo') or contains(text(), 'Siguiente') or contains(text(), 'Avançar') or contains(@class, 'Next')]"
    CONTINUE_BUTTON: str = "//button[contains(text(), 'Continue') or contains(text(), 'Continuar') or contains(text(), 'Continuar')]"
    SAVE_BUTTON: str = "//button[contains(text(), 'Save') or contains(text(), 'Salvar') or contains(text(), 'Guardar')]"

    # Verificação do site
    VERIFICATION_METHOD_DROPDOWN: str = "//div[contains(@role, 'combobox') and contains(@aria-labelledby, 'verification')]"
    VERIFICATION_CODE_FIELD: str = "//textarea[contains(@aria-labelledby, 'code') or contains(@aria-labelledby, 'tag')]"
    VERIFY_BUTTON: str = "//button[contains(text(), 'Verify') or contains(text(), 'Verificar') or contains(text(), 'Verificar')]"


@dataclass
class AdSensePaymentLocators:
    """Localizadores para configuração de pagamento."""
    PAYMENT_METHOD_DROPDOWN: str = "//div[contains(@role, 'combobox') and contains(@aria-labelledby, 'payment')]"
    BANK_ACCOUNT_NUMBER_FIELD: str = "//input[contains(@aria-labelledby, 'account')]"
    BANK_ROUTING_NUMBER_FIELD: str = "//input[contains(@aria-labelledby, 'routing')]"
    BANK_NAME_FIELD: str = "//input[contains(@aria-labelledby, 'bankName')]"
    TAX_INFO_BUTTON: str = "//button[contains(text(), 'Tax') or contains(text(), 'Imposto') or contains(text(), 'Impuesto')]"


@dataclass
class AdSenseDashboardLocators:
    """Localizadores para o painel do AdSense."""
    ACCOUNT_STATUS_LABEL: str = "//div[contains(@class, 'status')]"
    REVIEW_STATUS_MESSAGE: str = "//div[contains(text(), 'review') or contains(text(), 'revisão') or contains(text(), 'revisión')]"
    EARNINGS_WIDGET: str = "//div[contains(@class, 'earnings')]"
    SETTINGS_MENU: str = "//button[contains(@aria-label, 'Settings') or contains(@aria-label, 'Configurações') or contains(@aria-label, 'Configuración')]"
    LOGOUT_BUTTON: str = "//button[contains(text(), 'Sign out') or contains(text(), 'Sair') or contains(text(), 'Cerrar sesión')]"


# Criar instâncias para acesso global
login_locators = LoginLocators()
signup_locators = AdSenseSignupLocators()
payment_locators = AdSensePaymentLocators()
dashboard_locators = AdSenseDashboardLocators()
