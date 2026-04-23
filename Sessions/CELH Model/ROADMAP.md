---
type: roadmap
date: 2026-04-23
project: Celsius HF Case Study
scope: CELH financial model pipeline + GLP-1 + SNAP + cross-model integration
last_session: "April 23rd Generic Library Migration Session"
---

# Celsius HF Case Study — Roadmap

Living document. Update after each session. Three workstreams feed one final question: **"What's the net impact on CELH revenue from GLP-1 headwinds + SNAP energy-drink bans + demographic trends?"**

---

## Status at a glance

| Workstream | State | Next action |
|---|---|---|
| **CELH financial pipeline** (6 skills) | **5 of 6 built**, 2 filings end-to-end through the xlsx | Finish generic-library migration (Phases 3–7), then `model-calc` |
| **Generic cross-ticker library** | **Phases 1–2 shipped** (file created, reconcile loads it) | Phase 3: strip model_row + label renames in CELH ledger |
| **GLP-1 projection model** | Built standalone, live in xlsx | Integrate into CELH revenue forecast (later) |
| **SNAP / demographics model** | Built standalone, live in xlsx | Integrate into CELH revenue forecast (later) |
| **Cross-model integration** | Not started | Blocked until `model-calc` exposes forecast rows |

**Critical path to a defensible case study:** ~~`model-write` → verify historicals~~ ✓ → finish generic-library migration (Phases 3–7) → `model-calc` (growth/margins/WC ratios + forecast columns) → cross-model integration of GLP-1 + SNAP into the revenue forecast.

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
  - `financials-validate` — `MappedFiling` → `ValidatedFiling`; 48 rule instances across BS-1..6, CF-1..5, **IS-1..4 (new April 23 2026)**, X-1/2/4, and M-1 (mapping-consistency: all items on one rule_id must agree on section).
  - `financials-playground` — multi-filing HTML explorer; period dedup across filings, canonical section ordering, subtotal promotion, supplementals carved out, mezzanine under SE, FX in financing, NOVELS tab.
  - **`model-write` — builds fresh xlsx from scratch** (no template). 3 sheets, row layout driven by ledger (refactor to filing-order pending Phase 4), period columns normalized via `Period` model → `FY{year}` / `Q{Q} FY{year}` labels. Features: historical dedup (per-filing sum + newer-filing-wins across filings), zero-fill empty cells, **IS+BS+CF subtotal formulas** (IS added April 23 2026) with cascading (Total Assets = TCA + NC items, etc.) and grand total (TL + Mezz + TSE). Top black border on every sum-formula row. Subtotal format `$#,##0_);($#,##0);"$--"_)`, line items `#,##0;(#,##0);"--"`, EPS `$#,##0.00`. Honors `superseded_by` + `memo` + `sign_convention` fields.
