"""
scheduler.py — the core task execution engine.

Responsibilities:   
- Find tasks whose dependencies have all succeeded
- Respect the global concurrency limit (asyncio.Semaphore)
- Simulate task execution with configurable duration + failure rate
- Handle retries with exponential backoff
- Propagate BLOCKED state when a task permanently fails
- Recover interrupted RUNNING tasks on startup

The scheduler runs as a background asyncio loop. It polls the database
every second to find newly eligible tasks. This is simple and correct;
a production system might use LISTEN/NOTIFY instead to avoid polling.
"""

import asyncio
import logging
import random
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.task import Task, TaskAttempt, TaskDependency, TaskStatus
from app.services.task_service import _propagate_blocked

logger = logging.getLogger(__name__)

# Global semaphore — initialized in startup_recovery()
_semaphore: asyncio.Semaphore | None = None


def get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.max_concurrency)
    return _semaphore


async def startup_recovery() -> None:
    """
    On startup, any RUNNING task was interrupted mid-execution because the
    process was killed. We don't know if the work completed, so we reset
    them to WAITING so they'll be retried. This is at-least-once semantics.
    """
    global _semaphore
    _semaphore = asyncio.Semaphore(settings.max_concurrency)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Task).where(Task.status == TaskStatus.RUNNING)
        )
        interrupted = result.scalars().all()
        for task in interrupted:
            logger.warning(
                "Task %s (%s) was RUNNING at shutdown — resetting to WAITING for retry",
                task.id,
                task.name,
            )
            task.status = TaskStatus.WAITING
        if interrupted:
            await db.commit()


async def run_scheduler() -> None:
    """Main scheduler loop. Runs indefinitely until the process stops."""
    logger.info("Scheduler started (max_concurrency=%d)", settings.max_concurrency)
    while True:
        try:
            await _dispatch_ready_tasks()
        except Exception:
            logger.exception("Unexpected error in scheduler loop")
        await asyncio.sleep(1)


async def _dispatch_ready_tasks() -> None:
    """
    Find all WAITING tasks whose dependencies have all SUCCEEDED,
    then launch them up to the concurrency limit.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Task)
            .where(Task.status == TaskStatus.WAITING)
            .options(selectinload(Task.dependencies))
            .order_by(Task.created_at.asc())  # FIFO
        )
        waiting_tasks = result.scalars().all()

    for task in waiting_tasks:
        if not await _all_dependencies_succeeded(task):
            continue

        # Acquire the semaphore before launching — this is the only place
        # we take a slot, so we can never exceed max_concurrency.
        # We use acquire() rather than a context-manager because we want
        # to release it inside the spawned coroutine after it finishes.
        semaphore = get_semaphore()
        await semaphore.acquire()

        # Check once more inside a fresh session in case the task was
        # cancelled or grabbed by another scheduler iteration between
        # the query above and the semaphore acquisition.
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Task).where(Task.id == task.id))
            fresh = result.scalar_one_or_none()
            if fresh is None or fresh.status != TaskStatus.WAITING:
                semaphore.release()
                continue

            fresh.status = TaskStatus.RUNNING
            fresh.started_at = datetime.now(timezone.utc)
            await db.commit()

        asyncio.create_task(_run_task(task.id))


async def _all_dependencies_succeeded(task: Task) -> bool:
    """Return True if every dependency of this task has SUCCEEDED."""
    if not task.dependencies:
        return True

    dep_ids = [d.depends_on_task_id for d in task.dependencies]
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Task.status).where(Task.id.in_(dep_ids))
        )
        statuses = [row.status for row in result]

    return all(s == TaskStatus.SUCCEEDED for s in statuses)


async def _run_task(task_id) -> None:
    """
    Execute a single task attempt. Handles success, failure, retry, and
    permanent failure (which triggers blocked-propagation).
    Releases the semaphore slot when done regardless of outcome.
    """
    semaphore = get_semaphore()
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Task).where(Task.id == task_id))
            task = result.scalar_one_or_none()
            if task is None:
                return

            attempt_number = task.attempts + 1
            task.attempts = attempt_number
            started = datetime.now(timezone.utc)
            task.started_at = started
            attempt_record = TaskAttempt(
                task_id=task.id,
                attempt_number=attempt_number,
                started_at=started,
            )
            db.add(attempt_record)
            await db.commit()
            attempt_id = attempt_record.id

        # Simulate work outside the DB session
        logger.info("Task %s attempt %d starting (duration=%.1fs)", task_id, attempt_number, task.duration)
        await asyncio.sleep(task.duration)

        # Determine outcome
        failed = random.random() < task.failure_rate
        completed_at = datetime.now(timezone.utc)

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Task).where(Task.id == task_id))
            task = result.scalar_one_or_none()
            if task is None:
                return

            # Update the attempt record
            attempt_result = await db.execute(
                select(TaskAttempt).where(TaskAttempt.id == attempt_id)
            )
            attempt = attempt_result.scalar_one_or_none()

            if not failed:
                logger.info("Task %s attempt %d succeeded", task_id, attempt_number)
                task.status = TaskStatus.SUCCEEDED
                task.completed_at = completed_at
                task.error_message = None
                if attempt:
                    attempt.completed_at = completed_at
                    attempt.outcome = "succeeded"
            else:
                error_msg = f"Simulated failure on attempt {attempt_number}"
                logger.warning("Task %s attempt %d failed: %s", task_id, attempt_number, error_msg)
                task.error_message = error_msg
                if attempt:
                    attempt.completed_at = completed_at
                    attempt.outcome = "failed"
                    attempt.error_message = error_msg

                # max_retries=N means up to N+1 total attempts
                if attempt_number <= task.max_retries:
                    delay = settings.retry_base_delay * (2 ** (attempt_number - 1))
                    logger.info("Task %s will retry in %.1fs", task_id, delay)
                    task.status = TaskStatus.WAITING
                    await db.commit()
                    await asyncio.sleep(delay)
                    # Re-queue by setting back to WAITING; scheduler will pick it up
                    return
                else:
                    logger.error("Task %s permanently failed after %d attempts", task_id, attempt_number)
                    task.status = TaskStatus.FAILED
                    task.completed_at = completed_at
                    await db.flush()
                    await _propagate_blocked(db, task_id)

            await db.commit()

    except asyncio.CancelledError:
        # Process shutdown — the startup_recovery will handle this on next start
        raise
    except Exception:
        logger.exception("Unhandled error executing task %s", task_id)
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Task).where(Task.id == task_id))
            task = result.scalar_one_or_none()
            if task:
                task.status = TaskStatus.FAILED
                task.error_message = "Internal scheduler error"
                await db.flush()
                await _propagate_blocked(db, task_id)
                await db.commit()
    finally:
        semaphore.release()
