import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import stats, tasks
from app.core.config import settings
from app.services.scheduler import run_scheduler, startup_recovery

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown lifecycle."""
    await startup_recovery()
    scheduler_task = asyncio.create_task(run_scheduler())
    logger.info("Application started")
    yield
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    logger.info("Application shutdown")


app = FastAPI(
    title="Task Runner Service",
    description="A document-processing task runner with dependency management.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)
app.include_router(stats.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
