"""FastAPI application factory for AgentBench."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..models import init_db
from .context import STATIC_DIR
from .routers.experiments import router as experiments_router
from .routers.pages import router as pages_router
from .routers.resources import router as resources_router
from .routers.runs import router as runs_router
from .routers.system import router as system_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="AgentBench Local",
        description=(
            "Local-first coding-agent evaluation with deterministic corpora, "
            "reproducible execution, and uncertainty-aware comparison."
        ),
        version=__version__,
        lifespan=lifespan,
    )
    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    for router in (
        system_router,
        pages_router,
        resources_router,
        runs_router,
        experiments_router,
    ):
        app.include_router(router)
    return app


__all__ = ["create_app", "lifespan"]
