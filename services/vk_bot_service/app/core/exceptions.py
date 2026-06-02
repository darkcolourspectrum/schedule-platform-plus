"""Доменные исключения VK Bot Service."""


class VkBotException(Exception):
    """Базовое исключение сервиса."""


# ==================== VK API ====================


class VkApiError(VkBotException):
    """
    Ошибка вызова VK API.

    code - числовой код ошибки VK (см. https://dev.vk.com/reference/errors).
    Хранится отдельно, чтобы вызывающий код мог отличить транзиентные
    ошибки (повторить) от перманентных (не повторять).
    """

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"VK API error {code}: {message}")


class VkMessageUndeliverable(VkApiError):
    """
    Сообщение не может быть доставлено по перманентной причине.

    Главный случай - код 901: нельзя писать пользователю, который не
    начал диалог с сообществом и/или не разрешил сообщения. Это штатная
    ситуация (человек не подключил бота), НЕ повод для ретраев. Отправляющий
    слой помечает такое сообщение undeliverable и не повторяет.
    """


class VkNotConfigured(VkBotException):
    """VK-сообщество не настроено (нет токена/group_id). Отправка невозможна."""


# ==================== EXTERNAL SERVICES ====================


class ExternalServiceError(VkBotException):
    """Ошибка вызова внешнего сервиса платформы (auth/crm/schedule)."""

    def __init__(self, service: str, detail: str, status_code: int | None = None):
        self.service = service
        self.detail = detail
        self.status_code = status_code
        super().__init__(f"{service} error ({status_code}): {detail}")


class UserNotResolved(VkBotException):
    """Не удалось сопоставить vk_id с пользователем платформы (нет в кеше)."""
