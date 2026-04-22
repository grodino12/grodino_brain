---
type: session-handoff
date: 2026-04-22
topic: event-pump fix + mediasite dropdown + q4_inc + choruscall + iframe scan + per-quarter IR overrides → audio 3/33 → 26/33
tags: [session, consumer-staples, earnings, scraper, audio, playwright, event-loop, q4-inc, choruscall, youtube-embed]
---

# April 21st — Event Pump Bug Session

Picks up where `April 21st Audio Extraction Session.md` left off (PDFs 33/33; audio 3/33; west_intrado sniffer "form submits but no m3u8" bug outstanding).

## Starting state

- PDFs: 33/33.
- Audio: 3/33 (PM, KMB, WMT).
- Code state: `_sniff_west_intrado_hls` existed, dispatched from `_scan_and_download_audio`. Form-fill Phase 1 + Phase 2 logic working. Submit click working (POST to `proc_register.jsp` confirmed in earlier session). But the wait loop returned `None` every run on LW's event — m3u8 never captured.

## Work done this session

### 1. Diagnosed west_intrado sniffer bug — root cause: `time.sleep` doesn't pump Playwright's sync event queue

The sniffer returned `None` consistently even though the registration POST succeeded. Initial hypotheses (reCAPTCHA, headless detection, bot-speed rate limiting) were all wrong. Built `debug_west_intrado.py` + `debug_prod_sniffer.py` to trace step-by-step.

**Key diagnostic:** ran the same sniffer flow two ways:
- Standalone `debug_west_intrado.py`: m3u8 captured at t+30s post-click → SUCCESS.
- Production `_sniff_west_intrado_hls`: m3u8 arrived at t+33s but the wait loop's 30s deadline fired first → returned `None`.
- Bumped timeout to 90s — still returned `None`. But the `[nav]` print on `framenavigated` showed `landing.jsp` → `event.jsp` transitions appearing *after* the function returned, and m3u8 capture logged at t+93s.

**Root cause:** In Playwright's **sync** API, `time.sleep()` does not yield control to the underlying event pump. The browser-side network events + `on_request` callbacks queue up but never dispatch. They only flush when the Python code calls a Playwright method (e.g. `page.url`, `page.evaluate`, `page.wait_for_timeout`).

The production wait loop was:
```python
while time.time() < deadline:
    if captured["url"]:
        break
    time.sleep(0.5)  # <-- never pumps events
```

The original `debug_west_intrado.py` accidentally worked because its loop called `page.url` on each iteration — that round-trip to the browser pumps events. Bumping timeout to 90s still failed because the loop never pumps events at all.

**Fix:** replace `time.sleep(0.5)` with `page.wait_for_timeout(500)` in both `_sniff_west_intrado_hls` and `_sniff_mediasite_hls`. `page.wait_for_timeout` is an async-aware sleep that yields to Playwright's event queue.

```python
# west_intrado sniffer — line ~370
while time.time() < deadline:
    if captured["url"]:
        break
    page.wait_for_timeout(500)  # was time.sleep(0.5)
return captured["url"]
```

**Diagnostic insight to preserve for future sync-Playwright code:** any loop that waits for a `page.on(...)` callback to fire MUST call a Playwright method inside the loop (not just `time.sleep`). Otherwise callbacks never dispatch.

### 2. Timeout bumped 30s → 60s default / 90s at callsite

West/Intrado's archived-event flow consistently takes ~30s from submit click to first `.m3u8` request (POST proc_register.jsp → landing.jsp POST → event.jsp → Bitmovin player init → HLS manifest fetch). 25s default was too tight — `_sniff_west_intrado_hls` default raised to `timeout_s=60`, and the dispatch callsite calls it with `timeout_s=90`. Notes documented in the docstring.

### 3. Mediasite dispatch wired

