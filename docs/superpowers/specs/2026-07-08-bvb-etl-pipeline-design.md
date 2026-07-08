# BVB Scraper → Production ETL Pipeline — Design

**Date:** 2026-07-08
**Status:** Approved
**Author:** brainstormed with Claude

## Goal

Transform the proof-of-concept `bvb_full_data.py` (446-line single file) into a
production-quality, modular ETL pipeline that ingests Bucharest Stock Exchange
(BVB) data into PostgreSQL and can later power a Next.js frontend (the Romanian
equivalent of Fiscal.ai). This is the **ingestion layer**, not the frontend.

**Preserve every endpoint that already works. Do not rewrite working
functionality unless necessary.** Improve architecture, reliability,
maintainability, extensibility.

## Endpoints (all preserved)

- `GET  /TradingAndStatistics/Trading/CurrentTradingDay` — trading snapshot
- `POST /TradingAndStatistics/Trading/CurrentTradingDay` — ETF tab (ASP.NET postback)
- `GET  /FinancialInstruments/Details/FinancialInstrumentsDetails.aspx?s=SYM` — company detail
- `GET  /FinancialInstruments/Indices/IndicesProfiles` — index components
- `POST /proxyshld.aspx/GetInstrumentsList` — symbol discovery (autocomplete)

### New endpoints discovered via live inspection (2026-07-08)

- `GET /FinancialInstruments/SelectedData/CurrentReports` — **real filings feed**
- `GET /FinancialInstruments/SelectedData/ReportedShareholders`
- `GET /TradingAndStatistics/Publications/DailyReport`, `/MonthlyReports`
- Dividend PDFs linked from detail pages

### Live-inspection finding that drives the HTML rewrite

The detail page exposes **stable element IDs**:
`gvDetails`, `gvStructuraActionari` (shareholders), `gv5News` (news),
`gvAGA` (general meetings), `gvCF`, and
`ctl00_body_ctl02_StructuraActionariControl_shareHolder`.
BeautifulSoup selectors anchored on these IDs replace all regex parsing and
survive minor layout changes.

## Architecture

Python package `bvb_scraper/` with layered modules:

```
bvb_scraper/
  config.py            # pydantic-settings; ALL config via env/.env
  logging_config.py    # timestamped logging; log every request + every failure
  session.py           # threading.local() -> get_session(); per-session warmup
  retry.py             # urllib3 Retry adapter + tenacity for app-level retries
  models.py            # Pydantic v2 models
  db/
    base.py            # SQLAlchemy 2.0 engine/session; Postgres else SQLite fallback
    schema.py          # ORM table definitions
    repository.py      # idempotent upserts + incremental via crawl_metadata
  crawler/
    discover.py        # POST proxyshld.aspx/GetInstrumentsList (A-Z0-9 brute force)
    prices.py          # GET + POST CurrentTradingDay (snapshot + ETF)
    companies.py       # GET FinancialInstrumentsDetails.aspx
    indices.py         # GET IndicesProfiles
    filings.py         # GET SelectedData/CurrentReports (REAL) + download
  parsers/
    numbers.py         # ro_float / ro_pct (unit-tested)
    html.py            # BeautifulSoup detail-page parser (id-anchored)
    pdf.py             # pdfplumber skeleton — interface real, extraction Phase 2
    xlsx.py            # pandas/openpyxl skeleton — Phase 2
  etl/
    normalize.py       # Romanian -> canonical field mapping
    pipeline.py        # API facade: get_company/update_company/update_all/
                       #             download_prices/download_filings
  export.py            # JSON export (debug; preserves current output)
  main.py              # argparse CLI
alembic/               # migrations
tests/                 # pytest + HTML fixtures
storage/               # downloaded filings
requirements.txt  README.md  docker-compose.yml  Dockerfile  .env.example
pyproject.toml (black + tooling)  alembic.ini
```

### Design principles

- **No god-object main().** `etl/pipeline.py` is a thin facade over pure,
  independently testable functions. Callable unchanged from cron/Celery/RQ.
- **Thread-local sessions** — each worker gets its own `requests.Session`
  (current shared-session-across-threads is unsafe).
- **Dependency injection** where it matters (session, db repository passed in).
- **Type hints + docstrings + black** throughout.
- **JSON over HTML**: prefer discovered JSON endpoints when cleaner.

## Database schema (normalized; SQLAlchemy + Alembic)

| Table | Purpose |
|---|---|
| `companies` | one row per issuer (name, isin, sector, description) |
| `symbols` | ticker -> company; instrument type, market, segment, status |
| `daily_prices` | one row per (symbol, date): price/open/max/min/avg/value/volume/trades — **accumulates history across runs** |
| `indices` | index catalogue (BET, BET-TR, ...) |
| `index_constituents` | index -> symbol, shares, ref price, free float |
| `shareholders` | symbol -> holder, shares, pct, as-of date |
| `financial_metrics` | valuation metrics (market_cap, pe_ratio, pbv, eps, div_yield...) |
| `financial_statements` | line items from PDF/XLS (Phase 2 populated) |
| `filings` | current reports: date, type, title, url, local_path, hash |
| `dividends` | ex-date, pay-date, amount, yield, source url |
| `news` | detail-page news items |
| `crawl_metadata` | per-resource etag/last_modified/content_hash/last_updated for incremental |

## Data flow

`discover` -> `prices` + `etf` -> `indices` -> per-symbol `companies`
(thread pool, thread-local sessions, one failure never aborts the run) ->
`normalize` -> `repository` upsert -> optional JSON `export`.

**Incremental:** `crawl_metadata` short-circuits unchanged resources via
ETag / Last-Modified / content-hash. `daily_prices` is append/upsert per date,
so repeated runs build a price history (the de-facto historical source, since
BVB exposes no bulk historical endpoint).

## Reliability

- urllib3 `Retry`: retry on 429/500/502/503/504, connection resets, timeouts;
  honors `Retry-After`; exponential backoff.
- Every request logged at DEBUG/INFO; every failure logged at WARNING/ERROR.
- Per-company failures are caught, logged, and skipped — the run continues.

## Phasing

- **Phase 1 — fully implemented, runnable now:** everything except PDF/XLS
  *value extraction*. Filings *discovery + download* is real.
- **Phase 2 — real wired skeleton, clearly marked:** PDF/XLS financial-figure
  extraction into `financial_statements` / `financial_metrics`. The interfaces
  exist and are invoked by the pipeline; they log "extraction not yet
  implemented" rather than being empty pass-through stubs.

## Testing

pytest units for: `numbers` (Romanian number/percent parser), `html` detail
parser + `shareholders` (against saved HTML fixtures), `normalize` (Romanian ->
canonical mapping).

## "Just runs" acceptance

- `python main.py update-all` works with **zero external setup** (SQLite
  fallback + JSON export written).
- `docker-compose up` provisions PostgreSQL; `.env` switches the pipeline to it.
- README documents install, DB setup, running, updating, folder structure,
  architecture, adding new endpoints, troubleshooting.

## Non-goals

- The Next.js frontend (future).
- Real PDF/XLS financial-figure extraction (Phase 2 skeleton only).
- Bulk historical backfill beyond what `daily_prices` accumulates over runs
  (no such BVB endpoint exists; architecture leaves a clean placeholder).
