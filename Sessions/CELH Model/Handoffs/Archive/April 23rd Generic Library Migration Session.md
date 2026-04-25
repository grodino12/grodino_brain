---
type: session-handoff
date: 2026-04-23
topic: Generic line-item mappings cross-ticker library — design + Phase 1 (file creation, 89 entries) + Phase 2 (reconcile loader + tier-based ticker-over-generic precedence) shipped. Phases 3-7 queued. Also: IS subtotal formulas + "--" zero format on sheets + architecture playground made editable + CF investing order fix.
tags: [session, celh, generic-library, migration, reconcile, model-write, architecture]
---

# April 23rd — Generic Library Migration Session

Picks up from `April 23rd Model-Write Shipped Session.md`. This session was supposed to start with IS subtotals and then `model-calc`, but the scope expanded into a substantial architectural shift toward a cross-ticker canonical nomenclature library. **Phases 1-2 of that migration are shipped. Phases 3-7 are queued and need a fresh session.**

## Starting state (beginning of this session)

- `model-write` just shipped (April 23 handoff) — 3 sheets (ANNL P&L / BALANCE SHEET / CASH FLOW), BS + CF live subtotal formulas, 354 cells, 48/48 validators PASS (after M-1 added).
- CELH decisions ledger: 126 mappings + 24 new_rows + 7 structural. All per-ticker.
- Pipeline architecture: `extract` → `reconcile` (per-ticker ledger only) → `validate` → `model-write` → `playground`.
- `model-calc` not yet built.

## Work done this session

### 1. IS subtotal formulas on ANNL P&L (shipped)

- Added `Gross Profit / Operating Profit / Pre-Tax / Net Income` as live SUM formulas:
  - `=B2-B3` (Gross Profit = Revenue − COGS)
  - `=B4-B5` (Operating Profit = GP − OpEx)
  - `=B6+SUM(B7:B9)` (Pre-Tax = OP + signed non-op)
  - `=B10+B11` (Net Income = PT + signed Tax)
- Bold + top-border styling, all 10 columns (historical + forecast).
- After debugging: turned up real **ledger bugs at row 17 (Interest Income collision) + row 18 (FX/FCT collision)**. Fixed.

### 2. IS Pydantic validators IS-1..IS-4 (shipped in `financials-validate/scripts/validate.py`)

- `partition_income_statement()` walks IS items, anchors on canonical subtotal labels (Gross Profit / Operating Income / Pre-Tax / NI), buckets into revenue_cost / opex / non_op / tax.
- Skips below-NI items (Pref Div, NI-to-Common, Participating, FCT, Comprehensive Income).
- Also filters mid-section subtotals like `"Total other income, net"` (extract sometimes tags these as `line_item` instead of `subtotal` — label-based guard).
- Per-period IS-1..IS-4 rules, paired with existing BS-1..6 / CF-1..5 / X-1..X-4 / M-1.
- Both CELH filings now: **48/48 PASS** (up from 36/36).

### 3. Ledger collision fixes (shipped in CELH/decisions_ledger.json)

- `MAP-IS-004` marked `superseded_by: MAP-IS-030` (legacy FX duplicate).
- `MAP-IS-018` marked `superseded_by: "not_modeled"` with note — it was Foreign Currency Translation (OCI / below-NI), wrongly mapped to row 18 alongside above-NI FX loss.
- Fixed `model-write` collision bug: value-write now sums same-filing sibling rule_ids at the same (sheet, row, period), newest-filing-wins across filings. Covers Interest Income sibling siblings (MAP-IS-010/011/031 at row 17).

### 4. Number-format polish on xlsx (shipped in `model-write/scripts/write.py`)

- Subtotal rows: `$#,##0_);($#,##0);"$--"_)` (accountant alignment, dollar sign, `$--` on zero).
- Line items: `#,##0;(#,##0);"--"` (zero → `--`).
- EPS rows (label-detected "EPS"): `$#,##0.00_);($#,##0.00)` (decimal cents).
- Universally applied — every cell displays `$--` or `--` for zero at the format-string level, no code-side scanning needed.

### 5. Architecture playground made editable (shipped in `playground_architecture.html`)

- Toolbar: Select / + Arrow / Delete / Export / Reset.
- Drag nodes to reposition (in Select mode).
- Click arrows to select (wider invisible hit-path for thin strokes); Delete removes.
- **+ Arrow** mode: click source → click target to create edge. Esc cancels.
- Every edit auto-saves to `localStorage` (key `celh-architecture-playground-v1`); survives reloads.
- Export dumps current `NODES` + `EDGES` JSON to clipboard for baking back into the `.html`.
- Reset restores baked-in defaults.
- Also added a permanent `DerivedCalcs → xlsm-model` edge.

### 6. CF investing section reordering

