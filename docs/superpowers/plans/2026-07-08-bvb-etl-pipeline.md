# BVB ETL Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the single-file `bvb_full_data.py` proof-of-concept into a modular, production-quality BVB ingestion pipeline feeding PostgreSQL (with SQLite fallback), with retries, logging, config, BeautifulSoup parsing, incremental updates, tests, and docs.

**Architecture:** Layered `bvb_scraper/` package. `crawler/*` fetch raw HTML/JSON from the preserved BVB endpoints via thread-local retrying sessions; `parsers/*` turn responses into typed Pydantic models; `etl/normalize.py` maps Romanian labels to a canonical schema; `db/repository.py` upserts models into a normalized SQLAlchemy schema; `etl/pipeline.py` is the callable facade orchestrating everything; `main.py` is the CLI.

**Tech Stack:** Python 3.11+, requests + urllib3 Retry + tenacity, BeautifulSoup4/lxml, pandas (read_html), Pydantic v2 + pydantic-settings, SQLAlchemy 2.0 + Alembic, PostgreSQL/SQLite, pdfplumber/openpyxl (Phase 2 skeleton), pytest, black.

## Global Constraints

- **Preserve every working endpoint** — GET/POST `CurrentTradingDay`, GET `FinancialInstrumentsDetails.aspx`, GET `IndicesProfiles`, POST `proxyshld.aspx/GetInstrumentsList`. Verbatim URLs live in `config.py`.
- **No regex for HTML** — use BeautifulSoup anchored on stable IDs (`gvDetails`, `gvStructuraActionari`, `gv5News`, `gvAGA`, `gvCF`). ASP.NET hidden-field extraction uses BeautifulSoup too.
- **Thread-local sessions** — never share a `requests.Session` across threads.
- **Prefer JSON over HTML** where a JSON endpoint exists (discovery already is JSON).
- **Never crash on one company** — catch, log, continue.
- **Config via env** — all tunables in `config.py` (pydantic-settings), overridable by `.env`.
- **`python -m bvb_scraper.main update-all` runs with zero setup** (SQLite fallback + JSON export).
- **Type hints + docstrings + black** everywhere.
- **Python floor:** 3.11. **SQLAlchemy:** 2.0 style. **Pydantic:** v2.

## File Structure

| File | Responsibility |
|---|---|
| `bvb_scraper/__init__.py` | package marker, version |
| `bvb_scraper/config.py` | `Settings` (pydantic-settings): URLs, headers, UA, timeouts, workers, delay, retry count, DB URL |
| `bvb_scraper/logging_config.py` | `setup_logging(level)` — timestamped formatter |
| `bvb_scraper/session.py` | `get_session()` thread-local; `_build_session()` with retry adapter + warmup |
| `bvb_scraper/retry.py` | `build_retry_adapter()` (urllib3 Retry) + `retryable` tenacity decorator |
| `bvb_scraper/models.py` | Pydantic v2 models |
| `bvb_scraper/parsers/numbers.py` | `ro_float`, `ro_pct` |
| `bvb_scraper/parsers/html.py` | `parse_detail_page(html, symbol) -> Company`; table helpers |
| `bvb_scraper/parsers/pdf.py` | `extract_financials(path)` — Phase 2 skeleton |
| `bvb_scraper/parsers/xlsx.py` | `extract_financials(path)` — Phase 2 skeleton |
| `bvb_scraper/crawler/discover.py` | `discover_all_symbols(session)` |
| `bvb_scraper/crawler/prices.py` | `fetch_trading_snapshot`, `fetch_etf_snapshot` |
| `bvb_scraper/crawler/companies.py` | `fetch_symbol_detail(session, symbol)` |
| `bvb_scraper/crawler/indices.py` | `fetch_index_components(session)` |
| `bvb_scraper/crawler/filings.py` | `fetch_current_reports`, `download_filing` |
| `bvb_scraper/etl/normalize.py` | `RO_TO_CANONICAL` + `normalize_metrics` |
| `bvb_scraper/db/base.py` | engine/session factory; `init_db()`; Postgres-or-SQLite |
| `bvb_scraper/db/schema.py` | SQLAlchemy ORM tables |
| `bvb_scraper/db/repository.py` | `Repository` upserts + `crawl_metadata` incremental |
| `bvb_scraper/etl/pipeline.py` | `get_company`, `update_company`, `update_all`, `download_prices`, `download_filings` |
| `bvb_scraper/export.py` | `export_json(data, path)` |
| `bvb_scraper/main.py` | argparse CLI |
| `tests/test_numbers.py` | Romanian parser tests |
| `tests/test_html_parser.py` | detail-page + shareholder parse tests (fixtures) |
| `tests/test_normalize.py` | canonical mapping tests |
| `tests/fixtures/detail_sample.html` | trimmed real detail-page HTML |
| infra | `requirements.txt`, `pyproject.toml`, `.env.example`, `alembic.ini`, `alembic/`, `docker-compose.yml`, `Dockerfile`, `README.md` |

