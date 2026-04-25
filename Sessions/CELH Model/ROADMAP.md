---
type: roadmap
date: 2026-04-25
project: Celsius HF Case Study
scope: CELH financial model pipeline + universal model creation architecture + (later) GLP-1 / SNAP integration
last_session: "April 25th Framework Audit + Section-Driven Architecture Session"
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
| **Generic cross-ticker library** | **109 entries** (down from 122: -7 OCI removed, -6 split donors after recombination). All BS+CF+IS have `filing_section` set (or intentionally null on bottom-line/reconciliation rows). Sign_convention now on 7 entries only | Grow per novel triage protocol; restore OCI when 4th statement ships |
| **Sign-convention architecture** | **Reduced to abs-based 3-value (`as_reported` / `positive` / `negative`) 2026-04-25.** IS-only keyword detection in `match_raw_item` covers split-direction lines (Income Tax, FX, Other Non-Op). `parens_negative` special-case removed | Stable |
| **Validator architecture** | **Section-driven 2026-04-25** — `partition_balance_sheet` and `partition_cash_flow` bucket by `item.section`; subtotals captured as anchors. CF-1, X-4 keyed on `canonical_label` not English prose. UNCLASSIFIED triggers reconcile halt | Stable; CF-2 keys on model_label (canonical-equivalent) |
| **Library load-time guard** | **`LibraryEntry` Pydantic model 2026-04-25** — `extra="forbid"` catches field-name typos, invalid enum values at load | Stable |
| **Generic forecast-rules library** | Not started | Extract from `calc.py` after QTR polish ships |
| **Ticker onboarding doc** | Not started | One-page guide once QTR xlsx polish stabilizes |
| **GLP-1 / SNAP integration** | Standalone, deferred | Revisit after universal architecture stabilizes |

**Revised critical path:** ~~`model-write`~~ ✓ → ~~generic-library migration~~ ✓ → ~~`model-calc` drivers + forecast~~ ✓ → ~~fix forecast BS balance gap~~ ✓ → ~~SEC EDGAR ingestion + iXBRL extractor~~ ✓ → ~~quarterly pipeline~~ ✓ → ~~triage PG 107-novel count~~ ✓ → ~~Option B architecture~~ ✓ → ~~sign-convention end-to-end~~ ✓ → ~~library splits~~ ✓ → ~~QTR pivot to YTD durations~~ ✓ → ~~model-write QTR parity port~~ ✓ → ~~merge two extract skills into one~~ ✓ → ~~sign-convention reduced to abs-based 3-value with IS keyword detection~~ ✓ → ~~library splits recombined~~ ✓ → ~~validators: state machines + English prose anchors → section-driven + canonical_label~~ ✓ → ~~UNCLASSIFIED enforcement at reconcile~~ ✓ → ~~LibraryEntry Pydantic guard~~ ✓ → ~~framework audit~~ ✓ → **refresh playgrounds (large backlog: extract-merge, lookup.py LibraryEntry, CASH_OTHER, sign 3-value, section-driven partitions, canonical_label-keyed validators)** → **CELH + PG regressions on new architecture** → **PG xlsx polish (NI formula self-reference, CF subtotal rows, preferred-stock canonical)** → **answer LTM-period validation question** → **break OCI into 4th statement** → **extend model-calc to quarterly drivers** → **extract generic forecast-rules JSON** → **formalize ticker onboarding flow** → (later) cross-model integration.

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
3. **Refresh playgrounds** (active propagating rule, very large backlog from 04-24 + 04-25 sessions):
   - `playground_architecture.html`: collapse the two extract nodes into one (`financials-extract` only); add LibraryEntry validator step inside lookup; add CASH_OTHER section + 4-section CF; change sign_convention enum to 3-value; reflect section-driven validator architecture.
   - `playground_schema.html`: SignConvention 3-value enum; Section enum changes (CASH_OTHER added, FX_RECONCILIATION removed); LibraryEntry model.
   - Bump `LS_KEY`.
4. **CELH + PG regressions on the new architecture.** Overdue — last clean run was before the merge / sign-convention overhaul / section-driven validators. Expected to surface: fuzzy-threshold-70 false positives, library entries needing concept-name aliases for iXBRL, possibly section-fix triages from the UNCLASSIFIED halt.
5. **PG xlsx polish (carried from prior handoff):**
   - **IS "Net Income (Loss)" subtotal formula self-reference**: emits `=B9-SUM(B10:B12)` where row 12 is the NI row itself.
   - **CF subtotal rows (CFO / CFI / CFF / NetChange) not emitted**: need `insert_cf_subtotal_slots` helper.
   - **"Convertible Preferred Stock" mis-label**: PG's preferred is ESOP-linked. Split into Preferred Stock vs Convertible Preferred, or rename.
   - **EPS format branch**: `"EPS" in label.upper()` doesn't match "Basic Earnings (Loss) per Share".