- CELH CF investing was rendering PP&E **last** because `MAP-CF-019` had `model_row=35` (higher than Collections at 34 + anchor-positioned NEW items at 34.00x). Fixed by re-anchoring `NEW-CF-007` (Non-Marketable) and `NEW-CF-009` (Big Beverages) from "after Collections (34)" to "after PP&E (35)" / "after Non-Marketable (35)".
- Order now matches FY2024 10-K: Collections → PP&E → Non-Marketable → Big Beverages.
- **Principle established**: when ledger ordering differs across filings, align to the **latest** filing. Saved to memory (`feedback_ledger_ordering.md`).

### 7. Ledger label hygiene (shipped)

- `MAP-CF-010/033` model_label renamed `Receivables` → `Accounts Receivable`.
- `MAP-CF-012/035` model_label renamed `Prepaids` → `Prepaid Expenses`.
- Established **sign-agnostic label convention** for any item whose sign can flip (Interest Income (Expense), Net Income (Loss), etc.). Saved to memory (`feedback_sign_agnostic_labels.md`).

### 8. **Generic library migration — PHASES 1 + 2 SHIPPED**

The big architectural shift. User's goal: pull the ~80% of line-item mappings that are universal (COGS, Cash, NI, etc.) out of the per-ticker CELH ledger and into a **cross-ticker generic library** at `pattern_libraries/generic_line_item_mappings.json`. Per-ticker ledger keeps only ticker-specific anomalies.

**Key architecture decisions from the walkthrough (91 items confirmed, one at a time with user):**

