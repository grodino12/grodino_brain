---
type: roadmap
date: 2026-04-22
project: Celsius HF Case Study
scope: CELH financial model pipeline + GLP-1 + SNAP + cross-model integration
---

# Celsius HF Case Study — Roadmap

Living document. Update after each session. Three workstreams feed one final question: **"What's the net impact on CELH revenue from GLP-1 headwinds + SNAP energy-drink bans + demographic trends?"**

---

## Status at a glance

| Workstream | State | Next action |
|---|---|---|
| **CELH financial pipeline** (6 skills) | 4 of 6 built, 2 filings validated end-to-end | Build `model-write` (payoff milestone) |
| **GLP-1 projection model** | Built standalone, live in xlsx | Integrate into CELH revenue forecast (later) |
| **SNAP / demographics model** | Built standalone, live in xlsx | Integrate into CELH revenue forecast (later) |
| **Cross-model integration** | Not started | Blocked until CELH pipeline writes to the xlsm |

**Critical path to a defensible case study:** `model-write` → re-verify FY2023 + FY2024 values land in the xlsm cleanly → `model-calc` (growth/margins/WC ratios) → cross-model integration of GLP-1 + SNAP into the revenue forecast.

---

## Project scope

Three interlocking workbooks living at `C:\Users\rodin\Desktop\Pl3 Celsius Case Study\data\derived\`:

1. **`CELH Financial Model.xlsm`** — primary target; 10 sheets w/ macros; ANNL/QTR P&L already populated, BS + CF pending the first `model-write` run.
2. **`GLP1_Projection Data.xlsx`** — PWBM take-up curve × insurance coverage × survival curves → % of energy-drink consumers on GLP-1 over time.
3. **`Celsius_SNAP Data_GR.xlsx`** — SNAP participation × state bans × Celsius demographic share → SNAP-funded volume at risk.

Shared Postgres backing (Docker): `demographic_data` DB on localhost:5432. pgAdmin at localhost:5050.

---

## Done

### CELH pipeline (6-skill architecture)

- **Designed and shipped 4 of 6 skills** — all ticker-agnostic, CELH specifics live as JSON under `Brain\Knowledge\Model Schema\CELH\`.
  - `financials-extract` — PDF → `RawFiling`; unit detection, 3-pass period detection, subtotal-driven BS section flips, IS section classifier, EPS/shares disambiguation via `subsection_context`.
  - `financials-reconcile` — `RawFiling` + ledger → `MappedFiling`; sheet-aware lookup, `filing_section`/`filing_subsection` discriminators, fuzzy auto-apply ≥ 85, novels surface as `NovelItem` with top-3 candidates.
  - `financials-validate` — `MappedFiling` → `ValidatedFiling`; 35 rule instances across BS-1..6, CF-1..5, X-1/2/4.
  - `financials-playground` — multi-filing HTML explorer; period dedup across filings, canonical section ordering, subtotal promotion, supplementals carved out, mezzanine under SE, FX in financing, NOVELS tab.
- **Shared schema package** `financials-schema/` — 13 Pydantic classes, 16/16 pytest pass.
- **CELH decisions ledger** — 124 mappings + 24 new_rows + 7 structural + 1 rename.
- **End-to-end runs:** FY2023 10-K 35/35 PASS, FY2024 10-K 35/35 PASS (gap = 0 on every rule, both filings).
- **Meta-playgrounds refreshed:** `playground_architecture.html` (pipeline), `playground_schema.html` (Pydantic classes).
- **Design docs** (01–04) at `Brain\Knowledge\Model Schema\`.

### Supporting infrastructure

- Global Claude Code statusline configured (context-window %/tokens).
- Session-handoff convention + template living at `Brain\Sessions\{Theme}\`.
- Naming-convention memory: filings are always referenced by fiscal period reported (FY2023 10-K), never by year filed.

### Pre-pipeline (historical)

- Old monolithic `celh-model-update` skill deleted 2026-04-22, cleanly replaced by multi-skill pipeline.
- ANNL P&L FY2023–FY2025 and QTR P&L Q1 2023–Q4 2024 already populated in the xlsm from the old skill — survives as-is; model-write only touches ledger-listed rows.
- GLP-1 model rebuilt from corrupt state (`cell.fill = None` lesson baked into excel_safety rules).
- SNAP model built out w/ raked demographic joins and state-ban flags.

---

## Active — current objectives

### `model-write` (Layer 4, part 2) — THE PAYOFF MILESTONE

Takes validated JSONs + the xlsm, writes values into the CELH model. First run is the proof point: FY2023 + FY2024 BS and CF land in the correct cells while the xlsm's macros, formulas, and existing P&L data survive intact.

**Requirements carried forward from `04_pipeline_design.md`:**
- `keep_vba=True` on load/save.
- Never `cell.fill = None` — use `PatternFill(fill_type=None)`.
- `.bak` backup before any write.
- Emit `ManualInsertPlan` for `new_rows` (Path 3: user inserts rows manually in Excel to preserve cross-sheet formulas; script populates once inserts are done).
- Save to `_updated.xlsm`, never overwrite the original.
- Verify-after-save: reload, grep for `#REF!`, spot-check known cells.

**First ManualInsertPlan test case:** NEW-CF-011 "Proceeds from Common" — insert immediately above Proceeds from Preferred (currently row 42), bump existing rows 42+ down by 1, assign `model_row: 42` back into the ledger entry.

---

## Near horizon — next milestones