6. **Add IS D&A library entry** when we hit a filer that breaks D&A out on the IS (PG embeds it in COGS/SG&A).
7. **Answer LTM-period validation question for quarterlies.** Carried.
8. **Break OCI into its own worksheet (4th statement).** Carried. Library entries pulled this session, will be restored when sheet exists. Scope: add `COMPREHENSIVE_INCOME` to StatementType enum, un-merge CI from IS, OCI/QTR OCI sheets in model-write, OCI-1 + X-5 validators, restore the 7 GEN-IS entries.
9. **Extend `model-calc` to quarterly drivers.** Currently annual-only.
10. **Extract `pattern_libraries/generic_forecast_rules.json`** from `calc.py`. Blocked on §9.
11. **Formalize the ticker onboarding doc** at `Brain\Knowledge\Model Schema\05_ticker_onboarding.md`.
12. **PG first 10-K onboarding** — parallel ANNL BS entry for `NEW-BS-001 ESOP Debt Retirement Reserve`.
13. **PG ledger NEW-BS-001 note text** — still says "stored expense_positive" (cosmetic; encoding quirks blocked auto-edit).

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
6. **PG xlsx polish.** See Active §4. Specifically: self-ref NI formula, CF subtotal row insertion, preferred-stock label, EPS format branch.
7. **Refresh playgrounds** (backlog from Option B). See Active §5.
8. **CELH regression confirmation.** See Active §6.
9. **Answer LTM-period validation question.** See Active §7.
10. **Break OCI into its own worksheet.** See Active §8.
11. **Extract `pattern_libraries/generic_forecast_rules.json`.** Blocked on §9 (model-calc quarterly).
12. **Ticker onboarding doc** at `Brain\Knowledge\Model Schema\05_ticker_onboarding.md`.
13. **Close the Allowance-driven BS gap** — optional polish. Low priority (<1% of TA at CELH).
14. **Cross-model integration (GLP-1 + SNAP → CELH Revenue Growth %).** Deferred indefinitely per user.
15. ~~Build `model-calc`~~ — shipped.
16. ~~CF orphan-row slotting~~ — shipped.

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
| **Latest session handoff** | `Brain\Sessions\CELH Model\Handoffs\April 25th Framework Audit + Section-Driven Architecture Session.md` |
| Prior handoff (Option B + PG YTD) | `Brain\Sessions\CELH Model\Handoffs\April 24th Option B Migration + PG YTD Quarterly Session.md` |
| Prior handoff (PG novel triage + library expansion) | `Brain\Sessions\CELH Model\Handoffs\April 24th PG Novel Triage + Library Expansion Session.md` |
| Prior handoff (quarterly pipeline) | `Brain\Sessions\CELH Model\Handoffs\April 24th SEC EDGAR + Quarterly Pipeline Session.md` |
| Prior handoff (model-calc forecast balance) | `Brain\Sessions\CELH Model\Handoffs\April 24th Model-Calc Forecast Balance Session.md` |
| Prior handoff (Phases 3–7) | `Brain\Sessions\CELH Model\Handoffs\April 23rd Generic Migration Phases 3-7 Session.md` |
| Prior handoff (Phases 1–2) | `Brain\Sessions\CELH Model\Handoffs\April 23rd Generic Library Migration Session.md` |
| Prior handoff (model-write shipped) | `Brain\Sessions\CELH Model\Handoffs\April 23rd Model-Write Shipped Session.md` |
| Prior handoff (playground polish) | `Brain\Sessions\CELH Model\Handoffs\April 22nd Playground Polish Session.md` |
| **sec-edgar-fetch skill** | `~\.claude\skills\sec-edgar-fetch\` |
| **financials-extract-ixbrl skill** | `~\.claude\skills\financials-extract-ixbrl\` |
| PG ticker root (1 ticker-specific entry for ESOP reserve) | `Brain\Knowledge\Model Schema\PG\` |
| PG filing archive (99 10-Qs) | `Brain\Sources\PG\` |
| PG MappedFiling (ready for validate) | `Brain\Knowledge\Model Schema\PG\Model Output\mapped_2026_Q2.json` |
| PG NovelReport (0 novels) | `Brain\Knowledge\Model Schema\PG\Model Output\novels_2026_Q2.json` |
| **Generic cross-ticker library (122 entries)** | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` |
| Shared lookup module (new this session) | `Brain\Knowledge\Model Schema\financials-schema\financials_schema\lookup.py` |
| PG_model.xlsx (first QTR build) | `Brain\Knowledge\Model Schema\PG\Model Output\PG_model.xlsx` |
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
