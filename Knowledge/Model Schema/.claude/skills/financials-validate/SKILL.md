---
name: financials-validate
description: Run accounting-identity + cross-statement validators on a MappedFiling. Checks BS-1..BS-5, IS-4, CF-1..CF-4 — 10 filer-tie rules total. Blocks the pipeline on fail. Use after financials-reconcile has produced a MappedFiling JSON.
---

# financials-validate

Layer 3 of the multi-skill financials pipeline. Takes a `MappedFiling` from
`financials-reconcile` and runs 10 filer-tie rules: every rule sums extracted
line items and ties the total to a filer-reported subtotal. No cross-statement
roll-forwards (BS-7) or cross-filing checks live here — they belong in higher
layers when those land. Produces a `ValidatedFiling`. Refuses to proceed if
any rule fails.

## CLI

```
financials-validate \
    --ticker-root <path to ticker folder> \
    --in          <input MappedFiling JSON> \
    --out         <output ValidatedFiling JSON>
```

## Rules

| Rule | Check |
|------|-------|
| BS-1 | Total Current Assets = sum of CA line items |
| BS-2 | Total Assets = TCA + sum of non-current-asset line items |
| BS-3 | Total Current Liabilities = sum of CL line items |
| BS-4 | Total Liabilities = TCL + sum of non-current-liability line items |
| BS-5 | Total Stockholders' Equity = sum of equity components |
| IS-4 | Net Income = Pre-Tax Income + signed Tax |
| CF-1 | CFO + CFI + CFF + FX effect = Net Change in Cash |
| CF-2 | Filer-reported CFO = sum of operating-section components |
| CF-3 | Filer-reported CFI = sum of investing-section components |
| CF-4 | Filer-reported CFF = sum of financing-section components |

All 10 rules are implemented and run on every filing. CF-2/CF-3/CF-4 were
added 2026-04-25 (per-section subtotal tie-out, shared `_run_cf_section()`
helper).

## Tolerances

- Absolute: $1K (statements are in thousands)
- Relative: 0.1% of expected value
- A rule passes if gap is within EITHER tolerance.

## Sectioning via subtotal boundaries

Balance sheet items don't have explicit `section` tags. The validator walks
line items in document order and uses subtotal rows ("Total current assets",
"Total Assets", etc.) as section boundaries. Line items between two subtotals
belong to the section the first subtotal is summing.

## Failure behavior

- Any rule with `severity="fail"` → exit code 1, no output file written.
- All rules `pass` or `warning` → write ValidatedFiling JSON.

## Dependencies

- `financials-schema` (shared Pydantic package)

## Status

Stable. 10 filer-tie rules. Tested across 14 PG filings (3 10-Ks +
11 10-Qs covering FY2023 → H1 FY2026): 0 FAILs.
