from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer

from panoptes_server.models import JobStatus, WorkflowStatus


def serialize_utc(dt: datetime | None) -> str | None:
    """Format a datetime as ISO-8601 with an explicit UTC offset.

    SQLAlchemy + sqlite roundtrips strip tzinfo, so we treat naive
    datetimes here as UTC (which is what the ingest service stores).
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()


class WorkflowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    name: str | None
    status: WorkflowStatus
    started_at: datetime
    completed_at: datetime | None
    total_jobs: int | None
    snakemake_version: str | None
    cwd: str | None
    snakefile: str | None

    @field_serializer("started_at", "completed_at")
    def _ser_dt(self, v: datetime | None) -> str | None:
        return serialize_utc(v)


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_id: int
    internal_id: int
    rule: str
    wildcards: str | None
    status: JobStatus
    started_at: datetime | None
    finished_at: datetime | None
    threads: int | None
    log_path: str | None

    @field_serializer("started_at", "finished_at")
    def _ser_dt(self, v: datetime | None) -> str | None:
        return serialize_utc(v)


class WorkflowRename(BaseModel):
    name: str


class IngestEvent(BaseModel):
    """A single LogEvent payload from the snakemake plugin.

    Schema is permissive — extra keys are kept under `detail` JSON. Only
    the dispatch key (`event`) and `ts` are required across all events.
    """

    event: str
    ts: datetime
    # Workflow-level
    snakemake_version: str | None = None
    snakefile: str | None = None
    cwd: str | None = None
    total_jobs: int | None = None
    workflow_name: str | None = None
    # Job-level
    internal_id: int | None = None
    rule: str | None = None
    wildcards: dict[str, Any] | None = None
    threads: int | None = None
    log: str | None = None
    # Progress
    done: int | None = None
    total: int | None = None
    # Rulegraph payload (RULEGRAPH event)
    nodes: list[dict[str, Any]] | None = None
    edges: list[dict[str, Any]] | None = None
    # Free-form
    detail: dict[str, Any] | None = None


class IngestBatch(BaseModel):
    run_id: str
    events: list[IngestEvent]


class IngestResponse(BaseModel):
    accepted: int


class ServiceInfo(BaseModel):
    status: str
    version: str


class DagNode(BaseModel):
    rule: str


class DagEdge(BaseModel):
    source: int
    target: int


class WorkflowDagRead(BaseModel):
    nodes: list[DagNode]
    edges: list[DagEdge]
    captured_at: datetime

    @field_serializer("captured_at")
    def _ser_captured(self, v: datetime) -> str:
        return serialize_utc(v)


class JobLogRead(BaseModel):
    path: str
    lines: list[str]
    truncated: bool
    size_bytes: int
