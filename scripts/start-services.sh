#!/bin/bash

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Запуск Schedule Platform Plus${NC}"
echo "=================================================="

# Проверяем что Docker запущен
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker не запущен или не доступен${NC}"
    echo "Пожалуйста, запустите Docker Desktop"
    exit 1
fi

echo -e "${YELLOW}📦 Создание docker сети...${NC}"
docker network create schedule_platform_network 2>/dev/null || true

echo -e "${YELLOW}🗄️  Запуск баз данных...${NC}"
docker-compose up -d postgres redis

echo -e "${YELLOW}⏳ Ожидание готовности баз данных...${NC}"
sleep 10

# Проверяем готовность PostgreSQL
until docker-compose exec postgres pg_isready -U postgres > /dev/null 2>&1; do
  echo -e "${YELLOW}⏳ Ждем PostgreSQL...${NC}"
  sleep 2
done

# Проверяем готовность Redis
until docker-compose exec redis redis-cli ping > /dev/null 2>&1; do
  echo -e "${YELLOW}⏳ Ждем Redis...${NC}"
  sleep 2
done

echo -e "${GREEN}✅ Базы данных готовы!${NC}"

echo -e "${YELLOW}🔧 Применяем миграции...${NC}"

# Миграции для Auth Service
echo -e "${BLUE}📝 Миграции Auth Service...${NC}"
docker-compose run --rm auth-service alembic upgrade head

# Миграции для Profile Service  
echo -e "${BLUE}📝 Миграции Profile Service...${NC}"
docker-compose run --rm profile-service alembic upgrade head

# Миграции для Schedule Service
echo -e "${BLUE}📝 Миграции Schedule Service...${NC}"  
docker-compose run --rm schedule-service alembic upgrade head

echo -e "${YELLOW}🚀 Запуск всех сервисов...${NC}"
docker-compose up -d

echo ""
echo -e "${GREEN}🎉 Все сервисы запущены!${NC}"
echo "=================================================="
echo -e "${BLUE}📚 Доступные сервисы:${NC}"
echo "• Auth Service:     http://localhost:8000/docs"
echo "• Profile Service:  http://localhost:8002/docs"  
echo "• Schedule Service: http://localhost:8001/docs"
echo ""
echo -e "${BLUE}🛠️  Инструменты управления:${NC}"
echo "• PgAdmin:          http://localhost:5050"
echo "  Email: admin@example.com, Password: admin"
echo "• Redis Commander:  http://localhost:8081"
echo ""
echo -e "${YELLOW}📋 Полезные команды:${NC}"
echo "• Просмотр логов:   docker-compose logs -f [service-name]"
echo "• Остановка:        docker-compose down"
echo "• Пересборка:       docker-compose build"
echo ""
echo -e "${GREEN}✨ Готово к разработке фронтенда!${NC}"