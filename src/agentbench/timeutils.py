"""Time helpers with an intentionally naive UTC database convention."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return current UTC as a naive datetime for existing database columns."""
    return datetime.now(UTC).replace(tzinfo=None)
