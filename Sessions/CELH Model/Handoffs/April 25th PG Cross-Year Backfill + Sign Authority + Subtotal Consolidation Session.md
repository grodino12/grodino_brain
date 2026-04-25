---
type: session-handoff
date: 2026-04-25
topic: PG cross-year backfill (3 10-Ks + 11 10-Qs), variant-collapse architecture, paren-of-value as authoritative sign, subtotal row consolidation, layered subtotal-tie-out validation across per-filing + post-dedup workbook layers.
tags: [session, pg-backfill, variant-collapse, ixbrl-paren-sign, cf-section-validators, row-consolidation, cross-filing-dedup]
---

# April 25th — PG Cross-Year Backfill + Sign Authority + Subtotal Consolidation Session

Picks up from `Archive\April 25th PG Filing Tie-Out + Validator Trim Session.md`. That session got PG H1 FY2026 through end-to-end and trimmed the validator set to 7 filer-tie rules. This session scaled up to **3 fiscal years × all PG quarterly filings (3 10-Ks + 11 10-Qs)** and surfaced — then fixed — the deeper architectural issues that don't appear with one filing. **Next**: download a couple more tickers and confirm the updated framework holds across companies.

## Starting state

- One PG 10-Q (H1 FY2026) running clean. No 10-Ks, no multi-period workbook.
- Library lookup variant-split between ANNL/QTR for ticker entries — required parallel ANNL entries to onboard 10-Ks.
- iXBRL extractor inferred sign from XBRL `sign` attr + presentation `negatedLabel` — filer-by-filer inconsistent.
- Validate ran CF-1 (Net Change in Cash) but had no per-section subtotal checks.
- Model-write dedup was newer-filing-wins per period; row layout keyed by rule_id (so two rule_ids → same canonical → two rows).

## Work done this session

### 1. PG backfill end-to-end

Pulled FY2023/24/25 10-Ks via `sec-edgar-fetch --ticker PG --all --forms 10-K` (32 fiscal years now cached). 14 filings total (3 10-Ks + 11 10-Qs; 2026-Q3 not yet filed). All 14 reach `validated_*.json` with **0 novels, 0 FAILs**.

### 2. Variant collapse — one library entry serves both 10-K and 10-Q

`reconcile.py`: dropped `_sheet_variant` / `_target_variant`; `build_ticker_index` now keys on `(normalized_alias, sheet_group)` only. Ticker-entry path in `reconcile_item` derives `model_sheet` from `SHEET_NAME[(filing_type, statement_type)]` instead of the entry's stored field. PG ledger entries (MAP-IS-001 Pre-Tax override, NEW-BS-001 ESOP Reserve) now fire on both 10-K and 10-Q without duplicates.

### 3. Six novel-triage library updates (per user decisions)

Added: GEN-BS-042 Par Value of Equity (memo), GEN-CF-050 Gain (Loss) on Extinguishment of Debt, GEN-IS-024 Impairment of Intangibles (IS, operating_expenses), GEN-CF-051 Net Change in Other Working Capital. Aliases extended on GEN-CF-003 (Impairment CF), GEN-IS-009 (Pre-Tax — added `income loss from continuing operations before income taxes`). Plus GEN-BS-043 Treasury Stock - Shares Outstanding (memo) added during extractor-bug triage.

### 4. iXBRL extractor — paren-of-value as authoritative sign

Replaced sign-attr + `negatedLabel` inference with `_is_parens_negative()` that walks the iXBRL fact element's surrounding text in the rendered HTML. If wrapped in `(VALUE)`, value is negative; otherwise positive. Drops `negate_map` consumption in `group_into_statements`. Single source of truth across statements/tickers — matches what humans read off the rendered filing. Back-solved against PG Q3 FY2023 9M CFI (−2,328 + 9 + 331 − 714 = −2,702 ✓ filer-reported) and PG FY2023 10-K AOCI (−12,220 ✓ filer visual). Eliminates the sign-attr-vs-negatedLabel double-flip class of bugs entirely.

