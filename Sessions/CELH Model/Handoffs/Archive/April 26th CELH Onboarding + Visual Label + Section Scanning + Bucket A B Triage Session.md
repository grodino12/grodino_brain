---
type: session-handoff
date: 2026-04-26
topic: CELH 3-year onboarding (3 10-Ks + 9 10-Qs); 9 framework fixes spanning library lookup, iXBRL visual-label authority, presentation-linkbase + R-file section walkers, supplemental-noncash detection, ticker-ledger dual schema, normalize_label regex bug; Bucket A + Bucket B novel triage applied; identified dimensioned-only-concept synthesis as the next-session opening task.
tags: [session, celh, ixbrl-extractor, visual-labels, section-scanning, novel-triage, generic-library, ticker-ledger]
---

# April 26th — CELH Onboarding + Visual Label + Section Scanning + Bucket A/B Triage Session

Picks up from `Archive\April 25th PG Cross-Year Backfill + Sign Authority + Subtotal Consolidation Session.md`. That session shipped PG end-to-end across 14 filings with 0 novels / 0 FAILs and put per-period dedup in place. This session onboarded CELH (3 years × 12 filings = 3 10-Ks + 9 10-Qs), surfaced 9 framework gaps that would block any consumer-staples ticker, fixed every one, and triaged Buckets A + B of CELH novels. Result: **0 novels across all 12 CELH filings**, but validation still partially failing on the 2025-FY (Alani Nu acquisition year) due to a dimensioned-only-concept extraction gap. **Next session opens with the proper fix for that gap (Option 2 below).**

## Starting state

- PG: 14 filings clean, `PG_model_v14.xlsx` canonical. Per-period dedup architecture done.
- Library: 115 entries. 10 filer-tie validators. Variant collapse + paren-of-value sign authority shipped.
- CELH: existing CELH ledger (6 mappings + 2 new_rows from old PDF era), `CELH_model.xlsx` from FY2023+FY2024 PDF runs.
- Outstanding: multi-ticker validation pending. Generic library hadn't been stress-tested on a non-PG ticker.

## Work done this session

### 1. PG: cross-filing CF tie-out tier + per-period dedup
`write.py:check_cf_section_subtotals` now returns `(warnings, errors)`. `CF_TIE_OUT_WARN_MIN = $2M` (silent below), `CF_TIE_OUT_ERROR_MIN = $4M` (raise above). User flagged a $21M cross-filing gap on PG QTR CF 2024-03-31 Investing as not-acceptable. Root cause: per-row dedup picked PG's hybrid concept (`PaymentsForProceedsFromBusinessesAndOtherInvestingActivities`) from 2024-Q3 AND the pure concept (`PaymentsToAcquireBusinessesNetOfCashAcquired`) from 2025-Q3 comparative — same economic item double-counted across two rows. Fix: `aggregate_cell_totals` now does **per-(sheet, period) first-filing-wins** instead of per-row. Entire row set comes from the oldest filing reporting that period; never mixes rows. Eliminates the concept-rename double-count class of bug. `PG_model_v15.xlsx` confirms — Investing subtotal at 2024-03-31 ties to filer's reported -$2,986M exactly.

### 2. CELH SEC pull
`sec-edgar-fetch --ticker CELH --forms 10-K,10-Q --since 2023-01-01 --limit 15` pulled 12 filings under `Brain\Sources\CELH\{2023-Q1..2025-FY}\`. Required `pip install pymupdf` (was missing for PDF path's load-time imports).

### 3. Library lookup — alias-dedup at index-build
`lookup.build_generic_index`: when multiple aliases on the same entry normalize to the same string (e.g. `'net income (loss)'` and `'net income loss'` both → `'net income loss'`), don't register the entry twice. Fixed first-novel-found bug where `Net Income Loss` on CF surfaced as novel despite a 1.00 fuzzy match — duplicate registration forced `select_entry` into multi-candidate branch, which rejected on section mismatch.

### 4. iXBRL visual labels — sole authority, all namespaces
`ixbrl_path.extract_anchors_from_report` parses `defref_<ns>_<concept>'…>label</a>` from R-files and emits `{concept: visual_label}` per statement. `build_concept_statement_map` returns a per-(concept, statement_code) label map; the call site picks the visual label keyed by the statement we're emitting into; CamelCase synthesis is fallback only. Works for any namespace (us-gaap, dei, custom celh:/pep:/etc.). New `visual_label_misses` counter in `extraction_metadata` surfaces gaps.

