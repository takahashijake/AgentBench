"""AgentBench FastAPI composition surface."""

from .app import create_app
from .context import (
    PACKAGE_ROOT,
    STATIC_DIR,
    TEMPLATES_DIR,
    get_db,
    templates,
)


app = create_app()


__all__ = [
    "PACKAGE_ROOT",
    "STATIC_DIR",
    "TEMPLATES_DIR",
    "app",
    "create_app",
    "get_db",
    "templates",
]
