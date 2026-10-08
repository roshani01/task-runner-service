# Design

## What the service does

The task runner accepts batches of tasks, resolves their dependencies, and executes them respecting a global concurrency limit. Tasks are persisted in PostgreSQL so they survive process restarts. The simulated work is an `asyncio.sleep` combined with a configurable random failure probability — the task runner itself, not the document processing, is what this project is demonstrating.

## Document-processing scenario

The example scenario is a pipeline for processing uploaded documents:

```
Upload Document → Extract Text → Generate Summary → Create Embeddings → Store Result
```

Each step depends on the previous one completing successfully. If any step permanently fails, all downstream steps are marked BLOCKED rather than waiting indefinitely. Each step has a configurable duration (simulated processing time) and failure probability (simulated flakiness).

---

## Architecture

The backend is a single FastAPI process with two logical components:

1. **HTTP API** — accepts submissions, handles status queries and cancellation, returns stats.
2. **Scheduler** — a background `asyncio.Task` that runs a loop every second. It queries the DB for WAITING tasks whose dependencies have all SUCCEEDED, then dispatches them within the concurrency limit.

The scheduler and the API share the same PostgreSQL database. There is no message queue, no separate worker process, and no in-memory task queue. Everything that matters is in the database.

---

## Task lifecycle

```
                 ┌──────────┐
    submit ───▶  │ WAITING  │ ◀── retry after failure
                 └────┬─────┘
                      │ scheduler picks up
                 ┌────▼─────┐
                 │ RUNNING  │
                 └────┬─────┘
           ┌──────────┴─────────┐
      success               failure
           │                    │
    ┌──────▼───┐         attempts <= max_retries?
    │SUCCEEDED │          Yes → WAITING (with backoff)
    └──────────┘          No  → FAILED → propagate BLOCKED to dependents
```

Cancellation:

```
WAITING → CANCELLED (and all dependents → BLOCKED)
```

---

## Dependency handling

Dependencies are stored in a normalized `task_dependencies` table, not as a JSON list. Each row records that `task_id` depends on `depends_on_task_id`. This makes it straightforward to query all dependencies of a task, or all tasks that depend on a given task, with simple `WHERE` clauses and joins.

At submission, all dependency IDs must be present in the same batch. Cross-batch dependencies are not supported. This keeps the submission transaction atomic: either the whole batch goes in or nothing does.

---

## Cycle detection

Before any task is written to the database, the submission handler runs a DFS-based cycle detection over the submitted batch. If a cycle exists, the entire batch is rejected with a 422 response that includes the cycle path.

The algorithm is iterative (not recursive) to avoid Python stack limits on large graphs. It uses a "coloring" approach: unvisited (0), in current path (1), fully explored (2). A back-edge to a node with color 1 indicates a cycle.

The cycle check happens in-process before any DB writes, so there is no risk of partially-written cyclic data.

---

## Concurrency control

**Question 1: How do we ensure the concurrency limit is never exceeded?**

The scheduler uses `asyncio.Semaphore(MAX_CONCURRENCY)`. Before a task transitions to RUNNING, the scheduler calls `semaphore.acquire()`. The semaphore is released in the task's `finally` block regardless of outcome.

A naive implementation might check a counter like:
```python
if running_count < max_concurrency:
    running_count += 1
    start_task()
```
This has a race: if the scheduler loop runs again before the first task finishes incrementing the count, two tasks could both see `running_count < limit` and both start. With `asyncio.Semaphore`, the acquire is atomic — at most `MAX_CONCURRENCY` coroutines can hold the semaphore simultaneously.

There is a secondary defence: after acquiring the semaphore, the task re-reads its own status from the database and verifies it is still WAITING before transitioning to RUNNING. This prevents a race between the scheduler's dispatch loop and a concurrent cancellation request.

---

## Retry strategy

A task with `max_retries=N` can make at most `N+1` total attempts (one initial try plus N retries).

After each failed attempt, before the retry limit is reached, the task is reset to WAITING. The scheduler picks it up again after a delay. The delay is computed as:

```
delay = retry_base_delay * (2 ** (attempt_number - 1))
```

So with `retry_base_delay=1`:
- After attempt 1: wait 1 second
- After attempt 2: wait 2 seconds  
- After attempt 3: wait 4 seconds

The backoff sleep happens inside the running task coroutine, not by scheduling a future wakeup. This means the semaphore slot is held during the backoff delay. This is the simplest correct approach given the design; a more sophisticated system might release the slot during backoff.

---

## Failed dependency propagation

When a task permanently fails (attempts exhausted), the scheduler calls `_propagate_blocked()`. This uses BFS to find all downstream dependents and marks them BLOCKED. The same function is called when a WAITING task is cancelled.

Tasks already in a terminal state (SUCCEEDED, FAILED, CANCELLED) are skipped during propagation.

---

## Restart recovery

**Question 2: What happens when the service restarts while tasks are running?**

On startup, `startup_recovery()` queries the database for any tasks still in RUNNING state. These are tasks that were mid-execution when the process was killed. The recovery function resets them to WAITING.

This means interrupted tasks will re-execute from the beginning — work may run twice. The implementation deliberately chooses **at-least-once** semantics here. The alternative (marking interrupted tasks as FAILED) would silently lose work that may have completed just before the process died. Since the simulated work is idempotent by nature, re-running is safer than losing.

SUCCEEDED, FAILED, BLOCKED, and CANCELLED tasks are untouched by recovery.

---

## Cancellation semantics

Only WAITING tasks can be cancelled. Requesting cancellation of a RUNNING task returns a 409 error.

Rationale: cancelling a RUNNING asyncio task would require calling `task.cancel()` on the coroutine, which raises `CancelledError` at the next `await` point. In the scheduler, that `await` is the `asyncio.sleep` simulating work. Cancelling mid-sleep might be acceptable for simulated work, but in a real system the underlying work (an external HTTP call, a database write, a file write) may have already started and cancellation would not undo it. Documenting "RUNNING tasks cannot be cancelled" is more honest than pretending cancellation is clean.

When a WAITING task is cancelled, all its downstream dependents are marked BLOCKED via BFS propagation.

---

## FIFO scheduling

**Question 3: When several tasks are ready and a slot opens, which one runs next?**

The scheduler queries WAITING tasks ordered by `created_at ASC`. The oldest WAITING task runs next.

Why FIFO: it is predictable, simple, and avoids starvation — every task will eventually run as long as its dependencies complete. Priority queues require either caller-specified priorities (which adds API complexity) or heuristics (which are opaque).

Where FIFO gives a poor result: if a short 0.1-second task is submitted after 100 long 60-second tasks, it will wait behind all 100 tasks rather than running immediately. A priority system where tasks declare expected duration and shorter tasks run first (Shortest Job First) would give better average wait time in that scenario. But SJF requires accurate duration estimates and is much harder to make fair.

---

## Execution history

Every attempt is recorded in `task_attempts`. This includes: attempt number, start time, completion time, outcome (succeeded/failed), and error message. The `/tasks/{id}` response includes the full attempt history, which is useful for debugging flaky tasks.

---

## Important correctness invariant

**Question 4: What must always be true for the service to be considered correct?**

The concurrency limit must never be exceeded. At most `MAX_CONCURRENCY` tasks can be in RUNNING state at any point in time.

This is enforced by the `asyncio.Semaphore` in `scheduler.py`. The semaphore is acquired before the task transitions to RUNNING and released in the `finally` block after the task completes or fails. No code path can start a task without first acquiring the semaphore.

The secondary check (re-reading task status after semaphore acquisition) ensures that a task cancelled between the dispatch query and the semaphore acquire does not consume a slot.
