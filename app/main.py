import asyncio
import logging
import os
from fastapi import FastAPI, BackgroundTasks
from .database import init_db, cleanup_old_tourism_news
from .scheduler import start_scheduler, process_news_task, scrape_news_task
from .config import settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Travel News Editorial System")

@app.on_event("startup")
async def startup_event():
    logger.info("Initializing database...")
    init_db()
    logger.info("Cleaning up old tourism news...")
    cleanup_old_tourism_news()
    logger.info("Starting scheduler...")
    start_scheduler()
    # Запуск скрапера сразу при старте (иначе первый раз только через SCRAPE_INTERVAL_MINUTES)
    asyncio.create_task(scrape_news_task())
    logger.info("Initial scrape task scheduled (run once at startup).")

@app.get("/")
async def root():
    return {"status": "ok", "message": "AI Travel News System is running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/trigger-scrape")
async def trigger_scrape(background_tasks: BackgroundTasks):
    """
    Вручную запустить скрапер (сбор новостей в черновики).
    """
    background_tasks.add_task(scrape_news_task)
    return {"message": "Scrape task triggered in background"}

@app.get("/trigger-manual")
async def trigger_manual(background_tasks: BackgroundTasks):
    """
    Вручную запустить обработку одного черновика (рерайт + публикация в Telegram).
    """
    background_tasks.add_task(process_news_task)
    return {"message": "Processing task triggered in background"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
