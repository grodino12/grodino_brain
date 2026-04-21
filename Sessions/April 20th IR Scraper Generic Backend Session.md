---
type: session-handoff
date: 2026-04-20
topic: IR scraper generic backend — coverage from 7/33 → 22/33 (67%) in 6 iterations
tags: [session, consumer-staples, earnings, scraper, generic-backend, ir-sites]
---

# April 20th — IR Scraper Generic Backend Session

Second handoff on 2026-04-20. Picks up where `April 20th IR Scraper v1 Session.md` left off (PM working via pmi_backend, 32 other tickers with no backend / no IR URLs).

## Starting state

Per the prior (v1) handoff:
- PM (Philip Morris) complete via `pmi_backend` with Mediasite semi-auto flow.
- 32 other tickers had no backend and would skip with `no backend for {TICKER}`.
- Scripts folder cleanup + quarter folder restructure (`Brain\Sources\{TICKER}\{QUARTER}\audio/presentation/transcripts`) done.
- Weekly Task Scheduler job re-pointed at `C:\Users\rodin\.claude\scripts\investor-relations-data-scraper\run_consumer_staples_earnings.bat`.
- End-of-run calendar refresh wired into `scrape.py::main()`.
- Session-handoff convention established + saved to memory.

## Work done this session

### 1. Decision: build a generic backend, not per-ticker
User raised the architectural question: "Can we just have the search for these something that is a part of the program?" and later "We are going to continue to develop this program so that as we find unique entry points for some that are more difficult they become an option that we search for automatically when the basic search function on the IR site doesn't work."

Agreed on **chain-of-strategies dispatch**: `TICKER_BACKENDS.get(ticker, generic_backend)`. Per-ticker bespoke backends override; generic_backend handles everything else. Future vendor modules (Q4 Inc, Mediasite, Nasdaq IR Hub, Issuer Direct) slot in above generic_backend but are shared across every ticker that uses that vendor.

### 2. Removed `IR_URLS` empty-skip gate
The `IR_URLS` dict is for display only (calendar + gap report links). Each backend bakes its own archive URL internally (`pmi_backend` has `PMI_ARCHIVE_URL`; `generic_backend` derives from yfinance). So the dict is no longer a hard prerequisite — the real prerequisite is "is a backend registered?"

### 3. Generic backend v1 — baseline pipeline (7 steps)
Built `generic_backend()` with: start URL resolution → IR page discovery → candidate collection → event URL matching → event page navigation → PDF classification → download.

Initial failure rate was high. First full sweep: **7/33 tickers** (PM + 6 via generic_backend). Errors clustered into distinct categories, which set up the next 5 rounds of targeted fixes.

### 4. Round-by-round fixes (6 rounds total)

Each round probed the largest failure bucket, added a targeted fix, re-ran. Coverage grew:

**Round 1 — PDFs and early errors** → 11 tickers (33%)
- **`curl_cffi` with `impersonate="chrome131"`** for all PDF downloads. Q4 Inc's `gcs-web.com` + similar hosts sit behind Akamai Bot Manager which RST_STREAMs Playwright Chromium's HTTP/2 regardless of headers. Real Chrome's TLS fingerprint passes cleanly.
- **Widened `_EVENTS_KEYWORDS_TEXT/URL`** to include `quarterly-reports`, `financial-information`, `sec-filings`, `results`, `reports`, etc. Previously too narrow.
- **"Download is starting" fallback** — when Playwright refuses to `goto()` a file-download URL, route it straight to `download_pdf()` as a direct press release. Unblocked CHD, CAG (Q4 Inc doc-host URLs).
- **`parse_quarter_label()` now prefers tightly adjacent year-quarter pairs** — `2025-Q4` from `"2025-q4-..."` wins over loose matches, fixing misclassifications like CHD's `2026-Q4` bug (URL had `/2026/Jan/30/2025-Q4-Earnings-Release.pdf` — old regex grabbed 2026 from path + Q4 from filename separately).

**Round 2 — candidate retry + webcast portal filter** → 12 tickers (36%)
- **Per-candidate retry**: refactored the candidate loop so landing on a dead-end candidate falls through to the next one instead of erroring. Previously we'd match the first candidate and give up if it had no PDFs.
- **Webcast-portal skip**: `events.q4inc.com/attendee/*`, `edge.media-server.com`, `event.webcasts.com`, `webcasts.com/starthere`, `wsw.com/webcast` — these are audio-only by design. If any candidate's URL matches one of these, skip it without navigating.

**Round 3 — subpath brute-force fallback** → 16 tickers (48%)
- When IR nav yields 0 candidates (common on JS-heavy SPAs and minimalist landings), brute-force common URL paths via `curl_cffi`: `/news-releases`, `/press-releases`, `/events`, `/quarterly-results`, `/financial-information`, `/sec-filings`, etc. Any 200-OK response that mentions earnings-related keywords becomes a candidate.

