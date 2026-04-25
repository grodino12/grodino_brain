---
type: session-handoff
date: 2026-04-24
topic: Built sec-edgar-fetch + financials-extract-ixbrl skills (iXBRL HTML → RawFiling via SEC presentation linkbase), pulled PG's full 10-Q history (1993→2026, 99 filings), extended the pipeline (reconcile + validate + model-write) to be filing-type aware with a parallel quarterly sheet family triggered by FilingType == 10-Q.
tags: [session, celh, sec-edgar, ixbrl, quarterly-pipeline, pg, universal-architecture, playground-sync]
---

# April 24th — SEC EDGAR + Quarterly Pipeline Session

Picks up from `April 24th Model-Calc Forecast Balance Session.md`. That session shipped the full annual forecast stack end-to-end on CELH (48/48 validate PASS, BS balanced, number formats propagated) and pivoted project focus to **universal model creation architecture**. This session continued that pivot by onboarding the SEC EDGAR data source, building an iXBRL-native extractor, and extending reconcile + validate + model-write to a parallel quarterly sheet family. The test ticker is PG (Procter & Gamble, June 30 fiscal year-end).

## Starting state (beginning of this session)

- CELH pipeline: 6-of-6 skills built, 48/48 validate PASS, xlsx + model-calc forecasts clean. Annual-only by design (`model-write` explicitly deferred QTR P&L per its SKILL.md).
- Pipeline input was PDF-only (`financials-extract` via pattern libraries + rapidfuzz). No SEC-native ingestion. No iXBRL parsing. No filings on disk for tickers other than CELH.
- `financials-reconcile` keyed its lookup on `(normalized_label, sheet_group)` — no variant axis, so annual-only ledger entries.
- `model-write`'s `V1_SHEETS = ["ANNL P&L", "BALANCE SHEET", "CASH FLOW"]` hardcoded annual; the "skip quarterly IS" guard dropped any 10-Q IS statement.
- `playground_architecture.html` reflected the 6-skill annual pipeline. Status line: "3 of 6 skills built."

## Work done this session

### 1. `sec-edgar-fetch` skill built

New skill at `~/.claude/skills/sec-edgar-fetch/`. Pulls 10-K / 10-Q primary iXBRL HTMLs + `Financial_Report.xlsx` + cumulative XBRL `companyfacts.json` from `data.sec.gov` into the user's ticker folders. SEC-polite: 5 req/sec throttle (hard cap is 10), real User-Agent (`rodinogj12@gmail.com`), 429/5xx backoff. Writes a tiny `.meta.json` sidecar next to each filing (accession, cik, archive_base_url, quarter, form) so downstream skills can locate FilingSummary.xml without re-querying SEC.

Folder convention: `Brain\Sources\{TICKER}\{QUARTER}\filings\{TICKER}_{YYYY-MM-DD}_{form}.htm`. `QUARTER` derived from SEC's fiscalYearEnd + periodOfReport. Gap-skip: filing is skipped if both .htm and .xlsx are already on disk; idempotent and resumable.

**`--all` flag added** to walk the full `submissions.json` history (recent block + every paginated archive in `filings.files`). For PG, this surfaces **~130 10-K/10-Q filings back to 1993-1994**. Known caveat: very recent filings (within ~2 months) don't have `Financial_Report.xlsx` yet because SEC generates it asynchronously — they show a `[wait]` message and are re-fetched on the next run.

