---
type: roadmap
date: 2026-04-23
project: Celsius HF Case Study
scope: CELH financial model pipeline + GLP-1 + SNAP + cross-model integration
---

# Celsius HF Case Study — Roadmap

Living document. Update after each session. Three workstreams feed one final question: **"What's the net impact on CELH revenue from GLP-1 headwinds + SNAP energy-drink bans + demographic trends?"**

---

## Status at a glance

| Workstream | State | Next action |
|---|---|---|
| **CELH financial pipeline** (6 skills) | **5 of 6 built**, 2 filings end-to-end through the xlsx | Build `model-calc` (forecast columns) |
| **GLP-1 projection model** | Built standalone, live in xlsx | Integrate into CELH revenue forecast (later) |
| **SNAP / demographics model** | Built standalone, live in xlsx | Integrate into CELH revenue forecast (later) |
| **Cross-model integration** | Not started | Blocked until `model-calc` exposes forecast rows |

**Critical path to a defensible case study:** ~~`model-write` → verify historicals~~ ✓ → `model-calc` (growth/margins/WC ratios + forecast columns) → cross-model integration of GLP-1 + SNAP into the revenue forecast.

---

## Project scope

Three interlocking workbooks. CELH model is now built from scratch at `Brain\Knowledge\Model Schema\CELH\Model Output\CELH_model.xlsx`; the old `Pl3 Celsius Case Study\data\derived\CELH Financial Model.xlsm` stays as reference, untouched.

1. **`CELH_model.xlsx`** — primary target; built fresh by `model-write` from validated JSONs. 3 sheets (ANNL P&L, BALANCE SHEET, CASH FLOW), historical columns FY2021–FY2024 + forecast columns FY2025E–FY2030E, plain .xlsx (no macros).
2. **`GLP1_Projection Data.xlsx`** — PWBM take-up curve × insurance coverage × survival curves → % of energy-drink consumers on GLP-1 over time.
3. **`Celsius_SNAP Data_GR.xlsx`** — SNAP participation × state bans × Celsius demographic share → SNAP-funded volume at risk.

Shared Postgres backing (Docker): `demographic_data` DB on localhost:5432. pgAdmin at localhost:5050.

---

## Done

### CELH pipeline (6-skill architecture)

