import logging
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

from app.config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer()


def decode_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode JWT token from Auth Service"""
    try:
        payload = jwt.decode(
            token, 
            settings.jwt_secret_key, 
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError as e:
        logger.error(f"JWT decode error: {e}")
        return None


def extract_user_id_from_token(token: str) -> Optional[int]:
    """Extract user_id from JWT token"""
    payload = decode_jwt_token(token)
    if payload:
        return payload.get("user_id")
    return None


# FastAPI Dependencies
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict:
    """Validate JWT token and return user data"""
    try:
        token = credentials.credentials
        payload = jwt.decode(
            token, 
            settings.jwt_secret_key, 
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError as e:
        logger.error(f"JWT validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )


async def get_current_admin(
    current_user: Dict = Depends(get_current_user)
) -> Dict:
    """Verify user has admin role"""
    user_role = current_user.get("role")
    
    # Обработка разных форматов role (dict или string)
    if isinstance(user_role, dict):
        role_name = user_role.get("name", "")
    elif isinstance(user_role, str):
        role_name = user_role
    else:
        role_name = ""
    
    logger.info(f"Checking admin access for user {current_user.get('user_id')}, role: {role_name}")
    
    if role_name.lower() != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Admin access required. Current role: {role_name}"
        )
    
    return current_user