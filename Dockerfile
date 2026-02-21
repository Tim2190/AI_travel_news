# Обновляем версию до v1.58.0-jammy, как просит ошибка
FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

WORKDIR /app

COPY . .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем браузеры
RUN playwright install chromium
RUN playwright install-deps

# ВАЖНО: Убрали скобки, чтобы Render подставил свой порт
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
