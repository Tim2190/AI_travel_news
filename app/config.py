import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/dbname"
    HF_API_KEY: str
    HF_MODEL: str = "mistralai/Mixtral-8x7B-Instruct-v0.1"
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_CHAT_ID: str
    SCRAPE_INTERVAL_MINUTES: int = 30
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
