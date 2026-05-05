from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from panoptes_server import __version__, db
from panoptes_server.routes import jobs, service, workflows
from panoptes_server.routes.ingest import router as ingest_router
from panoptes_server.routes.ws import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_engine()
    await db.create_all()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="panoptes",
        version=__version__,
        description="Snakemake monitor — ingest + REST API",
        lifespan=lifespan,
    )
    app.include_router(service.router, prefix="/api/v1", tags=["service"])
    app.include_router(workflows.router, prefix="/api/v1/workflows", tags=["workflows"])
    app.include_router(jobs.router, prefix="/api/v1/workflows", tags=["jobs"])
    app.include_router(ingest_router, prefix="/api/v1", tags=["ingest"])
    app.include_router(ws_router, prefix="/api/v1", tags=["ws"])
    _mount_ui(app)
    return app


def _mount_ui(app: FastAPI) -> None:
    """Serve the built UI bundle if present. Skipped during tests where
    the static dir hasn't been generated."""
    static_dir = Path(__file__).parent / "static"
    if not static_dir.exists():
        return
    index_html = static_dir / "index.html"
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="ui-assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa_fallback(path: str) -> FileResponse:
        # any non-API GET falls through to the SPA's index.html so
        # client-side routing works on refresh.
        candidate = static_dir / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_html)


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("panoptes_server.main:app", host="0.0.0.0", port=5000, reload=False)


if __name__ == "__main__":
    run()
