import asyncio
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from .database import SessionLocal, NewsArchive, NewsStatus
from .scraper import scraper
from .rewriter import rewriter
from .publisher import publisher
import requests

logger = logging.getLogger(__name__)

async def process_news_task():
    """
    Main background task to scrape, rewrite and publish news.
    """
    db = SessionLocal()
    try:
        logger.info("Starting news processing cycle...")
        
        # 1. Scrape new items
        new_items = scraper.scrape()
        if not new_items:
            logger.warning("No news found in any RSS sources.")
            return

        added_count = 0
        for item in new_items:
            # Check if already exists
            exists = db.query(NewsArchive).filter(NewsArchive.source_url == item["source_url"]).first()
            if not exists:
                news_entry = NewsArchive(
                    title=item["title"],
                    original_text=item["original_text"],
                    source_name=item["source_name"],
                    source_url=item["source_url"],
                    image_url=item["image_url"],
                    status=NewsStatus.draft.value
                )
                db.add(news_entry)
                added_count += 1
        
        db.commit()
        logger.info(f"Successfully added {added_count} new unique news items to database.")

        # 2. Process only one draft per cycle (ensures 1 news every interval)
        draft = (
            db.query(NewsArchive)
            .filter(NewsArchive.status == NewsStatus.draft.value)
            .order_by(NewsArchive.created_at.asc())
            .first()
        )
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
            post_id = await publisher.publish(draft.rewritten_text, draft.image_url)
            
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
    scheduler.add_job(process_news_task, 'interval', minutes=settings.SCRAPE_INTERVAL_MINUTES)
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
