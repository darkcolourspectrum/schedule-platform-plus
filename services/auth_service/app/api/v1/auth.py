from fastapi import APIRouter, Depends, Response, Request, status
from typing import Optional
from fastapi.responses import JSONResponse

from app.dependencies import (
    get_auth_service,
    get_client_info,
    get_current_user,
    verify_internal_api_key
)
from app.services.auth_service import AuthService
from app.services.vk_id_client import vk_id_client, VkIdError
from app.core.security import (
    create_vk_registration_token,
    decode_vk_registration_token,
)
from app.core.exceptions import RateLimitExceededException
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    AuthResponse,
    RefreshTokenRequest,
    AccessTokenResponse,
    LogoutRequest,
    MessageResponse,
    VkLoginRequest,
    VkRegisterRequest,
    VkRegisterCompleteRequest,
    VkRegisterResponse,
    InternalVkLoginRequest,
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
    request: Request,
    response: Response,
    client_info: dict = Depends(get_client_info),
    auth_service: AuthService = Depends(get_auth_service)
):
    """Регистрация нового пользователя с rate limiting"""
    
    try:
        result = await auth_service.register_user(
            email=user_data.email,
            password=user_data.password,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            phone=user_data.phone,
            privacy_policy_accepted=user_data.privacy_policy_accepted,
            ip_address=client_info.get("ip_address")
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
        
    except RateLimitExceededException as e:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": f"Rate limit exceeded. Try again in {e.retry_after} seconds"},
            headers={"Retry-After": str(e.retry_after)}
        )

@router.post(
    "/vk/register",
    response_model=VkRegisterResponse,
    summary="Регистрация через VK (шаг 1)",
    description=(
        "Шаг 1 регистрации через VK. Обменивает код на проверенный vk_id "
        "(один раз — код одноразовый). Если email известен (из тела запроса "
        "или из данных VK) — создаёт аккаунт и возвращает токены "
        "(needs_email=false). Если email нет — аккаунт не создаётся, "
        "возвращается needs_email=true с registration_token и именем для "
        "второго шага."
    ),
)
async def vk_register(
    payload: VkRegisterRequest,
    request: Request,
    response: Response,
    client_info: dict = Depends(get_client_info),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Шаг 1 регистрации через VK.
 
    Код обменивается РОВНО ОДИН раз. Дальше развилка по email:
      - email есть -> создаём аккаунт сразу (vk_register) -> токены + cookie;
      - email нет  -> возвращаем registration_token (подписанный нами,
        с проверенным vk_id и именем) для второго шага.
    """
    # 1. Единственный обмен кода. Достаём vk_id и доступный профиль.
    try:
        vk_result = await vk_id_client.exchange_code(
            code=payload.code,
            device_id=payload.device_id,
            code_verifier=payload.code_verifier,
            state=payload.state,
        )
    except VkIdError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": f"VK authorization failed: {exc}"},
        )
 
    # Имя/фамилия: берём из данных VK, с безопасными запасными значениями
    # (VK обычно их отдаёт; пустые строки на крайний случай, чтобы не упасть).
    first_name = vk_result.first_name or ""
    last_name = vk_result.last_name or ""
 
    # 2. Определяем итоговый email: приоритет — тело запроса, затем VK.
    final_email = payload.email or vk_result.email
 
    # 3a. Email нет ниоткуда -> второй шаг. Аккаунт НЕ создаём.
    if not final_email:
        registration_token = create_vk_registration_token(
            vk_id=vk_result.vk_id,
            first_name=first_name,
            last_name=last_name,
            vk_email=vk_result.email,
        )
        return VkRegisterResponse(
            needs_email=True,
            registration_token=registration_token,
            first_name=first_name,
            last_name=last_name,
        )
 
    # 3b. Email есть -> создаём аккаунт сразу.
    result = await auth_service.vk_register(
        vk_id=vk_result.vk_id,
        email=final_email,
        first_name=first_name,
        last_name=last_name,
        device_info=client_info.get("device_info"),
        ip_address=client_info.get("ip_address"),
        user_agent=client_info.get("user_agent"),
    )
 
    response.set_cookie(
        key="refresh_token",
        value=result["tokens"]["refresh_token"],
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
 
    return VkRegisterResponse(
        needs_email=False,
        auth=AuthResponse(
            user=result["user"],
            tokens={
                "access_token": result["tokens"]["access_token"],
                "refresh_token": result["tokens"]["refresh_token"],
                "token_type": result["tokens"]["token_type"],
            },
        ),
    )

@router.post(
    "/vk/register/complete",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация через VK (шаг 2)",
    description=(
        "Шаг 2 регистрации через VK. Вызывается, когда на шаге 1 email не "
        "был получен. Принимает registration_token (выданный на шаге 1, с "
        "проверенным vk_id) и введённый email. Создаёт аккаунт. Повторный "
        "обмен кода не нужен."
    ),
)
async def vk_register_complete(
    payload: VkRegisterCompleteRequest,
    request: Request,
    response: Response,
    client_info: dict = Depends(get_client_info),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Шаг 2 регистрации через VK.
 
    vk_id берётся из registration_token (подписан нами на шаге 1, подделать
    нельзя). Код VK тут уже не участвует — он был обменян на шаге 1.
    """
    # Проверяем наш токен с шага 1.
    token_data = decode_vk_registration_token(payload.registration_token)
    if not token_data:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Invalid or expired registration token"},
        )
 
    # Создаём аккаунт по проверенному vk_id из токена + введённому email.
    result = await auth_service.vk_register(
        vk_id=token_data["vk_id"],
        email=payload.email,
        first_name=token_data.get("first_name") or "",
        last_name=token_data.get("last_name") or "",
        device_info=client_info.get("device_info"),
        ip_address=client_info.get("ip_address"),
        user_agent=client_info.get("user_agent"),
    )
 
    response.set_cookie(
        key="refresh_token",
        value=result["tokens"]["refresh_token"],
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
 
    return AuthResponse(
        user=result["user"],
        tokens={
            "access_token": result["tokens"]["access_token"],
            "refresh_token": result["tokens"]["refresh_token"],
            "token_type": result["tokens"]["token_type"],
        },
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Вход в систему",
    description="Аутентификация пользователя по email и паролю"
)
async def login(
    credentials: LoginRequest,
    request: Request,
    response: Response,
    client_info: dict = Depends(get_client_info),
    auth_service: AuthService = Depends(get_auth_service)
):
    """Вход в систему с rate limiting"""
    
    try:
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
        
    except RateLimitExceededException as e:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": f"Rate limit exceeded. Try again in {e.retry_after} seconds"},
            headers={"Retry-After": str(e.retry_after)}
        )

