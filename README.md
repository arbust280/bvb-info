# BVB-INFO : Free API solution for BVB data | API Gratis pentru BVB 🇷🇴

**Free Bucharest Stock Exchange data: scraper, database, API, and a terminal website. No key, no signup, fully open-source and free to use.** 
Toate scraperele/APIurile pentru BVB erau platite, print Tiriac, Tradeville etc. Acesta este un scraper gratis de date JSON. Fara signup sau alte 
kkturi. Ceri API, primesti, folosesti date instant in proiectul tau.

**Terminal:** [bvb-api.vercel.app](https://bvb-api.vercel.app) ·
**API docs/Documentatie FastAPI:** [bvb-api.vercel.app/api/docs](https://bvb-api.vercel.app/api/docs)

---

EN: The Bucharest Stock Exchange publishes plenty of data, but not in a way you
can `curl`. This project fixes that. Every weekday after market close, a
scraper walks BVB's own public endpoints, tidies the Romanian-formatted
numbers into a proper schema, and loads everything into Postgres. A small
FastAPI app then serves it two ways: as a browsable website and as a free
JSON API.

RO: BVB-ul tine o tona de date despre companiile locale. Totusi, toate solutiile API
pentru a extrage datele acestea sunt platite, cauzand un impas pentru persoanele
care doresc sa faca aplicatii/websiteuri fara sa plateasca folosind aceste date. 
Acest scraper FastAPI este rapid, nelimitat, si up-to-date (cron job cand se inchide
marketul la ora 19).

EN: If you've ever wanted to build something on Romanian market data; a
screener, a dashboard, a spreadsheet that updates itself; this is the
missing ingredient.

RO: Daca ati vrut vreodata sa faceti orice cu datele BVB **FARA** sa platiti pentru ele
si fara sa stati sa consumati tokenuri pe claude code sau pe codex degeaba, mai bine folositi
acest screener/dashboard/spreedsheet cu auto update PRIN API!!! 


## What's in the data

- **~400 instruments** — every listed company, fund, and ETF, with profile,
  ISIN, segment, and share structure
- **Daily prices** — OHLC, volume, traded value; one row per instrument per
  session, accumulating history over time
- **Valuation metrics** — market cap, P/E, P/BV, EPS, dividend yield
- **Shareholders** — who owns what, in percentages and share counts
- **Index constituents** — BET and friends
- **Company news** — the announcement feed, per symbol

## The API

Everything is under `/api/v1`, everything is `GET`, and everything returns
JSON. Responses are cached at the edge, so go ahead and hit it from your
cron job — you'll mostly be talking to a CDN, not our database.

```bash
# What's in the dataset right now?
curl https://bvb-api.vercel.app/api/v1/

# Banca Transilvania: profile, metrics, shareholders, news, latest price
curl https://bvb-api.vercel.app/api/v1/companies/TLV

# Every company with "energ" in the name
curl "https://bvb-api.vercel.app/api/v1/companies?search=energ"

# Price history for a symbol
curl "https://bvb-api.vercel.app/api/v1/prices?symbol=SNP&date_from=2026-07-01"

# Who's in the BET index?
curl https://bvb-api.vercel.app/api/v1/indices/BET
```

| Endpoint | What you get |
|---|---|
| `/api/v1/` | Dataset status — counts, freshness, available indices |
| `/api/v1/companies` | Search & filter companies (`search`, `segment`, `category`, `limit`, `offset`) |
| `/api/v1/companies/{symbol}` | The works: profile + metrics + shareholders + news + latest price |
| `/api/v1/prices` | Daily prices (`symbol`, `date_from`, `date_to`, paginated) |
| `/api/v1/indices` · `/{name}` | Index list and constituents |
| `/api/v1/news` | Announcements (`symbol`, paginated) |

Interactive docs with a try-it button live at
[`/api/docs`](https://bvb-api.vercel.app/api/docs).

## Run it yourself

Python 3.11+. The scraper works out of the box against a local SQLite file —
no server, no config:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m bvb_scraper.main init-db      # create tables
python -m bvb_scraper.main update-all   # scrape everything (~15 min)

uvicorn bvb_scraper.api:app --reload    # website + API on :8000
```

That's it — open http://localhost:8000 and you have your own private copy.

Want Postgres instead? Point `BVB_DATABASE_URL` at it and run
`alembic upgrade head` first. There's also a `docker compose up --build`
that does Postgres + migrate + scrape in one go.

### Scraper commands

| Command | Does |
|---|---|
| `update-all` | Full run: discover → prices → indices → per-company details |
| `update-all --with-filings` | …plus download filings per company |
| `update-all --no-details` | Prices + indices only (fast) |
| `prices` | Just today's price snapshot |
| `company TLV` | One company, fetched and persisted |
| `filings TLV` | Discover + download one company's filings |
| `discover` | List every discoverable symbol |

All tunables (request pacing, retries, workers, log level) are `BVB_*` env
vars — see `.env.example`.

## How it stays fresh

A GitHub Actions workflow ([`scrape.yml`](.github/workflows/scrape.yml))
runs the full update every weekday at ~19:20 Bucharest time, after the 18:00
close. The site shows a "DATA AS OF" stamp so you always know what session
you're looking at.

## How it's put together

```
crawler/   fetches raw HTML/JSON from bvb.ro (thread-local sessions, retries)
parsers/   turns responses into typed Pydantic models (BeautifulSoup, no regex)
etl/       maps Romanian labels to canonical fields, orchestrates the run
db/        SQLAlchemy 2.0 schema + dialect-agnostic upserts (Postgres/SQLite)
api/       FastAPI: /api/v1 JSON + the Jinja2-rendered frontend
main.py    thin CLI over the pipeline functions
```

Design choices worth knowing: selectors anchor on stable element IDs (never
regex over HTML), one failing company never aborts a run, and the public API
reads through a separate read-only database role. The frontend is
server-rendered with zero build step — one CSS file, a splash of vanilla JS.

Adding an endpoint is a well-worn path: URL in `config.py` → fetch function
in `crawler/` → parse in `parsers/html.py` → label map in `etl/normalize.py`
→ table + upsert in `db/` → wire into `etl/pipeline.py` → test with a saved
HTML fixture. The README of your dreams it is not, but `git log` shows it
works.

## When something breaks

- **Empty results / connection errors** — BVB rate-limits sometimes; retries
  are automatic. Bump `BVB_REQUEST_DELAY` if it persists.
- **"target database is not up to date"** — `alembic upgrade head`.
- **Fields suddenly missing** — BVB renamed an element ID; update
  `parsers/html.py` and `etl/normalize.py`.
- **Chatty logs wanted** — `BVB_LOG_LEVEL=DEBUG` shows every request.

## DISCLAIMER

BVB as well as the scraper can lag, gap, or be wrong. Treat it as a convenient market feed, not 
an exact exact exact replica. Nothing here is investment advice obviously. Don't abuse my
rate limits pls (pls!) 🙏🙏🙏🙏

---

*For rate limits or broken data problems, please reach out to me at aethrex@proton.me* :)))
*Daca aveti probleme cu coruptie de date sau orice altceva, va rog sa imi scrieti la aethrex@proton.me* :)))


from arbust 🇷🇴 with love