- **Shipped 5 of 6 skills** — all ticker-agnostic, CELH specifics live as JSON under `Brain\Knowledge\Model Schema\CELH\`.
  - `financials-extract` — PDF → `RawFiling`; unit detection, 3-pass period detection, subtotal-driven BS section flips, IS section classifier, EPS/shares disambiguation via `subsection_context`.
  - `financials-reconcile` — `RawFiling` + ledger → `MappedFiling`; sheet-aware lookup, `filing_section`/`filing_subsection` discriminators, fuzzy auto-apply ≥ 85, novels surface as `NovelItem` with top-3 candidates. **Section-collision guard refuses ambiguous mappings** (blocks collisions like Operating lease current/NC sharing one rule_id).
  - `financials-validate` — `MappedFiling` → `ValidatedFiling`; 36 rule instances across BS-1..6, CF-1..5, X-1/2/4, **and M-1 (mapping-consistency: all items on one rule_id must agree on section)**.
  - `financials-playground` — multi-filing HTML explorer; period dedup across filings, canonical section ordering, subtotal promotion, supplementals carved out, mezzanine under SE, FX in financing, NOVELS tab.
  - **`model-write` — builds fresh xlsx from scratch** (no template). 3 sheets, row layout driven by ledger, period columns normalized via `Period` model → `FY{year}` / `Q{Q} FY{year}` labels. Features: historical dedup (newer filing wins), zero-fill empty cells, BS+CF subtotal formulas with cascading (Total Assets = TCA + NC items, etc.) and grand total (TL + Mezz + TSE). Top black border on every sum-formula row. Honors `superseded_by` ledger fields and explicit `model_row` on new_rows.
- **Shared schema package** `financials-schema/` — 13 Pydantic classes, 16/16 pytest pass.
- **CELH decisions ledger** — 126 mappings + 24 new_rows + 7 structural + 1 rename. Cleaned: 28 `Delta`/`Δ` label renames, 6 superseded entries (5 redundant + 1 placeholder), 8 position_note anchors added, duplicate `NEW-CF-009` rule_id fixed. `filing_section` discriminator added for both Finance and Operating lease splits.
- **End-to-end runs:** FY2023 10-K 36/36 PASS, FY2024 10-K 36/36 PASS (gap = 0 on every rule, both filings). `CELH_model.xlsx` generated with 354 cells across 3 sheets + 6 empty forecast columns each.
- **Meta-playgrounds refreshed:** `playground_architecture.html` (pipeline, decisions_ledger now aligned with financials-reconcile), `playground_schema.html` (Pydantic classes).
- **Design docs** (01–04) at `Brain\Knowledge\Model Schema\`.

### Supporting infrastructure

- Global Claude Code statusline configured (context-window %/tokens).
- Session-handoff convention updated: handoffs live in `Brain\Sessions\{Task-Theme}\Handoffs\` subfolders. Retroactive for CELH Model + Transcript Scraping.
- Folder renamed: `CELH\derived\` → `CELH\Model Output\` (paths updated across skills + docs + latest handoff).
- Naming-convention memory: filings are always referenced by fiscal period reported (FY2023 10-K), never by year filed.

### Pre-pipeline (historical)

- Old monolithic `celh-model-update` skill deleted 2026-04-22, cleanly replaced by multi-skill pipeline.
- GLP-1 model rebuilt from corrupt state (`cell.fill = None` lesson baked into excel_safety rules).
- SNAP model built out w/ raked demographic joins and state-ban flags.

---

## Active — current objective

### `model-calc` (Layer 4, part 3) — fills the forecast columns

Takes the validated filings + the xlsx and populates the six empty forecast columns (FY2025E–FY2030E) with derived calcs. Per prior user direction, simplified scope:

- **Growth:** YoY / QoQ growth per line item on historicals; apply a base growth assumption to project forward.
- **Margins:** GP, OP, NI as % of revenue; use latest-year ratio to project cost lines.
- **Working-capital ratios:** DSO, DIO, DPO, CCC; project BS WC rows from assumed revenue × ratio.
- **Base scenario only** — GLP-1 and SNAP overlays explicitly deferred.

Design note: since BS/CF subtotals are already live formulas, `model-calc` only has to populate line items — subtotals recompute automatically. That's a concrete win from this session's formula work.

---

## Near horizon — next milestones

1. **Pull FY2025 10-K from EDGAR.** Accession `0001341766-26-000024`, HTML-only at `https://www.sec.gov/Archives/edgar/data/1341766/000134176626000024/celh-20251231.htm`. Needs one of: `weasyprint` HTML→PDF, `playwright`-driven headless print, or an HTML-aware branch in `financials-extract`. After conversion, run full pipeline; expect a handful of novels from FY2025 10-K wording drift.
2. **IS subtotal SUM formulas.** BS and CF have live subtotals; IS does not yet. Add Gross Profit = Revenue − COGS, Operating Profit = GP − OpEx, etc. Small follow-on to the existing CF/BS subtotal logic in `model-write`.
3. **Cross-model integration — first cut.** Wire GLP-1 % and SNAP-ban volume at-risk into CELH revenue rows FY2026E–FY2028E (extend through FY2030E per original plan). Requires `model-calc` live first so the forecast rows are driven by formulas.

---

## Later horizon — architectural + coverage

1. **Multi-era reporting-style drift (biggest architectural TODO).** Older 10-Ks use different wording and page layouts. Current mitigation is progressive ledger expansion, which works but requires manual curation per filing era. Options to evaluate:
   - Per-entry `filing_date_range` so ledger mappings know their validity window.
   - Explicit filing-era normalization adapter run BEFORE ledger lookup.
   - Multi-variant entries (one ledger row lists multiple equivalent labels).
   - Semantic / LLM-assisted matching for unknowns.
