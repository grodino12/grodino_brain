---
name: financials-reconcile
description: Map raw filing line-item labels to Excel model rows via the per-ticker decisions ledger. Takes a RawFiling (from financials-extract — PDF or iXBRL path) and outputs a MappedFiling with each line item carrying model_sheet / model_row / model_label. Filing-type aware — 10-Ks feed ANNL sheets (ANNL P&L / BALANCE SHEET / CASH FLOW), 10-Qs feed QTR sheets (QTR P&L / QTR BS / QTR CF). Auto-applies known ledger rules; surfaces novel items for user decision. Use after financials-extract has produced a RawFiling JSON.
---

# financials-reconcile

Layer 2 of the multi-skill financials pipeline. Takes the `RawFiling` from an
extractor and produces a `MappedFiling` — every raw line item now has a
destination in the Excel financial model.

**Filing-type-aware sheet routing (added in the quarterly-support refactor):**
- `filing_type == 10-K` → line items route to the annual sheet family
  (`ANNL P&L`, `BALANCE SHEET`, `CASH FLOW`).
- `filing_type == 10-Q` → line items route to the parallel quarterly family
  (`QTR P&L`, `QTR BS`, `QTR CF`). Before mapping, reconcile drops IS and CF
  statements whose `period_length_weeks` is outside [11, 15] — i.e. the YTD
  6-month / 9-month rows a 10-Q reports alongside the current 3-month period.
  Only the pure 3-month duration is carried into the QTR sheets.

The lookup index is keyed on `(normalized_label, sheet_group, sheet_variant)`
where `sheet_variant ∈ {"ANNL", "QTR"}`. The same concept (e.g. `us-gaap:Revenues`)
can have two ledger entries — one for ANNL P&L row N, one for QTR P&L row M —
and reconcile picks by `filing_type`. Ledgers without QTR entries continue to
work for 10-Ks; 10-Q filings surface novel items for every concept until the
ledger grows QTR entries.

## CLI

```
financials-reconcile \
    --ticker-root <path to ticker folder> \
    --in          <input RawFiling JSON> \
    --out         <output MappedFiling JSON>
```

### Example

```
financials-reconcile \
    --ticker-root "Brain/Knowledge/Model Schema/Ticker Libraries/CELH/" \
    --in          "Brain/Knowledge/Model Schema/Ticker Libraries/CELH/.cache/raw_2024_10K.json" \
    --out         "Brain/Knowledge/Model Schema/Ticker Libraries/CELH/.cache/mapped_2024_10K.json" \
    --novels-out  "Brain/Knowledge/Model Schema/Ticker Libraries/CELH/.cache/novels_2024_10K.json"
```

Add `--dry-run` to preview the mapping + novel items without writing output
or failing on unresolved novel items.

## What the ticker root must contain

- `config.json` — ticker metadata (for the CLI ticker guard)
- `decisions_ledger.json` — the per-ticker mapping rules

## Outputs

A `MappedFiling` Pydantic object serialized to JSON. Each `MappedLineItem`
inherits every field of its `RawLineItem` plus: `model_sheet`, `model_row`,
`model_label`, `mapping_source`, `ledger_rule_id`.

Subtotal rows (labels starting with "Total" or "Subtotal") carry through as
synthetic `MappedLineItem`s with `model_sheet="_subtotal"` and
`row_type="subtotal"` so the validate skill can check accounting identities.

## Matching behavior

1. **Normalize** the raw_filing_label (lowercase, strip punctuation, drop
   articles like "the" / "our", collapse whitespace)
2. **Exact-match** the normalized label against ledger entries
3. If matched → `MappedLineItem` with `mapping_source="ledger_auto"`
4. If not matched → wrap in `NovelItem` with top-3 rapidfuzz suggestions
5. If any `NovelItem` remains after the whole filing is processed, the skill
   **refuses to construct** a `MappedFiling` — user must resolve novel items
   by appending to the ledger, then re-run

## Ledger sections consumed

- `mappings[]` — existing Excel rows (primary)
- `new_rows[]` — rows that need to be inserted (model_row=0 placeholder,
   resolved by `model-write` via ManualInsertPlan)

`structural_decisions`, `renames`, and `validation_overrides` are informational
only at this stage — consumed by downstream skills.

## Dependencies

- `financials-schema` (shared Pydantic package)
- `rapidfuzz` (fuzzy matching for novel-item suggestions)

## Status

Phase 1 — working. Does exact-match lookup + subtotal handling + novel
detection. No interactive prompt yet (future: `--interactive` to walk through
novel items and append confirmed mappings to the ledger).
