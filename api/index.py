"""Vercel serverless entrypoint — exposes the FastAPI ASGI app."""

from bvb_scraper.api import app

__all__ = ["app"]