**Round 4 — date-agnostic matching + alt-root subdomain swap** → 22 tickers (67%) **[biggest jump]**
- User suggested: **don't target dates, just find the most recent earnings release and derive quarter from the page content**. Landmark insight — every IR site uses a different date format (long-form, slash-delimited, URL path segments `/2026/02/19/`, compact `20260219`, etc.) and missing any format was a false negative.
- Rewrote `_find_earnings_event_link()` to return the **first earnings-keyword-matching link on the listing page** (IR sites list reverse-chronologically, so first match = most recent).
- Dropped year requirement from `_url_is_earnings_event()`.
- **Alt-root subdomain swap**: `_derive_alt_roots()` takes any URL, extracts the apex domain, and generates sibling-subdomain alternates (`corporate.{apex}`, `news.{apex}`, `newsroom.{apex}`, `{apex}`). Solves the WMT case where yfinance returned `stock.walmart.com` (a stub landing) but press releases actually live on `corporate.walmart.com/news/`. Run on WMT after this change: 3 PDFs downloaded (press_release + presentation + transcript) from exactly the URL the user pointed at.

**Round 5 — loosened earnings-link matcher** → 22 tickers (67%, +PG recovered)
- Round 4's `_find_earnings_event_link` was too strict: required specific patterns like `"-q2-"` or `"earnings-release"` in addition to the earnings keyword. Regressed PG because its press release titles use "Second Quarter 2026 Results" (no dashes, no `q2`).
- New matcher: accept any link that passes `is_earnings_event()`, minus a hard blocklist of generic nav labels (`"earnings"`, `"events"`, `"news"`, `"view all news"`, etc.), with a length-guard for short tabs that don't have a detail-page URL.

### 5. All fixes documented in SKILL.md
Per user's "ensure all troubleshooting is encapsulated in the skill so the next pull is smoother", SKILL.md now documents the generic_backend's 7-step pipeline, four fallback layers (alt-root → subpath → candidate retry → Playwright `goto` fallback), and 10+ known quirks (Akamai HTTP/2, Angular reactive forms, OneTrust banner, Q4 Inc attendee URLs, "Download is starting", Mediasite reCAPTCHA wall, etc.).

## Current state

### Coverage
**22/33 tickers (67%) have at least one artifact on disk** covering the current earnings cycle:

| Ticker | Artifacts |
|---|---|
| PM | audio + press_release + presentation |
| WMT | press_release + presentation + transcript |
| GIS | press_release + presentation + transcript |
| HRL | press_release + presentation + transcript |
| EL | press_release + presentation + transcript |
| KR | press_release + presentation + transcript |
| DLTR | press_release + presentation |
| STZ | press_release + presentation |
| ADM | presentation + transcript |
| SJM | press_release + transcript |
| KO | press_release + transcript |
| PEP | press_release + transcript |
| BG | transcript |
| CELH | transcript |
| SYY | presentation |
| BF-B, CAG, CHD, CLX, KDP, PG, TGT | press_release each |

### 11 tickers still uncovered — grouped by failure mode
- **Stage 2 "no earnings link matched on candidate pages" (5)**: CL, KMB, MNST, MKC, LW. Candidates are found, but `_find_earnings_event_link()` doesn't locate a release link on them — likely JS-rendered listings that need longer wait times, or unusual title phrasing.
- **Stage 3 "candidates resolved to event URLs but no PDFs classified" (6)**: COST, MO, MDLZ, HSY, TSN, DG. Landed on what looks like an event page but the PDF classifier finds no matches — probably sites where the press release body is HTML (not linked as a PDF download) OR where PDFs use unusual label text.

### Infrastructure
- **SKILL.md** fully documents the generic_backend pipeline, fallbacks, and known quirks. Follow-session-ready.
- **`scrape.py`** is ~900 lines. Key helpers: `_find_ir_page`, `_try_common_ir_patterns`, `_try_common_ir_subpaths`, `_derive_alt_roots`, `_ranked_candidates`, `_find_earnings_event_link`, `_collect_pdf_links`, `generic_backend`, `pmi_backend`.
- **`consumer_staples_earnings.py`** — calendar generator, has `parse_quarter_label()` which now prefers tight year-quarter pairings.

## Open decisions / pending work

