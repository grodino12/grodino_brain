---
name: model-qtr-derive
description: Add 3 single-quarter sheets (QTR P&L / QTR BS / QTR CF) to a workbook produced by model-write. Renames existing YTD-shaped quarterly sheets to YTD P&L / YTD BS / YTD CF and writes new sheets containing cell-reference formulas that derive single-quarter values from the YTD + ANNL sheets. Auto-runs at the end of model-write — usually invoked indirectly. Run standalone via the CLI when you need to re-derive on an existing workbook without rebuilding from validated JSONs.
---

# model-qtr-derive

Layer 4 part 3 of the financials pipeline. Takes the workbook `model-write`
just produced (6 sheets — 3 ANNL + 3 YTD-shaped QTR) and adds 3 single-quarter
sheets that decompose YTD into single-quarter values via formulas. Result: a
9-sheet workbook.

## Why this skill exists

10-Q filings report **YTD** numbers on the IS and CF (Q1 = 1 quarter, Q2 = 6
months, Q3 = 9 months) and **point-in-time** balances on the BS. `model-write`
preserves those YTD numbers as-filed because they're how the filer reports
them. But for analysis — trend, seasonality, sequential growth — single-quarter
values are what users actually want. This skill computes them.

A 10-Q never reports Q4 standalone (Q4 = full year minus 9-month YTD), so Q4
values are derived from the ANNL sheets.

## CLI

```
model-qtr-derive --in <workbook.xlsx>
```

In-place edit of the workbook. Backs up nothing — assume model-write is the
source of truth and re-runnable.

## What gets done

1. **Rename existing sheets:**
   - `QTR P&L` → `YTD P&L`
   - `QTR BS`  → `YTD BS`
   - `QTR CF`  → `YTD CF`

2. **Create 3 new sheets** (`QTR P&L`, `QTR BS`, `QTR CF`) with row layout
   mirroring the YTD sheet exactly (same labels, same row indices, same
   formats). Header row 1 lists target columns chronologically: `Q1 FY2023`,
   `Q2 FY2023`, …, `Q4 FY2023`, `Q1 FY2024`, …

3. **Per-cell formulas:**

   | Sheet | Quarter | Formula |
   |---|---|---|
   | QTR P&L / QTR CF | Q1 | `='YTD P&L'!{ytd_q1_col}{row}` |
   | QTR P&L / QTR CF | Q2 | `='YTD P&L'!{q2_col}{row} - 'YTD P&L'!{q1_col}{row}` |
   | QTR P&L / QTR CF | Q3 | `='YTD P&L'!{q3_col}{row} - 'YTD P&L'!{q2_col}{row}` |
   | QTR P&L / QTR CF | Q4 | `='ANNL P&L'!{fy_col}{row} - 'YTD P&L'!{q3_col}{row}` |
   | QTR BS | Q1 / Q2 / Q3 | `='YTD BS'!{qN_col}{row}` |
   | QTR BS | Q4 | `='BALANCE SHEET'!{fy_col}{row}` |

   A column is only emitted if all its dependencies exist. PEP example: FY2026
   has only Q1 YTD as of 2026-04-27 → new sheet shows just `Q1 FY2026` for
   FY2026 (Q2/Q3/Q4 omitted until later 10-Qs land).

4. **EPS / share-count rows**: skipped — left blank. Subtraction doesn't
   work for per-share metrics (share count drifts within the year). Detected
   by label substring match on `per share` / `eps` / `shares`.

5. **Subtotals**: same formula treatment as line items — no recompute needed.
   Subtraction is linear, so `(YTD_subtotal_Q3 - YTD_subtotal_Q2) =
   single_quarter_subtotal`. Subtotal cells inherit the bold + border + dollar
   format from the YTD source.

## Auto-chain from model-write

`model-write` calls `derive_quarterly(out_path)` (the importable function in
`scripts/build.py`) at the very end of `build_workbook()`, after the workbook
is saved. No flag to opt out — every model-write run produces a 9-sheet
workbook. To run only the base 6 sheets, comment the call out manually.

## Outputs

Same workbook, in place. Stdout report:

```
model-qtr-derive: added 3 single-quarter sheets to <path>
  QTR P&L:  N rows × M quarters
  QTR BS:   N rows × M quarters
  QTR CF:   N rows × M quarters
```

## Dependencies

- `openpyxl` (workbook read/write)

## v1 scope and deferred

v1 ships:
- Renames + adds 3 sheets
- Cell-reference formulas (no hardcoded values)
- EPS / share-count rows skipped
- Q4 derived from ANNL when both ANNL[FY] and YTD[Q3] exist

Deferred:
- EPS treatment (would need 3-month EPS column from filer when present)
- Quarterly forecast columns — model-calc rebuild's responsibility (§20 in roadmap)
