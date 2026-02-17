import asyncio
import html
import logging
import re
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from difflib import SequenceMatcher
from .database import SessionLocal, NewsArchive, NewsStatus
from .scraper import scraper
from .rewriter import rewriter
from .publisher import publisher
from .config import settings
import requests

logger = logging.getLogger(__name__)

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def is_fuzzy_duplicate(new_title: str, existing_titles: list, threshold=0.65) -> bool:
    """Проверяет, похож ли заголовок на один из существующих."""
    if not new_title:
        return False
    new_lower = new_title.lower()
    for old_title in existing_titles:
        if not old_title:
            continue
        similarity = SequenceMatcher(None, new_lower, old_title.lower()).ratio()
        if similarity > threshold:
            return True
    return False

def is_text_kazakh(text: str) -> bool:
    """Определяет язык текста для выбора правильного лимита."""
    if not text: return False
    # Расширенный набор символов казахского алфавита
    kz_chars = r'[әіңғүұқөһӘІҢҒҮҰҚӨҺ]'
    return bool(re.search(kz_chars, text))

# --- ОСНОВНЫЕ ЗАДАЧИ ---

async def scrape_news_task():
    """
    Scrape news, select up to 5 best items and store as drafts.
    """
    db = SessionLocal()
    try:
        logger.info("Starting scraping cycle...")
        new_items = scraper.scrape()
        if not new_items:
            logger.warning("No news found from any direct sources.")
            return

        # Фильтрация по ключевым словам
        topic_keywords = [k.strip().lower() for k in settings.TOPIC_KEYWORDS.split(",") if k.strip()]
        def matches_topic(item):
            if not topic_keywords:
                return True
            title = (item.get("title") or "").lower()
            text = (item.get("original_text") or "").lower()
            combined = f"{title} {text}"
            return any(kw in combined for kw in topic_keywords)
        
        new_items = [i for i in new_items if matches_topic(i)]
        if not new_items:
            logger.warning("No news matching topic keywords.")
            return

        # --- ЖЕСТКАЯ ПРОВЕРКА АКТУАЛЬНОСТИ ---
        cutoff = datetime.utcnow() - timedelta(days=settings.NEWS_MAX_AGE_DAYS)
        def is_recent(item):
            pub = item.get("published_at")
            
            # ИСПРАВЛЕНО: Если даты нет — считаем новость подозрительной и НЕ берем
            if pub is None:
                logger.warning(f"Rejected (no date): {item.get('title', 'Unknown')[:50]}...")
                return False
                
            if getattr(pub, "tzinfo", None):
                pub = pub.replace(tzinfo=None)
            
            check_ok = pub >= cutoff
            if not check_ok:
                logger.info(f"Skipped (outdated, from {pub}): {item.get('title')[:50]}...")
            return check_ok
        
        new_items = [i for i in new_items if is_recent(i)]
        if not new_items:
            logger.warning("No recent news found after filtering dates.")
            return

        # Сортировка и скоринг (приоритет важным темам)
        def normalize_title(title):
            if not title: return ""
            return re.sub(r"\s+", " ", title.strip().lower())[:500]

        def score(item):
            text = (item.get("original_text") or "").lower()
            title = (item.get("title") or "").lower()
            base = min(len(text) / 500, 3) 
            keywords = ["экономика", "финансы", "инвестиции", "президент", "закон", "правительство"]
            kw_score = sum(2 for k in keywords if k in text or k in title)
            return base + kw_score

        scored = sorted(new_items, key=score, reverse=True)
        top_items = scored[:10] # Берем с запасом для проверки дублей

        # Загрузка истории для защиты от повторов
        check_date = datetime.utcnow() - timedelta(days=3)
        recent_records = db.query(NewsArchive.title).filter(NewsArchive.created_at >= check_date).all()
        existing_titles_cache = [row[0] for row in recent_records if row[0]]

        added_count = 0
        for item in top_items:
            if added_count >= 5: break # Лимит на один цикл сбора

            current_title = item["title"]
            # Проверка по URL
            if db.query(NewsArchive).filter(NewsArchive.source_url == item["source_url"]).first():
                continue

            # Проверка по нормализованному заголовку
            norm = normalize_title(current_title)
            if norm and db.query(NewsArchive).filter(NewsArchive.normalized_title == norm).first():
                continue

            # Fuzzy matching
            if is_fuzzy_duplicate(current_title, existing_titles_cache, threshold=0.65):
                logger.info(f"Skipping fuzzy duplicate: '{current_title}'")
                continue

            news_entry = NewsArchive(
                title=current_title,
                normalized_title=norm or None,
                original_text=item["original_text"],
                source_name=item["source_name"],
                source_url=item["source_url"],
                source_published_at=item.get("published_at"),
                image_url=item["image_url"],
                status=NewsStatus.draft.value
            )
            db.add(news_entry)
            added_count += 1
            existing_titles_cache.append(current_title)

        db.commit()
        logger.info(f"Successfully added {added_count} prioritized news items to drafts.")
    except Exception as e:
        logger.error(f"Error in scrape_news_task: {str(e)}")
    finally:
        db.close()

