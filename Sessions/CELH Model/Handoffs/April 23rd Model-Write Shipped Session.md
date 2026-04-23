---
type: session-handoff
date: 2026-04-23
topic: model-write skill shipped (fresh-build xlsx with BS/CF subtotal formulas + top borders), handoffs folder reorg, ledger cleanup (28 renames + 6 superseded + anchor fixes + lease filing_section split), M-1 consistency validator + reconcile B-guard, ROADMAP established + updated, CELH/derived → CELH/Model Output rename, playground alignment
tags: [session, celh, model-write, ledger-cleanup, validator, handoffs-folder, roadmap]
---

# April 23rd — Model-Write Shipped Session

Picks up from `April 22nd Playground Polish Session.md`, which ended with the pipeline fully validated (35/35 on both FY2023 + FY2024 10-Ks) and model-write flagged as the next payoff milestone. This session established a project roadmap, built model-write from scratch end-to-end, iterated on output quality, surfaced + fixed deep data-consistency gaps in the ledger/validation, and reorganized the handoffs folder structure.

## Starting state

- 4 of 6 skills shipped (extract, reconcile, validate, playground); 2 unbuilt (model-write, model-calc).
- FY2023 10-K: 35/35 validation rules PASS. FY2024 10-K: 35/35 PASS. Values verified end-to-end.
- Decisions ledger: 124 mappings + 24 new_rows + 7 structural + 1 rename.
- Multi-filing playground at `CELH/derived/explorer_multi.html` rendering cleanly.
- No roadmap doc existed; handoffs living directly in `Brain\Sessions\CELH Model\` root.
- User had deferred QTR P&L (no 10-Q loaded), FY2025 10-K pull, and GLP-1/SNAP scenario overlays.

## Work done this session

### 1. ROADMAP established

Created `Brain\Sessions\CELH Model\ROADMAP.md` with: status-at-a-glance table, project scope, Done, Active, Near horizon, Later horizon, Deferred, Known small issues, Key references. Scope covers all three workbooks (CELH financial, GLP-1, SNAP) and the eventual cross-model integration. User then requested iterative updates throughout the session.

### 2. Handoffs subfolder reorganization

User: "If you are going to write the roadmap in that folder please create a subfolder at that level for handoffs and drop all the handoffs into that folder."

Created `Brain\Sessions\CELH Model\Handoffs\` and moved the three April 22nd Session.md files into it. Left the 00–04 numbered pre-rebuild context docs in the root (they're reference, not per-session handoffs).

Applied retroactively to the sibling task folder: created `Brain\Sessions\Transcript Scraping & Consolidation\Handoffs\` and moved all 6 handoffs in.

Updated the global convention memory (`feedback_session_handoffs.md`) + MEMORY.md index to reflect the new path: `Brain\Sessions\{Task-Theme}\Handoffs\{Month} {Day}{ord} {topic} Session.md`. Future handoffs default there; older templates that don't mention the subfolder are treated as stale.

### 3. `CELH/derived/` → `CELH/Model Output/` rename

User-requested folder rename. Used `mv` (git bash), updated all operational references:
- 3 skill SKILL.md example commands (`financials-extract`, `financials-reconcile`, `financials-playground`)
- `playground_architecture.html` (2 path refs)
- `ROADMAP.md` (key-paths table)
- Latest handoff `April 22nd Playground Polish Session.md` (pipeline invocation + key-paths table)

Deliberately did NOT update the two older handoffs (`April 22nd Multi-Skill Framework Session.md`, `April 22nd Novels Disambiguation Session.md`) — treated as historical records frozen at their original state. A cold next session reads the latest handoff + ROADMAP, both of which are current.

### 4. `model-write` skill built end-to-end (from scratch)

User pivot at session start: **build the xlsx from scratch, not from the old `CELH Financial Model.xlsm` template**. Huge simplification — no macro preservation, no `.bak` dance, no ManualInsertPlan, no cross-sheet formula fragility. Layout is ours to define.

Decisions locked:
- Output: `Brain\Knowledge\Model Schema\CELH\Model Output\CELH_model.xlsx`
- v1 sheets: **ANNL P&L, BALANCE SHEET, CASH FLOW** (QTR P&L skipped — no 10-Q data loaded)
- Columns: historicals sorted chronologically + forecast columns `FY2025E`–`FY2030E` appended right
- Plain `.xlsx`, no macros
- Column headers normalized via `Period` model: 10-K → `FY{year}`; 10-Q → `Q{Q} FY{year}` (never `raw_period_label`)

Scaffolded at `~\.claude\skills\model-write\` with `SKILL.md` + `scripts\write.py`. Installed `openpyxl` in the shared venv at `financials-schema/.venv/`.

Core algorithm:
1. `resolve_row_positions(ledger)` — groups mappings by `(sheet, model_row)` so multiple rule_ids at the same row collapse into one excel row; new_rows get positioned via `position_note` regex-anchor parsing (`(N)` or `row N`), or explicit `model_row` if set, or fallback to end of sheet.
2. `build_column_layout(filings)` — union of period_end_dates per sheet from all validated filings, sorted ascending; append forecast labels.
3. `collect_writes(filings, superseded)` — flatten all validated items to `{(sheet, rule_id, period_end_date): (filing_date, value)}`; newer filing wins on period overlap; drops items with superseded `ledger_rule_id`.
4. `build_workbook(...)` — writes headers (bold, navy fill), row labels (bold), value cells (number format `#,##0;(#,##0)`), zero-fills empty historicals (0), forecast-column tint (light gray), freeze at B2.

