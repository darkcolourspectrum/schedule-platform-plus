"""Database package initialization"""

from app.database.connection import (
    get_db,
    get_schedule_db,
    get_auth_db,
    check_database_connection,
    check_auth_database_connection
)
from app.database.redis_client import redis_client

__all__ = [
    "get_db",
    "get_schedule_db",
    "get_auth_db",
    "redis_client",
    "check_database_connection",
    "check_auth_database_connection",
]
