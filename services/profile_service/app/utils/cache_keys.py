"""
Утилиты для генерации ключей кэша
Централизованное управление ключами для консистентности
"""

from typing import Optional


class CacheKeys:
    """Генератор ключей кэша для Profile Service"""
    
    # Префиксы для разных типов данных
    PROFILE_PREFIX = "profile"
    DASHBOARD_PREFIX = "dashboard"
    COMMENTS_PREFIX = "comments"
    ACTIVITIES_PREFIX = "activities"
    STATS_PREFIX = "stats"
    REVIEWS_PREFIX = "reviews"
    USERS_PREFIX = "users"
    
    @staticmethod
    def user_profile_full(user_id: int) -> str:
        """Ключ для полного профиля пользователя"""
        return f"{CacheKeys.PROFILE_PREFIX}_full:{user_id}"
    
    @staticmethod
    def user_profile_public(user_id: int) -> str:
        """Ключ для публичного профиля пользователя"""
        return f"{CacheKeys.PROFILE_PREFIX}_public:{user_id}"
    
    @staticmethod
    def dashboard(role: str, user_id: int) -> str:
        """Ключ для дашборда пользователя"""
        return f"{CacheKeys.DASHBOARD_PREFIX}:{role}:{user_id}"
    
    @staticmethod
    def comments_for_target(target_type: str, target_id: int, comment_type: Optional[str] = None) -> str:
        """Ключ для комментариев к объекту"""
        if comment_type:
            return f"{CacheKeys.COMMENTS_PREFIX}:{target_type}:{target_id}:{comment_type}"
        return f"{CacheKeys.COMMENTS_PREFIX}:{target_type}:{target_id}:all"
    
    @staticmethod
    def user_comments(user_id: int) -> str:
        """Ключ для комментариев пользователя"""
        return f"{CacheKeys.COMMENTS_PREFIX}_user:{user_id}"
    
    @staticmethod
    def user_activities(user_id: int) -> str:
        """Ключ для активности пользователя"""
        return f"{CacheKeys.ACTIVITIES_PREFIX}:{user_id}"
    
    @staticmethod
    def user_activities_recent(user_id: int, days: int = 7) -> str:
        """Ключ для недавней активности пользователя"""
        return f"{CacheKeys.ACTIVITIES_PREFIX}_recent:{user_id}:{days}d"
    
    @staticmethod
    def teacher_stats(teacher_id: int) -> str:
        """Ключ для статистики преподавателя"""
        return f"{CacheKeys.STATS_PREFIX}_teacher:{teacher_id}"
    
    @staticmethod
    def teacher_reviews_full(teacher_id: int) -> str:
        """Ключ для полной информации об отзывах преподавателя"""
        return f"{CacheKeys.REVIEWS_PREFIX}_teacher_full:{teacher_id}"
    
    @staticmethod
    def teacher_reviews_rating(teacher_id: int) -> str:
        """Ключ для рейтинга преподавателя"""
        return f"{CacheKeys.REVIEWS_PREFIX}_teacher_rating:{teacher_id}"
    
    @staticmethod
    def system_stats() -> str:
        """Ключ для общей статистики системы"""
        return f"{CacheKeys.STATS_PREFIX}_system"
    
    @staticmethod
    def users_by_role(role: str) -> str:
        """Ключ для списка пользователей по роли"""
        return f"{CacheKeys.USERS_PREFIX}_by_role:{role}"
    
    @staticmethod
    def public_profiles(page: int = 0) -> str:
        """Ключ для списка публичных профилей"""
        return f"{CacheKeys.PROFILE_PREFIX}_public_list:page_{page}"
    
    @staticmethod
    def search_profiles(query: str) -> str:
        """Ключ для результатов поиска профилей"""
        # Нормализуем запрос для ключа
        normalized_query = query.lower().strip().replace(" ", "_")[:50]
        return f"{CacheKeys.PROFILE_PREFIX}_search:{normalized_query}"
    
    @staticmethod
    def available_teachers() -> str:
        """Ключ для списка доступных преподавателей"""
        return f"{CacheKeys.USERS_PREFIX}_teachers_available"
    
    @staticmethod
    def student_stats(student_id: int) -> str:
        """Ключ для статистики студента"""
        return f"{CacheKeys.STATS_PREFIX}_student:{student_id}"
    
    # Методы для генерации паттернов очистки кэша
    
    @staticmethod
    def user_cache_pattern(user_id: int) -> str:
        """Паттерн для очистки всего кэша пользователя"""
        return f"*:{user_id}*"
    
    @staticmethod
    def profile_cache_pattern(user_id: int) -> str:
        """Паттерн для очистки кэша профиля пользователя"""
        return f"{CacheKeys.PROFILE_PREFIX}*:{user_id}*"
    
    @staticmethod
    def dashboard_cache_pattern(user_id: int) -> str:
        """Паттерн для очистки кэша дашбордов пользователя"""
        return f"{CacheKeys.DASHBOARD_PREFIX}:*:{user_id}"
    
    @staticmethod
    def comments_cache_pattern(target_type: str, target_id: int) -> str:
        """Паттерн для очистки кэша комментариев к объекту"""
        return f"{CacheKeys.COMMENTS_PREFIX}:{target_type}:{target_id}:*"
    
    @staticmethod
    def teacher_cache_pattern(teacher_id: int) -> str:
        """Паттерн для очистки кэша преподавателя"""
        return f"*teacher*:{teacher_id}*"
    
    @staticmethod
    def stats_cache_pattern() -> str:
        """Паттерн для очистки кэша статистики"""
        return f"{CacheKeys.STATS_PREFIX}*"
    
    # Методы для работы с TTL
    
    @staticmethod
    def get_ttl_for_key_type(key: str) -> int:
        """
        Получение рекомендуемого TTL для типа ключа
        
        Args:
            key: Ключ кэша
            
        Returns:
            TTL в секундах
        """
        from app.config import settings
        
        if key.startswith(CacheKeys.PROFILE_PREFIX):
            return settings.cache_user_profile_ttl
        elif key.startswith(CacheKeys.DASHBOARD_PREFIX):
            return settings.cache_dashboard_ttl
        elif key.startswith(CacheKeys.COMMENTS_PREFIX):
            return settings.cache_comments_ttl
        elif key.startswith(CacheKeys.ACTIVITIES_PREFIX):
            return settings.cache_activity_ttl
        elif key.startswith(CacheKeys.STATS_PREFIX):
            return settings.cache_dashboard_ttl  # Статистика как дашборд
        elif key.startswith(CacheKeys.REVIEWS_PREFIX):
            return settings.cache_comments_ttl  # Отзывы как комментарии
        else:
            return 300  # 5 минут по умолчанию
    
    @staticmethod
    def is_user_specific_key(key: str, user_id: int) -> bool:
        """
        Проверка, относится ли ключ к конкретному пользователю
        
        Args:
            key: Ключ кэша
            user_id: ID пользователя
            
        Returns:
            True если ключ относится к пользователю
        """
        user_patterns = [
            f":{user_id}",
            f":{user_id}:",
            f"_{user_id}",
            f"_{user_id}_"
        ]
        
        return any(pattern in key for pattern in user_patterns)
    
    @staticmethod
    def extract_user_id_from_key(key: str) -> Optional[int]:
        """
        Извлечение ID пользователя из ключа кэша
        
        Args:
            key: Ключ кэша
            
        Returns:
            ID пользователя или None
        """
        try:
            # Пытаемся найти паттерны с ID пользователя
            parts = key.split(':')
            for part in parts:
                if part.isdigit():
                    return int(part)
            
            # Пытаемся найти паттерны с подчеркиванием
            parts = key.split('_')
            for part in parts:
                if part.isdigit():
                    return int(part)
            
            return None
            
        except (ValueError, IndexError):
            return None


# Создаем экземпляр для удобства использования
cache_keys = CacheKeys()