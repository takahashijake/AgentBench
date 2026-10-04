"""Database session management."""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from .database import Base

# Default database URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agentbench.db")

# Engine and session factory
engine = create_engine(
    DATABASE_URL,
    connect_args=(
        {"check_same_thread": False, "timeout": 30} if "sqlite" in DATABASE_URL else {}
    ),
)
session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Session = scoped_session(session_factory)


def init_db():
    """Initialize the database and create tables."""
    Base.metadata.create_all(bind=engine)


def get_session():
    """Get a database session."""
    return Session()


def close_session():
    """Close the current session."""
    Session.remove()


def reset_db():
    """Drop all tables and recreate them."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
