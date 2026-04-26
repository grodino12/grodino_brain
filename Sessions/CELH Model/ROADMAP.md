---
type: roadmap
date: 2026-04-26
project: Celsius HF Case Study
scope: CELH financial model pipeline + universal model creation architecture + (later) GLP-1 / SNAP integration
last_session: "April 26th HTM Walker Build-Out + 12 Filing Clean Session"
---

# Celsius HF Case Study — Roadmap

Living document. Update after each session. **Current project focus: build a universal model creation architecture** that works across any consumer-staples ticker, not just CELH. The original case-study question ("What's the net impact on CELH revenue from GLP-1 headwinds + SNAP energy-drink bans + demographic trends?") is deferred — the pipeline will answer it once the architecture is generalized.

---

## Status at a glance

| Workstream | State | Next action |
|---|---|---|
| **Financials pipeline** (now 7 skills, was 8) | **All shipped** — `financials-extract` (PDF+iXBRL merged 2026-04-25), reconcile, validate, playground, model-write, model-calc, sec-edgar-fetch. model-calc still annual-only | Extend model-calc to quarterly after PG xlsx polish ships |
| **Quarterly pipeline** | Shipped 2026-04-24 — YTD durations for 10-Qs | Polish QTR xlsx (Active §3) |
| **SEC EDGAR ingestion** | Shipped 2026-04-24 — `sec-edgar-fetch` + `--all`. PG: 99 10-Q folders | Pull more tickers on demand |
| **Generic cross-ticker library** | **122 entries** (115 + 7 from 2026-04-26: GEN-CF-052 Depreciation-only, GEN-CF-056 Other Financing Activities, alias widening on CFO/CFI/CFF for `(used in) provided by` parenthetical phrasing, alias additions to GEN-BS-027 for Temporary Equity carrying-amount + Series B preferred) | Grow per novel triage protocol; restore OCI when 4th statement ships |
| **Sign-convention architecture** | **Multi-cell paren detection added 2026-04-26.** `_is_parens_negative()` now handles 4 patterns: (A) single-cell parens-in-text, (B) single-cell parens-as-sibling-spans, (C) multi-cell `<td>(</td><td>VALUE</td><td>)</td>` (modern 10-Q renderer), (D) hybrid. Plus leading currency-symbol stripping (`$ ( 1,278,691 )` → matches Pattern A). Per user 2026-04-26: paren-detection is SOLE sign authority for CF (zero CF library entries carry `sign_convention` overlay — verified); BS/IS additionally layer library `sign_convention` (e.g. NEW-IS-001 Distributor Term flips +327,461 to -327,461 for IS-cascade subtraction). | Stable |
| **Validator architecture** | **14 filer-tie rules 2026-04-26** — BS-1..5, IS-1..3 + IS-5 (cascade GP / OpInc / PreTax / end-to-end NI from line items), IS-4 (NI=PT+tax), CF-1..4. Per user directive: "Pydantic validation comparing calculated NI vs filer-rendered NI in HTML" → IS-5 sums Revenue − cost − opex + non_op + tax and ties to filer's NI canonical. IS-2 catches the class of bug where a single opex row has wrong sign that IS-4 alone misses. | Stable |
| **Model-write cross-filing dedup** | **First-filing-wins per period 2026-04-25 (third session).** Was newer-filing-wins. Filers re-categorize line items between filings, so the original 10-Q/10-K's breakdown is the authoritative match for that period. Plus row consolidation by `canonical_label` (multiple rule_ids that map to same canonical → one excel row, fixes IS cascade double-counting Pre-Tax). Plus 2 layered subtotal validators: CF section/subtotal containment (raises) + cross-filing CF tie-out (warns) | Stable |
| **Library load-time guard** | **`LibraryEntry` Pydantic model 2026-04-25** — `extra="forbid"` catches field-name typos, invalid enum values at load | Stable |
| **Generic forecast-rules library** | Not started | Extract from `calc.py` after QTR polish ships |
| **Ticker onboarding doc** | Not started | One-page guide once QTR xlsx polish stabilizes |
| **GLP-1 / SNAP integration** | Standalone, deferred | Revisit after universal architecture stabilizes |

