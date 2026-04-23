---
type: session-handoff
date: 2026-04-22
topic: user-guided coverage extension (CL/TGT/EL) → iframe scan → ChorusCall dropdown → folder dedup → EDGAR proposal — audio 23/33 → 26/33
tags: [session, consumer-staples, earnings, scraper, audio, choruscall, youtube-embed, iframe, edgar, cleanup]
---

# April 22nd — Audio Coverage Push Session

Picks up where `April 21st Event Pump Bug Session.md` left off (audio 23/33 — w/ ChorusCall sniffer just built). Goal: close the remaining 10 missing tickers and clean up the artifact tree. End state: 26/33 audio, single folder per ticker, comprehensive Source Map.

## Starting state

Per the April 21st handoff:
- PDFs 33/33, audio 23/33.
- Working sniffers: direct_audio, west_intrado, q4_inc_attendee, choruscall, youtube_live (live URLs only), mediasite (auto path; reCAPTCHA blocks most events).
- 10 tickers still missing audio: PEP, MDLZ, KDP, DLTR, MKC (mediasite reCAPTCHA), CL, TGT, EL, DG, MNST.
- IR Audio Source Map drafted at `Brain\Knowledge\IR Audio Source Map.md`.
- Folder structure had duplicates from multiple scrape runs creating both date-labeled and Q-labeled folders for the same event.

## Work done this session

### 1. User-guided lead — EL via ChorusCall

User flagged via screenshot that EL's webcasts live at `elcompanies.com/en/investors/events-and-presentations`. Probed: every earnings event listed has a `event.choruscall.com/mediaframe/webcast.html?webcastid={id}` link. Q2 FY2026 (Feb 5 2026) is at `webcastid=kv9nzVwN`.

**No code change required.** ChorusCall sniffer was added in the prior session; EL just hadn't been re-run since. Re-ran `--tickers EL`: scraper iterated through 3 west_intrado `tp_special=8` URLs (all returned no HLS — those are conference appearances, not earnings) before hitting the ChorusCall earnings URL and downloading. **EL ✓**.

### 2. User-guided lead — TGT via YouTube iframe

User flagged via screenshot that TGT's earnings event-details pages embed a YouTube video directly via `<iframe src="https://www.youtube.com/embed/{video_id}?rel=0">`. Three changes needed:

1. **Extended `youtube_live` vendor pattern** to match `youtube.com/embed/`, `youtube.com/watch`, and `youtube-nocookie.com/embed/` in addition to the existing `youtube.com/live/` and `youtu.be/`. Iframe embeds are functionally the same as direct video URLs for yt-dlp.

2. **Extended `_scan_and_download_audio` to scan iframes**, not just `a[href]`. Added a separate `iframe[src]` eval after the link scan; concatenates into the same `links` list with iframe `title` or `name` attribute as link text.

3. **IR_URLS override** to point at `corporate.target.com/investors/events-presentations/event-details-03-03-26` directly. The events index page (`/events-presentations/`) lists events but doesn't surface the iframe; only the per-event-details page does. **Will need updating per quarter** — the URL slug is `event-details-MM-DD-YY`.

After all three changes: **TGT ✓** (yt-dlp downloads to `.m4a`).

### 3. User-guided lead — CL via ChorusCall (multi-step)

User screenshot showed CL's webcasts at `investor.colgatepalmolive.com/events-and-webcasts` (an "Archived Events" listing). Each event has a "Listen to webcast" link, but the link goes to a **same-domain intermediate page** (`/notice-q4-2025-earnings-webcast`), not directly to the vendor. Probed the notice page: contains the actual ChorusCall URL `webcastid=s8h4YO2M`.

Two changes needed:
1. **IR_URLS override** to the notice page directly: `investor.colgatepalmolive.com/notice-q4-2025-earnings-webcast`. (Index page works too via the audio-only candidate scan, but pointing at the notice page directly is faster.)

2. **Extended ChorusCall sniffer** to fill `select#udef1` (Investor Type dropdown). CL's CC form has an extra required dropdown that STZ/SYY/EL didn't have. Reused `_is_placeholder_option(text, opt)` helper from mediasite to skip placeholder options ("-- Investor Type --", etc.). Picks first real option (e.g. "Analyst").

After: **CL ✓**.

### 4. EL/CL: dropdown logic generalization

The `_is_placeholder_option` helper now covers both Mediasite Country/Investor Type dropdowns and ChorusCall `udef1` Investor Type. Detection rules:
- HTML `disabled` attribute set
- Empty `value` attribute
- Text has no alphanumerics (dots, dashes, whitespace only)
- Text starts with "Select", "Choose", "Please", "Pick one", or "- -"

