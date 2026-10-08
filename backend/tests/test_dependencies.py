"""Tests for dependency handling and circular dependency detection."""
import pytest

from app.utils.dependency_graph import build_adjacency, detect_cycle


# --- Unit tests for cycle detection (no DB needed) ---

def test_simple_cycle_detected():
    tasks = [
        {"id": "A", "depends_on": ["B"]},
        {"id": "B", "depends_on": ["C"]},
        {"id": "C", "depends_on": ["A"]},
    ]
    adj = build_adjacency(tasks)
    cycle = detect_cycle(adj)
    assert cycle is not None
    assert len(cycle) >= 3


def test_longer_cycle_detected():
    tasks = [
        {"id": "A", "depends_on": ["B"]},
        {"id": "B", "depends_on": ["C"]},
        {"id": "C", "depends_on": ["D"]},
        {"id": "D", "depends_on": ["A"]},
    ]
    adj = build_adjacency(tasks)
    assert detect_cycle(adj) is not None


def test_valid_dag_no_cycle():
    tasks = [
        {"id": "A", "depends_on": []},
        {"id": "B", "depends_on": ["A"]},
        {"id": "C", "depends_on": ["A", "B"]},
    ]
    adj = build_adjacency(tasks)
    assert detect_cycle(adj) is None


def test_independent_tasks_no_cycle():
    tasks = [
        {"id": "A", "depends_on": []},
        {"id": "B", "depends_on": []},
        {"id": "C", "depends_on": []},
    ]
    adj = build_adjacency(tasks)
    assert detect_cycle(adj) is None


def test_self_loop_cycle():
    tasks = [{"id": "A", "depends_on": ["A"]}]
    adj = build_adjacency(tasks)
    assert detect_cycle(adj) is not None


# --- Integration tests via API ---

@pytest.mark.asyncio
async def test_api_rejects_circular_dependency(client):
    resp = await client.post("/tasks", json={"tasks": [
        {"id": "A", "name": "Task A", "depends_on": ["B"]},
        {"id": "B", "name": "Task B", "depends_on": ["C"]},
        {"id": "C", "name": "Task C", "depends_on": ["A"]},
    ]})
    assert resp.status_code == 422
    assert "Circular" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_api_rejects_unknown_dependency(client):
    resp = await client.post("/tasks", json={"tasks": [
        {"id": "A", "name": "Task A", "depends_on": ["nonexistent"]},
    ]})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_api_accepts_valid_dependency_chain(client):
    resp = await client.post("/tasks", json={"tasks": [
        {"id": "upload", "name": "Upload Document", "duration": 0.01},
        {"id": "extract", "name": "Extract Text", "duration": 0.01, "depends_on": ["upload"]},
        {"id": "summary", "name": "Generate Summary", "duration": 0.01, "depends_on": ["extract"]},
    ]})
    assert resp.status_code == 201
    tasks = {t["name"]: t for t in resp.json()}
    assert len(tasks["Extract Text"]["dependency_ids"]) == 1
    assert len(tasks["Generate Summary"]["dependency_ids"]) == 1