`_sniff_mediasite_hls` already existed; added a vendor dispatch branch in `_scan_and_download_audio` modeled after `west_intrado`. Threaded `semi_auto` through `_try_extract_audio_from_page` → `_scan_and_download_audio` → `_sniff_mediasite_hls`. The auto (non-semi) path fills firstname/lastname/email/institution + selects Investor Type via label text, then clicks submit. Works for some events; fails on reCAPTCHA-gated ones.

Same event-pump fix (`page.wait_for_timeout` instead of `time.sleep`) applied to mediasite's wait loop.

### 4. Per-page failed-vendor dedupe

IR pages commonly link the same webcast vendor multiple times (sidebar + inline player + footer, or multiple recording angles). First batch run wasted 10+ minutes on PEP trying 5 different mediasite URLs all gated by the same reCAPTCHA. Added a `failed_vendors: set[str]` dedupe inside `_scan_and_download_audio`: once any attempt for a vendor fails on a given page, skip subsequent links for that vendor.

```python
# _scan_and_download_audio
failed_vendors: set[str] = set()
...
if vendor in failed_vendors:
    continue
...
if not hls_url:
    failed_vendors.add(vendor)
    continue
```

This DOES reset on drill-in (new `_scan_and_download_audio` call with fresh set), which is intentional — a different page may legitimately have a working link for the same vendor.

### 5. Context-level timeouts to prevent MNST-like hangs

Survey mode already did `page.set_default_timeout(15000)` + `page.set_default_navigation_timeout(15000)`. The main scrape path didn't — MNST hung for 3+ hours on its IR SPA during the first batch run (last file write 16:33, discovered 19:43).

Fix: set these on the `BrowserContext` (not per-page) so every new page inherits. Chose 30s since the main path has multi-step work per ticker.

```python
ctx = browser.new_context(user_agent=USER_AGENT)
ctx.set_default_timeout(30000)
ctx.set_default_navigation_timeout(30000)
```

### 6. Batch scrape results (first wave)

