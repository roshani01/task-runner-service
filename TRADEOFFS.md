# Tradeoffs

## 1. PostgreSQL vs SQLite

**Decision:** PostgreSQL.

**Alternative:** SQLite is simpler to set up (no Docker required) and would work fine for a take-home project this size.

**Why PostgreSQL:** The assignment explicitly requires it. Beyond compliance, PostgreSQL handles concurrent writes more reliably — SQLite's write-lock would be a problem when the scheduler and API are writing simultaneously, even in an asyncio single-process setup. PostgreSQL also supports the UUID, enum, and timezone-aware datetime types natively.

**Downside:** Requires Docker or a local PostgreSQL installation to run. The setup is slightly more involved than SQLite. For a pure demo, this is unnecessary overhead.

---

## 2. In-process asyncio scheduler vs. separate worker (Celery, etc.)

**Decision:** Single-process asyncio scheduler running as a background task inside the FastAPI process.

**Alternative:** Celery with Redis or RabbitMQ as a broker. The scheduler and API would run as separate processes communicating over a message queue.

**Why in-process:** The assignment is small. Adding Celery and Redis adds two more infrastructure dependencies, a separate process to start and manage, and a debugging surface that dwarfs the actual task runner logic. The asyncio approach keeps everything in one codebase, one process, one database — which is much easier to reason about for an interview. The `asyncio.Semaphore` gives correct concurrency control without distributed locking.

**Downside:** The scheduler is tied to the FastAPI process. If you want to scale API servers horizontally, the scheduler would run in each instance and tasks could be double-dispatched. This is a real production concern. Mitigation would require a distributed lock (e.g. PostgreSQL advisory locks or a `SELECT FOR UPDATE SKIP LOCKED` pattern) when claiming tasks. That pattern is well-understood but adds complexity that doesn't belong in a 4-hour assignment.

---

## 3. Semaphore-held backoff delay vs. releasing the slot during backoff

**Decision:** The scheduler holds the semaphore slot during the exponential backoff sleep between retry attempts.

**Alternative:** Release the semaphore immediately after a failed attempt, sleep the backoff delay, then re-queue the task and let the scheduler pick it up normally.

**Why hold the slot:** Simpler code. The entire task lifecycle — execution, failure, backoff, retry — happens inside one coroutine. There are no re-queuing races, no duplicate execution risk, no need to track "this task is in backoff delay."

**Downside:** During the backoff sleep, the slot is unavailable for other tasks. With `max_retries=3` and `retry_base_delay=1`, a failing task occupies a slot for up to 7 seconds of sleep (1+2+4) where it is doing nothing. With `MAX_CONCURRENCY=3` and three tasks in retry backoff simultaneously, the service appears completely idle. This is the most significant operational downside of this design and should be fixed in a production system.

---

## 4. Reset interrupted RUNNING tasks to WAITING vs. marking them FAILED

**Decision:** On startup, RUNNING tasks are reset to WAITING.

**Alternative:** On startup, RUNNING tasks are marked FAILED (and their dependents BLOCKED).

**Why WAITING:** The service was killed without knowing whether the task's work completed or not. Marking it FAILED silently discards work that may have been completed just before the process died. Resetting to WAITING retries the work — which may cause it to execute twice if it completed before the kill, but at least the work is not silently lost. For idempotent operations (which simulated tasks are, by nature), this is safer.

**Downside:** Non-idempotent real tasks may execute twice. If a task is "send an email" or "charge a credit card," running it twice is harmful. In a real system, tasks should either be idempotent by design, or the recovery policy should be configurable per task type. This implementation documents the at-least-once assumption and leaves it to the caller to handle idempotency.