async def process_news_task():
    """
    Обработка очереди публикаций. 
    ИСПРАВЛЕНО: Бот больше не зависает, если нет новостей на выбранном языке.
    """
    db = SessionLocal()
    try:
        logger.info("Starting news processing cycle (with limits)...")

        # 1. СТАТИСТИКА ЗА СЕГОДНЯ
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        published_today = db.query(NewsArchive).filter(
            NewsArchive.status == NewsStatus.published.value,
            NewsArchive.published_at >= today_start
        ).all()

        kz_count = sum(1 for p in published_today if is_text_kazakh(p.rewritten_text or p.title))
        ru_count = len(published_today) - kz_count

        # Ищем время последней KZ публикации
        last_kz_pub_time = datetime.min
        for p in published_today:
            if is_text_kazakh(p.rewritten_text or p.title):
                if p.published_at and p.published_at > last_kz_pub_time:
                    last_kz_pub_time = p.published_at

        logger.info(f"Today's stats: KZ {kz_count}/20, RU {ru_count}/40")

        # 2. ОПРЕДЕЛЕНИЕ ПРИОРИТЕТНОГО ЯЗЫКА
        target_lang = "RU"
        time_since_kz = datetime.utcnow() - last_kz_pub_time
        
        # Если прошел час и лимит KZ не исчерпан — приоритет KZ
        if kz_count < 20 and time_since_kz >= timedelta(hours=1):
            target_lang = "KZ"
            logger.info("Priority target: Kazakh (Hour interval reached)")

        # 3. ПОИСК ЧЕРНОВИКА
        drafts = db.query(NewsArchive).filter(
            NewsArchive.status == NewsStatus.draft.value
        ).order_by(NewsArchive.created_at.asc()).all()

        if not drafts:
            logger.info("No drafts available in database.")
            return

        selected = None
        # Сначала пытаемся найти новость на целевом языке
        for d in drafts:
            is_kz = is_text_kazakh(d.original_text)
            if target_lang == "KZ" and is_kz:
                selected = d
                break
            if target_lang == "RU" and not is_kz:
                selected = d
                break
        
        # FALLBACK: Если на целевом языке ничего нет, берем ПЕРВУЮ ЛЮБУЮ новость из очереди
        if not selected:
            logger.info(f"No drafts found for {target_lang}. Taking first available draft to avoid idle time.")
            selected = drafts[0]

        # 4. РЕРАЙТ И ПУБЛИКАЦИЯ
        try:
            # Обновляем объект из базы, чтобы избежать проблем с сессией
            selected = db.merge(selected)
            logger.info(f"--- Processing: {selected.title} ---")
            
            rewritten = await rewriter.rewrite(selected.original_text)
            if not rewritten:
                selected.status = NewsStatus.error.value
                db.commit()
                return
            
            # ФОРМАТИРОВАНИЕ И ДОБАВЛЕНИЕ ДИСКЛЕЙМЕРА
            safe_url = html.escape(selected.source_url, quote=True)
            disclaimer = "\n\n<i>⚠️ Сообщение создано ИИ. Проверяйте информацию по ссылке ниже.</i>"
            source_link = f"\n\n<a href=\"{safe_url}\">🌐 Түпнұсқа / Источник</a>"
            
            # Собираем финальный текст
            final_text = f"{rewritten}{disclaimer}{source_link}"
            
            # Публикация
            post_id = await publisher.publish(final_text, selected.image_url)
            
            if post_id:
                selected.telegram_post_id = str(post_id)
                selected.status = NewsStatus.published.value
                selected.published_at = datetime.utcnow()
                selected.rewritten_text = rewritten
                db.commit()
                logger.info(f"Successfully published ID {selected.id}. Post ID: {post_id}")
            else:
                raise Exception("Publisher returned empty post_id")
            
        except Exception as e:
            logger.error(f"Error in publishing {selected.id}: {str(e)}")
            selected.status = NewsStatus.error.value
            db.commit()

    except Exception as e:
        logger.error(f"Error in process_news_task: {str(e)}")
    finally:
        db.close()

def is_post_integrity_ok(final_text: str, source_url: str) -> bool:
    """Проверяет финальный текст на критические ошибки перед публикацией."""
    
    # 1. Проверка на пустоту
    if not final_text or len(final_text) < 150:
        logger.error("integrity Check Failed: Текст слишком короткий или пустой.")
        return False
        
    # 2. Проверка ссылки
    if not source_url or "http" not in source_url:
        logger.error("Integrity Check Failed: Отсутствует корректная ссылка на источник.")
        return False
        
    # 3. Проверка структуры (должен быть заголовок и ссылка в тексте)
    if "<b>" not in final_text:
        logger.error("Integrity Check Failed: В тексте отсутствует заголовок (тег <b>).")
        return False
        
    if "Түпнұсқа" not in final_text and "Источник" not in final_text:
        logger.error("Integrity Check Failed: В финальном тексте не найдена ссылка на оригинал.")
        return False

    return True
    
def start_scheduler():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler()
    
    # Сбор новостей (интервал из конфига, например 20 мин)
    scheduler.add_job(scrape_news_task, 'interval', minutes=settings.SCRAPE_INTERVAL_MINUTES)
    
    # Публикация (интервал из конфига, например 5 или 15 мин)
    scheduler.add_job(process_news_task, 'interval', minutes=settings.PUBLISH_INTERVAL_MINUTES)
    
    # Пинг самого себя для предотвращения сна на Koyeb
    def ping_self():
        try:
            requests.get("http://127.0.0.1:8000/health", timeout=5)
            logger.info("Keepalive ping OK")
        except Exception as e:
            logger.warning(f"Keepalive ping failed: {e}")
            
    scheduler.add_job(ping_self, 'interval', minutes=4)
    
    scheduler.start()
    logger.info("APScheduler started successfully.")
    return scheduler
