import asyncio
import html
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from .database import SessionLocal, NewsArchive, NewsStatus
from .scraper import scraper
from .rewriter import rewriter
from .publisher import publisher
from .config import settings
import requests

logger = logging.getLogger(__name__)

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

        # Только актуальные: отбрасываем материалы старше NEWS_MAX_AGE_DAYS
        cutoff = datetime.utcnow() - timedelta(days=settings.NEWS_MAX_AGE_DAYS)
        def is_recent(item):
            pub = item.get("published_at")
            if pub is None:
                return True  # дату не нашли — не отбрасываем
            if getattr(pub, "tzinfo", None):
                pub = pub.replace(tzinfo=None)  # к наивному для сравнения
            return pub >= cutoff
        new_items = [i for i in new_items if is_recent(i)]
        if not new_items:
            logger.warning("No recent news (all older than %s days).", settings.NEWS_MAX_AGE_DAYS)
            return

        # ограничим максимум 30 новостями
        new_items = new_items[:30]

        # простое скорингование: по длине текста и наличию ключевых слов
        def score(item):
            text = (item.get("original_text") or "").lower()
            title = (item.get("title") or "").lower()
            base = min(len(text) / 500, 3)  # до 3 баллов за объем
            keywords = ["экономика", "финансы", "банк", "инфляция", "рынок", "валюта", "инвестиции"]
            kw_score = sum(1 for k in keywords if k in text or k in title)
            region_keywords = ["казахстан", "россия", "узбекистан", "снг", "алматы", "астана", "москва", "ташкент"]
            region_score = sum(1 for k in region_keywords if k in text or k in title)
            return base + kw_score + region_score

        scored = sorted(new_items, key=score, reverse=True)
        top_items = scored[:5]

        added_count = 0
        for item in top_items:
            # Дубликаты: проверка по URL (один материал — один пост)
            exists = db.query(NewsArchive).filter(NewsArchive.source_url == item["source_url"]).first()
            if exists:
                continue
            news_entry = NewsArchive(
                title=item["title"],
                original_text=item["original_text"],
                source_name=item["source_name"],
                source_url=item["source_url"],
                source_published_at=item.get("published_at"),
                image_url=item["image_url"],
                status=NewsStatus.draft.value
            )
            db.add(news_entry)
            added_count += 1

        db.commit()
        logger.info(f"Successfully added {added_count} prioritized news items to database.")
    except Exception as e:
        logger.error(f"Error in scrape_news_task: {str(e)}")
    finally:
        db.close()
        logger.info("Scraping cycle finished.")


async def process_news_task():
    """
    Process one draft: rewrite and publish.
    Runs every PUBLISH_INTERVAL_MINUTES.
    """
    db = SessionLocal()
    try:
        logger.info("Starting news processing cycle...")

        # 1. Process only one draft per cycle (ensures 1 news every interval)
        draft_query = (
            db.query(NewsArchive)
            .filter(NewsArchive.status == NewsStatus.draft.value, NewsArchive.telegram_post_id == None)
            .order_by(NewsArchive.created_at.asc())
        )
        try:
            draft = draft_query.with_for_update(skip_locked=True).first()
        except Exception:
            draft = draft_query.first()
        if not draft:
            logger.info("No drafts to process at this time.")
            return
        try:
            # Refresh session object
            db.expire_all()
            draft = db.merge(draft)
            logger.info(f"--- Processing single news: {draft.title} ---")
            
            # REWRITE STAGE
            rewritten = await rewriter.rewrite(draft.original_text)
            if not rewritten:
                logger.info(f"News ID {draft.id} rejected by editors.")
                draft.status = NewsStatus.error.value
                draft.error_log = "Rejected by editors (significance or legal check)"
                db.commit()
                return
            draft.rewritten_text = rewritten
            db.commit()
            
            # PUBLISH STAGE
            logger.info(f"Publishing to Telegram: {draft.title}")
            # Ссылка на конкретный материал (оригинал статьи)
            safe_url = html.escape(draft.source_url, quote=True)
            final_text = f"{draft.rewritten_text}\n\n<a href=\"{safe_url}\">Түпнұсқа</a>"
            post_id = await publisher.publish(final_text, draft.image_url)
            
            draft.telegram_post_id = str(post_id)
            draft.status = NewsStatus.published.value
            draft.published_at = datetime.utcnow()
            db.commit()
            logger.info(f"Successfully published news ID {draft.id}. Post ID: {post_id}")
        except Exception as e:
            logger.error(f"Error processing news {draft.id} ('{draft.title}'): {str(e)}")
            draft.status = NewsStatus.error.value
            draft.error_log = str(e)
            db.commit()

    except Exception as e:
        logger.error(f"Error in process_news_task: {str(e)}")
    finally:
        db.close()
        logger.info("News processing cycle finished.")

def start_scheduler():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from .config import settings

    scheduler = AsyncIOScheduler()
    scheduler.add_job(scrape_news_task, 'interval', minutes=settings.SCRAPE_INTERVAL_MINUTES)
    scheduler.add_job(process_news_task, 'interval', minutes=settings.PUBLISH_INTERVAL_MINUTES)
    # Keepalive ping to prevent sleep
    def ping_self():
        try:
            requests.get("http://127.0.0.1:8000/health", timeout=5)
            logger.info("Keepalive ping OK")
        except Exception as e:
            logger.warning(f"Keepalive ping failed: {e}")
    scheduler.add_job(ping_self, 'interval', minutes=4)
    scheduler.start()
    return scheduler