First run: 344 cells, 3 sheets × (18/41/72 rows × 4/3/4 historical periods + 6 forecast).

### 5. Row-dedup bug + latest-decided_date label tiebreaker

First build produced duplicate rows (e.g. "Note Receivable" appeared 3× on BS, "Accounts Payable" twice on CF). Root cause: I keyed the row map on `rule_id` but multiple ledger mappings share a `model_row` (e.g. MAP-BS-003 / MAP-BS-024 / MAP-BS-033 all at BS row 12). Fix: key on `(sheet, model_row)` for mappings; new_rows stay keyed on rule_id. Rows dropped: ANNL P&L 24→18, BS 41→33, CF 72→41.

Second issue: on collapsed rows, which label wins? User: *"Make sure the latest filing is what was used for names when there is clash."* Implemented a `_upsert_label` helper that takes `(decided_date, rule_id)` as the tiebreak key — latest date wins, rule_id breaks date ties lexicographically (MAP-CF-070 > MAP-CF-036, so "Accounts Payable" beats "Change in A/P and Accrued (legacy)").

### 6. Ledger `Delta`/`Δ` label cleanup (28 renames)

User: *"We should probably remove delta from all these items as well."* Enumerated all CF entries (21 mappings + 5 new_rows) with `Delta` or `Δ` prefix; applied renames via Python script. Also dropped redundant `(change)` parentheticals on `MAP-CF-070/071/072`. Moved `Accrued Promo` from shared row 27 → its own row 26. Row 27 now holds the 3 merged `Other Current Liabilities` entries (collapsed via dedup).

### 7. Ledger hygiene pass (superseded + anchors + row assignments)

User: *"Yes go ahead. Make sure the latest filing is what was use for names when there is clash."* Triggered a deeper cleanup:

- **Duplicate rule_id fixed:** the older `NEW-CF-009` ("Repurchase of Common Stock, Tax Withholdings", 2026-04-16) renamed to `NEW-CF-012`; the newer `NEW-CF-009` ("Acquisition of Big Beverages", 2026-04-22) kept.
- **6 entries marked `superseded_by`:** `NEW-CF-003` (duplicate of `NEW-CF-010` Note Receivable), `NEW-CF-004`/`NEW-CF-005` (redundant with `MAP-CF-070`/`MAP-CF-071`), `MAP-CF-031` (dup of `NEW-CF-001` Loss on Disposal), `MAP-CF-063` (dup of `NEW-CF-011` Proceeds from Common), `NEW-CF-008` (placeholder template `Acquisition of [entity]`). model-write respects `superseded_by` and skips those items.
- **7 position_note anchors added** (`NEW-CF-002/006/007/008/009/010/012`) so the parseable `(N)` regex finds an anchor.
- **Explicit `model_row` set** on `NEW-CF-011` (→ 41, above Proceeds from Preferred at 42 — but then rolled back to anchor-based positioning to avoid collapsing with Stock Options at row 41).
- **`MAP-CF-038 Accrued Distributor Termination` → model_row=30** (WC slot between Deferred Revenue at 29 and CFO at 31).
- **`NEW-CF-011` position_note order fix:** initial "immediately above Proceeds from Preferred (42)" matched `(42)` first → sorted AFTER Preferred. Rewrote as "after Proceeds from Stock Options (41), before Proceeds from Preferred" so the anchor regex picks `(41)` → position 41.001 → correct slot.

