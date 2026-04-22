---
type: session-handoff
date: 2026-04-22
topic: Built the multi-skill financials pipeline (schema + extract + reconcile + validate), end-to-end CELH 2024 10-K run with 26/26 validation rules passing
tags: [session, celh, multi-skill, pydantic, pipeline, extract, reconcile, validate]
---

# April 22nd — Multi-Skill Financials Pipeline Framework Session

Picks up from the five in-folder handoff docs (`00_README.md` through `04_celh_source_citations.md`) that described the old monolithic `celh-model-update` skill. That skill was **deleted at the start of this session**; all the work here is a clean-slate rebuild as a chain of 6 generic, ticker-agnostic skills.

## Starting state

The prior session left:
- An existing `CELH Financial Model.xlsm` at `C:\Users\rodin\Desktop\Pl3 Celsius Case Study\data\derived\`. ANNL P&L (FY2023-FY2025) and QTR P&L (Q1 2023-Q4 2024) already populated via the old skill. BS + CF for FY2023 + FY2024 extracted and validated in the Source Citations doc but **not yet written** to the xlsm.
- The 5 handoff/state docs in this folder (`00_README.md` through `04_celh_source_citations.md`) describing Phase 0-5 of the old workflow.
- The old `celh-model-update` skill at `~/.claude/skills/celh-model-update/`. User asked to delete it at session start; reworking into a proper multi-skill pipeline was the explicit reason.
- Source PDFs under `C:\Users\rodin\Desktop\Pl3 Celsius Case Study\data\CELH Reporting\Financial Statements\` (2021-2025 10-Ks + 2022-2025 10-Qs).

## Work done this session

### 1. Deleted the old monolithic skill
User confirmed deletion. Purged `~/.claude/skills/celh-model-update/` (SKILL.md + references + all Phase 0-5 workflow). Old skill was 300+ lines of CELH-hardcoded Phase 0-5 orchestration with embedded decisions ledger markdown tables. Replaced with a clean multi-skill architecture below.

### 2. Designed a 6-skill pipeline (3 layers + shared contracts)

Architecture locked in after extensive discussion:
- **Layer 1 — `financials-extract`** — PDF → `RawFiling` (line items with page citations + detected currency unit)
- **Layer 2 — `financials-reconcile`** — `RawFiling` + decisions ledger → `MappedFiling` (every line item carries model_sheet + model_row)
- **Layer 3 — `financials-validate`** — `MappedFiling` → `ValidatedFiling` (BS-1..BS-6, CF-1/CF-2, X-1/X-2/X-4 as Pydantic validators)
- **Layer 4 (pending)** — `financials-playground` (HTML QA explorer), `model-write` (Excel writer), `model-calc` (derived calcs)

Key design choices (capture the *why*):

- **Generic + ledger scope.** No `if ticker == "CELH"` anywhere in code. All CELH-specific quirks live in `Brain/Knowledge/Model Schema/CELH/` as JSON/YAML data. Adding a new ticker is a `mkdir tickers/{name}/` + populate 3 files, not a code change.
- **Shared Pydantic schema package** at `Brain/Knowledge/Model Schema/financials-schema/`. Every skill imports from the same `financials_schema` package. Single source of truth for data contracts.
- **JSON for all persistent state** (decisions ledger, source citations, config, anomalies). Started with YAML for pattern libraries; user and I agreed to flip everything to JSON for consistency — simpler Python stdlib handling, no pyyaml dependency in the shared package.
- **Progressive learning via append-only stores.** Pattern libraries and decisions ledger grow as filings flow through. User confirms novel mappings once; future runs silent.
- **Russian-doll wrapping for audit trail.** `ValidatedFiling` wraps `MappedFiling` wraps `RawFiling`. From the final output you can walk back to the source PDF page + line hint for any value.
- **CLI-level ticker guard** (not a Pydantic field) — each skill's entry point checks `config.ticker` matches `raw.ticker`, raises `TickerMismatchError` on mismatch. Rejected the duplicated-schema-field approach as "fake security."

### 3. Built the shared schema package (`financials-schema`)

Location: `C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\financials-schema\`

Structure:
```
financials-schema/
├── pyproject.toml           (hatchling, Python 3.11+, pydantic 2.6+)
├── .venv/                   (local venv; pdfplumber, pymupdf, rapidfuzz, pytest)
├── financials_schema/       (13 Pydantic classes across 10 files)
│   ├── __init__.py
│   ├── enums.py             (Unit, StatementType, FilingType, Section, NumericNotation)
│   ├── citation.py          (Citation)
│   ├── period.py            (Period, incl. raw_period_label, period_length_weeks, is_comparative)
│   ├── line_item.py         (RawLineItem, MappedLineItem — inheritance)
│   ├── statement.py         (Statement, unit detection fields, validators)
│   ├── filing.py            (RawFiling, press-release-only-IS validator)
│   ├── mapped.py            (MappedFiling, NovelItem, no_unresolved_novel_items validator)
│   ├── validated.py         (ValidatedFiling, ValidationResult)
│   └── patterns.py          (PatternEntry, RegexPattern, RegexPatternEntry, PatternLibrary)
└── tests/
    └── test_smoke.py        (16 tests — ALL PASSING)
