---
type: session-handoff
date: 2026-04-28
topic: Made the forecast balance sheet balance to $0 across all 3 tickers (PEP/PG/CELH) by implementing Path B closure — BS-driven CF where every BS row's delta is absorbed by a CF entry. Diagnosed root causes (BS+CF forecast independently → identity drift), introduced RESIDUAL_PLUG, library-declared cf_delta_target, APIC/AOCI rollforwards capturing SBC + FX equity offsets, ZERO defaults for non-anchor CF rows, dynamic FORECAST_LABELS, annual→QTR row mirror in model-write, forecast cell formatting carried from historicals. Cleaned up stale workbooks; one canonical xlsx per ticker.
tags: [session, bs-closure, path-b, residual-plug, cf-delta-target, forecast-formatting]
---

# April 28th — BS Closure Session

Picks up from `Archive\April 28th Quarterly Forecasting Layer Session.md` (same day; that session shipped model-qtr-derive + the model-calc rebuild and left a forecast BS that didn't tie). This session diagnosed why and shipped Path B — a BS-driven CF closure that forces the BS identity to hold by construction. PEP, PG, CELH all balance at $0 across every forecast quarter. Next session opens with Open §1 (carried) — make driver-kind determination fully systematic, replacing remaining `_label_contains` checks with structural canonical metadata.

## Starting state

- Prior session left PEP_model_v9 with a forecast BS gap that grew to +$23,757 by Q4 FY2030E (peaks at every Q1 of a new fiscal year).
- model-calc fully rebuilt, 15 DriverKinds inferred per row.
- CELH (12) + PG (14) had not been re-run on the new model-calc.
- 39 filings clean through validate; harness golden.

## Work done this session

### 1. BS gap diagnosis

Quantified the gap row-by-row. Three classes of leak surfaced:
- Unmapped WC BS rows where filer's BS-vs-CF labeling didn't match (PEP "Accrued Expenses" on BS but "AP" + "Other CL" on CF — neither side picked it up, ΔBS leaked).
- Phantom CF flows: rows with non-zero historical values and no BS counterpart held flat (Issue/Repay LT Debt, Share Repurchases) — drained Cash without reducing the matching BS row.
- Non-cash add-backs (SBC, FX Effect) that hit CFO but had no BS-side rollforward → Cash created out of nothing.

### 2. Path B closure architecture

New `DriverKind.RESIDUAL_PLUG` on `driver_models.py`. New `DriverSpec.residual_plug_sources: list[(sheet, label, is_liab)]` field. Rewrote `infer_cf_kind` to default non-rollforward / non-WC operating rows to ZERO instead of HOLD_LAST; tag "Other Operating Items" canonical as RESIDUAL_PLUG; force investing non-CapEx and financing non-dividend rows to ZERO. Added BS_DELTA wiring pass after both BS and CF inference: exact-label match first, then `cf_delta_target` library declaration as fallback. Added `_computed_forecast_formula` branch that emits `=±(BS[t]-BS[t-1])` summed over `residual_plug_sources`.

### 3. Library declaration: `cf_delta_target`

Added `cf_delta_target` field reader on `inference.py:load_label_section_map` (also reads ticker ledger's `section` field as a fallback to library's `filing_section` — caught CELH's NEW-BS-009 Distributor Termination Fees that wasn't surfacing in the plug because section name differed). Declared `cf_delta_target: "Accounts Payable"` on `GEN-BS-016 Accrued Expenses` so PEP's accrued ΔBS routes to CF AP.

### 4. APIC + AOCI rollforwards

Extended BS inference: APIC → ROLLFORWARD with input = CF SBC; AOCI → ROLLFORWARD with input = CF FX Effect on Cash. Captures equity offsets that were previously creating leaks. Plus closure pass protection: any CF row referenced as a rollforward input or output that ended up ZERO gets upgraded to HOLD_LAST (would otherwise nullify the rollforward — caught DTA's CF Provision row defaulting to ZERO incorrectly). Plus demoting non-cash CF add-backs (RATIO_OF_REV in operating section) to ZERO when they don't anchor a BS rollforward — caught PEP's ROU Amortization, which has no separate ROU asset row in our BS layout.

### 5. Equity / mezzanine plug extension

Final closure pass: include non-rollforward, non-DERIVED BS rows (HOLD_LAST + ZERO) in residual_plug_sources whether section is asset, liability, equity, or mezzanine. Equity drops are sign-treated as liability-side for BS identity. Caught CELH's Distributor Termination Fees (current_liabilities ZERO with $264K boundary delta), PG's ESOP Debt Retirement Reserve (equity ZERO), and CELH's Pepsi Mezzanine memo rows.

### 6. Restricted Cash double-rollforward fix

Inference engine matched both "Cash & Cash Equivalents" and "Restricted Cash" to ROLLFORWARD with input = Net Change in Cash → both BS rows added the SAME ΔCash, doubling cash drift. Split: only "Cash & Cash Equivalents" rollforwards via Net Change; "Restricted Cash" → HOLD_LAST.

### 7. Dynamic FORECAST_LABELS in model-write

`FORECAST_LABELS = [f"FY{y}E" for y in range(2025, 2031)]` was hardcoded. Filers whose latest 10-K is FY2025 (CELH, PEP, PG) got a duplicate `FY2025` + `FY2025E` column. Replaced with per-sheet dynamic computation: `last_fy = max(hist_map labels); forecast = [FY{last_fy+1+i}E for i in 0..N_FORECAST_YEARS-1]`. Constant `N_FORECAST_YEARS = 6`.

### 8. Annual→QTR row mirror in model-write

CELH's 10-Q condensed BS omits Treasury Stock (Reg S-X Article 10 condensed presentation; ~83% of FY2025 -$48K Treasury came from a single Q4 buyback program absent from prior 10-Q YTD CFs). Annual BALANCE SHEET had the row; QTR BS didn't. QTR forecast subtotal pattern (translated from YTD) inherited the omission, leaving a constant -$48,226 BS gap. Fix in model-write: for each parallel sheet pair (ANNL P&L↔QTR P&L, BALANCE SHEET↔QTR BS, CASH FLOW↔QTR CF), mirror any rule_id present on annual but missing on QTR — insert after the most recent shared anchor in annual document order. Structural (rule_id-based, not label-text); user confirmed acceptable.

### 9. Forecast cell formatting carried from historicals

`aggregate_annl_forecasts` in model-calc was writing ANNL forecast formulas without setting number_format / font / border → cells rendered as "General". Same issue on QTR side: `write_forecast_cells` and `copy_subtotal_pattern_to_forecast` only set hardcoded LINE_ITEM_FMT / SUBTOTAL_FMT, missing the top-border on subtotal rows. Fixed both: sample formatting from the last populated historical cell on the same row (number_format, font, border) and apply identically to forecast cells.

### 10. Workbook cleanup

Deleted 12 stale snapshots (CELH_model_v5, PG_model_v2/v3/v5, PEP_model_v3 through v10, plus pre-fix `{TICKER}_model.xlsx`). Renamed `*_balance_test.xlsx` → `{TICKER}_model.xlsx`. Each ticker folder now has exactly one canonical workbook built under the new pipeline.

### 11. Folder layout reorg (post-session)

After main work shipped, restructured `Knowledge/` so the only artifact under `Model Outputs/{TICKER}/` is the deliverable workbook. All per-ticker workspace data — `config.json`, `decisions_ledger.json`, `anomalies.json`, `validated_*.json`, `explorer_*.html`, `.cache/` — now lives at `Knowledge/Model Schema/Ticker Libraries/{TICKER}/`. `pattern_libraries/`, `financials-schema/`, and `_regression/` stay where they were under `Model Schema/`. Updated:
- `reconcile.py:446`, `write.py:159` — auto-resolve generic library via `ticker_root.parent.parent / "pattern_libraries"` (one extra level since ticker folders are now nested under Ticker Libraries).
- `_regression/run.py` — added `validated_dir()` helper, `cache_dir()` now points at `ticker_root / .cache`, `model_output_dir()` returns `Knowledge/Model Outputs/{ticker}/` for workbook only.
- 5 SKILL.md examples (extract/reconcile/playground/model-calc/model-write) and `_regression/README.md` updated.
- `playground_architecture.html` decisions_ledger / source_citations / xlsm path nodes updated.

Saved `project_brain_layout.md` memory so future sessions don't re-derive the convention. ROADMAP.md not updated (per user) — its path table is now stale; treat the table in this handoff as authoritative.

## Current state

- **PEP**: 19 forecast quarters Q2 FY2026E..Q4 FY2030E, BS gap = $0 max abs.
- **PG**: 18 forecast quarters Q3 FY2026E..Q4 FY2030E, BS gap = $0 max abs.
- **CELH**: 16 forecast quarters Q1 FY2026E..Q4 FY2029E, BS gap = $0 max abs.
- **model-calc**: closure logic shipped — Path B BS-driven CF holds by construction.
- **model-write**: annual→QTR row mirror, dynamic FORECAST_LABELS.
- **Library**: 1 `cf_delta_target` declaration on GEN-BS-016 (Accrued Expenses).
- **No new feedback rules saved** (rules from prior session still active).

## Open decisions / pending work

1. **NEXT SESSION OPENS WITH** (carried from prior session): make driver-kind determination fully systematic. Replace remaining `_label_contains` checks (Cash, Goodwill, Debt, RE, APIC, AOCI, etc.) with structural canonical metadata (`us_gaap_concept` mappings, library-declared `driver_kind` field, calc-linkbase position).
2. **Active propagating rule**: playground sync — `playground_architecture.html` + `playground_schema.html` need updates for: RESIDUAL_PLUG DriverKind, residual_plug_sources field, cf_delta_target library field, APIC/AOCI ROLLFORWARD wiring, dynamic FORECAST_LABELS, annual→QTR row mirror. LS_KEY bump owed v9 → v12 cumulatively (prior 2 bumps still owed).
3. **No-heuristic policy** active (per `feedback_structural_over_heuristic.md`). The annual→QTR mirror was reviewed by user and ruled structural (rule_id + document-order based, no label-text matching). Add as carried rule.
4. **Active propagating rule**: no validator sign flips, no duplicate anchor subtotals from cascade injection.
5. **Treasury Stock CELH**: small position-marker — the only annual-only row that triggered the mirror logic. If future filers have annual-only rows with non-stable forecasts, HOLD_LAST default may overstate; analyst can override on driver tab.
6. **DTL still HOLD_LAST**: PEP carries both DTA and DTL. CF Provision moves DTA only; DTL drift accepted v1.

## Key file paths

| Purpose | Path |
|---|---|
| This handoff | `Brain\Sessions\CELH Model\Handoffs\April 28th BS Closure Session.md` |
| Prior handoff (archived) | `Brain\Sessions\CELH Model\Handoffs\Archive\April 28th Quarterly Forecasting Layer Session.md` |
| Roadmap | `Brain\Sessions\CELH Model\ROADMAP.md` |
| model-calc inference | `~\.claude\skills\model-calc\scripts\inference.py` |
| model-calc orchestrator | `~\.claude\skills\model-calc\scripts\calc.py` |
| model-calc DriverKind enum | `~\.claude\skills\model-calc\scripts\driver_models.py` |
| model-write annual→QTR mirror | `~\.claude\skills\model-write\scripts\write.py:344-378` |
| model-write dynamic FORECAST_LABELS | `~\.claude\skills\model-write\scripts\write.py:30,477-498` |
| Generic library (137 entries; +1 cf_delta_target) | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` |
| **PEP canonical workbook** | `Brain\Knowledge\Model Outputs\PEP\PEP_model.xlsx` |
| **PG canonical workbook** | `Brain\Knowledge\Model Outputs\PG\PG_model.xlsx` |
| **CELH canonical workbook** | `Brain\Knowledge\Model Outputs\CELH\CELH_model.xlsx` |
| Per-ticker workspace (config, ledger, validated_*, .cache, explorers) | `Brain\Knowledge\Model Schema\Ticker Libraries\{TICKER}\` |
| Playgrounds (need v9 → v12 bump) | `Brain\Knowledge\Model Schema\playground_{architecture,schema}.html` |

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