- **Shared schema package** `financials-schema/` — 13 Pydantic classes, 16/16 pytest pass.
- **Generic cross-ticker library (new April 23 2026, Phases 1–2):** `pattern_libraries/generic_line_item_mappings.json` — 89 canonical entries (19 IS, 31 BS, 39 CF) with aliases covering all known filing wordings. `reconcile.py` loads it alongside the per-ticker ledger with tier-based ticker-over-generic precedence. Pipeline still passes 48/48.
- **CELH decisions ledger** — 126 mappings + 24 new_rows + 7 structural + 1 rename. Cleaned this session: 28 `Delta`/`Δ` label renames, 6 superseded entries, 8 position_note anchors added, duplicate `NEW-CF-009` rule_id fixed, `MAP-IS-004`/`MAP-IS-018` superseded, `Receivables`/`Prepaids` CF-label renames, CF investing reordered to match FY2024 10-K. `filing_section` discriminator used for Finance + Operating lease splits.
- **End-to-end runs:** FY2023 10-K + FY2024 10-K **48/48 PASS** (36 original + IS-1..4 × 3 periods per filing, gap = 0 on every rule, both filings). `CELH_model.xlsx` generated with 315+ cells, IS + BS + CF live subtotal formulas, accountant-style number formats with `$--` on zero.
- **Meta-playgrounds refreshed:** `playground_architecture.html` is now **interactive** (drag nodes / add + remove arrows / localStorage autosave / export JSON / reset). `playground_schema.html` (Pydantic classes).
- **Design docs** (01–04) at `Brain\Knowledge\Model Schema\`.
- **Memory feedback saved this session:**
  - `feedback_ledger_ordering.md` — align ledger ordering to the latest filing when filings differ.
  - `feedback_sign_agnostic_labels.md` — canonical labels use parentheticals for the alternative sign.

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

### Finish the generic-library migration (Phases 3–7), THEN `model-calc`

A cross-ticker canonical nomenclature library was introduced this session to lift ~80% of line-item mappings out of the per-ticker CELH ledger. Phases 1–2 are shipped (file created at `pattern_libraries/generic_line_item_mappings.json` with 89 entries; `reconcile.py` loads + merges with tier-based ticker precedence; pipeline still 48/48 PASS). Phases 3–7 remain:

- **Phase 3** — Strip `model_row` from CELH `decisions_ledger.json`, mark generic-covered entries `superseded_by: "generic"`, apply ~30 label renames (sign-agnostic convention — `Net Income (Loss)`, `Interest Income (Expense)`, etc.). Keep 7 CELH-specific entries (Deferred Other Costs pair, Accrued Distributor Termination, Amortization of Deferred Other Costs, Big Beverages acquisition, Gain (Loss) on Lease Cancellations, Interest Income on Note Receivable).
- **Phase 4** — Refactor `model-write/scripts/write.py` row layout. Row order no longer pinned in the ledger — derived from the latest filing's raw `line_items` document order. Older-filing-only items append preserving their prior-filing position.
- **Phase 5** — Refactor `validate.py` cross-statement rules. `_find_by_model_row` → `_find_by_canonical_label` / `_find_by_rule_id`.
- **Phase 6** — Income Tax sign flip (scope B: all expense-convention items). `sign_convention: "expense_positive"` on Interest Income (Expense), FX Gain (Loss), Other Income (Expense), Income Tax (Benefit) Expense. `model-write` negates at write time; IS subtotal formulas become `=PT−SUM(non_op)` and `=PT−Tax`.
- **Phase 7** — Regression on CELH FY2023 + FY2024 10-Ks, confirm 48/48 still PASS, inspect xlsx output.

Once migration lands, `model-calc` resumes with its deferred scope:

### `model-calc` (Layer 4, part 3) — deferred until migration complete

Per earlier user direction:
- **Growth:** YoY per line item; project forward.
- **Margins:** GP / OP / NI as % of revenue to project cost lines.
- **Working-capital ratios:** DSO / DIO / DPO.
- **Three driver tabs:** IS DRIVERS, BS DRIVERS, CF DRIVERS.
- **Base scenario only** — GLP-1 and SNAP overlays explicitly deferred.

Design note: since BS/CF + IS subtotals are already live formulas, `model-calc` only has to populate line items — subtotals recompute automatically.

---

## Near horizon — next milestones

1. **Finish generic-library migration (Phases 3–7).** See Active above. The handoff at `Brain\Sessions\CELH Model\Handoffs\April 23rd Generic Library Migration Session.md` has the complete rename list + queued work detail.
2. **Pull FY2025 10-K from EDGAR.** Accession `0001341766-26-000024`, HTML-only at `https://www.sec.gov/Archives/edgar/data/1341766/000134176626000024/celh-20251231.htm`. Needs one of: `weasyprint` HTML→PDF, `playwright`-driven headless print, or an HTML-aware branch in `financials-extract`. After conversion, run full pipeline; expect a handful of novels from FY2025 10-K wording drift.
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
| **Latest session handoff** | `Brain\Sessions\CELH Model\Handoffs\April 23rd Generic Library Migration Session.md` |
| Prior handoff (model-write shipped) | `Brain\Sessions\CELH Model\Handoffs\April 23rd Model-Write Shipped Session.md` |
| Prior handoff (playground polish) | `Brain\Sessions\CELH Model\Handoffs\April 22nd Playground Polish Session.md` |
| **Generic cross-ticker library** | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` |
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
