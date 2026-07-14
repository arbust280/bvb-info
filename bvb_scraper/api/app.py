"""FastAPI application factory for the public API + frontend."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from bvb_scraper.api import v1, web
from bvb_scraper.config import settings

_DESCRIPTION = """
Free, no-auth, read-only API over daily-scraped Bucharest Stock Exchange
(BVB) data: companies, price snapshots, valuation metrics, shareholders,
index constituents and company news.

Data is refreshed once per trading day after market close. Responses are
edge-cached — please just consume them; no key or registration needed.
"""


def create_app() -> FastAPI:
    """Build the application (separate factory so tests can make their own)."""
    application = FastAPI(
        title="BVB Info API",
        description=_DESCRIPTION,
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    application.include_router(v1.router, prefix="/api/v1", tags=["v1"])
    application.include_router(web.router, include_in_schema=False)
    application.mount(
        "/static",
        StaticFiles(directory=str(Path(__file__).parent / "static")),
        name="static",
    )

    @application.middleware("http")
    async def cache_control(request: Request, call_next) -> Response:
        """Let the CDN absorb repeat traffic: data changes at most daily."""
        response = await call_next(request)
        if request.method == "GET" and response.status_code == 200:
            response.headers.setdefault(
                "Cache-Control",
                f"public, s-maxage={settings.api_cache_seconds}, "
                "stale-while-revalidate=86400",
            )
        return response

    return application


app = create_app()
