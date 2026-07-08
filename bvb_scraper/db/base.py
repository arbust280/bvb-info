"""Database engine/session bootstrap.

Uses ``settings.database_url``: PostgreSQL when configured, otherwise a local
SQLite file so the pipeline runs with zero external setup.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from bvb_scraper.config import settings
from bvb_scraper.db.schema import Base
from bvb_scraper.logging_config import get_logger

logger = get_logger(__name__)


@lru_cache
def get_engine() -> Engine:
    """Return the process-wide SQLAlchemy engine."""
    url = settings.database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)
    logger.info("Database engine: %s", url.split("://", 1)[0])
    return engine


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    """Return a configured session factory."""
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


def init_db() -> None:
    """Create all tables if they do not exist (idempotent)."""
    Base.metadata.create_all(get_engine())
    logger.info("Database schema ensured (%d tables)", len(Base.metadata.tables))