**Revised critical path:** ~~`model-write`~~ ✓ → ~~generic-library migration~~ ✓ → ~~`model-calc` drivers + forecast~~ ✓ → ~~SEC EDGAR ingestion + iXBRL extractor~~ ✓ → ~~quarterly pipeline~~ ✓ → ~~PG 14-filing clean baseline~~ ✓ → ~~paren-of-value as authoritative sign~~ ✓ → ~~CF-2/CF-3/CF-4 section validators~~ ✓ → ~~first-filing-wins dedup + layered model-write checks~~ ✓ → ~~CELH multi-ticker onboarding (3 10-Ks + 9 10-Qs through new architecture)~~ ✓ → ~~HTM-only iXBRL walker rewrite (drops R-files entirely from primary statements)~~ ✓ 2026-04-26 → ~~CELH 12-filing clean (0 novels, 0 validate fails, 1,182-cell workbook)~~ ✓ 2026-04-26 → ~~multi-cell paren detection (modern 10-Q renderer)~~ ✓ 2026-04-26 → ~~IS-1/IS-2/IS-3/IS-5 cascade validators (catches sign-flipped opex rows that IS-4 alone misses)~~ ✓ 2026-04-26 → ~~Convertible Preferred → Equity layout fold + Net Change in Cash always-synthesized~~ ✓ 2026-04-26 → **PG 14-filing regression on the new HTM-walker** → **third ticker onboarding (PEP / KO)** → **break OCI into 4th statement** → **extend model-calc to quarterly drivers** → **extract generic forecast-rules JSON** → **formalize ticker onboarding flow** → (later) cross-model integration.

**Active propagating rule:** every structural change to the financials pipeline must update `playground_architecture.html` + `playground_schema.html`. Bump `LS_KEY` when NODES/EDGES change so the user's browser picks up fresh defaults instead of cached state. Carry this into every future handoff under "Open decisions / pending work." (User explicitly asked this rule propagate.)

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

### PG cross-year backfill + sign authority + subtotal consolidation (2026-04-25 — third session same day)

