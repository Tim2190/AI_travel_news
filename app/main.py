import asyncio
import logging
import os
from fastapi import FastAPI, BackgroundTasks
from sqlalchemy import text
from .database import init_db, cleanup_old_tourism_news, engine
from .scheduler import start_scheduler, process_news_task, scrape_news_task

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Один фиксированный ID блокировки: только один процесс в кластере запускает планировщик
SCHEDULER_LOCK_ID = 0x0A7C9F26

app = FastAPI(title="AI Travel News Editorial System")

def _try_acquire_scheduler_lock():
    """Пытается захватить advisory lock в PostgreSQL. Возвращает (connection или None, получили_ли_лок)."""
    try:
        conn = engine.connect()
        row = conn.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": SCHEDULER_LOCK_ID})
        got = row.scalar()
        if got:
            return conn, True
        conn.close()
        return None, False
    except Exception as e:
        logger.warning("Advisory lock not available (e.g. not PostgreSQL): %s. Scheduler will run in this process.", e)
        return None, True  # не PostgreSQL — запускаем планировщик как раньше

@app.on_event("startup")
async def startup_event():
    logger.info("Initializing database...")
    init_db()
    logger.info("Cleaning up old tourism news...")
    cleanup_old_tourism_news()

    # Запускаем планировщик и начальный скрап только в одном процессе (избегаем race condition при 2+ воркерах)
    lock_conn, is_leader = _try_acquire_scheduler_lock()
    if lock_conn is not None:
        app.state.scheduler_lock_connection = lock_conn  # держим соединение, чтобы не отпустить lock
    if is_leader:
        logger.info("This process is scheduler leader. Starting scheduler...")
        start_scheduler()
        asyncio.create_task(scrape_news_task())
        logger.info("Initial scrape task scheduled (run once at startup).")
    else:
        logger.info("Scheduler skipped: another process holds the lock (single scheduler in cluster).")

@app.on_event("shutdown")
def shutdown_event():
    if getattr(app.state, "scheduler_lock_connection", None) is not None:
        try:
            app.state.scheduler_lock_connection.close()
        except Exception:
            pass
        app.state.scheduler_lock_connection = None

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
