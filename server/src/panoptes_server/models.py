from datetime import datetime
from enum import Enum

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class WorkflowStatus(str, Enum):
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    NO_EXECUTION = "no_execution"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class Workflow(SQLModel, table=True):
    __tablename__ = "workflow"

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(index=True, unique=True)
    name: str | None = None
    status: WorkflowStatus = Field(default=WorkflowStatus.RUNNING)
    started_at: datetime
    completed_at: datetime | None = None
    total_jobs: int | None = None
    snakemake_version: str | None = None
    cwd: str | None = None
    snakefile: str | None = None


class Job(SQLModel, table=True):
    __tablename__ = "job"
    __table_args__ = (UniqueConstraint("workflow_id", "internal_id"),)

    id: int | None = Field(default=None, primary_key=True)
    workflow_id: int = Field(foreign_key="workflow.id", index=True)
    internal_id: int = Field(index=True)
    rule: str = Field(index=True)
    wildcards: str | None = None  # JSON string
    status: JobStatus = Field(default=JobStatus.PENDING)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    threads: int | None = None
    log_path: str | None = None


class WorkflowDag(SQLModel, table=True):
    """Rule-level dependency graph captured at workflow start.

    One row per workflow; payload is JSON-encoded
    `{"nodes": [{"rule": "..."}], "edges": [{"source": int, "target": int}]}`.
    """
    __tablename__ = "workflow_dag"

    workflow_id: int = Field(foreign_key="workflow.id", primary_key=True)
    payload: str
    captured_at: datetime


class JobEvent(SQLModel, table=True):
    __tablename__ = "job_event"
    __table_args__ = (UniqueConstraint("job_id", "timestamp", "event"),)

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id", index=True)
    timestamp: datetime
    event: str
    detail: str | None = None  # JSON
