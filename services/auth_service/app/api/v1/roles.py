from typing import List
from fastapi import APIRouter, Depends

from app.dependencies import get_current_admin
from app.schemas.role import RoleResponse
from app.repositories.role_repository import RoleRepository
from app.database.connection import get_async_session
from app.models.user import User

router = APIRouter(prefix="/roles", tags=["Roles"])


@router.get(
    "/",
    response_model=List[RoleResponse],
    summary="Получение списка ролей",
    description="Доступно только администраторам"
)
async def get_roles(
    admin_user: User = Depends(get_current_admin),
    db = Depends(get_async_session)
):
    """Получение списка всех ролей"""
    
    role_repo = RoleRepository(db)
    roles = await role_repo.get_all()
    
    return [RoleResponse.from_orm(role) for role in roles]