import asyncio
import html
import logging
import re
from datetime import datetime, time, timedelta
from difflib import SequenceMatcher
from sqlalchemy.orm import Session
from sqlalchemy import func
import requests
import pytz 

from .database import SessionLocal, NewsArchive, NewsStatus
from .scraper import scraper
from .rewriter import rewriter
from .publisher import publisher
from .config import settings

logger = logging.getLogger(__name__)

# --- НАСТРОЙКИ ---
TIMEZONE = pytz.timezone('Asia/Almaty')
WORK_START = time(7, 0)  
WORK_END = time(21, 0)   

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def is_fuzzy_duplicate(new_title: str, existing_titles: list, threshold=0.65) -> bool:
    """Проверяет, похож ли заголовок на один из существующих."""
    if not new_title: return False
    new_lower = new_title.lower()
    for old_title in existing_titles:
        if not old_title: continue
        similarity = SequenceMatcher(None, new_lower, old_title.lower()).ratio()
        if similarity > threshold:
            return True
    return False

def is_text_kazakh(text: str) -> bool:
    """Определяет язык текста."""
    if not text: return False
    kz_chars = r'[әіңғүұқөһӘІҢҒҮҰҚӨҺ]'
    return bool(re.search(kz_chars, text, re.IGNORECASE))

def is_post_integrity_ok(final_text: str, source_url: str) -> bool:
    """КОНТРОЛЕР: Проверка поста перед публикацией."""
    if not final_text or len(final_text) < 100:
        logger.error("❌ Integrity Check: Текст слишком короткий.")
        return False
        
    if "Түпнұсқа" not in final_text and "Источник" not in final_text:
        logger.error("❌ Integrity Check: Ссылка на источник не найдена в тексте.")
        return False
        
    if "<b>" not in final_text:
        logger.error("❌ Integrity Check: Нет заголовка (тег <b>).")
        return False

    if not source_url or "http" not in source_url:
        logger.error("❌ Integrity Check: Битый URL источника.")
        return False

    return True

# --- ЗАДАЧИ ---

async def scrape_news_task():
    """Сбор новостей: сначала заголовки, потом проверка БД, потом мясо (enrich)."""
    db = SessionLocal()
    try:
        logger.info("🚀 Starting scraping cycle (Async Mode)...")
        # 1. Получаем «легкий» список
        raw_items = await scraper.scrape_async() 
        if not raw_items:
            logger.warning("No news found from direct sources.")
            return

        # 2. Подготовка к проверке дублей
        check_date = datetime.utcnow() - timedelta(days=3)
        recent_titles = [r[0] for r in db.query(NewsArchive.title).filter(NewsArchive.created_at >= check_date).all()]
        
        added = 0
        cutoff = datetime.utcnow() - timedelta(days=settings.NEWS_MAX_AGE_DAYS)
        
        # --- ФИЛЬТР КЛЮЧЕВЫХ СЛОВ УБРАН ---

        for item in raw_items:
            if added >= 10: break 

            title = item["title"]
            url = item["source_url"]

            # 3. БЫСТРЫЙ ФИЛЬТР: Проверка в БД по URL и заголовку
            if db.query(NewsArchive).filter(NewsArchive.source_url == url).first():
                continue
            if is_fuzzy_duplicate(title, recent_titles):
                continue

            # 4. ОБОГАЩЕНИЕ: Идем на страницу за текстом и датой
            logger.info(f"🔎 Enriching: {title[:50]}...")
            enriched_item = await asyncio.to_thread(scraper.enrich_news_with_content, item)

            # 5. ФИЛЬТР ПО ТЕМЕ - ОТКЛЮЧЕН (ВСЕ НОВОСТИ ПРОХОДЯТ)
            # Раньше здесь был блок if topic_keywords... теперь его нет.

            # 6. ФИЛЬТР ПО ДАТЕ
            pub = enriched_item.get("published_at")
            if not pub: 
                pub = datetime.utcnow() 
            
            if getattr(pub, "tzinfo", None):
                pub = pub.replace(tzinfo=None)
            
            if pub < cutoff:
                logger.info(f"⏭ Skip: Too old ({pub.strftime('%Y-%m-%d')})")
                continue

            # 7. СОХРАНЕНИЕ В БД
            db.add(NewsArchive(
                title=enriched_item["title"],
                original_text=enriched_item.get("original_text") or enriched_item["title"],
                source_name=enriched_item["source_name"],
                source_url=enriched_item["source_url"],
                source_published_at=pub,
                image_url=enriched_item.get("image_url"),
                status=NewsStatus.draft.value
            ))
            added += 1
            recent_titles.append(title)
            db.commit()

        logger.info(f"✅ Cycle finished. Added {added} new drafts.")
        
    except Exception as e:
        logger.error(f"Scrape Error: {e}", exc_info=True)
    finally:
        db.close()

