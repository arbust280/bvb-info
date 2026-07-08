#!/usr/bin/env python3
"""
bvb_full_data.py — Scrape ALL BVB companies with full details.
No official API; reverse-engineers BVB's own public endpoints.

Endpoints used:
  GET  https://www.bvb.ro/TradingAndStatistics/Trading/CurrentTradingDay
  GET  https://www.bvb.ro/FinancialInstruments/Details/FinancialInstrumentsDetails.aspx?s=SYMBOL
  GET  https://www.bvb.ro/FinancialInstruments/Indices/IndicesProfiles
  POST https://www.bvb.ro/proxyshld.aspx/GetInstrumentsList   (autocomplete, for symbol discovery)
  POST https://www.bvb.ro/TradingAndStatistics/Trading/CurrentTradingDay  (ETF tab via ASP.NET postback)
"""

import requests, re, json, time, os
from io import StringIO
from datetime import datetime, date
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

# ──────────────────────────────────────────────
# HTTP session — mimic a real browser
# ──────────────────────────────────────────────
def make_session():
    s = requests.Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://www.bvb.ro/',
    })
    # Warm up cookies
    s.get("https://www.bvb.ro", timeout=15)
    return s

# ──────────────────────────────────────────────
# Romanian number parser
# ──────────────────────────────────────────────
def ro_float(s):
    """Convert '1.090.322,25' or '0,20' or '43.416.630.999,50' → float."""
    if s is None:
        return None
    s = str(s).strip()
    if not s or s in ('-', '—'):
        return None
    # currency sign
    s = s.replace(' lei', '').replace(' RON', '').strip()
    # remove dots (thousands), swap comma→dot (decimal)
    if '.' in s and ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None

def ro_pct(s):
    """'0,20' or '+0,52%' → float (value in percent). Returns None if unparseable."""
    if s is None:
        return None
    s = str(s).replace('%', '').replace('+', '').replace('▲', '').strip()
    return ro_float(s)

# ──────────────────────────────────────────────
# 1. Discover all ticker symbols
# ──────────────────────────────────────────────
def discover_all_symbols(session, delay=0.3):
    """
    The autocomplete endpoint (proxyshld.aspx/GetInstrumentsList)
    returns max 10 results per searchtext. We brute-force every A-Z
    prefix to enumerate the full list, then deduplicate.
    """
    url = "https://www.bvb.ro/proxyshld.aspx/GetInstrumentsList"
    seen = {}

    for prefix in [chr(c) for c in range(ord('A'), ord('Z')+1)] + \
                 [chr(c) for c in range(ord('0'), ord('9')+1)]:
        payload = json.dumps({"searchtext": prefix})
        r = session.post(url, data=payload, timeout=15)
        if r.status_code != 200:
            continue
        try:
            items = r.json().get('d', [])
        except Exception:
            items = []
        for item in items:
            sym = item.get('Symbol', '').strip()
            if sym and sym not in seen:
                seen[sym] = {
                    'symbol': sym,
                    'isin': item.get('Isin', ''),
                    'name': item.get('Name', ''),
                    'status': item.get('Status', ''),  # T=tradable, D=delisted
                }
        time.sleep(delay)

    symbols = sorted(seen.values(), key=lambda x: x['symbol'])
    print(f"[discover] Found {len(symbols)} symbols via autocomplete endpoint")
    return symbols

