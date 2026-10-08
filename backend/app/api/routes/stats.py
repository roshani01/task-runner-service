from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.task import StatsRead
from app.services.task_service import get_stats

router = APIRouter()


@router.get("/stats", response_model=StatsRead)
async def stats(db: AsyncSession = Depends(get_db)):
    return await get_stats(db)
