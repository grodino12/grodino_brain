---
name: sec-edgar-fetch
description: Pull SEC filings (10-K, 10-Q) and structured XBRL company facts from EDGAR and drop them into the user's ticker-organized folders under Brain\Sources\{TICKER}\{QUARTER}\filings\. Also caches the cumulative companyfacts JSON at Brain\Sources\{TICKER}\companyfacts.json for fast line-item lookups. Gap-fills: skips filings already on disk. Rate-limited (5 req/sec) with SEC-compliant User-Agent. Accepts any ticker — falls back to the Consumer Staples list when no ticker is given. Use when the user asks to pull SEC filings, refresh EDGAR data, download 10-Ks/10-Qs, or refresh XBRL facts for a ticker.
---

# sec-edgar-fetch

Pulls 10-K / 10-Q filings and XBRL company facts from EDGAR and lands them in the same `Brain\Sources\{TICKER}\{QUARTER}\` hierarchy the IR scraper uses.

## When to use
- User says "pull the 10-K for PG", "refresh SEC filings for CELH", "grab EDGAR data for the consumer staples list", "update company facts for KO", or similar.
- User explicitly invokes the skill by name.

## Folder layout
```
Brain\Sources\{TICKER}\
├── companyfacts.json                     # cumulative XBRL facts (ticker-root, not per-quarter)
└── {QUARTER}\                            # e.g. "2026-Q2", "2025-FY" — sourced from SEC fy+fp
    └── filings\
        ├── {TICKER}_{periodOfReport}_10-K.htm
        ├── {TICKER}_{periodOfReport}_10-K_financial_report.xlsx
        ├── {TICKER}_{periodOfReport}_10-Q.htm
        └── {TICKER}_{periodOfReport}_10-Q_financial_report.xlsx
```

Quarter label comes from SEC's own `fy` + `fp` fields in the submission metadata (authoritative). A 10-K lands in `{fy}-FY`; a 10-Q lands in `{fy}-Q{N}`. This may differ from folder labels produced by the IR scraper (which parses IR-page titles) — when they disagree, each source files under its own label and the user can reconcile manually.

## Prerequisites
- Python 3.12 with `requests` (already installed).
- No API key needed. SEC requires a User-Agent header identifying the requester — the skill uses `rodinogj12@gmail.com` (from the user's memory).

## How to run
```bash
python "C:\Users\rodin\.claude\skills\sec-edgar-fetch\scripts\fetch.py" \
    [--tickers PG,KO,CELH]        # optional: comma-separated list. Default: the Consumer Staples TICKERS dict.
    [--ticker PG]                  # optional single-ticker shortcut
    [--forms 10-K,10-Q]            # optional: default "10-K,10-Q"
    [--limit 8]                    # optional: max filings per ticker, newest first. Default 8.
                                   # Ignored when --all is set.
    [--all]                        # optional: pull the ENTIRE historical archive, not just the
                                   # most recent --limit. Walks both the submissions.json `recent`
                                   # block AND every paginated archive in `filings.files`. Can be
                                   # hundreds of filings per ticker for long-lived companies
                                   # (PG → ~130 10-Ks/10-Qs since 1993).
    [--since 2022-01-01]           # optional: earliest periodOfReport to keep. Applies to --all too.
    [--companyfacts-only]          # optional: skip filing downloads, only refresh XBRL cache
    [--no-companyfacts]            # optional: skip XBRL cache refresh
    [--dry-run]                    # optional: list what would be pulled, don't download
