"""
Retry and backoff tests.

We control randomness via monkeypatching random.random so tests are deterministic.
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.task import Task, TaskStatus
from app.schemas.task import TaskBatchSubmit
from app.services import scheduler as sched_module
from app.services.task_service import submit_batch


async def _run_until_done(factory, task_id, max_seconds=15):
    """Poll DB until task reaches a terminal state."""
    for _ in range(max_seconds * 10):
        await asyncio.sleep(0.1)
        async with factory() as db:
            result = await db.execute(select(Task).where(Task.id == task_id))
            task = result.scalar_one_or_none()
            if task and task.status in (
                TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.CANCELLED
            ):
                return task
    return task


@pytest.mark.asyncio
async def test_task_succeeds_on_first_attempt(test_engine, monkeypatch):
    from app.core import database as db_module
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", factory)
    monkeypatch.setattr(sched_module, "_semaphore", asyncio.Semaphore(3))

    payload = TaskBatchSubmit(tasks=[
        {"id": "t1", "name": "Sure Task", "duration": 0.05, "failure_rate": 0.0, "max_retries": 0}
    ])
    async with factory() as db:
        tasks = await submit_batch(db, payload)
    task_id = tasks[0].id

    with patch("app.services.scheduler.random.random", return_value=0.5):  # 0.5 > 0.0 = no fail
        await sched_module._dispatch_ready_tasks()
        task = await _run_until_done(factory, task_id, max_seconds=5)

    assert task.status == TaskStatus.SUCCEEDED
    assert task.attempts == 1


@pytest.mark.asyncio
async def test_retry_on_failure_then_success(test_engine, monkeypatch):
    """Task fails once, then succeeds on retry."""
    from app.core import database as db_module
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", factory)
    monkeypatch.setattr(sched_module, "_semaphore", asyncio.Semaphore(3))
    monkeypatch.setattr(sched_module.settings, "retry_base_delay", 0.05)

    payload = TaskBatchSubmit(tasks=[
        {"id": "t1", "name": "Flaky Task", "duration": 0.05, "failure_rate": 1.0, "max_retries": 1}
    ])
    async with factory() as db:
        tasks = await submit_batch(db, payload)
    task_id = tasks[0].id

    # attempt 1 fails (random < 1.0), attempt 2 succeeds
    call_count = 0
    def controlled_random():
        nonlocal call_count
        call_count += 1
        return 0.0 if call_count == 1 else 0.5

    with patch("app.services.scheduler.random.random", side_effect=controlled_random):
        await sched_module._dispatch_ready_tasks()
        await asyncio.sleep(0.5)
        await sched_module._dispatch_ready_tasks()  # pick up WAITING again after backoff
        task = await _run_until_done(factory, task_id, max_seconds=5)

    assert task.status == TaskStatus.SUCCEEDED
    assert task.attempts == 2


@pytest.mark.asyncio
async def test_all_retries_exhausted(test_engine, monkeypatch):
    """Task with max_retries=2 fails all 3 attempts → FAILED."""
    from app.core import database as db_module
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", factory)
    monkeypatch.setattr(sched_module, "_semaphore", asyncio.Semaphore(3))
    monkeypatch.setattr(sched_module.settings, "retry_base_delay", 0.05)

    payload = TaskBatchSubmit(tasks=[
        {"id": "t1", "name": "Always Fails", "duration": 0.05, "failure_rate": 1.0, "max_retries": 2}
    ])
    async with factory() as db:
        tasks = await submit_batch(db, payload)
    task_id = tasks[0].id

    with patch("app.services.scheduler.random.random", return_value=0.0):  # always fail
        for _ in range(3):
            await sched_module._dispatch_ready_tasks()
            await asyncio.sleep(0.5)

        task = await _run_until_done(factory, task_id, max_seconds=5)

    assert task.status == TaskStatus.FAILED
    assert task.attempts == 3  # max_retries=2 → 3 total attempts


@pytest.mark.asyncio
async def test_attempt_count_persisted(test_engine, monkeypatch):
    """Verify attempt count increments correctly."""
    from app.core import database as db_module
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", factory)
    monkeypatch.setattr(sched_module, "_semaphore", asyncio.Semaphore(3))
    monkeypatch.setattr(sched_module.settings, "retry_base_delay", 0.05)

    payload = TaskBatchSubmit(tasks=[
        {"id": "t1", "name": "Count Test", "duration": 0.05, "failure_rate": 1.0, "max_retries": 1}
    ])
    async with factory() as db:
        tasks = await submit_batch(db, payload)
    task_id = tasks[0].id

    with patch("app.services.scheduler.random.random", return_value=0.0):
        await sched_module._dispatch_ready_tasks()
        await asyncio.sleep(0.3)
        await sched_module._dispatch_ready_tasks()
        task = await _run_until_done(factory, task_id, max_seconds=5)

    assert task.attempts == 2
