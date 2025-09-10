#!/bin/bash

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🛑 Остановка Schedule Platform Plus${NC}"
echo "=================================================="

echo -e "${YELLOW}📦 Остановка всех сервисов...${NC}"
docker-compose down

echo -e "${YELLOW}🧹 Очистка неиспользуемых контейнеров...${NC}"
docker system prune -f

echo -e "${GREEN}✅ Все сервисы остановлены!${NC}"

echo ""
echo -e "${BLUE}💡 Дополнительные команды:${NC}"
echo "• Полная очистка (включая volumes): docker-compose down -v"
echo "• Пересборка при следующем запуске: docker-compose build"
echo "• Просмотр запущенных контейнеров: docker ps"