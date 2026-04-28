---
type: session-handoff
date: 2026-04-28
topic: Forecast-UX rebuild (per-row YoY/QoQ basis toggle, 5-year horizon, chained driver defaults), Net Income (Loss) Attributable to Common Shareholders as a live subtotal, LINK_TO_CF for IS Pref Div mirror of CF, GEN-IS-013 sign_convention fix, per-sheet column-alignment fix, LibraryEntry schema sync. Five new memory rules saved.
tags: [session, forecast-ux, basis-toggle, subtotals, link-to-cf, sign-convention, schema-sync]
---

# April 28th — Forecast UX & Subtotal Hardening Session

Picks up from `Archive\April 28th BS Closure Session.md` (same day; that session shipped Path B closure and BS-tied $0 across all three tickers). This session was an analyst-UX pass driven by user observations on the freshly-closed model: forecasts only ran 4 years instead of 5, driver overrides didn't propagate, NI Attrib Common was a hardcoded number not a formula, IS Preferred Dividends had no forecast, and a column-alignment defect was inflating BS ratios by ~2× silently behind the Path B plug. Next session opens with the playground sync that's now ~5 framework changes behind.

## Starting state

- All three tickers tied BS at $0 across forecast quarters per prior session, but with several latent defects masked by the plug.
- model-calc forecast horizon set to 4 fiscal years (off-by-one).
- Driver forecast cells defaulted to `last_hist_col` — overriding any cell didn't propagate forward.
- IS Pref Div forecasts blank; NI Attrib Common rendered filer-extracted hardcodes; Income Allocated forecasts blank.
- `LibraryEntry` Pydantic model out of sync with library JSON (missing `cf_delta_target` from prior session).

## Work done this session

### 1. Per-row growth basis toggle (YoY vs QoQ)

New `growth_basis` field on `DriverSpec`, threaded from `config.json:growth_basis` through `infer_drivers(growth_basis_default=...)` into every GROWTH-kind spec. New "Basis" column at column B on IS DRIVERS (period cols shift to start at C); each GROWTH row shows a yellow YoY/QoQ dropdown (DataValidation list). Historical Growth % formula and forecast Revenue formula on QTR P&L both wrap the choice in `IF($B{r}="QoQ", prev_qtr_ref, prev_year_ref)`. Single fall-back when only one prior period exists. Required `build_driver_tab` to also return `col_idx_by_period` and `write_forecast_cells` to take a `driver_col_by_period_by_group` map — driver-tab cols and source-sheet cols no longer align (Basis col shifts IS DRIVERS by 1) so cross-sheet refs need period-keyed lookup. CELH defaulted to `qoq`; PEP/PG keep `yoy` default. Per `feedback_forecast_ux.md`.

### 2. Forecast horizon off-by-one fix

`compute_forecast_periods` was using `last_year + (n_years - 1)` → CELH (Q4 anchor) got 16 quarters not 20. Changed to `last_year + n_years`. CELH now 20Q (Q1 FY2026E..Q4 FY2030E), PEP 23Q (mid-FY anchor + 5 full years), PG 22Q. Last forecast period is always Q4 of some fiscal year so ANNL `=SUM(Q1..Q4)` aggregation always reflects a complete fiscal year.

### 3. Chained driver forecast defaults

Forecast cells used to all default to `={last_hist_col}{r}` — overriding Q1 FY2026E left Q2..Qn untouched. Replaced with `={target_col-1}{r}`, so each forecast cell chains off the immediately prior period. Single override propagates forward; mid-stream override re-routes. Applied to GROWTH / RATIO_OF_REV / RATIO_OF_COGS / DSO / DIO / DPO / TAX_RATE / PAYOUT_RATIO / HOLD_LAST / DOLLAR_INPUT. ZERO kept as literal 0 (its semantic is non-recurring; do not propagate).

### 4. Per-sheet column-alignment fix in historical ratio formulas

