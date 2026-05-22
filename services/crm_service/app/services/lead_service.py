"""
Сервис работы с лидами - слой бизнес-логики CRM.

Здесь живут бизнес-правила (что значит "создать лида", какие записи
при этом появляются в журнале), а не доступ к БД - доступ инкапсулирован
в LeadRepository.

Транзакции: сервис управляет границей транзакции. Метод выполняет все
изменения через репозиторий (flush) и сам вызывает commit() в конце.
"""

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import LeadActivityType, LeadSource, LeadStatus
from app.core.exceptions import (
    ConversionError,
    InvalidAssigneeError,
    LeadConflictError,
    LeadNotFoundError,
)
from app.messaging.auth_client import (
    auth_client,
    AuthServiceError,
    AuthServiceUserConflict,
)
from app.messaging.outbox import (
    record_lead_converted,
    record_lead_created,
    record_lead_status_changed,
)
from app.models.lead import Lead
from app.models.lead_activity import LeadActivity
from app.repositories.lead import LeadRepository
from app.repositories.studio_cache import StudioCacheRepository
from app.repositories.user_cache import UserCacheRepository
from app.schemas.lead import (
    LeadActivityCreate,
    LeadConversionResponse,
    LeadConvertRequest,
    LeadDetailResponse,
    LeadListResponse,
    LeadPublicCreate,
    LeadResponse,
    LeadStatusUpdate,
    LeadUpdate,
)

logger = logging.getLogger(__name__)


