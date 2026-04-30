"""sec-edgar-fetch: pull 10-K / 10-Q filings and XBRL company facts from EDGAR.

See SKILL.md for folder layout and usage.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import requests

try:
    from playwright.sync_api import sync_playwright
    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False

# --- Paths --------------------------------------------------------------------

BRAIN_SOURCES = Path(r"C:\Users\rodin\Desktop\Brain\Sources")
SKILL_DIR = Path(__file__).resolve().parent
CACHE_DIR = SKILL_DIR / ".cache"

# Reuse the Consumer Staples ticker list maintained by the IR scraper.
IR_SCRAPER_SCRIPTS = Path(r"C:\Users\rodin\.claude\scripts\investor-relations-data-scraper")
sys.path.insert(0, str(IR_SCRAPER_SCRIPTS))
try:
    from consumer_staples_earnings import TICKERS as DEFAULT_TICKERS  # type: ignore
except Exception:  # pragma: no cover - fallback when IR scraper module missing
    DEFAULT_TICKERS = {}

# --- HTTP ---------------------------------------------------------------------

USER_AGENT = "rodinogj12@gmail.com sec-edgar-fetch/1.0"
REQ_INTERVAL_S = 0.2  # 5 req/sec, SEC hard cap is 10 req/sec
_last_req_ts: float = 0.0


def _throttle() -> None:
    global _last_req_ts
    now = time.monotonic()
    wait = REQ_INTERVAL_S - (now - _last_req_ts)
    if wait > 0:
        time.sleep(wait)
    _last_req_ts = time.monotonic()


def _get(url: str, *, accept: str = "application/json", stream: bool = False, max_retries: int = 4) -> requests.Response:
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    delay = 1.0
    for attempt in range(max_retries):
        _throttle()
        r = requests.get(url, headers=headers, stream=stream, timeout=30)
        if r.status_code == 200:
            return r
        if r.status_code in (403, 404):
            r.raise_for_status()
        # 429 / 5xx — back off
        time.sleep(delay)
        delay *= 2
    r.raise_for_status()
    return r  # unreachable


# --- Ticker -> CIK ------------------------------------------------------------

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
CACHE_TTL = timedelta(days=7)


def load_ticker_cik_map() -> dict[str, int]:
    cache_file = CACHE_DIR / "company_tickers.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    fresh = cache_file.exists() and (
        datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime) < CACHE_TTL
    )
    if not fresh:
        r = _get(COMPANY_TICKERS_URL)
        cache_file.write_text(r.text, encoding="utf-8")
    data = json.loads(cache_file.read_text(encoding="utf-8"))
    # company_tickers.json structure: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
    return {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}


def resolve_cik(ticker: str, cik_map: dict[str, int]) -> int | None:
    # SEC uses "BRK-B" style for dual-class; user uses "BF-B". Try both.
    candidates = [ticker.upper(), ticker.upper().replace("-", "."), ticker.upper().replace("-", "")]
    for c in candidates:
        if c in cik_map:
            return cik_map[c]
    return None


# --- Submissions --------------------------------------------------------------

@dataclass
class Filing:
    form: str            # "10-K" / "10-Q"
    accession: str       # "0000320193-24-000123"
    filing_date: str     # "2024-11-01"
    report_date: str     # "2024-09-28" (periodOfReport)
    primary_doc: str     # "aapl-20240928.htm"
    quarter: str         # "2026-Q2", "2025-FY" — fiscal label

    @property
    def accession_nodash(self) -> str:
        return self.accession.replace("-", "")


def derive_fiscal_label(form: str, report_date: str, fye_mmdd: str, fy: int | None, fp: str | None) -> str:
    """Compute folder label like '2026-Q2' or '2025-FY'.

    SEC-provided fy/fp wins when present. Otherwise derive from fiscal year end
    (MMDD) + periodOfReport + form type.
    """
    if fy and fp:
        return f"{fy}-{fp}"

    y, m, _ = report_date.split("-")
    period_month = int(m)
    period_year = int(y)
    try:
        fye_month = int(fye_mmdd[:2])
    except Exception:
        fye_month = 12

    # Fiscal year containing this period: periods after the FYE month roll into next FY.
    fiscal_year = period_year + 1 if period_month > fye_month else period_year

    if form == "10-K":
        return f"{fiscal_year}-FY"

    # 10-Q: month index within fiscal year (1..12), then ceil-divide by 3.
    month_idx = ((period_month - fye_month - 1) % 12) + 1
    quarter = (month_idx + 2) // 3  # 1-3 -> 1, 4-6 -> 2, etc.
    return f"{fiscal_year}-Q{quarter}"


def _parse_submission_arrays(arrays: dict, fye: str) -> list[Filing]:
    """Parse a parallel-array submissions block (either the `recent` object or
    one of the older archive JSONs) into a list of Filing objects."""
    if not arrays:
        return []
    n = len(arrays.get("accessionNumber", []))
    fy_arr = arrays.get("fy") or [None] * n
    fp_arr = arrays.get("fp") or [None] * n
    out = []
    for i in range(n):
        form = arrays["form"][i]
        report_date = arrays["reportDate"][i]
        if not report_date:  # filings with no periodOfReport (e.g. some 8-Ks) — skip
            continue
        fy_val = int(fy_arr[i]) if fy_arr[i] else None
        fp_val = fp_arr[i] or None
        out.append(
            Filing(
                form=form,
                accession=arrays["accessionNumber"][i],
                filing_date=arrays["filingDate"][i],
                report_date=report_date,
                primary_doc=arrays["primaryDocument"][i],
                quarter=derive_fiscal_label(form, report_date, fye, fy_val, fp_val),
            )
        )
    return out


def fetch_submissions(cik: int, full_history: bool = False) -> list[Filing]:
    """Fetch filing metadata for a CIK.

    SEC's submissions.json holds the most recent ~1000 filings in its `recent`
    block. Older filings are paginated through `filings.files` — each entry
    points to a sibling JSON with the same parallel-array schema. Set
    `full_history=True` to walk those archives too.
    """
    url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
    data = _get(url).json()
    fye = data.get("fiscalYearEnd", "1231") or "1231"
    filings = _parse_submission_arrays(data.get("filings", {}).get("recent", {}), fye)
    if not full_history:
        return filings
    for archive in data.get("filings", {}).get("files", []):
        name = archive.get("name")
        if not name:
            continue
        try:
            arch_data = _get(f"https://data.sec.gov/submissions/{name}").json()
        except requests.HTTPError as e:
            print(f"  [warn] archive {name} failed: {e}")
            continue
        filings.extend(_parse_submission_arrays(arch_data, fye))
    return filings


# --- Download -----------------------------------------------------------------

def archive_url(cik: int, filing: Filing, filename: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{filing.accession_nodash}/{filename}"


def download_filing(cik: int, ticker: str, filing: Filing, dry_run: bool) -> tuple[int, int]:
    """Returns (new_files, skipped_files)."""
    out_dir = BRAIN_SOURCES / ticker / filing.quarter / "filings"
    quarter = filing.quarter
    form_slug = filing.form.replace("/", "-")
    htm_path = out_dir / f"{ticker}_{filing.report_date}_{form_slug}.htm"
    xlsx_path = out_dir / f"{ticker}_{filing.report_date}_{form_slug}_financial_report.xlsx"

    if htm_path.exists() and xlsx_path.exists():
        print(f"  [skip] {ticker} {filing.form} {filing.report_date} ({quarter}) — already on disk")
        return 0, 1

    if dry_run:
        print(f"  [plan] {ticker} {filing.form} {filing.report_date} ({quarter}) -> {out_dir}")
        return 1, 0

    out_dir.mkdir(parents=True, exist_ok=True)
    new_count = 0

    meta_path = htm_path.with_suffix(".meta.json")

    if not htm_path.exists():
        url = archive_url(cik, filing, filing.primary_doc)
        try:
            r = _get(url, accept="text/html", stream=True)
            htm_path.write_bytes(r.content)
            print(f"  [get ] {htm_path.name}")
            new_count += 1
        except requests.HTTPError as e:
            print(f"  [fail] primary doc for {ticker} {filing.accession}: {e}")

    if htm_path.exists() and not meta_path.exists():
        meta = {
            "ticker": ticker,
            "cik": cik,
            "form": filing.form,
            "accession": filing.accession,
            "filing_date": filing.filing_date,
            "report_date": filing.report_date,
            "primary_doc": filing.primary_doc,
            "quarter": filing.quarter,
            "archive_base_url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{filing.accession_nodash}/",
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    if not xlsx_path.exists():
        url = archive_url(cik, filing, "Financial_Report.xlsx")
        try:
            r = _get(url, accept="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", stream=True)
            xlsx_path.write_bytes(r.content)
            print(f"  [get ] {xlsx_path.name}")
            new_count += 1
        except requests.HTTPError as e:
            # Very recent filings (iXBRL) don't have Financial_Report.xlsx yet — SEC
            # generates it asynchronously. Older filings also occasionally lack it.
            # Next run will pick it up once it appears.
            if e.response is not None and e.response.status_code == 404:
                print(f"  [wait] Financial_Report.xlsx not yet available for {filing.form} {filing.report_date} (will retry next run)")
            else:
                print(f"  [fail] Financial_Report.xlsx for {ticker} {filing.accession}: {e}")

    return new_count, 0


def download_companyfacts(cik: int, ticker: str, dry_run: bool) -> bool:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
    out_path = BRAIN_SOURCES / ticker / "companyfacts.json"
    if dry_run:
        print(f"  [plan] companyfacts -> {out_path}")
        return False
    try:
        r = _get(url)
    except requests.HTTPError as e:
        print(f"  [fail] companyfacts for {ticker}: {e}")
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(r.content)
    size_mb = len(r.content) / (1024 * 1024)
    print(f"  [get ] companyfacts.json ({size_mb:.1f} MB)")
    return True


# --- Orchestrator -------------------------------------------------------------

def process_ticker(
    ticker: str,
    cik_map: dict[str, int],
    *,
    forms: list[str],
    limit: int | None,
    since: str | None,
    do_filings: bool,
    do_facts: bool,
    dry_run: bool,
    full_history: bool = False,
) -> dict[str, int]:
    ticker = ticker.upper()
    print(f"\n== {ticker} ==")
    cik = resolve_cik(ticker, cik_map)
    if cik is None:
        print(f"  [fail] no CIK mapping for {ticker}")
        return {"missing_cik": 1}

    stats = {"new": 0, "skipped": 0, "facts": 0}

    if do_filings:
        try:
            all_filings = fetch_submissions(cik, full_history=full_history)
        except requests.HTTPError as e:
            print(f"  [fail] submissions for {ticker}: {e}")
            return stats
        wanted = [f for f in all_filings if f.form in forms]
        if since:
            wanted = [f for f in wanted if f.report_date >= since]
        if limit is not None:
            wanted = wanted[:limit]
        if not wanted:
            print(f"  [info] no matching filings")
        for f in wanted:
            n, s = download_filing(cik, ticker, f, dry_run)
            stats["new"] += n
            stats["skipped"] += s

    if do_facts:
        if download_companyfacts(cik, ticker, dry_run):
            stats["facts"] = 1

    return stats


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Pull SEC EDGAR filings + company facts into Brain\\Sources")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--ticker", help="single ticker")
    g.add_argument("--tickers", help="comma-separated list")
    p.add_argument("--forms", default="10-K,10-Q", help="forms to pull (comma-separated)")
    p.add_argument("--limit", type=int, default=8, help="max filings per ticker, newest first (ignored when --all is set)")
    p.add_argument("--since", help="earliest periodOfReport (YYYY-MM-DD) — applies to --all too")
    p.add_argument("--all", action="store_true", dest="all_history",
                   help="pull the entire historical archive, not just the most recent --limit filings. "
                        "Walks submissions.json `recent` + every paginated archive in `filings.files`. "
                        "Can be hundreds of filings per ticker for long-lived companies.")
    p.add_argument("--companyfacts-only", action="store_true")
    p.add_argument("--no-companyfacts", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.ticker:
        tickers = [args.ticker]
    elif args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = list(DEFAULT_TICKERS.keys())
        if not tickers:
            print("No tickers: provide --ticker/--tickers or ensure the Consumer Staples list loads.")
            return 2

    forms = [f.strip() for f in args.forms.split(",") if f.strip()]
    do_filings = not args.companyfacts_only
    do_facts = not args.no_companyfacts

    print(f"Loading ticker -> CIK map ...")
    cik_map = load_ticker_cik_map()
    print(f"Loaded {len(cik_map)} ticker mappings.")

    effective_limit = None if args.all_history else args.limit
    if args.all_history:
        print(f"[info] --all: walking entire submissions history (paginated). --limit ignored.")

    totals = {"new": 0, "skipped": 0, "facts": 0, "missing_cik": 0}
    for t in tickers:
        r = process_ticker(
            t, cik_map,
            forms=forms, limit=effective_limit, since=args.since,
            do_filings=do_filings, do_facts=do_facts, dry_run=args.dry_run,
            full_history=args.all_history,
        )
        for k, v in r.items():
            totals[k] = totals.get(k, 0) + v

    print("\n== Summary ==")
    print(f"  Tickers processed: {len(tickers)}")
    print(f"  New files:         {totals['new']}")
    print(f"  Skipped (on disk): {totals['skipped']}")
    print(f"  companyfacts:      {totals['facts']}")
    if totals["missing_cik"]:
        print(f"  Missing CIK:       {totals['missing_cik']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