`_historical_driver_formula` was building P&L cell refs as `'QTR P&L'!{L(src_col)}{rev_row}` — using the BS row's column index for the P&L lookup. CELH's QTR BS starts at Q4 FY2022 but QTR P&L starts at Q1 FY2022 (3-quarter offset). Result: Deferred Other Costs / Revenue computed Q4 FY2025 BS divided by Q1 FY2025 Revenue (seasonally tiny quarter), inflating ratios ~2.18×. Path B plug absorbed the error so BS still tied at $0 — silent failure. Added `pl_col` parameter; caller passes `qtr_hist_cols_by_sheet["QTR P&L"].get((y, q))`. CELH Q4 FY2025 Deferred Other Costs ratio: 234% → **107%** (correct). Per `feedback_per_sheet_period_alignment.md`.

### 5. Net Income (Loss) Attributable to Common Shareholders → live subtotal

Row 16 used to render filer-extracted hardcodes (CELH FY2023 = $181,991). Added handler in `write_is_subtotals` after the existing NI Less NCI block: `=NI + Preferred Dividends + Income Allocated to Participating Preferred` (components carry natural filer signs). Added "Net Income (Loss) Attributable to Common Shareholders" to `DERIVED_LABELS_IS` so model-calc skips creating a redundant driver row. CELH NIC live formula matches filer to $1 across FY2021–FY2025 after the GEN-IS-013 fix. Per `feedback_subtotals_and_links.md`.

### 6. GEN-IS-013 sign_convention=negative

Library entry "Income Allocated to Participating Preferred" had no `sign_convention`, so `match_raw_item._derive_sign_from_label` keyword-scanned the alias "Income allocated to participating..." and matched `"income"` → `sign_convention="positive"` → `value = abs(value)` → flipped CELH's correctly-extracted -17,348 to +17,348. NIC formula then over-summed by 2× the magnitude of Allocated. Declared `sign_convention: "negative"` on GEN-IS-013 (per-entry wins over keyword scan, per the carried `feedback_charge_means_expense.md` precedent). Income Allocated to Participating Preferred is structurally always a deduction from common.

### 7. eps-section dollar items get explicit driver kinds

`infer_is_kind` had a blanket `if section == "eps": return SKIP` — correct for per-share / share-count rows (which `_is_skip_label` already handles before the section dispatch) but wrong for Pref Div and Income Allocated. Special-cased: Pref Div → `LINK_TO_CF` (single shared driver on CF side, IS row mirrors); Income Allocated → `HOLD_LAST` (no CF counterpart; analyst overrides per-quarter). Other eps items still SKIP.

### 8. New DriverKind: LINK_TO_CF

Symmetric to existing LINK_TO_IS. New `cf_link_source: Optional[Tuple[str, str]] = None` field on DriverSpec; `_build_spec` sets to `("QTR CF", "Preferred Dividends")` for LINK_TO_CF. Added to `DRIVER_TAB_KINDS` (so a driver row is created on IS DRIVERS) AND `COMPUTED_KINDS` (so the cell is a derivation formula not a yellow input). New `_computed_forecast_formula` branch emits `='QTR CF'!{L(cf_col)}{cf_row}`. Verified: IS PrefDiv Q1 FY2026E = -$14,307 = CF PrefDiv Q1 FY2026E. Single override surface — analyst changes CF DRIVERS Pref Div, both QTR CF and QTR P&L update.

### 9. LibraryEntry schema sync

`load_generic_library` validates every entry through `LibraryEntry` (Pydantic, `extra="forbid"`). Prior session added `cf_delta_target` to GEN-BS-016 in the library but didn't update the schema model. Surfaced 2026-04-28 when re-extracting CELH for the GEN-IS-013 fix — every filing failed with `Extra inputs are not permitted` on the FIRST entry. Added `cf_delta_target: str | None = None` field to `LibraryEntry` with comment pointing at model-calc as the consumer. Per `feedback_library_entry_schema_sync.md`.

### 10. Preferred dividend accounting verification

