"""Shared FastAPI application context and dependencies."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

from ..models import get_session


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = PACKAGE_ROOT / "static"
TEMPLATES_DIR = PACKAGE_ROOT / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


__all__ = [
    "PACKAGE_ROOT",
    "STATIC_DIR",
    "TEMPLATES_DIR",
    "get_db",
    "templates",
]