- **PG 3-year backfill.** 3 10-Ks (FY2023/24/25) + 11 10-Qs (Q1 FY2023 → Q2 FY2026) — 14 filings total, 0 novels, 0 FAILs. `PG_model_v14.xlsx` ships with 5 historical FY columns + 14 quarterly columns, ANNL P&L 15 rows / QTR P&L 16 rows after Pre-Tax consolidation.
- **Variant collapse architecture.** Reconcile ticker-ledger lookup keys on `(alias, sheet_group)` only (variant axis dropped). One ticker entry serves both 10-K and 10-Q runs; sheet routing comes from `SHEET_NAME[(filing_type, statement_type)]` at item-reconcile time. Killed the parallel-ANNL-entry onboarding requirement for new ticker entries.
- **Paren-of-value as sole sign authority.** `_is_parens_negative()` walks the iXBRL fact element's surrounding HTML — single source of truth across statements/tickers, matches what humans read. Drops sign-attr + negatedLabel inference (was filer-by-filer inconsistent — PG's FY2023 10-K AOCI stacked both, double-flipping vs filer's `(12,220)` visual). Back-solved against PG Q3 FY2023 9M CFI (−2,328 + 9 + 331 − 714 = −2,702 ✓ filer subtotal) and FY2023 10-K AOCI (−12,220 ✓ visual).
- **3 additional iXBRL extractor fixes.** (1) `IXBRL_SUBTOTAL_CONCEPTS` guard — subtotal concepts (`StockholdersEquityIncluding...`, `Assets`, etc.) skip library lookup so they don't fuzzy-match into a sibling line-item canonical (was double-counting equity). (2) `StatementClassOfStockAxis` dimensioned-fact whitelist — Series A/B preferred breakdowns now flow through and sum to the canonical balance (was missing $777M PG preferred). (3) Presentation-linkbase visual ordering DFS — line items sort by filer's intended visual order, not iXBRL XML scan order (PG Q2/Q3 FY2024 tag Impairment as fact #0 in XML but visually present it lower).
- **6 novel-triage library updates.** GEN-BS-042 Par Value of Equity (memo), GEN-BS-043 Treasury Stock - Shares Outstanding (memo, prevents share-count fuzzy-matching the dollar Treasury canonical), GEN-CF-050 Gain (Loss) on Extinguishment of Debt, GEN-CF-051 Net Change in Other Working Capital, GEN-IS-024 Impairment of Intangibles (IS), alias adds on GEN-IS-009 / GEN-CF-003. Library: 109 → 115.
- **Validate: CF-2/CF-3/CF-4 added.** Per-section subtotal tie-out (filer-reported CFO/CFI/CFF vs sum of section components). 10 filer-tie rules total now. Plus slice-alignment fix in `group_items_by_statement` (was iterating ALL raw statements but slicing kept-only items, drifting indices on every 10-Q — silently misattributing values across periods). Plus utf-8 stdout reconfigure (Windows cp1252 was crashing on Δ / em-dash mid-loop and skipping the JSON write). All 14 PG filings: 0 FAILs.
- **Model-write architecture: first-filing-wins + row consolidation + layered subtotal checks.** Dedup flipped from newer-filing-wins to first-filing-wins per period — original 10-Q/10-K's line-item breakdown is what users see when comparing the workbook to that filing (PG redistributed H1 FY2025 Other Noncash between the 2025-Q2 and 2026-Q2 filings without changing the CFO subtotal). Row consolidation by canonical_label — multiple rule_ids that map to the same canonical (PG MAP-IS-001 + GEN-IS-009 both → "Pre-Tax Income (Loss)") now share one excel row. Without this the IS cascade SUM range double-counted Pre-Tax. Plus 2 layered model-write checks: CF section/subtotal containment (raises) and cross-filing CF tie-out (warns) — currently 4 micro-warnings on PG ($2-21M gaps from filer micro-recategorizations). Plus row insertion forward-look-up for atypical filing orders.
- **`.cache/` folder convention.** Per-filing intermediates (raw_*, mapped_*, novels_*) moved to `Model Output/.cache/`. Top-level shows just the canonical `validated_*.json` + workbook + explorer HTML. Updated extract + reconcile SKILL.md examples to use `.cache/` paths. PG output went from 56 files cluttering the top to 16.

### Option B architecture + PG YTD quarterly + model-write QTR parity (2026-04-24 — fourth session same day)

- **Option B shipped.** Library lookup moved from reconcile to extract time. New `financials_schema/lookup.py` shared by both extractors + reconcile (+ validator for normalize_label). `RawLineItem` gains `canonical_label: str | None` + `ledger_rule_id: str | None`. PDF + iXBRL extractors both take `--library`, populate canonical labels at construction. Reconcile slimmed: ticker-ledger overrides only, plus pure-function `SHEET_NAME[(filing_type, statement_type)]` router. Validator: BS anchor detection switched from substring match on raw_filing_label to normalized-set equality (supports `assets current`, `stockholders equity including portion attributable to noncontrolling interest`); IS anchors switched from fuzzy English to exact canonical_label match; mezz detection uses `item.section==MEZZANINE` not label keyword; memo rows excluded from sums; `_signed_sum()` helper applied to BS-5 / IS-3 / IS-4. Rationale: one vocabulary downstream of extract — filer idiosyncrasies converge at the canonical layer instead of needing branches in every consumer.
- **iXBRL extractor hardened.** `raw_filing_label` now comes from filer's presentation-layer display label (scraped from `R{n}.htm` onclick anchors) instead of the us-gaap concept local name. HTML entities unescaped. Per-share concepts (`EarningsPerShare*`, dividend-per-share) + share-count concepts (`WeightedAverageNumberOf*`, `*SharesIssued`) exempted from statement-unit scaling — PG's EPS was rendering 1.94e-06 ($1.94 / 1M) before.
- **Sign-convention end-to-end.** Library's `sign_convention` (`expense_positive` / `contra_account`) propagates through both extractors onto `RawLineItem.sign_convention`. PDF extractor: if PARENS_NEGATIVE notation is detected, use `parens_negative` (value already signed by pdfplumber) instead of library's sign — prevents the CELH Tax double-flip that would otherwise happen. Reconcile ticker overrides also propagate sign_convention (fixed PG ESOP reserve summation). Validator's `_signed_sum()` flips expense_positive/contra_account values. Result: BS-5 gap went from -285,236 to 0 (Treasury Stock flip); IS-4 to 0 (Tax flip).
- **Library splits (Interest / FX / Other income vs expense).** GEN-IS-006/007/008 were sign-agnostic canonicals tagged `expense_positive` — wrong when filers report income + expense as separate lines (both got wrongly flipped). Split into 6 new entries (GEN-IS-029 Interest Income / 030 Interest Expense / 031 FX Gain / 032 FX Loss / 033 Other Non-Op Income / 034 Other Non-Op Expense). Net canonicals (006/007/008) kept for net-reported lines but `sign_convention` dropped — value sign comes from filer's parens (PDF) or xbrli:balance (iXBRL).
- **`"net earnings"` alias disambiguation.** Moved from GEN-IS-011 ("Net Income (Loss)") to GEN-IS-022 ("Net Income (Loss) Including NCI"). Rationale: filers using "NET EARNINGS" (PG/JNJ/KO/COST) all have NCI — that line is consolidated pre-attribution. Filers without NCI use "net income" (stays on GEN-IS-011). Concept `NetIncomeLoss` added as alias to GEN-IS-011 so the attributable-to-parent line routes correctly via concept fallback.
- **CF library expansion (8 new canonicals).** GEN-CF-041 Proceeds from Sale of Assets, GEN-CF-042 Acquisitions Net of Cash, GEN-CF-043 Other Investing, GEN-CF-044 Proceeds from Short-Term Debt, GEN-CF-045 Repayments of Short-Term Debt, GEN-CF-046 Net Change in Other Short-Term Debt, GEN-CF-047 Proceeds from Long-Term Debt, GEN-CF-048 Repayments of Long-Term Debt, GEN-CF-049 Stock Options & Other Financing. Alias widening on GEN-CF-007/034/035/040.
- **BS filing_section on 22 entries.** iXBRL `classify_section` heuristic routes "Cash..." to NCA because concept name lacks "Current". Library `filing_section` is now authoritative (Cash / AR / Inventory / Prepaid → current_assets; PP&E / Goodwill / Intangibles / Other NC → non_current_assets; AP / Accrued / Tax Payable → current_liabilities; Preferred / Common / APIC / AOCI / RE → equity).
- **QTR pipeline pivoted from 3-month to YTD.** Filers (especially PG) report CF only as YTD. Prior "keep 3-month only" design left CF empty for H1/9M filings. `_keep_statement_for_reconcile` now keeps longest duration per period_end. iXBRL extractor tags YTD durations with `fiscal_quarter = filing_fq` so column labels render as "Q2 FY2026" = YTD-through-Q2. Result: PG H1 FY2026 CF has 22 rows (was 0).
- **Model-write QTR parity.** Four `sheet_name == X` conditionals extended to `sheet_name in (X, "QTR X")` in `build_workbook` — unlocks BS subtotal rebuild, BS cascade/grand formulas, CF subtotal SUM formulas, IS subtotal formulas on the QTR sheet family. Also fixed idx-walk alignment bug: iteration skips YTD-losers without advancing idx, so `mapped_line_items` slicing stays aligned (was silently reading items from wrong statements).
- **Library grew 109 → 122 entries.**

### PG novel triage + generic library expansion (2026-04-24 — third session same day)

- **PG reconcile 107 → 0 novels.** Root-caused 5 issues in reconcile/library: variant bug (generic library keyed only to ANNL; invisible to 10-Qs), no CamelCase normalization (us-gaap concept names couldn't match PDF-label aliases), iXBRL subtotal concept names missed by `is_subtotal_label` regex, library gaps (no Long-Term Debt / Treasury Stock / NCI / OCI components / Other NC Liabilities canonical rows), subsection filter too strict for iXBRL items (EPS filing_subsection="eps" rejected iXBRL items with subsection_context=None).
- **Reconcile fixes shipped.** `normalize_label` now splits CamelCase (iXBRL concept names tokenize properly). `build_lookup_index` indexes generic library entries under BOTH ANNL + QTR variants (canonical concepts are variant-agnostic; ticker entries stay variant-specific). `is_subtotal_label` has `IXBRL_SUBTOTAL_CONCEPTS` allowlist (9 concept names: Assets, AssetsCurrent, Liabilities, LiabilitiesCurrent, LiabilitiesAndStockholdersEquity, StockholdersEquity/…IncludingNCI, etc.). `select_entry` single-candidate fallback when item has no subsection context. CELH FY2024+FY2025 10-Ks regression-tested: both still 0 novels.
- **Library: 92 → 109 entries.** 15 us-gaap concept-name aliases added to existing entries. 15 new canonical entries: Short-Term Debt + Current Portion of Long-Term Debt (user-chosen split; `DebtCurrent` aggregate aliased under Current Portion), Other Non-Current Liabilities, Treasury Stock, Noncontrolling Interest (BS), Common Stock Shares Issued (memo), collapsed Inventory detail memo (Raw+WIP+Finished into one entry labeled "Inventories"), Long-Term Debt, NI Including NCI, NI Attributable to NCI, OCI - Total Net of Tax (rendered on IS as placeholder for deferred OCI statement), OCI - AFS Securities / Pension / CI Attributable-to-NCI / CI Including NCI (all memo).
- **PG ticker ledger: 1 new entry.** `NEW-BS-001 "ESOP Debt Retirement Reserve"` as QTR BS contra-equity (`expense_positive`, section=equity). Company-specific per user (most filers don't have a legacy leveraged ESOP). Note flags that parallel ANNL entry needed when first PG 10-K runs.
- **`mapped_2026_Q2.json` written and ready for validate.** Final reconcile stats: 95 mapped + 12 subtotals + 0 novels + 0 fuzzy fallbacks.
- **Architectural tangent: "move library to extract time?"** User proposed routing generic library through extractors so RawFiling carries canonical labels. Scoped refactor (4 skills, new source_label/canonical_label fields, shared helper). Pushed back with peer-inputs-to-reconcile symmetry argument; user agreed, reverted.
- **Playground scaffolds refreshed.** `scaffoldBody()` entries for financials-extract / financials-reconcile / financials-validate / financials-playground / model-write / model-calc all rewritten — the text was stale (CELH-only language, pre-library-migration references, xlsm/VBA assumptions). `schemaLine()` + `scopeLine()` + `updatePrompt()` ledgerNote updated. `pattern-libraries` node consolidated (single node serves both PDF extract + reconcile, reflecting physical single-folder reality). LS_KEY bumped v5 → v6 → v7 → v8.
- **Memory feedback saved this session:**
  - `feedback_novel_triage_protocol.md` — when reconcile surfaces novels: check generic library → check ticker ledger → escalate to user with scope/disposition/model_label/render questions. Claude does NOT pick labels.
  - `feedback_token_efficiency.md` — 8 habits for efficient long sessions (short default responses, one question at a time, no unilateral decisions needing retroactive review, Grep before Read, trim command output, no intermediate artifacts).

### SEC EDGAR + iXBRL + quarterly pipeline (2026-04-24 — second session same day)

- **`sec-edgar-fetch` shipped.** New skill at `~\.claude\skills\sec-edgar-fetch\`. Pulls 10-K / 10-Q primary iXBRL HTMLs + `Financial_Report.xlsx` (when SEC has generated it) + cumulative `companyfacts.json` into `Brain\Sources\{TICKER}\{QUARTER}\filings\`. SEC-polite: 5 req/sec throttle, User-Agent `rodinogj12@gmail.com`, retry on 429/5xx. Writes per-filing `.meta.json` sidecar with accession + archive URL so downstream skills can locate FilingSummary.xml without re-querying SEC. **`--all` flag walks the full submissions history** (recent + paginated archives in `filings.files`). Gap-skip per artifact; idempotent + resumable.
- **`financials-extract-ixbrl` shipped.** New skill at `~\.claude\skills\financials-extract-ixbrl\`. Emits the same `RawFiling` JSON shape as PDF extractor — plug-compatible downstream. Uses SEC's **presentation linkbase** (`FilingSummary.xml` + per-role `R{n}.htm` sidecars) for authoritative IS/CI/BS/CF/SE classification (not heuristic prefix matching). Parses iXBRL via lxml's **XML parser** — HTMLParser mangles namespaces. Merges CI into IS. Top-2 BS-date filter kills SE roll-forward reference balances that leak in via shared concepts. `fiscal_quarter=None` for YTD durations so "Q2" isn't misleadingly applied to a 6-month period.
- **PG historical pull** — ran `sec-edgar-fetch --ticker PG --all --forms 10-Q`. 99 quarter folders on disk from 1994-Q2 through 2026-Q2. Pre-2009 filings are HTML-only (no inline XBRL); only ~50 of the 99 are iXBRL-era and thus extractable via the new extractor. Older filings available as raw HTML for manual reading or future `companyfacts.json` direct-query.
- **Quarterly pipeline shipped across 3 skills** (same session) — separate sheet family, 3-month only, triggered by `FilingType == 10-Q`:
  - `financials-reconcile` — lookup key extended to `(label, sheet_group, sheet_variant)` where variant ∈ {ANNL, QTR}. `_target_variant(filing_type)` picks by filing type. `_keep_statement_for_reconcile` drops 10-Q statements whose `period_length_weeks ∉ [11, 15]` before the mapping loop (BS instants exempt). NovelReport entries carry `target_variant`.
  - `financials-validate` — period_label format fix (`Q2 FY2026` not `Q2 2026`). Otherwise period-agnostic: reconcile's YTD drop means validate sees clean 3-month data and all existing rules work without change. BS-7 remains deferred.
  - `model-write` — new `QTR P&L` / `QTR BS` / `QTR CF` sheet family. `stmt_to_sheet(stmt_type, filing_type)` routes. QTR column labels `Q{N} FY{YYYY}` (disambiguates quarters within a fiscal year). QTR forecast columns skipped in v1 (deferred to model-calc). Empty sheets suppressed.
- **`financials-playground` tooltip dispatch** — `citation_tooltip()` detects `.htm` / `.html` source_path and renders iXBRL-aware format (`Concept: ... | From: ... | Period: ...`) instead of the `p.1` placeholder. PDF path unchanged.
- **`playground_architecture.html` overhauled** — new input layer (2 rows: externals on top, fetch skill + stores below), new extract-layer node for `financials-extract-ixbrl`, new edges, new scaffolding prompts for both new skills. Header count: "7 of 8 skills built." Reconcile + model-write node descriptions updated with quarterly behavior. Title: "Financials Pipeline" (was CELH-specific). LS_KEY bumped `v1 → v5`.
- **PG ticker root scaffolded** at `Brain\Knowledge\Model Schema\PG\` with `config.json` (June FYE, expected ranges in $millions), empty `decisions_ledger.json`, empty `anomalies.json`. Extracted PG Q2 FY26 10-Q → 199 line items / 10 Statements. Reconcile --dry-run surfaced **107 novel items** — all structural code paths exercised without errors. Novel breakdown: BS 64, IS 41, CF 2. **⚠️ 107 flagged as suspiciously high** — triage required (see Active §1 + Near-horizon §13).
- **Memory feedback saved this session:**
  - `feedback_keep_playgrounds_in_sync.md` — every structural change must update both playgrounds; bump LS_KEY on NODES/EDGES changes. User explicitly asked this rule propagate across handoffs.
  - `feedback_session_handoffs.md` (extended) — handoffs now required to include the playground-sync reminder under "Open decisions / pending work".

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

1. ~~**Run PG end-to-end to a first QTR xlsx.**~~ Shipped 2026-04-24.
2. ~~**Framework audit (extract merge, sign-convention overhaul, section-driven validators, LibraryEntry guard, dead-code purge).**~~ Shipped 2026-04-25.
3. ~~**Refresh playgrounds** (extract-merge collapse, CASH_OTHER, sign 3-value, section-driven validators, LibraryEntry, RawLineItem field updates).~~ Shipped 2026-04-25 (second session). LS_KEY bumped v8 → v9.
4. ~~**PG end-to-end on new architecture (preferredLabel parsing for visual signs, multi-statement concept attribution, CI dropped from IS, IS canonical NI semantics, Pre-Tax override for PG, IS cascade injection + PLUS-SUM formulas, NI Less NCI formula, CF Net Change formula, EPS matcher).**~~ Shipped 2026-04-25 (second session). PG H1 FY2026 ties to filed IS / BS / CF.
5. ~~**Validator trim 18 → 7 filer-tie rules.**~~ Shipped 2026-04-25 (second session).
6. ~~**PG 3-year cross-year backfill.**~~ Shipped 2026-04-25 (third session). 3 10-Ks (FY2023/24/25) + 11 10-Qs (Q1 FY2023 → Q2 FY2026); 0 novels, 0 FAILs across all 14. `PG_model_v14.xlsx` is the canonical workbook.
7. ~~**Variant collapse.**~~ Shipped 2026-04-25 (third session). Ticker-ledger lookup is variant-agnostic; `MAP-IS-001` and `NEW-BS-001` fire on both 10-K and 10-Q without parallel entries. Killed the "PG full 10-K onboarding requires parallel ANNL entries" carry-over.
8. ~~**Paren-of-value visual sign.**~~ Shipped 2026-04-25 (third session). Replaced sign-attr + negatedLabel inference with `_is_parens_negative()` walking the iXBRL fact's surrounding HTML. Also iXBRL extractor adds: subtotal-concept guard, class-of-stock dimension whitelist (Series A/B preferred), presentation-linkbase visual ordering DFS.
9. ~~**CF-2/CF-3/CF-4 section validators + slice-alignment fix.**~~ Shipped 2026-04-25 (third session). validate.py now 10 rules. `group_items_by_statement` no longer drifts indices on 10-Qs.
10. ~~**Model-write: first-filing-wins, row consolidation, layered subtotal checks.**~~ Shipped 2026-04-25 (third session). Original-filer breakdown wins per period. Two rule_ids → same canonical → one row. CF section containment raises; cross-filing CF tie-out warns on micro-shifts.
11. ~~**Multi-ticker validation.**~~ Shipped 2026-04-26 against CELH (3 10-Ks + 9 10-Qs). Surfaced 9 framework gaps; all fixed. Result: 0 novels across 12 filings, but 2025-FY validation still failing on missing Intangibles ($1.5B+ from Alani Nu acquisition tagged with dimensioned facts only).
12. ~~**HTM-only iXBRL extractor rewrite.**~~ Shipped 2026-04-26. New `ixbrl_path.py` (~830 lines) walks primary HTM tables in document order — first td = label, value cells = ix:nonFraction with paren-detected sign. Multi-table primary statements (CELH CF spans 3 sub-tables); title detection bounded (anchored regex, ≤150 char, no trailing period, notes-section terminator gated on `primary_collected`); OCI block STOP in combined IS+CI tables; CF non-cash supplemental STOP; cash beg/end instant→duration fold with 1-day tolerance; equity-class label-cell handling (text+ix mixed → memo facts with synthesized labels skip library lookup, route to reconcile `_memo` passthrough). All R-file machinery deleted. Per `feedback_no_rfiles_for_financials.md`.
13. ~~**CELH 12-filing clean integration.**~~ Shipped 2026-04-26. All 12 filings (3 10-Ks + 9 10-Qs) → 0 novels, 0 validate fails, single `CELH_model.xlsx` with 1,182 cells. ANNL 5y FY2021–FY2025 + 6 forecast cols, BS 4 instants, CF 5y, QTR sheets 12 quarters. Multi-cell paren detection (modern 10-Q renderer pattern `<td>(</td><td>VALUE</td><td>)</td>`) plus leading currency-symbol stripping. Stale validated_*_*.json (underscore-named, prior session) caused cross-filing dedup doubling on CFI for 2025-12-31 — removed.
14. ~~**IS-1 / IS-2 / IS-3 / IS-5 cascade validators.**~~ Shipped 2026-04-26. Per user directive: "Pydantic validation comparing calculated NI vs filer-rendered NI in HTML". IS-2 catches sign-flipped opex rows that IS-4 alone misses (the Distributor Termination Fees +327,461 case). validate.py now 14 rules per filing.
15. ~~**Convertible preferred → Equity layout fold.**~~ Shipped 2026-04-26. Per user directive. Walker keeps section=mezzanine (faithful to filer's ASC 480 rendering — preserves BS-5 tie to filer's TSE). model-write's BS layout buckets `mezzanine` items into `equity` so the workbook shows convertible preferred under SE.
16. ~~**Net Change in Cash always-synthesized subtotal.**~~ Shipped 2026-04-26. Per user directive. model-write inserts `=CFO+CFI+CFF+CashOther` row at end of CF section even when filer doesn't break it out.
17. **NEXT SESSION OPENS WITH: PG 14-filing regression on the new HTM-walker.** Confirm the rewrite holds across PG (3 10-Ks + 11 10-Qs). PG is the canonical "filer that breaks every assumption" — Q2/Q3 FY2024 visual-ordering, ESOP reserve, redeemable preferred. If PG re-validates clean, the architecture is generalized.
18. **Onboard a third ticker (PEP or KO)** after PG re-validation. One-page onboarding flow: mkdir ticker root, drop config.json, run extract→reconcile→validate→model-write, surface novels for triage.
19. **`_pre.xml` linkbase removal cleanup pass** — current code keeps it dormant; do a delete-pass once PG also passes. Per `feedback_no_rfiles_for_financials.md`.
20. **Break OCI into its own worksheet (4th statement).** Carried. Walker currently STOPS on OCI header; emit them as `StatementType.COMPREHENSIVE_INCOME` once that StatementType ships.
21. **Extend `model-calc` to quarterly drivers.** Currently annual-only.
22. **Extract `pattern_libraries/generic_forecast_rules.json`** from `calc.py`. Blocked on §21.
23. **Formalize the ticker onboarding doc** at `Brain\Knowledge\Model Schema\05_ticker_onboarding.md`.
24. **`financials-validate/SKILL.md` description stale** — still says "10 filer-tie rules". Update to "14 rules: BS-1..5, IS-1..3 + IS-5, IS-4, CF-1..4". Add the IS cascade rationale (catches sign-flipped opex rows).
25. **Refresh playgrounds + LS_KEY v9 → v10** for: HTM-only walker (R-file nodes deleted from graph), multi-cell paren detection, IS-1..3+IS-5, mezz→equity fold, NetChange always-synth, .cache/ convention. Carried per active propagating rule.
26. **Cross-filing CF tie-out micro-warnings on PG** ($2-21M gaps on 4 periods). Acceptable for now; revisit if larger gaps appear elsewhere.

Surface area to watch when running PEP:
- `FORECAST_STATEMENT_SPECS` references CELH-specific canonical labels: `Deferred Other Costs - Current/Non-Current`, `Accrued Distributor Termination Fees`, `Note Receivable - Current/Non-Current`, `Convertible Preferred Stock`, `Acquisition of Big Beverages`. PEP will not have these; labels referenced by spec but missing on sheet simply skip (via the `if label not in sheet_rows: continue` guard), but CELH has specs for items PEP doesn't have that still surface other issues.
- `DRIVER_SPECS` references some CELH-specific lines (`Preferred Dividends % of Preferred Balance`, specific lease sub-lines). PEP may or may not have matching rows.
- `apic_rollforward`, `re_rollforward`, `pp_e_rollforward`, `cash_rollforward` should generalize fine — they reference universal canonical labels.
- FX treatment: PEP has real international exposure. The current `zero` treatment for IS/CFO FX Gain (Loss) will understate NI swing; the `aoci_rollforward` for translation FX will be meaningful. Worth revisiting both if PEP's FX is material.

---

## Near horizon — next milestones

1. ~~**Fix forecast BS balance gap**~~ — shipped 2026-04-24 (first session).
2. ~~**Number format propagation to forecast cells**~~ — shipped 2026-04-24.
3. ~~**Allowance for Credit Losses as `ratio_of_rev`**~~ — shipped 2026-04-24.
4. ~~**iXBRL-concept-keyed generic library layer**~~ — shipped 2026-04-24 (third session) as reconcile-side CamelCase normalization + us-gaap aliases on existing library entries. Novel count diagnosis resolved: PDF-label mismatch WAS the main issue; CamelCase splitter in `normalize_label` bridges the vocabulary gap; no separate library needed.
5. ~~**Run PG through the pipeline to a first QTR xlsx.**~~ Shipped 2026-04-24 (fourth session).
6. ~~**PG xlsx polish.**~~ Shipped 2026-04-25 (second session). Gross Profit row injection, all IS subtotals as formulas, NI Less NCI formula, CF Net Change formula, EPS matcher fixed.
7. ~~**Refresh playgrounds.**~~ Shipped 2026-04-25 (second session).
8. **CELH regression confirmation.** See Active §6.
9. **Break OCI into its own worksheet.** See Active §7.
10. **Extract `pattern_libraries/generic_forecast_rules.json`.** Blocked on §8 (model-calc quarterly).
11. **Ticker onboarding doc** at `Brain\Knowledge\Model Schema\05_ticker_onboarding.md`.
12. **Close the Allowance-driven BS gap** — optional polish. Low priority (<1% of TA at CELH).
13. **Cross-model integration (GLP-1 + SNAP → CELH Revenue Growth %).** Deferred indefinitely per user.
14. ~~Build `model-calc`~~ — shipped.
15. ~~CF orphan-row slotting~~ — shipped.

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
5. ~~**10-Q quarterly pipeline support.**~~ **Shipped 2026-04-24 (second session same day).** Reconcile filters 10-Qs to 3-month durations and routes to QTR P&L / QTR BS / QTR CF. model-write emits the QTR sheet family. Still pending: model-calc quarterly drivers (see Active §4).
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
| **Latest session handoff** | `Brain\Sessions\CELH Model\Handoffs\April 26th HTM Walker Build-Out + 12 Filing Clean Session.md` |
| Prior handoffs (rotated) | `Brain\Sessions\CELH Model\Handoffs\Archive\` |
| **sec-edgar-fetch skill** | `~\.claude\skills\sec-edgar-fetch\` |
| **financials-extract-ixbrl skill** | `~\.claude\skills\financials-extract-ixbrl\` |
| PG ticker root (1 ticker-specific entry for ESOP reserve) | `Brain\Knowledge\Model Schema\PG\` |
| PG filing archive (99 10-Qs) | `Brain\Sources\PG\` |
| PG MappedFiling (ready for validate) | `Brain\Knowledge\Model Schema\PG\Model Output\mapped_2026_Q2.json` |
| PG NovelReport (0 novels) | `Brain\Knowledge\Model Schema\PG\Model Output\novels_2026_Q2.json` |
| **Generic cross-ticker library (115 entries)** | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` |
| Shared lookup module (new this session) | `Brain\Knowledge\Model Schema\financials-schema\financials_schema\lookup.py` |
| PG canonical workbook (3 yrs × 14 filings) | `Brain\Knowledge\Model Schema\PG\Model Output\PG_model_v14.xlsx` |
| PG validated JSONs (top-level, model-write input) | `Brain\Knowledge\Model Schema\PG\Model Output\validated_*.json` |
| PG intermediates (raw / mapped / novels) | `Brain\Knowledge\Model Schema\PG\Model Output\.cache\` |
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
