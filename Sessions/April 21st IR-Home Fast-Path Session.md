---
type: session-handoff
date: 2026-04-21
topic: IR-home fast-path + curl_cffi-on-Playwright-failure — coverage 23/33 → 26/33 (79%)
tags: [session, consumer-staples, earnings, scraper, generic-backend, ir-home-pattern]
---

# April 21st — IR-Home Fast-Path Session

Picks up where `April 20th IR Scraper Generic Backend Session.md` left off (23/33 tickers covered, 10 uncovered).

## Starting state

Per the 4/20 handoff:
- 23/33 tickers (70%) covered via `pmi_backend` (PM) + `generic_backend` (everything else).
- 10 uncovered, split into two buckets:
  - **Stage 2 "no earnings link matched on candidate pages" (5)**: CL, KMB, MNST, MKC, LW
  - **Stage 3 "candidates resolved to event URLs but no PDFs classified" (5)**: COST, MO, HSY, TSN, DG
- `generic_backend` had a 7-step pipeline with Playwright + curl_cffi fallback for Akamai-blocked static-file hosts, but the curl_cffi fallback only fired when Playwright *successfully* rendered a page with empty PDFs — not when `page.goto()` itself failed.

## Work done this session

### 1. LW's IR-home pattern — the trigger for this session

User pointed at `https://investors.lambweston.com/`. Probing the HTML showed LW's Drupal-based IR landing exposes the latest quarter's artifacts directly on the home page as `/static-files/{uuid}` links:
- `[Earnings Presentation] -> /static-files/a8a54519-...`
- `[Press Release] -> /static-files/9f03ff19-...`
- `[Financial Schedules] -> /static-files/ff3d9c28-...` (not classifier-matched; supplementary)

User asked to generalize this pattern for all remaining-uncovered tickers: "check for it in this location for all tickers where we are still missing transcripts". MKC and HSY turned out to use the same pattern.

### 2. Added IR-home fast-path to `generic_backend`

Inserted a pre-candidate-walk step: call `_try_extract_from_event_url(ir)` directly on the resolved IR home URL before falling through to the ranked sub-navigation candidate walk. If the IR home has classifiable PDFs, we return in one hop with `note="via generic_backend (IR-home direct)"`.

Previously `ir` was appended to `candidates` at the end and only reached as a last resort. The fast-path inverts that priority because CMS widgets on IR home pages auto-update to point at the latest quarter — when present, they're authoritative.

Also added a `continue` guard in the candidate walk so `ir` isn't retried after the fast-path.

### 3. Curl_cffi fallback when Playwright `page.goto()` fails

The initial LW test revealed `ERR_HTTP2_PROTOCOL_ERROR` on `https://investors.lambweston.com/` — same Akamai HTTP/2 issue as `gcs-web.com`. The existing curl_cffi fallback only triggered after a successful `page.goto()` returned empty PDFs — not on navigation failure.

Extended the `except Exception as e` block in `_try_extract_from_event_url`:
- If the event URL responds 200 via curl_cffi with Chrome131 impersonation, parse its HTML and run `_extract_pdfs_from_html`.
- On non-empty result: download and return.

This unlocked LW (presentation + press_release) on the next run.

### 4. `_extract_pdfs_from_html` now returns `(pdfs, all_hrefs)`

Refactored from `dict[str, str]` to `tuple[dict[str, str], list[str]]`. All 3 callsites updated to unpack. The hrefs list feeds two new capabilities: quarter derivation and curl_cffi-based hop-follow.

### 5. Quarter-label derivation from page links (`_derive_quarter_from_links`)

Problem after step 2-3: LW's fast-path used the IR home URL for quarter parsing — `cse.parse_quarter_label("https://investors.lambweston.com/", "2026-04-01")` returns the date fallback `"2026-04-01"` because the URL has no quarter info. Artifacts landed in `Brain/Sources/LW/2026-04-01/` instead of `Brain/Sources/LW/2026-Q3/`.

Added `_derive_quarter_from_links(hrefs, target_date)`: scans a list of hrefs and returns the first one that `parse_quarter_label` can parse as `YYYY-QN`. LW's IR home links out to `/events/event-details/fiscal-2026-third-quarter-earnings-call` — that parses cleanly as `2026-Q3`.

Integrated into:
- The Playwright-failure curl_cffi branch (uses hrefs returned by `_extract_pdfs_from_html`)
- The end-of-function quarter re-derivation step (falls back to link scan when event_detail_url yields the date fallback)
- The Playwright-success path (collects hrefs via `page.eval_on_selector_all` before the fallback ladder so HSY-style direct-classify paths also benefit)

Verified LW → `2026-Q3`, MKC → `2026-Q1`. HSY stays at `2026-02-05` because its IR home doesn't expose any link with quarter info — not a regression, just a gap.

### 6. Curl_cffi hop-follow (new)

Added module-level constants `_HOP_DETAIL_PATTERNS`, `_HOP_ANNOUNCE_PATTERNS`, `_HOP_EARNINGS_KWS` plus helper `_find_hop_url_from_hrefs(hrefs, current_url)` — URL-only version of the existing Playwright hop-follow.