# ──────────────────────────────────────────────
# 2. Today's trading snapshot (all symbols)
# ──────────────────────────────────────────────
def fetch_trading_snapshot(session):
    """Returns list[dict] — one row per symbol on CurrentTradingDay table."""
    r = session.get(
        "https://www.bvb.ro/TradingAndStatistics/Trading/CurrentTradingDay",
        timeout=20
    )
    r.raise_for_status()

    try:
        tables = pd.read_html(StringIO(r.text), flavor='lxml')
    except Exception:
        tables = pd.read_html(StringIO(r.text))

    result = []
    for df in tables:
        cols = list(df.columns)
        if 'Simbol' in cols and 'Valoare' in cols:
            for _, row in df.iterrows():
                try:
                    result.append({
                        'symbol':      str(row.get('Simbol', '')).strip(),
                        'price':       ro_float(row.get('Pret')),
                        'var_pct':     ro_pct(row.get('Var. (%)')),
                        'open':        ro_float(row.get('Desch.')),
                        'max':         ro_float(row.get('Max.')),
                        'min':         ro_float(row.get('Min.')),
                        'avg':         ro_float(row.get('Mediu')),
                        'value_ron':   ro_float(row.get('Valoare')),   # trade value in RON
                        'volume':      ro_float(row.get('Volum')),
                        'trades':      ro_float(row.get('Nr. tranz.')),
                        'market':      str(row.get('Piata', '')).strip(),
                        'last_time':   str(row.get('Ora', '')).strip(),
                    })
                except Exception:
                    continue
            break  # use first matching table
    print(f"[snapshot] {len(result)} symbols on CurrentTradingDay")
    return result

# ──────────────────────────────────────────────
# 3. ETF / Unitati de fond tab (ASP.NET postback)
# ──────────────────────────────────────────────
def fetch_etf_snapshot(session):
    """
    Posts back to CurrentTradingDay to switch to the ETF tab.
    Requires __VIEWSTATE, __VIEWSTATEGENERATOR, __EVENTVALIDATION from the GET page.
    """
    r = session.get(
        "https://www.bvb.ro/TradingAndStatistics/Trading/CurrentTradingDay",
        timeout=20
    )

    # Extract ASP.NET hidden form fields correctly
    fields = {}
    for name in ['__VIEWSTATE', '__VIEWSTATEGENERATOR', '__EVENTVALIDATION']:
        m = re.search(
            r'id="__{}"\s+value="([^"]*)"'.format(name),
            r.text
        )
        if not m:
            m = re.search(
                r'name="__{}"\s+value="([^"]*)"'.format(name),
                r.text
            )
        if m:
            fields[name] = m.group(1)

    post_data = {
        '__EVENTTARGET':   'ctl00$ctl00$body$rightColumnPlaceHolder$TabsCtrlInstrumentsType$lb3',
        '__EVENTARGUMENT': '',
        '__LASTFOCUS':     '',
    }
    post_data.update(fields)

    r_etf = session.post(
        "https://www.bvb.ro/TradingAndStatistics/Trading/CurrentTradingDay",
        data=post_data, timeout=20
    )

    try:
        tables = pd.read_html(StringIO(r_etf.text), flavor='lxml')
    except Exception:
        tables = pd.read_html(StringIO(r_etf.text))

    result = []
    for df in tables:
        cols = list(df.columns)
        if 'Simbol' in cols and 'Valoare' in cols:
            for _, row in df.iterrows():
                try:
                    result.append({
                        'symbol':      str(row.get('Simbol', '')).strip(),
                        'price':       ro_float(row.get('Pret')),
                        'var_pct':     ro_pct(row.get('Var. (%)')),
                        'value_ron':   ro_float(row.get('Valoare')),
                    })
                except Exception:
                    continue
            break
    print(f"[etf]    {len(result)} ETFs/unitati de fond")
    return result

