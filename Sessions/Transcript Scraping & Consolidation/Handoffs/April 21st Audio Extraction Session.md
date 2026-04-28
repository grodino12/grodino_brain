---
type: session-handoff
date: 2026-04-21
topic: audio extraction workstream — survey → vendor catalog → direct_audio + youtube_live wired → west_intrado partially wired
tags: [session, consumer-staples, earnings, scraper, audio, survey, vendor-modules]
---

# April 21st — Audio Extraction Session

Picks up where `April 21st IR-Home Fast-Path Session.md` left off (33/33 PDF coverage; audio pending per-vendor sniffer modules).

## Starting state

Per the 4/21 IR-Home handoff:
- 33/33 tickers had PDF coverage on disk.
- Audio was at 1/33 (PM's `PM_2026-02-06.m4a` from the old `pmi_backend` flow).
- Plan was: (1) factor out `_sniff_mediasite_hls`, (2) build `q4_inc_attendee_vendor`, (3) add other vendor modules as discovered.
- Open architecture question: how to identify which vendor each ticker uses without hardcoding (which led to building a webcast-URL survey this session).

## Work done this session

### 1. PMI-specific code removed

User requested removing "all references to PMI" — the bespoke `pmi_backend` was a v1 debugging scaffold that shouldn't outlive its purpose.

Deleted:
- `pmi_backend` function (~130 lines) + `PMI_ARCHIVE_URL` constant
- `TARGET_DATE_WINDOW_DAYS`, `_date_format_variants` (pmi-specific date matching, zero other callers)
- `TICKER_BACKENDS` dict + dispatch logic — now always `generic_backend(...)` direct call
- Unused `timedelta` import
- `"PM": "https://www.pmi.com/investor-relations"` override in IR_URLS (later re-added pointing at the archive URL — see section 6)
- `### pmi_backend` section in SKILL.md + stale ±7 days event-matching window quirk
- Updated frontmatter description to reflect 33/33 PDF coverage

Kept (vendor-generic helpers; needed for future vendor modules):
- `_sniff_mediasite_hls`, `_sniff_west_intrado_hls` — vendor sniffers
- `download_hls_to_m4a`, `FAKE_REG_INFO` — shared audio helpers

scrape.py went from ~1815 → 1685 lines before the audio work below.

### 2. Webcast-vendor URL catalog

Added `WEBCAST_VENDOR_PATTERNS` dict (module-level) and `classify_webcast_url(href, text)` function. Seeded from the existing `_is_webcast_portal` filter (5 hosts) plus hosts observed across IR sites. Final catalog covers:
- `mediasite`, `q4_inc_attendee`, `west_intrado`, `wsw`, `open_exchange`, `veracast`, `ir_direct`, `spark_live`, `brainshark`, `streetevents`, `cc.webcasts` (via west_intrado), `webcast_eqs`, `youtube_live`, `direct_audio` (special bucket for raw MP3/M4A).

Plus `_WEBCAST_TEXT_HINTS` / `_WEBCAST_URL_HINTS` for the `(unknown)` fallback bucket when a link is webcast-ish but the host isn't in the catalog.

### 3. Webcast-URL survey mode (`--survey-webcasts`)

Added `run_webcast_survey()`, `survey_webcast_urls_for_ticker()`, `_collect_webcast_hits_on_page()`, `write_webcast_survey_report()`, `WebcastHit` dataclass. Walks each ticker's IR the same way `generic_backend` does but harvests webcast URLs instead of downloading PDFs. Produces a bucketed markdown report.

Writes a single report at the end of the run (atomic; not incremental — known limitation).

Iteration during the session:
- **Noise filter** — dropped `DownloadICal.aspx`, `cts.businesswire.com/ct/` redirectors, social links, internal `event-details/` listings that pollute the `(unknown)` bucket.
- **`_SURVEY_BLOCKED_CANDIDATE_PATTERNS`** — skip `annual-report`, `/10-k`, `/proxy-statement`, `/governance`, `/sustainability`, `/esg/`, `/careers`, etc. before `page.goto`. Fixes KMB hang on `kimberly-clark.com/en-us/investors/annual-reports` where Playwright's goto blocked past its own timeout.
- **`max_candidates: 4 → 3`** — trims the low-signal tail of ranked candidates.
- **Tighter survey timeouts** — `page.goto` 30s → 15s, `time.sleep(2) → 1`, `set_default_navigation_timeout(15000)`.
- **`_find_earnings_event_link` wrapped in try/except** — inner `page.evaluate` scroll calls can hang; guard so the survey continues.
- **`python -u` + `line_buffering=True`** — forces live output through `tee`; 10+ min of buffered silence during earlier runs made hangs undiagnosable.
- **`socket.setdefaulttimeout(15)`** — caps yfinance's underlying socket hang (MNST stalled on IR-page walk for 10+ min with no output).

### 4. Survey results

Final run covered 32 tickers (MNST intentionally excluded after repeat hangs). Bucketed breakdown:

| Vendor | Tickers | Notes |
|---|---|---|
| `west_intrado` | 18 | `_sniff_west_intrado_hls` already exists — biggest audience |
| `q4_inc_attendee` | 11 | Needs a new sniffer module |
| `mediasite` | 7 | `_sniff_mediasite_hls` already exists; needs `--semi-auto` for CAPTCHA |
| `direct_audio` | 6 | No sniffer needed — just download |
| `veracast` | 2 | ADM, CHD — new sniffer |
| `open_exchange` | 1 | MO only — new sniffer |
| `(unknown)` | 20 | Same-domain landing pages that need one-hop follow |
| *(empty)* | 4 | DG, MKC, PM, WMT — investigated separately in section 5 |

Note: tickers overlap multiple buckets (e.g. PEP has `mediasite` + `west_intrado` + `(unknown)`). Dispatch by URL pattern handles this naturally.

### 5. Diagnosis of the 5 "empty" tickers

All 5 have webcasts — the survey just didn't reach them. Distinct failure modes:

| Ticker | Vendor | Root cause |
|---|---|---|
| MNST | `mediasite` + `cc.webcasts.com` | Playwright hung on MNST IR home SPA |
| MKC | `mediasite` + `west_intrado` | Akamai blocked Playwright HTTP/2 on `ir.mccormick.com` |
| DG | **`webcast-eqs.com`** + `west_intrado` | IR home had no keyword-matching nav; pages JS-rendered |
| PM | `mediasite` | Archive page is a listing — webcasts live on per-event detail pages |
| WMT | **`youtube.com/live/*`** | `stock.walmart.com` refuses connections; real events at `corporate.walmart.com/investors/events` |

Two **new vendors** surfaced: **EQS** (`webcast-eqs.com`, DG) and **YouTube Live** (WMT). YouTube Live is actually the easiest vendor possible — yt-dlp handles it trivially.

### 6. IR_URLS overrides added

In `consumer_staples_earnings.py`:
```python
"WMT":  "https://corporate.walmart.com/investors/events",
"PM":   "https://www.pmi.com/investor-relations/press-releases-and-events/events-archive/?offset=0&limit=50",
"MNST": "https://investors.monsterbevcorp.com/events-and-presentations",
"MKC":  "https://ir.mccormick.com/events",
"DG":   "https://investor.dollargeneral.com/events-presentations",
```
Plus TSN from the prior session (`ir.tyson.com/presentations/default.aspx`).

### 7. Vendor catalog extended

Added to `WEBCAST_VENDOR_PATTERNS`:
```python
"webcast_eqs":  ("webcast-eqs.com",),
"youtube_live": ("youtube.com/live/", "youtu.be/"),
```

### 8. `direct_audio` download path — fully wired

New helpers in scrape.py:
- `download_audio_file(url, dest, referer)` — raw MP3/M4A/WAV download via curl_cffi with `impersonate="chrome131"`.
- `_try_extract_audio_from_page(page, ticker, target_date, event_url, audio_dir)` — scans current page for webcast URLs, dispatches to vendor-specific downloaders.
- `_scan_and_download_audio(...)` — per-page scan + dispatch (internal helper of above).
- `_looks_like_audio_text(text, href)` — text-based audio hint for opaque URLs where only the anchor text reveals it's audio. Reference case: **KMB's Q4 Inc `/static-files/{uuid}` with link text "Pre-Recorded Management Discussion (Audio)"**. Without this, the MP3 was invisible to an extension-based classifier.
- `_audio_ext_from_response(url, referer)` — HEAD the URL, map Content-Type to file extension when href has no extension. Falls back to `mp3`.

False-positive guard: text-signal audio detection only fires when no known vendor matched OR vendor is `(unknown)`. Otherwise a Mediasite URL with "Listen to audio webcast" text would be wrongly treated as a direct download.

Tested end-to-end on **KMB**: 22MB MP3 on disk, valid MPEG-1 Layer 3 magic bytes (`FF FB`).

### 9. `youtube_live` download path — fully wired

- `download_youtube_audio(url, dest)` — shells out to `yt-dlp -x --audio-format m4a --no-playlist`.
- `yt-dlp` added as a dependency (`pip install yt-dlp`). Version 2026.3.17.
- Dispatched from `_scan_and_download_audio` when the URL matches `youtube.com/live/*` or `youtu.be/*`.

Tested end-to-end on **WMT**: 26MB WAV on disk, valid RIFF WAVE magic bytes. `-x --audio-format m4a` fell back to WAV when yt-dlp didn't convert — still a valid audio file that the `audio-transcription` skill accepts.

### 10. `west_intrado` audio dispatch — wired, sniffer needs fix

- `elif vendor == "west_intrado":` branch in `_scan_and_download_audio` — calls existing `_sniff_west_intrado_hls(page, href, timeout_s=30)`, pipes captured `.m3u8` URL through `download_hls_to_m4a` to produce `.m4a`.
- **Sniffer updated**: old code used `page.get_by_label(label, exact=False)` which fails on `event.webcasts.com`'s newer forms where field `name`/`id` values are obfuscated (hex hashes, rotate per event). Added type-based fallback fill: `input[type='text']:visible` positionally maps to First Name / Last Name / Company; `input[type='email']` → Email; `input[type='tel']` → `"5551234567"` (new — prior sniffer ignored the tel field).
- **Status: integration flow works** — drill-in from IR home to event-details page, webcast URL detected, sniffer called, registration form filled. **But form submission isn't producing an `.m3u8` request** for LW's test case. Unknown whether the block is CAPTCHA, required fields we don't fill, or archived-event access flow.

### 11. Two-pass audio extraction (drill-in)

IR-home fast-path tickers (LW, MKC, HSY) typically expose PDFs on the IR home but webcast links only on the sub-event page. Audio extraction is two-pass:

1. Scan the current page (where PDFs were just found).
2. If empty, find the first `/events/event-details/` URL on the page matching earnings keywords (and not announcement markers: `to-host`, `announces`, etc.). Navigate there. Scan again.

Fallback beyond the event-detail pattern: `_find_hop_url_from_hrefs` (news-release-detail patterns used by the PDF hop-follow).

### 12. Gap-skip logic updated

Old: `if has_transcript: continue` — skip ticker if any press-release PDF on disk. Rationale was "audio is vendor-specific, not worth re-running for covered tickers". Now that `generic_backend` handles `direct_audio` + `youtube_live` inline during the PDF walk, tickers with a transcript but no audio are worth re-running.

New: `if has_transcript and has_audio: continue` — skip only when fully covered.

### 13. Playwright stall debugging

Multiple full survey runs + partial ticker runs stalled in different places. Fixes layered:
- KMB annual-reports hang → URL blocklist
- MNST events page hang → explicit IR_URLS override (bypass auto-discovery)
- SYY post-skip stall → couldn't fully root-cause (may be yfinance socket hang; covered by socket.setdefaulttimeout)
- Buffered stdout hiding live progress → `-u` flag + `line_buffering=True`

Known unresolved: `page.evaluate(...)` can hang without respecting `set_default_timeout`. The `_find_earnings_event_link` helper does a `page.evaluate("window.scrollTo(...)")` that could block on misbehaving JS. Workaround is the try/except wrapper around the call; not a full fix.

## Current state

### Coverage

- **PDFs: 33/33** (unchanged from prior session).
- **Audio: 3/33** — PM (old), KMB (new this session via direct_audio), WMT (new this session via youtube_live). Calendar file reflects this.

### Infrastructure

- **scrape.py** ~1830 lines. New sections:
  - Webcast-vendor URL catalog + `classify_webcast_url` (~60 lines)
  - Webcast-URL survey (data classes, walker, report writer, orchestrator) (~270 lines)
  - Audio extraction helpers (`download_audio_file`, `download_youtube_audio`, `_scan_and_download_audio`, `_try_extract_audio_from_page`, `_looks_like_audio_text`, `_audio_ext_from_response`) (~200 lines)
  - West/Intrado sniffer updates (phase 2 type-based fill) (~40 lines)
- **`_socket.setdefaulttimeout(15)`** added at module level to cap yfinance hangs.
- **`yt-dlp`** (2026.3.17) installed as a new dependency.
- **consumer_staples_earnings.py**: 5 new IR_URLS overrides.
- **SKILL.md**: updated for 33/33 PDFs, pmi_backend removed, future vendor-module list refreshed.
- **Survey report**: `Brain\Knowledge\IR Webcast Vendor Survey.md` (may have been deleted during this session — regenerate with `python scrape.py --survey-webcasts`).
- **`_survey_run.log`**: live log from the last survey run (tee'd output).

### What's working end-to-end

- `direct_audio` path (KMB Q4 Inc pattern confirmed).
- `youtube_live` path (WMT confirmed).
- Two-pass audio extraction (drill-in from IR-home-fast-path to event-details).
- Audio-vendor dispatch from `_try_extract_from_event_url` after PDF extraction.
- Survey infrastructure (`--survey-webcasts` flag, vendor-bucketed report).

### What's wired but not producing audio

- `west_intrado` — sniffer form submission fails on LW's event. Covers 18 tickers once fixed.

### What's not yet built

- `q4_inc_attendee` sniffer (11 tickers)
- `mediasite` wiring — sniffer exists; needs dispatch branch + `--semi-auto` reachability
- `cc.webcasts.com` sniffer (MNST + others — similar shape to West/Intrado)
- `webcast_eqs` sniffer (DG at minimum)
- `veracast` sniffer (ADM, CHD)
- `open_exchange` sniffer (MO)

## Open decisions / pending work

### 1. Module refactor (deferred, plan finalized)

User asked about splitting scrape.py into multiple files because it's ~1830 lines. Decision: **defer until audio coverage stabilizes**, then do a single-package-multi-file split. The wrong boundary is PDF-vs-audio (both share ~900 lines of walker logic). The right boundary is:

```
C:\Users\rodin\.claude\skills\investor-relations-data-scraper\scripts\
  ir_walker.py       # Shared. IR resolution, candidate ranking, hop-follow,
                     #   quarter derivation, `_find_ir_page`, `_find_events_page`,
                     #   `_find_earnings_event_link`, `_try_common_ir_patterns`,
                     #   `_try_common_ir_subpaths`, `_derive_alt_roots`,
                     #   `_rank_link`, `_best_link`, `_ranked_candidates`,
                     #   `_HOP_*` constants, `_SURVEY_BLOCKED_CANDIDATE_PATTERNS`.
                     #   ~500-600 lines.
  pdf_extractor.py   # PDF-specific. `_collect_pdf_links`, `_extract_pdfs_from_html`,
                     #   `download_pdf`, HTML press-release rendering via `page.pdf()`,
                     #   `_try_extract_from_event_url` (the main per-page extractor).
                     #   ~400 lines.
  audio_extractor.py # Audio-specific. All vendor sniffers (`_sniff_mediasite_hls`,
                     #   `_sniff_west_intrado_hls`, future `_sniff_q4_inc_hls`,
                     #   `_sniff_veracast_hls`, etc.), `download_audio_file`,
                     #   `download_youtube_audio`, `download_hls_to_m4a`,
                     #   `_scan_and_download_audio`, `_try_extract_audio_from_page`,
                     #   `classify_webcast_url`, `WEBCAST_VENDOR_PATTERNS`,
                     #   `FAKE_REG_INFO`, `_WEBCAST_TEXT_HINTS`/`_WEBCAST_URL_HINTS`,
                     #   `_AUDIO_*` constants, survey functions.
                     #   ~500-600 lines.
  scrape.py          # Thin orchestrator (~150 lines). CLI parsing, browser setup,
                     #   `build_gap_list`, `generic_backend` reduced to a coordination
                     #   function that calls into pdf_extractor + audio_extractor,
                     #   gap report writer, transcription chain, `main()`.
```

**Why defer**: mid-discovery refactor = churn. Wait until we've built all vendor modules and know the final shape of `audio_extractor`. Estimated 2-3 hour refactor once triggered.

**When to trigger**: after audio coverage reaches 25+/33 (roughly: west_intrado sniffer fixed + mediasite wired + q4_inc_attendee built). That's the point where the audio workstream is stable enough to know what belongs in each module.

**Risks to manage during the refactor**:
- Circular imports (audio_extractor may want to call ir_walker helpers to do follow-hops — keep audio_extractor imports one-way from ir_walker).
- Shared state like `FAKE_REG_INFO`, `USER_AGENT` — decide whether they live in `scrape.py` (config module) or in the module that uses them.
- Survey mode imports across all three modules; may want a dedicated `survey.py` as a 5th file.

### 2. West/Intrado sniffer debugging

Form fills succeed (Phase 2 type-based fallback), submit button click executes, but no `.m3u8` request follows. Next investigation steps:
- Run sniffer with `--semi-auto` to see the rendered page at submit time. Check whether the form was actually accepted or whether validation errors appear.
- Monitor ALL network requests after submit (not just `.m3u8`) — the form may redirect to a registration-complete page that doesn't auto-play the replay.
- Check whether `event.webcasts.com` has added a reCAPTCHA or other bot check since the sniffer was originally written.
- Consider: some archived events require clicking a "View Replay" button after registration that isn't the auto-play trigger.

### 3. Mediasite wiring

`_sniff_mediasite_hls` is already in scrape.py. Needs:
- Dispatch branch in `_scan_and_download_audio` (trivial — follow the `west_intrado` pattern).
- `--semi-auto` plumbing through to the sniffer (already wired in function signature).
- Test with MNST (now has IR_URLS override) and MKC.

### 4. Q4 Inc attendee sniffer (11 tickers)

Need to build from scratch. Reference URL pattern: `events.q4inc.com/attendee/{id}`. Next session tasks:
- Probe one of the 11 tickers' webcast URL (COST, TSN, etc.) to see Q4 Inc's player layout.
- Determine registration flow (if any) + HLS URL pattern.
- Model after `_sniff_west_intrado_hls` structure.

### 5. MNST remaining issue

MNST was excluded from the final survey run due to repeat Playwright hangs on its IR home. With the IR_URLS override now pointing at `investors.monsterbevcorp.com/events-and-presentations` directly, the next run should reach it. But the MNST IR home SPA hang risk remains for any code path that re-navigates to the IR home. Watch for regressions.

### 6. Direct-audio handling beyond event-details

The current `_try_extract_audio_from_page` only runs from `_try_extract_from_event_url` which is called on event-detail pages. If a direct audio link lives somewhere else (e.g. on the IR home that didn't yield PDFs and fell through to the candidate walk), it'd be missed. Low priority — haven't seen a case yet.

### 7. WMT WAV vs M4A

yt-dlp `--audio-format m4a` fell back to WAV (requires ffmpeg). File is valid and transcribable. Optional: verify ffmpeg is on PATH; force m4a output more reliably. Cosmetic.

### 8. Survey report lifecycle

`IR Webcast Vendor Survey.md` at `Brain\Knowledge\` may have been lost during the session (couldn't locate it at end of session). Regenerate with `python scrape.py --survey-webcasts` as needed. Consider committing to disk from multiple runs (append mode) instead of atomic-overwrite.

## Key file paths

| Purpose | Path |
|---|---|
| Scraper entry point (CLI + orchestrator + survey + audio dispatch) | `C:\Users\rodin\.claude\skills\investor-relations-data-scraper\scripts\scrape.py` |
| Skill definition | `C:\Users\rodin\.claude\skills\investor-relations-data-scraper\SKILL.md` |
| Calendar generator + IR_URLS overrides | `C:\Users\rodin\.claude\scripts\investor-relations-data-scraper\consumer_staples_earnings.py` |
| Task-Scheduler `.bat` | `C:\Users\rodin\.claude\scripts\investor-relations-data-scraper\run_consumer_staples_earnings.bat` |
| Calendar output | `C:\Users\rodin\Desktop\Brain\Knowledge\Consumer Staples Earnings Calendar.md` |
| Gap report | `C:\Users\rodin\Desktop\Brain\Knowledge\IR Scraper Gap Report.md` |
| Webcast vendor survey | `C:\Users\rodin\Desktop\Brain\Knowledge\IR Webcast Vendor Survey.md` (regenerate if missing) |
| Live survey log | `C:\Users\rodin\Desktop\Brain\Knowledge\_survey_run.log` |
| Per-ticker sources | `C:\Users\rodin\Desktop\Brain\Sources\{TICKER}\{QUARTER}\{audio\|presentation\|transcripts}\` |
| Scheduled task name | `Consumer Staples Earnings Weekly` |
| This session's handoff | `C:\Users\rodin\Desktop\Brain\Sessions\Transcript Scraping & Consolidation\April 21st Audio Extraction Session.md` |
| Prior handoffs in this task | `Brain\Sessions\Transcript Scraping & Consolidation\April 18th...`, `April 20th IR Scraper v1...`, `April 20th IR Scraper Generic Backend...`, `April 21st IR-Home Fast-Path...` |

## How to run

```bash
# Full gap-filling run (walks all tickers with missing PDFs or missing audio)
python "C:\Users\rodin\.claude\skills\investor-relations-data-scraper\scripts\scrape.py"

# One ticker only (testing)
python "C:\Users\rodin\.claude\skills\investor-relations-data-scraper\scripts\scrape.py" --tickers KMB --no-transcribe

# Regenerate the webcast vendor survey
python "C:\Users\rodin\.claude\skills\investor-relations-data-scraper\scripts\scrape.py" --survey-webcasts

# Headed browser + pause for CAPTCHA (for mediasite tickers once wired)
python "C:\Users\rodin\.claude\skills\investor-relations-data-scraper\scripts\scrape.py" --semi-auto

# Live log through tee (Python unbuffered for live visibility)
python -u "C:\...\scrape.py" 2>&1 | tee "C:\Users\rodin\Desktop\Brain\Knowledge\_run.log"
```

---

## How to create the next handoff

At the end of every session, write a new handoff under `C:\Users\rodin\Desktop\Brain\Sessions\{Task-Theme}\` following the exact structure below. This keeps every future "cold start" predictable — the next session picks up one file and knows everything it needs.

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