```

Default (no flags): for every Consumer Staples ticker, ensure the latest 10-K and the most recent 10-Qs (up to 8 filings total per ticker) are on disk, and refresh `companyfacts.json`.

**Gap skip rule:** a filing is skipped if its target `filings\*_{form}.htm` path already exists. `companyfacts.json` is always re-downloaded on each run (it's the XBRL cache — should stay fresh). This means `--all` is resumable — if it's interrupted halfway through a ticker's 100+ filings, re-running picks up where it left off without re-downloading anything.

**Historical depth with --all.** SEC's `submissions.json` keeps the most recent ~1000 filings in a `recent` block; older filings live in paginated sibling archives listed under `filings.files`. Without `--all`, only `recent` is read. With `--all`, every archive is walked. Combined with `--since 1995-01-01` you can backfill the entire public company history (iXBRL didn't exist pre-2009, so pre-2009 filings will be plain HTML — `financials-extract`'s iXBRL path will skip those; they're only useful for manual reading).

## Output
- Per-filing artifacts under `Brain\Sources\{TICKER}\{QUARTER}\filings\`:
  - Primary filing HTML (`.htm`) — the document users click through on EDGAR.
  - `Financial_Report.xlsx` — SEC auto-generated from the filing's XBRL instance. Directly openable, all statements pre-parsed.
- Per-ticker `companyfacts.json` at the ticker root — one JSON with every historical value for every XBRL-tagged concept (Revenues, NetIncomeLoss, Assets, etc.), spanning all filings.
- Console: per-ticker status (✓ / ✗ / skip), final summary counts.

## Architecture
Single orchestrator at `scripts\fetch.py`. No shared helpers — imports `TICKERS` from the existing investor-relations-data-scraper script (`C:\Users\rodin\.claude\scripts\investor-relations-data-scraper\consumer_staples_earnings.py`) to keep the Consumer Staples list in one place.

Pipeline per ticker:
1. **Resolve CIK**: download `https://www.sec.gov/files/company_tickers.json` once per run and look up ticker → CIK. Cache file at `C:\Users\rodin\.claude\skills\sec-edgar-fetch\scripts\.cache\company_tickers.json` (refreshed if >7 days old).
2. **Fetch submissions**: `https://data.sec.gov/submissions/CIK{cik:010d}.json`. Parse `recent` filing arrays (form, filingDate, accessionNumber, primaryDocument, reportDate, fy, fp).
3. **Filter** to requested forms, newest-first, apply `--since` and `--limit`.
4. **For each filing**:
   - Compute quarter label from `fy` + `fp` (e.g. `2026-Q2`, `2025-FY`).
   - Gap check: if `{TICKER}_{reportDate}_{form}.htm` already exists under that path, skip.
   - Download primary doc + `Financial_Report.xlsx` from `https://www.sec.gov/Archives/edgar/data/{cik}/{accession-nodash}/`.
5. **Refresh companyfacts**: `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json` → write to `Brain\Sources\{TICKER}\companyfacts.json`.

## SEC rate limits and etiquette
- Hard limit: 10 req/sec. Skill is set to 5 req/sec (200ms between calls) with jittered backoff on 429.
- Required: `User-Agent: rodinogj12@gmail.com`. SEC rejects requests without a real-looking UA.
- No other auth — the relevant endpoints are all public.

## Known quirks
- **Quarter labeling divergence.** SEC's `fy`/`fp` are fiscal-year/fiscal-period as the company reports them. For PG (June FY end), a 10-Q with `periodOfReport=2025-12-31` has `fy=2026, fp=Q2` — so the folder is `2026-Q2`. The IR scraper parses PG's IR page titles and may produce `2026-Q3` for the matching press release because the PG marketing team sometimes labels differently. Both are the same event; the file just lands in the SEC-labeled folder. Acceptable v1 behavior.
- **10-K Q4 overlap.** A 10-K covers the full fiscal year including Q4; no separate 10-Q is filed for Q4. The skill files 10-Ks as `{fy}-FY`. If the user also wants a `{fy}-Q4` copy, run the IR scraper — 10-Ks satisfy the Q4 "earnings release" slot there.
- **No PDF.** SEC never serves PDFs. Primary docs are `.htm`. The `financials-extract` skill currently requires PDFs — to bridge, use the browser's Print-to-PDF, or pair with a future `htm→pdf` converter. Not in v1.
- **Large companyfacts JSON.** Big-cap tickers produce 10-30 MB JSON files. Still small enough to git-ignore and keep on disk.
- **Historical depth.** `submissions.json` `recent` holds the last ~1,000 filings. For very old filings, SEC paginates via `files` sub-object — not handled in v1 (recent filings are what matters for active modeling).

## Chaining
None in v1. Future: after pulling a filing, optionally kick off `financials-extract` once HTM support lands there. For now the downloads are standalone and the user invokes downstream skills manually.
