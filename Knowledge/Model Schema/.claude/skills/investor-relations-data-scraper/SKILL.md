---
name: investor-relations-data-scraper
description: Pull missing earnings-call audio, press releases, and presentation PDFs for consumer-staples tickers by scraping each company's investor-relations site. Reads the Consumer Staples Earnings Calendar to identify gaps (tickers whose latest earnings call has no audio/transcript under Brain\Sources\{TICKER}\{QUARTER}\), walks the IR site with a heuristic generic backend, and downloads every artifact it can find. Audio → Brain\Sources\{TICKER}\{QUARTER}\audio\; press release → transcripts\; investor presentation → presentation\. After audio downloads, chains into the `audio-transcription` skill to produce a whisper transcript, and then regenerates the Consumer Staples Earnings Calendar so ✅/❌ cells reflect the newly-pulled sources. Use this skill when the user asks to pull missing IR sources, fill the earnings calendar gaps, or scrape earnings data for one or more tickers. Current coverage: PDFs for all 33 consumer-staples tickers. Audio extraction is pending per-vendor sniffer modules — run `--survey-webcasts` to catalog each ticker's webcast vendor.
---

# Investor Relations Data Scraper

Fills the ❌ cells in the Consumer Staples Earnings Calendar by downloading each company's latest earnings artifacts from their IR site into per-quarter folders.

## When to use
- User says "pull missing consumer staples sources", "run the IR scraper", "fill the earnings calendar gaps", or similar.
- User explicitly invokes the skill by name.
- Not auto-triggered by the weekly calendar refresh (manual-only — scrapers fail in ways that benefit from eyes on them, and v1 tickers currently require a manual CAPTCHA step).

## Folder layout
```
Brain\Sources\{TICKER}\
└── {QUARTER}\                          # e.g. "2025-Q4", YYYY-MM-DD fallback if unknown
    ├── audio\{TICKER}_{YYYY-MM-DD}.m4a
    ├── presentation\{TICKER}_{YYYY-MM-DD}_presentation.pdf
    └── transcripts\
        ├── {TICKER}_{YYYY-MM-DD}_press_release.pdf
        └── {TICKER}_{YYYY-MM-DD}.md    # whisper transcript (produced later by audio-transcription)
```
The quarter label is parsed from the event title / landing URL (e.g. `.../2025-q4-earnings-release`). If parsing fails, the folder is named by the event date (`YYYY-MM-DD`).

**Folder meanings:**
- `audio\` — raw earnings call recording (m4a from the webcast).
- `presentation\` — investor slide deck PDF.
- `transcripts\` — press release PDF plus the whisper-generated call transcript markdown.

## Prerequisites
- `consumer_staples_earnings.py` has been run recently (calendar is current).
- `IR_URLS` in that script is **optional** (only used for display in the calendar / gap report — the scraper bakes its own URLs into each backend).
- Python 3.12 with `playwright`, `playwright-stealth`, `curl_cffi`, `requests`, `yfinance`, `pandas`, `lxml`. `ffmpeg` on PATH. All installed.

## How to run
```bash
python "C:\Users\rodin\.claude\skills\investor-relations-data-scraper\scripts\scrape.py" \
    [--tickers PM,CELH]   # optional: restrict to specific tickers
    [--no-transcribe]     # optional: skip chaining into audio-transcription
    [--dry-run]           # optional: report gaps, don't download
    [--semi-auto]         # Headed Chromium; pauses for the user to solve
                          #   a visible CAPTCHA when a webcast player requires
                          #   it (typically Mediasite). Needed only once audio
                          #   vendor modules are wired in.
