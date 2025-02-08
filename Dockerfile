# Этап 1: Сборка
FROM python:3.12.2-slim AS builder

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем только файл с зависимостями
COPY requirements.txt .

# Устанавливаем зависимости в отдельную директорию
RUN pip install --user --no-cache-dir -r requirements.txt

# Этап 2: Финальный образ
FROM python:3.12.2-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем установленные зависимости из этапа builder
COPY --from=builder /root/.local /root/.local

# Копируем исходный код
COPY . .

# Убедимся, что скрипты в .local доступны для выполнения
ENV PATH=/root/.local/bin:$PATH

# Указываем команду для запуска бота
CMD ["python", "redmine_bot.py"]