@router.post(
    "/vk/login",
    response_model=AuthResponse,
    summary="Вход через VK",
    description=(
        "Вход в систему через VK ID. Принимает code/device_id/code_verifier "
        "из окна VK ID на фронте, серверно обменивает их на проверенный vk_id "
        "и выдаёт токены для уже существующего аккаунта. Если аккаунта с таким "
        "vk_id нет - возвращает 404 (фронт показывает регистрацию через VK)."
    ),
)
async def vk_login(
    payload: VkLoginRequest,
    request: Request,
    response: Response,
    client_info: dict = Depends(get_client_info),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Вход через VK.
 
    Поток:
        1. Обмениваем code -> проверенный vk_id (vk_id_client, поход в VK).
        2. По vk_id находим пользователя и выдаём токены (auth_service.vk_login).
        3. Ставим refresh в httpOnly cookie - так же, как обычный login,
           чтобы фронтовый сценарий не отличался.
 
    Коды ответов:
        200 - вошли, тело AuthResponse;
        404 - нет аккаунта с таким vk_id (VkUserNotFoundException из сервиса) -
              фронт показывает регистрацию через VK;
        400 - обмен кода не удался (VkIdError): код истёк/повторно использован,
              неверный code_verifier/device_id и т.п.
    """
    # 1. Обмен кода на проверенный vk_id. Ошибки обмена -> 400 с понятным detail.
    try:
        vk_result = await vk_id_client.exchange_code(
            code=payload.code,
            device_id=payload.device_id,
            code_verifier=payload.code_verifier,
            state=payload.state,
        )
    except VkIdError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": f"VK authorization failed: {exc}"},
        )
 
    # 2. Вход по vk_id. Если пользователя нет - vk_login бросит
    #    VkUserNotFoundException (это AuthException -> FastAPI отдаст 404).
    result = await auth_service.vk_login(
        vk_id=vk_result.vk_id,
        device_info=client_info.get("device_info"),
        ip_address=client_info.get("ip_address"),
        user_agent=client_info.get("user_agent"),
    )
 
    # 3. Refresh в cookie - один в один как в login/register.
    response.set_cookie(
        key="refresh_token",
        value=result["tokens"]["refresh_token"],
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,  # 7 дней
    )
 
    return AuthResponse(
        user=result["user"],
        tokens={
            "access_token": result["tokens"]["access_token"],
            "refresh_token": result["tokens"]["refresh_token"],
            "token_type": result["tokens"]["token_type"],
        },
    )


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    summary="Обновление access токена",
    description=(
        "Получение нового access токена по refresh токену. Источник "
        "refresh-токена: сначала httpOnly cookie (веб-фронт), затем тело "
        "запроса (клиенты без cookie, например бот)."
    )
)
async def refresh_token(
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
    body: Optional[RefreshTokenRequest] = None,
):
    """Обновление access токена с rate limiting.

    refresh-токен берётся приоритетно из cookie (поведение веб-фронта
    не меняется), а если cookie нет - из тела запроса (RefreshTokenRequest).
    Это нужно не-браузерным клиентам (бот), у которых cookie отсутствует.
    """

    # 1. Приоритет - cookie (как было раньше, поведение фронта не меняется).
    refresh_token = request.cookies.get("refresh_token")

    # 2. Fallback - тело запроса, если cookie нет.
    if not refresh_token and body is not None:
        refresh_token = body.refresh_token

    if not refresh_token:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Refresh token not provided"}
        )

    try:
        result = await auth_service.refresh_access_token(refresh_token, user_id=None)

        return AccessTokenResponse(
            access_token=result["access_token"],
            token_type=result["token_type"]
        )

    except RateLimitExceededException as e:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": f"Rate limit exceeded. Try again in {e.retry_after} seconds"},
            headers={"Retry-After": str(e.retry_after)}
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
    """Выход из системы с Redis blacklist"""
    
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
    """Выход со всех устройств с очисткой Redis кеша"""
    
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
        studio_name=None,  # Studio data now managed by admin_service
        is_admin=current_user.is_admin,
        is_teacher=current_user.is_teacher,
        is_student=current_user.is_student,
        vk_linked=current_user.vk_id is not None,
        permissions=[]
    )


@router.post(
    "/validate-token",
    status_code=status.HTTP_200_OK,
    summary="Валидация access токена",
    description="Проверка валидности текущего access токена с Redis blacklist (для внутренних сервисов)"
)
async def validate_token(
    current_user: User = Depends(get_current_user),
    internal_key_valid: bool = Depends(verify_internal_api_key)
):
    """
    Валидация access токена с использованием Redis кеша
    
    ИСПРАВЛЕНО: Теперь требует X-Internal-API-Key для защиты от внешних запросов
    """
    
    return {
        "valid": True,
        "user_id": current_user.id,
        "role": current_user.role.name,
        "email": current_user.email,
        "studio_id": current_user.studio_id
    }


@router.get(
    "/stats",
    summary="Статистика аутентификации",
    description="Статистика rate limiting и blacklist кеша (только для администраторов)"
)
async def get_auth_stats(
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    """Получение статистики аутентификации"""
    
    # Проверяем права доступа
    if not current_user.is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Access denied. Admin role required"}
        )
    
    stats = await auth_service.get_auth_stats()
    return stats

@router.post(
    "/internal/vk-login",
    response_model=AuthResponse,
    summary="Внутренний вход по vk_id (для бота)",
    description=(
        "Только для внутренних сервисов (X-Internal-API-Key). Принимает "
        "доверенный vk_id (бот получает его из Long Poll сообщества) и "
        "выдаёт токены платформы для существующего пользователя. "
        "404, если аккаунта с таким vk_id нет."
    ),
)
async def internal_vk_login(
    payload: InternalVkLoginRequest,
    request: Request,
    client_info: dict = Depends(get_client_info),
    internal_key_valid: bool = Depends(verify_internal_api_key),
    auth_service: AuthService = Depends(get_auth_service),
):
    result = await auth_service.vk_login(
        vk_id=payload.vk_id,
        device_info=client_info.get("device_info"),
        ip_address=client_info.get("ip_address"),
        user_agent=client_info.get("user_agent"),
    )
    return AuthResponse(
        user=result["user"],
        tokens={
            "access_token": result["tokens"]["access_token"],
            "refresh_token": result["tokens"]["refresh_token"],
            "token_type": result["tokens"]["token_type"],
        },
    )