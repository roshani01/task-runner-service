import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.task import TaskStatus


class TaskAttemptRead(BaseModel):
    id: int
    attempt_number: int
    started_at: datetime
    completed_at: datetime | None
    outcome: str | None
    error_message: str | None

    model_config = {"from_attributes": True}


class TaskRead(BaseModel):
    id: uuid.UUID
    name: str
    status: TaskStatus
    duration: float
    failure_rate: float
    max_retries: int
    attempts: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime
    dependency_ids: list[uuid.UUID] = Field(default_factory=list)
    history: list[TaskAttemptRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class TaskSubmit(BaseModel):
    """Schema for a single task in a submission batch."""

    id: str = Field(..., description="Client-provided string ID, used to wire up dependencies")
    name: str = Field(..., min_length=1, max_length=255)
    duration: float = Field(default=1.0, ge=0.0, le=3600.0, description="Simulated execution time in seconds")
    failure_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Probability of failure per attempt")
    max_retries: int = Field(default=0, ge=0, le=10)
    depends_on: list[str] = Field(default_factory=list, description="IDs of tasks this task depends on")


class TaskBatchSubmit(BaseModel):
    """
    Submit a batch of tasks that may depend on each other.
    All task IDs are resolved within the batch; they don't refer to previously submitted tasks.
    """

    tasks: list[TaskSubmit] = Field(..., min_length=1)

    @field_validator("tasks")
    @classmethod
    def no_duplicate_ids(cls, tasks: list[TaskSubmit]) -> list[TaskSubmit]:
        ids = [t.id for t in tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate task IDs in submission")
        return tasks


class TaskCancelResponse(BaseModel):
    task_id: uuid.UUID
    status: TaskStatus


class StatsRead(BaseModel):
    running: int
    waiting: int
    succeeded: int
    failed: int
    blocked: int
    cancelled: int
    total: int
