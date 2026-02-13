import asyncio
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from .database import SessionLocal, NewsArchive, NewsStatus
from .scraper import scraper
from .rewriter import rewriter
from .publisher import publisher

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
        db.commit()

        # 2. Process drafts (Rewrite)
        drafts = db.query(NewsArchive).filter(NewsArchive.status == NewsStatus.draft.value).all()
        for draft in drafts:
            try:
                logger.info(f"Rewriting news: {draft.title}")
                rewritten = await rewriter.rewrite(draft.original_text)
                draft.rewritten_text = rewritten
                db.commit()
                
                # 3. Publish
                logger.info(f"Publishing news: {draft.title}")
                post_id = await publisher.publish(draft.rewritten_text, draft.image_url)
                
                draft.telegram_post_id = str(post_id)
                draft.status = NewsStatus.published.value
                draft.published_at = datetime.utcnow()
                db.commit()
                
            except Exception as e:
                logger.error(f"Error processing news {draft.id}: {str(e)}")
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
    scheduler.start()
    return scheduler
