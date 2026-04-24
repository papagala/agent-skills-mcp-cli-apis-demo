from datetime import datetime, timezone
from itertools import count
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

TaskStatus = Literal["open", "in_progress", "done"]
TaskPriority = Literal["low", "medium", "high"]


class Task(BaseModel):
    id: int
    title: str
    assignee: str
    priority: TaskPriority
    status: TaskStatus
    note: str | None = None
    created_at: datetime
    updated_at: datetime


class CreateTaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    assignee: str = Field(min_length=1, max_length=80)
    priority: TaskPriority = "medium"


class UpdateTaskRequest(BaseModel):
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    note: str | None = None


_id_sequence = count(start=1)
_tasks: dict[int, Task] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _seed_demo_data() -> None:
    if _tasks:
        return
    seeds = [
        ("Investigate flaky test in payment-service", "alice", "high"),
        ("Document onboarding for new hires", "bob", "low"),
        ("Upgrade base image to python:3.12", "carol", "medium"),
    ]
    for title, assignee, priority in seeds:
        task_id = next(_id_sequence)
        timestamp = _now()
        _tasks[task_id] = Task(
            id=task_id,
            title=title,
            assignee=assignee,
            priority=priority,
            status="open",
            note=None,
            created_at=timestamp,
            updated_at=timestamp,
        )


app = FastAPI(title="Tasks API", version="0.1.0")
_seed_demo_data()


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/tasks", response_model=list[Task])
def list_tasks(status: TaskStatus | None = None) -> list[Task]:
    tasks = list(_tasks.values())
    if status is None:
        return tasks
    return [task for task in tasks if task.status == status]


@app.get("/tasks/{task_id}", response_model=Task)
def get_task(task_id: int) -> Task:
    task = _tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@app.post("/tasks", response_model=Task, status_code=201)
def create_task(payload: CreateTaskRequest) -> Task:
    task_id = next(_id_sequence)
    timestamp = _now()
    task = Task(
        id=task_id,
        title=payload.title,
        assignee=payload.assignee,
        priority=payload.priority,
        status="open",
        note=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    _tasks[task_id] = task
    return task


@app.patch("/tasks/{task_id}", response_model=Task)
def update_task(task_id: int, payload: UpdateTaskRequest) -> Task:
    task = _tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    refreshed = task.model_copy(update={**updates, "updated_at": _now()})
    _tasks[task_id] = refreshed
    return refreshed


@app.post("/admin/reset", response_model=list[Task])
def reset_demo_data() -> list[Task]:
    """Wipe all tasks and re-seed the demo dataset. Demo-only convenience."""
    global _id_sequence
    _tasks.clear()
    _id_sequence = count(start=1)
    _seed_demo_data()
    return list(_tasks.values())