This pattern (placeholder-skip + first-real-option select) is now the standard for any required dropdown across vendors.

### 5. Folder dedup + consolidation

Multiple scrape runs created split folders for the same earnings event — typically a date-labeled folder (e.g. `ADM/2026-02-03/`) AND a Q-labeled folder (e.g. `ADM/2026-Q1/`) for the same event, with overlapping or differing files. Inventory:

- 9 ticker folders had files with duplicate basenames across two folders.
- **6 of 10 duplicate-named files had DIFFERENT md5s** — the scraper pulled different versions across runs. e.g. ADM presentation was 3.4MB in one folder vs 25.5MB in another (smaller version was a degraded HTML→PDF render fallback).

Deduplication rules applied:
- For exact-content dupes (md5 match): keep one, delete the other.
- For different-content dupes: keep the LARGER file (typically the real PDF; smaller is HTML render fallback).
- For split folders (no overlap, e.g. transcript in date folder + audio in Q folder): consolidate to the folder that has audio (audio was the scarcest artifact, so it anchors the canonical event folder).

Per-ticker actions executed:
| Ticker | Action | Final folder |
|---|---|---|
| ADM | Delete `2026-02-03/` (smaller dupes) | `2026-Q1/` (3 files) |
| BF-B | Delete `2026-Q2/` (lone dup) | `2026-Q3/` (3 files) |
| BG | Move orphan transcript → `2025-Q4/` | `2025-Q4/` (4 files) |
| CELH | Consolidate both Q4 folders → `2026-Q4/` | `2026-Q4/` (4 files) |
| CL | Delete `2026-Q1/` (lone smaller dup) | `2025-Q4/` (3 files) |
| CLX | Merge `2026-02-03/` → `2026-Q3/` (kept larger press_release) | `2026-Q3/` (3 files) |
| EL | Merge `2026-02-05/` → `2026-Q3/` | `2026-Q3/` (4 files) |
| KO | Consolidate → `2026-Q1/` | `2026-Q1/` (4 files) |
| MDLZ | Consolidate → `2025-Q4/` | `2025-Q4/` (2 files) |
| PG | Delete `2026-01-22/` (kept larger press_release) | `2026-Q3/` (3 files) |
| TGT | Delete `2025-Q3/` (identical dup) | `2025-Q4/` (3 files) |

After: every ticker has exactly one quarter folder, zero duplicate basenames, all 26 audio files preserved.

**Future-scraper note:** when a destination file already exists, hash-compare and keep the larger one rather than silently overwriting. Several different-content collisions in this session were the result of overwrite-on-rerun.

### 6. EDGAR discussion (not built)

User raised: "Can we use EDGAR's free API instead of scraping IR sites?" Honest assessment delivered:

- **EDGAR has**: 8-K (earnings press release as exhibit 99.1, prepared remarks as 99.2 sometimes, presentation as 99.3 sometimes), 10-Q, 10-K. All public companies file by law. ~20+ years of history.
- **EDGAR does NOT have**: earnings call audio (never), Q&A transcripts (rare — only the ~20-30% of cos that file prepared remarks).
- **Where EDGAR wins**:
  - Press releases — guaranteed-present, structured PDF, no IR-scraping needed. Replaces our messy HTML render fallback.
  - **10-K and 10-Q** — completely net new capability not in current scraper.
  - Filing-time source-of-truth for "what's the most recent earnings event" (vs yfinance approximation).
- **Where EDGAR loses**: audio (zero) and transcripts (mostly zero).

**Proposal made, not yet built**: separate `edgar.py` module (~150-200 lines), `Brain/Sources/{TICKER}/filings/{form-type}/{yyyy-mm-dd}/`. Stays independent of IR scraper. Recommended as the next session's primary workstream.

### 7. Historical backfill discussion (not built)

User asked whether we can pull all historical data from IR sites, not just the latest. Honest answer:

- **Press releases**: EDGAR is the answer. Don't extend the IR scraper.
- **Presentations**: 50-70% achievable from IR sites (companies typically retain last 2-8 quarters). Modest extension.
- **Audio**: ~20-22 of 33 tickers programmatically reachable for non-gated vendors (direct_audio, choruscall, youtube_live, q4_inc_attendee, west_intrado). Each historical event = distinct URL on IR page; just loop. Audio retention is the real cap — many companies delete replays after 90 days to 1 year.
- **Mediasite tickers**: each historical event = one manual reCAPTCHA solve. Prohibitively tedious for full backfill.
- **Unresolved tickers**: same blockers as current (MNST, DG).

