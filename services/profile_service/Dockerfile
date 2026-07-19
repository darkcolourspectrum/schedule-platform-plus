FROM python:3.11-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Создаем рабочую директорию
WORKDIR /app
ENV PYTHONPATH=/app

# Копируем requirements.txt
COPY services/profile_service/requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY shared/ /app/shared/
COPY services/profile_service/ .


# Создаем папки для статических файлов
RUN mkdir -p /app/static/avatars

# Создаем non-root пользователя
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app

# Переключаемся на non-root пользователя
USER appuser

# Открываем порт
EXPOSE 8002

# Команда запуска
CMD ["python", "run_server.py"]