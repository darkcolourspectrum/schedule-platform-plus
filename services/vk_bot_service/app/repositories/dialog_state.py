"""Репозиторий для dialog_states (состояние FSM диалога)."""
import logging
from typing import Any, Dict, Optional

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dialog_state import DialogState

logger = logging.getLogger(__name__)


class DialogStateRepository:
    """
    Доступ к состоянию диалога одного VK-собеседника.

    Методы коммитят сами: состояние диалога меняется в ответ на каждое
    входящее сообщение Long Poll, это самостоятельная короткая операция
    вне общей транзакции бизнес-действия. Так проще и безопаснее, чем
    тянуть Unit of Work через весь обработчик сообщения.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, vk_id: int) -> Optional[DialogState]:
        result = await self.db.execute(
            select(DialogState).where(DialogState.vk_id == vk_id)
        )
        return result.scalar_one_or_none()

    async def set(
        self,
        *,
        vk_id: int,
        scenario: str,
        state: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Установить/обновить состояние диалога. Upsert по vk_id.

        Перезаписывает scenario/state/data целиком - вызывающий слой
        сценария передаёт полную картину текущего шага.
        """
        stmt = pg_insert(DialogState).values(
            vk_id=vk_id,
            scenario=scenario,
            state=state,
            data=data,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["vk_id"],
            set_={
                "scenario": stmt.excluded.scenario,
                "state": stmt.excluded.state,
                "data": stmt.excluded.data,
            },
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def clear(self, vk_id: int) -> None:
        """Удалить состояние диалога (завершение/отмена сценария)."""
        await self.db.execute(
            delete(DialogState).where(DialogState.vk_id == vk_id)
        )
        await self.db.commit()