Recommended order: **EDGAR first** (text history, biggest win), then **non-gated audio loop** (extends current sniffers).

### 8. User concern about ROI captured

User pushed back: "this was inefficient — I could've done this all manually by now." Acknowledged. Honest framing for future sessions:

- Total session time: ~8-12 hours across April 21-22.
- Manual equivalent: ~2 hrs per quarter × N quarters of recurring use to break even.
- Real alternatives that probably should have been used: AlphaSense / Sentieo / Bamsec subscription (~$3-15k/yr; engineering time > subscription cost for professional research workflows), or just relying on the 31/33 transcripts already on hand without needing audio.
- The scraper IS genuinely good at the recurring incremental run — front-loaded build cost, but next quarter's run on these 33 tickers should take ~15 min vs ~45-60 min in this session.
- For new tickers using known vendors: should "just work" via the Source Map. For new vendors: still ~30-60 min of investigation per vendor.

Future sessions should weigh build-vs-buy explicitly before extending the scraper further.

## Current state

### Coverage

- **PDFs: 33/33** (unchanged).
- **Audio: 26/33** — up from 23/33 at session start, 3/33 at start of multi-day work.
  - Pre-existing: PM, KMB, WMT.
  - Added in April 21st: LW, PG, KO, MO, GIS, HSY, CELH, SJM, BF-B, HRL, TSN, ADM, KR, COST, CAG, BG, CHD, CLX, STZ, SYY.
  - **Added today: EL, TGT, CL.**
- Still missing audio (7 tickers):
  - **5 mediasite reCAPTCHA**: PEP, MDLZ, KDP, DLTR, MKC. Run `python scrape.py --semi-auto --tickers PEP,MDLZ,KDP,DLTR,MKC` and solve manually.
  - **1 webcast_eqs**: DG. Sniffer not built; login-form submit stays on `/login/` after submitting email-only form. Needs probe (possibly Enter key vs click, or email-confirmation step).
  - **1 SPA hang**: MNST. Context-level 30s timeout doesn't catch the hang; needs deeper Playwright tracing.
- **Transcripts: 31/33** (unchanged — provenance unknown; not derived from this scraper).

### Folder structure

Every ticker now has exactly ONE quarter folder. No duplicate basenames. All 26 audio files preserved through cleanup.

### Infrastructure changes today

- **scrape.py**:
  - `youtube_live` vendor catalog extended to `youtube.com/embed/`, `youtube.com/watch`, `youtube-nocookie.com/embed/`.
  - `_scan_and_download_audio` extended to scan `iframe[src]` in addition to `a[href]`. Iframes get treated as synthetic links with title/name as text.
  - `_sniff_choruscall_mp4` extended to handle `select` elements inside `form#registrationForm` — picks first non-placeholder option using shared `_is_placeholder_option` helper.
- **consumer_staples_earnings.py** — IR_URLS overrides:
  - `CL`: `investor.colgatepalmolive.com/notice-q4-2025-earnings-webcast`
  - `TGT`: `corporate.target.com/investors/events-presentations/event-details-03-03-26`
