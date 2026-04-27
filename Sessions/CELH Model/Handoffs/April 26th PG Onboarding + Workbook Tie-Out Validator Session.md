---
type: session-handoff
date: 2026-04-26
topic: Brought PG (14 filings) end-to-end through the new HTM-walker architecture clean (0 novels / 0 fails), introduced a workbook-level tie-out validator in model-write that catches structural mis-routing the data-side BS/IS/CF rules can't see, and hardened the framework with label-only library matching, per-period tax-sign derivation, and a section-mismatch guard that caught a $5.7B liability-routed-to-assets bug. Both CELH and PG now build clean to xlsx.
tags: [session, pg, celh, workbook-tie-out, label-only-matching, tax-sign-per-period, section-filter, deferred-tax-liability]
---

# April 26th — PG Onboarding + Workbook Tie-Out Validator Session

Picks up from `Archive\April 26th HTM Walker Build-Out + 12 Filing Clean Session.md`. That session built the HTM walker and drove CELH to 12-filing clean; this session brought PG (3 10-Ks + 11 10-Qs) end-to-end through the same architecture clean, surfaced and fixed nine framework gaps along the way, added a workbook-level tie-out validator to model-write that compares rendered subtotals against filer-reported values, and resolved two long-standing CELH issues (duplicate NI rows and broken tax sign for loss-year benefits). Next session opens with onboarding a third ticker (PEP or KO) to validate cross-ticker generality of the now-hardened framework.

## Starting state

- CELH 12 filings clean from prior session (0 novels / 0 fails / single 1,182-cell workbook).
- PG 14 filings (3 10-Ks FY2023/24/25 + 11 10-Qs Q1 FY2023 → Q2 FY2026) untouched since pre-HTM-walker rewrite — stale `validated_*_*.json` files (underscore-named) needed clearing.
- ROADMAP listed "PG 14-filing regression on the new HTM-walker" as Active §17.

## Work done this session

### 1. Library lookup: HTM-label-only matching
Per user directive ("scrap the gaap concept I think — looks like it's throwing things off"). Removed the concept-name fallback path (3) from `match_raw_item` and the threshold-lowering when concept is present. Lookup now matches `raw_filing_label` against canonical aliases ONLY. Saved `feedback_label_only_matching.md`.

### 2. CLUTTER_RE tightening + trailing-paren strip
Original CLUTTER_RE clobbered library aliases like `'preferred stock par or stated value per share'` mid-string when I added `stated\s+value` clutter handling. Tightened to require `[,;]\s*` trigger before clutter keywords + allow whitespace between `$` and digits (CELH writes `$ 0.001 par value`). New `TRAILING_PAREN_RE` strips trailing parenthetical metadata like PG's `Treasury stock (shares held: 2023 - 1,647.1 ; 2022 - ...)`.

### 3. Section filter applied uniformly in `select_entry`
PG's `DEFERRED INCOME TAXES` (NC liability) was routing to the asset-side `Deferred Tax Assets` canonical because select_entry's single-candidate fallback bypassed the section filter. Now: when `item.section` is concrete and conflicts with `filing_section`, candidate is rejected. Skipped only when `item.section` is None or "unclassified" (lets walker-couldn't-classify items inherit the canonical's hint). Added DTL alias `deferred income taxes` to GEN-BS-025 so PG routes correctly.

