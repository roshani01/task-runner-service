"""
task_service.py — database operations for tasks.

Scheduler logic lives in scheduler.py. This module only handles persistence.
"""
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.task import Task, TaskDependency, TaskStatus
from app.schemas.task import StatsRead, TaskBatchSubmit
from app.utils.dependency_graph import build_adjacency, detect_cycle

if TYPE_CHECKING:
    pass


class TaskNotFoundError(Exception):
    pass


class TaskValidationError(Exception):
    pass


async def submit_batch(db: AsyncSession, payload: TaskBatchSubmit) -> list[Task]:
    """
    Validate and persist a batch of tasks with their dependencies.

    Steps:
    1. Check for unknown dependency references within the batch
    2. Detect circular dependencies before touching the DB
    3. Persist tasks, then create dependency rows
    """
    task_dicts = [t.model_dump() for t in payload.tasks]
    batch_ids = {t["id"] for t in task_dicts}

    # All depends_on must reference tasks in the same batch
    for td in task_dicts:
        for dep in td["depends_on"]:
            if dep not in batch_ids:
                raise TaskValidationError(
                    f"Task '{td['id']}' references unknown dependency '{dep}'"
                )

    adj = build_adjacency(task_dicts)
    cycle = detect_cycle(adj)
    if cycle:
        raise TaskValidationError(f"Circular dependency detected: {' → '.join(cycle)}")

    # Map client string IDs to DB UUIDs
    id_map: dict[str, uuid.UUID] = {td["id"]: uuid.uuid4() for td in task_dicts}

    db_tasks: list[Task] = []
    for td in task_dicts:
        task = Task(
            id=id_map[td["id"]],
            name=td["name"],
            duration=td["duration"],
            failure_rate=td["failure_rate"],
            max_retries=td["max_retries"],
            status=TaskStatus.WAITING,
        )
        db.add(task)
        db_tasks.append(task)

    # Flush so FK constraints succeed when we insert dependencies
    await db.flush()

    for td in task_dicts:
        for dep_client_id in td["depends_on"]:
            dep_row = TaskDependency(
                task_id=id_map[td["id"]],
                depends_on_task_id=id_map[dep_client_id],
            )
            db.add(dep_row)

    await db.commit()

    # Reload with relationships for the response
    refreshed = []
    for task in db_tasks:
        await db.refresh(task, ["dependencies", "history"])
        refreshed.append(task)

    return refreshed


async def get_task(db: AsyncSession, task_id: uuid.UUID) -> Task:
    result = await db.execute(
        select(Task)
        .where(Task.id == task_id)
        .options(selectinload(Task.dependencies), selectinload(Task.history))
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise TaskNotFoundError(task_id)
    return task


async def list_tasks(db: AsyncSession) -> list[Task]:
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.dependencies), selectinload(Task.history))
        .order_by(Task.created_at.asc())
    )
    return list(result.scalars().all())


async def cancel_task(db: AsyncSession, task_id: uuid.UUID) -> Task:
    """
    Cancel a WAITING task. RUNNING cancellation is not supported (documented in DESIGN.md).
    Dependents of a cancelled task become BLOCKED.
    """
    task = await get_task(db, task_id)

    if task.status == TaskStatus.CANCELLED:
        return task

    if task.status not in (TaskStatus.WAITING,):
        raise TaskValidationError(
            f"Cannot cancel task in state {task.status}. "
            "Only WAITING tasks can be cancelled."
        )

    task.status = TaskStatus.CANCELLED
    await db.flush()

    # Propagate BLOCKED to all downstream dependents
    await _propagate_blocked(db, task_id)

    await db.commit()
    await db.refresh(task, ["dependencies", "history"])
    return task


async def get_stats(db: AsyncSession) -> StatsRead:
    result = await db.execute(
        select(Task.status, func.count().label("cnt")).group_by(Task.status)
    )
    counts = {row.status: row.cnt for row in result}

    def c(s: TaskStatus) -> int:
        return counts.get(s, 0)

    total = sum(counts.values())
    return StatsRead(
        running=c(TaskStatus.RUNNING),
        waiting=c(TaskStatus.WAITING),
        succeeded=c(TaskStatus.SUCCEEDED),
        failed=c(TaskStatus.FAILED),
        blocked=c(TaskStatus.BLOCKED),
        cancelled=c(TaskStatus.CANCELLED),
        total=total,
    )


async def _propagate_blocked(db: AsyncSession, failed_task_id: uuid.UUID) -> None:
    """
    Walk the dependency graph and mark all downstream tasks BLOCKED.
    Uses BFS to avoid deep recursion on large graphs.
    """
    from collections import deque

    queue: deque[uuid.UUID] = deque([failed_task_id])
    visited: set[uuid.UUID] = {failed_task_id}

    while queue:
        current_id = queue.popleft()

        # Find tasks that directly depend on current_id
        result = await db.execute(
            select(TaskDependency.task_id).where(
                TaskDependency.depends_on_task_id == current_id
            )
        )
        dependent_ids = [row.task_id for row in result]

        for dep_id in dependent_ids:
            if dep_id in visited:
                continue
            visited.add(dep_id)

            dep_task_result = await db.execute(select(Task).where(Task.id == dep_id))
            dep_task = dep_task_result.scalar_one_or_none()
            if dep_task and dep_task.status in (TaskStatus.WAITING, TaskStatus.BLOCKED):
                dep_task.status = TaskStatus.BLOCKED
                queue.append(dep_id)

    await db.flush()
