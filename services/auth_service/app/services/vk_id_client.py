"""
HTTP-клиент для обмена кода авторизации VK ID на проверенный vk_id.

Назначение
----------
Это слой "общения с внешним VK", изолированный от бизнес-логики (по тому
же принципу, что auth_client в CRM изолирует поход в Auth Service).
Роут принимает от фронта `code` + `device_id` + `code_verifier`, которые
фронт получил из официального окна VK ID, и передаёт их сюда. Клиент
делает серверный обмен на стороне VK (id.vk.com) и возвращает уже
ПРОВЕРЕННЫЙ vk_id вместе с данными профиля.

Почему обмен делает бэкенд, а не фронт
--------------------------------------
Фронту доверять нельзя: `code` от фронта сам по себе ничего не
доказывает (его можно подделать/перехватить). Доказательством служит
прямой ответ серверов VK на наш серверный запрос обмена. Только vk_id,
полученный ЭТИМ путём, считается подтверждённым.

Схема обмена (VK ID, OAuth 2.1 + PKCE)
--------------------------------------
POST https://id.vk.com/oauth2/auth
Content-Type: application/x-www-form-urlencoded
Тело:
    grant_type=authorization_code
    code=<код от фронта>
    device_id=<device_id от фронта; обязателен, без него VK откажет>
    code_verifier=<PKCE-verifier от фронта; сверяется с code_challenge>
    client_id=<id приложения VK>
    redirect_uri=<тот же, что при открытии окна>
    state=<опционально>

Ответ (200):
    {
        "access_token": "...",
        "token_type": "bearer",
        "expires_in": 3600,
        "user_id": 12345,        # <- это наш проверенный vk_id
        "email": "...",          # только если запрошен scope email и пользователь дал согласие
        ...
    }

Замечания
---------
- Публичный клиент VK ID использует PKCE, поэтому client_secret в обмене
  НЕ участвует (защита держится на code_verifier). В конфиге секрет не нужен.
- Профиль (имя/фамилия) в ответе обмена может отсутствовать. Если он нужен
  для регистрации, его можно дозапросить отдельным методом VK ID
  (user_info) - это добавим на шаге регистрации, не здесь.
- Этот модуль НЕ управляет БД и НЕ знает про User - только VK.
"""

import logging
from typing import Any, Dict, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class VkIdError(Exception):
    """
    Базовая ошибка обмена кода VK ID.

    Поднимается, когда обмен не удался: сетевой сбой, VK вернул ошибку,
    либо в ответе нет user_id. Роут транслирует её в осмысленный HTTP-код
    (как правило 400/502) - сюда HTTP-логика не протекает.
    """

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class VkIdExchangeResult:
    """
    Результат успешного обмена кода на токен VK ID.

    Содержит проверенный vk_id и доступные данные профиля. Поля профиля
    опциональны: VK не гарантирует ни email (часто его нет, если аккаунт
    привязан только к телефону), ни имя в ответе обмена.
    """

    def __init__(
        self,
        vk_id: str,
        email: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        raw: Optional[Dict[str, Any]] = None,
    ):
        self.vk_id = vk_id
        self.email = email
        self.first_name = first_name
        self.last_name = last_name
        # Полный ответ VK - на случай, если позже понадобятся другие поля.
        self.raw = raw or {}


class VkIdClient:
    """Клиент серверного обмена кода авторизации VK ID на vk_id."""

    def __init__(self) -> None:
        self.base_url = settings.vk_id_base_url.rstrip("/")
        self.client_id = settings.vk_client_id
        self.redirect_uri = settings.vk_redirect_uri
        self.timeout = settings.vk_id_timeout

    async def exchange_code(
        self,
        code: str,
        device_id: str,
        code_verifier: str,
        state: Optional[str] = None,
    ) -> VkIdExchangeResult:
        """
        Обменять код авторизации на проверенный vk_id.

        Args:
            code: код авторизации из окна VK (получен фронтом).
            device_id: идентификатор устройства из окна VK (обязателен).
            code_verifier: PKCE-verifier, парный к code_challenge, который
                фронт отправил при открытии окна. VK сверит их.
            state: необязательный параметр анти-CSRF (если фронт его слал).

        Returns:
            VkIdExchangeResult с проверенным vk_id и доступными данными
            профиля.

        Raises:
            VkIdError: сетевой сбой, неуспешный ответ VK, либо отсутствие
                user_id в ответе.
        """
        if not self.client_id:
            # Защита от запуска с ненастроенным VK: даём понятную ошибку,
            # а не падаем где-то глубже с неинформативным сообщением.
            raise VkIdError(
                "VK ID is not configured (VK_CLIENT_ID is empty)"
            )

        url = f"{self.base_url}/oauth2/auth"
        form: Dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "device_id": device_id,
            "code_verifier": code_verifier,
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
        }
        if state is not None:
            form["state"] = state

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, data=form, headers=headers)
        except httpx.RequestError as exc:
            logger.error("VK ID network error on code exchange: %s", exc)
            raise VkIdError(f"Network error calling VK ID: {exc}") from exc

        if response.status_code != 200:
            # VK вернул ошибку обмена (истёкший/повторно использованный код,
            # неверный code_verifier, неверный device_id и т.п.).
            logger.warning(
                "VK ID exchange failed: status=%s body=%s",
                response.status_code,
                response.text,
            )
            raise VkIdError(
                f"VK ID returned {response.status_code}: {response.text}",
                status_code=response.status_code,
            )

        try:
            data: Dict[str, Any] = response.json()
        except ValueError as exc:
            logger.error("VK ID returned non-JSON body: %s", response.text)
            raise VkIdError("VK ID returned invalid JSON") from exc

        # Иногда VK кладёт ошибку в тело при HTTP 200.
        if "error" in data:
            logger.warning("VK ID exchange error in body: %s", data)
            raise VkIdError(
                f"VK ID error: {data.get('error_description') or data.get('error')}"
            )

        user_id = data.get("user_id")
        if user_id is None:
            logger.error("VK ID response has no user_id: %s", data)
            raise VkIdError("VK ID response did not contain user_id")

        # vk_id в нашей модели User хранится строкой (String(50)) - приводим.
        vk_id = str(user_id)

        result = VkIdExchangeResult(
            vk_id=vk_id,
            email=data.get("email"),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            raw=data,
        )

        logger.info("VK ID exchange ok: vk_id=%s", vk_id)
        return result


# Singleton-экземпляр клиента (по образцу auth_client в CRM).
vk_id_client = VkIdClient()