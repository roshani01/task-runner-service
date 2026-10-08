"""Tests for task cancellation semantics."""
import asyncio
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.task import Task, TaskStatus
from app.schemas.task import TaskBatchSubmit
from app.services import scheduler as sched_module
from app.services.task_service import submit_batch


@pytest.mark.asyncio
async def test_cancel_waiting_task(client):
    resp = await client.post("/tasks", json={"tasks": [
        {"id": "t1", "name": "Cancellable Task", "duration": 0.01}
    ]})
    task_id = resp.json()[0]["id"]

    resp = await client.post(f"/tasks/{task_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"

    resp = await client.get(f"/tasks/{task_id}")
    assert resp.json()["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_cancel_cascades_to_dependents(client):
    """Cancelling a task should BLOCK all downstream dependents."""
    resp = await client.post("/tasks", json={"tasks": [
        {"id": "A", "name": "Task A"},
        {"id": "B", "name": "Task B", "depends_on": ["A"]},
        {"id": "C", "name": "Task C", "depends_on": ["B"]},
    ]})
    tasks = {t["name"]: t for t in resp.json()}
    a_id = tasks["Task A"]["id"]
    b_id = tasks["Task B"]["id"]
    c_id = tasks["Task C"]["id"]

    await client.post(f"/tasks/{a_id}/cancel")

    resp_b = await client.get(f"/tasks/{b_id}")
    resp_c = await client.get(f"/tasks/{c_id}")
    assert resp_b.json()["status"] == "BLOCKED"
    assert resp_c.json()["status"] == "BLOCKED"


@pytest.mark.asyncio
async def test_cancel_already_cancelled_is_idempotent(client):
    resp = await client.post("/tasks", json={"tasks": [
        {"id": "t1", "name": "Task X"}
    ]})
    task_id = resp.json()[0]["id"]

    await client.post(f"/tasks/{task_id}/cancel")
    resp2 = await client.post(f"/tasks/{task_id}/cancel")
    assert resp2.status_code == 200  # idempotent


@pytest.mark.asyncio
async def test_cancel_succeeded_task_rejected(test_engine, monkeypatch):
    """Cannot cancel a task that has already SUCCEEDED."""
    from app.core import database as db_module
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", factory)
    monkeypatch.setattr(sched_module, "_semaphore", asyncio.Semaphore(3))

    from httpx import ASGITransport, AsyncClient
    from app.main import app

    import app.main as main_module
    monkeypatch.setattr(main_module, "on_startup", lambda: None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/tasks", json={"tasks": [
            {"id": "t1", "name": "Done Task", "duration": 0.05, "failure_rate": 0.0}
        ]})
        task_id = resp.json()[0]["id"]

        with patch("app.services.scheduler.random.random", return_value=0.5):
            await sched_module._dispatch_ready_tasks()
            await asyncio.sleep(0.3)

        resp2 = await ac.post(f"/tasks/{task_id}/cancel")
        # Should be 409 — task is not in WAITING state
        assert resp2.status_code == 409