class LeadService:
    """Бизнес-логика работы с лидами."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = LeadRepository(db)
        self.user_cache = UserCacheRepository(db)
        self.studio_cache = StudioCacheRepository(db)

    async def create_from_public_request(self, data: LeadPublicCreate) -> Lead:
        """
        Создать лид из публичной заявки с лендинга.

        Бизнес-правила:
            - новый лид всегда в статусе 'new';
            - источник жёстко 'landing' (публичная ручка - вход только
              для лендинга, см. комментарий в LeadPublicCreate);
            - сразу создаётся первая запись журнала, чтобы лента истории
              лида была полной с момента появления.

        Всё выполняется в одной транзакции: либо появляются и лид, и
        запись журнала, либо ничего.
        """
        lead = Lead(
            name=data.name,
            phone=data.phone,
            email=data.email,
            source=LeadSource.LANDING.value,
            status=LeadStatus.NEW.value,
            studio_id=data.studio_id,
        )
        # add делает flush - после этого у lead есть id, он нужен для
        # привязки записи журнала.
        lead = await self.repo.add(lead)

        # Первая запись журнала. created_by=None - заявка пришла извне,
        # инициатора-админа нет.
        activity = LeadActivity(
            lead_id=lead.id,
            type=LeadActivityType.NOTE.value,
            content="Лид создан из заявки с лендинга",
            created_by=None,
        )
        await self.repo.add_activity(activity)

        # Запись события в outbox - в той же транзакции, что и лид.
        # Воркер опубликует его в RabbitMQ асинхронно.
        await record_lead_created(self.db, lead)

        await self.db.commit()
        await self.db.refresh(lead)

        logger.info(
            "Lead created from public request: id=%s phone=%s studio_id=%s",
            lead.id, lead.phone, lead.studio_id,
        )
        return lead

    # ==================== ЧТЕНИЕ ====================

    async def get_lead(self, lead_id: int) -> Lead:
        """
        Получить лид по id.

        Raises:
            LeadNotFoundError: лида с таким id нет.
        """
        lead = await self.repo.get_by_id(lead_id)
        if lead is None:
            raise LeadNotFoundError(lead_id)
        return lead

    async def get_lead_with_activities(self, lead_id: int) -> Lead:
        """
        Получить лид вместе с журналом активностей (для карточки).

        Raises:
            LeadNotFoundError: лида с таким id нет.
        """
        lead = await self.repo.get_by_id_with_activities(lead_id)
        if lead is None:
            raise LeadNotFoundError(lead_id)
        return lead

    async def list_leads(
        self,
        *,
        status: str | None = None,
        assigned_to: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Lead], int]:
        """Получить страницу лидов с фильтрами. Возвращает (лиды, total)."""
        return await self.repo.list_filtered(
            status=status,
            assigned_to=assigned_to,
            limit=limit,
            offset=offset,
        )

    # ==================== ИЗМЕНЕНИЕ ====================

    async def change_status(
        self,
        lead_id: int,
        data: LeadStatusUpdate,
        admin_user_id: int,
    ) -> Lead:
        """
        Сменить статус лида.

        Бизнес-правила:
            - сконвертированный лид (converted_user_id заполнен) - в
              терминальном состоянии: менять его статус нельзя;
            - граф переходов не ограничивается: движение по воронке ручное,
              админ - источник истины, законные "прыжки" статусов возможны;
            - при переходе в 'lost' сохраняется причина (lost_reason);
            - смена статуса автоматически дописывает в журнал системную
              запись типа status_changed с описанием перехода.

        Всё выполняется в одной транзакции.

        Raises:
            LeadNotFoundError: лида нет.
            LeadConflictError: лид уже сконвертирован.
        """
        lead = await self.get_lead(lead_id)

        old_status = lead.status
        new_status = data.status.value

        # Валидация целевого статуса по правилу инварианта воронки.
        # Статусы trial_scheduled / trial_attended / converted доступны
        # только лидам с converted_user_id (есть аккаунт). Статусы
        # new / contacted - только лидам без converted_user_id (нет
        # аккаунта). Статус lost доступен с любого этапа.
        self._validate_status_transition(lead, data.status)

        # Идемпотентность: смена статуса на тот же самый - не ошибка,
        # но и не бизнес-событие. Ничего не делаем, журнал не засоряем.
        if old_status == new_status:
            return lead

        lead.status = new_status
        # lost_reason заполняется только при уходе в 'lost'; при любом
        # другом статусе схема гарантирует, что lost_reason отсутствует.
        if data.status == LeadStatus.LOST:
            lead.lost_reason = data.lost_reason

        # Системная запись в журнал. created_by - админ, инициировавший
        # смену (в отличие от чисто системных записей с created_by=None).
        description = f"Статус: {old_status} -> {new_status}"
        if data.comment:
            description += f". Комментарий: {data.comment}"
        activity = LeadActivity(
            lead_id=lead.id,
            type=LeadActivityType.STATUS_CHANGED.value,
            content=description,
            created_by=admin_user_id,
        )
        await self.repo.add_activity(activity)

        # Запись события в outbox - в той же транзакции со сменой статуса.
        await record_lead_status_changed(
            self.db,
            lead,
            old_status=old_status,
            new_status=new_status,
            changed_by=admin_user_id,
        )

        await self.db.commit()
        await self.db.refresh(lead)

        logger.info(
            "Lead %s status changed: %s -> %s by admin %s",
            lead_id, old_status, new_status, admin_user_id,
        )
        return lead

    @staticmethod
    def _validate_status_transition(lead: Lead, new_status: LeadStatus) -> None:
        """
        Проверить, что лид может перейти в указанный статус.

        Инвариант воронки:
            - new / contacted - только для лидов БЕЗ converted_user_id;
            - trial_scheduled / trial_attended / converted - только для
              лидов С converted_user_id (есть аккаунт);
            - lost - разрешён всегда (выход из воронки на любом этапе).

        trial_scheduled у лида БЕЗ converted_user_id - запрещён напрямую:
            в этот статус лид попадает только через конвертацию
            (POST /convert-to-user), которая сама создаёт юзера и ставит
            статус. Прямой PATCH сюда невозможен, чтобы не создавать
            рассинхрон "статус trial_scheduled, юзера нет".

        Raises:
            LeadConflictError: переход недопустим.
        """
        # lost разрешён всегда.
        if new_status == LeadStatus.LOST:
            return

        is_converted = lead.converted_user_id is not None

        # Статусы для лидов с аккаунтом.
        post_conversion = {
            LeadStatus.TRIAL_SCHEDULED,
            LeadStatus.TRIAL_ATTENDED,
            LeadStatus.CONVERTED,
        }
        # Статусы для лидов без аккаунта.
        pre_conversion = {LeadStatus.NEW, LeadStatus.CONTACTED}

        if is_converted and new_status in pre_conversion:
            raise LeadConflictError(
                f"Нельзя вернуть лид с аккаунтом в статус "
                f"«{new_status.value}». Доступны только переходы вперёд "
                f"по воронке или в «потерян»."
            )

        if not is_converted and new_status in post_conversion:
            if new_status == LeadStatus.TRIAL_SCHEDULED:
                raise LeadConflictError(
                    "Нельзя перевести лид в «записаны на пробное» напрямую. "
                    "Используйте «Конвертировать в клиента» — это создаст "
                    "аккаунт и переведёт лид в нужный статус."
                )
            raise LeadConflictError(
                f"Нельзя перевести лид в «{new_status.value}» без аккаунта. "
                f"Сначала выполните конвертацию через «Конвертировать в клиента»."
            )

    async def update_lead(
        self,
        lead_id: int,
        data: LeadUpdate,
    ) -> Lead:
        """
        Обновить поля лида (assigned_to, notes).

        Применяются только реально присланные поля - см. model_fields_set:
        это позволяет отличить "поле не трогаем" от "поле явно обнуляем"
        (assigned_to=null снимает назначение).

        Валидация assigned_to: если назначение задано (не null), проверяем
        по users_cache, что пользователь существует, активен и имеет роль
        admin. CRM-воронку ведут только администраторы.

        Смена статуса сюда не входит - для неё отдельный метод change_status.

        Raises:
            LeadNotFoundError: лида нет.
            InvalidAssigneeError: assigned_to указывает на пользователя,
                которого нельзя назначить ответственным.
        """
        lead = await self.get_lead(lead_id)

        # exclude_unset: в словарь попадут только присланные клиентом поля.
        changes = data.model_dump(exclude_unset=True)

        # Валидация назначения. Проверяем только если assigned_to реально
        # прислан и не null (null = снять назначение, проверять нечего).
        if changes.get("assigned_to") is not None:
            await self._validate_assignee(changes["assigned_to"])

        for field, value in changes.items():
            setattr(lead, field, value)

        await self.db.commit()
        await self.db.refresh(lead)

        logger.info("Lead %s updated: fields=%s", lead_id, list(changes.keys()))
        return lead

    async def _validate_assignee(self, user_id: int) -> None:
        """
        Проверить, что лид можно назначить на пользователя user_id.

        Условия: пользователь есть в users_cache, активен, роль 'admin'.

        Raises:
            InvalidAssigneeError: любое из условий не выполнено.

        Примечание: users_cache наполняется событиями auth_events. Если
        админ был создан до запуска consumer'а, его может не быть в кеше -
        см. пункт 2 в TECH_DEBT.md (бутстрап-синхронизация).
        """
        user = await self.user_cache.get_by_id(user_id)
        if user is None:
            raise InvalidAssigneeError(
                f"User {user_id} not found in cache; cannot assign lead"
            )
        if not user.is_active:
            raise InvalidAssigneeError(
                f"User {user_id} is inactive; cannot assign lead"
            )
        if user.role_name != "admin":
            raise InvalidAssigneeError(
                f"User {user_id} has role '{user.role_name}'; "
                f"only admins can be assigned to leads"
            )

    async def add_activity(
        self,
        lead_id: int,
        data: LeadActivityCreate,
        admin_user_id: int,
    ) -> LeadActivity:
        """
        Добавить запись (заметку или отметку о звонке) в журнал лида.

        Тип status_changed сюда не пройдёт - он отсекается на уровне
        схемы LeadActivityCreate (создаётся только системой).

        Raises:
            LeadNotFoundError: лида нет.
        """
        # Проверяем существование лида - иначе можно создать висячую
        # запись на несуществующий lead_id.
        await self.get_lead(lead_id)

        activity = LeadActivity(
            lead_id=lead_id,
            type=data.type.value,
            content=data.content,
            created_by=admin_user_id,
        )
        await self.repo.add_activity(activity)
        await self.db.commit()
        await self.db.refresh(activity)

        logger.info(
            "Activity added to lead %s: type=%s by admin %s",
            lead_id, data.type.value, admin_user_id,
        )
        return activity

    # ==================== КОНВЕРТАЦИЯ ====================

    @staticmethod
    def _split_name(full_name: str) -> tuple[str, str]:
        """
        Разбить имя лида (одна строка) на first_name / last_name для User.

        Правило: первое слово - имя, остаток - фамилия. Если слово одно,
        last_name дублирует first_name (User.last_name - NOT NULL). Это
        приближение: админ при необходимости поправит профиль позже
        (см. TECH_DEBT.md).
        """
        parts = full_name.strip().split(maxsplit=1)
        if len(parts) == 2:
            return parts[0], parts[1]
        single = parts[0] if parts else full_name.strip()
        return single, single

    async def convert_to_user(
        self,
        lead_id: int,
        admin_user_id: int,
        data: Optional[LeadConvertRequest] = None,
    ) -> LeadConversionResponse:
        """
        Конвертировать лид в клиента (provisioned-пользователя).

        Создаёт в Auth Service пользователя без пароля, привязывает его
        к лиду (converted_user_id) и переводит лид в статус
        trial_scheduled - готов к записи на первое занятие.

        Тело запроса (data) опционально: если поле не передано - берётся
        из лида. После слияния body+лида обязаны быть заполнены email и
        studio_id, иначе создать юзера в Auth невозможно. studio_id
        дополнительно проверяется по локальному кешу studios_cache
        (студия должна существовать и быть активной).

        Идемпотентность: если лид уже сконвертирован (converted_user_id
        заполнен) - повторный вызов не создаёт второго пользователя,
        а возвращает существующий результат.

        Порядок операций важен. Сначала - необратимый HTTP-вызов в Auth
        (создание пользователя). Только при его успехе пишем изменения
        в свою БД. Если Auth упал - лид не тронут, ошибка уходит наверх.

        Граница MVP: если Auth вернул 409 (email занят), а лид ещё не
        сконвертирован - это либо email реально занят другим человеком,
        либо "висячее состояние" (пользователь создан, но локальный
        commit прошлой попытки не прошёл). Автоматически это не
        разрешается - возвращается ConversionError (см. TECH_DEBT.md).

        Raises:
            LeadNotFoundError: лида нет.
            ConversionError: лид в статусе lost, недостающие/невалидные
                данные (email, studio_id), либо сбой/конфликт Auth.
        """
        lead = await self.get_lead(lead_id)

        # Идемпотентность: уже сконвертирован - возвращаем как есть.
        if lead.converted_user_id is not None:
            logger.info(
                "Lead %s already converted (user_id=%s), returning existing",
                lead_id, lead.converted_user_id,
            )
            response = await self.build_lead_response(lead)
            return LeadConversionResponse(
                converted_user_id=lead.converted_user_id,
                lead=response,
            )

        # Проигранный лид конвертировать нельзя.
        if lead.status == LeadStatus.LOST.value:
            raise ConversionError(
                "Невозможно конвертировать проигранный лид."
            )

        # Сливаем body + данные лида. Поля из body побеждают; если поле
        # не передано - дефолт из лида.
        data = data or LeadConvertRequest()

        if data.first_name and data.last_name:
            first_name, last_name = data.first_name, data.last_name
        else:
            split_first, split_last = self._split_name(lead.name)
            first_name = data.first_name or split_first
            last_name = data.last_name or split_last

        email = data.email or lead.email
        phone = data.phone if data.phone is not None else lead.phone
        studio_id = data.studio_id or lead.studio_id

        # Финальная валидация: после слияния body+лида email и studio_id
        # обязаны быть, иначе создать юзера в Auth невозможно.
        if not email:
            raise ConversionError(
                "Невозможно конвертировать лид: укажите email "
                "(не передан в запросе и не указан в карточке лида)."
            )
        if studio_id is None:
            raise ConversionError(
                "Невозможно конвертировать лид: укажите студию "
                "(не передана в запросе и не указана в карточке лида)."
            )
        if not await self.studio_cache.exists_and_active(studio_id):
            raise ConversionError(
                f"Невозможно конвертировать лид: студия {studio_id} "
                f"не существует или неактивна."
            )

        # Необратимый шаг: создаём пользователя в Auth Service.
        try:
            user_data = await auth_client.provision_user(
                email=email,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                studio_id=studio_id,
            )
        except AuthServiceUserConflict:
            raise ConversionError(
                f"Пользователь с email «{email}» уже зарегистрирован "
                f"в системе."
            )
        except AuthServiceError as exc:
            raise ConversionError(
                f"Сервис аутентификации недоступен. Попробуйте позже."
            ) from exc

        converted_user_id = user_data["id"]

        # Auth отработал - записываем изменения в свою БД одной транзакцией.
        old_status = lead.status
        lead.converted_user_id = converted_user_id
        lead.status = LeadStatus.TRIAL_SCHEDULED.value

        activity = LeadActivity(
            lead_id=lead.id,
            type=LeadActivityType.STATUS_CHANGED.value,
            content=(
                f"Лид сконвертирован в клиента (user_id={converted_user_id}). "
                f"Статус: {old_status} -> {LeadStatus.TRIAL_SCHEDULED.value}"
            ),
            created_by=admin_user_id,
        )
        await self.repo.add_activity(activity)

        await record_lead_converted(
            self.db, lead, converted_user_id, admin_user_id
        )
        # Конвертация меняет и статус - публикуем оба события.
        await record_lead_status_changed(
            self.db,
            lead,
            old_status=old_status,
            new_status=LeadStatus.TRIAL_SCHEDULED.value,
            changed_by=admin_user_id,
        )

        await self.db.commit()
        await self.db.refresh(lead)

        logger.info(
            "Lead %s converted to user %s by admin %s",
            lead_id, converted_user_id, admin_user_id,
        )

        response = await self.build_lead_response(lead)
        return LeadConversionResponse(
            converted_user_id=converted_user_id,
            lead=response,
        )

    # ==================== ПОСТРОЕНИЕ ОТВЕТОВ ====================
    # Обогащение - бизнес-логика (подстановка имени ответственного из
    # users_cache), поэтому живёт в сервисе, а не в роутере. Роутер
    # вызывает эти методы, чтобы превратить ORM-объект в схему ответа.

    async def build_lead_response(self, lead: Lead) -> LeadResponse:
        """Собрать LeadResponse с обогащением именем ответственного."""
        response = LeadResponse.model_validate(lead)
        if lead.assigned_to is not None:
            user = await self.user_cache.get_by_id(lead.assigned_to)
            if user is not None:
                response.assigned_to_name = user.full_name
        return response

    async def build_lead_detail_response(
        self, lead: Lead
    ) -> LeadDetailResponse:
        """
        Собрать LeadDetailResponse (карточка с журналом) с обогащением.

        lead должен быть загружен вместе с activities (см.
        get_lead_with_activities), иначе обращение к lead.activities
        в async-контексте упадёт.
        """
        response = LeadDetailResponse.model_validate(lead)
        if lead.assigned_to is not None:
            user = await self.user_cache.get_by_id(lead.assigned_to)
            if user is not None:
                response.assigned_to_name = user.full_name
        return response

    async def build_lead_list_response(
        self, leads: list[Lead], total: int
    ) -> LeadListResponse:
        """
        Собрать LeadListResponse с обогащением имён ответственных.

        Имена подгружаются одним запросом по всем уникальным assigned_to
        страницы - без N+1 обращений к кешу.
        """
        # Уникальные id ответственных на странице.
        assignee_ids = list(
            {lead.assigned_to for lead in leads if lead.assigned_to is not None}
        )
        users = await self.user_cache.get_many_by_ids(assignee_ids)

        items: list[LeadResponse] = []
        for lead in leads:
            response = LeadResponse.model_validate(lead)
            if lead.assigned_to is not None:
                user = users.get(lead.assigned_to)
                if user is not None:
                    response.assigned_to_name = user.full_name
            items.append(response)

        return LeadListResponse(total=total, items=items)