# ──────────────────────────────────────────────
# 4. Full details for ONE symbol
# ──────────────────────────────────────────────
def fetch_symbol_detail(session, symbol):
    """
    Scrapes FinancialInstrumentsDetails.aspx?s=SYMBOL and returns
    a fully structured dict. Fetches both Analysis (PE/PB/EPS)
    and shareholding structure in one shot.
    All 9 tables are parsed.
    """
    url = f"https://www.bvb.ro/FinancialInstruments/Details/FinancialInstrumentsDetails.aspx?s={symbol}"
    try:
        r = session.get(url, timeout=20)
        if r.status_code != 200:
            return {'symbol': symbol, '_error': f'HTTP {r.status_code}'}
    except Exception as e:
        return {'symbol': symbol, '_error': str(e)}

    html = r.text
    out = {'symbol': symbol}

    # ── Table 0: basic identity ──
    identity_map = {
        'ISIN': 'isin',
        'Tip': 'instrument_type',
        'Segment': 'segment',
        'Categorie': 'category',
    }
    for ro_label, key in identity_map.items():
        m = re.search(
            rf'{re.escape(ro_label)}\s*</[^>]+>\s*<[^>]+>\s*([^<\n]+)',
            html
        )
        if m:
            out[key] = m.group(1).strip()

    # Status (green-span)
    m = re.search(r'id="[^"]*Stare[^"]*"[^>]*>\s*<span[^>]*>\s*([^<]+)', html)
    out['status'] = m.group(1).strip() if m else None

    # ── Tables 6 & 7: prices + valuation ──
    def tbl_label_value(table_html, label):
        """Find <td>LABEL</td>...<td>VALUE</td> in a table."""
        pattern = (
            rf'<t[dh][^>]*>\s*(?:<[^>]+>\s*)*{re.escape(label)}\s*'
            rf'(?:</[^>]+>)?\s*</t[dh]>'
            rf'.*?<t[dh][^>]*>(.*?)</t[dh]>'
        )
        m = re.search(pattern, table_html, re.DOTALL | re.IGNORECASE)
        if m:
            raw = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            return raw
        # Alternate: label in first column, value in second
        pattern2 = (
            rf'<tr[^>]*>.*?<t[dh][^>]*>\s*(?:<[^>]+>\s*)*{re.escape(label)}\s*(?:</[^>]+>)?\s*</t[dh]>'
            rf'.*?<t[dh][^>]*>(.*?)</t[dh]>(?=.*?</tr>)'
        )
        m2 = re.search(pattern2, html, re.DOTALL | re.IGNORECASE)
        if m2:
            raw = re.sub(r'<[^>]+>', '', m2.group(1)).strip()
            return raw
        return None

    # Known labels across the tables
    value_labels = {
        'Bid / Ask':             'bid_ask',
        'Bid / Ask Vol.':        'bid_ask_vol',
        'Pret referinta':       'reference_price',
        'Data/ora':              'reference_datetime',
        'Ultimul pret':          'last_price',
        'Var':                   'var_abs',
        'Var (%)':               'var_pct',
        'Max.':                  'day_max',
        'Min.':                  'day_min',
        'Capitalizare':          'market_cap_ron',
        'PER':                   'per',
        'P/BV':                  'pbv',
        'EPS':                   'eps',
        'DIVY':                  'divyield_pct',
        'Dividend (2025)':       'dividend_2025_ron',
    }
    for label, key in value_labels.items():
        val = tbl_label_value(html, label)
        if val:
            out[key] = val

    # ── Table 5: shareholders ──
    shareholders = []
    # Find Actionar | Actiuni | Procent header row
    shd_block = re.search(
        r'Actionar\s*</th>(.*?)</table>',
        html, re.DOTALL | re.IGNORECASE
    )
    if shd_block:
        rows = re.findall(
            r'<tr[^>]*>(.*?)</tr>',
            shd_block.group(1),
            re.DOTALL
        )
        for row in rows:
            cells = re.findall(r'<(?:th|td)[^>]*>(.*?)\s*</(?:th|td)>', row, re.DOTALL)
            cleaned = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            cleaned = [c for c in cleaned if c]
            if len(cleaned) >= 3:
                shareholders.append({
                    'holder':    cleaned[0],
                    'shares':    ro_float(cleaned[1]),
                    'pct':       ro_pct(cleaned[2]),
                })
    if shareholders:
        out['shareholders'] = shareholders

    # ── Table 8: share capital ──
    capital_labels = {
        'Numar total actiuni':  'total_shares',
        'Valoare Nominala':     'nominal_value_ron',
        'Capital social':       'share_capital_ron',
        'Data start tranzactionare': 'trade_start_date',
    }
    for label, key in capital_labels.items():
        val = tbl_label_value(html, label)
        if val:
            out[key] = val

    return out