### 4. Walker subtotal-row library lookup, strict-mode (exact-match only)
Walker now does library lookups for subtotal rows but constrained: subtotal canonicals (e.g. CFO `Net cash provided by operating activities`) keep row_type=subtotal; line-item canonicals promote subtotal→line_item (PG's `Total inventories` rollup IS the BS Inventories line). Fuzzy matches blocked via new `strict=True` parameter — prevents `Total current liabilities` mis-promoting to `Other Current Liabilities` at 88% fuzzy.

### 5. Walker stmt-type-scoped section classifier
PG's CF concept `IncomeTaxesPaid` was getting `Section.TAX` from the IS-side regex. Split `_SECTION_BY_CONCEPT_FRAGMENT` into BS/CF/IS lists; `classify_section(local_name, stmt_type)` only consults the relevant list.

### 6. CF section transitions + GEN-CF-035 row_type
`TOTAL FINANCING ACTIVITIES` added to walker subtotal-transition patterns (PG-style header). `GEN-CF-035 Net Change in Cash` set to `row_type=subtotal` + `filing_section=cash_other` so the walker's subtotal-row library lookup keeps it tagged correctly. Validate's `partition_cash_flow` excludes Net Change in Cash from section bucketing (it's a bottom-line reconciliation row, not a section subtotal).

### 7. Reconcile path-1 gated on `canonical_label is None`
PG's `TOTAL OPERATING ACTIVITIES` was routing to `_subtotal` pseudo-bucket because path-1 (subtotal heuristic) fired before path-3 (canonical lookup). Gating on `canonical_label is None` lets canonical-matched subtotals flow through to their proper sheet (CASH FLOW), where model-write's section subtotal logic anchors them.

### 8. Walker `subsection_context` for EPS/shares + date-only label fallback
Per-share concepts → `eps`; share-count concepts → `shares_outstanding`. Resolves the `Basic`/`Diluted` alias collision between GEN-IS-016/017 and GEN-IS-018/019. New `_DATE_ONLY_LABEL_RE` triggers concept-derived label fallback for PG's quarterly BS rows that label only `June 2025` while carrying CommonStockValue.

### 9. Workbook tie-out validator (model-write)
New `_collect_filer_subtotals()` + `_collect_filer_mezzanine_sums()` + `validate_workbook_ties()` in `write.py`. After build, compares each section sum (workbook line-item rows) against the filer's reported subtotal for that period. Folds mezzanine into equity for TSE comparison (per `feedback_convertible_preferred_to_equity.md`). Skips subtotal-canonical rows (CFO/CFI/CFF/Net Change in Cash) so they don't double-count in section sums. Snapshots `row_map` + `row_section` BEFORE the per-sheet loop's `insert_bs_subtotal_slots` mutation. Tolerance widened to $5 to absorb cross-filing rounding. Caught the DTL→assets routing bug at first run.

### 10. CELH duplicate NI row + per-period tax-sign correction
Per user feedback: CELH workbook showed two NI rows (`Net Income (Loss)` + `Net Income (Loss) Less NCI`) and tax displayed as expense in loss-year benefit periods. Fixes: (a) Moved bare-NI aliases (`net income (loss)`, `net income`, `net loss`, `net income loss`) from GEN-IS-011 to GEN-IS-022 — single-NI filers route to consolidated Net Income canonical, NCI filers (PG) keep both via specific aliases. (b) New `correct_tax_signs()` post-walker pass in `extract.py`: for each IS Statement, if NI > PT (benefit period), flips tax `sign_convention` to "positive" via `model_copy` (RawLineItem frozen). PG unaffected (always profit, NI < PT). CELH 2021 tax now renders +$7,996 as expected. Validate's IS-4 / IS-5 also tolerate either tax sign formulation as a backup.

### 11. Library updates (~40 alias additions, 1 new canonical, key rule changes)
- New: `GEN-CF-057 Proceeds from Sale of Short-Term Investments` (investing).
- `GEN-IS-024 sign_convention=negative` + `"charge"` added to `_NEGATIVE_KEYWORDS` (PG's "Indefinite-lived intangible asset impairment charge" now renders negative).
- `GEN-CF-022/-026/-033` aliased with `total operating/investing/financing activities`.
- Hyphen-suffix aliases added across BS/CF for CELH-style labels (`brands-net`, `customer relationships-net`, `deferred revenue-current`, lease-non-current, etc.).
- Total inventories alias on GEN-BS-005 to handle PG's inventory rollup pattern.
- Library: 122 → 124 entries.

## Current state

- **CELH 12 filings**: 0 novels / 0 validate fails / 0 workbook tie-out errors. `CELH_model_v5.xlsx` 1,197 cells.
- **PG 14 filings**: 0 novels / 0 validate fails / 0 workbook tie-out errors. `PG_model_v5.xlsx` 1,178 cells.
- **Validators**: BS-1..5 + IS-1..5 + CF-1..4 (14 data-side) + workbook tie-out (BS section sums + Total Assets/Total Liabilities cumulative + CF section subtotals). IS-4/IS-5 tolerate either tax sign.
- **Library**: 124 entries, ~40 aliases added across CELH+PG hardening.
- **Memory**: 4 new feedback rules saved (`label_only_matching`, `charge_means_expense`, `celh_pg_joint_regression`, `tax_sign_per_period`).

## Open decisions / pending work

1. **NEXT SESSION OPENS WITH: onboard a third ticker (PEP or KO).** Validate cross-ticker generality of the hardened framework. Workflow: mkdir ticker root, drop config.json, run extract → reconcile → validate → model-write, triage novels per protocol.
2. **Refresh playgrounds + LS_KEY v9 → v10** — `playground_architecture.html` needs to reflect: HTM-only walker, label-only matching, workbook tie-out validator, per-period tax-sign correction. Carried per active propagating rule.
3. **`financials-validate/SKILL.md` description stale** — still says "10 filer-tie rules". Update to "14 rules + IS cascade + tax-sign tolerance."
4. **`_pre.xml` linkbase removal cleanup pass** in `ixbrl_path.py` — code keeps it dormant; do a delete-pass.
5. **OCI 4th-statement build** — walker still STOPS on OCI header. Carried.
6. **Extend `model-calc` to quarterly drivers.** Currently annual-only.
7. **Extract `pattern_libraries/generic_forecast_rules.json`** from `calc.py`. Blocked on §6.
8. **Formalize ticker onboarding doc** at `Brain\Knowledge\Model Schema\05_ticker_onboarding.md`.

## Key file paths

| Purpose | Path |
|---|---|
| This handoff | `Brain\Sessions\CELH Model\Handoffs\April 26th PG Onboarding + Workbook Tie-Out Validator Session.md` |
| Prior handoffs | `Brain\Sessions\CELH Model\Handoffs\Archive\` |
| Roadmap | `Brain\Sessions\CELH Model\ROADMAP.md` |
| Lookup module (label-only + section filter) | `Brain\Knowledge\Model Schema\financials-schema\financials_schema\lookup.py` |
| Walker (subsection_ctx + date-only fallback + strict subtotal lookup) | `~\.claude\skills\financials-extract\scripts\ixbrl_path.py` |
| Extract dispatcher (correct_tax_signs post-pass) | `~\.claude\skills\financials-extract\scripts\extract.py` |
| Reconcile (path-1 gated on canonical_label) | `~\.claude\skills\financials-reconcile\scripts\reconcile.py` |
| Validate (IS-4/IS-5 try-both-tax-signs, CF NetChange exclusion) | `~\.claude\skills\financials-validate\scripts\validate.py` |
| Model-write (workbook tie-out validator) | `~\.claude\skills\model-write\scripts\write.py` |
| Generic library (124 entries) | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` |
| **CELH built workbook** | `Brain\Knowledge\Model Schema\CELH\Model Output\CELH_model_v5.xlsx` |
| **PG built workbook** | `Brain\Knowledge\Model Schema\PG\Model Output\PG_model_v5.xlsx` |
| Playground (needs LS_KEY v9 → v10 update) | `Brain\Knowledge\Model Schema\playground_architecture.html` |

## How to create the next handoff

Write at end of session under `Brain\Sessions\{Task-Theme}\Handoffs\{Month} {Day}{ord} {topic} Session.md`. **Target: ~800–1200 words; hard ceiling 1500.**

### Required steps

1. **Archive prior handoffs.** Move every `*.md` file in the task's `Handoffs\` root into `Handoffs\Archive\`. The root must contain exactly one file when you're done: today's new handoff.
2. **Update `ROADMAP.md`** — bump `last_session` field to point at the new handoff filename.
3. **Write the new handoff** in the `Handoffs\` root using the structure below.

### Structure

1. **YAML frontmatter** — `type`, `date` (absolute YYYY-MM-DD), `topic` (one sentence), `tags`.
2. **Title** matching filename.
3. **One-paragraph intro** — prior handoff reference (now in `Archive\`) + one sentence on what this session did + one sentence on what the next session should do.
4. **Starting state** — 3–5 bullet points.
5. **Work done this session** — numbered `### N.` subsections grouped by subsystem. Why over what.
6. **Current state** — bullet list, one line per subsystem. Numbers and status.
7. **Open decisions / pending work** — numbered, 1–2 lines each. Include the active playground-sync rule. Flag unresolved user questions and **explicitly highlight any fix that should open the next session.**
8. **Key file paths** — two-column table. Absolute paths. Only load-bearing files.
9. **How to create the next handoff** — paste this section verbatim.

### Consolidation rules

- Don't list every library entry / ledger row added — cite file + count + non-obvious decisions.
- Don't re-explain code. Reference by function/file name.
- Reverted exploration: one line.
- Memory rules referenced not duplicated — say "per `feedback_X.md`".
- Cold-start reader picks this up and can act. No re-asking.