User raised "shouldn't preferred dividends also reduce preferred equity?" Verified CELH is cash-pay (Convertible Preferred Stock balance flat at $824,488 from FY2022→FY2024 despite cash dividends; jump to $1,759,975 in FY2025 was a Series B issuance, not accretion). Current model is correct: Pref Div reduces Cash (CF) and RE (rollforward inputs include CF Pref Div); Preferred Equity stays flat. Documented PIK alternative for future tickers in `feedback_preferred_dividend_accounting.md`. No code change.

## Current state

- **CELH**: 12 filings clean through full pipeline. 20 forecast Q (Q1 FY2026E..Q4 FY2030E). NIC matches filer to $1 across all 5 historical years. IS PrefDiv = CF PrefDiv. BS gap = $0.
- **PEP**: 13 filings clean. 23 forecast Q. BS gap = $0. (No preferred — LINK_TO_CF / NIC handlers inert.)
- **PG**: 14 filings clean. 22 forecast Q. BS gap = $0. (Same.)
- **Library**: GEN-IS-013 + sign_convention=negative; otherwise unchanged.
- **Schema**: LibraryEntry now declares `cf_delta_target`.

## Open decisions / pending work

1. **NEXT SESSION OPENS WITH** — playground sync. `playground_architecture.html` + `playground_schema.html` are now ~5 framework changes behind. Owe LS_KEY bump from v9 cumulatively for: RESIDUAL_PLUG, residual_plug_sources, cf_delta_target, APIC/AOCI rollforwards, dynamic FORECAST_LABELS, annual→QTR mirror (carried from BS Closure), 5-year horizon, chained defaults, growth_basis + Basis col, NIC live formula, LINK_TO_CF, eps-section policy, GEN-IS-013 sign, LibraryEntry cf_delta_target. Single dedicated session.
2. **Then resume** — systematic-driver-determination work (carried from prior session). Replace remaining `_label_contains` checks (Cash, Goodwill, Debt, RE, APIC, AOCI, etc.) with structural canonical metadata.
3. **Active propagating rules** — playground sync, no-heuristic policy, no validator sign flips, no duplicate anchor subtotals, joint CELH+PG (+PEP) regression on every framework change. All carried.
4. **Future PIK preferred ticker** — would need ROLLFORWARD on Preferred Equity row with IS Pref Div as input. Not in scope for current 3 tickers. Per `feedback_preferred_dividend_accounting.md`.

## Key file paths

| Purpose | Path |
|---|---|
| This handoff | `Brain\Sessions\CELH Model\Handoffs\April 28th Forecast UX & Subtotal Hardening Session.md` |
| Prior handoff (archived) | `Brain\Sessions\CELH Model\Handoffs\Archive\April 28th BS Closure Session.md` |
| Roadmap | `Brain\Sessions\CELH Model\ROADMAP.md` |
| model-calc inference (eps-section special-cases, growth_basis threading) | `~\.claude\skills\model-calc\scripts\inference.py` |
| model-calc orchestrator (forecast horizon, chained defaults, Basis column, col-alignment fix, LINK_TO_CF formula) | `~\.claude\skills\model-calc\scripts\calc.py` |
| model-calc DriverSpec (growth_basis, cf_link_source fields; LINK_TO_CF kind) | `~\.claude\skills\model-calc\scripts\driver_models.py` |
| model-write IS subtotals (NIC handler) | `~\.claude\skills\model-write\scripts\write.py:805-840` |
| LibraryEntry schema (cf_delta_target field added) | `Brain\Knowledge\Model Schema\financials-schema\financials_schema\lookup.py:170-220` |
| Generic library (GEN-IS-013 sign_convention=negative) | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` |
| **CELH workbook** | `Brain\Knowledge\Model Outputs\CELH\CELH_model.xlsx` |
| **PEP workbook** | `Brain\Knowledge\Model Outputs\PEP\PEP_model.xlsx` |
| **PG workbook** | `Brain\Knowledge\Model Outputs\PG\PG_model.xlsx` |
| Playgrounds (owe v9 → v13+ cumulative) | `Brain\Knowledge\Model Schema\playground_{architecture,schema}.html` |

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
