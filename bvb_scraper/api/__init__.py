"""Public read-only API + frontend for the scraped BVB data.

``create_app()`` builds the FastAPI application; ``api/index.py`` at the repo
root exposes it for Vercel's Python runtime, and ``uvicorn
bvb_scraper.api:app`` serves it locally.
"""

from __future__ import annotations

from bvb_scraper.api.app import app, create_app

__all__ = ["app", "create_app"]
