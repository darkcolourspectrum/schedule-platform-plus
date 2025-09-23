FROM python:3.11-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Создаем рабочую директорию
WORKDIR /app

# Копируем requirements.txt
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY . .

# Создаем non-root пользователя
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app

# Переключаемся на non-root пользователя
USER appuser

# Открываем порт
EXPOSE 8001

# Команда запуска
CMD ["python", "run_server.py"]