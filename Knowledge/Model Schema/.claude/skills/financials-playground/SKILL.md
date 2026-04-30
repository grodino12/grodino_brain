---
name: financials-playground
description: Render a self-contained HTML QA explorer over one or more ValidatedFiling JSON files. Tabbed BS / IS / CF tables with period columns, YoY highlights, citation tooltips, and a validation results pane. Use after financials-validate has produced a validated_*.json — for sanity-checking values before model-write.
---

# financials-playground

Layer 4 (part 1) of the multi-skill financials pipeline. Single Python script
that reads one or more `ValidatedFiling` JSON files and emits a self-contained
HTML explorer.

## CLI

```
python scripts/build_playground.py \
    --in  <path to validated_*.json>  [--in <other.json> ...] \
    --out <path for output HTML>
```

### Example

```
python scripts/build_playground.py \
    --in  "C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/Ticker Libraries/CELH/validated_2024_10K.json" \
    --out "C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/Ticker Libraries/CELH/explorer_2024_10K.html"
```

Multiple `--in` flags merge filings — each filing contributes its statement
periods to the same tabs (e.g. pass FY2024 + FY2023 10-Ks to get a 5-year view).

## What the HTML contains

- **Header bar** — ticker, filing list, source PDFs, validation status badge (pass / fail count)
- **Tabs** — `BALANCE SHEET` · `INCOME STATEMENT` · `CASH FLOW` · `VALIDATION`
- **Per-statement tables** — one row per `(model_sheet, model_row, model_label)`;
  one column per period (most recent first); subtotal rows highlighted; section
  group headers inserted between sections
- **YoY highlighting** — adjacent-period delta > 20% orange, > 50% red
- **Citation tooltip** — hover any value cell to see source PDF page + raw line hint
- **Raw / Model label toggle** — header button switches the leftmost column between
  the canonical model label and the raw filing label
- **Validation tab** — all 26 rules with rule_id, expected, actual, gap, severity, message;
  grouped by family (BS / CF / X)

## Inputs assumed

- The input(s) must be valid `ValidatedFiling` JSON, i.e. produced by
  `financials-validate`. The script does not re-validate; it trusts the structure.
- Subtotal rows (`row_type == "subtotal"`, `model_sheet == "_subtotal"`) are
  shown but visually distinguished from real mapped rows.

## Dependencies

- Python 3.11+ standard library only. No external packages.

## Status

**Built.** Renders cleanly for the CELH 2024 10-K (8 statements, 260 mapped items,
26 validation results). See `02_pipeline_design.md` in the Model Schema docs for
where this fits in the Layer 4 trio (`financials-playground` / `model-write` / `model-calc`).
