"""
Общие исключения для shared/auth_lib
"""


class AuthLibException(Exception):
    """Базовое исключение библиотеки"""
    pass


class InvalidTokenError(AuthLibException):
    """Токен невалиден (неправильная подпись, формат, истёк срок)"""
    pass


class TokenRevokedError(AuthLibException):
    """Токен отозван (logout, смена роли, деактивация пользователя)"""
    pass


class TokenTypeMismatchError(AuthLibException):
    """Тип токена не соответствует ожидаемому (например, refresh вместо access)"""
    pass