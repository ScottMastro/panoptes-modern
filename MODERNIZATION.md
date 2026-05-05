# Panoptes Modernization Plan

Context doc for refreshing the panoptes snakemake monitor. Backend +
frontend rewrite; not a deps-bump pass.

## What's here

Inherited from the upstream `panoptes-organization/panoptes` fork
(last commit ~2 years ago, snakemake 7-era):

```
panoptes/
├── app.py                  Flask app factory + DB init
├── database.py             SQLAlchemy session
├── models.py               2 tables: Workflows, WorkflowMessages
├── routes/api.py           8 REST endpoints
├── server_utilities/       DB query helpers
├── schema_forms.py         marshmallow schemas
└── static/src/             jQuery + CoreUI 2.1.15 frontend
    ├── *.html              workflows.html, workflow.html, job.html
    ├── js/src/             charts.js, main.js, popovers.js (CoreUI demo)
    └── css/                bootstrap 4 era styling
```

Total: ~1000 LOC Python, ~400 LOC JS (mostly chart demos that need
deletion).

## Existing API surface

```
GET    /api/service-info
GET    /api/workflows
GET    /api/workflow/<id>
GET    /api/workflow/<id>/jobs
GET    /api/workflow/<id>/job/<job_id>
PUT    /api/workflow/<id>           (rename)
DELETE /api/workflow/<id>
DELETE /api/workflows/all
```

## Existing schema

```
workflows         id, name, status, done, total, started_at, completed_at
workflow_messages id, wf_id, msg, status
users             id, name, email                (unused; kill)
```

## Why it doesn't work on snakemake 8

Panoptes was the receive-side of snakemake 7's `--wms-monitor URL`
flag. snakemake 7 POSTed each rule's start/end events as JSON to the
panoptes server. snakemake 8 deleted that flag and replaced it with
the `snakemake-interface-logger-plugins` system (proper logger
plugin contract; LogEvent enums for `RUN_INFO`, `JOB_STARTED`,
`JOB_FINISHED`, `JOB_ERROR`, `WORKFLOW_STARTED`, `WORKFLOW_DONE`).

The HTTP receiver still works — what's missing is anything pushing
events to it. Two ways to fix that, both in scope below.

## Backend rewrite

### Stack choice

**FastAPI + SQLModel + Uvicorn**. Reasons:
- Async out of the box (matters when streaming live updates to the UI)
- Pydantic models double as request/response validators
- Native OpenAPI docs at `/docs`, useful for the snakemake plugin's POST contract
- SQLModel keeps the SQLAlchemy familiarity but with type-checked models
- WebSocket support without flask-sockets gymnastics

### Project layout

```
panoptes_modern/
├── server/
│   ├── main.py             FastAPI app + lifespan
│   ├── db.py               async engine, session dependency
│   ├── models.py           SQLModel tables (Workflow, Job, JobEvent)
│   ├── schemas.py          Pydantic request/response schemas
│   ├── routes/
│   │   ├── workflows.py    /api/v1/workflows*
│   │   ├── jobs.py         /api/v1/jobs*
│   │   ├── ingest.py       /api/v1/ingest         (logger plugin POSTs here)
│   │   └── ws.py           /api/v1/ws/{wf_id}     (live updates)
│   └── services/
│       ├── ingest.py       parse LogEvent payloads -> rows
│       └── stats.py        progress aggregations
├── plugin/
│   ├── pyproject.toml      package: snakemake-logger-plugin-panoptes
│   └── src/
│       └── snakemake_logger_plugin_panoptes/
│           └── __init__.py  Plugin class subscribing to LogEvent
└── ui/                      (frontend; see below)
```

### Schema redesign

The current schema has just `done` / `total` ints — too coarse for
the per-job UI we want. Replace with:

```python
class Workflow(SQLModel, table=True):
    id: int = Field(primary_key=True)
    run_id: str = Field(index=True, unique=True)   # snakemake's run UUID
    name: str | None
    status: WorkflowStatus = WorkflowStatus.RUNNING
    started_at: datetime
    completed_at: datetime | None
    total_jobs: int | None     # filled when DAG-build event arrives
    snakemake_version: str | None
    cwd: str | None
    snakefile: str | None

class Job(SQLModel, table=True):
    id: int = Field(primary_key=True)
    workflow_id: int = Field(foreign_key="workflow.id", index=True)
    rule: str = Field(index=True)
    wildcards: str | None       # JSON-encoded
    status: JobStatus = JobStatus.PENDING
    started_at: datetime | None
    finished_at: datetime | None
    threads: int | None
    log_path: str | None

class JobEvent(SQLModel, table=True):
    id: int = Field(primary_key=True)
    job_id: int = Field(foreign_key="job.id", index=True)
    timestamp: datetime
    event: str                  # 'started', 'finished', 'error', etc.
    detail: str | None          # JSON for arbitrary plugin payload
```

