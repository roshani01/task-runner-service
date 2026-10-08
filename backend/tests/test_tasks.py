"""Tests for task submission and basic status retrieval."""
import pytest


@pytest.mark.asyncio
async def test_submit_single_task(client):
    resp = await client.post("/tasks", json={"tasks": [
        {"id": "t1", "name": "Upload Document", "duration": 0.01, "failure_rate": 0.0, "max_retries": 0}
    ]})
    assert resp.status_code == 201
    tasks = resp.json()
    assert len(tasks) == 1
    assert tasks[0]["name"] == "Upload Document"
    assert tasks[0]["status"] == "WAITING"
    assert tasks[0]["attempts"] == 0


@pytest.mark.asyncio
async def test_get_task_by_id(client):
    resp = await client.post("/tasks", json={"tasks": [
        {"id": "t1", "name": "Extract Text", "duration": 0.01}
    ]})
    task_id = resp.json()[0]["id"]

    resp = await client.get(f"/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Extract Text"


@pytest.mark.asyncio
async def test_get_nonexistent_task(client):
    resp = await client.get("/tasks/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_tasks(client):
    await client.post("/tasks", json={"tasks": [
        {"id": "t1", "name": "Task A", "duration": 0.01},
        {"id": "t2", "name": "Task B", "duration": 0.01},
    ]})
    resp = await client.get("/tasks")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_invalid_failure_rate(client):
    resp = await client.post("/tasks", json={"tasks": [
        {"id": "t1", "name": "Bad Task", "duration": 0.01, "failure_rate": 1.5}
    ]})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_duration_negative(client):
    resp = await client.post("/tasks", json={"tasks": [
        {"id": "t1", "name": "Bad Task", "duration": -1.0}
    ]})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_max_retries_negative(client):
    resp = await client.post("/tasks", json={"tasks": [
        {"id": "t1", "name": "Bad Task", "max_retries": -1}
    ]})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_duplicate_task_ids_in_batch(client):
    resp = await client.post("/tasks", json={"tasks": [
        {"id": "t1", "name": "Task A"},
        {"id": "t1", "name": "Task B"},
    ]})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_stats_endpoint(client):
    await client.post("/tasks", json={"tasks": [
        {"id": "t1", "name": "Task A"},
    ]})
    resp = await client.get("/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["waiting"] == 1
    assert data["total"] == 1