1. **`model-calc` (Layer 4, part 3).** Simplified scope per prior user direction: YoY/QoQ growth, margins (GP/OP/NI), working-capital ratios (DSO/DIO/DPO/CCC), base scenario only. No GLP-1 / SNAP overlays at this stage.
2. **Pull FY2025 10-K from EDGAR.** Accession `0001341766-26-000024`, HTML-only at `https://www.sec.gov/Archives/edgar/data/1341766/000134176626000024/celh-20251231.htm`. Needs one of: `weasyprint` HTML→PDF, `playwright`-driven headless print, or an HTML-aware branch in `financials-extract`. After conversion, run full pipeline; expect a handful of novels from FY2025 10-K wording drift.
3. **Assign `model_row` to NEW-CF-011** in the ledger once `model-write` has executed its first ManualInsertPlan.
4. **Cross-model integration — first cut.** Wire GLP-1 % and SNAP-ban volume at-risk into CELH revenue rows 2026E–2028E (extend through 2030E per original plan). Requires `model-write` and `model-calc` live first so the forecast rows exist and are driven by formulas.

---

## Later horizon — architectural + coverage

1. **Multi-era reporting-style drift (biggest architectural TODO).** Older 10-Ks use different wording and page layouts. Current mitigation is progressive ledger expansion, which works but requires manual curation per filing era. Options to evaluate:
   - Per-entry `filing_date_range` so ledger mappings know their validity window.
   - Explicit filing-era normalization adapter run BEFORE ledger lookup.
   - Multi-variant entries (one ledger row lists multiple equivalent labels).
   - Semantic / LLM-assisted matching for unknowns.
2. **Pivot extract from label-matching to semantic line-item recognition.** (Late-stage, not near-term — current label-matching architecture is fine for now.) Instead of the ledger carrying an ever-growing library of label variants for each model row, rework `financials-extract` so it classifies each line item semantically into a canonical Pydantic shape (e.g. `CashAndEquivalents`, `AccountsReceivable`, `InterestExpense`) regardless of filing-era wording. Reconcile would then match by canonical type, not by string similarity. Shifts complexity from ledger curation → extractor intelligence. Likely subsumes the multi-era drift TODO above — may end up being the same solution.
2. **FY2021 / FY2022 BS coverage.** Blocked on 39 older-era-wording reconcile novels in `2022_CELH_10-K.pdf`. Would close once multi-era handling lands.
3. **BS-7 RE roll-forward validator** (`RE(t) = RE(t-1) + NI(t) − PrefDiv(t)`). Needs cross-filing prior-period BS data — best addressed as part of a "cross-filing" validation mode.
4. **10-Q quarterly pipeline support.** Current extract assumes annual periods; quarterly filings need a period-detection branch plus adjustments to validators that assume a 12-month frame.
5. **Pytest coverage for extract / reconcile / validate.** Only `financials-schema/tests/test_smoke.py` exists today; each skill needs ≥1 fixture-based integration test.
6. **Decisions-ledger audit.** Many of the 124 mappings are generic (any ticker); some are CELH-specific. Consider splitting `generic_mappings.json` (cross-ticker) from `CELH/decisions_ledger.json` (ticker-specific anomalies + new_rows).
7. **BS section-header detection for older filings.** Subtotal-flip fix covers CA→NCA and CL→NCL; doesn't handle TL→Mezz→Equity splits in older-era layouts.

---

## Deferred / out of scope

- **GLP-1 + SNAP scenario overlays** (bull/bear/recession) inside `model-calc`. User explicitly scoped `model-calc` down to base-case derived calcs only.
- **Cross-model integration beyond first cut.** Multi-scenario sensitivity rolling GLP-1 take-up × SNAP ban timing × demographic shifts is future work.
- **Other tickers.** Architecture supports them (`mkdir tickers/{name}/` + 3 JSON files), but no non-CELH ticker is in scope for the case study.

---

## Known small issues (tracked, non-blocking)

- `Acquisition of Big Beverages` label truncation — pdfplumber column-width artifact. NEW-CF-009 uses the full normalized form; if a future extract yields a different truncation, the entry may need adjustment.
- Windows console encoding — Δ / — in validator messages break cp1252 stdout. Workaround: `PYTHONIOENCODING=utf-8`. Proper fix: ASCII-ize messages or force stdout encoding in `main()`.

---

## Key references

| Purpose | Path |
|---|---|
| Handoffs folder | `Brain\Sessions\CELH Model\Handoffs\` |
| Latest session handoff | `Brain\Sessions\CELH Model\Handoffs\April 22nd Playground Polish Session.md` |
| Prior handoff (novels walk) | `Brain\Sessions\CELH Model\Handoffs\April 22nd Novels Disambiguation Session.md` |
| Pipeline framework session | `Brain\Sessions\CELH Model\Handoffs\April 22nd Multi-Skill Framework Session.md` |
| Three-model overview | `Brain\Sessions\CELH Model\01_three_model_overview.md` |
| Pipeline architecture playground | `Brain\Knowledge\Model Schema\playground_architecture.html` |
| Pydantic schema playground | `Brain\Knowledge\Model Schema\playground_schema.html` |
| Design docs (01–04) | `Brain\Knowledge\Model Schema\0{1..4}_*.md` |
| Shared schema package | `Brain\Knowledge\Model Schema\financials-schema\` |
| CELH config / anomalies / ledger | `Brain\Knowledge\Model Schema\CELH\{config,anomalies,decisions_ledger}.json` |
| CELH derived outputs | `Brain\Knowledge\Model Schema\CELH\derived\` |
| Target xlsm | `Pl3 Celsius Case Study\data\derived\CELH Financial Model.xlsm` |
| Source PDFs | `Pl3 Celsius Case Study\data\CELH Reporting\Financial Statements\` |