Drop `users` (no auth needed in v1; runs on a single-user dev box).
Drop `workflow_messages` (replaced by JobEvent).

### Logger plugin (the bridge)

A separate Python package, `snakemake-logger-plugin-panoptes`, that
implements the `snakemake-interface-logger-plugins` contract. The
plugin subscribes to LogEvent notifications from snakemake and POSTs
them to `/api/v1/ingest` on the panoptes server.

User invokes it via:

```bash
snakemake --logger panoptes --panoptes-url http://localhost:5000 ...
```

Plugin responsibilities (small, ~150 LOC):
- Buffer events; flush every N events or every K seconds
- Retry on connection failure (server might be starting up)
- Add a `run_id` so multiple concurrent snakemake invocations don't
  collide in the database
- Convert snakemake's LogEvent enums into the panoptes event vocabulary
  (1:1 mostly)

Tested against snakemake 8.20+ (logger plugin API stabilized there)
and 9.x.

### Ingest endpoint

Receives a list of LogEvent dicts. Idempotent — re-POSTs from the
plugin (after a transient network error) shouldn't double-count.

```
POST /api/v1/ingest
Body: {
  "run_id": "uuid-...",
  "events": [
    {"event": "WORKFLOW_STARTED", "ts": "...", "snakemake_version": "...",
     "snakefile": "...", "total_jobs": 9692},
    {"event": "JOB_STARTED", "ts": "...", "rule": "align_hg38",
     "wildcards": {"sample": "HG00097", "hap": "hap1"}, "internal_id": 1234},
    {"event": "JOB_FINISHED", "ts": "...", "internal_id": 1234},
    ...
  ]
}
```

Server upserts rows by `(run_id, internal_id)` for jobs and dedupes
events on `(job_id, timestamp, event)`.

### Live updates

WebSocket per-workflow at `/api/v1/ws/{workflow_id}`. The ingest
service publishes to an in-process pub/sub (asyncio.Queue) on every
event; ws clients subscribe and get pushed JSON deltas. Reconnect on
client side; on reconnect, server replays the last N events (or
client requests since-timestamp).

### Auth

V1: none, single-user. V2: token in `Authorization: Bearer ...`,
issued once at server start and printed to stderr (Jupyter-style).

## Frontend rewrite

### Stack choice

**Vite + React + TypeScript + TanStack Query + shadcn/ui +
recharts/visx**. Reasons:
- React's component model matches the natural workflow→job→event tree
- TanStack Query handles the polling/cache/websocket-merge story
- shadcn/ui copies in source rather than wrapping a vendor lib;
  better long-term maintainability
- recharts (or visx for the DAG view) for charts; visx if we want
  custom DAG layout

Drop: jQuery, CoreUI 2.x, Bootstrap 4, the chart.js demos.

### Pages

```
/                            workflows list (live)
/workflow/<id>               detail: progress bar, rule-grouped table
/workflow/<id>/job/<job_id>  job detail: timeline, log path, wildcards
/workflow/<id>/dag           DAG view (visx) — rule nodes colored by status
/about                       version + connection info
```

The DAG view is the headline feature panoptes never had — snakemake
provides DAG topology in the WORKFLOW_STARTED payload, so the server
can ship it once and the client renders + colors live.

### Build + deploy

```
ui/
├── package.json
├── vite.config.ts
├── src/
│   ├── App.tsx
│   ├── api/                 typed clients + WS hooks
│   ├── pages/
│   ├── components/
│   └── lib/
└── public/
```

Built bundle goes into `server/static/` and FastAPI serves it via
`StaticFiles` mount at `/`. Single-binary feel; no separate web
server needed.

## Phasing

### Phase 1 — backend MVP (~3-5 days)

1. Set up `server/` with FastAPI + SQLModel
2. Schema migrations (Alembic, even if v1 is just `create_all`)
3. Ingest endpoint accepting the LogEvent shape
4. CRUD routes mirroring the existing 8-endpoint API
5. Write the logger plugin in `plugin/`
6. Smoke test: run a small snakemake workflow with
   `--logger panoptes`, confirm rows land

### Phase 2 — UI MVP (~5-7 days)

1. Vite + React + TS scaffold in `ui/`
2. Workflows list page with TanStack Query polling
3. Workflow detail page with rule-grouped progress bars
4. Connect WebSocket hook for live updates
5. shadcn install + theme
6. Drop the bundle into `server/static/`

### Phase 3 — DAG view (~2-3 days)

1. Persist DAG topology on WORKFLOW_STARTED
2. visx force-directed or layered DAG layout
3. Click a node → job detail

### Phase 4 — polish

