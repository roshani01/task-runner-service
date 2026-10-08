"""
Concurrency limit tests.

These tests run the actual scheduler against a real DB to verify the
semaphore never allows more than max_concurrency tasks to run simultaneously.
We inject a tracking mechanism via monkeypatching asyncio.sleep to record
the maximum observed concurrency.
"""
import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.services import scheduler as sched_module
from app.services.scheduler import _dispatch_ready_tasks, get_semaphore, startup_recovery


@pytest.mark.asyncio
async def test_concurrency_limit_never_exceeded(test_engine, monkeypatch):
    """
    Submit N tasks (N > MAX_CONCURRENCY). Patch asyncio.sleep inside _run_task
    to record how many tasks are running concurrently at their peak.
    Assert peak <= max_concurrency.
    """
    from app.core import database as db_module
    from sqlalchemy.ext.asyncio import async_sessionmaker

    monkeypatch.setattr(db_module, "engine", test_engine)
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", factory)

    # Re-initialize semaphore for this test
    monkeypatch.setattr(sched_module, "_semaphore", asyncio.Semaphore(settings.max_concurrency))

    # Submit more tasks than max_concurrency
    task_count = settings.max_concurrency + 3
    from app.schemas.task import TaskBatchSubmit
    from app.services.task_service import submit_batch

    payload = TaskBatchSubmit(tasks=[
        {"id": f"t{i}", "name": f"Task {i}", "duration": 0.2, "failure_rate": 0.0}
        for i in range(task_count)
    ])
    async with factory() as db:
        await submit_batch(db, payload)

    # Track concurrency
    running_count = 0
    peak_count = 0
    lock = asyncio.Lock()

    original_sleep = asyncio.sleep

    async def tracking_sleep(delay):
        nonlocal running_count, peak_count
        async with lock:
            running_count += 1
            if running_count > peak_count:
                peak_count = running_count
        try:
            await original_sleep(delay)
        finally:
            async with lock:
                running_count -= 1

    with patch("app.services.scheduler.asyncio.sleep", side_effect=tracking_sleep):
        # Dispatch tasks and give them time to run
        await _dispatch_ready_tasks()
        await asyncio.sleep(1.5)

    assert peak_count > 0, "No tasks ran"
    assert peak_count <= settings.max_concurrency, (
        f"Concurrency limit violated: {peak_count} tasks ran simultaneously "
        f"(limit={settings.max_concurrency})"
    )
