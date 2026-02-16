import asyncio
import html
import logging
import re
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from difflib import SequenceMatcher  # <--- СОХРАНЕНО
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
    kz_chars = r'[әіңғүұқөһӘІҢҒҮҰҚӨҺ]'
    return bool(re.search(kz_chars, text))

# --- ОСНОВНЫЕ ЗАДАЧИ ---

async def scrape_news_task():
    """
    Scrape news, select up to 5 best items and store as drafts.
    Runs every SCRAPE_INTERVAL_MINUTES.
    """
    db = SessionLocal()
    try:
        logger.info("Starting scraping cycle...")
        new_items = scraper.scrape()
        if not new_items:
            logger.warning("No news found from any direct sources.")
            return

        # Только по заданной тематике
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

        # Только актуальные
        cutoff = datetime.utcnow() - timedelta(days=settings.NEWS_MAX_AGE_DAYS)
        def is_recent(item):
            pub = item.get("published_at")
            if pub is None:
                return True 
            if getattr(pub, "tzinfo", None):
                pub = pub.replace(tzinfo=None)
            return pub >= cutoff
        
        new_items = [i for i in new_items if is_recent(i)]
        if not new_items:
            logger.warning("No recent news (all older than %s days).", settings.NEWS_MAX_AGE_DAYS)
            return

        new_items = new_items[:30]

        def normalize_title(title):
            if not title:
                return ""
            return re.sub(r"\s+", " ", title.strip().lower())[:500]

        def score(item):
            text = (item.get("original_text") or "").lower()
            title = (item.get("title") or "").lower()
            base = min(len(text) / 500, 3) 
            keywords = ["экономика", "финансы", "банк", "инфляция", "рынок", "валюта", "инвестиции"]
            kw_score = sum(1 for k in keywords if k in text or k in title)
            region_keywords = ["казахстан", "россия", "узбекистан", "снг", "алматы", "астана", "москва", "ташкент"]
            region_score = sum(1 for k in region_keywords if k in text or k in title)
            return base + kw_score + region_score

        scored = sorted(new_items, key=score, reverse=True)
        top_items = scored[:5]

        # === ЗАГРУЗКА ИСТОРИИ ДЛЯ FUZZY MATCHING ===
        check_date = datetime.utcnow() - timedelta(days=3)
        recent_records = db.query(NewsArchive.title).filter(NewsArchive.created_at >= check_date).all()
        existing_titles_cache = [row[0] for row in recent_records if row[0]]

        added_count = 0
        for item in top_items:
            current_title = item["title"]

            url_exists = db.query(NewsArchive).filter(NewsArchive.source_url == item["source_url"]).first()
            if url_exists:
                continue

            norm = normalize_title(current_title)
            if norm and db.query(NewsArchive).filter(NewsArchive.normalized_title == norm).first():
                continue

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
        logger.info(f"Successfully added {added_count} prioritized news items.")
    except Exception as e:
        logger.error(f"Error in scrape_news_task: {str(e)}")
    finally:
        db.close()

async def process_news_task():
    """
    Умная обработка очереди:
    - KZ: 1 раз в час (макс 20/день)
    - RU: каждые 15 мин (макс 40/день)
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

        kz_count = 0
        ru_count = 0
        last_kz_pub_time = datetime.min

        for p in published_today:
            if is_text_kazakh(p.rewritten_text or p.title):
                kz_count += 1
                if p.published_at > last_kz_pub_time:
                    last_kz_pub_time = p.published_at
            else:
                ru_count += 1

        logger.info(f"Today's stats: KZ {kz_count}/20, RU {ru_count}/40")

        # 2. ВЫБОР ЦЕЛЕВОГО ЯЗЫКА
        target_lang = None
        time_since_kz = datetime.utcnow() - last_kz_pub_time
        
        # Если прошел час и лимит KZ не исчерпан
        if kz_count < 20 and time_since_kz >= timedelta(hours=1):
            target_lang = "KZ"
            logger.info("Target: Kazakh (Hour interval reached)")
        elif ru_count < 40:
            target_lang = "RU"
            logger.info("Target: Russian (Standard interval)")
        else:
            logger.info("All daily limits reached. Sleeping.")
            return

        # 3. ПОИСК ПОДХОДЯЩЕГО ЧЕРНОВИКА
        drafts = db.query(NewsArchive).filter(
            NewsArchive.status == NewsStatus.draft.value,
            NewsArchive.telegram_post_id == None
        ).order_by(NewsArchive.created_at.asc()).all()

        selected = None
        for d in drafts:
            is_kz = is_text_kazakh(d.original_text)
            if target_lang == "KZ" and is_kz:
                selected = d
                break
            if target_lang == "RU" and not is_kz:
                selected = d
                break
        
        # Если для KZ черновика нет, а время пришло — пробуем взять RU, чтобы не простаивать
        if not selected and target_lang == "KZ" and ru_count < 40:
            selected = next((d for d in drafts if not is_text_kazakh(d.original_text)), None)

        if not selected:
            logger.info(f"No drafts found for {target_lang} language.")
            return

        # 4. ПРОЦЕССИНГ
        try:
            db.expire_all()
            selected = db.merge(selected)
            logger.info(f"--- Processing: {selected.title} ---")
            
            rewritten = await rewriter.rewrite(selected.original_text)
            if not rewritten:
                selected.status = NewsStatus.error.value
                db.commit()
                return
            
            selected.rewritten_text = rewritten
            db.commit()

            safe_url = html.escape(selected.source_url, quote=True)
            final_text = f"{selected.rewritten_text}\n\n<a href=\"{safe_url}\">Түпнұсқа</a>"
            
            post_id = await publisher.publish(final_text, selected.image_url)
            
            selected.telegram_post_id = str(post_id)
            selected.status = NewsStatus.published.value
            selected.published_at = datetime.utcnow()
            db.commit()
            logger.info(f"Successfully published ID {selected.id}. Post ID: {post_id}")
            
        except Exception as e:
            logger.error(f"Error in publishing {selected.id}: {str(e)}")
            selected.status = NewsStatus.error.value
            db.commit()

    except Exception as e:
        logger.error(f"Error in process_news_task: {str(e)}")
    finally:
        db.close()

def start_scheduler():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from .config import settings

    scheduler = AsyncIOScheduler()
    scheduler.add_job(scrape_news_task, 'interval', minutes=settings.SCRAPE_INTERVAL_MINUTES)
    scheduler.add_job(process_news_task, 'interval', minutes=settings.PUBLISH_INTERVAL_MINUTES)
    
    def ping_self():
        try:
            requests.get("http://127.0.0.1:8000/health", timeout=5)
            logger.info("Keepalive ping OK")
        except Exception as e:
            logger.warning(f"Keepalive ping failed: {e}")
            
    scheduler.add_job(ping_self, 'interval', minutes=4)
    scheduler.start()
    return scheduler