Ran `scrape.py --no-transcribe` in two batches (first stopped after PEP's 10-min mediasite thrash before dedupe; second covered remaining 14 tickers after MNST was explicitly excluded via `--tickers` filter).

**Audio wins first wave (10 new):**
- `direct_audio`: KO, GIS, SJM
- `west_intrado`: LW (test), PG, MO, HSY, CELH, BF-B, HRL

### 7. Mediasite placeholder-option fix

Dropdown logic was picking the first non-empty `<option>`, which on Mediasite's Country + Investor Type dropdowns was a placeholder like `"...................."`. Angular's form validation rejected that, so the submit button stayed `aria-disabled="true"`. Added `_is_placeholder_option(text, opt)`:
- Skip options with `disabled` attribute
- Skip options with empty `value` attribute
- Skip options whose text has no alphanumerics (dots, dashes, whitespace)
- Skip options starting with "Select", "Choose", "Please", "Pick one", "- -"

After fix: PEP picks "Afghanistan" (Country) + "Sell-side analyst" (Investor Type), submit button enables, form submits. But still no m3u8 — reCAPTCHA blocks PEP/MDLZ/CLX. Auto mode still useful on events without reCAPTCHA; `--semi-auto` needed for the rest.

### 8. Q4 Inc attendee sniffer — NEW

Biggest bucket (~11 tickers). Probed `events.q4inc.com/attendee/{id}` directly. Discovered flow:

1. React SPA at `/attendee/{event_id}`. Registration gate: 3 buttons (`#registration-box_signup-button` / `_guest-button` / `_login-button`). Click `#registration-box_login-button` ("Continue without a Q4 account").
2. Navigates to `/attendee/{event_id}/guest`. Guest form:
   - `#GuestRegistrationFirstNameInput` / `LastNameInput` / `EmailInput` (text)
   - `#GuestRegistrationInvestorCheckboxInput` ("I am an individual attendee") — **critical**: custom component, `input.check()` times out. Click via `label:has-text('I am an individual attendee')` with `force=True`. Setting this removes the Institution/Company requirement (which is an autocomplete combobox we can't satisfy via plain fill).
   - `#GuestRegistrationSubmitButton` ("Register for this Event")
3. Post-submit: player loads, recording arrives at `https://static.events.q4inc.com/edited-recordings/{event_id}/{uuid}.mp4`. **Direct MP4**. No HLS, no reCAPTCHA. Download via `download_audio_file` (curl_cffi).

Reference: validated on TSN attendee/891408037 (Feb 5 Annual Meeting — past event, has recording). COST attendee/247600739 returns no media because it's May 28 Q3 2026 (future event) — the sniffer correctly returns None for future events.

New helper: `_sniff_q4_inc_mp4(page, webcast_url, timeout_s=60)`. Dispatch branch added to `_scan_and_download_audio` before the mediasite branch.

### 9. Per-event-vs-systemic dedupe split

The `failed_vendors` dedupe from §4 was too aggressive for Q4 Inc. TSN's IR page lists 3 q4_inc URLs (Q1 past, Q2 future, annual meeting past). The Q2 future event has no recording; the Q1 past one does. Original dedupe blocked the Q1 attempt after Q2 failed.

Introduced `_DEDUPE_ON_VENDOR_FAILURE = {"mediasite", "veracast", "open_exchange", "webcast_eqs"}` — only dedupe vendors where failures are systemic (reCAPTCHA, form gating that applies identically to all events). Excluded: `q4_inc_attendee`, `west_intrado` — each URL is a distinct event with independent state.

After fix: TSN tries `/759959591` (future, fails), then `/891408037` (past, succeeds → MP4 downloaded).

### 10. Batch scrape results (second wave — q4_inc + dedupe fixes)

Re-ran 18 remaining gap tickers (ex-MNST). Q4 Inc sniffer unlocked 4 additional tickers:
- `q4_inc_attendee`: TSN, ADM, KR, COST

**Total audio wins this session (14 new):**
- `direct_audio` (3): KO, GIS, SJM
- `west_intrado` (7): LW (test), PG, MO, HSY, CELH, BF-B, HRL
- `q4_inc_attendee` (4): TSN, ADM, KR, COST

**Final coverage: audio 17/33, transcripts 31/33, PDFs (latest) 33/33.**

### 11. MNST still hangs — context timeout not enough

After §5, re-ran `--tickers MNST` in isolation. Still hung 15+ min past the `[generic] start=...` line with no further output. Context-level `ctx.set_default_timeout(30000)` applies to individual Playwright page calls but apparently doesn't catch whatever MNST's SPA is doing (possibly a page.evaluate inside a helper that doesn't honor context defaults, or something at the yfinance / curl_cffi layer). Needs deeper tracing next session. Current workaround: always pass `--tickers <without-MNST>` to avoid locking the batch.

### 12. Multi-candidate audio walk refactor

Initial candidate walk logic returned early on the first candidate that yielded *any* PDFs, skipping later candidates that might host the webcast link. Refactored to:
  - Accumulate artifacts instead of returning early.
  - After finding PDFs, keep walking candidates — but skip the full PDF+audio extractor; just do `_try_extract_audio_from_page` (audio-only scan) since we already have PDFs.
  - Return only when we have both PDFs and audio.
  - Added a post-IR-home-fast-path audio walk symmetrically — if IR home yields PDFs but no audio, scan candidates audio-only.
  - Added a no-PDF-anywhere audio-only fallback at the end of the candidate walk — unblocks tickers whose events calendar doesn't host classifiable PDFs (CAG, SYY).

This fix unlocked CAG, CHD (past-event Q4 on events-and-presentations sub-page), and more.

### 13. ChorusCall sniffer — NEW

STZ's webcast turned out to be `event.choruscall.com/mediaframe/webcast.html?webcastid=qgIohQED`, a vendor we hadn't catalogued. Probed directly:

- Form inputs: `#firstName` / `#lastName` / `#email` / `#company` (no obfuscation)
- Button: `#registrationSubmit` (value "Submit")
- **No reCAPTCHA**
- Media URL pattern: `https://vodchoruscall.akamaized.net/{account}/{slug}/{eventid}.mp4` — **direct MP4**

Built `_sniff_choruscall_mp4(page, webcast_url, timeout_s=60)`. Added `choruscall` to `WEBCAST_VENDOR_PATTERNS` matching `event.choruscall.com/mediaframe` + `services.choruscall.com/mediaframe`. Dispatch branch placed before `q4_inc_attendee` in `_scan_and_download_audio`.

Unlocked STZ + SYY this session. Other tickers with ChorusCall in survey (BG) already got audio via direct_audio, so ChorusCall wasn't needed there.

### 14. Final session batch runs

Cumulative audio wins from all batch runs this session (**20 new tickers, 3 → 23**):
- `direct_audio` (4): KO, GIS, SJM, BG
- `west_intrado` (9): LW, PG, MO, HSY, CELH, BF-B, HRL, CAG, CLX
- `q4_inc_attendee` (5): TSN, ADM, KR, COST, CHD
- `choruscall` (2): STZ, SYY

### 15. User-guided probing unlocked CL + TGT + EL

User flagged via screenshots: CL's webcasts live at `investor.colgatepalmolive.com/events-and-webcasts`, TGT uses a YouTube iframe on event-details pages, EL's webcasts are on `elcompanies.com/en/investors/events-and-presentations`. Probed each:

- **EL**: Q2 Fiscal 2026 earnings IS on `event.choruscall.com/mediaframe/webcast.html?webcastid=kv9nzVwN`. Scraper just hadn't tried it before (ChorusCall was added after the initial EL run). Zero code change — just re-ran.
- **TGT**: iframe `<iframe src="https://www.youtube.com/embed/muSby1cblaw?rel=0">` on the event-details page. Required: (a) extending `_scan_and_download_audio` to scan `iframe[src]` in addition to `a[href]`, (b) extending `youtube_live` vendor pattern to match `youtube.com/embed/` + `youtube.com/watch` + `youtube-nocookie.com/embed/`, (c) IR_URLS override pointing directly at the quarterly `event-details-MM-DD-YY` URL (the index page doesn't surface it). yt-dlp downloads as m4a.
- **CL**: ChorusCall (`webcastid=s8h4YO2M`) on intermediate notice page `investor.colgatepalmolive.com/notice-q4-2025-earnings-webcast`. ChorusCall sniffer had to be extended to fill `select#udef1` (Investor Type dropdown — uses the same `_is_placeholder_option` helper built for mediasite). IR_URLS override pointed directly at the notice page.

### 16. IR Audio Source Map documented

Per-ticker map saved at `Brain\Knowledge\IR Audio Source Map.md` — maps each of the 33 tickers to its vendor + landing URL + notes. Also contains a vendor playbook and "how to add a new ticker" section. This is the authoritative reference for future quarterly runs: if a vendor is known-working, just run the scraper; if survey shows an unbuilt vendor, build a sniffer using ChorusCall as the simplest template.

## Current state

### Coverage

- **PDFs: 33/33** (unchanged).
- **Audio: 26/33** — up from 3/33:
  - From prior sessions: PM, KMB, WMT.
  - New this session: LW, PG, KO, MO, GIS, HSY, CELH, SJM, BF-B, HRL, TSN, ADM, KR, COST, CAG, BG, CHD, CLX, STZ, SYY, CL, TGT, EL.
- Still missing audio (7 tickers): PEP, MDLZ, KDP, DLTR, MKC (mediasite reCAPTCHA — `--semi-auto`), DG (webcast_eqs login flow incomplete), MNST (SPA hang).

### Infrastructure changes

- **scrape.py** ~2150 lines. Changes:
  - Event-pump fix (`page.wait_for_timeout` replacing `time.sleep`) in both sniffer wait loops.
  - `_sniff_west_intrado_hls` timeout default 25 → 60, callsite 30 → 90.
  - `_scan_and_download_audio` gained `semi_auto` param + per-page `failed_vendors` dedupe + mediasite dispatch + **q4_inc_attendee dispatch**.
  - `_try_extract_audio_from_page` passes `semi_auto` through.
  - `generic_backend` calls `_try_extract_audio_from_page(..., semi_auto=semi_auto)`.
  - `main()` sets `ctx.set_default_timeout(30000)` + nav variant on the BrowserContext.
  - New helper `_is_placeholder_option(text, opt)` — skips "...", "Select...", etc. when filling mediasite dropdowns.
  - New sniffer `_sniff_q4_inc_mp4(page, webcast_url, timeout_s=60)`.
  - New constant `_DEDUPE_ON_VENDOR_FAILURE = {mediasite, veracast, open_exchange, webcast_eqs}` — vendors to skip on first fail. q4_inc_attendee and west_intrado explicitly excluded.
- **Debug scripts written + deleted** (`debug_west_intrado.py`, `debug_prod_sniffer.py`, `debug_q4_inc.py`): kept in conversation context, removed from disk after diagnosis. Screenshots at `Brain\Knowledge\_q4_debug\` also removed.

## Open decisions / pending work

### 1. MNST still hangs on IR SPA — needs specific investigation

The IR_URLS override (`investors.monsterbevcorp.com/events-and-presentations`) set last session did not prevent the hang; first batch ran 3+ hours on it before we killed it. The new context-level `set_default_timeout(30000)` should now cap individual operations at 30s. Next session: run `--tickers MNST` alone and inspect which operation actually stalls within `generic_backend`. Likely culprit: `_ranked_candidates` or `_find_earnings_event_link` doing a `page.evaluate` that the SPA's JS deadlocks.

### 2. Mediasite reCAPTCHA — needs `--semi-auto` run (5 tickers)

Dropdown placeholder fix resolved the `aria-disabled` issue. PEP/MDLZ/KDP/DLTR/MKC form submit executes, but still no m3u8 — reCAPTCHA blocks the path. Action:
```
python scrape.py --semi-auto --tickers PEP,MDLZ,KDP,DLTR,MKC
```
User sits with headed browser, solves each reCAPTCHA manually, sniffer captures HLS and continues. Each takes ~30s of human time. **Highest-priority pending action**.

### 3. DG — webcast_eqs sniffer needs finishing (1 ticker)

DG's current Q4 2025 earnings call is on `www.webcast-eqs.com/dollargeneralq42025`. Form is trivial: single `input[name='username']` for email + submit. Filled + submitted in probe, but post-submit URL stayed at `/login/` (may need longer wait, may need email confirmation step, may be gated by event date). Unblocks DG once done. Note: `webcast-eqs.com` (current) ≠ `webcasts.eqs.com` (dead / redirected). Vendor catalog entry `webcast_eqs` currently points at `webcast-eqs.com` only.

### 4. CL, TGT, EL — unknown-vendor investigation (3 tickers)

- **CL**: IR pages all show only `(unknown)` URLs. `investor.colgatepalmolive.com/news-releases/news-release-details/colgate-palmolive-webcasts-2026-first-quarter-earnings` was the title of the drill-in target but the page had no webcast link. Colgate may stream only live (no replay) or host the webcast on a sub-page we didn't reach. Worth manually loading `investor.colgatepalmolive.com/events` in a browser on earnings day.
- **TGT**: only 1 candidate URL surveyed (`corporate.target.com/investors/financial-information`). Target's earnings-day page may gate audio behind a sign-up form not visible to anonymous browsers, OR the call is hosted on a conferencing URL not indexed on the IR site.
- **EL**: `elcompanies.com/en/investors/events-and-presentations` has 3 west_intrado event URLs all with `tp_special=8`. Sniffer runs but captures no m3u8 on any of them. May be recordings expired, may be a `tp_special=8` variant that gates replay access differently. Worth one-off probe with headed browser to see what register-submit actually does.

### 5. MNST SPA hang (1 ticker)

Separate from vendor issues. Context-level timeout didn't help. Needs deeper Playwright tracing (possibly `page.on('load')` + `page.on('domcontentloaded')` listeners) to pinpoint where it stalls. Or switch to `curl_cffi` + HTML parsing for MNST's page and skip Playwright entirely.

### 5. Veracast (ADM, CHD) + Open Exchange (MO via different path) + EQS (DG) sniffers unbuilt

Minor buckets from the survey. Defer until bigger wins (Q4 Inc) are complete.

### 6. Module refactor (carried forward)

scrape.py now ~2050 lines. Defer refactor until audio coverage stabilizes at ~25+/33. Same plan as prior handoff: `ir_walker.py` / `pdf_extractor.py` / `audio_extractor.py` / thin `scrape.py` orchestrator.

### 7. Transcription pass

13 audio files now on disk; only PM has been transcribed historically. Consider running `python scrape.py --no-transcribe` (already done) then a separate pass to transcribe the 12 new files: the audio-transcription skill can be invoked per-file, or the scraper's `--no-transcribe` absence will pick them up but re-runs everything.

## Key file paths

| Purpose | Path |
|---|---|
| Scraper entry point | `C:\Users\rodin\.claude\skills\investor-relations-data-scraper\scripts\scrape.py` |
| Skill definition | `C:\Users\rodin\.claude\skills\investor-relations-data-scraper\SKILL.md` |
| Calendar generator + IR_URLS | `C:\Users\rodin\.claude\scripts\investor-relations-data-scraper\consumer_staples_earnings.py` |
| Calendar output | `C:\Users\rodin\Desktop\Brain\Knowledge\Consumer Staples Earnings Calendar.md` |
| Gap report | `C:\Users\rodin\Desktop\Brain\Knowledge\IR Scraper Gap Report.md` |
| Live scrape log (most recent) | `C:\Users\rodin\Desktop\Brain\Knowledge\_scrape_run.log` |
| Per-ticker sources | `C:\Users\rodin\Desktop\Brain\Sources\{TICKER}\{QUARTER}\{audio\|presentation\|transcripts}\` |
| Scheduled task | `Consumer Staples Earnings Weekly` |
| This handoff | `C:\Users\rodin\Desktop\Brain\Sessions\Transcript Scraping & Consolidation\April 21st Event Pump Bug Session.md` |
| Prior handoffs | `Brain\Sessions\Transcript Scraping & Consolidation\April 18th...`, `April 20th IR Scraper v1...`, `April 20th IR Scraper Generic Backend...`, `April 21st IR-Home Fast-Path...`, `April 21st Audio Extraction...` |

## How to run

```bash
# Full gap-filling run (all tickers with missing audio/PDFs)
python "C:\Users\rodin\.claude\skills\investor-relations-data-scraper\scripts\scrape.py"

# Skip MNST explicitly (until its SPA hang is solved)
python "C:\Users\rodin\.claude\skills\investor-relations-data-scraper\scripts\scrape.py" \
    --tickers COST,PEP,MDLZ,CL,TGT,SYY,KR,STZ,KDP,EL,TSN,ADM,CHD,CAG,CLX,MKC,BG,DLTR,DG

# Mediasite tickers with manual reCAPTCHA
python "C:\...\scrape.py" --semi-auto --tickers PEP,MDLZ,CLX

# Regenerate webcast vendor survey
python "C:\...\scrape.py" --survey-webcasts

# Live log through tee
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