- Filters (by rule, by status)
- Search across jobs
- Failed job log preview (server reads `log:` paths, returns last N
  lines)
- Workflow comparison (two runs side-by-side)
- Export to JSON for archival

## Open questions

1. **Multi-user** — most labs run snakemake on a shared cluster.
   Should the server support multiple users posting to the same
   panoptes instance, or is this strictly single-user? Affects auth,
   workflow listing scope, schema (add `user` column to Workflow?).

2. **Deployment target** — local dev box, cluster login node, or
   separately-hosted? Cluster login node implies firewall
   considerations for the WebSocket; separate host implies the
   logger plugin needs reliable network back to panoptes.

3. **Persistence** — SQLite file (current), or postgres? SQLite is
   fine for hundreds of runs; if archive/long-term is in scope,
   postgres + a TTL job for old runs.

4. **DAG payload size** — snakemake's full DAG for a 10k-job workflow
   is megabytes. Stream nodes/edges incrementally rather than
   one-shot, or accept the upload size?

5. **Backwards compat with snakemake 7?** — there are still installs
   on 7. If we keep the legacy `--wms-monitor` HTTP endpoint as a
   shim, we cover both. ~1 day of extra work.

## What I'd actually do first

Phase 1 only. Confirm the logger plugin reliably ships events from
snakemake 8.20+ to a FastAPI ingest endpoint backed by SQLModel.
Once that's working end-to-end, the UI can iterate without further
backend churn.

Risk concentrated in:
- snakemake-interface-logger-plugins API stability across point
  releases (LogEvent enums have moved at least once)
- handling concurrent runs in a single panoptes instance (the
  `run_id` discipline must be airtight)

Both surface in phase 1's smoke test.

---

# Status (as-built)

Everything above is the original planning doc, kept for context. This
section reflects what actually shipped. The build was done in four
phases; all four are in the tree.

## Layout

```
panoptes-modern/
├── panoptes/      legacy Flask app — UNTOUCHED, kept as reference
├── server/        FastAPI + SQLModel + aiosqlite (new)
├── plugin/        snakemake-logger-plugin-panoptes (new)
└── ui/            Vite + React + TS + Tailwind (new)
```

The doc proposed a single `panoptes_modern/server/` dir; we used three
top-level siblings instead so the JS toolchain wasn't nested inside a
Python package. The legacy `panoptes/` is unchanged and not used by
the new stack — final cutover (renaming dirs, updating root
`Dockerfile` / `setup.py`) hasn't happened yet.

## What shipped vs the plan

**Shipped:**
- All 8 mirrored REST endpoints under `/api/v1/`, plus
  `POST /ingest`, `GET /workflows/{id}/{stats,dag}`,
  `GET /workflows/{id}/jobs/{job_id}/{events,log}`.
- `snakemake-logger-plugin-panoptes`: buffered HTTP forwarder,
  retry with backoff, `--logger panoptes --logger-panoptes-url ...`.
- React UI: workflows list, workflow detail (rule-grouped progress,
  recharts duration chart, jobs filters with URL-synced state, DAG
  tab), job detail (event timeline + log preview).
- DAG view: React Flow + dagre, color-coded by per-rule status,
  click-to-filter the jobs table.
- Live updates via WebSocket pub/sub (`/api/v1/ws/{wf_id}`); polling
  stays at 2s as a safety net.
- Built UI bundle is served by FastAPI at `/` via `StaticFiles` —
  single `uvicorn` invocation, no separate web server.
- 25 server tests, 7 plugin tests, all green. UI is `tsc --noEmit`
  clean and builds to ~256 KB gzipped.

**Deferred / not built:**
- snakemake 7 `--wms-monitor` backcompat shim (decision: drop).
- Auth (still none — single-user dev box assumption).
- Multi-user / per-user scoping.
- Run comparison (two runs side-by-side).
- JSON export of a workflow tree.
- Alembic migrations (schema bootstrap is `SQLModel.metadata.create_all()`
  in lifespan — fine until the schema settles).

**Stack deltas from the doc:**
- Charts: doc said "recharts (or visx)" — we used **recharts** for the
  duration histogram and **React Flow + dagre** for the DAG (better
  click/select UX than visx for graph interaction).
- shadcn/ui CLI: not actually invoked — hand-rolled the four
  components we needed (`badge`, `card`, `progress`, `tabs`) so the
  UI doesn't depend on the CLI's working directory layout. Same
  `cn(clsx + tailwind-merge)` convention.
- Snakemake: doc targeted 8.20+; current verification is on **9.13**.
  See "Snakemake version quirks" below.

## How to run

