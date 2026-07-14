"""Read-only engine/session for the public API.

Separate from ``db.base`` on purpose: the API uses the read-only credentials
(``BVB_API_DATABASE_URL``) and ``NullPool`` — on serverless every invocation
may be a fresh process, so client-side pooling only leaks connections; Neon's
pgbouncer endpoint does the pooling server-side.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from bvb_scraper.config import settings


@lru_cache
def get_read_engine() -> Engine:
    """Return the API's read-only engine (falls back to the main DB URL)."""
    url = settings.api_database_url or settings.database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, future=True, poolclass=NullPool, connect_args=connect_args)


@lru_cache
def get_read_sessionmaker() -> sessionmaker[Session]:
    """Return the session factory bound to the read-only engine."""
    return sessionmaker(bind=get_read_engine(), expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a read-only session."""
    session = get_read_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
