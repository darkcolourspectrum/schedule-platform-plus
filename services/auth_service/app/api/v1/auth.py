from fastapi import APIRouter, Depends, Response, Request, status
from fastapi.responses import JSONResponse

from app.dependencies import get_auth_service, get_client_info, get_current_user
from app.services.auth_service import AuthService
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    AuthResponse,
    RefreshTokenRequest,
    AccessTokenResponse,
    LogoutRequest,
    MessageResponse
)
from app.schemas.user import CurrentUser
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация нового пользователя",
    description="Создание нового аккаунта пользователя с ролью студента"
)
async def register(
    user_data: RegisterRequest,
    response: Response,
    client_info: dict = Depends(get_client_info),
    auth_service: AuthService = Depends(get_auth_service)
):
    """Регистрация нового пользователя"""
    
    result = await auth_service.register_user(
        email=user_data.email,
        password=user_data.password,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        phone=user_data.phone,
        privacy_policy_accepted=user_data.privacy_policy_accepted
    )
    
    # Устанавливаем refresh token в httpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=result["tokens"]["refresh_token"],
        httponly=True,
        secure=True,  # HTTPS only в production
        samesite="lax",
        max_age=60 * 60 * 24 * 7  # 7 дней
    )
    
    return AuthResponse(
        user=result["user"],
        tokens={
            "access_token": result["tokens"]["access_token"],
            "refresh_token": result["tokens"]["refresh_token"],
            "token_type": result["tokens"]["token_type"]
        }
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Вход в систему",
    description="Аутентификация пользователя по email и паролю"
)
async def login(
    credentials: LoginRequest,
    response: Response,
    client_info: dict = Depends(get_client_info),
    auth_service: AuthService = Depends(get_auth_service)
):
    """Вход в систему"""
    
    result = await auth_service.login_user(
        email=credentials.email,
        password=credentials.password,
        device_info=client_info.get("device_info"),
        ip_address=client_info.get("ip_address"),
        user_agent=client_info.get("user_agent")
    )
    
    # Устанавливаем refresh token в httpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=result["tokens"]["refresh_token"],
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7  # 7 дней
    )
    
    return AuthResponse(
        user=result["user"],
        tokens={
            "access_token": result["tokens"]["access_token"],
            "refresh_token": result["tokens"]["refresh_token"],
            "token_type": result["tokens"]["token_type"]
        }
    )


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    summary="Обновление access токена",
    description="Получение нового access токена по refresh токену"
)
async def refresh_token(
    request: Request,
    auth_service: AuthService = Depends(get_auth_service)
):
    """Обновление access токена"""
    
    # Получаем refresh token из cookie
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Refresh token not provided"}
        )
    
    result = await auth_service.refresh_access_token(refresh_token)
    
    return AccessTokenResponse(
        access_token=result["access_token"],
        token_type=result["token_type"]
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Выход из системы",
    description="Выход из текущего устройства"
)
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    """Выход из системы"""
    
    # Получаем refresh token из cookie
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Refresh token not found"}
        )
    
    # Получаем access token из заголовков
    authorization = request.headers.get("Authorization")
    access_token = None
    if authorization and authorization.startswith("Bearer "):
        access_token = authorization[7:]
    
    result = await auth_service.logout_user(refresh_token, access_token)
    
    # Удаляем refresh token cookie
    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        secure=True,
        samesite="lax"
    )
    
    return MessageResponse(message=result["message"])


@router.post(
    "/logout-all",
    response_model=MessageResponse,
    summary="Выход со всех устройств",
    description="Отзыв всех токенов пользователя"
)
async def logout_all_devices(
    response: Response,
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    """Выход со всех устройств"""
    
    result = await auth_service.logout_all_devices(current_user.id)
    
    # Удаляем refresh token cookie
    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        secure=True,
        samesite="lax"
    )
    
    return MessageResponse(message=result["message"])


@router.get(
    "/me",
    response_model=CurrentUser,
    summary="Получение данных текущего пользователя",
    description="Информация о текущем авторизованном пользователе"
)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Получение информации о текущем пользователе"""
    
    return CurrentUser(
        id=current_user.id,
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        full_name=current_user.full_name,
        role=current_user.role.name,
        studio_id=current_user.studio_id,
        studio_name=current_user.studio.name if current_user.studio else None,
        is_admin=current_user.is_admin,
        is_teacher=current_user.is_teacher,
        is_student=current_user.is_student,
        permissions=[]  # Добавим позже систему разрешений
    )


@router.post(
    "/validate-token",
    status_code=status.HTTP_200_OK,
    summary="Валидация access токена",
    description="Проверка валидности текущего access токена"
)
async def validate_token(
    current_user: User = Depends(get_current_user)
):
    """Валидация access токена"""
    
    return {
        "valid": True,
        "user_id": current_user.id,
        "role": current_user.role.name
    }