```bash
# 1. Server (defaults to ./panoptes.db; override via PANOPTES_DB_URL)
cd server && pip install -e ".[dev]"
PANOPTES_DB_URL="sqlite+aiosqlite:///$(pwd)/panoptes.db" \
  uvicorn panoptes_server.main:app --host 127.0.0.1 --port 5050

# 2. Plugin
cd ../plugin && pip install -e .

# 3. UI (only needed when iterating; the built bundle is served by the
#    server out of server/src/panoptes_server/static/)
cd ../ui && npm install && npm run build
# or for hot reload during development:
#   npm run dev      # talks to the running server via vite proxy

# 4. Point any snakemake run at the server
snakemake --logger panoptes \
          --logger-panoptes-url http://127.0.0.1:5050 \
          --cores 2
```

Then open `http://127.0.0.1:5050`. The "/docs" Swagger page is also
useful for poking the API directly.

## Open questions, resolved

1. **Multi-user** — out of scope for v1 (decision deferred).
2. **Deployment target** — local dev box. Cluster login node /
   separate-host scenarios untested.
3. **Persistence** — SQLite via aiosqlite. Migration to postgres
   would be a connection-string change plus moving `metadata.create_all`
   to alembic.
4. **DAG payload size** — non-issue: the rulegraph is rule-level
   (one node per rule, not per job), so even a 50-rule workflow is
   <5 KB. One-shot upload at workflow start is fine.
5. **SM7 backcompat** — dropped.

## Snakemake version quirks (worth knowing before touching the plugin)

These are the things that surfaced during smoke-testing on 9.13 and
forced plugin code to compensate. They likely also apply to late 8.x
but haven't been re-verified across the matrix.

1. **`WORKFLOW_STARTED` / `WORKFLOW_DONE` are not delivered to logger
   plugins** in the way the snakemake source suggests. The plugin
   synthesizes both itself: a startup event at handler init (with
   `snakemake.__version__`, `os.getcwd()`, and the Snakefile path
   guessed from the cwd) and a completion event in `close()`. The
   server has a fallback that marks a workflow `done` when an empty
   batch arrives and all known jobs are `done`, in case the plugin is
   killed before its synthetic completion event flushes.

2. **`RULEGRAPH` event payload is nested**. Snakemake puts the
   topology under `record.__dict__["rulegraph"]` as
   `{"nodes": [...], "links": [...]}` (note: `links`, not `edges`,
   and each link has both numeric `source`/`target` indices and
   `sourcerule`/`targetrule` names). The plugin unwraps and renames
   to `{nodes, edges}` on the wire so the server contract stays clean.

3. **Field name inconsistency**: `JOB_INFO` and `JOB_ERROR` use
   `jobid`; `JOB_FINISHED` uses `job_id` (with underscore);
   `JOB_STARTED` uses `jobs` (a *list* of ids). The plugin handles
   each individually and fans `JOB_STARTED` out into one ingest
   event per id.

4. **`needs_rulegraph=True` must be set on the handler** for snakemake
   to compute and emit the rulegraph at all. The default is `False`.

5. **`LogHandlerBase.__init__` does not chain into `logging.Handler.__init__`**,
   so `_name` is never set and `Handler.close()` raises
   `AttributeError`. Plugin calls `logging.Handler.__init__(self)`
   explicitly in its constructor.

## Test infrastructure quirks (worth knowing before adding tests)

1. **Async fixtures must dispose the engine on teardown**, otherwise
   lingering aiosqlite connections block pytest's process exit
   forever (looks like an infinite test). See
   `server/tests/conftest.py` and `server/tests/test_ws.py` for the
   pattern.

2. **Don't use file-level `pytestmark = pytest.mark.asyncio`** in
   files that mix sync (TestClient) and async (httpx AsyncClient)
   tests — pytest-asyncio mis-runs the sync tests. Mark async tests
   individually instead.

3. **`from panoptes_server.db import _sessionmaker` captures `None`**
   at import time and stays `None` even after lifespan initializes
   the engine. Reference `db._sessionmaker` through the module so
   live values are visible.

## Where things live

| Concern | File |
|---|---|
| Models / schema | `server/src/panoptes_server/models.py` |
| Ingest event dispatch | `server/src/panoptes_server/services/ingest.py` |
| Pub/sub bus | `server/src/panoptes_server/services/pubsub.py` |
| Log tail + sandbox | `server/src/panoptes_server/services/log_tail.py` |
| WS endpoint | `server/src/panoptes_server/routes/ws.py` |
| Plugin entry / event mapping | `plugin/src/snakemake_logger_plugin_panoptes/__init__.py` |
| UI route table | `ui/src/App.tsx` |
| TanStack Query hooks | `ui/src/api/hooks.ts` |
| WS subscriber hook | `ui/src/api/useWorkflowEvents.ts` |
| DAG component | `ui/src/components/DagView.tsx` |
| Workflow detail page | `ui/src/pages/WorkflowDetailPage.tsx` |

