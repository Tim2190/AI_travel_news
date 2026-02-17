# Берем готовый образ, где уже есть Python + Playwright + Chrome + Все драйверы
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Папка внутри сервера
WORKDIR /app

# Копируем твои файлы
COPY . .

# Ставим библиотеки (FastAPI, SQLAlchemy и т.д.)
RUN pip install --no-cache-dir -r requirements.txt

# Запускаем бота
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