Wired into the Playwright-failure curl_cffi branch: after direct-PDF fallback returns empty, scan the collected hrefs for a press-release-detail URL matching earnings keywords (skipping announcement posts). If found, fetch it via curl_cffi and classify PDFs on the hop target. Previously hop-follow only worked in the Playwright-success path.

Tested on MNST: the hop-follow correctly identified `https://investors.monsterbevcorp.com/news-releases/news-release-details/monster-beverage-reports-2025-fourth-quarter-and-full-year` from the IR home. But the hop target's own page then didn't yield classifiable PDFs — MNST's news-release-details page doesn't expose `/static-files/` or `.pdf` links the classifier recognizes. Still uncovered; needs a site-specific probe.

### 7. SKILL.md updated

Documented in §Pipeline:
- Step 4: IR-home fast-path (before candidate walk)
- Step 6's Playwright-failure curl_cffi fallback
- Step 8: new quarter-derivation step using `_derive_quarter_from_links`

## Current state

### Coverage: 26/33 (79%), +3 vs. session start

New artifacts this session:

| Ticker | Folder | Artifacts |
|---|---|---|
| LW | 2026-Q3 | presentation + press_release |
| MKC | 2026-Q1 | presentation + transcript |
| HSY | 2026-02-05 | press_release |

Existing coverage unchanged (23 prior tickers).

### 7 tickers still uncovered

- **CL** — Playwright ERR_HTTP2. IR home has `/static-files/` links but they're Annual Report / Proxy Statement / SEC filings, not labeled as earnings artifacts. No hop-follow target on the home page.
- **KMB** — Playwright ERR_HTTP2. IR home has `/events/event-details/first-quarter-2026-earnings` URL that WOULD match `_url_is_earnings_event` if we could make it a candidate — but `_ranked_candidates` returns empty after the Playwright failure, so that URL never enters the walk. Needs curl_cffi-based candidate enumeration.
- **MNST** — Curl_cffi hop-follow works; detail page at `/news-releases/news-release-details/...` doesn't yield classifiable PDFs. Needs site-specific probe of the detail page structure (what PDF URL pattern does it use?).
- **COST** — Q4 Inc tenant behind Cloudflare bot protection; needs JSON API reverse-engineering (same as prior session).
- **MO** — Hop-follow keeps latching onto "Altria Declares Regular Quarterly Dividend" because that contains "quarterly" in the text. Needs tighter earnings vs. dividend discrimination or pagination/scroll into the archive.
- **TSN** — Minimalist 55KB IR home, zero earnings-ish links visible. Heavy JS SPA; curl_cffi doesn't see the real content.
- **DG** — 2KB IR home HTML (likely a redirect or shell). Needs direct archive URL or Playwright-with-long-wait for SPA hydration.

### Infrastructure

- **SKILL.md** updated with new pipeline steps.
- **`scrape.py`** ~1120 lines now. Key new helpers: `_derive_quarter_from_links`, `_find_hop_url_from_hrefs`, plus module-level constants `_HOP_DETAIL_PATTERNS`, `_HOP_ANNOUNCE_PATTERNS`, `_HOP_EARNINGS_KWS`.
- `_extract_pdfs_from_html` now returns `tuple[dict, list]` — breaking change propagated to all 3 callsites.

## Open decisions / pending work

1. **Curl_cffi-based candidate enumeration.** When Playwright `page.goto(ir)` fails, `_ranked_candidates(page, ...)` returns [] because the page never loaded. The IR URL gets appended as sole candidate. For KMB (home links `/events/event-details/first-quarter-2026-earnings`) and MNST (home links `/news-releases/news-release-details/...`), enumerating candidates from curl_cffi HTML would give the walk real work to do. Highest-leverage next fix — likely unlocks KMB, MNST, possibly CL.
2. **MNST news-release-details PDF classifier.** The hop-follow reaches the right page but finds nothing classifiable. Need to `curl_cffi` that URL manually and see what PDF link pattern Monster uses — likely `/static-files/` on the same domain, but the classifier may need a tweak.
3. **MO earnings-vs-dividend discrimination.** "Altria Declares Regular Quarterly Dividend" contains "quarterly" so passes the earnings keyword filter, and the announcement filter doesn't catch "Declares". Options: add `declares-regular` / `dividend` to the ANNOUNCE list (risky — could exclude real dividend-related earnings releases); or require the title contain "results" / "earnings" / "reports results" (tighter).
4. **PM audio still not transcribed.** `Brain\Sources\PM\2025-Q4\audio\PM_2026-02-06.m4a` exists — whisper transcript chain deferred again.
5. **No per-vendor modules built yet.** Still just `pmi_backend`. MKC + LW's "IR-home direct artifacts" pattern now suggests a possible shared "Drupal-IR-home" vendor module, but it's really just exercising the generic path — no code to factor out.
6. **HSY quarter labeling is date-based** (`2026-02-05`). Fine functionally (artifacts still discovered by the calendar's glob), cosmetically inconsistent. Fix would be: scan page *text* (not just URLs) for `Q4 2025` / `fourth quarter 2025` patterns.

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
| New artifacts this session | LW/2026-Q3, MKC/2026-Q1, HSY/2026-02-05 |
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
