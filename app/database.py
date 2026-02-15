from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
import datetime
import enum
import logging
from .config import settings

_log = logging.getLogger(__name__)

Base = declarative_base()

class NewsStatus(enum.Enum):
    draft = "draft"
    published = "published"
    error = "error"

class NewsArchive(Base):
    __tablename__ = "news_archive"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500))
    normalized_title = Column(String(500), index=True, nullable=True)  # для проверки дубликатов по заголовку
    original_text = Column(Text)
    rewritten_text = Column(Text, nullable=True)
    source_name = Column(String(255))
    source_url = Column(String(1000), unique=True)
    source_published_at = Column(DateTime, nullable=True)  # дата/время публикации на сайте источника
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

def ensure_migrations():
    """Добавляет колонки, которых нет в уже существующей таблице (например после деплоя на Koyeb)."""
    with engine.connect() as conn:
        try:
            # PostgreSQL: добавить колонку normalized_title, если её нет
            conn.execute(text("""
                ALTER TABLE news_archive
                ADD COLUMN IF NOT EXISTS normalized_title VARCHAR(500)
            """))
            conn.commit()
            _log.info("Migration: normalized_title column ensured.")
        except Exception as e:
            conn.rollback()
            # Может не быть прав ALTER или это не PostgreSQL — не падаем
            _log.warning("Migration normalized_title skipped (already exists or not supported): %s", e)
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_news_archive_normalized_title
                ON news_archive(normalized_title)
            """))
            conn.commit()
        except Exception as e:
            conn.rollback()
            _log.warning("Migration index normalized_title skipped: %s", e)

def init_db():
    Base.metadata.create_all(bind=engine)
    ensure_migrations()

def cleanup_old_tourism_news():
    db = SessionLocal()
    try:
        old_sources = [
            "TengriTravel",
            "Kapital Tourism",
            "Skift",
            "TravelPulse",
            "Travel Weekly",
            "Euronews Travel",
        ]
        deleted = db.query(NewsArchive).filter(NewsArchive.source_name.in_(old_sources)).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
