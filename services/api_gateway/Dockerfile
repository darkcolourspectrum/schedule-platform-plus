FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app

# Копируем зависимости
COPY services/api_gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY services/api_gateway/app /app/app
COPY shared/ /app/shared/

# Запуск
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--reload"]