"""
Доменные исключения CRM Service.

Сервисный слой не должен знать про HTTP. Он оперирует доменными
понятиями и кидает доменные исключения; перевод в HTTP-ответы -
ответственность API-слоя (роутера).

Это разделение позволяет переиспользовать сервис вне HTTP-контекста
(например, в consumer'е RabbitMQ или фоновом воркере) без протечки
веб-специфики.
"""


class CrmError(Exception):
    """Базовое исключение домена CRM."""


class LeadNotFoundError(CrmError):
    """Лид с указанным id не существует."""

    def __init__(self, lead_id: int):
        self.lead_id = lead_id
        super().__init__(f"Lead {lead_id} not found")


class LeadConflictError(CrmError):
    """
    Операция невозможна из-за текущего состояния лида.

    Например: попытка сменить статус уже сконвертированного лида -
    после конвертации воронка для лида завершена.
    """

    def __init__(self, message: str):
        super().__init__(message)


class InvalidAssigneeError(CrmError):
    """
    Лид нельзя назначить на указанного пользователя.

    Причины: пользователя нет в локальном кеше (users_cache), он
    неактивен, или его роль не 'admin'. CRM-воронку ведут только
    администраторы.
    """

    def __init__(self, message: str):
        super().__init__(message)


class ConversionError(CrmError):
    """
    Конвертация лида в пользователя невозможна.

    Причины: лид уже сконвертирован, лид в статусе 'lost', сбой связи
    с Auth Service, либо email лида уже занят в Auth Service.
    """

    def __init__(self, message: str):
        super().__init__(message)