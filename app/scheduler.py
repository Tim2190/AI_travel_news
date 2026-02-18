import asyncio
import html
import logging
import re
from datetime import datetime, time, timedelta
from difflib import SequenceMatcher
from sqlalchemy.orm import Session
from sqlalchemy import func
import requests
import pytz # Для работы с часовым поясом Астаны

from .database import SessionLocal, NewsArchive, NewsStatus
from .scraper import scraper
from .rewriter import rewriter
from .publisher import publisher
from .config import settings

logger = logging.getLogger(__name__)

# --- НАСТРОЙКИ ---
TIMEZONE = pytz.timezone('Asia/Almaty')
WORK_START = time(7, 0)  # 07:00 утра
WORK_END = time(21, 0)   # 21:00 вечера

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
    # 1. Проверка на пустоту и длину
    if not final_text or len(final_text) < 100:
        logger.error("❌ Integrity Check: Текст слишком короткий.")
        return False
        
    # 2. Проверка наличия ссылки на источник в тексте
    if "Түпнұсқа" not in final_text and "Источник" not in final_text:
        logger.error("❌ Integrity Check: Ссылка на источник не найдена в тексте.")
        return False
        
    # 3. Проверка структуры (заголовок)
    if "<b>" not in final_text:
        logger.error("❌ Integrity Check: Нет заголовка (тег <b>).")
        return False

    # 4. Проверка самого URL
    if not source_url or "http" not in source_url:
        logger.error("❌ Integrity Check: Битый URL источника.")
        return False

    return True

# --- ЗАДАЧИ ---

async def scrape_news_task():
    """Сбор новостей с жесткой фильтрацией дат."""
    db = SessionLocal()
    try:
        logger.info("Starting scraping cycle...")
        new_items = scraper.scrape()
        if not new_items:
            logger.warning("No news found from direct sources.")
            return

        # 1. Фильтр по ключевым словам
        topic_keywords = [k.strip().lower() for k in settings.TOPIC_KEYWORDS.split(",") if k.strip()]
        def matches_topic(item):
            if not topic_keywords: return True
            text_blob = (f"{item.get('title', '')} {item.get('original_text', '')}").lower()
            return any(kw in text_blob for kw in topic_keywords)
        
        new_items = [i for i in new_items if matches_topic(i)]

        # 2. ЖЕСТКИЙ ФИЛЬТР ПО ДАТЕ (Только за последние сутки)
        cutoff = datetime.utcnow() - timedelta(days=settings.NEWS_MAX_AGE_DAYS)
        def is_recent(item):
            pub = item.get("published_at")
            if not pub: # Если даты нет — в мусорку
                return False
            if getattr(pub, "tzinfo", None):
                pub = pub.replace(tzinfo=None)
            return pub >= cutoff
        
        new_items = [i for i in new_items if is_recent(i)]
        
        if not new_items:
            logger.info("No recent news found after filtering.")
            return

        # 3. Скоринг и отбор
        new_items.sort(key=lambda x: len(x.get('original_text', '')), reverse=True)
        top_items = new_items[:10]

        # 4. Сохранение (с проверкой дублей)
        check_date = datetime.utcnow() - timedelta(days=3)
        recent_titles = [r[0] for r in db.query(NewsArchive.title).filter(NewsArchive.created_at >= check_date).all()]
        
        added = 0
        for item in top_items:
            if added >= 5: break
            
            title = item["title"]
            if db.query(NewsArchive).filter(NewsArchive.source_url == item["source_url"]).first():
                continue
            if is_fuzzy_duplicate(title, recent_titles):
                continue

            db.add(NewsArchive(
                title=title,
                original_text=item["original_text"],
                source_name=item["source_name"],
                source_url=item["source_url"],
                source_published_at=item.get("published_at"),
                image_url=item["image_url"],
                status=NewsStatus.draft.value
            ))
            added += 1
            recent_titles.append(title)
        
        db.commit()
        logger.info(f"Added {added} new drafts.")
        
    except Exception as e:
        logger.error(f"Scrape Error: {e}")
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
        # Берем последние 3 опубликованные новости
        last_posts = db.query(NewsArchive).filter(
            NewsArchive.status == NewsStatus.published.value
        ).order_by(NewsArchive.published_at.desc()).limit(3).all()

        target_lang = "RU" # По умолчанию
        
        if last_posts:
            # Логика чередования:
            # Если последняя была KZ -> Сейчас RU
            # Если последняя была RU, и предпоследняя RU -> Сейчас KZ
            p1 = last_posts[0] # Самая свежая
            
            p1_is_kz = is_text_kazakh(p1.rewritten_text or p1.title)
            
            if p1_is_kz:
                target_lang = "RU"
                logger.info("Rotation: Last was KZ -> Next RU")
            else:
                # Последняя была RU. Смотрим предпоследнюю.
                if len(last_posts) >= 2:
                    p2 = last_posts[1]
                    p2_is_kz = is_text_kazakh(p2.rewritten_text or p2.title)
                    if not p2_is_kz: # И предпоследняя тоже не KZ (значит было 2 RU подряд)
                        target_lang = "KZ"
                        logger.info("Rotation: Last 2 were RU -> Next KZ")
                    else:
                        target_lang = "RU" # Было RU, KZ -> Значит еще одно RU
                else:
                    target_lang = "RU" # Мало данных, пока гоним RU

        # 3. Поиск подходящего черновика
        drafts = db.query(NewsArchive).filter(NewsArchive.status == NewsStatus.draft.value).all()
        if not drafts:
            logger.info("No drafts.")
            return

        selected = None
        # Ищем строгое совпадение языка
        for d in drafts:
            draft_is_kz = is_text_kazakh(d.original_text)
            if target_lang == "KZ" and draft_is_kz:
                selected = d
                break
            if target_lang == "RU" and not draft_is_kz:
                selected = d
                break
        
        # Fallback: Если нужного языка нет, берем что есть (чтобы не стоять)
        if not selected:
            selected = drafts[0]
            logger.info(f"Fallback: No {target_lang} drafts. Taking available.")

        # 4. Обработка
        try:
            selected = db.merge(selected)
            logger.info(f"Processing: {selected.title}...")

            # Рерайт через Gemini Ensemble
            rewritten = await rewriter.rewrite(selected.original_text)
            
            if not rewritten:
                selected.status = NewsStatus.error.value
                db.commit()
                return

            # Сборка
            safe_url = html.escape(selected.source_url, quote=True)
            disclaimer = "\n\n<i>⚠️ Сообщение создано ИИ. Проверяйте информацию по ссылке ниже.</i>"
            source_link = f"\n<a href=\"{safe_url}\">🌐 Түпнұсқа / Источник</a>"
            final_text = f"{rewritten}{disclaimer}{source_link}"

            # Контроль целостности
            if not is_post_integrity_ok(final_text, selected.source_url):
                logger.warning(f"⚠️ Rejected by Integrity Check: {selected.id}")
                selected.status = NewsStatus.error.value
                db.commit()
                return

            # Публикация
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