---

### Task 1: Packaging skeleton + config + logging

**Files:** Create `bvb_scraper/__init__.py`, `config.py`, `logging_config.py`, `requirements.txt`, `pyproject.toml`, `.env.example`.

**Interfaces produced:**
- `config.settings: Settings` with: `base_url`, `discovery_url`, `trading_url`, `detail_url_tmpl`, `indices_url`, `current_reports_url`, `user_agent`, `headers`, `request_timeout`, `max_workers`, `request_delay`, `retry_total`, `retry_backoff`, `database_url` (default `sqlite:///bvb.sqlite3`), `storage_dir`, `log_level`.
- `logging_config.setup_logging(level: str) -> None`.

- [ ] Write `requirements.txt` (requests, urllib3, tenacity, beautifulsoup4, lxml, pandas, pydantic>=2, pydantic-settings, SQLAlchemy>=2, alembic, psycopg2-binary, pdfplumber, openpyxl, pytest, black).
- [ ] Write `config.py` with `Settings(BaseSettings)`, `env_prefix="BVB_"`, `.env` support; instantiate `settings`.
- [ ] Write `logging_config.py`, `pyproject.toml` (black line-length 100, pytest config), `.env.example`.
- [ ] Verify: `python -c "from bvb_scraper.config import settings; print(settings.database_url)"`.
- [ ] Commit.

### Task 2: Romanian number parser + tests (TDD)

**Files:** Create `parsers/__init__.py`, `parsers/numbers.py`, `tests/test_numbers.py`.
**Produces:** `ro_float(s) -> float | None`, `ro_pct(s) -> float | None`.

- [ ] Failing tests: `ro_float("1.090.322,25")==1090322.25`, `ro_float("0,20")==0.2`, `ro_float("43.416.630.999,50")==43416630999.5`, `ro_float("1234")==1234.0`, `ro_float("-") is None`, `ro_float(None) is None`, `ro_float("12 lei")==12.0`; `ro_pct("+0,52%")==0.52`, `ro_pct("-") is None`.
- [ ] Run — expect fail. Port from `bvb_full_data.py:39-63` with hints/docstrings. Run — pass. Commit.

### Task 3: Pydantic models

**Files:** Create `models.py`. **Produces:** `Symbol, PriceSnapshot, Shareholder, FinancialMetrics, Company, IndexComponent, Filing, Dividend, News` (field lists per spec; numeric fields `float|None`; `Company` has `shareholders:list[Shareholder]`, `news:list[News]`, `error:str|None`; `PriceSnapshot` has `date`, `source`).

- [ ] Write models with `ConfigDict(extra="ignore")`. Verify `Company(symbol='TLV')`. Commit.

### Task 4: Retry adapter + thread-local sessions