async def process_news_task():
    """Публикация: Режим работы 07-21, Чередование 2 RU / 1 KZ."""
    
    # 1. Проверка рабочего времени (Астана)
    now_kz = datetime.now(TIMEZONE).time()
    if not (WORK_START <= now_kz <= WORK_END):
        logger.info(f"😴 Zzz... Time is {now_kz.strftime('%H:%M')}. Working hours: 07:00-21:00.")
        return

    db = SessionLocal()
    try:
        logger.info("Starting processing cycle...")

        # 2. Определение очереди (2 RU -> 1 KZ)
        last_posts = db.query(NewsArchive).filter(
            NewsArchive.status == NewsStatus.published.value
        ).order_by(NewsArchive.published_at.desc()).limit(3).all()

        target_lang = "RU" 
        
        if last_posts:
            p1 = last_posts[0] 
            p1_is_kz = is_text_kazakh(p1.rewritten_text or p1.title)
            
            if p1_is_kz:
                target_lang = "RU"
                logger.info("Rotation: Last was KZ -> Next RU")
            else:
                if len(last_posts) >= 2:
                    p2 = last_posts[1]
                    p2_is_kz = is_text_kazakh(p2.rewritten_text or p2.title)
                    if not p2_is_kz: 
                        target_lang = "KZ"
                        logger.info("Rotation: Last 2 were RU -> Next KZ")
                    else:
                        target_lang = "RU" 
                else:
                    target_lang = "RU"

        # 3. Поиск подходящего черновика
        drafts = db.query(NewsArchive).filter(NewsArchive.status == NewsStatus.draft.value).all()
        if not drafts:
            logger.info("No drafts.")
            return

        selected = None
        for d in drafts:
            draft_is_kz = is_text_kazakh(d.original_text)
            if target_lang == "KZ" and draft_is_kz:
                selected = d
                break
            if target_lang == "RU" and not draft_is_kz:
                selected = d
                break
        
        if not selected:
            selected = drafts[0]
            logger.info(f"Fallback: No {target_lang} drafts. Taking available.")

        # 4. Обработка
        try:
            selected = db.merge(selected)
            logger.info(f"Processing: {selected.title}...")

            rewritten = await rewriter.rewrite(selected.original_text)
            
            if not rewritten:
                selected.status = NewsStatus.error.value
                db.commit()
                return

            safe_url = html.escape(selected.source_url, quote=True)
            disclaimer = "\n\n<i>⚠️ Сообщение создано ИИ. Проверяйте информацию по ссылке ниже.</i>"
            source_link = f"\n<a href=\"{safe_url}\">🌐 Түпнұсқа / Источник</a>"
            final_text = f"{rewritten}{disclaimer}{source_link}"

            if not is_post_integrity_ok(final_text, selected.source_url):
                logger.warning(f"⚠️ Rejected by Integrity Check: {selected.id}")
                selected.status = NewsStatus.error.value
                db.commit()
                return

            post_id = await publisher.publish(final_text, selected.image_url)
            
            if post_id:
                selected.telegram_post_id = str(post_id)
                selected.status = NewsStatus.published.value
                selected.published_at = datetime.utcnow()
                selected.rewritten_text = rewritten
                db.commit()
                logger.info(f"✅ Published: {post_id}")
            
        except Exception as e:
            logger.error(f"Processing Error: {e}")
            selected.status = NewsStatus.error.value
            db.commit()

    except Exception as e:
        logger.error(f"Task Error: {e}")
    finally:
        db.close()

def start_scheduler():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(scrape_news_task, 'interval', minutes=settings.SCRAPE_INTERVAL_MINUTES)
    scheduler.add_job(process_news_task, 'interval', minutes=settings.PUBLISH_INTERVAL_MINUTES)
    
    def ping():
        try: requests.get("http://127.0.0.1:8000/health", timeout=5)
        except: pass
    scheduler.add_job(ping, 'interval', minutes=4)
    
    scheduler.start()
    return scheduler
