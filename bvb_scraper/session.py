"""Thread-local HTTP sessions.

The proof-of-concept shared a single ``requests.Session`` across worker
threads, which is unsafe. Here each thread gets its own session (with the
retrying adapter mounted and cookies warmed once).
"""

from __future__ import annotations

import threading

import requests

from bvb_scraper.config import settings
from bvb_scraper.logging_config import get_logger
from bvb_scraper.retry import build_retry_adapter

logger = get_logger(__name__)

_local = threading.local()


def _build_session() -> requests.Session:
    """Create a new configured session for the current thread."""
    session = requests.Session()
    session.headers.update(settings.headers)
    adapter = build_retry_adapter()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    # Warm up cookies (best-effort; failures are non-fatal).
    try:
        session.get(settings.base_url, timeout=settings.request_timeout)
        logger.debug("Session warmed up against %s", settings.base_url)
    except requests.RequestException as exc:
        logger.warning("Session warmup failed (continuing): %s", exc)
    return session


def get_session() -> requests.Session:
    """Return the current thread's session, creating it on first use."""
    session = getattr(_local, "session", None)
    if session is None:
        session = _build_session()
        _local.session = session
    return session
