# Dockerfile для Lead Listener Service
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копируем requirements
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Создаём необходимые директории
RUN mkdir -p logs sessions

# Устанавливаем переменную окружения для Python
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Команда запуска
CMD ["python", "lead_listener/main.py"]

