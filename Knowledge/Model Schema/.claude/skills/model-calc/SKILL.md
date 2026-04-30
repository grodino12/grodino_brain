---
name: model-calc
description: Add a quarterly-first forecasting layer to a model-write workbook (post-model-qtr-derive). Infers driver kinds per row from canonical filing_section + label (no hand-curated specs), extends QTR P&L / BS / CF with 5 years of forecast quarter columns, builds IS DRIVERS / BS DRIVERS / CF DRIVERS tabs with historical formulas + yellow user-input cells, writes forecast formulas on QTR sheets (growth %, % of revenue, DSO/DIO/DPO, tax rate, payout ratio, BS deltas, rollforwards, cross-sheet links), and aggregates ANNL forecast cells from QTR (SUM for IS/CF; Q4 for BS). Use after model-write + model-qtr-derive have produced the 9-sheet xlsx.
---

# model-calc

Layer 4 part 3 of the multi-skill financials pipeline. Reads a built
`.xlsx` from `model-write`, adds three driver tabs (`IS DRIVERS`,
`BS DRIVERS`, `CF DRIVERS`), and saves in place (or to a separate `--out`).

Drivers are computed via Excel formulas that reference the cells on
`ANNL P&L`, `BALANCE SHEET`, and `CASH FLOW`. Live — if the user edits a
historical cell, the driver recomputes automatically. Forecast columns
(`FY2025E`..`FY2030E`) are left blank in v1; a later iteration wires in
forecast assumptions (hold-last-year for ratios, linear decay to terminal
for revenue growth, etc.).

## CLI

```
model-calc \
    --ticker-root <path to ticker folder> \
    --in          <input .xlsx from model-write> \
   [--out         <output .xlsx; defaults to --in>]
```

### Example

```
model-calc \
    --ticker-root "Brain/Knowledge/Model Schema/Ticker Libraries/CELH/" \
    --in  "Brain/Knowledge/Model Outputs/CELH/CELH_model.xlsx"
```

## Drivers

### IS DRIVERS
- Revenue Growth % — YoY on `Net Sales / Revenue`
- COGS % of Revenue
- SG&A % of Revenue
- Interest Income (Expense) $ — raw P&L cell (expense-positive convention — negative = income)
- FX / Other Income $ — sum of `Foreign Currency Gain (Loss)` + `Other Income (Expense)` (expense-positive)
- Effective Tax Rate % — `Income Tax (Benefit) Expense` / `Pre-Tax Income (Loss)`

### BS DRIVERS
**Current Assets:**
- DSO (days) — AR / Revenue × 365
- DIO (days) — Inventories / COGS × 365
- Note Receivable - Current % of Revenue
- Deferred Other Costs - Current % of Revenue
- Prepaid Expenses % of Revenue

**Current Liabilities:**
- DPO (days) — AP / COGS × 365
- Accrued Expenses % of Revenue
- Income Taxes Payable % of Revenue
- Accrued Distributor Termination Fees % of Revenue
- Accrued Promotional Allowance % of Revenue
- Lease Liability - Operating - Current % of Revenue
- Lease Liability - Finance - Current % of Revenue
- Deferred Revenue - Current % of Revenue
- Other Current Liabilities % of Revenue

### CF DRIVERS
- D&A $ — raw CF cell
- SBC $ — raw CF cell
- CapEx $ — raw CF cell (`Purchase of PP&E`)
- Preferred Dividends $ — raw CF `Dividends Paid`
- Share Repurchases $ — raw CF cell
- Net Debt $ — (all lease liabilities) − (Cash & Cash Equivalents + Restricted Cash). Signed: positive = net debt, negative = net cash.

## How it finds cells

For each sheet, builds a lookup:
- **Row by canonical label** (column A of the sheet, rows 2..max)
- **Column by period label** (row 1 of the sheet, cols B..max)

Driver formulas resolve references at build time. If the referenced cell
doesn't exist on the source sheet (e.g. BS has no FY2021 column for CELH),
that driver's cell is left blank — no broken formula.

Runtime division errors are guarded with `IFERROR(..., 0)` so the number
format renders `--` on zero/divide-by-zero. Blank driver cells remain
visually blank (distinguishing "data not in xlsx" from "computed zero").

## Number formats

| Kind          | Format                |
|---------------|-----------------------|
| growth/ratio  | `0.0%;(0.0%);"--"`    |
| days_ratio    | `0.0;(0.0);"--"`      |
| dollar        | `#,##0;(#,##0);"--"`  |
| net_debt      | `#,##0;(#,##0);"--"`  |

## What the ticker root must contain

- `config.json` — ticker metadata (for CLI guard)

## Dependencies

- `openpyxl` (xlsx read/write)

## v1 scope and deferred items

v1 ships:
- Historical formulas for all drivers listed above
- Live references (recomputes on source-cell edits)
- Forecast columns blank, lightly tinted

Deferred to later iterations:
- Forecast assumption rows (hold-last-year / linear decay / user overrides)
- Non-current BS drivers (PP&E turnover, intangibles amortization schedule, etc.)
- Equity rollforward (RE += NI − PrefDiv, APIC += SBC, etc.)
- Cross-model integration hooks for GLP-1 / SNAP overlays
- Multi-scenario switch (base / bull / bear)

## Status

Phase 1 — historical only. Forecast-assumption wiring tracked under `model-calc`
in `Brain/Sessions/CELH Model/ROADMAP.md`.