**Files:** Create `retry.py`, `session.py`.
**Produces:** `retry.build_retry_adapter() -> HTTPAdapter` (urllib3 `Retry(total, backoff_factor, status_forcelist=[429,500,502,503,504], allowed_methods={"GET","POST"}, respect_retry_after_header=True)`); `session.get_session() -> requests.Session` (thread-local, mounts adapter, headers, one-time cookie warmup, logs).

- [ ] Implement both (`threading.local()`; warmup in try/except+log). Verify import. Commit.

### Task 5: BeautifulSoup detail-page parser + tests (TDD)

**Files:** Create `parsers/html.py`, `tests/test_html_parser.py`, `tests/fixtures/detail_sample.html`.
**Consumes:** `ro_float`, `ro_pct`, `Company`, `Shareholder`, `News`, `RO_TO_CANONICAL`.
**Produces:** `parse_detail_page(html:str, symbol:str) -> Company`; `_labeled_value(soup, label)`; `_parse_shareholders(soup) -> list[Shareholder]`.

- [ ] Save trimmed fixture (gvDetails, gvStructuraActionari, valuation rows, gv5News).
- [ ] Failing tests: ISIN/market_cap/pe_ratio/eps parsed; `len(shareholders)>=1` with float `pct`; symbol set; empty html → `Company` w/o exception.
- [ ] Run — fail. Implement (BS4, id-anchored, label→canonical). Run — pass. Commit.

### Task 6: Normalize + tests (TDD)

**Files:** Create `etl/__init__.py`, `etl/normalize.py`, `tests/test_normalize.py`.
**Produces:** `RO_TO_CANONICAL` (`Capitalizare→market_cap`, `PER→pe_ratio`, `P/BV→pbv`, `EPS→eps`, `DIVY→div_yield`, `Pret→price`, `Pret referinta→reference_price`, `Numar total actiuni→total_shares`, `Valoare Nominala→nominal_value`, `Capital social→share_capital`, ...); `normalize_label(ro)->str|None`; `normalize_metrics(raw, symbol)->FinancialMetrics`.

- [ ] Failing tests: `normalize_label("Capitalizare")=="market_cap"`; `normalize_metrics({"Capitalizare":"1.000,00","PER":"12,5"},"TLV")` → `market_cap==1000.0`, `pe_ratio==12.5`. Implement. Pass. Commit.

### Task 7: Crawler — discover, prices, indices

**Files:** Create `crawler/__init__.py`, `crawler/discover.py`, `crawler/prices.py`, `crawler/indices.py`.
**Produces:** `discover_all_symbols(session=None)->list[Symbol]`; `fetch_trading_snapshot(session=None)->list[PriceSnapshot]` (source="trading"); `fetch_etf_snapshot(session=None)->list[PriceSnapshot]` (source="etf"; ASP.NET fields via BS4 `find(id=name)["value"]`); `fetch_index_components(session=None, index="BET")->list[IndexComponent]`.

- [ ] Port from `bvb_full_data.py:68-205,336-361`, regex→BS4, return models, try/except+log→`[]`. Verify import. Commit.

### Task 8: Crawler — companies + filings

**Files:** Create `crawler/companies.py`, `crawler/filings.py`.
**Produces:** `fetch_symbol_detail(session, symbol)->Company` (non-200/exc → `Company(symbol, error=...)`); `fetch_current_reports(session, symbol)->list[Filing]`; `download_filing(session, filing, storage_dir)->Filing` (stream, sha256, skip if unchanged).

- [ ] Implement; never raise to caller. Commit.

### Task 9: Database — base, schema, repository

