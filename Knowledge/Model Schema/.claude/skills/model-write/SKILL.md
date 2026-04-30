---
name: model-write
description: Build a financial model workbook from scratch from one or more ValidatedFiling JSONs. Emits ANNL P&L / BALANCE SHEET / CASH FLOW sheets for 10-K inputs, QTR P&L / QTR BS / QTR CF sheets for 10-Q inputs, or both when mixed. Historical period columns sourced from the filings (FY labels for annual, Q{N} FY{YYYY} labels for quarterly); empty forecast columns (FY2025E..FY2030E) on annual sheets only — quarterly forecasts deferred to model-calc. Row layout derived from the per-ticker decisions ledger (mappings + new_rows). Use after financials-validate produces one or more validated_*.json.
---

# model-write

Layer 4 part 2 of the multi-skill financials pipeline. Takes one or more
`ValidatedFiling` JSONs and writes a fresh `.xlsx` model workbook.

This skill builds from scratch — it does not read or modify any existing
template. The decisions ledger (`mappings[]` + `new_rows[]`) defines the row
layout per sheet; validated filings supply the historical column data;
forecast columns are pre-allocated empty for `model-calc` to fill later.

## CLI

```
model-write \
    --ticker-root <path to ticker folder> \
    --in          <validated_*.json>  [--in <other.json> ...] \
    --out         <path for output .xlsx>
```

### Example

```
model-write \
    --ticker-root "Brain/Knowledge/Model Schema/Ticker Libraries/CELH/" \
    --in "Brain/Knowledge/Model Schema/Ticker Libraries/CELH/validated_2024_10K.json" \
    --in "Brain/Knowledge/Model Schema/Ticker Libraries/CELH/validated_2025_10K.json" \
    --out "Brain/Knowledge/Model Outputs/CELH/CELH_model.xlsx"
```

## What gets built

**Sheets** — chosen based on the filing types in the input set. A sheet is
only emitted if it has at least one row or historical column populated.

| Filing type | Sheet set |
|-------------|-----------|
| 10-K / 8-K / press release | `ANNL P&L`, `BALANCE SHEET`, `CASH FLOW` |
| 10-Q | `QTR P&L`, `QTR BS`, `QTR CF` |
| Mixed input | both sheet sets, filled from their respective filings |

Routing is done via `stmt_to_sheet(statement_type, filing_type)` — no statement
ever crosses families. Reconcile has already applied the 3-month-only filter
to 10-Q statements before this skill sees them (YTD 6-month / 9-month IS+CF
statements dropped), so quarterly sheets receive clean 3-month data.

**Columns per sheet:**
- **Annual sheets:** historical columns = one per unique `period_end_date`,
  labeled `FY{year}`, sorted chronologically. Forecast columns `FY2025E`...
  `FY2030E` appended right of historicals; empty cells for `model-calc` to fill.
- **Quarterly sheets:** historical columns labeled `Q{fiscal_quarter} FY{fiscal_year}`
  to disambiguate quarters within a fiscal year. **No forecast columns** in v1 —
  quarterly forecasts are model-calc's responsibility.
- On period overlap across filings (same period reported in multiple filings),
  **first-filing-wins per (sheet, period)** — every row in that period column
  comes from the oldest filing that reported it. Never mixes rows from
  different filings within the same period column. Eliminates the
  concept-rename double-count class of bug (e.g. PG used a hybrid us-gaap
  concept in 2024-Q3 then split it in 2025-Q3 — per-row dedup would have
  picked both rows; per-period dedup uses 2024-Q3's complete breakdown).

**Rows per sheet:**
- Sourced from the decisions ledger (`mappings[]` + `new_rows[]`) matched to
  each sheet's canonical name. Annual entries have `model_sheet ∈ {BALANCE SHEET,
  CASH FLOW, ANNL P&L, ANNL P&L / QTR P&L}`; quarterly entries use `QTR BS`,
  `QTR CF`, `QTR P&L`. The ledger typically carries separate entries per
  variant (e.g. `us-gaap:Revenues → ANNL P&L row 10` and
  `us-gaap:Revenues → QTR P&L row M`) because quarterly models are often more
  row-granular than annual.
- Entries with assigned `model_row` keep their relative ordering.
- `new_rows[]` entries without a `model_row` are inserted via `position_note`
  parsing and re-numbered densely at emit time.
- `_subtotal` synthetic items from the validated JSON are skipped in v1
  (no live SUM formulas yet — computed visually by user).

**Cells:**
- For each `MappedLineItem`, write `value` at `(resolved_excel_row,
  period_column)` on the correct sheet.
- Period column resolved by `period.period_end_date` via the column map.
- Values written as-is in native statement unit (usually thousands for CELH).

## Outputs

A fresh `.xlsx` at `--out`. No macros, no formulas in v1. Stdout report:

```
Built CELH_model.xlsx
  ANNL P&L:       N rows × M periods
  BALANCE SHEET:  N rows × M periods
  CASH FLOW:      N rows × M periods
  Historical columns: [FY2021 FY2022 FY2023 FY2024]
  Forecast columns:   [FY2025E ... FY2030E]
  Cells written: K
```

## What the ticker root must contain

- `config.json` — ticker metadata (for CLI guard)
- `decisions_ledger.json` — per-sheet row layout source

## Dependencies

- `financials-schema` (shared Pydantic package)
- `openpyxl` (xlsx writing)

## v1 scope and deferred items

v1 ships:
- Writes raw values into the correct `(sheet, row, column)` cells
- Handles period dedup across filings (newer wins)
- Resolves new_row positions from `position_note` anchors

Deferred to later iterations:
- Live SUM formulas for subtotals (currently skipped — `_subtotal` items ignored)
- Number formatting (`#,##0.0` etc.)
- Section headers / grouping styles
- Unit normalization across statements (writes in native unit)
- QTR P&L sheet (blocked on 10-Q data loading)
- Writing back resolved `model_row` values into the ledger

## Status

Phase 1 — in-progress. End-to-end target: CELH FY2023 + FY2024 10-Ks produce a
readable `CELH_model.xlsx` with three sheets, four historical columns, and six
empty forecast columns.