# ──────────────────────────────────────────────
# 5. BET (or other index) components
# ──────────────────────────────────────────────
def fetch_index_components(session):
    """Returns dict: index_name → list of {symbol, name, shares, ref_price, ff_pct}."""
    r = session.get(
        "https://www.bvb.ro/FinancialInstruments/Indices/IndicesProfiles",
        timeout=20
    )
    try:
        tables = pd.read_html(StringIO(r.text), flavor='lxml')
    except Exception:
        tables = pd.read_html(StringIO(r.text))

    # Table 1 is the components table at the time of writing,
    # but we iterate all tables and find the one with 'Simbol'+'Societate'
    for df in tables:
        if 'Simbol' in list(df.columns):
            records = []
            for _, row in df.iterrows():
                records.append({
                    'symbol':       str(row.get('Simbol', '')).strip(),
                    'company':      str(row.get('Societate', '')).strip(),
                    'shares_issued': ro_float(row.get('Actiuni')),
                    'ref_price':    ro_float(row.get('Pret ref.')),
                    'free_float_pct': ro_pct(row.get('FF')),
                })
            return records
    return []

# ──────────────────────────────────────────────
# 6. Master orchestrator
# ──────────────────────────────────────────────
def build_full_dataset(max_workers=6, delay=0.35):
    """
    Orchestrates all scrapes and returns a single structured dict.
    Saves JSON to ./bvb_dataset_YYYY-MM-DD.json
    """
    session = make_session()
    today   = date.today().isoformat()
    out     = {
        'meta': {
            'date': today,
            'generated_at': datetime.now().isoformat(),
            'source': 'https://www.bvb.ro/ (reverse-engineered)',
        },
        'indices':         {},
        'trading_snapshot': [],
        'etf_snapshot':    [],
        'symbols':         [],
        'companies':       {},
        'index_components': {},
    }

    # Step A — trading snapshot (all stocks, live)
    out['trading_snapshot'] = fetch_trading_snapshot(session)

    # Step B — ETF tab via ASP.NET postback
    out['etf_snapshot'] = fetch_etf_snapshot(session)

    # Step C — BET + other index components (full list with ref prices)
    out['index_components']['BET'] = fetch_index_components(session)

    # Step D — merge into a unified symbol list
    all_syms = {s['symbol']: s for s in out['trading_snapshot']}
    all_syms.update({s['symbol']: s for s in out['etf_snapshot']})
    out['symbols'] = sorted(all_syms.values(), key=lambda x: x['symbol'])

    # Step E — deep-dive each symbol (parallel)
    symbols_only = [s['symbol'] for s in out['symbols']]
    print(f"[main] Enriching {len(symbols_only)} symbols (workers={max_workers})...")

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(fetch_symbol_detail, session, sym): sym
            for sym in symbols_only
        }
        for fut in as_completed(futures):
            sym   = futures[fut]
            try:
                detail = fut.result()
                out['companies'][sym] = detail
            except Exception as e:
                out['companies'][sym] = {'symbol': sym, '_error': str(e)}

    # Persist to disk
    out_path = f"./bvb_dataset_{today}.json"
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
    print(f"[main] Dataset written → {out_path}  ({os.path.getsize(out_path)//1024} KB)")

    return out

# ──────────────────────────────────────────────
if __name__ == '__main__':
    data = build_full_dataset(max_workers=6)
    # Quick summary
    companies = data['companies']
    with_details = [c for c in companies.values() if '_error' not in c]
    print(f"\n=== SUMMARY ===")
    print(f"  Trading snapshot  : {len(data['trading_snapshot'])} symbols")
    print(f"  ETF snapshot      : {len(data['etf_snapshot'])} symbols")
    print(f"  Total symbols     : {len(data['symbols'])}")
    print(f"  Detail pages OK   : {len(with_details)}")
    print(f"  BET components    : {len(data['index_components'].get('BET', []))}")
    if with_details:
        # Show a sample
        tlv = companies.get('TLV', companies.get(list(companies.keys())[0]))
        if tlv:
            print(f"\n  Sample: {tlv.get('symbol')}")
            skip = {'symbol', '_error'}
            for k, v in tlv.items():
                if k not in skip:
                    print(f"    {k}: {v}")