### 8. Tool improvements to model-write

- `resolve_row_positions` returns `(rule_to_excel, row_labels)` as two separate maps; `build_row_labels` was removed.
- `_parse_anchor` supports both `\((\d+)\)` and `\brow\s+(\d+)\b` patterns.
- `resolve_row_positions` and `collect_writes` skip entries with `superseded_by`.
- new_rows with explicit `model_row` go through the mapping path (collapse with any mapping at the same row).
- Summary report prints accurate distinct-row counts (was reporting `len(rule_to_excel)` which double-counted collapses).

### 9. Zero-fill empty historical cells

User: *"We should have 0s where no data is available."* Added a post-write pass: for each `(excel_row, historical_col)` cell, if value is None, write `0` with `#,##0;(#,##0)` format. Forecast columns stay blank (reserved for `model-calc`).

### 10. CF subtotal SUM formulas

User: *"Any item that is a sum formula should have a top black border as well."*

First attempt used `item.section` tags to determine range — fell into a bug where CFF range extended to `=SUM(B31:B41)`, sweeping FX Effect + Net Change in Cash + Cash at Beg/End (below-the-line rows that `extract` also tags as `financing` because the section state machine doesn't reset after the last subtotal). Fix: walk rows top-to-bottom in order, bounds each subtotal to `[section_start, subtotal_row-1]`. Matches `validate.py::partition_cash_flow` semantics.

Result:
- r25 CFO = `=SUM(B2:B24)`
- r30 CFI = `=SUM(B26:B29)`
- r37 CFF = `=SUM(B31:B36)`

Formulas cover all columns (historical + forecast — forecast stays 0 until `model-calc` fills items). Bolded, top black border via `SUBTOTAL_BORDER = Border(top=Side(style="thin", color="000000"))`.

### 11. BS subtotal SUM formulas with cascading

For BS, subtotal rows don't exist as ledger entries — they need to be inserted. Rather than using openpyxl `insert_rows` (which has known edge cases with styles and shifted formulas), built a layout rebuilder `insert_bs_subtotal_slots(bs_rule_to_excel, bs_labels, bs_row_section)` that:

1. Buckets current BS rows by their item-level `section` tag (CURRENT_ASSETS, NON_CURRENT_ASSETS, CURRENT_LIABILITIES, NON_CURRENT_LIABILITIES, MEZZANINE, EQUITY).
2. Re-emits rows in canonical section order with subtotal rows inserted between sections.
3. Emits a grand total row at the end: `Total Liabilities, Mezzanine & Stockholders' Equity`.
4. Returns new `{rule_id: excel_row}`, `{excel_row: label}`, and a list of subtotal specs with formula type (`sum`, `cascade`, `grand`).

Cascading formulas prevent double-counting:
- `Total Current Assets = SUM(B2:B8)`
- `Total Assets = B9 + SUM(B10:B17)` (TCA + NC items, not `SUM(B2:B17)` which would double-count TCA)
- `Total Current Liabilities = SUM(B19:B26)`
- `Total Liabilities = B28 + SUM(B29:B32)`
- `Total Stockholders' Equity = SUM(B35:B38)` (skips mezz at B34)
- `Total L+M+SE = B33 + B34 + B39`

As a side effect, the rebuilder re-buckets strays: `NEW-BS-009 Accrued Distributor Termination Fees` was being appended at the bottom of BS (its position_note lacked a `(N)` anchor); after rebuild it lands in `current_liabilities` at r27 based on its item-level section tag.

### 12. Lease collision — M-1 validator + reconcile B-guard + ledger fix

During BS rebuild, found that two "Lease Liability - Operating" rows landed badly:
- r28 `Lease Liability - Operating Current` (with real data FY22=661 FY23=980 FY24=3265) placed in NCL section — wrong bucket
- r40 `Lease Liability - Operating NC` stranded at the bottom, unclassified

Root cause in FY2024 10-K: raw label `"Lease liability operating leases"` (no "current"/"NC" qualifier). Reconcile fuzzy-matched both occurrences to the same ledger rule (`MAP-BS-026` = "lease liability obligation-operating leases"), but the two items had different `section` tags from extract (current_liabilities + non_current_liabilities) because they appeared in different sections on the BS page. Downstream `model-write` had no way to tell them apart.

User asked: "Shouldn't the Pydantic validation have ensured this didn't happen?" Correct observation — existing validators check arithmetic identities (items sum to subtotals) and shape/types, but **no validator was checking semantic consistency across items**. The BS-1..BS-6 rules use `partition_balance_sheet` (walks items in document order, partitions by subtotal anchors), which correctly bucketed each item by its source position, so sums balanced — passing validation despite the collision.

Shipped both defensive layers:

- **A. `validate.py::run_m1`** — new rule "M-1": every `ledger_rule_id` in use must tag all its items with the same `section`. Emits one `ValidationResult` per colliding rule_id with severity=fail, including example raw labels and the fix recipe. Wired into `validate_filing` as a filing-wide check (not per-period).
- **B. `reconcile.py` section-collision guard** — after mapping all items, groups by `ledger_rule_id`, checks section uniqueness; if any rule_id has >1 distinct section, sys.exit with a descriptive error + the affected items. Prevents colliding MappedFilings from being written in the first place.

**Ledger fix**: added `MAP-BS-034` (filing_section=current_liabilities → row 33 Operating Current) and `MAP-BS-035` (filing_section=non_current_liabilities → row 39 Operating NC), mirroring the pre-existing `MAP-BS-031`/`MAP-BS-032` pattern for Finance leases. Both ship with `decided_date: 2026-04-23`.

Final pipeline state: **36/36 pass on both filings**, 354 cells written, all 4 lease rows in their correct sections in the xlsx.

### 13. Playground alignment nit

User screenshot showed `decisions_ledger` box misaligned with `financials-reconcile` in `playground_architecture.html`. Moved `decisions-ledger` from y=325 to y=418 (centers both at y=443 given their heights).

## Current state

### Built and verified

- All 5 shipped skills (`financials-extract`, `financials-reconcile`, `financials-validate`, `financials-playground`, `model-write`) working end-to-end.
- Shared schema package `financials-schema` — 16/16 pytest pass.
- FY2023 10-K + FY2024 10-K both: **36/36 validation rules PASS** (35 original + M-1).
- `CELH_model.xlsx` built cleanly: 18 rows ANNL P&L, 39 rows BS (includes 5 subtotal formulas + grand total), 40 rows CF (includes 3 subtotal formulas). 354 cells populated across 4 historical periods + 6 empty forecast columns.
- Architecture + schema meta-playgrounds current.
- Decisions ledger: **126 mappings + 24 new_rows + 7 structural + 1 rename**, with 6 `superseded_by` entries and ~15 `filing_section` discriminators.

### Not yet built

- `model-calc` — the next payoff: fills FY2025E–FY2030E forecast columns.

### Rule coverage matrix

| Period | BS rules | CF rules | X rules | M rules |
|---|---|---|---|---|
| FY2024 | BS-1..6 | CF-1..5 | X-1, X-2, X-4 | M-1 (filing-wide) |
| FY2023 | BS-1..6 | CF-1..5 | X-1, X-2, X-4 | M-1 (filing-wide) |
| FY2022 | BS-1..6 | CF-1..5 | X-1, X-2, X-4 | M-1 (filing-wide) |
| FY2021 | — | CF-1..5 | X-1, X-4 | M-1 (filing-wide) |

FY2021 BS gaps remain (blocked on older-era reconcile novels in `2022_CELH_10-K.pdf`).

## Pipeline invocation (copy-paste to resume)

```bash
cd "C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema"
source financials-schema/.venv/Scripts/activate

# Full pipeline on FY2023 10-K (reports FY2021/FY2022/FY2023 comparatives)
PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/financials-extract/scripts/extract.py" \
    --ticker-root "CELH/" \
    --pdf "C:/Users/rodin/Desktop/Pl3 Celsius Case Study/data/CELH Reporting/Financial Statements/2024_CELH_10-K.pdf" \
    --out "CELH/Model Output/raw_2024_10K.json" \
    --filing-type "10-K" --filing-date "2024-02-29"
PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/financials-reconcile/scripts/reconcile.py" \
    --ticker-root "CELH/" --in "CELH/Model Output/raw_2024_10K.json" --out "CELH/Model Output/mapped_2024_10K.json"
PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/financials-validate/scripts/validate.py" \
    --ticker-root "CELH/" --in "CELH/Model Output/mapped_2024_10K.json" --out "CELH/Model Output/validated_2024_10K.json"

# Full pipeline on FY2024 10-K (reports FY2022/FY2023/FY2024 comparatives)
PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/financials-extract/scripts/extract.py" \
    --ticker-root "CELH/" \
    --pdf "C:/Users/rodin/Desktop/Pl3 Celsius Case Study/data/CELH Reporting/Financial Statements/2025_CELH_10-K.pdf" \
    --out "CELH/Model Output/raw_2025_10K.json" \
    --filing-type "10-K" --filing-date "2025-02-27"
PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/financials-reconcile/scripts/reconcile.py" \
    --ticker-root "CELH/" --in "CELH/Model Output/raw_2025_10K.json" --out "CELH/Model Output/mapped_2025_10K.json"
PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/financials-validate/scripts/validate.py" \
    --ticker-root "CELH/" --in "CELH/Model Output/mapped_2025_10K.json" --out "CELH/Model Output/validated_2025_10K.json"

# Build the xlsx from both validated filings
PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/model-write/scripts/write.py" \
    --ticker-root "CELH/" \
    --in "CELH/Model Output/validated_2024_10K.json" \
    --in "CELH/Model Output/validated_2025_10K.json" \
    --out "CELH/Model Output/CELH_model.xlsx"

# Multi-filing playground (unchanged)
python "C:/Users/rodin/.claude/skills/financials-playground/scripts/build_playground.py" \
    --in "CELH/Model Output/validated_2024_10K.json" \
    --in "CELH/Model Output/validated_2025_10K.json" \
    --out "CELH/Model Output/explorer_multi.html"
```

## Open decisions / pending work

1. **Build `model-calc`** — the next big skill. Fills FY2025E–FY2030E forecast columns with growth + margin + WC-ratio projections, base scenario only. Because BS+CF subtotals are already live formulas, `model-calc` only needs to project line items — subtotals recompute automatically. Scoped per prior sessions: no GLP-1/SNAP overlays.
2. **IS subtotal SUM formulas** on ANNL P&L (Gross Profit, Operating Profit, Pre-Tax Income, Net Income). Small follow-on to the existing CF/BS subtotal logic in `model-write` — currently IS doesn't have live formulas at these subtotal rows, just values from the filings.
3. **Pull FY2025 10-K from EDGAR.** HTML-only at `https://www.sec.gov/Archives/edgar/data/1341766/000134176626000024/celh-20251231.htm`. Needs `weasyprint` / `playwright` / HTML-aware extract branch. Expect novels from wording drift (FY2025 is a new era).
4. **`NEW-CF-011 Proceeds from Common`** — currently positioned via position_note anchor `(41)` so it sorts between Stock Options (41) and Preferred (42). Data is 0 across all years so far (first issuance hasn't happened). Leave as-is until a filing populates it.
5. **Δ-vs-Delta ledger duplicates still live side-by-side** at shared rows — each row has multiple rule_ids mapped to the same model_row. Dedup collapses them at render time, but this is ledger clutter. Worth a hygiene pass: decide whether to mark the older Δ-prefixed variants as `superseded_by` their Delta siblings.
6. **Row 27 on CF still has 5 rule_ids** mapped to it (Δ Accrued Promo, Δ Other Current Liabilities, Delta Accrued Promo, Delta Other Current Liab, Delta Other Current Liabilities). After the label rename pass, labels collapse to 2 distinct (Accrued Promo + Other Current Liabilities), but the dedup only uses one. Confusing; not breaking.
7. **BS-7 RE roll-forward validator** still deferred (needs cross-filing prior-period BS data).
8. **Known bugs carry-forward:**
   - `Acquisition of Big Beverages` label truncation (pdfplumber artifact) — non-urgent.
   - Windows console cp1252 encoding on Δ / — chars. Workaround: `PYTHONIOENCODING=utf-8`.
9. **Multi-era reporting-style drift** — still the biggest architectural TODO. Blocks FY2021 BS coverage from `2022_CELH_10-K.pdf`.
10. **Semantic extract pivot** (roadmap Later item #2) — late-stage. Replace label-based ledger matching with Pydantic-typed semantic recognition. Subsumes the multi-era drift solution if pursued.

## Key file paths

| Purpose | Path |
|---|---|
| Roadmap | `C:/Users/rodin/Desktop/Brain/Sessions/CELH Model/ROADMAP.md` |
| Prior handoff | `C:/Users/rodin/Desktop/Brain/Sessions/CELH Model/Handoffs/April 22nd Playground Polish Session.md` |
| This handoff | `C:/Users/rodin/Desktop/Brain/Sessions/CELH Model/Handoffs/April 23rd Model-Write Shipped Session.md` |
| model-write skill | `C:/Users/rodin/.claude/skills/model-write/` |
| model-write script | `C:/Users/rodin/.claude/skills/model-write/scripts/write.py` |
| Validate skill (M-1 added) | `C:/Users/rodin/.claude/skills/financials-validate/scripts/validate.py` |
| Reconcile skill (B-guard added) | `C:/Users/rodin/.claude/skills/financials-reconcile/scripts/reconcile.py` |
| Shared venv (openpyxl installed) | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/financials-schema/.venv/` |
| CELH config / anomalies / ledger | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/CELH/{config,anomalies,decisions_ledger}.json` |
| CELH model outputs (renamed from `derived/`) | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/CELH/Model Output/` |
| **The built xlsx** | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/CELH/Model Output/CELH_model.xlsx` |
| Old xlsm (reference only, untouched) | `C:/Users/rodin/Desktop/Pl3 Celsius Case Study/data/derived/CELH Financial Model.xlsm` |
| Source PDFs | `C:/Users/rodin/Desktop/Pl3 Celsius Case Study/data/CELH Reporting/Financial Statements/` |
| Pipeline architecture playground | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/playground_architecture.html` |
| Pydantic schema playground | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/playground_schema.html` |
| FY2025 10-K on EDGAR (HTML-only) | `https://www.sec.gov/Archives/edgar/data/1341766/000134176626000024/celh-20251231.htm` |
| Handoff convention memory | `C:/Users/rodin/.claude/projects/C--Users-rodin/memory/feedback_session_handoffs.md` |

---

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
6. **`## Open decisions / pending work`** — numbered list of unresolved items. Each one should state the *decision* or *action* needed, not just a vague "look into X". If a decision is blocked on user input, say so.
7. **`## Key file paths`** — two-column table: Purpose | Path. Use absolute paths. Include scheduled task names and external system references.
8. **`## How to create the next handoff`** — paste this exact section verbatim. Never drop it; never let the template drift without updating all copies forward.

### Quality bar

- Write so the next session (cold, no conversation history) can act without re-asking you questions.
- Prefer concrete over abstract.
- Capture *why* a design choice was made when it's non-obvious. Code shows what; handoffs should show why.
- If you deleted, renamed, or moved files, explicitly mention it — the next session will otherwise hunt for the old paths.
- Keep it self-contained. Don't say "as discussed" — write out the discussion outcome.
