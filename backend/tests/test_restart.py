"""
Restart/recovery tests.

These tests verify that RUNNING tasks at shutdown are reset to WAITING
and can be re-executed after startup_recovery() is called.
"""
import asyncio
from unittest.mock import patch

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.task import Task, TaskStatus
from app.schemas.task import TaskBatchSubmit
from app.services import scheduler as sched_module
from app.services.scheduler import startup_recovery
from app.services.task_service import submit_batch


@pytest.mark.asyncio
async def test_running_tasks_reset_on_startup(test_engine, monkeypatch):
    """
    Simulate interrupted RUNNING tasks by directly setting status=RUNNING in the DB.
    After startup_recovery(), they should all be WAITING again.
    """
    from app.core import database as db_module
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", factory)

    # Create tasks and manually force them into RUNNING state
    payload = TaskBatchSubmit(tasks=[
        {"id": "t1", "name": "Interrupted Task 1", "duration": 0.05},
        {"id": "t2", "name": "Interrupted Task 2", "duration": 0.05},
        {"id": "t3", "name": "Normal Waiting Task", "duration": 0.05},
    ])
    async with factory() as db:
        tasks = await submit_batch(db, payload)

    interrupted_ids = [tasks[0].id, tasks[1].id]
    async with factory() as db:
        await db.execute(
            update(Task)
            .where(Task.id.in_(interrupted_ids))
            .values(status=TaskStatus.RUNNING)
        )
        await db.commit()

    # Verify they're RUNNING before recovery
    async with factory() as db:
        result = await db.execute(select(Task).where(Task.id.in_(interrupted_ids)))
        before = result.scalars().all()
        assert all(t.status == TaskStatus.RUNNING for t in before)

    # Run recovery
    await startup_recovery()

    # All should be back to WAITING
    async with factory() as db:
        result = await db.execute(select(Task))
        all_tasks = result.scalars().all()
        status_map = {t.id: t.status for t in all_tasks}

    for tid in interrupted_ids:
        assert status_map[tid] == TaskStatus.WAITING, f"Task {tid} should be WAITING after recovery"

    # The task that was already WAITING should remain WAITING
    waiting_id = tasks[2].id
    assert status_map[waiting_id] == TaskStatus.WAITING


@pytest.mark.asyncio
async def test_succeeded_tasks_untouched_by_recovery(test_engine, monkeypatch):
    """Recovery must not reset SUCCEEDED or FAILED tasks."""
    from app.core import database as db_module
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", factory)

    payload = TaskBatchSubmit(tasks=[
        {"id": "done", "name": "Done Task"},
        {"id": "failed", "name": "Failed Task"},
        {"id": "running", "name": "Running Task"},
    ])
    async with factory() as db:
        tasks = await submit_batch(db, payload)
    id_map = {t.name: t.id for t in tasks}

    async with factory() as db:
        await db.execute(update(Task).where(Task.id == id_map["Done Task"]).values(status=TaskStatus.SUCCEEDED))
        await db.execute(update(Task).where(Task.id == id_map["Failed Task"]).values(status=TaskStatus.FAILED))
        await db.execute(update(Task).where(Task.id == id_map["Running Task"]).values(status=TaskStatus.RUNNING))
        await db.commit()

    await startup_recovery()

    async with factory() as db:
        result = await db.execute(select(Task))
        status_map = {t.name: t.status for t in result.scalars().all()}

    assert status_map["Done Task"] == TaskStatus.SUCCEEDED
    assert status_map["Failed Task"] == TaskStatus.FAILED
    assert status_map["Running Task"] == TaskStatus.WAITING  # reset