- **Brain/Knowledge/IR Audio Source Map.md** — comprehensive per-ticker map updated with CL/TGT/EL entries; remaining 7 tickers labeled with concrete next-step actions.
- **Brain/Sources/** — folder structure cleaned: 33 ticker folders, each with one quarter subfolder, zero dupes.

## Open decisions / pending work

### 1. Mediasite reCAPTCHA queue (5 tickers)

Highest-ROI remaining action. Run interactively:
```
python scrape.py --semi-auto --tickers PEP,MDLZ,KDP,DLTR,MKC
```
User sits with headed browser, solves each reCAPTCHA manually (~30s per ticker). Should unlock all 5.

### 2. Build EDGAR scraper (recommended next session)

Separate module `edgar.py`. Get full text history (8-K + 10-Q + 10-K) for all 33 tickers via free API. Best build-vs-extend decision available. Replaces messy IR press-release scraping with guaranteed-present 8-K exhibit 99.1. Adds 10-K/10-Q which IR scraper never did.

Estimated: 1-2 hrs. No blockers (EDGAR rate-limit is generous, format is consistent across all companies).

### 3. DG webcast_eqs login flow

Current state: form has single `input[name='username']` (email) + submit button. Sniffer fills + submits but URL stays at `/login/`. Likely needs:
- Email-confirmation flow (EQS may email a magic link to actual real address)
- OR specific Enter-key vs click-button behavior
- OR an embedded confirmation step we missed

Quick further probe in headed Playwright would resolve. ~30 min.

### 4. MNST SPA hang

Unresolved across multiple sessions. Context-level 30s timeout doesn't catch it. Needs deeper Playwright tracing — possibly `page.on('load')` + `page.on('domcontentloaded')` listeners to identify the stalling operation. OR alternative: switch MNST to a `curl_cffi` + raw HTML parse path that bypasses Playwright entirely.

### 5. Historical backfill (deferred per user's ROI concerns)

If pursued, recommended order:
1. EDGAR for press releases + 10-K + 10-Q (full history, free, easy).
2. Non-gated audio loop (extend current sniffers to iterate all URLs per page, not just first match): ~20-22 tickers, last 4-8 quarters each, depending on company audio retention.
3. Skip mediasite historical (each event = one CAPTCHA solve).

### 6. Scraper hygiene improvement (low priority)

When a destination file already exists, hash-compare and keep the larger one rather than overwriting. Several different-content collisions in this session were the result of silent overwrite-on-rerun.

### 7. Module refactor (deferred from prior sessions)

scrape.py is now ~2200 lines. Split plan still on the table for when audio coverage stabilizes:
- `ir_walker.py` — IR resolution, candidate ranking, hop-follow
- `pdf_extractor.py` — PDF detection + classification + render fallback
- `audio_extractor.py` — vendor sniffers, dispatch, download
- `scrape.py` — thin orchestrator (CLI, browser setup, gap list)

Now that we're at 26/33 and the remaining 7 are mostly known-blockers, this is a reasonable trigger point. Estimated 2-3 hrs.

## Key file paths

| Purpose | Path |
|---|---|
| Scraper entry point | `C:\Users\rodin\.claude\skills\investor-relations-data-scraper\scripts\scrape.py` |
| Skill definition | `C:\Users\rodin\.claude\skills\investor-relations-data-scraper\SKILL.md` |
| Calendar generator + IR_URLS | `C:\Users\rodin\.claude\scripts\investor-relations-data-scraper\consumer_staples_earnings.py` |
| Calendar output | `C:\Users\rodin\Desktop\Brain\Knowledge\Consumer Staples Earnings Calendar.md` |
| Gap report | `C:\Users\rodin\Desktop\Brain\Knowledge\IR Scraper Gap Report.md` |
| **IR Audio Source Map** | `C:\Users\rodin\Desktop\Brain\Knowledge\IR Audio Source Map.md` |
| Webcast vendor survey | `C:\Users\rodin\Desktop\Brain\Knowledge\IR Webcast Vendor Survey.md` |
| Per-ticker sources | `C:\Users\rodin\Desktop\Brain\Sources\{TICKER}\{QUARTER}\{audio\|presentation\|transcripts}\` |
| Scheduled task name | `Consumer Staples Earnings Weekly` |
| This handoff | `C:\Users\rodin\Desktop\Brain\Sessions\Transcript Scraping & Consolidation\Handoffs\April 22nd Audio Coverage Push Session.md` |
| Prior handoffs | `Brain\Sessions\Transcript Scraping & Consolidation\Handoffs\April 18th...`, `April 20th IR Scraper v1...`, `April 20th IR Scraper Generic Backend...`, `April 21st IR-Home Fast-Path...`, `April 21st Audio Extraction...`, `April 21st Event Pump Bug...` |

## How to run

```bash
# Standard gap-filling run (all tickers with missing audio/PDFs, MNST excluded)
python "C:\Users\rodin\.claude\skills\investor-relations-data-scraper\scripts\scrape.py" \
    --tickers PG,COST,WMT,KO,PEP,PM,MO,MDLZ,CL,TGT,KMB,GIS,SYY,KR,STZ,HSY,KDP,EL,TSN,ADM,CHD,CAG,CLX,SJM,HRL,MKC,LW,BG,DLTR,DG,BF-B,CELH

# Mediasite reCAPTCHA queue (interactive — solve captcha per ticker)
python scrape.py --semi-auto --tickers PEP,MDLZ,KDP,DLTR,MKC

# Just one ticker for testing
python scrape.py --tickers TSN --no-transcribe

# Regenerate webcast vendor survey
python scrape.py --survey-webcasts

# Live log through tee
python -u scrape.py 2>&1 | tee "C:\Users\rodin\Desktop\Brain\Knowledge\_run.log"
```

---

## How to create the next handoff

At the end of every session, write a new handoff under `C:\Users\rodin\Desktop\Brain\Sessions\{Task-Theme}\Handoffs\` following the exact structure below. This keeps every future "cold start" predictable — the next session picks up one file and knows everything it needs.

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
