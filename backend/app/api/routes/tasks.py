import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.task import TaskBatchSubmit, TaskCancelResponse, TaskRead
from app.services.task_service import (
    TaskNotFoundError,
    TaskValidationError,
    cancel_task,
    get_task,
    list_tasks,
    submit_batch,
)

router = APIRouter()


def _task_to_read(task) -> TaskRead:
    return TaskRead(
        **{
            k: getattr(task, k)
            for k in TaskRead.model_fields
            if k not in ("dependency_ids", "history")
        },
        dependency_ids=[d.depends_on_task_id for d in task.dependencies],
        history=task.history,
    )


@router.post("/tasks", response_model=list[TaskRead], status_code=201)
async def submit_tasks(payload: TaskBatchSubmit, db: AsyncSession = Depends(get_db)):
    try:
        tasks = await submit_batch(db, payload)
    except TaskValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return [_task_to_read(t) for t in tasks]


@router.get("/tasks", response_model=list[TaskRead])
async def list_all_tasks(db: AsyncSession = Depends(get_db)):
    tasks = await list_tasks(db)
    return [_task_to_read(t) for t in tasks]


@router.get("/tasks/{task_id}", response_model=TaskRead)
async def get_task_by_id(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    try:
        task = await get_task(db, task_id)
    except TaskNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_to_read(task)


@router.post("/tasks/{task_id}/cancel", response_model=TaskCancelResponse)
async def cancel_task_endpoint(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    try:
        task = await cancel_task(db, task_id)
    except TaskNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")
    except TaskValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return TaskCancelResponse(task_id=task.id, status=task.status)