```

Install: `pip install -e ".[test]"` in the venv. pytest passes 16/16.

### 4. Built `financials-extract` (Layer 1)

Location: `~/.claude/skills/financials-extract/`

Files:
- `SKILL.md` — frontmatter + description + CLI spec
- `scripts/pattern.py` — 4-layer match ladder (normalize → keyword → fuzzy → append) using rapidfuzz
- `scripts/pdf_reader.py` — thin wrappers over pymupdf (text) and pdfplumber (tables)
- `scripts/extract.py` — CLI + orchestration
- `references/*.json` — 6 pattern libraries (copied from `Brain/Knowledge/Model Schema/pattern_libraries/`)

Extracts line items from 10-K / 10-Q / press release PDFs. Key behaviors:
- **Statement heading detection** requires the line to start with `Consolidated|Statement|Statements|Condensed` AND not contain `for the years|years ended|as of` (filters out MD&A prose and TOC entries).
- **Unit detection** tries explicit header phrase first ("(in thousands)"), falls back to `ACTUAL` dollars if no phrase found within the page.
- **Period detection** has 3 passes: single-line date regex, "For the years ended MONTH DAY," anchor + bare year lines, and "MONTH DAY," single-anchor + bare year lines (CELH 2022 10-K format).
- **Table extraction** merges ALL pdfplumber tables on the statement page (BS often splits into separate Assets and Liabilities tables).

### 5. Built `financials-reconcile` (Layer 2)

Location: `~/.claude/skills/financials-reconcile/`

Files:
- `SKILL.md`
- `scripts/reconcile.py` — CLI + matching logic

Key behaviors:
- **Label normalization** strips equity-row clutter (`, $0.001 par value, X shares authorized...`) via a specific regex — preserves intentional commas like `property, plant and equipment-net`.
- **Sheet-aware lookup index** — ledger mappings are keyed by `(normalized_label, sheet_group)` where sheet_group ∈ {`BS`, `CF`, `IS`}. Prevents collisions where e.g. `net income loss` legitimately appears on both IS (row 22) and CF (row 12).
- **Subtotal rows** ("Total current assets", "Total Assets", etc.) carry through as synthetic `MappedLineItem`s with `model_sheet="_subtotal"` and `row_type="subtotal"`. Validate uses these to check accounting identities.
- **Fuzzy auto-apply** at rapidfuzz ratio ≥ 85. Below 85 → `NovelItem` with top-3 suggestions surfaces for user decision. Novel items block `MappedFiling` construction.

### 6. Built `financials-validate` (Layer 3)

Location: `~/.claude/skills/financials-validate/`

Files:
- `SKILL.md`
- `scripts/validate.py` — CLI + 11-rule orchestration

Rules implemented this session:
- **BS-1..BS-5** — subtotal sums (TCA, NCA, TCL, NCL, TSE) match their component items
- **BS-6** — accounting equation: `TA = TL + Mezzanine + TSE`
- **CF-1** — `CFO + CFI + CFF + FX = ΔCash`
- **CF-2** — `Cash End = Cash Beginning + ΔCash`
- **X-1** — CF Net Income = P&L Net Income (via model-row lookup: IS row 22, CF row 12)
- **X-2** — CF Cash End = BS Cash, honors `cash_convention_per_year` from `anomalies.json` (cash_only vs cash_plus_restricted per year)
- **X-4** — |CF Preferred Dividends Paid| = |P&L Preferred Dividends|

**BS-7 not implemented yet** (would need prior-period BS data for RE roll-forward; currently out of scope with single-filing runs).

Tolerances: $1K absolute OR 0.1% relative. Any rule with `severity="fail"` → skill exits non-zero, no output file written.

### 7. Data files under `Brain/Knowledge/Model Schema/`

Cleaned and populated per-ticker + shared infrastructure:

```
Brain/Knowledge/Model Schema/
├── README.md                            (index + reading order)
├── 01_architecture_map.html             (pipeline playground — 3/6 skills now badged ✓ built)
├── 02_pydantic_schema.html              (Pydantic class diagram)
├── 03_schema_spec.md
├── 04_pipeline_design.md
├── 05_ticker_folder_spec.md
├── 06_pattern_library_design.md
├── CELH/
│   ├── config.json                      (ticker metadata, expected magnitude ranges, stock splits)
│   ├── anomalies.json                   (cash_convention_per_year, mezzanine, identical-YoY items, structural rules)
│   ├── decisions_ledger.json            (111 mappings + 18 new_rows + 7 structural decisions)
│   └── derived/
│       ├── raw_2024_10K.json            (extract output — 8 Statements, 260 line items)
│       ├── mapped_2024_10K.json         (reconcile output — 260 items, 0 novel)
│       ├── validated_2024_10K.json      (validate output — 26 rules, 0 warnings, 0 fails)
│       └── raw_2023_10K.json            (2023 10-K partially extracted; reconcile blocked on novels)
├── financials-schema/                   (shared Pydantic package — 16/16 tests passing)
└── pattern_libraries/                   (6 shared JSON pattern files)
```

### 8. End-to-end run on CELH 2024 10-K — 26/26 validation rules PASS

Full pipeline verified against the 2024 10-K (filed Feb 2024, reports FY2023 + comparatives):
- Extract: 8 Statement objects across 3 statement types × up to 3 periods → 260 `RawLineItem` objects
- Reconcile: 202 mapped to existing rows + 43 to new rows + 15 subtotals + **0 novel**
- Validate: 26 rules (BS-1..BS-6 × 2 periods + CF-1/CF-2 × 3 periods + X-1/X-2/X-4 × 3 periods) — **all PASS with gap = 0**
- Cross-statement ties confirmed: CF Net Income = P&L Net Income across all 3 years; CF Cash End = BS Cash across both BS periods (with cash_plus_restricted convention correctly applied for FY2022).

### 9. Playgrounds (pipeline map + Pydantic schema map)

Two interactive HTML playgrounds rebuilt multiple times this session:
- **`01_architecture_map.html`** — layered pipeline diagram with pan/zoom/fit controls. Top-to-bottom flow: INPUT (SEC PDFs) → Layer 1-4 → Layer 5 (shared schema). Each built skill gets a green ✓ badge. Stores positioned next to their consumer skill (decisions_ledger.json next to reconcile; pattern_libraries next to extract). Scaffold-prompt generator at the bottom driven by Schema Hosting + Scope toggles.
- **`02_pydantic_schema.html`** — Pydantic class diagram with composition arrows (teal) and inheritance arrows (red). Every field type color-coded (primitive gray, enum cyan, model teal, literal purple, container yellow). Click a card for full details + Python source. Long Literal types truncated with tooltip for full type.

### 10. Known-issue flagging: reporting-style drift (important — needs Phase 2 design decision)

Tested the pipeline on CELH's older filings (2022 10-K and 2023 10-K) to fill FY2021 Balance Sheet coverage. Found:

- **CELH 2022 10-K reports in ACTUAL DOLLARS** (not thousands). No unit phrase on the statement page. Relaxed extract's unit-detection fallback to default to `Unit.ACTUAL` when no phrase found.
- **Period headers split differently** across 10-K eras. 2022 10-K has `December 31,` on one line and `2021` on next line (separate bare-year lines). 2024 10-K has them on the same line. Added 3-pass period detection to handle both formats.
- **TOC entries collided with real statement headings** in 2023 10-K ("Consolidated Balance Sheets as of December 31, 2022 and 2021" on page 38 was a TOC reference, real BS on page 44). Added `\bas\s+of\b` to the prose-rejection filter.
- **Line-item wording drifts over time.** CELH older 10-Ks use "Share-based payment expense" for what newer filings call "Stock-based compensation expense". "Amortization" alone vs "Amortization of deferred other costs". "Accounts payable and accrued expenses" combined vs split.

**Consequence:** extracting the 2023 10-K worked, but reconcile flagged **39 novel items** due to older-era wording that isn't in the ledger. Each older filing era requires its own batch of ledger entries.

**Design question flagged for Phase 2 (not resolved this session):**

> The current approach handles reporting-style drift via progressive ledger expansion — every filing era adds mappings. Works but requires manual curation per filing. **Should the ledger itself know about filing-era contexts** (e.g. `filing_date_range` attached to each mapping)? Or should there be an explicit "filing-era adapter" that normalizes older labels to current wording BEFORE ledger lookup? Or should reconcile surface a "this probably maps to X in the current-era vocabulary" prompt?
>
> User's words: *"we are going to need to make this stage dynamic and figure out what the best course of action is when reporting style changes for a company over time."*
>
> This is the biggest architectural TODO. Current pipeline works cleanly on same-era filings (2024 10-K ran end-to-end with 0 novels after ledger pre-population). Multi-era coverage requires thought.

### 11. Deferred: GLP-1 and SNAP model overlay

Mid-session, user confirmed these overlays are **out of scope for now**. `model-calc` (Layer 4 skill not yet built) should be simplified to just:
- YoY / QoQ growth
- Margins (GP, OP, NI)
- Working capital ratios (DSO, DIO, DPO, CCC)
- Base scenario sensitivity (no bull/bear scenarios, no external model inputs)

When scope expands back to include scenario overlays, re-read `04_pipeline_design.md` section on model-calc.

## Current state

### Built and verified (3 of 6 skills)

| Skill | Status | Tests |
|---|---|---|
| `financials-extract` | Built; runs on CELH 2024 10-K cleanly; 2023 10-K works with format adaptations; 2022 10-K extracts but has unresolved wording novels downstream | Manual end-to-end only (no pytest yet) |
| `financials-reconcile` | Built; sheet-aware lookup; fuzzy auto-apply @ 85; subtotal passthrough; 111-mapping CELH ledger | Manual end-to-end only |
| `financials-validate` | Built; 11 rules implemented (BS-7 deferred); honors anomalies.json cash convention | Manual end-to-end only |
| `financials-schema` (shared package) | Built; 16/16 pytest passing | `tests/test_smoke.py` |

### Not yet built (3 of 6 skills)

| Skill | Purpose | Rough design |
|---|---|---|
| `financials-playground` | HTML QA explorer over a `ValidatedFiling` — tabbed BS/CF/IS tables with YoY highlights and citation tooltips | Single Python script producing a self-contained HTML file. Dark theme matching the two design playgrounds. User chose this as NEXT to build at session end. |
| `model-write` | Write a `ValidatedFiling` into the CELH `.xlsm` model using openpyxl. Path 3 manual inserts for new rows. `.bak` backup before writes. Verify-after-save. | See `04_pipeline_design.md` for full spec. |
| `model-calc` | Derived calcs only — growth, margins, WC ratios, base scenario. **GLP-1 and SNAP overlays explicitly deferred.** | Simplified scope per user direction. |

### Coverage of the CELH 2024 10-K (the primary test case)

- All 3 statements extracted cleanly
- All 260 line items mapped (0 novel after ledger-building iterations)
- All 26 validation rules pass (gap = 0 on every rule)
- Cash-convention anomaly correctly handled for FY2022 comparative column

### Partial coverage of older filings

- **2023 10-K** (FY2022 + FY2021): extract works; reconcile flagged 39 novels from older-era wording. Resolving these is Phase 2 work.
- **2022 10-K** (FY2021 + FY2020): extract partially works; BS on wrong page (TOC collision was fixed for 2023 but 2022's TOC is in a different position); periods split in unusual format; needs further format adaptation.
- **FY2021 BS verified manually** from the 2023 10-K extract: `TA (314,018) = TL (96,973) + Mezz (0) + TSE (217,045)` ties perfectly. Would PASS BS-6 and X-2 if reconcile could get through the novels.

### Pipeline invocation sequence (CELH 2024 10-K)

```bash
# Activate venv first
cd "C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\financials-schema"
source .venv/Scripts/activate

# 1. Extract
python "C:\Users\rodin\.claude\skills\financials-extract\scripts\extract.py" \
  --ticker-root "C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\CELH/" \
  --pdf "C:\Users\rodin\Desktop\Pl3 Celsius Case Study\data\CELH Reporting\Financial Statements\2024_CELH_10-K.pdf" \
  --out "C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\CELH\derived\raw_2024_10K.json" \
  --filing-type "10-K" --filing-date "2024-02-29"

# 2. Reconcile
python "C:\Users\rodin\.claude\skills\financials-reconcile\scripts\reconcile.py" \
  --ticker-root "C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\CELH/" \
  --in "...\derived\raw_2024_10K.json" --out "...\derived\mapped_2024_10K.json"

# 3. Validate (needs PYTHONIOENCODING=utf-8 on Windows for Δ / — chars)
PYTHONIOENCODING=utf-8 python "C:\Users\rodin\.claude\skills\financials-validate\scripts\validate.py" \
  --ticker-root "C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\CELH/" \
  --in "...\derived\mapped_2024_10K.json" --out "...\derived\validated_2024_10K.json"
```

## Open decisions / pending work

1. **Build `financials-playground` next** (Layer 4, part 1). User's chosen next step at end of session. Single Python script → self-contained HTML. Input: `validated_2024_10K.json`. Output: tabbed BS/CF/IS tables with YoY highlights + citation tooltips.

2. **Then `model-write`** (Layer 4, part 2). This is the payoff — actually writes the 260 extracted/validated values into `C:\Users\rodin\Desktop\Pl3 Celsius Case Study\data\derived\CELH Financial Model.xlsm`. Requirements from old skill carry forward: `keep_vba=True`, never `cell.fill = None`, `.bak` backup before any write, emit `ManualInsertPlan` for new rows (Path 3 — user inserts rows manually in Excel to preserve cross-sheet formulas), save to `_updated.xlsm` filename, verify-after-save with `#REF!` grep.

3. **Then `model-calc`** (Layer 4, part 3) — simplified scope. Just derived calcs, no GLP-1/SNAP overlays.

4. **BIG ARCHITECTURAL TODO — reporting-style drift.** Older 10-K filings use different wording and formatting than current filings. Handling multi-era coverage for a single ticker currently requires manual progressive ledger expansion per filing era. **User explicitly flagged this as needing a better solution in a future phase.** Options to evaluate:
   - Per-era mapping contexts on each ledger entry (`filing_date_range`)
   - Explicit filing-era normalization adapter that runs BEFORE ledger lookup
   - Semantic / LLM-assisted matching for unknown labels
   - Multi-variant lookup (each mapping can list multiple equivalent labels)
   
   Do not skip this — it's the difference between "works on current filings only" and "works across a company's full history." See section 10 of Work done for more context.

5. **BS-7 validator** (RE roll-forward: `RE(t) = RE(t-1) + NI(t) − PrefDiv(t)`) not implemented. Requires prior-period BS data. Consider implementing as part of a "cross-filing" validation mode.

6. **Pytest coverage** for extract / reconcile / validate. Currently only `financials-schema/tests/test_smoke.py` exists. Each skill should get at least one end-to-end integration test against a fixture PDF.

7. **Windows console encoding.** Validate uses Δ and — characters in messages that break Windows cp1252 stdout. Worked around via `PYTHONIOENCODING=utf-8`. Better fix: swap Δ/— for ASCII equivalents in messages, or force stdout encoding at main() start.

8. **Skill tests live under each skill's `tests/` folder but are empty.** Populate when scaffolding CI.

9. **The existing `CELH Financial Model.xlsm`** at `C:\Users\rodin\Desktop\Pl3 Celsius Case Study\data\derived\` has the P&L filled in from the OLD skill runs (ANNL P&L FY2023-FY2025, QTR P&L Q1 2023-Q4 2024). **BS and CF rows are not yet written.** When `model-write` is built, first run against the 2024 10-K's BS + CF. The existing old-skill values can stay; model-write only writes to the rows in the ledger.

10. **Decisions ledger inflation.** The ledger grew from ~30 rules at session start to 111 mappings by end. Many are CELH-specific filing variants (e.g. MAP-IS-014 through MAP-IS-021 are aliases for IS line items). **These are all generic (any ticker can use them)** but were added opportunistically. Consider auditing which mappings belong in `CELH/decisions_ledger.json` (ticker-specific) vs a shared `generic_mappings.json` (cross-ticker).

## Key file paths

| Purpose | Path |
|---|---|
| Pipeline architecture map (playground) | `C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\01_architecture_map.html` |
| Pydantic schema map (playground) | `C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\02_pydantic_schema.html` |
| Design docs | `C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\0{3..6}_*.md` |
| Shared Pydantic package | `C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\financials-schema\` |
| Shared pattern libraries | `C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\pattern_libraries\*.json` |
| CELH ticker config | `C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\CELH\config.json` |
| CELH anomalies (cash convention etc.) | `C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\CELH\anomalies.json` |
| CELH decisions ledger (111 entries) | `C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\CELH\decisions_ledger.json` |
| CELH derived outputs | `C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\CELH\derived\` |
| Extract skill | `C:\Users\rodin\.claude\skills\financials-extract\` |
| Reconcile skill | `C:\Users\rodin\.claude\skills\financials-reconcile\` |
| Validate skill | `C:\Users\rodin\.claude\skills\financials-validate\` |
| Source PDFs (CELH) | `C:\Users\rodin\Desktop\Pl3 Celsius Case Study\data\CELH Reporting\Financial Statements\` |
| Target Excel model | `C:\Users\rodin\Desktop\Pl3 Celsius Case Study\data\derived\CELH Financial Model.xlsm` |
| Prior handoffs in this task | `Brain\Sessions\CELH Model\00_README.md` (+ 01-04 numbered state docs from the pre-rebuild era) |
| This session's handoff | `C:\Users\rodin\Desktop\Brain\Sessions\CELH Model\April 22nd Multi-Skill Framework Session.md` |

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
