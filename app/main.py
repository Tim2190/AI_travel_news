import logging
from fastapi import FastAPI, BackgroundTasks
from .database import init_db
from .scheduler import start_scheduler, process_news_task
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
    logger.info("Starting scheduler...")
    start_scheduler()

@app.get("/")
async def root():
    return {"status": "ok", "message": "AI Travel News System is running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/trigger-manual")
async def trigger_manual(background_tasks: BackgroundTasks):
    """
    Manually trigger the news processing task.
    """
    background_tasks.add_task(process_news_task)
    return {"message": "Processing task triggered in background"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
