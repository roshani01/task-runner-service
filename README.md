# Task Runner Service

A document-processing task runner built as a take-home engineering assignment. It demonstrates dependency management, concurrency control, retry logic, failure propagation, and crash recovery — all backed by PostgreSQL and exposed through a FastAPI HTTP API and a Next.js dashboard.

The "work" tasks perform is simulated (async sleep + configurable failure probability). The task runner itself is the real implementation.

---

## Architecture

```
frontend/          Next.js dashboard (TypeScript, Tailwind CSS)
backend/
  app/
    api/routes/    HTTP endpoints (FastAPI)
    core/          Config, DB session
    models/        SQLAlchemy ORM models
    schemas/       Pydantic request/response schemas
    services/      task_service.py (DB ops), scheduler.py (execution engine)
    utils/         dependency_graph.py (cycle detection)
  tests/           pytest test suite
  alembic/         Database migrations
docker-compose.yml PostgreSQL container
```

The scheduler runs as a background asyncio task inside the FastAPI process. It polls the database every second for tasks whose dependencies have all succeeded, and dispatches them up to the configured concurrency limit using `asyncio.Semaphore`.

---

## Technology Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.x |
| Database | PostgreSQL 16, Alembic migrations |
| Async DB driver | asyncpg |
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| Container | Docker Compose (PostgreSQL only) |
| Tests | pytest, pytest-asyncio, httpx |

---

## Prerequisites

- Python 3.12+
- Node.js 18+ and npm
- Docker and Docker Compose

---

## Setup

### 1. Start PostgreSQL

```bash
docker compose up -d
```

Wait for it to be healthy:

```bash
docker compose ps
```

### 2. Configure the backend

```bash
cd backend
cp ../.env.example .env
# Edit .env if needed (defaults work with the Docker Compose setup)
```

### 3. Create a virtual environment and install dependencies

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 4. Run database migrations

```bash
cd backend
alembic upgrade head
```

### 5. Start the backend

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API is available at http://localhost:8000  
Interactive docs: http://localhost:8000/docs

### 6. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard available at http://localhost:3000

---

## Running Tests

```bash
cd backend
# Make sure PostgreSQL is running and .env is configured
pytest -v
```

Tests use the same database as the application. Tables are truncated between tests.

---

## API Reference

### Submit tasks

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "tasks": [
      {"id": "upload", "name": "Upload Document", "duration": 2.0, "failure_rate": 0.1},
      {"id": "extract", "name": "Extract Text", "duration": 3.0, "depends_on": ["upload"]},
      {"id": "summary", "name": "Generate Summary", "duration": 2.0, "depends_on": ["extract"]},
      {"id": "embed", "name": "Create Embeddings", "duration": 4.0, "depends_on": ["summary"]}
    ]
  }'
```

### Get task status

```bash
curl http://localhost:8000/tasks/{task_id}
```

### List all tasks

```bash
curl http://localhost:8000/tasks
```

### Cancel a task

```bash
curl -X POST http://localhost:8000/tasks/{task_id}/cancel
```

### Get stats

```bash
curl http://localhost:8000/stats
```

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://...@localhost:5432/task_runner` | PostgreSQL connection string |
| `MAX_CONCURRENCY` | `3` | Maximum simultaneous running tasks |
| `RETRY_BASE_DELAY` | `1` | Base delay (seconds) for exponential backoff |
| `LOG_LEVEL` | `INFO` | Python logging level |

---

## Assumptions

- All tasks in a batch are submitted atomically — either all are accepted or none are.
- A `max_retries=N` task can make `N+1` total attempts (the initial try plus N retries).
- Dependencies can only reference tasks in the same batch submission. Cross-batch dependencies are not supported.
- Only `WAITING` tasks can be cancelled. Cancelling a `RUNNING` task is not supported (see DESIGN.md).
- If the service is killed while tasks are running, those tasks are reset to `WAITING` on the next startup. Work may execute more than once as a result.
