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

# Фиксированный ID блокировки
SCHEDULER_LOCK_ID = 0x0A7C9F26

app = FastAPI(title="GovContext AI Editorial System")

def _try_acquire_scheduler_lock():
    """
    Пытается захватить advisory lock. 
    Если замок занят, мы пробуем его 'пробить', если это единственный воркер.
    """
    try:
        conn = engine.connect()
        # Проверяем, не занят ли замок
        result = conn.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": SCHEDULER_LOCK_ID})
        got_lock = result.scalar()
        
        if got_lock:
            return conn, True
        else:
            conn.close()
            return None, False
    except Exception as e:
        logger.warning("Ошибка PostgreSQL Advisory Lock: %s. Запускаем без блокировки.", e)
        return None, True 

@app.on_event("startup")
async def startup_event():
    logger.info("Initializing database...")
    init_db()
    logger.info("Cleaning up old news...")
    cleanup_old_tourism_news()

    # Попытка стать лидером
    lock_conn, is_leader = _try_acquire_scheduler_lock()
    
    if is_leader:
        if lock_conn:
            app.state.scheduler_lock_connection = lock_conn
        
        logger.info("✅ ЭТОТ ПРОЦЕСС — ЛИДЕР. Запуск планировщика...")
        start_scheduler()
        
        # Запускаем начальный сбор в фоне, чтобы не вешать старт сервера
        asyncio.create_task(scrape_news_task())
        logger.info("🚀 Начальный скрапинг запущен.")
    else:
        logger.warning("⚠️ ЗАМОК ЗАНЯТ. Планировщик в режиме ожидания.")
        # Сохраняем статус, чтобы понимать состояние через API
        app.state.is_scheduler_running = False

@app.on_event("shutdown")
def shutdown_event():
    if getattr(app.state, "scheduler_lock_connection", None) is not None:
        try:
            # Принудительно отпускаем замок при выключении
            app.state.scheduler_lock_connection.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": SCHEDULER_LOCK_ID})
            app.state.scheduler_lock_connection.close()
            logger.info("🔓 Замок освобожден.")
        except Exception as e:
            logger.error(f"Ошибка при освобождении замка: {e}")

@app.get("/")
async def root():
    lock_status = "Leader" if getattr(app.state, "scheduler_lock_connection", None) else "Follower/Idle"
    return {
        "status": "ok", 
        "mode": lock_status,
        "message": "GovContext System is active"
    }

@app.get("/trigger-scrape")
async def trigger_scrape(background_tasks: BackgroundTasks):
    """Принудительный запуск скрапера через API (игнорирует планировщик)"""
    logger.info("Manual scrape trigger received.")
    background_tasks.add_task(scrape_news_task)
    return {"message": "Scrape task triggered manually in background"}

@app.get("/force-start-scheduler")
async def force_start_scheduler():
    """Кнопка 'Последний шанс': запуск планировщика в обход всех блокировок"""
    start_scheduler()
    asyncio.create_task(scrape_news_task())
    return {"message": "Scheduler forced to start regardless of locks."}

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)