2. **Pivot extract from label-matching to semantic line-item recognition.** (Late-stage, not near-term — current label-matching architecture is fine for now.) Instead of the ledger carrying an ever-growing library of label variants for each model row, rework `financials-extract` so it classifies each line item semantically into a canonical Pydantic shape (e.g. `CashAndEquivalents`, `AccountsReceivable`, `InterestExpense`) regardless of filing-era wording. Reconcile would then match by canonical type, not by string similarity. Shifts complexity from ledger curation → extractor intelligence. Likely subsumes the multi-era drift TODO above — may end up being the same solution.
3. **FY2021 / FY2022 BS coverage.** Blocked on 39 older-era-wording reconcile novels in `2022_CELH_10-K.pdf`. Would close once multi-era handling lands.
4. **BS-7 RE roll-forward validator** (`RE(t) = RE(t-1) + NI(t) − PrefDiv(t)`). Needs cross-filing prior-period BS data — best addressed as part of a "cross-filing" validation mode.
5. **10-Q quarterly pipeline support.** Current extract assumes annual periods; quarterly filings need a period-detection branch plus adjustments to validators that assume a 12-month frame. When loaded, QTR P&L sheet re-opens in `model-write`.
6. **Pytest coverage for extract / reconcile / validate / model-write.** Only `financials-schema/tests/test_smoke.py` exists today; each skill needs ≥1 fixture-based integration test.
7. **Decisions-ledger audit.** Many of the 126 mappings are generic (any ticker); some are CELH-specific. Consider splitting `generic_mappings.json` (cross-ticker) from `CELH/decisions_ledger.json` (ticker-specific anomalies + new_rows). Plus cleanup of the dup rule_ids that remain (Δ-vs-Delta siblings still live side by side at the same rows).
8. **BS section-header detection for older filings.** Subtotal-flip fix covers CA→NCA and CL→NCL; doesn't handle TL→Mezz→Equity splits in older-era layouts.

---

## Deferred / out of scope

- **GLP-1 + SNAP scenario overlays** (bull/bear/recession) inside `model-calc`. User explicitly scoped `model-calc` down to base-case derived calcs only.
- **Cross-model integration beyond first cut.** Multi-scenario sensitivity rolling GLP-1 take-up × SNAP ban timing × demographic shifts is future work.
- **Expense-lines-always-negative-in-parens** sign normalization in `model-write`. Flagged 2026-04-22, user deferred.
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
| Latest session handoff | `Brain\Sessions\CELH Model\Handoffs\April 23rd Model-Write Shipped Session.md` |
| Prior handoff (playground polish) | `Brain\Sessions\CELH Model\Handoffs\April 22nd Playground Polish Session.md` |
| Three-model overview | `Brain\Sessions\CELH Model\01_three_model_overview.md` |
| Pipeline architecture playground | `Brain\Knowledge\Model Schema\playground_architecture.html` |
| Pydantic schema playground | `Brain\Knowledge\Model Schema\playground_schema.html` |
| Design docs (01–04) | `Brain\Knowledge\Model Schema\0{1..4}_*.md` |
| Shared schema package | `Brain\Knowledge\Model Schema\financials-schema\` |
| CELH config / anomalies / ledger | `Brain\Knowledge\Model Schema\CELH\{config,anomalies,decisions_ledger}.json` |
| CELH model outputs | `Brain\Knowledge\Model Schema\CELH\Model Output\` |
| CELH_model.xlsx (the built output) | `Brain\Knowledge\Model Schema\CELH\Model Output\CELH_model.xlsx` |
| Old xlsm (reference only, untouched) | `Pl3 Celsius Case Study\data\derived\CELH Financial Model.xlsm` |
| Source PDFs | `Pl3 Celsius Case Study\data\CELH Reporting\Financial Statements\` |
| model-write skill | `~\.claude\skills\model-write\` |