1. **`model_row` dropped entirely from ledger entries.** Row order is derived dynamically at model-write time from the **latest filing's document order**. Ledger is pure label→concept mapping now.
2. **Sign-agnostic labels everywhere** (Gross Profit (Loss), Net Income (Loss), Interest Income (Expense), etc.).
3. **Latest-filing-wins for order conflicts** across filings.
4. **Canonical labels win over raw filing labels** on the xlsx.
5. **Ticker-over-generic precedence** via `_tier` field (ticker = 10, generic = 0) in reconcile's `select_entry`.
6. **`filing_section` discriminator** for Current/Non-Current pairs (Note Receivable, Lease Liability Operating, Lease Liability Finance, Deferred Revenue, Deferred Other Costs).
7. **`filing_subsection` discriminator** for EPS block (eps vs shares_outstanding).
8. **Income Tax sign flip**: user wants expense-positive, benefit-negative (opposite of filing's natural sign). Scope = **option B (all non-op expenses flipped)**. Not yet implemented — queued for Phase 6.
9. **Items present only in older filings**: append after latest filing's items, preserving their prior filing's position (not dropped).

**Phase 1 shipped:** `pattern_libraries/generic_line_item_mappings.json`
- 89 canonical entries (19 IS, 31 BS, 39 CF)
- 8 subtotals, 3 memos, 10 filing_section disc., 4 filing_subsection disc.
- Aliases capture all known filing-wording variants per concept
- JSON validates cleanly

**Phase 2 shipped:** `reconcile.py` updated
- New `load_generic_library()` + optional auto-resolve from `<ticker-root>/../pattern_libraries/generic_line_item_mappings.json`
- `build_lookup_index(ledger, generic)` now accepts both — expands generic `aliases` into per-alias lookup keys
- Entries carry `_source` ("ticker" / "generic") + `_tier` (10 / 0); `select_entry` prefers high-tier when both match
- `--generic-library` CLI flag for overrides
- **Pipeline regression: 48/48 PASS on FY2024 10-K**

### 9. Items confirmed as CELH-specific (do NOT migrate to generic)

- IS: `Interest Income on Note Receivable` (MAP-IS-011)
- BS: `Deferred Other Costs - Current` + `Deferred Other Costs - Non-Current` (MAP-BS-005, MAP-BS-012); `Accrued Distributor Termination Fees` (NEW-BS-009)
- CF: `Amortization of Deferred Other Costs` (MAP-CF-005); `Accrued Distributor Termination` (MAP-CF-038); `Acquisition of Big Beverages` (NEW-CF-009); `Gain (Loss) on Lease Cancellations` (MAP-CF-060)

### 10. Label renames confirmed (need applying in Phase 3 CELH ledger cleanup)

- `Operating Profit` → `Income (Loss) from Operations`
- `Pre-Tax Income` → `Pre-Tax Income (Loss)`
- `Net Income` → `Net Income (Loss)`
- `Income Taxes` → `Income Tax (Benefit) Expense`
- `Foreign Exchange Loss` → `Foreign Currency Gain (Loss)`
- `Foreign exchange gain (loss)` → `Foreign Currency Gain (Loss)`
- `Loss on Disposal of PP&E` → `Gain (Loss) on Disposal of PP&E`
- `Accumulated Other Comprehensive Loss` → `Accumulated Other Comprehensive Income (Loss)`
- `Deferred Other Costs (Current)` → `Deferred Other Costs - Current` (CELH keeps this)
- `Deferred Other Costs (NC)` → `Deferred Other Costs - Non-Current` (CELH keeps this)
- `ROU Assets - Operating` → `ROU Assets - Operating - Non-Current`
- `ROU Assets - Finance` → `ROU Assets - Finance - Non-Current`
- `Intangibles` → `Intangible Assets`
- `Other Long-Term Assets` → `Other Non-Current Assets`
- `Inventory Obsolescence` → `Inventory Write-Down`
- `Other Items` → `Other Operating Items`
- `Cash at Beginning` → `Cash at Beginning of Period`
- `Cash at End` → `Cash at End of Period`
- `Proceeds from Stock Options` → `Proceeds from Exercise of Stock Options`
- `Proceeds from Preferred` → `Proceeds from Issuance of Preferred Stock`
- `Proceeds from Common` → `Proceeds from Issuance of Common Stock`
- `Repurchase of Common Stock (Tax Withholdings)` → `Share Repurchases` (also absorbs open-market buybacks)
- `Dividends on Series A Pref` → `Dividends` (IS) / `Dividends Paid` (CF)
- `Net Income to Common Shareholders` → `Net Income (Loss) Attributable to Common Shareholders`
- `Income Allocated to Participating` → `Income Allocated to Participating Preferred`
- `GAAP EPS (Basic)` → `Basic Earnings (Loss) per Share`
- `GAAP EPS (Diluted)` → `Diluted Earnings (Loss) per Share`
- `Weighted Avg Shares Outstanding (Basic/Diluted)` → `Weighted Average Shares Outstanding (Basic/Diluted)`
- `Comprehensive Income (memo)` → `Total Comprehensive Income (Loss)`
- `ROU/Lease` → `ROU & Lease Liability, Net`

## Current state

### Built + verified

- All Phase 2 infra works. `reconcile.py` loads both libraries, applies tier scoring, produces identical MappedFilings to pre-migration (because ticker still overrides generic via tier).
- `generic_line_item_mappings.json` validates; 89 entries, no JSON errors.
- CELH FY2023 10-K + FY2024 10-K: **48/48 validators PASS** (unchanged from baseline).
- `CELH_model.xlsx` still writes cleanly.
- Architecture playground: interactive (drag / add arrow / delete / export / reset).

### Not yet done (Phases 3-7, in order)

**Phase 3** — Strip `model_row` from CELH `decisions_ledger.json`. Mark generic-covered entries as `superseded_by: "generic"`. Apply label renames from section 10 above. Keep 7 CELH-specific entries listed in section 9.

**Phase 4** — Refactor `model-write/scripts/write.py` row layout. Currently `resolve_row_positions()` sorts ledger entries by `model_row`. New: walk the **latest filing's raw `line_items`** in document order, assign sequential xlsx rows, match older filings' items to existing rows via `ledger_rule_id`. Items present only in older filings append at end (preserving their prior-filing order per user direction). `insert_bs_subtotal_slots()` still runs since BS subtotals are ledger-invisible and need inserting. IS + CF subtotal formulas re-derive cell refs after row layout finalizes.

**Phase 5** — `validate.py` cross-statement rules currently do `_find_by_model_row(bs_items, sheet_contains="BALANCE SHEET", row=9)` — these hard-code row numbers. Refactor to `_find_by_canonical_label(items, label="Cash & Cash Equivalents")` (or by `ledger_rule_id` match). Keeps the BS-1..6, CF-1..5, X-1/X-2/X-4 rules working without row-number dependence.

**Phase 6** — Income Tax sign flip. User chose **option B** (all expense-convention items — Interest Expense, FX Loss, Tax). Implementation:
- Generic entries mark `sign_convention: "expense_positive"` (already set on `GEN-IS-010 Income Tax (Benefit) Expense`; add to GEN-IS-006 Interest Income (Expense), GEN-IS-007 FX Gain (Loss), GEN-IS-008 Other Income (Expense))
- `model-write` negates the stored value at cell-write time when writing items with this convention
- IS subtotal formulas change: `=PT-SUM(non_op_rows)` for Pre-Tax (was `+SUM`), `=PT-Tax` for NI (was `+Tax`)
- `validate.py` IS-3 + IS-4 formulas stay natural-sign (they operate on MappedFiling data which is still natural-signed); only the xlsx render flips.

**Phase 7** — End-to-end regression. Run extract→reconcile→validate→model-write→playground on both filings. Confirm 48/48. Inspect xlsx output: IS subtotal formulas should now use `-SUM` for PT/NI, tax displays positive for expense years. Compare against pre-migration xlsx for any unintentional drift.

### Deferred (picks up after the migration is clean)

- **`model-calc`** — the 6th skill. Build 3 driver tabs (IS / BS / CF) with historical driver computation + forecast defaults. Per-filing document-order architecture now in place makes `model-calc` simpler (it just populates forecast columns; row layout already stable).
- `model-calc` scope per earlier discussion:
  - IS DRIVERS: Revenue Growth %, COGS % of Rev, SG&A % of Rev, Interest Income $, FX / Other $, Effective Tax Rate %
  - BS DRIVERS: DSO, DIO, DPO, Other CA % of Rev, Accrued Liab days of OpEx
  - CF DRIVERS: D&A $, SBC $, CapEx $, Preferred Div $, Share Repurchases $, Net Debt $
  - Single skill (compute + write) — confirmed
  - Forecast defaults: hold-last-year for ratios, linear decay to 3% terminal for revenue growth (still unconfirmed — pending)

## Pipeline invocation (unchanged from April 23 prior handoff)

```bash
cd "C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema"
source financials-schema/.venv/Scripts/activate

PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/financials-extract/scripts/extract.py" \
    --ticker-root "CELH/" \
    --pdf "C:/Users/rodin/Desktop/Pl3 Celsius Case Study/data/CELH Reporting/Financial Statements/2025_CELH_10-K.pdf" \
    --out "CELH/Model Output/raw_2025_10K.json" \
    --filing-type "10-K" --filing-date "2025-02-27"

# Reconcile NOW also loads the generic library automatically
PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/financials-reconcile/scripts/reconcile.py" \
    --ticker-root "CELH/" \
    --in "CELH/Model Output/raw_2025_10K.json" \
    --out "CELH/Model Output/mapped_2025_10K.json"

PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/financials-validate/scripts/validate.py" \
    --ticker-root "CELH/" \
    --in "CELH/Model Output/mapped_2025_10K.json" \
    --out "CELH/Model Output/validated_2025_10K.json"

PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/model-write/scripts/write.py" \
    --ticker-root "CELH/" \
    --in "CELH/Model Output/validated_2024_10K.json" \
    --in "CELH/Model Output/validated_2025_10K.json" \
    --out "CELH/Model Output/CELH_model.xlsx"
```

## Open decisions / pending work

1. **Resume Phase 3** — strip `model_row` from CELH `decisions_ledger.json`, mark superseded, apply renames. Straightforward JSON edit pass.
2. **Phase 4** — `model-write` row-layout refactor. Most invasive. `resolve_row_positions()` + `insert_bs_subtotal_slots()` get rewritten to walk filing order.
3. **Phase 5** — `validate.py` cross-statement lookups. Switch `_find_by_model_row` → `_find_by_canonical_label` (or `_find_by_rule_id`).
4. **Phase 6** — Income Tax sign flip (scope B). Implementation pattern: `sign_convention: "expense_positive"` field on generic entry → model-write negates at write time → IS subtotal formulas subtract instead of add.
5. **Phase 7** — regression. 48/48 still pass, xlsx matches (modulo intentional changes).
6. **Then `model-calc`** — driver tabs, historical driver compute, forecast defaults.
7. **FY2025 10-K pull** — still deferred. HTML-only SEC filing. Needs `weasyprint` or HTML branch in extract.

## Key file paths

| Purpose | Path |
|---|---|
| Roadmap | `C:/Users/rodin/Desktop/Brain/Sessions/CELH Model/ROADMAP.md` |
| Prior handoff | `C:/Users/rodin/Desktop/Brain/Sessions/CELH Model/Handoffs/April 23rd Model-Write Shipped Session.md` |
| This handoff | `C:/Users/rodin/Desktop/Brain/Sessions/CELH Model/Handoffs/April 23rd Generic Library Migration Session.md` |
| **Generic library (new this session)** | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/pattern_libraries/generic_line_item_mappings.json` |
| Reconcile skill (Phase 2 updates) | `C:/Users/rodin/.claude/skills/financials-reconcile/scripts/reconcile.py` |
| Model-write (to be refactored in Phase 4) | `C:/Users/rodin/.claude/skills/model-write/scripts/write.py` |
| Validate (to be refactored in Phase 5) | `C:/Users/rodin/.claude/skills/financials-validate/scripts/validate.py` |
| CELH ledger (Phase 3 target) | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/CELH/decisions_ledger.json` |
| Interactive playground | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/playground_architecture.html` |
| Sign-agnostic convention memory | `C:/Users/rodin/.claude/projects/C--Users-rodin/memory/feedback_sign_agnostic_labels.md` |
| Ledger ordering convention memory | `C:/Users/rodin/.claude/projects/C--Users-rodin/memory/feedback_ledger_ordering.md` |

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
