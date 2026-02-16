import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # --- БАЗА ДАННЫХ ---
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/dbname"

    # --- СТАРЫЕ НАСТРОЙКИ (Можно оставить, чтобы не ломать зависимости) ---
    HF_API_KEY: str | None = None
    HF_MODEL_JOURNALIST: str | None = None
    HF_MODEL_EDITOR: str | None = None

    # --- НЕЙРОСЕТИ ---
    # 1. Groq (Для новостей на Русском) - Llama 3
    GROQ_API_KEY: str
    GROQ_MODEL: str = "groq/compound" 
    GROQ_DELAY_SECONDS: int = 20  # Пауза, чтобы не упереться в лимиты TPM

    # 2. Google Gemini (Для новостей на Казахском)
    # Используем модель Flash, она самая быстрая и экономичная
    GOOGLE_API_KEY: str
    GEMINI_MODEL: str = "gemini-2.5-flash" 

    # --- TELEGRAM ---
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_CHAT_ID: str

    # --- РАСПИСАНИЕ (Оптимизировано под "Ленту") ---
    SCRAPE_INTERVAL_MINUTES: int = 5    # Сканируем источники ЧАСТО (раз в 5 минут)
    PUBLISH_INTERVAL_MINUTES: int = 15  # Публикуем РАЗМЕРЕННО (раз в 15 минут = 3 поста в час)

    # --- ФИЛЬТРЫ ---
    NEWS_MAX_AGE_DAYS: int = 2  # Берем только свежие новости (не старше 2 дней)
    
    # Ключевые слова (добавил слова для гос.сектора: бюджет, налог, закон)
    TOPIC_KEYWORDS: str = "экономика,финансы,туризм,жаңалық,банк,инфляция,инвестиции,казахстан,саяхат,валюта,рынок,бюджет,салық,заң,әкім,министр"
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
