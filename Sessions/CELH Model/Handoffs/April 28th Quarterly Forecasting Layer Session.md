---
type: session-handoff
date: 2026-04-28
topic: Built `model-qtr-derive` (single-quarter sheets layer over YTD) and rebuilt `model-calc` from scratch as a quarterly-first forecasting engine. Drivers infer per-row from canonical filing_section + label heuristics (no hand-curated DRIVER_SPECS), then centralize on IS/BS/CF DRIVERS tabs as the single place the user overrides. Source-sheet forecast cells = lookups (value/computed kinds) or rate-applied formulas (ratio kinds). Several sign bugs caught + fixed along the way (Net Change in Cash circular, RE rollforward, dividend payout sign, PP&E rollforward direction, DTA rollforward). PEP_model_v9.xlsx is the locked end-state.
tags: [session, model-calc-rebuild, model-qtr-derive, quarterly-forecasting, driver-inference, centralized-drivers]
---

# April 28th — Quarterly Forecasting Layer Session

Picks up from `Archive\April 27th PEP Onboarding Session.md` (third ticker onboarded; harness locked at 39 filings; framework hardened). This session shipped the §20 model-calc rebuild from the roadmap — quarterly-first forecasting with a brand-new driver-inference engine and centralized DRIVERS tabs. Next session opens with making driver determination fully systematic so adding a new ticker requires zero manual driver-kind selection (Open §1).

## Starting state

- CELH (12) + PG (14) + PEP (13) = 39 filings clean through validate; PEP_model_v3.xlsx golden (model-write-only, no forecast layer).
- model-calc (legacy, hand-curated DRIVER_SPECS) and model-write existed; QTR sheets were YTD-shaped (Q2 FY24 = first-half value, not single-quarter).
- `_calc_legacy.py` snapshot saved before rebuild.
- No-heuristic policy + all carried propagating rules (per `feedback_structural_over_heuristic.md` etc).

## Work done this session

### 1. New skill `model-qtr-derive`

