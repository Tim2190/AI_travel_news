import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/dbname"
    HF_API_KEY: str | None = None
    HF_MODEL_JOURNALIST: str | None = None
    HF_MODEL_EDITOR: str | None = None
    GROQ_API_KEY: str
    GROQ_MODEL: str = "groq/compound"
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_CHAT_ID: str
    SCRAPE_INTERVAL_MINUTES: int = 20
    PUBLISH_INTERVAL_MINUTES: int = 5
    NEWS_MAX_AGE_DAYS: int = 7  # Не брать материалы старше N дней (только актуальные новости)
    # Тематика канала: только материалы, где в заголовке/тексте есть хотя бы одно слово (через запятую)
    TOPIC_KEYWORDS: str = "экономика,финансы,туризм,жаңалық,банк,инфляция,инвестиции,казахстан,саяхат,валюта,рынок"
    GROQ_DELAY_SECONDS: int = 20  # Пауза между запросами к Groq (TPM лимит ~8000)
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
