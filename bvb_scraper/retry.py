"""Retry configuration.

Provides a urllib3-backed HTTP adapter (transport-level retries with
exponential backoff and ``Retry-After`` support) plus a tenacity decorator
for application-level retries around higher-level operations.
"""

from __future__ import annotations

from typing import Callable, TypeVar

from requests.adapters import HTTPAdapter
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from urllib3.util.retry import Retry

from bvb_scraper.config import settings

RETRYABLE_STATUS = (429, 500, 502, 503, 504)

T = TypeVar("T")


def build_retry_adapter() -> HTTPAdapter:
    """Build an :class:`HTTPAdapter` with transport-level retries.

    Retries on 429/5xx, connection resets and timeouts, honours the
    ``Retry-After`` header, and backs off exponentially.
    """
    retry_cfg = Retry(
        total=settings.retry_total,
        connect=settings.retry_total,
        read=settings.retry_total,
        backoff_factor=settings.retry_backoff,
        status_forcelist=RETRYABLE_STATUS,
        allowed_methods=frozenset(["GET", "POST"]),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    return HTTPAdapter(max_retries=retry_cfg, pool_connections=20, pool_maxsize=20)


def retryable(func: Callable[..., T]) -> Callable[..., T]:
    """Decorate an operation with application-level exponential-backoff retry.

    Complements transport retries for logical failures (e.g. transient
    parsing on partial responses).
    """
    wrapped = retry(
        reraise=True,
        stop=stop_after_attempt(settings.retry_total),
        wait=wait_exponential(multiplier=settings.retry_backoff, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    )(func)
    return wrapped