**Files:** Create `db/__init__.py`, `db/base.py`, `db/schema.py`, `db/repository.py`, `alembic.ini`, `alembic/env.py`, `alembic/versions/<initial>.py`.
**Produces:** `base.get_engine()/get_sessionmaker()/init_db()`; ORM `Company, Symbol, DailyPrice, Index, IndexConstituent, Shareholder, FinancialMetric, FinancialStatement, Filing, Dividend, News, CrawlMetadata` (daily_prices unique `(symbol,date)`); `Repository(session)` with `upsert_symbols/upsert_prices/upsert_company/upsert_index_components/upsert_filings`, `should_refresh(key, etag, last_modified, content_hash)->bool`, `record_crawl(...)`. Dialect-agnostic upserts (select-then-insert/update).

- [ ] Implement; Alembic initial migration reading `settings.database_url`. Verify `init_db()` creates `bvb.sqlite3`. Commit.

### Task 10: Pipeline facade + JSON export

**Files:** Create `etl/pipeline.py`, `export.py`.
**Produces:** `download_prices(session=None, repo=None)`; `get_company(symbol, session=None)`; `update_company(symbol, session=None, repo=None)`; `download_filings(symbol, session=None, repo=None)`; `update_all(max_workers=None, export_path=None, with_details=True, with_filings=False)->dict` (discover→prices→etf→indices→threaded details w/ thread-local sessions, per-item try/except, upserts, optional export). `export.export_json(payload, path)`.

- [ ] Implement (workers call `get_session()` internally). Verify import. Commit.

### Task 11: PDF/XLS Phase-2 skeletons

**Files:** Create `parsers/pdf.py`, `parsers/xlsx.py`.
**Produces:** `pdf.extract_financials(path)->list[dict]` (opens with pdfplumber, returns detected table rows, logs `"financial-figure extraction not yet implemented (Phase 2)"`); `xlsx.extract_financials(path)->list[dict]` (pandas/openpyxl sheet preview + same notice). Wired into `download_filings` (called, logged, not yet persisted to `financial_statements`).

- [ ] Implement genuine-open skeletons (not empty `pass`). Commit.

### Task 12: CLI

**Files:** Create `main.py`.
**Produces:** argparse subcommands `update-all` (`--workers`, `--export`, `--with-filings`, `--no-details`), `prices`, `company SYMBOL`, `filings SYMBOL`, `init-db`, `discover`; calls `setup_logging(settings.log_level)` then dispatches to `pipeline`.

- [ ] Implement. `--help` lists subcommands. `init-db` succeeds (SQLite). Commit.

### Task 13: Infra + docs

**Files:** Create `Dockerfile`, `docker-compose.yml`, `README.md`.

- [ ] `docker-compose.yml`: `postgres:16` + app, env → `BVB_DATABASE_URL`. `Dockerfile`: python:3.11-slim + requirements, entrypoint `python -m bvb_scraper.main`. `README.md`: install / DB setup / running / updating / folder structure / architecture / adding endpoints / troubleshooting. Commit.

### Task 14: Full-suite verification

- [ ] `black --check bvb_scraper tests` (format if needed). `pytest -q` green. `python -m bvb_scraper.main init-db` ok. Final commit.

## Self-Review

**Spec coverage:** endpoints preserved (Tasks 1,7,8) ✓; regex→BS4 (5,7) ✓; thread-local sessions (4,10) ✓; retry+Retry-After (4) ✓; logging (1, all) ✓; config (1) ✓; normalized Postgres schema (9) ✓; models (3) ✓; filings real + PDF/XLS skeleton (8,11) ✓; historical via daily_prices (9) ✓; incremental crawl_metadata (9) ✓; scheduler-ready facade + API layer (10) ✓; normalization (6) ✓; tests (2,5,6) ✓; requirements (1) ✓; README (13) ✓; JSON export retained (10) ✓; Docker (13) ✓; JSON-over-HTML (discovery JSON; documented) ✓.

**Placeholder scan:** Phase-2 skeletons (11) are real-but-limited by design, not plan placeholders. No TBDs.

**Type consistency:** model field names identical across Tasks 3/5/6/9/10; `get_session()` signature consistent across 4/7/8/10; `Repository` method names consistent 9/10.