Also: `IXBRL_SUBTOTAL_CONCEPTS` guard at extract (subtotal concepts skip library lookup), `StatementClassOfStockAxis` dimensioned-fact whitelist (Series A/B preferred breakdowns now flow through), presentation-linkbase visual ordering (DFS over `presentationArc/@order` — fixes PG Q2/Q3 FY2024 Impairment placement that XML scan order got wrong).

### 5. Validate — added CF-2/CF-3/CF-4 + slice-alignment fix + Windows console encoding

CF-2/CF-3/CF-4 added in `validate.py`: per-section subtotal tie-out (filer-reported CFO/CFI/CFF vs sum of section components). Pattern: `_run_cf_section()` shared helper; `partition_cash_flow` already buckets correctly.

Slice-alignment bug found in `group_items_by_statement`: was iterating ALL raw statements but slicing the kept-only `mapped_line_items` list — silently mixing values across periods. Fixed by skipping the same statements `keep_statement_for_pipeline` drops at reconcile time.

Windows cp1252 console encoding crash on Δ / em-dash characters: `validate.py main()` now does `sys.stdout.reconfigure(encoding="utf-8")` so the loop completes and the output JSON gets written.

### 6. Model-write — row consolidation, first-filing-wins, CF-section validators

**Row consolidation by canonical_label.** When multiple rule_ids share a canonical label (PG MAP-IS-001 + GEN-IS-009 both → "Pre-Tax Income (Loss)"), they now point at the SAME excel_row. Without this, the IS cascade SUM range double-counted Pre-Tax (filer-extracted row + cascade formula row both present). Fix in `resolve_row_positions` final stage: build `label_to_row` map, alias subsequent rule_ids to the first row's index.

