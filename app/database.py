from sqlalchemy import Column, Integer, String, Text, DateTime, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
import datetime
import enum
from .config import settings

Base = declarative_base()

class NewsStatus(enum.Enum):
    draft = "draft"
    published = "published"
    error = "error"

class NewsArchive(Base):
    __tablename__ = "news_archive"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500))
    original_text = Column(Text)
    rewritten_text = Column(Text, nullable=True)
    source_name = Column(String(255))
    source_url = Column(String(1000), unique=True)
    telegram_post_id = Column(String(100), nullable=True)
    image_url = Column(String(1000), nullable=True) # or image_prompt
    status = Column(String(20), default="draft")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    published_at = Column(DateTime, nullable=True)
    error_log = Column(Text, nullable=True)

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # Проверяет соединение перед каждым запросом
    pool_recycle=300,    # Пересоздает соединение каждые 5 минут
    pool_size=10,        # Размер пула
    max_overflow=20      # Максимальное количество дополнительных соединений
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
