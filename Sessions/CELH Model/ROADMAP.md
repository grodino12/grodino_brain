---
type: roadmap
date: 2026-04-24
project: Celsius HF Case Study
scope: CELH financial model pipeline + universal model creation architecture + (later) GLP-1 / SNAP integration
last_session: "April 24th Model-Calc Forecast Balance Session"
---

# Celsius HF Case Study — Roadmap

Living document. Update after each session. **Current project focus: build a universal model creation architecture** that works across any consumer-staples ticker, not just CELH. The original case-study question ("What's the net impact on CELH revenue from GLP-1 headwinds + SNAP energy-drink bans + demographic trends?") is deferred — the pipeline will answer it once the architecture is generalized.

---

## Status at a glance

| Workstream | State | Next action |
|---|---|---|
| **CELH financial pipeline** (6 skills) | **6 of 6 built**, forecast BS balances end-to-end | Stress-test with a second ticker (recommended: PEP) |
| **Generic cross-ticker library (mappings)** | **Phases 1–7 shipped** — 92 entries | Maintain; expand aliases as new tickers land |
| **Generic forecast-rules library** | Not started | Extract from `calc.py` after second-ticker run |
| **Ticker onboarding doc** | Not started | One-page guide once universal architecture stabilizes |
| **GLP-1 projection model** | Built standalone, live in xlsx | Integrate once architecture is universal (deferred) |
| **SNAP / demographics model** | Built standalone, live in xlsx | Integrate once architecture is universal (deferred) |
| **Cross-model integration** | Deferred per user direction | Revisit after universal architecture ships |

**Revised critical path:** ~~`model-write`~~ ✓ → ~~generic-library migration~~ ✓ → ~~`model-calc` drivers + forecast~~ ✓ → ~~fix forecast BS balance gap~~ ✓ → **bring a second ticker online (PEP)** → **extract generic forecast-rules JSON** → **formalize ticker onboarding flow** → (later) cross-model integration.

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