### 5. Presentation-linkbase section walk
`_parse_presentation_linkbase` now also returns a `section_map: {(stmt_type, concept): Section}`. DFS over the linkbase tracks (a) explicit section-abstract subtrees (`LiabilitiesCurrentAbstract` etc., extended to mezzanine + CF activities) AND (b) sibling-level subtotal transitions (after `LiabilitiesCurrent` subtotal, next siblings inherit non-current). The transition propagates UP the call stack via return value so subtotals nested inside `LiabilitiesCurrentAbstract` correctly transition the OUTER sibling list to non-current. Resolves CELH's lease NC items + most other section ambiguities for filers with proper linkbase coverage.

### 6. R-file section-detection fallback
`extract_sections_from_report` walks R-file HTML in document order using `_HEADER_PATTERNS` (Current/Non-Current Assets/Liabilities, Mezzanine/Stockholders' Equity, CF activity blocks) and `_RFILE_SUBTOTAL_TRANSITIONS` (subtotal-driven section advances). State-machine event walk merging `<td>` headers + `defref` anchors. Used as a fallback when linkbase is incomplete (CELH 2023-era filings tag NC concepts in the rendered statement but omit them from `_pre.xml` hierarchy). Cascade: linkbase first → R-file → concept-name heuristic last.

### 7. Supplemental-noncash header reset
`_HEADER_RESET_PATTERNS` resets `current_section` to None on phrases like "Supplemental schedule of noncash investing and financing activities" / "Supplemental disclosures". Without this, items below the financing subtotal inherited the financing state and got wrongly tagged — e.g., $721M of CELH stock issued for Alani Nu would have inflated CFF.

### 8. Ticker-ledger dual schema
`reconcile.build_ticker_index._entry_aliases` accepts both modern `aliases: list[str]` and legacy `filing_term_normalized: str`. Plus `_register` now reads `filing_section` OR `section` (legacy name on new_rows), so the ticker entry's section actually overrides extract-time tagging. Without this, MAP-BS-005 (Deferred Other Costs - Current) had no effect on item.section — extract had stamped it `non_current_liabilities` via fuzzy match to GEN-BS-026 and reconcile's overlay didn't fix it.

### 9. CLUTTER_RE regex bug
`lookup.CLUTTER_RE` had `[\d,]+\s+shares\s+\w+` which accepted a bare comma as the leading digit-or-comma — silently clobbering labels like `"Mezzanine equity, shares outstanding (in shares)"` to just `"mezzanine equity"`. Fix: `\d[\d,]*` requires at least one digit anchor. Three different mezzanine memo concepts (par value, shares outstanding, shares issued) had been collapsing to the same normalized key.

### 10. Library section priority
The library entry's `filing_section` was overriding the iXBRL section_map / R-file section even when the latter was more accurate. Specifically: `GEN-BS-027 Convertible Preferred Stock` hardcoded `equity`, but for CELH the Pepsi conv pref sits under `TemporaryEquityAbstract` (mezzanine). Removed `filing_section` from GEN-BS-027 — filer's iXBRL placement wins. Plus added missing `GEN-CF-035 filing_section: cash_other` so Net Change in Cash doesn't inherit financing state from the R-file walk.

### 11. Bucket A + Bucket B applied
**Library**: 7 alias adds (A1-A4, A8-A10) + 2 new canonicals A5/A6 (`Depreciation` alone + `Amortization` alone, kept separate from combined `Depreciation & Amortization` per "split when filer splits" rule); 4 new generic canonicals B1-B6 (`payments on term loan` alias to GEN-CF-048; `Debt Issuance Fees` GEN-CF-054 with 7 aliases; `Change in Fair Value of Contingent Consideration` GEN-CF-055; `Contingent Consideration - Current` GEN-BS-045). Library: 116 → 119 entries.

**CELH ledger**: 5 Pepsi Mezzanine memo entries (NEW-BS-MZ-PAR/SHO/SHI/RED/DIV consolidating B1-B5 + B13-B20 variants) + 5 Alani Nu / Pepsi pref / Rockstar entries (NEW-CF-PEPSI-WC real investing + NEW-CF-MZ-AC1/AC2/AC3/PFV memos for supplemental noncash disclosures) + filing_section adds to MAP-BS-005 / MAP-BS-012. CELH ledger: 8 → 18 entries.

### 12. Memory rule saved
`feedback_novel_triage_citations.md` — when presenting novels to the user, always cite the **financial statement** + **section/position** + **iXBRL concept name** so the user can navigate the filing directly.

## Current state

- **CELH novels**: 0 across all 12 filings (was 32 unique pre-fixes).
- **CELH validation 2024-Q1**: 10 PASS / 4 WARN / 0 FAIL (was 4 PASS / 4 WARN / 10 FAIL).
- **CELH validation 2025-FY**: still 10 FAIL — `BS-2 gap +$1,391,915` (post-Alani Nu) + CF-3/CF-4 across multiple years. Root cause identified (next section).
- **Library**: 119 entries.
- **CELH ledger**: 6 mappings + 12 new_rows.
- **Generic framework**: visual labels authoritative for any namespace; section context comes from linkbase + R-file walk + library override (in that priority order); per-period dedup eliminates concept-rename double-count; ticker schema dual-supported.
- **PG**: regressions clean — `PG_model_v15.xlsx` builds with no warnings.

## Open decisions / pending work

1. **NEXT SESSION OPENS WITH: dimensioned-only-concept synthesis (Option 2).** CELH 2025-FY BS line `Intangible assets, net (excluding goodwill)` is rendered with concept `us-gaap:IntangibleAssetsNetExcludingGoodwill`, but every fact for that concept in the iXBRL is **dimensioned** by `FiniteLivedIntangibleAssetsByMajorClassAxis` (members: `CustomerRelationshipsMember`, `celh:BrandsMember`). Filer tagged the breakouts but never tagged a non-dimensioned total. Our `has_segments` filter drops dimensioned facts (only `StatementClassOfStockAxis` is whitelisted). Result: $1.5B+ of CELH intangibles silently missing → BS-2 gap. Generalizable — affects any acquirer with category-broken-out intangibles, ROU assets, lease liabilities, or any axis-dimensioned breakout.
   - **Detection**: a concept is "dimensioned-only" when (a) it has a `defref` anchor in some R-file (visually rendered on a primary statement) AND (b) every fact for that concept-period combo has segments (`f.has_segments == True`).
   - **Action**: post-process facts in `ixbrl_path.build_raw_filing` between `parse_facts` and `group_into_statements` — for each (concept, period_end) combo with no default-context fact but ≥1 dimensioned fact, **sum the dimensioned facts and synthesize a default-context IxFact** carrying the total.
   - **Where**: `ixbrl_path.py`. Will need access to `concept_to_codes` / `concept_anchors` set from `build_concept_statement_map` BEFORE the synthesis pass — refactor order if needed.
   - **Risk**: don't double-count concepts that already have a non-dimensioned default fact + dimensioned breakouts (skip those). Consider only "leaf" axis members — multi-axis nesting could over-sum.
   - **Test set**: CELH 2025-FY (Intangibles $1.5B+ should appear), CELH 2025-Q3 (same), CELH 2025-Q2 (Alani Nu pre-acquisition mostly), PG 2026-Q2 (no regression). Validate BS-2 closes the $1.4B gap.
2. **CF-3 / CF-4 across multiple CELH years** — likely related to the same missing items (e.g., Alani Nu acquisition cash outflow on the CF, intangibles-related acquisition adjustments). Re-evaluate after Option 2 lands.
3. **Bucket C still pending** for any items the dimensioned-only fix doesn't catch.
4. **CELH workbook build** — once validation passes across all 12 filings, run `model-write` for the CELH .xlsx.
5. **Playgrounds + LS_KEY → v13** — every fix here (visual labels, section-scanning, R-file fallback, supplemental-noncash, dual-schema, regex fix, library section priority) should be reflected in `playground_architecture.html`. Carry per propagating rule.
6. **OCI 4th statement** (still carried from prior sessions).
7. **`financials-validate/SKILL.md`** — already updated to 10-rule reality (last session); reconfirm after any new validators land.
8. **PG regression** — confirmed PG_model_v15 builds clean; next session: smoke-test the new section-scanning paths against PG too (linkbase has worked for PG; R-file fallback hadn't fired before).

## Key file paths

| Purpose | Path |
|---|---|
| This handoff | `Brain\Sessions\CELH model\Handoffs\April 26th CELH Onboarding + Visual Label + Section Scanning + Bucket A B Triage Session.md` |
| Prior handoffs (rotated) | `Brain\Sessions\CELH model\Handoffs\Archive\` |
| Roadmap | `Brain\Sessions\CELH model\ROADMAP.md` |
| iXBRL extractor (visual labels, section-scan, supplemental-reset) | `~\.claude\skills\financials-extract\scripts\ixbrl_path.py` |
| Lookup module (alias-dedup, CLUTTER_RE fix) | `Brain\Knowledge\Model Schema\financials-schema\financials_schema\lookup.py` |
| Reconcile (ticker dual schema) | `~\.claude\skills\financials-reconcile\scripts\reconcile.py` |
| Model-write (per-period dedup, $4M tier) | `~\.claude\skills\model-write\scripts\write.py` |
| Generic library (119 entries) | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` |
| CELH ledger (18 entries) | `Brain\Knowledge\Model Schema\CELH\decisions_ledger.json` |
| CELH validated outputs (when passing) | `Brain\Knowledge\Model Schema\CELH\Model Output\validated_*.json` |
| CELH intermediates | `Brain\Knowledge\Model Schema\CELH\Model Output\.cache\` |
| CELH source filings | `Brain\Sources\CELH\{2023-Q1..2025-FY}\filings\` |
| PG canonical workbook (v15) | `Brain\Knowledge\Model Schema\PG\Model Output\PG_model_v15.xlsx` |

## How to create the next handoff

Write at end of session under `Brain\Sessions\{Task-Theme}\Handoffs\{Month} {Day}{ord} {topic} Session.md`. **Target: ~800-1200 words; hard ceiling 1500.**

### Required steps

1. **Archive prior handoffs.** Move every `*.md` file in the task's `Handoffs\` root into `Handoffs\Archive\`. The root must contain exactly one file when you're done: today's new handoff.
2. **Update `ROADMAP.md`** — bump `last_session` field to point at the new handoff filename.
3. **Write the new handoff** in the `Handoffs\` root using the structure below.

### Structure

1. **YAML frontmatter** — `type`, `date` (absolute YYYY-MM-DD), `topic` (one sentence), `tags`.
2. **Title** matching filename.
3. **One-paragraph intro** — prior handoff reference (now in `Archive\`) + one sentence on what this session did + one sentence on what the next session should do.
4. **Starting state** — 3-5 bullet points.
5. **Work done this session** — numbered `### N.` subsections grouped by subsystem. Why over what.
6. **Current state** — bullet list, one line per subsystem. Numbers and status.
7. **Open decisions / pending work** — numbered, 1-2 lines each. Include the active playground-sync rule. Flag unresolved user questions and **explicitly highlight any fix that should open the next session.**
8. **Key file paths** — two-column table. Absolute paths. Only load-bearing files.
9. **How to create the next handoff** — paste this section verbatim.

### Consolidation rules

- Don't list every library entry / ledger row added — cite file + count + non-obvious decisions.
- Don't re-explain code. Reference by function/file name.
- Reverted exploration: one line.
- Memory rules referenced not duplicated — say "per `feedback_X.md`".
- Cold-start reader picks this up and can act. No re-asking.
