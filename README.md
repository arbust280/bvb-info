# BVB Scraper — Production ETL Pipeline

Reliable ingestion pipeline for **Bucharest Stock Exchange (BVB)** data. It
reverse-engineers BVB's own public endpoints, normalizes the data into a
canonical schema, and loads it into PostgreSQL (with a zero-setup SQLite
fallback). Designed as the ingestion layer for a Romanian equivalent of
Fiscal.ai.

> Evolved from a single-file proof of concept into a modular, tested,
> scheduler-ready package. Every original endpoint is preserved.

## Features

- **Symbol discovery** via the autocomplete JSON endpoint (A–Z0–9 brute force).
- **Live price snapshots** — all stocks + the ETF tab (ASP.NET postback).
- **Company details** — identity, valuation metrics, shareholders, news —
  parsed with BeautifulSoup (no regex), anchored on stable element IDs.
- **Index constituents** (BET and others).
- **Filings** — real `CurrentReports` discovery + content-hashed download.
- **Normalized PostgreSQL schema** (SQLAlchemy 2.0 + Alembic); SQLite fallback.
- **Robust HTTP** — thread-local sessions, urllib3 retries with `Retry-After`
  and exponential backoff.
- **Incremental** — `crawl_metadata` (etag / last-modified / content-hash).
- **Typed models** (Pydantic v2) end to end; JSON export for debugging.
- **Tested** — Romanian number parser, HTML/shareholder parser, normalization.

## Installation

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Requires Python 3.11+.

## Quick start (zero setup)

Runs against a local SQLite database — no server required:

```bash
python -m bvb_scraper.main init-db          # create tables
python -m bvb_scraper.main discover          # sanity-check connectivity
python -m bvb_scraper.main update-all --export storage/bvb_dataset.json
```

## Database setup

Default is SQLite (`sqlite:///bvb.sqlite3`). For PostgreSQL, set:

```bash
export BVB_DATABASE_URL=postgresql+psycopg2://bvb:bvb@localhost:5432/bvb
alembic upgrade head          # apply migrations
python -m bvb_scraper.main update-all
```

### With Docker

```bash
docker compose up --build     # starts Postgres, migrates, runs a full update
```

## Running the crawler

| Command | Description |
|---|---|
| `python -m bvb_scraper.main update-all` | Full ETL: discover → prices → indices → per-symbol details |
| `python -m bvb_scraper.main update-all --with-filings` | Also download filings per company |
| `python -m bvb_scraper.main update-all --no-details` | Prices + indices only (fast) |
| `python -m bvb_scraper.main prices` | Persist today's price snapshots |
| `python -m bvb_scraper.main company TLV` | Fetch + persist one company |
| `python -m bvb_scraper.main filings TLV` | Discover + download a company's filings |
| `python -m bvb_scraper.main discover` | List discoverable symbols |
| `python -m bvb_scraper.main init-db` | Create tables (SQLite/Postgres) |

`--export PATH` writes a JSON snapshot alongside the DB load.

## Updating data

Re-run `update-all` on a schedule. `daily_prices` accumulates one row per
`(symbol, date)`, building price history over time. `crawl_metadata` records
etag/last-modified/content-hash so unchanged resources can be skipped. The
pipeline functions in `bvb_scraper/etl/pipeline.py` are plain callables, so a
cron entry, Celery task, or RQ job needs no code changes:

```bash
# crontab: full refresh every weekday at 19:00
0 19 * * 1-5  cd /path/to/bvb && .venv/bin/python -m bvb_scraper.main update-all
```

## Folder structure

```
bvb_scraper/
  config.py          # all configuration (env: BVB_*)
  logging_config.py  # timestamped logging
  session.py         # thread-local requests sessions
  retry.py           # urllib3 Retry adapter + tenacity
  models.py          # Pydantic domain models
  parsers/           # numbers, html (BeautifulSoup), pdf/xlsx (Phase 2)
  crawler/           # discover, prices, companies, indices, filings
  etl/               # normalize (RO->canonical), pipeline (facade/API)
  db/                # base (engine), schema (ORM), repository (upserts)
  export.py          # JSON export
  main.py            # CLI
alembic/             # migrations
tests/               # pytest unit tests + HTML fixtures
storage/             # downloaded filings + JSON exports
docs/superpowers/    # design spec + implementation plan
```

## Architecture

`crawler/*` fetch raw HTML/JSON from BVB via thread-local retrying sessions →
`parsers/*` turn responses into typed Pydantic models → `etl/normalize.py`
maps Romanian labels to canonical field names → `db/repository.py` upserts into
the normalized schema → `etl/pipeline.py` orchestrates and exposes the API →
`main.py` is a thin CLI. A single failing company is logged and skipped; the
run continues.

## Adding a new endpoint

1. Add its URL to `bvb_scraper/config.py` (`Settings`).
2. Add a fetch function in a `bvb_scraper/crawler/` module returning typed
   models from `models.py` (add a model if needed).
3. If it returns HTML, parse it in `parsers/html.py` with BeautifulSoup
   (anchor on stable IDs; **never** regex). Prefer JSON endpoints when present.
4. Add Romanian→canonical entries to `etl/normalize.py` if new labels appear.
5. Add an ORM table in `db/schema.py` + a `Repository` upsert; generate a
   migration: `alembic revision --autogenerate -m "add X"`.
6. Wire it into `etl/pipeline.py` and expose a CLI subcommand in `main.py`.
7. Add a unit test with a saved HTML fixture.

## Troubleshooting

- **`ModuleNotFoundError`** — activate the venv and `pip install -r requirements.txt`.
- **Empty results / connection errors** — BVB may rate-limit or be down; retries
  and backoff are automatic. Increase `BVB_REQUEST_DELAY` / `BVB_RETRY_TOTAL`.
- **Postgres connection refused** — ensure the server is up and
  `BVB_DATABASE_URL` is correct; with Docker run `docker compose up db`.
- **Alembic "target database is not up to date"** — run `alembic upgrade head`.
- **Layout changed / fields missing** — selectors are ID-anchored; if BVB
  renames IDs, update `parsers/html.py` and the label map in `etl/normalize.py`.
- **Verbose HTTP logs** — set `BVB_LOG_LEVEL=DEBUG` to see every request.

## Phase 2 (planned)

PDF/XLS financial-figure extraction (Revenue, EBIT, EBITDA, Net Income, Assets,
Liabilities, Cash, Debt, Equity, CapEx, ...) into `financial_statements` /
`financial_metrics`. The parser interfaces (`parsers/pdf.py`, `parsers/xlsx.py`)
already open filings and are wired into `download_filings`; they log the
not-yet-implemented mapping step rather than silently doing nothing.