- **Shipped 6 of 6 skills** — all ticker-agnostic, CELH specifics live as JSON under `Brain\Knowledge\Model Schema\CELH\`.
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
- **Generic-library migration complete (2026-04-23):** CELH ledger cut from 150 → 10 entries; generic library is the source of truth. 3 architectural wins: (1) reconcile's `select_entry` only enforces `filing_section` on ambiguous aliases, unblocking single-candidate label matches; (2) model-write row layout derives from the latest filing's document order; (3) validate uses canonical-label lookups, no more hardcoded model_row. Tax sign flip (expense-positive convention) shipped. **48/48 PASS on both filings.**
- **Forecast BS balance fix (2026-04-24):** empirically diagnosed gap = sum of 9 `flat` CF items with no BS offset in the forecast (Allowance, Inv Write-Down, Gain/Loss Disposal, Deferred Tax, FX Gain/Loss, Gain/Loss Lease, Other Op, ROU Lease Net, Finance Lease Payments, FX Effect on Cash). Amort of Deferred Costs was a red herring — cancels symmetrically. Fix: added `zero` and `aoci_rollforward` kinds; flipped 10 specs. BS balances at $0 gap FY2022 → FY2030E.
- **Number format propagation (2026-04-24):** forecast cells on ANNL P&L / BS / CF were rendering with `General` format instead of the historical accounting format. `write_statement_forecasts` now samples the format from the last historical column and applies it to every forecast cell in the row (including subtotals whose formulas came from model-write).
- **Allowance for Credit Losses driver (2026-04-24):** per user request, added `Allowance for Credit Losses % of Revenue` (0.243% historical for CELH) to `CF DRIVERS`. CF forecast line flipped from `zero` to `ratio_of_rev`. Reopens a small BS gap (~$3.3k/yr growing to ~$20k at FY2030E; ~1.1% of TA) — flagged as acceptable v1 simplification. Proper fix requires either a BS Allowance-for-Doubtful-Accounts contra-AR line or an SG&A-ex-BDE forecast offset.
- **`model-calc` shipped (discovered 2026-04-24 — `scripts/calc.py` contains the full build; no session handoff captured it):**
  - **ASSUMPTIONS tab** with `Days in Year = 365` and `Share Repurchases $ = 0`; every formula references these cells, no magic numbers.
  - **IS / BS / CF DRIVERS tabs** with historical formulas (kinds: `growth`, `ratio`, `lagged_ratio`, `days_ratio`, `dollar`, `dollar_sum`, `net_debt`) and projection-period rules (`hold_last`, `input`, `assumption_ref`, `derived`). 7 IS + 14 BS + 7 CF drivers. Yellow tint on user-input cells (Revenue Growth %), grey on formula-forecast cells.
  - **Full three-statement forecast formulas** on ANNL P&L / BALANCE SHEET / CASH FLOW — 27 distinct kinds including `revenue_growth`, `ratio_of_rev/cogs`, `days_driven_rev/cogs`, `tax`, `cash_rollforward`, `pp_e_rollforward`, `apic_rollforward`, `re_rollforward`, `amortize`, `cf_wc_asset`/`liability`/`combined`, `capex`, `d_a`, `dividends_preferred/common`, `cf_net_change`, `cash_beg`, `cash_end`, `ni_attrib_common`.
  - Cross-sheet column lookups done by period label per target sheet (not index) — correctly handles BS having fewer historical columns than P&L/CF.
- **End-to-end pipeline verification (2026-04-24):** reconcile → validate → model-write → model-calc all ran clean on FY2023 10-K + FY2024 10-K. Reconcile 0 novels on both. Validate 48/48 PASS / 0 WARN / 0 FAIL on both. model-write 327 cells. model-calc 2 assumptions + 258 driver cells + 492 forecast cells. Workbook computes without circular refs or broken references (verified via `formulas` package).
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

### Universal model creation architecture

Cross-model integration (GLP-1 + SNAP into CELH Revenue) is deferred per user direction (2026-04-24). The project pivots to generalizing the pipeline so any consumer-staples ticker can run through it with minimal per-ticker work.

Concrete critical path:

1. **Bring a second ticker online.** Recommended: **PEP** (debt-heavy, dividend payer, share repurchases, real FX exposure — meaningfully different shape from CELH). Alternatives: KO, CL. Run the existing pipeline as-is; every failure, novel, and hardcoded-CELH label is a concrete TODO. **Do not build speculative abstractions before this step** — the second ticker's surface area is the evidence base.
2. **Extract `pattern_libraries/generic_forecast_rules.json`** from `calc.py`'s `FORECAST_STATEMENT_SPECS` + `DRIVER_SPECS`. Mirror the existing `generic_line_item_mappings.json` pattern: generic library + per-ticker overrides under `{TICKER}/forecast_overrides.json`. Precedence: ticker override → generic → engine fallback. The `kind` vocabulary (revenue_growth, ratio_of_rev, aoci_rollforward, etc.) stays in Python — it's the dispatch logic, not data. Only **line → kind+driver assignments** move to JSON.
3. **Formalize the ticker onboarding doc** at `Brain\Knowledge\Model Schema\05_ticker_onboarding.md`. One page: directory scaffold, pipeline invocation, novel triage, forecast review, override conventions. Short — no speculative flexibility docs.

Surface area to watch when running PEP:
- `FORECAST_STATEMENT_SPECS` references CELH-specific canonical labels: `Deferred Other Costs - Current/Non-Current`, `Accrued Distributor Termination Fees`, `Note Receivable - Current/Non-Current`, `Convertible Preferred Stock`, `Acquisition of Big Beverages`. PEP will not have these; labels referenced by spec but missing on sheet simply skip (via the `if label not in sheet_rows: continue` guard), but CELH has specs for items PEP doesn't have that still surface other issues.
- `DRIVER_SPECS` references some CELH-specific lines (`Preferred Dividends % of Preferred Balance`, specific lease sub-lines). PEP may or may not have matching rows.
- `apic_rollforward`, `re_rollforward`, `pp_e_rollforward`, `cash_rollforward` should generalize fine — they reference universal canonical labels.
- FX treatment: PEP has real international exposure. The current `zero` treatment for IS/CFO FX Gain (Loss) will understate NI swing; the `aoci_rollforward` for translation FX will be meaningful. Worth revisiting both if PEP's FX is material.

---

## Near horizon — next milestones

1. ~~**Fix forecast BS balance gap**~~ — shipped 2026-04-24. See Active above.
2. **Pull FY2025 10-K from EDGAR.** Accession `0001341766-26-000024`, HTML-only at `https://www.sec.gov/Archives/edgar/data/1341766/000134176626000024/celh-20251231.htm`. Needs one of: `weasyprint` HTML→PDF, `playwright`-driven headless print, or an HTML-aware branch in `financials-extract`. After conversion, run full pipeline; expect a handful of novels from FY2025 10-K wording drift.
3. **Cross-model integration — first cut.** Wire GLP-1 % and SNAP-ban volume at-risk into CELH revenue rows FY2026E–FY2028E (extend through FY2030E per original plan). Blocked until balance gap is fixed.
4. ~~Build `model-calc`~~ — shipped. Historical driver formulas + full three-statement forecast formulas live; verified via `formulas` package.
5. ~~CF orphan-row slotting~~ — shipped. Older-only items are now slotted next to the item that preceded them in the filing where they last appeared, via a per-filing advancing anchor in `resolve_row_positions`.
6. ~~Extractor section-tagging fix~~ — not needed. The "mis-tagging" was a stale `raw_2024_10K.json` left over from an older extract.py. Re-extracted fresh; sections are correct. Reconcile + model-write workarounds retained as defensive.

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
| **Latest session handoff** | `Brain\Sessions\CELH Model\Handoffs\April 23rd Generic Migration Phases 3-7 Session.md` |
| Prior handoff (Phases 1–2) | `Brain\Sessions\CELH Model\Handoffs\April 23rd Generic Library Migration Session.md` |
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
| model-calc skill | `~\.claude\skills\model-calc\` |
