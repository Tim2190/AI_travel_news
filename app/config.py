import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # --- БАЗА ДАННЫХ (Supabase) ---
    # Мы убрали дефолтное значение. Теперь, если ты не задашь DATABASE_URL в Koyeb, 
    # бот сразу упадет с ошибкой, а не будет пытаться подключиться к "localhost".
    DATABASE_URL: str 

    # --- НЕЙРОСЕТИ (Gemini Ensemble) ---
    # Мы используем один ключ для всех моделей
    GEMINI_API_KEY: str
    
    # Модели (можно переопределить через ENV, но лучше оставить дефолты)
    # Используем 2.0 Flash как основную "рабочую лошадку"
    GEMINI_MODEL: str = "gemini-2.0-flash"

    GROQ_API_KEY: str = ""

    # --- TELEGRAM ---
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_CHAT_ID: str

    # --- РАСПИСАНИЕ ---
    # 20 минут скрапинг (чтобы не спамить базу)
    SCRAPE_INTERVAL_MINUTES: int = 20   
    # 15 минут публикация (оптимальный ритм)
    PUBLISH_INTERVAL_MINUTES: int = 15  

    # --- ФИЛЬТРЫ ---
    # Ставим 1 день. Всё что старше — нам не нужно.
    NEWS_MAX_AGE_DAYS: int = 1 
    
    # Ключевые слова
    TOPIC_KEYWORDS: str = "эконом,финанс,туриз,жаңалық,банк,инфляц,инвестиц,казахст,саяхат,валют,рынок,бюджет,салық,заң,әкім,министр,президент,үкімет,тенге,образов,наук,школ,врач,здравоохр,медиц,білім,ғылым,мектеп,денсаулық,дәрігер,колледж,студент,аурухана,емхана"
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
