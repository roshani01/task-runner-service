"""
Tests for failed dependency propagation (BLOCKED state).
"""
import asyncio
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.task import Task, TaskStatus
from app.schemas.task import TaskBatchSubmit
from app.services import scheduler as sched_module
from app.services.task_service import submit_batch


async def _wait_for_status(factory, task_id, expected_statuses, max_seconds=10):
    for _ in range(max_seconds * 10):
        await asyncio.sleep(0.1)
        async with factory() as db:
            result = await db.execute(select(Task).where(Task.id == task_id))
            task = result.scalar_one_or_none()
            if task and task.status in expected_statuses:
                return task
    return task


@pytest.mark.asyncio
async def test_failed_dependency_blocks_child(test_engine, monkeypatch):
    """
    A → B. If A permanently fails, B should become BLOCKED.
    """
    from app.core import database as db_module
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", factory)
    monkeypatch.setattr(sched_module, "_semaphore", asyncio.Semaphore(3))
    monkeypatch.setattr(sched_module.settings, "retry_base_delay", 0.05)

    payload = TaskBatchSubmit(tasks=[
        {"id": "A", "name": "Task A", "duration": 0.05, "failure_rate": 1.0, "max_retries": 0},
        {"id": "B", "name": "Task B", "duration": 0.05, "failure_rate": 0.0, "depends_on": ["A"]},
    ])
    async with factory() as db:
        tasks = await submit_batch(db, payload)
    id_map = {t.name: t.id for t in tasks}

    with patch("app.services.scheduler.random.random", return_value=0.0):
        await sched_module._dispatch_ready_tasks()
        await asyncio.sleep(0.5)

    task_b = await _wait_for_status(factory, id_map["Task B"], {TaskStatus.BLOCKED}, max_seconds=5)
    assert task_b.status == TaskStatus.BLOCKED


@pytest.mark.asyncio
async def test_blocked_propagates_transitively(test_engine, monkeypatch):
    """
    A → B → C. A fails → B BLOCKED → C BLOCKED.
    """
    from app.core import database as db_module
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", factory)
    monkeypatch.setattr(sched_module, "_semaphore", asyncio.Semaphore(3))
    monkeypatch.setattr(sched_module.settings, "retry_base_delay", 0.05)

    payload = TaskBatchSubmit(tasks=[
        {"id": "A", "name": "Root", "duration": 0.05, "failure_rate": 1.0, "max_retries": 0},
        {"id": "B", "name": "Mid", "duration": 0.05, "depends_on": ["A"]},
        {"id": "C", "name": "Leaf", "duration": 0.05, "depends_on": ["B"]},
    ])
    async with factory() as db:
        tasks = await submit_batch(db, payload)
    id_map = {t.name: t.id for t in tasks}

    with patch("app.services.scheduler.random.random", return_value=0.0):
        await sched_module._dispatch_ready_tasks()
        await asyncio.sleep(0.5)

    mid = await _wait_for_status(factory, id_map["Mid"], {TaskStatus.BLOCKED}, max_seconds=5)
    leaf = await _wait_for_status(factory, id_map["Leaf"], {TaskStatus.BLOCKED}, max_seconds=5)
    assert mid.status == TaskStatus.BLOCKED
    assert leaf.status == TaskStatus.BLOCKED
