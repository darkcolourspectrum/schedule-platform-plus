"""
HTTP-клиент к CRM Service: подача заявки-лида из бота.

CRM-ручка приёма заявки публичная (без авторизации). Снаружи через
gateway она доступна как POST /api/crm/leads/public, но бот ходит к
сервису напрямую по внутренней сети, где роутер смонтирован под
/api/v1, то есть путь /api/v1/leads/public.

Тело запроса - LeadPublicCreate: name (обяз.), email (обяз.),
phone (опц.), studio_id (опц.). source и status сервер проставляет сам
(landing / new) - бот их не передаёт и не может.
"""
import logging
from typing import Any, Dict, Optional

import httpx

from app.config import settings
from app.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)


class CrmClient:
    """Клиент вызовов к CRM Service."""

    def __init__(self) -> None:
        self._base_url = settings.crm_service_url.rstrip("/")
        self._timeout = settings.external_service_timeout

    async def create_public_lead(
        self,
        *,
        name: str,
        email: str,
        phone: Optional[str] = None,
        studio_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Создать лид из заявки, поданной через бота.

        Returns:
            dict с полями созданного лида (LeadResponse).

        Raises:
            ExternalServiceError: транспортная ошибка или HTTP-ошибка CRM
                (например 422 при невалидном email - текст пробрасывается,
                чтобы слой сценария показал пользователю понятное сообщение).
        """
        url = f"{self._base_url}/api/v1/leads/public"
        body: Dict[str, Any] = {"name": name, "email": email}
        if phone:
            body["phone"] = phone
        if studio_id:
            body["studio_id"] = studio_id

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=body)
        except httpx.HTTPError as exc:
            raise ExternalServiceError("crm", f"request failed: {exc}") from exc

        if resp.status_code >= 400:
            raise ExternalServiceError(
                "crm", resp.text, status_code=resp.status_code
            )
        return resp.json()


crm_client = CrmClient()
