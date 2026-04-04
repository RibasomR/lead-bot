# Dockerfile для Admin Bot
FROM python:3.11-slim

# Метаданные
LABEL maintainer="LeadHunter Team"
LABEL description="Admin Bot for LeadHunter system"

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY . .

# Создаём директории для логов и сессий
RUN mkdir -p logs sessions

# Устанавливаем переменную окружения для Python
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Указываем пользователя (не root для безопасности)
RUN useradd -m -u 1000 leadhunter && \
    chown -R leadhunter:leadhunter /app
USER leadhunter

# Команда запуска
CMD ["python", "admin_bot/main.py"]