1. **The remaining 11 tickers need per-site probes.** Each failure is likely 1-2 site-specific quirks. Order of attack (by likely leverage): MO, MDLZ, CL, KMB, MNST (all probably share Q4 Inc or Nasdaq IR Hub patterns — if one unlocks, several may). Then COST, HSY, TSN, MKC, LW, DG individually.
2. **PM audio still not transcribed.** `Brain\Sources\PM\2025-Q4\audio\PM_2026-02-06.m4a` exists but no whisper transcript yet. Trigger the audio-transcription chain standalone when ready.
3. **No per-vendor modules built yet.** `pmi_backend` is still the only bespoke backend. Once 2-3 more tickers are diagnosed and they share a vendor (Q4 Inc most likely), factor out a vendor module that plugs in between `TICKER_BACKENDS` and `generic_backend` in the dispatch chain.
4. **Audio extraction for non-PM tickers.** Deferred. Need per-vendor webcast sniffers (Q4 Inc live portal, Nasdaq IR Hub, Issuer Direct) — each 100-200 lines modeled on `pmi_backend`'s `_sniff_mediasite_hls`.
5. **CAPTCHA automation long-term.** Currently PM requires `--semi-auto`. If other tickers turn out to also CAPTCHA-wall, consider a paid solver integration (2Captcha / Anti-Captcha).

## Key file paths

| Purpose | Path |
|---|---|
| Calendar generator | `C:\Users\rodin\.claude\scripts\investor-relations-data-scraper\consumer_staples_earnings.py` |
| Task-Scheduler `.bat` target | `C:\Users\rodin\.claude\scripts\investor-relations-data-scraper\run_consumer_staples_earnings.bat` |
| Weekly run log | `C:\Users\rodin\.claude\scripts\investor-relations-data-scraper\consumer_staples_earnings.log` |
| Last-run full log (this session) | `C:\Users\rodin\.claude\scripts\investor-relations-data-scraper\last_full_run.log` |
| Scraper entry point | `C:\Users\rodin\.claude\skills\investor-relations-data-scraper\scripts\scrape.py` |
| Skill definition (fully current) | `C:\Users\rodin\.claude\skills\investor-relations-data-scraper\SKILL.md` |
| Calendar markdown output | `C:\Users\rodin\Desktop\Brain\Knowledge\Consumer Staples Earnings Calendar.md` |
| Gap report output | `C:\Users\rodin\Desktop\Brain\Knowledge\IR Scraper Gap Report.md` |
| Per-ticker sources | `C:\Users\rodin\Desktop\Brain\Sources\{TICKER}\{QUARTER}\{audio\|presentation\|transcripts}\` |
| Scheduled task name | `Consumer Staples Earnings Weekly` (Task Scheduler → root) |

---

## How to create the next handoff

At the end of every session, write a new handoff under `C:\Users\rodin\Desktop\Brain\Sessions\` following the exact structure below. This keeps every future "cold start" predictable — the next session picks up one file and knows everything it needs.

### Naming
`{Month-name} {Day-ordinal} {short-topic} Session.md`
e.g. `April 20th IR Scraper v1 Session.md`, `April 25th CELH Backend Session.md`.

Ordinal = `st` / `nd` / `rd` / `th`. One or two topic words. Keep the filename short.

### Required sections (in this order)

1. **YAML frontmatter** — `type: session-handoff`, `date: YYYY-MM-DD` (absolute, never relative), `topic: {one-line}`, `tags: [session, ...]`.
2. **`# {Title}`** heading matching the filename.
3. **`## Starting state`** — what was true at session start. Reference the prior handoff filename explicitly so the chain is walkable.
4. **`## Work done this session`** — grouped by logical chunks (numbered `### 1.` subsections work well). Each subsection should say *what changed* and *why*, not just the surface action. Capture root-cause insights (e.g. "Akamai RST_STREAMs Playwright's HTTP/2 regardless of headers" — that sentence saves the next session an hour of diagnosis).
5. **`## Current state`** — bullet list of what's working, what's partially working, what's not. Include concrete file paths for artifacts produced.
6. **`## Open decisions / pending work`** — numbered list of unresolved items. Each one should state the *decision* or *action* needed, not just a vague "look into X". If a decision is blocked on user input, say so.
7. **`## Key file paths`** — two-column table: Purpose | Path. Use absolute paths. Include scheduled task names and external system references.
8. **`## How to create the next handoff`** — paste this exact section verbatim. Never drop it; never let the template drift without updating all copies forward.

### Quality bar

- Write so the next session (cold, no conversation history) can act without re-asking you questions.
- Prefer concrete over abstract: `curl_cffi impersonate="chrome131"` beats "the HTTP client".
- Capture *why* a design choice was made when it's non-obvious. Code shows what; handoffs should show why.
- If you deleted, renamed, or moved files, explicitly mention it — the next session will otherwise hunt for the old paths.
- Keep it self-contained. Don't say "as discussed" — write out the discussion outcome.
