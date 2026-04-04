#!/bin/bash

## Скрипт полной очистки проекта LeadHunter
## Удаляет контейнеры, образы, volumes, логи и временные файлы

set -e

echo "╔════════════════════════════════════════════════════════════╗"
echo "║         LeadHunter — Скрипт очистки проекта               ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Функция для вывода с цветом
print_info() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Проверка запуска из корня проекта
if [ ! -f "docker-compose.yml" ]; then
    print_error "Запустите скрипт из корневой директории проекта!"
    exit 1
fi

echo "Этот скрипт удалит:"
echo "  • Все Docker контейнеры LeadHunter"
echo "  • Все Docker образы LeadHunter"
echo "  • Все Docker volumes (включая БД!)"
echo "  • Все логи"
echo "  • Все временные файлы Python"
echo "  • Сессии userbot (опционально)"
echo ""
read -p "Продолжить? (y/N): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_warning "Очистка отменена"
    exit 0
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🐳 Очистка Docker"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Остановка и удаление контейнеров
if docker compose ps -q 2>/dev/null | grep -q .; then
    print_info "Остановка контейнеров..."
    docker compose down -v 2>/dev/null || true
else
    print_warning "Контейнеры не запущены"
fi

# Удаление образов
print_info "Удаление образов..."
docker images | grep "lead-hunter" | awk '{print $3}' | xargs -r docker rmi -f 2>/dev/null || true
docker images | grep "leadhunter" | awk '{print $3}' | xargs -r docker rmi -f 2>/dev/null || true

# Удаление volumes
print_info "Удаление volumes..."
docker volume ls | grep "lead-hunter" | awk '{print $2}' | xargs -r docker volume rm -f 2>/dev/null || true
docker volume ls | grep "leadhunter" | awk '{print $2}' | xargs -r docker volume rm -f 2>/dev/null || true

# Очистка неиспользуемых ресурсов
print_info "Очистка неиспользуемых ресурсов Docker..."
docker system prune -f --volumes 2>/dev/null || true

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📝 Очистка логов"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Удаление логов
if [ -d "logs" ]; then
    print_info "Удаление файлов логов..."
    rm -rf logs/*.log 2>/dev/null || true
    print_info "Создание пустой директории logs..."
    mkdir -p logs
    touch logs/.gitkeep
else
    print_warning "Директория logs не найдена"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🐍 Очистка Python временных файлов"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Удаление __pycache__
print_info "Удаление __pycache__..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Удаление .pyc файлов
print_info "Удаление .pyc файлов..."
find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Удаление .pyo файлов
print_info "Удаление .pyo файлов..."
find . -type f -name "*.pyo" -delete 2>/dev/null || true

# Удаление .pytest_cache
if [ -d ".pytest_cache" ]; then
    print_info "Удаление .pytest_cache..."
    rm -rf .pytest_cache
fi

# Удаление .coverage
if [ -f ".coverage" ]; then
    print_info "Удаление .coverage..."
    rm -f .coverage
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📱 Очистка сессий userbot (опционально)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -d "sessions" ] && [ "$(ls -A sessions 2>/dev/null)" ]; then
    echo ""
    print_warning "Найдены сессии userbot в директории sessions/"
    print_warning "Их удаление потребует повторной авторизации аккаунтов!"
    echo ""
    read -p "Удалить сессии userbot? (y/N): " -n 1 -r
    echo ""
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Удаление сессий userbot..."
        rm -rf sessions/*.session 2>/dev/null || true
        rm -rf sessions/*.session-journal 2>/dev/null || true
        print_info "Создание пустой директории sessions..."
        mkdir -p sessions
        touch sessions/.gitkeep
    else
        print_warning "Сессии userbot сохранены"
    fi
else
    print_warning "Сессии userbot не найдены"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🗑️  Очистка других временных файлов"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Удаление .DS_Store (macOS)
print_info "Удаление .DS_Store файлов..."
find . -name ".DS_Store" -delete 2>/dev/null || true

# Удаление Thumbs.db (Windows)
print_info "Удаление Thumbs.db файлов..."
find . -name "Thumbs.db" -delete 2>/dev/null || true

# Удаление временных файлов редакторов
print_info "Удаление временных файлов редакторов..."
find . -name "*~" -delete 2>/dev/null || true
find . -name "*.swp" -delete 2>/dev/null || true
find . -name "*.swo" -delete 2>/dev/null || true

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                  ✅ Очистка завершена!                     ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Что было удалено:"
echo "  ✓ Docker контейнеры и образы"
echo "  ✓ Docker volumes (включая БД)"
echo "  ✓ Логи"
echo "  ✓ Python временные файлы"
echo "  ✓ Временные файлы ОС"
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "  ✓ Сессии userbot"
fi
echo ""
echo "Для повторного запуска проекта:"
echo "  1. docker compose build"
echo "  2. docker compose up -d"
echo "  3. docker compose exec admin_bot python -m alembic upgrade head"
echo "  4. docker compose exec lead_listener python auth_cli.py"
echo ""