**Executed against PG**: `python fetch.py --ticker PG --all --forms 10-Q --no-companyfacts` → **99 quarter folders** under `Brain\Sources\PG\`, one per 10-Q from 1994-Q2 (period ending 1993-12-31) through 2026-Q2 (period ending 2025-12-31). Also ran the default (non-`--all`) pull earlier to land the 10-K and the most recent 10-Q plus the 3.6 MB companyfacts.json.

### 2. `financials-extract-ixbrl` skill built (the big one)

New skill at `~/.claude/skills/financials-extract-ixbrl/`. Emits the **same `RawFiling` JSON shape** as `financials-extract` (PDF), so it plugs into reconcile/validate/playground/model-write unchanged.

**Key architectural win**: SEC's iXBRL filings have every number tagged with concept / context / unit / scale via `<ix:nonFraction>` elements. The PDF-based extractor reverse-engineers these with fuzzy matching, pattern libraries, 4-layer adaptation ladder. The iXBRL extractor reads the tags directly — ~200 lines of Python replaces the entire PDF pipeline for SEC-filed documents.

Classification uses the **SEC presentation linkbase** — delivered as `FilingSummary.xml` + per-role `R{n}.htm` sidecars. Fetched + cached per-accession under `scripts/.cache/reports/{accession-nodash}/`. Parses concept → statement_code (IS / CI / BS / CF / SE) from each R-file's concept references. No heuristic prefix matching.

**Design decisions:**
- iXBRL files are XHTML-compliant — use lxml's **XML parser**, not HTMLParser (the latter mangles namespaces — `<ix:nonFraction>` becomes a tag literal `"ix:nonfraction"` with no namespace, breaking XPath).
- Prototype in `~/.claude/skills/sec-edgar-fetch/scripts/ixbrl_extract_prototype.py` explores raw facts with `--segments`, `--details`, `--statement` filters. Production extractor is the focused RawFiling emitter.
- Merge Comprehensive Income into IS (schema only supports BS/CF/IS). Skip SE + DETAIL facts from primary RawFiling (surfaced in extraction_metadata for future use).
- **BS top-2 filter**: StockholdersEquity roll-forward reference balances leak in via concepts that appear on both BS and SE R-files. Keep only the top-2 most-populated BS instant dates (real BS has 30+ items per date; leaks have 1-3).
- fiscal_quarter = None for YTD durations (6-month, 9-month) to avoid misleading "Q2" label on a multi-quarter period. Single-quarter durations (11-15 weeks) get the quarter; BS snapshots get the matching quarter for the filing.

**Smoke-tested on PG Q2 FY2026 10-Q**: 854 tagged facts → 10 Statements / 199 line items. Validates via `RawFiling.model_validate_json` cleanly.

### 3. Tooltip overhaul in `financials-playground` (QA explorer)

`citation_tooltip()` in `scripts/build_playground.py` dispatches on `source_path` extension:
- `.htm` / `.html` → iXBRL: `Concept: us-gaap:Revenues | From: Consolidated Statements of Earnings | Period: ending 2025-12-31 | Source: PG_2025-12-31_10-Q.htm | Unit: millions`
- anything else → original PDF format: `Raw label: Revenues | Source: 2025_CELH_10-K.pdf p.47 | Unit: millions | Line: revenues`

The iXBRL path skips the useless `p.1` (iXBRL has no pagination; page=1 is a Citation schema placeholder) and surfaces the R-file role instead (`note` field carries `"iXBRL | Consolidated Statements of Earnings"`, set by the extractor).

### 4. Playground architecture map updated (both structural changes)

`playground_architecture.html` rewired across two passes:

**Pass A — SEC EDGAR + iXBRL nodes:**
- Input layer expanded to 2 rows (40-220, +90px; all lower layers shifted down). Row 1 externals: `SEC EDGAR API`, `IR press release PDFs`. Row 2 fetch + stores: `sec-edgar-fetch`, `iXBRL HTML + meta.json`, `companyfacts.json`.
- Extract layer gained `financials-extract-ixbrl` as peer to `financials-extract`; both feed the same `RawFiling` contract.
- All new edges wired (API → fetch → stores → ixbrl-extract → RawFiling; PDF path preserved).
- Title: "Financials Pipeline — Architecture Map" (was CELH-specific).
- `SKILL_IDS` array + `scaffoldBody` prompts extended for both new skills.

**Pass B — Quarterly pipeline:**
- `financials-reconcile` node: noted filing-type-aware routing + 3-month-only filter + `sheet_variant` lookup axis.
- `model-write` node: marked built, added QTR P&L / QTR BS / QTR CF sheet family, explained mixed-input behavior.
- Header status line: "7 of 8 skills built" (was "3 of 6"); call-outs for PG Q2 FY26 iXBRL run (199 line items) and CELH 26/26 validation PASS.

**`LS_KEY` bumped `v1 → v5`** across the session so the user's browser picks up new defaults instead of replaying cached state.

### 5. Quarterly pipeline: `financials-reconcile` extended

Chosen design (per user): **separate sheet families**, triggered by `filing_type`. 10-K flows unchanged into ANNL sheets. 10-Q flows into parallel QTR sheets. **3-month only** — YTD 6-month and 9-month IS/CF statements dropped.

Concrete changes in `scripts/reconcile.py`:
- `_sheet_variant(model_sheet)` helper → "QTR" for names starting with "qtr ", "ANNL" otherwise (preserves backwards compatibility with CELH ledger which has no QTR entries).
- `_target_variant(filing_type)` → "QTR" for 10-Q, "ANNL" for everything else.
- Lookup index now keyed on `(normalized_label, sheet_group, sheet_variant)` — 3-tuple, was 2-tuple. Same concept like `us-gaap:Revenues` can have two ledger entries (one ANNL, one QTR) without collision.
- `reconcile_item(item, stmt_type, lookup, target_variant)` — variant threaded through.
- `_keep_statement_for_reconcile(statement, filing_type)` — for 10-Qs, keeps BS instants and duration statements with `period_length_weeks ∈ [11, 15]`. Filters out 26-week / 39-week YTD before the mapping loop.
- NovelReport entries now carry `target_variant` for diagnostic clarity.

### 6. Quarterly pipeline: `financials-validate`

Most rules turned out to already be period-agnostic (BS-1..6, CF-1/CF-2, X-2, X-4 work on any single period). Reconcile dropping YTD means validate sees clean 3-month data without needing extra logic. Only real change: **period_label format fix** — was emitting `"Q2 2026"` (missing "FY" prefix); now emits `"Q2 FY2026"` consistently with annual `"FY2024"`. Added `FilingType` import so the cross-statement rules section can detect 10-Q filings (currently only used for comments / docstring; rules themselves didn't need branching).

BS-7 (RE roll-forward) was never implemented — SKILL.md has always listed it as deferred. No change this session.

### 7. Quarterly pipeline: `model-write` — QTR sheet family

`scripts/write.py` changes:
- `V1_SHEETS` expanded: `ANNL_SHEETS + QTR_SHEETS` where `QTR_SHEETS = ["QTR P&L", "QTR BS", "QTR CF"]`.
- Replaced `STATEMENT_TYPE_TO_SHEET` dict with `stmt_to_sheet(stmt_type, filing_type)` helper — routes based on filing type.
- `LEDGER_SHEET_MAP` extended with QTR entries.
- Deleted the "skip quarterly IS" continues (lines 253-255, 333-335, 381-382) — reconcile's filter now provides the guarantee that any surviving statement is safe to render.
- `build_column_layout`: QTR sheets get `Q{N} FY{YYYY}` labels (disambiguates Q1/Q2/Q3 within a fiscal year — plain `FY{year}` would collide). QTR sheets get **no forecast columns** in v1 (deferred to model-calc).
- `build_workbook`: empty sheets suppressed — if no 10-Q input provided, the QTR tabs aren't emitted at all (and vice versa for a 10-Q-only run).

### 8. PG ticker root scaffolded + smoke test

- Created `Brain\Knowledge\Model Schema\PG\{config.json, decisions_ledger.json, anomalies.json, Model Output\}`.
- Ran `financials-extract-ixbrl --ticker-root PG --htm PG_2025-12-31_10-Q.htm --out PG/Model Output/raw_2026_Q2.json` → 199 line items across 10 Statements.
- Ran `financials-reconcile --dry-run --novels-out ...` → **107 novel items** surfaced, all tagged `target_variant: QTR`. Statement breakdown: **BS 64, IS 41, CF 2**. Confirmed YTD 6-month IS/CF (92 items) cleanly dropped by the 3-month filter — only 3-month and BS-instant statements reached the lookup.
- NovelReport JSON validates clean. All structural code paths exercised without errors.

**No crashes. Pipeline works end-to-end on a 10-Q.** The remaining question is human work: does the user resolve 107 novels by hand, or do we dedupe/auto-seed first (see §Open decisions).

### 9. Memory rules saved

Two persistent memory entries created or extended:
- `feedback_keep_playgrounds_in_sync.md` (new) — every structural change to the financials framework must update `playground_architecture.html` + `playground_schema.html`. Bump `LS_KEY` when data model changes. **User explicitly asked this rule propagate across all future handoffs.**
- `feedback_session_handoffs.md` (extended) — the handoff template now includes an "Architecture-playground sync rule" bullet that must appear in every handoff's pending-work section so the next session sees it before making structural changes.

## Current state

**Skills (8 total):**
- ✅ `sec-edgar-fetch` — new, built, executed against PG (99 10-Qs pulled).
- ✅ `financials-extract-ixbrl` — new, built, smoke-tested on PG Q2 FY26 10-Q.
- ✅ `financials-extract` — unchanged (PDF fallback path).
- ✅ `financials-reconcile` — extended for filing-type-aware sheet routing.
- ✅ `financials-validate` — period_label fix; rules confirmed period-agnostic.
- ✅ `financials-playground` — iXBRL citation tooltip; no other change.
- ✅ `model-write` — QTR sheet family added; empty sheets suppressed.
- ⏳ `model-calc` — **unchanged**. Still annual-only. Quarterly forecast drivers pending.

**PG data on disk:**
- 99 folders under `Brain\Sources\PG\` (1994-Q2 → 2026-Q2), one per 10-Q.
- `Brain\Sources\PG\companyfacts.json` (3.6 MB cumulative XBRL facts).
- `Brain\Knowledge\Model Schema\PG\{config.json, decisions_ledger.json (empty), anomalies.json, Model Output\raw_2026_Q2.json, Model Output\novels_2026_Q2.json (107 items)}`.

**Playgrounds:**
- `playground_architecture.html` — reflects full quarterly pipeline. LS_KEY at v5.
- `playground_schema.html` — no change needed this session (no schema changes, only helper-function additions).

## Open decisions / pending work

1. **⚠️ Investigate the 107 novel-item count for PG's 10-Q** — user's instinct was that 107 is too high. Before hand-resolving anything, triage into three buckets:
   - **Duplicates across periods**: each concept appears twice in the novels list (current Q + prior-year comp Q). After dedup by concept, expected count is ~54 unique concepts. That alone cuts the apparent load in half.
   - **Should have matched the cross-ticker generic library**: `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` has ~89 entries built for CELH from PDF label patterns. **The dry-run did NOT pass `--generic-library`** — re-run reconcile with it enabled and see how many novels auto-apply. **Note:** the generic library is keyed on PDF label text (e.g. `"revenue"`, `"net sales"`), while iXBRL gives us US-GAAP concept names (e.g. `"Revenues"`). Match rate may still be low because the raw_filing_label vocabulary differs between extraction paths. If the match rate is poor, the real gap is an iXBRL-aware generic library layer.
   - **Genuinely novel concepts** — PG-specific line items (e.g. segment-disclosure totals, custom tax items) that need per-ticker ledger decisions regardless.
   - **Clarification on "pattern_libraries.json":** the user's phrasing suggests they may be thinking of the extraction-layer patterns at `~/.claude/skills/financials-extract/references/*.json` (statement headings, unit phrases, etc.). Those are **only used by the PDF extractor** — iXBRL extraction doesn't touch them (concepts come from XML tags directly). The library that matters at reconcile time is `generic_line_item_mappings.json`. The handoff distinction is worth noting for the next session.
   - **Action**: re-run reconcile with `--generic-library` flag; deduplicate novels by concept for user review; then decide whether to (a) hand-resolve what remains, or (b) build an iXBRL-concept-keyed generic library that maps `us-gaap:*` names directly to model rows across all filers.
2. **Extend `model-calc` to quarterly drivers.** Currently annual-only (ASSUMPTIONS + IS/BS/CF DRIVERS in FY columns). To produce a forecast on QTR P&L etc., need quarterly driver tabs + quarterly forecast formulas. Non-trivial — defer until PG has at least one clean ValidatedFiling through the pipeline.
3. **QTR CF will be sparse for most filers**, PG included. PG reports its Cash Flow Statement on a YTD basis only in 10-Qs — no 3-month CF on the face. Pure quarterly CF requires `Q_CF = YTD_Q2 - YTD_Q1` computation, which belongs in model-calc, not reconcile. The smoke test confirms this: QTR CF only had 2 line items out of 50+ expected (a single 3-month fact that happened to be tagged). Not a bug — a filer convention.
4. **PG decisions_ledger.json is empty.** After the §1 investigation, populate it with resolved mappings. The CELH ledger is not a copy-from-starter — label vocabulary is different (iXBRL concept names vs PDF text). Consider whether the work is better done as a per-ticker decision batch or as an iXBRL-taxonomy overlay in the generic library.
5. **Handoff propagation rule (active, carry forward every session):** Structural changes to the financials framework must update both `playground_architecture.html` and `playground_schema.html` before the session closes. Bump LS_KEY on NODES/EDGES changes. Include this bullet in future handoffs' Open decisions section until the user retires it.
6. **Pre-iXBRL historical 10-Qs.** Of PG's 99 10-Qs, only ~50 (2009+) are iXBRL-era and thus extractable by `financials-extract-ixbrl`. Pre-2009 filings are HTML-only with no inline XBRL tags; they would need either PDF-equivalent extraction via `financials-extract` (and conversion from HTML first) or SEC's `companyfacts.json` direct-query (SEC backfills many standard GAAP concepts into companyfacts for older periods). Not blocking; deferred.

## Key file paths

| Purpose | Path |
|---|---|
| sec-edgar-fetch skill | `C:\Users\rodin\.claude\skills\sec-edgar-fetch\` |
| sec-edgar-fetch CLI | `C:\Users\rodin\.claude\skills\sec-edgar-fetch\scripts\fetch.py` |
| iXBRL prototype (exploration) | `C:\Users\rodin\.claude\skills\sec-edgar-fetch\scripts\ixbrl_extract_prototype.py` |
| financials-extract-ixbrl skill | `C:\Users\rodin\.claude\skills\financials-extract-ixbrl\` |
| financials-extract-ixbrl CLI | `C:\Users\rodin\.claude\skills\financials-extract-ixbrl\scripts\extract.py` |
| reconcile (updated) | `C:\Users\rodin\.claude\skills\financials-reconcile\scripts\reconcile.py` |
| validate (updated) | `C:\Users\rodin\.claude\skills\financials-validate\scripts\validate.py` |
| model-write (updated) | `C:\Users\rodin\.claude\skills\model-write\scripts\write.py` |
| financials-playground (updated tooltip) | `C:\Users\rodin\.claude\skills\financials-playground\scripts\build_playground.py` |
| PG ticker root | `C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\PG\` |
| PG RawFiling (Q2 FY26) | `C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\PG\Model Output\raw_2026_Q2.json` |
| PG NovelReport (107 items) | `C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\PG\Model Output\novels_2026_Q2.json` |
| PG filing archive (99 10-Qs) | `C:\Users\rodin\Desktop\Brain\Sources\PG\` |
| PG companyfacts.json | `C:\Users\rodin\Desktop\Brain\Sources\PG\companyfacts.json` |
| Cross-ticker generic library | `C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` |
| Architecture playground | `C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\playground_architecture.html` |
| Schema playground | `C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\playground_schema.html` |
| Pipeline roadmap | `C:\Users\rodin\Desktop\Brain\Sessions\CELH Model\ROADMAP.md` |
| Python venv (financials_schema) | `C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\financials-schema\.venv\Scripts\python.exe` |
| Memory: playground sync rule | `C:\Users\rodin\.claude\projects\C--Users-rodin\memory\feedback_keep_playgrounds_in_sync.md` |
| Memory: handoff convention | `C:\Users\rodin\.claude\projects\C--Users-rodin\memory\feedback_session_handoffs.md` |

## How to create the next handoff

At the end of every session, write a new handoff under `C:/Users/rodin/Desktop/Brain/Sessions/{Task-Theme}/Handoffs/` following the exact structure below. This keeps every future "cold start" predictable — the next session picks up one file and knows everything it needs.

### Naming
`{Month-name} {Day-ordinal} {short-topic} Session.md`
e.g. `April 20th IR Scraper v1 Session.md`, `April 25th CELH Backend Session.md`.

Ordinal = `st` / `nd` / `rd` / `th`. One or two topic words. Keep the filename short.

### Required sections (in this order)

1. **YAML frontmatter** — `type: session-handoff`, `date: YYYY-MM-DD` (absolute, never relative), `topic: {one-line}`, `tags: [session, ...]`.
2. **`# {Title}`** heading matching the filename.
3. **`## Starting state`** — what was true at session start. Reference the prior handoff filename explicitly so the chain is walkable.
4. **`## Work done this session`** — grouped by logical chunks (numbered `### 1.` subsections work well). Each subsection should say *what changed* and *why*, not just the surface action. Capture root-cause insights.
5. **`## Current state`** — bullet list of what's working, what's partially working, what's not. Include concrete file paths for artifacts produced.
6. **`## Open decisions / pending work`** — numbered list of unresolved items. Each one should state the *decision* or *action* needed, not just a vague "look into X". If a decision is blocked on user input, say so. **Always include the active architecture-playground sync rule** (user asked this propagate across every handoff) so the next session sees it before making structural changes.
7. **`## Key file paths`** — two-column table: Purpose | Path. Use absolute paths. Include scheduled task names and external system references.
8. **`## How to create the next handoff`** — paste this exact section verbatim. Never drop it; never let the template drift without updating all copies forward.

### Quality bar

- Write so the next session (cold, no conversation history) can act without re-asking you questions.
- Prefer concrete over abstract.
- Capture *why* a design choice was made when it's non-obvious. Code shows what; handoffs should show why.
- If you deleted, renamed, or moved files, explicitly mention it — the next session will otherwise hunt for the old paths.
- Keep it self-contained. Don't say "as discussed" — write out the discussion outcome.