Adds 3 single-quarter sheets to a model-write workbook. Renames existing `QTR P&L` / `QTR BS` / `QTR CF` → `YTD P&L` / `YTD BS` / `YTD CF` (the data they always held was YTD). Creates new `QTR P&L` / `QTR BS` / `QTR CF` with cell-reference formulas: `Q1 = YTD Q1`; `Q2 = YTD Q2 − Q1`; `Q3 = YTD Q3 − Q2`; `Q4 = ANNL FY − YTD Q3` for IS/CF; BS = direct mirror (point-in-time, Q4 = ANNL). ANNL row references resolved **by label** not by index — caught a real bug on PEP CF where `Indirect Tax Impact` (annual-only) shifts every row by 1 vs YTD. Auto-chains from model-write via dynamic import. EPS rows skipped (per-share isn't linearly subtractable). 9-sheet workbook is the new baseline shape.

### 2. model-calc full rebuild — three new files

`scripts/calc.py` (orchestrator + workbook indexers + driver-tab + write-forecast + ANNL aggregation), `scripts/inference.py` (section→DriverKind engine), `scripts/driver_models.py` (Pydantic `DriverKind` enum + `DriverSpec` class). Old `calc.py` archived as `_calc_legacy.py`.

### 3. DriverKind enum (15 kinds)

Ratio kinds (rate user-input): GROWTH, RATIO_OF_REV, RATIO_OF_COGS, DSO_RATIO, DIO_RATIO, DPO_RATIO, TAX_RATE, PAYOUT_RATIO. Value kinds (dollar user-input): HOLD_LAST, ZERO, DOLLAR_INPUT. Computed kinds (no user input): LINK_TO_IS, BS_DELTA, ROLLFORWARD. Pass-through: DERIVED (cascade SUMs already on workbook), SKIP (EPS / shares).

### 4. Inference engine

Walks every QTR sheet row, looks up canonical's `filing_section` from merged generic + ticker-ledger map (keyed by `(sheet_group, label)` to avoid cross-sheet collision class). Section + label-substring heuristics route to a DriverKind. Examples: `current_assets` + label contains "receivable" → DSO_RATIO; `equity` + label contains "retained earnings" → ROLLFORWARD with NI/Common-Div/Pref-Div anchors; ticker `new_rows[]` entries default to ZERO (one-time events like Juice Transaction, TCJ Act). Structural NWC detection: a CF operating row matches BS_DELTA iff its label is a member of QTR BS current_assets/current_liabilities label set — sign comes from which set matched. No label-text regex for AR / AP / Inventory.

### 5. Centralized DRIVERS tabs (per user request)

Every non-SKIP / non-DERIVED row gets a row on its group's DRIVERS tab. Driver historical formulas: ratio kinds compute (Rev/COGS/PreTax/NI denominators); value/computed kinds mirror the source value. Driver forecast formulas: ratio + HOLD_LAST + ZERO + DOLLAR_INPUT are yellow inputs (default = last historical for straight-line, 0 for ZERO); LINK_TO_IS / BS_DELTA / ROLLFORWARD are computed (no input). Source-sheet forecast cells: pure lookup `=DRIVERS!{col}{row}` for value/computed kinds; rate-applied formula (e.g., `Rev × DRIVERS!{rate_cell}`) for ratio kinds. Single override surface.

### 6. Forecast horizon + ANNL aggregation

5 fiscal years from year of last historical quarter. PEP: Q2 FY2026E .. Q4 FY2030E (19 quarters). ASSUMPTIONS tab with Days in Quarter = 91 (DSO/DIO/DPO denominator). ANNL forecast cells = `=SUM(QTR Q1+Q2+Q3+Q4)` for IS/CF; `=QTR Q4` for BS. EPS / shares-outstanding skipped on aggregation (per-share isn't linearly additive).

### 7. Subtotal pattern propagation

DERIVED rows on QTR sheets need cascade formulas in forecast columns (model-qtr-derive only mirrored historical YTD subtotals, not synthesizing forecast-column SUMs). Translation: walk YTD subtotal cells, find the SUM/+ formula pattern, regex-replace the column letter to each forecast column. Compatible with both `=SUM(B5:B12)` and `=B14+SUM(B15:B19)` patterns.

### 8. Sign bugs caught + fixed

(a) Net Change in Cash circular: model-write was including the Net Change row itself in `cash_other_rows` so the SUM referenced its own row → Excel circular. Fixed `model-write/scripts/write.py:1287` to exclude `net_change_row` from the SUM range. (b) RE rollforward: dividends were in `outputs` (subtracted) but CF dividends are signed-negative — subtracting flipped to positive, growing RE incorrectly. Moved to `inputs` (added). (c) PP&E rollforward: CapEx in `inputs` was wrong direction. CapEx is signed-negative on CF; subtracting gives the positive add to PP&E. Moved both CapEx + D&A to `outputs`. (d) Dividend forecast: leading `-` in PAYOUT_RATIO formula assumed user inputs positive payout %, but historical Div/NI is naturally negative. Dropped the negation — same sign-preserving pattern as ratio_of_rev for negative-rendered opex. (e) DTA: was HOLD_LAST; user flagged it should rollforward by `-CF Provision for Deferred Income Taxes`. Wired ROLLFORWARD with provision in outputs.

### 9. PEP rebuilt end-to-end

`PEP_model_v9.xlsx` is the new state — 13 sheets (ASSUMPTIONS + 3 ANNL + 3 YTD + 3 QTR + 3 DRIVERS), 91 specs inferred (8 ZERO for PEP-specific one-offs, 25 hold_last, 12 ratio_of_rev, 5 bs_delta, 4 skip, 4 rollforward incl. DTA, 1 each growth/tax/dso/dio/payout/link_to_is, 15 derived), 1,368 forecast cells written.

## Current state

- **model-qtr-derive**: shipped, auto-chains from model-write. 9-sheet workbook baseline.
- **model-calc**: rebuilt. Quarterly-first. Centralized DRIVERS tabs as the single override surface.
- **Driver inference**: 15 kinds, section+label-based. ~85% systematic; some kind decisions still depend on label-substring matches (Cash / Goodwill / Debt / etc.) — this is what next session targets.
- **Workbook**: PEP_model_v9.xlsx clean. CELH and PG have not been re-run on the new model-calc.
- **Memory**: no new feedback rules saved this session (would have been: "ratio kinds keep formula on source sheet; value/computed kinds get driver-tab lookup" but that's structural, lives in code).

## Open decisions / pending work

1. **NEXT SESSION OPENS WITH**: make driver-kind determination fully systematic. Currently some kinds are decided by label-substring matches (`_label_contains(label, "receivable")` → DSO; `_label_contains(label, "goodwill")` → HOLD_LAST). Goal: replace with structural signals — `us_gaap_concept` mappings, library-declared `driver_kind` field, calc-linkbase-derived position in the canonical declaration order, etc. Adding a new ticker should require zero `_label_contains` calls firing as fallbacks.
2. **Run CELH + PG through model-calc rebuild**. Sanity-check across 3 tickers. Likely surfaces edge cases in inference.
3. **Active propagating rule** (carry every handoff): playground-sync. `playground_architecture.html` + `playground_schema.html` need updates for: model-qtr-derive node + edges; model-calc rebuild (driver tabs centralized, DriverKind enum, inference engine); ASSUMPTIONS tab; new Pydantic class (`DriverSpec`). Bump `LS_KEY` v9 → v10 (was already owed from PEP session, now owed v9 → v11 with this session's deliverables).
4. **No-heuristic policy** (active propagating rule per Tier C 2026-04-27): inference engine still uses some `_label_contains` checks. The "structural"-only rewrite for driver inference is exactly Open §1.
5. **No validator sign flips** + **no duplicate anchor subtotals from cascade injection** — both still active propagating rules.
6. **DTL stays HOLD_LAST**: PEP has both DTA and DTL; the CF Provision moves DTA in our model. DTL drift is accepted v1 simplification (per user 2026-04-28).
7. **PEP-specific labels in DRIVER tabs**: Juice Transaction / Product Recall / TCJ Act all show as ZERO with the canonical label. Will straight-line to 0 across forecast horizon.

## Key file paths

| Purpose | Path |
|---|---|
| This handoff | `Brain\Sessions\CELH Model\Handoffs\April 28th Quarterly Forecasting Layer Session.md` |
| Roadmap | `Brain\Sessions\CELH Model\ROADMAP.md` |
| **New skill** model-qtr-derive | `~\.claude\skills\model-qtr-derive\` (SKILL.md + scripts/build.py) |
| **Rebuilt** model-calc | `~\.claude\skills\model-calc\scripts\{calc,inference,driver_models}.py` |
| Legacy model-calc (for reference) | `~\.claude\skills\model-calc\scripts\_calc_legacy.py` |
| model-write (Net Change fix) | `~\.claude\skills\model-write\scripts\write.py:1287` (cash_other_rows_no_self) |
| **PEP final workbook** | `Brain\Knowledge\Model Schema\PEP\Model Output\PEP_model_v9.xlsx` |
| Generic library | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` |
| Playgrounds (need v9 → v11 bump) | `Brain\Knowledge\Model Schema\playground_{architecture,schema}.html` |

## How to create the next handoff

Write at end of session under `Brain\Sessions\{Task-Theme}\Handoffs\{Month} {Day}{ord} {topic} Session.md`. **Target: ~800–1200 words; hard ceiling 1500.**

### Required steps

1. **Archive prior handoffs.** Move every `*.md` file in the task's `Handoffs\` root into `Handoffs\Archive\`. The root must contain exactly one file when you're done: today's new handoff.
2. **Update `ROADMAP.md`** — bump `last_session` field to point at the new handoff filename.
3. **Write the new handoff** in the `Handoffs\` root using the structure below.

### Structure

1. **YAML frontmatter** — `type`, `date` (absolute YYYY-MM-DD), `topic` (one sentence), `tags`.
2. **Title** matching filename.
3. **One-paragraph intro** — prior handoff reference (now in `Archive\`) + one sentence on what this session did + one sentence on what the next session should do.
4. **Starting state** — 3–5 bullet points.
5. **Work done this session** — numbered `### N.` subsections grouped by subsystem. Why over what.
6. **Current state** — bullet list, one line per subsystem. Numbers and status.
7. **Open decisions / pending work** — numbered, 1–2 lines each. Include the active playground-sync rule. Flag unresolved user questions and **explicitly highlight any fix that should open the next session.**
8. **Key file paths** — two-column table. Absolute paths. Only load-bearing files.
9. **How to create the next handoff** — paste this section verbatim.

### Consolidation rules

- Don't list every library entry / ledger row added — cite file + count + non-obvious decisions.
- Don't re-explain code. Reference by function/file name.
- Reverted exploration: one line.
- Memory rules referenced not duplicated — say "per `feedback_X.md`".
- Cold-start reader picks this up and can act. No re-asking.