**First-filing-wins dedup** (was newer-filing-wins). When a period appears in multiple filings (current in one, comparative in later ones), keep the value from the filing that originally reported it. Filers re-categorize line items between filings (PG's H1 FY2025 "Other Noncash" was 135 in 2025-Q2 but the 2026-Q2 comparative tagged it as a different concept worth −1,484); the original filing's breakdown is what users see when comparing the workbook to a filing.

**Two new layered checks in model-write:**
- CF section/subtotal *containment* (raises): every section-tagged row must fall in its subtotal's SUM range. Catches row-placement bugs.
- Cross-filing CF section/subtotal *tie-out* (warns, doesn't raise): for each (period, section), workbook-formula sum must match the dedup-picked subtotal. Fires when filers re-categorize between filings — currently 4 micro-shifts on PG ($2-21M).

Plus: row insertion now does forward look-up when no prior anchor exists (`_CASCADE_<section>` injection has its own placement logic; this fixed a Q2/Q3 FY2024 Impairment tail-of-sheet bug).

### 7. .cache/ folder convention

Per-filing `raw_*.json`, `mapped_*.json`, `novels_*.json` moved to `Model Output/.cache/`. Top level shows just the canonical `validated_*.json` (the only file model-write consumes) + the workbook + explorer HTML. Updated extract + reconcile SKILL.md examples to use `.cache/` paths.

## Current state

- **PG**: 14 filings clean (0 novels, 0 FAILs); `PG_model_v14.xlsx` is the canonical workbook; 5 historical FY columns + 14 quarterly columns; QTR P&L 16 rows, ANNL P&L 15 rows after Pre-Tax consolidation.
- **Validate**: 7 filer-tie rules → **10 rules** now (BS-1..BS-5, IS-4, CF-1, **CF-2, CF-3, CF-4**). 0 FAILs across all 14 PG filings.
- **Library**: 109 → **115 entries** (six novel-triage adds).
- **Model-write**: row consolidation + first-filing-wins + 2 layered subtotal validators (containment raises, cross-filing warns).
- **Extractor**: paren-of-value is the sole sign authority; subtotal-concept guard + class-of-stock dimension whitelist + presentation-linkbase visual ordering.

## Open decisions / pending work

1. **Multi-ticker validation** — pull a couple more consumer-staples tickers (KO/PEP/COST?) and run them through the pipeline to confirm the architecture generalizes. Primary purpose of next session.
2. **OCI 4th statement** (carried) — restore the 7 OCI library entries when the sheet ships.
3. **`financials-validate/SKILL.md` description** — still says "BS-1..BS-7, CF-1/CF-2, X-1..X-4". Update to 10-rule reality.
4. **Cross-filing CF tie-out warnings** — 4 micro-gaps ($2-21M) on PG QTR CF (2023-12-31 financing, 2024-03-31 investing, 2025-03-31 investing, 2025-09-30 financing). Acceptable for now; revisit if larger gaps appear on other tickers.
5. **Active propagating rules** — playgrounds + LS_KEY (currently v10) need refresh for the variant collapse, paren-of-value sign, CF-2/3/4, row consolidation, first-filing-wins dedup, layered model-write checks, .cache/ convention. Bumping LS_KEY → v11 next session.
6. **`model-calc` quarterly drivers** (long carry) — QTR sheets still no forecasts.

## Key file paths

| Purpose | Path |
|---|---|
| This handoff | `Brain\Sessions\CELH Model\Handoffs\April 25th PG Cross-Year Backfill + Sign Authority + Subtotal Consolidation Session.md` |
| Prior handoffs (rotated) | `Brain\Sessions\CELH Model\Handoffs\Archive\` |
| Roadmap | `Brain\Sessions\CELH Model\ROADMAP.md` |
| iXBRL extractor (paren-sign, subtotal guard, class-of-stock whitelist, presentation-order DFS) | `~\.claude\skills\financials-extract\scripts\ixbrl_path.py` |
| Reconcile (variant collapse) | `~\.claude\skills\financials-reconcile\scripts\reconcile.py` |
| Validate (CF-2/3/4, slice-alignment, utf-8 stdout) | `~\.claude\skills\financials-validate\scripts\validate.py` |
| Model-write (row consolidation, first-filing-wins, layered checks) | `~\.claude\skills\model-write\scripts\write.py` |
| Generic library (115 entries) | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` |
| PG ledger | `Brain\Knowledge\Model Schema\PG\decisions_ledger.json` |
| PG canonical workbook | `Brain\Knowledge\Model Schema\PG\Model Output\PG_model_v14.xlsx` |
| PG validated JSONs (top-level, canonical) | `Brain\Knowledge\Model Schema\PG\Model Output\validated_*.json` |
| PG intermediates | `Brain\Knowledge\Model Schema\PG\Model Output\.cache\` |

## How to create the next handoff

Write at end of session under `Brain\Sessions\{Task-Theme}\Handoffs\{Month} {Day}{ord} {topic} Session.md`. **Target length: ~800-1200 words; hard ceiling 1500.**

### Required steps

1. **Archive prior handoffs.** Move every `*.md` file currently in the task's `Handoffs\` root into `Handoffs\Archive\`. The root must contain exactly one file when you're done: today's new handoff.
2. **Update `ROADMAP.md`** — bump `last_session` field to point at the new handoff filename.
3. **Write the new handoff** in the `Handoffs\` root using the structure below.

### Structure

1. **YAML frontmatter** — `type`, `date` (absolute YYYY-MM-DD), `topic` (one sentence), `tags`.
2. **Title** matching filename.
3. **One-paragraph intro**: prior handoff reference (now in `Archive\`) + one sentence on what this session did + one sentence on what the next session should do.
4. **Starting state** — 3-5 bullet points.
5. **Work done this session** — numbered `### N.` subsections grouped by subsystem. Why over what — the diff already shows what.
6. **Current state** — bullet list, one line per subsystem. Numbers and status.
7. **Open decisions / pending work** — numbered, 1-2 lines each. Include the active playground-sync rule. Flag unresolved user questions.
8. **Key file paths** — two-column table. Absolute paths. Only load-bearing files.
9. **How to create the next handoff** — paste this section verbatim.

### Consolidation rules

- Don't list every library entry / ledger row added — cite file + count + non-obvious decisions.
- Don't re-explain code. Reference by function/file name.
- Reverted exploration: one line.
- Memory rules referenced not duplicated — say "per `feedback_X.md`".
- Cold-start reader picks this up and can act. No re-asking.
