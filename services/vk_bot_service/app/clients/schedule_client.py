"""
HTTP-клиент к Schedule Service: расписание и отмена занятий.

ВАЖНО про авторизацию. Ручки schedule защищены JWT с проверкой роли и
владения (get_current_teacher / check_teacher_access): преподаватель
может отменять только свои занятия. Internal-ключ тут НЕ подходит -
сервис должен знать, ОТ ЧЬЕГО имени действие. Поэтому бот вызывает
schedule с access-токеном конкретного пользователя.

Токен бот получает и обновляет через TokenService (см. services/) -
этот клиент принимает готовый access_token и только делает HTTP-вызовы.
Разделение намеренное: клиент не знает, откуда взялся токен, а добыча/
refresh токенов - ответственность отдельного слоя.
"""
import logging
from datetime import date
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings
from app.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)


class ScheduleClient:
    """Клиент вызовов к Schedule Service от имени пользователя (по JWT)."""

    def __init__(self) -> None:
        self._base_url = settings.schedule_service_url.rstrip("/")
        self._timeout = settings.external_service_timeout

    @staticmethod
    def _auth_headers(access_token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {access_token}"}

    async def get_teacher_schedule(
        self,
        *,
        access_token: str,
        teacher_id: int,
        from_date: date,
        to_date: date,
    ) -> Dict[str, Any]:
        """
        Расписание преподавателя за период.

        Returns:
            dict TeacherScheduleResponse (teacher_id, lessons[], total, ...).

        Raises:
            ExternalServiceError: транспорт/HTTP-ошибка (403 при чужом
                расписании, 401 при протухшем токене - вызывающий слой
                решает, обновлять токен или нет).
        """
        url = f"{self._base_url}/api/v1/schedule/teachers/{teacher_id}"
        params = {"from_date": from_date.isoformat(), "to_date": to_date.isoformat()}
        return await self._get(url, params, access_token)

    async def get_student_schedule(
        self,
        *,
        access_token: str,
        student_id: int,
        from_date: date,
        to_date: date,
    ) -> Dict[str, Any]:
        """Занятия ученика за период (StudentScheduleResponse)."""
        url = f"{self._base_url}/api/v1/schedule/students/{student_id}"
        params = {"from_date": from_date.isoformat(), "to_date": to_date.isoformat()}
        return await self._get(url, params, access_token)

    async def cancel_lesson(
        self,
        *,
        access_token: str,
        lesson_id: int,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Отменить занятие. Schedule опубликует lesson.cancelled, которое
        бот же и получит обратно как событие на рассылку студентам -
        замкнутый, но корректный цикл (consumer идемпотентен).

        Returns:
            dict LessonResponse отменённого занятия.
        """
        url = f"{self._base_url}/api/v1/schedule/lessons/{lesson_id}/cancel"
        body: Dict[str, Any] = {}
        if reason:
            body["reason"] = reason
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    url, json=body, headers=self._auth_headers(access_token)
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError("schedule", f"request failed: {exc}") from exc

        if resp.status_code >= 400:
            raise ExternalServiceError(
                "schedule", resp.text, status_code=resp.status_code
            )
        return resp.json()

    async def _get(
        self,
        url: str,
        params: Dict[str, Any],
        access_token: str,
    ) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    url, params=params, headers=self._auth_headers(access_token)
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError("schedule", f"request failed: {exc}") from exc

        if resp.status_code >= 400:
            raise ExternalServiceError(
                "schedule", resp.text, status_code=resp.status_code
            )
        return resp.json()


schedule_client = ScheduleClient()
