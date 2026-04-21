---
type: session-handoff
date: 2026-04-21
topic: IR-home fast-path + curl_cffi-on-Playwright-failure + playwright-stealth + direct-first walk — coverage 23/33 → 32/33 (97%)
tags: [session, consumer-staples, earnings, scraper, generic-backend, stealth, dedup]
---

# April 21st — IR-Home Fast-Path + Stealth Session

Picks up where `April 20th IR Scraper Generic Backend Session.md` left off (23/33, 10 uncovered).

## Starting state

Per the 4/20 handoff:
- 23/33 tickers (70%) covered.
- 10 uncovered: CL, KMB, MNST, MKC, LW (Stage 2); COST, MO, HSY, TSN, DG (Stage 3).
- `generic_backend` curl_cffi fallback only ran when Playwright *successfully rendered* an empty page — not on `page.goto()` failure.
- No stealth on Playwright; Akamai + Cloudflare both problematic.

## Work done this session

### 1. IR-home fast-path in `generic_backend`

Added pre-candidate-walk step: `_try_extract_from_event_url(ir)` directly on the resolved IR home URL. Returns early when the IR landing exposes the latest quarter's artifacts as `/static-files/{uuid}` or `.pdf` links (LW's Drupal pattern; also MKC, HSY).

### 2. curl_cffi fallback when Playwright `page.goto()` raises

Extended the `except Exception as e` block: if the URL responds 200 via curl_cffi Chrome131, parse HTML and run `_extract_pdfs_from_html` → download & return. Akamai `ERR_HTTP2_PROTOCOL_ERROR` no longer terminates extraction.

### 3. `_extract_pdfs_from_html` now returns `(pdfs, hrefs)`

Tuple return. All 3 callsites updated. The hrefs list feeds quarter derivation and curl_cffi hop-follow.

### 4. Quarter derivation from page links (`_derive_quarter_from_links`)

Problem: LW's IR home has no quarter in its URL, so `parse_quarter_label` fell back to `target_date`, putting artifacts in `Brain/Sources/LW/2026-04-01/` instead of `2026-Q3/`. New helper scans all hrefs for the first one that parses as `YYYY-QN`. LW's IR home links out to `/events/event-details/fiscal-2026-third-quarter-earnings-call` → `2026-Q3`. Integrated in all three code paths (Playwright-failure curl_cffi branch, Playwright-success fallback, end-of-function re-derivation).

### 5. curl_cffi-based hop-follow (`_find_hop_url_from_hrefs`)

Module-level constants `_HOP_DETAIL_PATTERNS`, `_HOP_ANNOUNCE_PATTERNS`, `_HOP_EARNINGS_KWS` plus URL-only hop-match helper. Used in the Playwright-failure branch after direct-PDF extraction returns empty: scan collected hrefs for press-release-detail URLs matching earnings keywords (skipping announcement posts), fetch the hop target via curl_cffi, classify PDFs there.

### 6. Sources folder dedup

Audited all 33 ticker folders; 13 had 2+ event folders from repeated runs during development. 3 patterns:
- **Exact duplicates** (GIS, DLTR): identical hashes in both folders → delete non-canonical side.
- **Complementary artifacts** (CELH, HRL, KR, PEP, SJM, STZ): each folder had a unique subset → merged into one folder.
- **Same-name-different-content CONFLICTs** (CHD, KDP, KO, SJM): kept the **larger** file (smaller = failed/stub re-downloads).

Canonical folder preference: `YYYY-QN` if present, else the date-labeled folder. Result: **12 files deleted, 10 moved, 12 folders removed.** HRL's `2026-Q1/press_release.pdf` turned out to be a misnamed copy of the transcript (same sha1) — correctly replaced with the real 357KB press_release.

### 7. MNST classifier fix (`/node/*/pdf` Drupal pattern)

MNST's press release detail page links to the PDF as `/node/17871/pdf` — Drupal's dynamic PDF renderer. The classifier's PDF-URL check required `.pdf` substring or `/static-files/`; extended to also accept `h.endswith("/pdf")`. Unlocked MNST: press release downloads cleanly via the curl_cffi hop-follow path.

### 8. Playwright-stealth integration

Installed `playwright-stealth` (2.0.3). Wrapped `sync_playwright()` in `Stealth().use_sync(...)`. Every page now gets stealth init-scripts injected — `navigator.webdriver`, plugin fingerprints, WebGL vendor, sec-ch-ua headers all match real Chrome. Bypasses Cloudflare's passive bot-check that was blocking COST.

