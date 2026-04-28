# CELH Update — Session State

**Last updated:** 2026-04-17
**Skill:** `~/.claude/skills/celh-model-update/SKILL.md`
**Phase:** Between Phase 2 (Citations) and Phase 3 (Excel Write)

This file captures live state — what's been decided, what's pending, and the current file inventory. Update it at the end of each work session so the next session can resume cleanly.

---

## Current Status

✅ **Done in this work stream:**
- ANNL P&L FY2023-FY2025 actuals updated (in current model)
- QTR P&L Q1 2023-Q4 2024 quarterly actuals updated (in current model)
- FY2024 BS + CF re-extracted cleanly from `2025_CELH_10-K.pdf` page 50/53
- FY2023 BS + CF extracted cleanly from `2024_CELH_10-K.pdf` page 45/48
- All 11 internal validation rules PASS for both years
- All 5 cross-period validation rules PASS (incl. RE roll-forward, cash continuity)
- Skill upgraded with Phase 1.5 (Reconciliation), Phase 1.75 (Validation), and progressive learning via decisions ledger
- Decisions ledger created and populated with 28 mappings + 16 new row rules + 4 structural decisions + 11 anomalies

⏳ **Pending — needs user input before Phase 3 can run:**

1. **Spawn 3rd subagent for FY2024 CF line-item detail re-extraction?**
   - FY2024 CFO/CFI/CFF subtotals are confirmed clean ($262,898 / $(101,726) / $(25,966))
   - But individual line items (D&A, SBC, capex, acquisitions, etc.) are still from the buggy first-pass extraction
   - BS-7 RE roll-forward proves CFF and dividend lines are right; CFO and CFI line items are the main remaining risk
   - Decision needed: spawn subagent (more defensible) OR proceed with current values (faster, less defensible at line-item level)

⏸️ **Held for Phase 3 execution:**
- Generate manual Excel insert instructions list (which rows to insert in which sheets, which labels to type, where to put the new mezzanine equity row, etc.)
- User performs manual inserts in Excel (Path 3 — preserves cross-sheet formulas)
- Python script populates values into `CELH Financial Model_updated.xlsm`
- Phase 4: verify file integrity (reload, scan for #REF!, sample known cells)
- Phase 5: diff report

---

## Confirmed User Decisions (this session)

1. **Convertible Preferred Stock = mezzanine row.** Sits between Total Liabilities and Total Stockholders' Equity. Does NOT sum into row 46 Total SE. Total L&E (row 48) includes Liab + Mezz + SE. Matches CELH's filed BS structure.

2. **CF row 24 zero-out + 2 new rows below.** Old combined row 24 ("Change in Accounts Payable and Accrued Expenses") becomes a memo line with $0 for FY2023+. Two new rows added below: Δ Accounts Payable, Δ Accrued Expenses. Older years (2016-2022) keep combined value in row 24.

3. **Path 3 implementation for new rows.** User performs row inserts manually in Excel (so cross-sheet formulas update correctly), then Python populates values into the now-correctly-shifted cells. Avoids the openpyxl `insert_rows` cross-sheet formula breakage risk.

4. **Identical-value items confirmed correct, not extraction errors:**
   - Deferred Other Costs (Current) = $14,124K both years (straight-line amortization)
   - Deferred Revenue (Current) = $9,513K both years (PEP contract straight-line recognition)

---

## Current File Inventory (`data/derived/`)

| File | Purpose |
|------|---------|
| `CELH Financial Model.xlsm` | Active model file (current truth, pre-Phase-3) |
| `CELH Financial Model.xlsm.bak` | Safety backup. **Keep until Phase 3 succeeds AND user verifies in Excel.** Then can delete. |
| `CELH Financial Model - Source Citations.md` | Definitive source-of-truth doc for every value being written. Has corrected FY2023+FY2024 BS/CF, all validations PASS. |
| `celh_decisions_ledger.md` | Persistent decisions store. Loaded by Phase 1.5 next time skill runs. Append-only by default. |
| `celh_session_state.md` | This file. Live session status. |
| `Celsius_SNAP Data_GR.xlsx` | SNAP/demographics workbook (separate work stream) |
| `GLP1_Projection Data.xlsx` | GLP-1 projection workbook (separate work stream) |
| `cohort_rates.csv` | GLP-1 input data |
| `national_data_with_snap_ed.csv` | SNAP input data |

**Folder cleanup performed 2026-04-17:** Removed stale `_updated.xlsm` (buggy first-pass output), `_Current.xlsx` and `_recovered.xlsx` (intermediate GLP-1 versions), and `celh_reconciliation_log.md` (superseded by ledger).

---

## Key Technical Facts to Remember

- **Source PDFs path:** `data/CELH Reporting/Financial Statements/[YYYY]_CELH_10-K.pdf` (year = year filed; FY2023 data is in 2024 10-K, FY2024 data is in 2025 10-K)
- **CELH cash convention varies by year:** FY2023 10-K uses "Cash + restricted cash" (restricted cash dropped to $0 by year-end). FY2024 10-K uses "Cash and cash equivalents" only. Validate per-year by checking the CF heading.
- **No Treasury Stock in either year.** Equity composition is Common + APIC + AOCI + Retained Earnings only.
- **Stock split 3-for-1 on Nov 13, 2023.** Don't touch share counts or EPS without verifying source convention.
- **Excel safety:** Always `keep_vba=True` for .xlsm. Never `cell.fill = None` (use `PatternFill(fill_type=None)`). Never insert rows in cross-linked sheets via openpyxl. Save to `_updated` filename, not original. Verify-after-save via reload.

---

## To Resume

> "Continue the CELH model update. Read `data/derived/celh_session_state.md` to see current pending decisions, then `data/derived/CELH Financial Model - Source Citations.md` and `data/derived/celh_decisions_ledger.md` for context. We need a call on whether to spawn the FY2024 CF line-item detail subagent before proceeding to Phase 3."