```

Default behavior (no flags): scan all tickers with gaps, download everything the generic backend can reach headlessly, chain each new audio file into the `audio-transcription` skill.

**Gap skip rule:** a ticker is skipped from the work queue as soon as it has a transcript (press release PDF or whisper md) on disk for the current quarter — even if audio is still missing. Audio is vendor-specific and often unreachable without a bespoke backend; re-running the whole generic pipeline every invocation for tickers that are already "covered enough" on the text side is pure waste. Audio gaps get picked up separately when a vendor backend exists for that ticker.

## Output
- **Artifacts**: saved under `Brain\Sources\{TICKER}\{QUARTER}\` — audio and transcripts split into the two subfolders shown above. The markdown transcript from the audio-transcription chain appears later in the same `transcripts\` folder as `{TICKER}_{YYYY-MM-DD}.md`.
- **Gap report**: `Brain\Knowledge\IR Scraper Gap Report.md` — lists tickers the skill couldn't fully handle, with the IR URL for manual follow-up.
- **Console**: per-ticker status log (artifacts ✓, errors ✗, per-step Mediasite progress).

## Architecture

Two files. Both live under `scripts\`:
- `scripts\scrape.py` — single orchestrator: gap detection → Playwright → per-ticker backend → ffmpeg → audio-transcription chain.
- Imports `consumer_staples_earnings.py` from `C:\Users\rodin\.claude\scripts\investor-relations-data-scraper\` for TICKERS / IR_URLS / `has_source` / `parse_quarter_label` / path helpers.

Every ticker runs through `generic_backend`. Audio extraction is handled separately by per-vendor sniffer modules (pending — run `--survey-webcasts` to catalog each ticker's webcast vendor and prioritize which modules to build).

### `generic_backend` — the one backend for every ticker

PDFs only. Audio is deferred to per-vendor sniffer modules once the webcast survey identifies which vendors matter (Mediasite, Q4 Inc attendee, West/Intrado, etc.).

Pipeline:
1. **Resolve starting point**: use `IR_URLS[ticker]` if present; otherwise `yfinance.Ticker(T).info['website']`.
2. **Find IR page** — three-pass strategy, cheapest first:
   - (a) if the starting URL is already IR-ish (contains "investor", "/ir/", etc.), use it directly;
   - (b) try common IR URL patterns via `curl_cffi`: `investors.{domain}`, `investor.{domain}` (singular — HRL/CHD use this), `ir.{domain}`, `{domain}/investors`, `{domain}/investor-relations`, `{domain}/investor`. First 200-OK that mentions "press release" / "earnings" / "quarterly" / "sec filing" wins;
   - (c) fall back to crawling the corp homepage for any nav link whose text matches `_IR_NAV_KEYWORDS_TEXT` or whose href matches `_IR_NAV_KEYWORDS_URL`.
3. **Collect up to 6 event/press candidate URLs** from the IR page, ranked by keyword score. Keywords span: "news & events", "press releases", "quarterly results", "financial results", "financial information", "sec filings", "earnings", "events", "news", "results", "reports", plus URL patterns `events`, `press-release`, `quarterly-results`, `financial-information`, `filings`, etc.
   - **Subpath fallback**: if the IR page yields zero candidates via nav-crawl (common on JS-heavy SPA tenants and minimalist landing pages like `stock.walmart.com`), brute-force common URL paths (`/news-releases`, `/press-releases`, `/events`, `/quarterly-results`, `/financial-information`, etc.) with `curl_cffi`. Every path that responds 200-OK with earnings-ish body text is added to the candidate list.
4. **IR-home fast-path** (checked BEFORE the candidate walk). Many IR CMS templates — LW's Drupal landing is the reference case, also MKC and HSY — surface the latest quarter's Earnings Presentation + Press Release + Transcript PDFs directly on the IR home page, linked as `/static-files/{uuid}` or direct `.pdf` URLs labeled "Earnings Presentation" / "Press Release" / "Transcript". The fast-path calls `_try_extract_from_event_url(ir)` once with the IR home URL — if it yields classifiable PDFs, we're done in one hop and skip sub-navigation entirely. CMS widgets auto-update these links to point at the most recent quarter, so when present they are authoritative.
5. **Walk candidates** with a two-pass strategy per candidate:
   - **Pass (a) direct extraction**: try `_try_extract_from_event_url(cand)` on the candidate URL itself. Listings often expose PDFs directly (COST's `/events-and-presentations/` shows "PRESENTATION → Q2-FY-26-Earnings-Supplement.pdf" inline with the Q2 row; KMB and MO similarly). Previously the walk always drilled down to sub-event pages first, skipping these.
   - **Pass (b) sub-event drill-down**: if direct extraction yielded nothing AND the candidate isn't already an event URL, call `_find_earnings_event_link(page, cand)` and extract from the resolved sub-event URL. Original behavior, now a fallback.
   - Skip candidates pointing at webcast portals: `events.q4inc.com/attendee/*`, `edge.media-server.com/*`, `event.webcasts.com/*`, `webcasts.com/starthere`, `wsw.com/webcast`. These are audio-only by design and never contain PDFs — landing on them wastes a navigation cycle.
   - If the candidate URL itself already looks like a specific earnings event (contains `-q1-`/`-q2-`/`-q3-`/`-q4-`, `fourth-quarter`, `earnings-release`, `quarterly-results`, etc.), skip Pass (b) — direct extraction is the only meaningful attempt.
   - `_find_earnings_event_link` returns the **first earnings-keyword-matching link on the page**. Date-agnostic by design: IR sites list news reverse-chronologically, so the topmost earnings match is the most recent release. Trying to match a specific `target_date` is fragile — every site uses a different date format (long-form, slash-delimited, URL path segments `/2026/02/19/`, compact `20260219`, etc.).
6. **Navigate to the event detail page.** If `page.goto()` raises "Download is starting" (event URL itself is a direct PDF, common with Q4 Inc doc-hosted sites), or the URL contains `.pdf` / `earnings-release` / `press-release`, route directly to `download_pdf()` and save as press release.
   - **Playwright-failure curl_cffi fallback**: when `page.goto()` fails with a non-download error (e.g. Akamai's `ERR_HTTP2_PROTOCOL_ERROR` on LW/MKC/MNST/CL/KMB IR hosts), switch to curl_cffi — fetch the HTML, run the PDF classifier on its links, and if empty, try a curl_cffi-based hop-follow: scan the parsed hrefs for a press-release-detail-pattern URL matching earnings keywords (skipping announcement posts), fetch that hop target via curl_cffi, and classify PDFs there. This was previously only reachable in the Playwright-success path.
7. **Classify PDFs on the event detail page.** Specific labels win over generic "Download as PDF":
   - `presentation` — link text contains "presentation"/"slide" or URL contains "slides"
   - `transcript` — link text or URL contains "transcript"
   - `press_release` — link text contains "press release"/"news release"/"earnings release"; otherwise, on a press-release detail page, a generic "Download as PDF"/"Download PDF"/"View PDF"/"PDF" link is treated as the press release.
8. **Derive the quarter label.** Start by running `parse_quarter_label(event_detail_url)`. If the URL has no quarter info (common after the IR-home fast-path — LW's `/static-files/{uuid}` URLs don't carry a quarter), fall back to scanning all hrefs on the same page via `_derive_quarter_from_links()` — the first link that parses as `YYYY-QN` wins. LW's IR home lacks quarter info in its own path but links out to `/events/event-details/fiscal-2026-third-quarter-earnings-call` which parses cleanly as `2026-Q3`, so the folder is correctly labeled.
9. **Download via `curl_cffi` with `impersonate="chrome131"`** (real Chrome TLS fingerprint) and place into `{QUARTER}\transcripts\` (press_release, transcript) or `{QUARTER}\presentation\` (presentation).
10. **HTML-press-release fallback**. If after PDF downloads the `press_release` artifact is still missing AND there's a text-labeled "Press Release" link on the current page pointing at a `news-detail` / `press-releases/detail` / `news-release-details` URL, navigate there and render the page to PDF via Playwright's `page.pdf()`. Handles IR sites (DG) that publish press releases as HTML-only articles with no downloadable file — the PDF icon on their events page is decorative.
11. **Page-to-PDF final fallback**. If we've arrived at a press-release-detail URL and nothing has been classified and the body contains earnings keywords, render that page to PDF as the press release. Covers the direct-drill-into-news-detail-URL case.

### Future vendor-audio modules (not yet implemented)

Audio extraction requires per-vendor logic. Dispatch will be by **webcast URL host**, not by ticker — each module registers the host patterns it handles. Priority order is driven by the webcast-vendor survey (`python scrape.py --survey-webcasts` → `Brain\Knowledge\IR Webcast Vendor Survey.md`).

Candidate modules (to be built):
- `mediasite_vendor` — `edge.media-server.com` / `sonicfoundry.com`. Guestbook form + reCAPTCHA v2 checkbox; auto-fills text/select fields, requires `--semi-auto` for the visible CAPTCHA, then sniffs the `.m3u8` playlist URL from network traffic. Sniff logic already present as `_sniff_mediasite_hls`.
- `q4_inc_attendee_vendor` — `events.q4inc.com/attendee/*`. Separate sniffer — different player protocol than Mediasite.
- `west_intrado_vendor` — `event.webcasts.com` / `webcasts.com/starthere` / `cc.webcasts.com`. Sniff logic already present as `_sniff_west_intrado_hls`.
- Other vendors as surfaced by the survey (`wsw.com/webcast`, `open-exchange.net`, etc.).

## Known quirks
- **Playwright-stealth wraps all browser contexts.** `scrape.py` imports `playwright_stealth.Stealth` and wraps `sync_playwright()` in `stealth.use_sync(...)`. Every page gets stealth init-scripts injected so `navigator.webdriver`, plugin fingerprints, WebGL vendor strings, sec-ch-ua headers etc. match real Chrome. This bypasses Cloudflare's passive bot-check (COST's Q4 Inc tenant was blocked without it) and keeps reCAPTCHA scores high enough to avoid triggering the challenge on most sites. **Does not solve visible CAPTCHAs** — Mediasite players with a visible reCAPTCHA v2 checkbox still require `--semi-auto`.
- **Presentation classifier is text-only, not URL-based.** Old versions accepted `"slides" in href` as a match signal, which made DG's 2016 Analyst Day deck (URL `.../1-MPilkington-Opening_Slides.pdf`) get mis-labeled as the current quarter's presentation. Fixed: now requires `"presentation"` or `"slide"` in the link *text*. `.pdf` / `/static-files/` / `/pdf` endings still qualify a URL as PDF-serving.
- **CAPTCHA wall on Mediasite.** Mediasite's guestbook form includes a reCAPTCHA v2 checkbox — fully-headless automation can't click through. Once the Mediasite vendor module lands, run with `--semi-auto`: opens a visible browser, pre-fills the form, and pauses with a terminal prompt; the user clicks CAPTCHA + Submit and presses Enter to resume. A paid solver service (2Captcha/Anti-Captcha) is the only way to fully automate; not worth it yet.
- **Fake registration info** is used. IR webcasts are public / lead-gen-only — no ToS concern.
- **HLS URLs are time-limited** (~1-2 hour token). Registration + download must happen in one run; URLs can't be cached.
- **Akamai Bot Manager blocks Playwright Chromium's HTTP/2** on Q4 Inc's `gcs-web.com` static-file host. Symptom: `page.goto()` fails with `ERR_HTTP2_PROTOCOL_ERROR` or `context.request.get()` times out. Fix: always download PDFs through `curl_cffi` with `impersonate="chrome131"` (real Chrome TLS fingerprint).
- **Angular reactive forms** (used by Mediasite's guestbook) only mark a control as "touched" after a blur event — `.fill()` alone doesn't enable the Submit button. Solution: `click` → `fill` → `Tab` for text inputs; for `<select>` elements, select by *label* (Angular's `ngValue` produces synthetic values like `"1: 1"` that don't always match `select_option(value=)`), then dispatch synthetic `change`+`blur` events.
- **OneTrust cookie banner** overlays the form on Mediasite pages and blocks the Submit button click. Always try `#onetrust-accept-btn-handler` dismissal before filling.
- **Q4 Inc `events.q4inc.com/attendee/` URLs** are webcast attendee portals — they have the live stream but no PDFs. `generic_backend._is_webcast_portal` filters these out of the PDF candidate walk; they'll be picked up by the future `q4_inc_attendee_vendor` module for audio.
- **"Download is starting" error** — Playwright raises this when a `page.goto()` target resolves to a direct file download (Content-Disposition: attachment). The generic backend catches this and routes the URL through `download_pdf()` as a direct press release, rather than failing.
- **Coverage is incremental.** Generic backend handles most of the PDF work; per-vendor modules handle audio + edge cases. Each addition covers every ticker using that vendor forever.

## Chaining
After downloading an audio file, the script shells out to:
```
python "C:\Users\rodin\.claude\skills\audio-transcription\scripts\transcribe.py" --audio <path> --ticker <T> --date <YYYY-MM-DD>
```
…which produces the markdown transcript and (per that skill's own chain) triggers `analyze-earnings-transcript` for the structured summary.

Pass `--no-transcribe` to disable this chain (download only).
