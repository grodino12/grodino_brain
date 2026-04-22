# Handoff Package — Celsius HF Case Study

**Snapshot date:** 2026-04-22
**Purpose:** Self-contained handoff bundle for resuming work in a new Claude Code session (or sending to a collaborator).

These files are **point-in-time copies** from `data/derived/`. The originals are the source of truth for ongoing work. If you make changes after this snapshot, regenerate the handoff folder before sending.

> ⚠️ **Skill status (2026-04-22):** The prior `celh-model-update` skill has been deleted from `~/.claude/skills/` and is being **reworked from scratch**. The old `skill/` subfolder that used to ship with this handoff (SKILL.md, excel_safety.md, model_row_map.md) has also been removed. The data files below (decisions ledger, citations, session state) are still the source of truth for what the reworked skill needs to produce and respect.

---

## What's in here

| # | File | What it is | Read first if... |
|---|------|------------|------------------|
| 00 | `00_README.md` | This file | Always |
| 01 | `01_three_model_overview.md` | High-level summary of all three models (CELH, GLP-1, SNAP) and how they connect | You're new to the project |
| 02 | `02_celh_session_state.md` | **Live status: what's done, what's pending, what decision is next** | You're resuming the CELH work |
| 03 | `03_celh_decisions_ledger.md` | Persistent decisions store — every reconciliation rule, mapping, structural choice, anomaly | The reworked skill needs to know what was decided in past runs |
| 04 | `04_celh_source_citations.md` | Definitive data values being written to the model, with PDF + page citations and validation results | You need to verify a specific number's source |

---

## How to use this handoff

### If resuming in a new Claude Code session on the same machine

1. Open Claude Code in the project directory: `C:\Users\rodin\Desktop\Pl3 Celsius Case Study`
2. The skill is **not** installed — it's being reworked. Until the new version ships, the workflow needs to be driven by hand against the decisions ledger + citations doc.
3. Tell Claude: *"Continue the CELH model update. Read `data/derived/celh_session_state.md` first, then the citations doc and decisions ledger for context. The old `celh-model-update` skill was deleted on 2026-04-22 and is being reworked — do not try to invoke it. We need a call on whether to spawn the FY2024 CF line-item detail subagent before proceeding to Phase 3."*

### If sending to someone else / a different machine

1. Zip this `CELH Model/` folder
2. Also send the source PDFs (or list of PDF paths — see below)
3. The recipient needs to:
   - Place the data files (citations, ledger, session state) in `data/derived/` of their working project
   - Place the source PDFs in `data/CELH Reporting/Financial Statements/`
   - Tell their Claude: *"Read `data/derived/celh_session_state.md` and resume the CELH model update. No skill is installed — work from the ledger + citations manually."*

---

## Source PDFs needed (not in this handoff — too large)

Located at `data/CELH Reporting/Financial Statements/`:
- `2024_CELH_10-K.pdf` — contains FY2023 BS (page 45) + CF (page 48)
- `2025_CELH_10-K.pdf` — contains FY2024 BS (page 50) + CF (page 53)
- `[YYYY]-Q[N]_CELH_10-Q.pdf` for quarterly data
- Press releases at `data/CELH Reporting/Press Releases/`
- Earnings presentations at `data/CELH Reporting/Earnings Presentations/`
- Earnings transcripts at `data/CELH Reporting/Earnings Transcripts/`

If you need to download these fresh, see CELH's investor relations site: https://ir.celsiusholdingsinc.com/financials/quarterly-results/default.aspx — the PDFs sit on the CloudFront CDN at `d18rn0p25nwr6d.cloudfront.net/CIK-0001341766/`.

---

## Files NOT in this handoff but referenced

These live in the project but aren't part of the active CELH work:
- `data/derived/Celsius_SNAP Data_GR.xlsx` — SNAP/demographics workbook (separate work stream)
- `data/derived/GLP1_Projection Data.xlsx` — GLP-1 projection workbook (separate work stream)
- `data/derived/national_data_with_snap_ed.csv` — SNAP input data
- `data/derived/cohort_rates.csv` — GLP-1 input data
- `data/derived/CELH Financial Model.xlsm` — the actual model (active)
- `data/derived/CELH Financial Model.xlsm.bak` — backup, keep until Phase 3 succeeds

---

## Open Decision Required Before Phase 3

**Spawn 3rd subagent for FY2024 CF line-item detail re-extraction, or skip and proceed to Phase 3 with current values?**

- FY2024 CFO/CFI/CFF subtotals are confirmed clean ($262,898 / $(101,726) / $(25,966))
- But individual line items (D&A, SBC, capex, acquisitions, etc.) are still from the buggy first-pass extraction
- BS-7 RE roll-forward proves CFF and dividend lines are right; CFO and CFI line items are the main risk
- Trade-off: more defensible (spawn subagent) vs faster (proceed)

---

## Skill rework — what the new version needs to preserve

When the replacement `celh-model-update` skill is built, it must:

1. **Load the decisions ledger (`03_celh_decisions_ledger.md`) before any reconciliation** and auto-apply matching rules without re-prompting the user. This was the key progressive-learning pattern from the old skill.
2. **Run a Phase 1.75 validation step** (BS-1 through BS-7, CF-1/CF-2, X-1 through X-4) before any Excel write. The old first pass had ~$394M of FY2024 misstatement that only this step caught.
3. **Honor the Excel safety rules** (keep_vba=True; never `cell.fill = None`; save to `_updated` filename; backup to `.bak` before writes; Path 3 manual row inserts for cross-sheet formula safety). The old `skill/references/excel_safety.md` encoded these — they need to be re-encoded in the rework.
4. **Respect CELH-specific anomalies** documented in Section E of the ledger — cash convention changes between FY2023 and FY2024 10-Ks, PEP mezzanine preferred treatment, the stock split, the straight-line amortization patterns that produce identical YoY values on Deferred Other Costs (Current) and Deferred Revenue (Current).