**Note on audio / CAPTCHA:** stealth does NOT solve visible reCAPTCHA v2 checkboxes (PM's Mediasite). It raises the reCAPTCHA score enough that many sites never challenge, and bypasses Cloudflare's passive fingerprinting, but a visible "I'm not a robot" widget still needs `--semi-auto` or a paid solver.

### 9. Direct-first candidate walk

Before this change: the walk resolved each candidate to a sub-event URL via `_find_earnings_event_link` (drilling into the first earnings-keyword link on the listing). For COST, the top link was "Q3 2026 Earnings Results" — an *upcoming* placeholder event with no PDFs. Meanwhile Q2-FY26's PDF was linked directly on the listing page under the Q2 row: "PRESENTATION → `s201.q4cdn.com/.../Q2-FY-26-Earnings-Supplement.pdf`".

New two-pass per candidate:
- **Pass (a)**: `_try_extract_from_event_url(cand)` on the candidate URL directly. Listings with inline PDFs return here.
- **Pass (b)**: if (a) empty and candidate isn't already an event URL, drill into sub-event via `_find_earnings_event_link`.

Unlocked: COST, CL, KMB, MO all on the same run.

## Current state

### Coverage: 32/33 (97%), +9 vs. session start

Tickers unlocked this session:

| Ticker | Folder | Artifacts | Unlock path |
|---|---|---|---|
| LW | 2026-Q3 | presentation + press_release | IR-home fast-path + curl_cffi on Playwright failure |
| MKC | 2026-Q1 | presentation + transcript | Same |
| HSY | 2026-02-05 | press_release | IR-home fast-path (Playwright path) |
| MNST | 2026-Q4 | press_release | Hop-follow + `/node/*/pdf` classifier |
| COST | 2026-Q3 | presentation | Stealth + direct-first walk |
| CL | 2026-Q4 | press_release | Hop-follow (Playwright-success path) |
| KMB | 2026-Q4 | presentation + press_release | Stealth + direct-first walk |
| MO | 2026-Q1 | press_release + presentation + transcript | Stealth + direct-first walk |
| DG | 2025-Q4 | presentation | Direct-first walk |

**Only TSN remains uncovered.** Its IR landing `https://www.tysonfoods.com/investors` renders with no earnings-classifiable PDFs or events-page links visible in stealth-Playwright; `_ranked_candidates` returns only the IR URL itself as a candidate, and direct extraction finds nothing. Needs a deeper probe — possibly the URL pattern heuristics miss something, or Tyson uses a non-standard IR CMS.

### Infrastructure

- **SKILL.md** updated: new pipeline steps (fast-path, curl_cffi-on-failure, hop-follow, direct-first walk), stealth documented under Known Quirks, prerequisites list now includes `playwright-stealth`.
- **`scrape.py`** ~1180 lines. New helpers: `_derive_quarter_from_links`, `_find_hop_url_from_hrefs`. Module-level constants for hop-follow: `_HOP_DETAIL_PATTERNS`, `_HOP_ANNOUNCE_PATTERNS`, `_HOP_EARNINGS_KWS`. `_extract_pdfs_from_html` now returns `tuple[dict, list]`.
- **Sources tree:** clean, all tickers under `{TICKER}/{QUARTER}/{audio|presentation|transcripts}/` except TSN (empty) and HSY (`2026-02-05` date folder; no quarter-bearing links on its IR home to derive).
- **Calendar refresh:** now shows `transcripts: 32/33`.

## Open decisions / pending work

1. **TSN unlock probe.** IR landing at `https://www.tysonfoods.com/investors` yields nothing. Try: search for a `/investors/news-releases/` or `/newsroom/` path; Tyson's press releases likely live in a separate subdomain or on the main `.com` newsroom. A Playwright-stealth walk of their newsroom with earnings keyword filter would likely find it.
2. **Audio extraction for non-PM tickers.** Still deferred. Many Q4 Inc tenants (MNST, MO, COST) expose webcast links to `events.q4inc.com/attendee/*` or `edge.media-server.com/*`. MO's events-and-presentations page in particular shows Mediasite URLs that could be sniffed via the factored-out `pmi_backend._sniff_mediasite_hls` logic. Factor into `mediasite_vendor` backend.
3. **PM audio still not transcribed.** `Brain\Sources\PM\2025-Q4\audio\PM_2026-02-06.m4a` — deferred again. Run `audio-transcription` skill standalone when ready.
4. **HSY quarter labeling** is still date-based (`2026-02-05`). Its IR home has no URL with quarter info. Could fix by scanning page *text* for "Q4 2025" / "fourth quarter" patterns.
5. **Refactor `pmi_backend` → `mediasite_vendor`.** With 4+ Mediasite-using tickers now identified (PM, MO likely, MNST likely), the `_sniff_mediasite_hls` logic should factor out of `pmi_backend` into a shared vendor module that plugs in between per-ticker backends and `generic_backend`.

## Key file paths

| Purpose | Path |
|---|---|
| Scraper entry point | `C:\Users\rodin\.claude\skills\investor-relations-data-scraper\scripts\scrape.py` |
| Skill definition | `C:\Users\rodin\.claude\skills\investor-relations-data-scraper\SKILL.md` |
| Calendar generator | `C:\Users\rodin\.claude\scripts\investor-relations-data-scraper\consumer_staples_earnings.py` |
| Task-Scheduler `.bat` | `C:\Users\rodin\.claude\scripts\investor-relations-data-scraper\run_consumer_staples_earnings.bat` |
| Calendar output | `C:\Users\rodin\Desktop\Brain\Knowledge\Consumer Staples Earnings Calendar.md` |
| Gap report | `C:\Users\rodin\Desktop\Brain\Knowledge\IR Scraper Gap Report.md` |
| Per-ticker sources | `C:\Users\rodin\Desktop\Brain\Sources\{TICKER}\{QUARTER}\{audio\|presentation\|transcripts}\` |
| Scheduled task name | `Consumer Staples Earnings Weekly` |

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
