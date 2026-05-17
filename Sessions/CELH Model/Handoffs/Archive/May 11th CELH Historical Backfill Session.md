---
type: session-handoff
date: 2026-05-11
topic: Extended CELH pipeline backwards to cover 2021-Q2 through 2022-Q3 historical filings; surfaced two framework gaps (accepted_sections plumbing + GEN-IS-026 row_type) and two structural extraction obstacles (CELH iXBRL boundary at Q2 2021; find_primary_tables title-detection failure on 2021-FY/2022-FY 10-Ks); shipped 5 new validated filings + workbook rebuilt with FY2021–FY2025 historicals + 6-year forecast; FY2021/FY2022 10-Ks deferred.
tags: [session, celh-backfill, ixbrl-classification, accepted-sections-fix, subtotal-row-type, fixup-extraction, framework-regression-pending]
---

# May 11th — CELH Historical Backfill Session

Prior session: `Archive\May 9th MDA Rework Architecture Session.md` (MDA rewrite phases 0-1). This session pivoted to financial-statements framework: user requested extending the CELH pipeline back to FY 2019 to align with the transcript archive just organized under `Brain\Sources\CELH\`. Scope contracted twice (pre-iXBRL block, then 10-K extraction artifacts), ending with 5 new validated quarterlies shipped + 2 framework patches + a working FY2021–FY2030 workbook. **Next session opens with two pending items:** (1) joint-regression sweep on CELH+PG+PEP+MNST to confirm the two framework changes don't break the harness baseline, and (2) decision on whether to revisit the 2021-FY/2022-FY 10-K extraction or accept the comparative-column annual coverage already present in the workbook.

## Starting state

- 12 CELH filings validated (2023-Q1 → 2025-FY), `CELH_model.xlsx` covered FY2023-FY2025 annual + Q1 2023-Q3 2025 quarterly.
- `Brain\Sources\CELH\` had transcripts for 2018-Q3 onward (unzipped + sorted into `{period}\transcripts\` earlier in session) but NO SEC source filings for 2019-2022.
- User's stated goal: extend financials framework backward to FY 2019 to line up with transcript coverage.

## Work done this session

### 1. Transcript zip unpack + sort (separate task, completed first)

68 PDFs from `CELH.zip` distributed into per-period `transcripts\` subfolders under `Brain\Sources\CELH\`. Renamed `2026-Q4` → `2026-Q1` (treated as typo per user). Earnings PDFs went to the reported period; conferences/M&A/shareholder meetings binned by most-recent-reported-quarter rule. 17 new period folders created for 2018-2022.

### 2. SEC EDGAR fetch — 17 filings landed

`sec-edgar-fetch` skill pulled 13 in-scope + 4 extras (2025-Q2/Q3/FY HTM source-of-truth + new 2026-Q1 10-Q). HTM landing path: `Brain\Sources\CELH\{period}\filings\`. The 4 extras' `Financial_Report.xlsx` were not yet SEC-generated; HTM alone suffices per `feedback_no_rfiles_for_financials.md`.

### 3. Scope contraction #1: pre-iXBRL filings deferred

Pre-mandate filings (FY2019, all 2020 quarterlies + FY, 2021-Q1) have zero `<ix:>` tags — CELH was non-accelerated through fiscal 2020, so iXBRL kicked in at Q2 2021. Six filings deferred. **Recovery path is structural** (presentation linkbase XMLs exist in archive — `celh-{YYYYMMDD}_pre.xml`, etc.) but requires a new extractor path that reads XBRL XML instance + linkbases instead of inline iXBRL HTM. Out of scope this session; could be a focused next-session build.

### 4. Standard iXBRL path — 5 quarterlies clean

`financials-extract` produced clean RawFilings for 2021-Q2, 2021-Q3, 2022-Q1, 2022-Q2, 2022-Q3 (6-8 statements each, 141-199 items).

### 5. 10-K extraction failure + monkey-patched fixup (2021-FY, 2022-FY)

`find_primary_tables` in `ixbrl_path.py` walks HTM text for `_PRIMARY_TITLE_RE` matches. CELH's 2021/2022 10-K formatting embeds primary titles in long TOC paragraphs (>150 chars) or as adjoining tables without standalone title elements — only the IS title fired, and the BS comparative columns ended up classified as CF. Documented in `_fixup_fy_extracts.py` under `.cache\`: fetches `celh-{YYYYMMDD}_pre.xml` from the archive, builds `concept → BS/IS/CF` from presentation-link roles (skips `*Details*` / `*Tables*` / `*Disclosure*` / `*Parenthetical*`), and monkey-patches `find_primary_tables` with a concept-membership classifier. Required three post-filters: (a) drop duration BS (SE rollforward bleed), (b) drop sub-48wk IS in 10-Ks (quarterly-reference noise), (c) cross-section duplicate filter where same canonical_label appears in multiple sections (Note Receivable-current showing up in both current_assets and current_liabilities). Final shape: 2 BS + 2-3 IS + 2-3 CF. **The 10-Ks reconcile clean but fail BS/IS/CF tie-out validation by significant gaps — fixup is good enough for SUM(filings)>=anchor checks to nearly pass, not for accounting-identity validation.**

### 6. Framework gap #1: `accepted_sections` was declared but never used

`LibraryEntry.accepted_sections` field exists in `financials_schema/lookup.py:219` and is documented in `feedback_accepted_sections_optin.md`, but `select_entry` (line ~410) filtered candidates only by `filing_section == item_section`. `_entry_canonical` (line ~282) also didn't project `accepted_sections` into the index. Result: `Cash Paid for Interest` (filing_section=operating, accepted_sections=[cash_other]) failed to match `Interest`-labeled items in 2021/2022 quarterlies because the walker tagged them `cash_other`. Two-line fix: project the field in `_entry_canonical` + include it in `select_entry`'s section filter. CELH 2023+ wasn't affected because the walker section logic placed the items in `operating` for those filings; older filings used a different filer layout that the walker rendered as `cash_other`.

### 7. Framework gap #2: `GEN-IS-026 Operating Expenses` had no `row_type`

CELH 2021-2022 filings render a "Total operating expenses" subtotal between S&M/G&A and Income from operations. The canonical had aliases `["operating expenses", "total operating expenses"]` but `row_type=None`, so the IS-2 validator summed S&M + G&A + Total OpEx → double-counted. Set `row_type=subtotal`. Re-validate of all 12 existing filings still passes (they don't render the line).

### 8. Novel triage — 16 aliases + 2 new generic canonicals + 8 CELH ticker rows

Batch dispositions decided with user. Generic library: 16 new aliases on existing canonicals (deferred-tax variants, capital-raise, bond-interest, security-deposits, deposits-and-OCL, preferred-dividend deduction) + 2 new canonicals (`GEN-CF-082 Goodwill Impairment`, `GEN-IS-031 Gain (Loss) on Lease Cancellations`). CELH ledger: 8 new_rows (China gain, Bonds payable payments, Section 16(b) recovery, Accrued Freight, Due to Pepsi, State Beverage Deposit, Unbilled Purchases, VAT Payable). Skipped: 14 disclosure-noise patterns (lease maturity buckets, Foreign/Domestic tax split, EPS reconciliation rows, SE rollforward beginning balances) — handled via regex post-filter in `_fixup_fy_extracts.py`.

### 9. End-to-end pipeline run

5 new + 12 existing = 17 validated_*.json under `Financial Statements\`. `model-write` consumed all 17 → workbook with historical FY2021-FY2025 + 6-year forecast columns. FY2021/FY2022 annual columns populated entirely from comparative columns in existing 10-Ks (2023-FY 10-K reports FY2022 + FY2021, 2024-FY 10-K extends to FY2022). `model-calc` layered 115 inferred quarterly forecast specs over Q1 2026E-Q4 2030E (20 forecast quarters, 2000 cells).

## Current state

- **Validated filings (CELH):** 17 (was 12). 2021-Q2 → 2025-FY contiguous quarterly; FY2021 → FY2025 annual columns (FY2021/FY2022 via comparative columns, not direct 10-K extracts).
- **Workbook:** `Model Outputs\CELH\CELH_model.xlsx` — 1561 cells in initial write + 2000 forecast cells; 6 sheets (ANNL P&L/BS/CF + QTR P&L/BS/CF).
- **Generic library:** 161 → 163 canonicals (+ Goodwill Impairment, Gain (Loss) on Lease Cancellations); ~16 aliases added; `GEN-IS-026` flagged `row_type=subtotal`.
- **CELH ledger:** 15 → 23 new_rows; 6 mappings unchanged.
- **Framework code:** `financials_schema/lookup.py` patched for `accepted_sections` (2 lines).
- **Harness baseline:** not yet re-locked. 87-filing CELH+PG+PEP+MNST regression PENDING.

## Open decisions / pending work

1. **Joint regression sweep PENDING.** Two framework changes (`lookup.py` + `GEN-IS-026 row_type`) need CELH+PG+PEP+MNST validation per `feedback_celh_pg_joint_regression.md`. CELH 12-filing baseline re-validated clean this session; PG (14) + PEP (13) + MNST (20) not yet re-run.
2. **2021-FY / 2022-FY 10-Ks: extraction artifacts persist** despite fixup. BS/IS/CF tie-out validations fail (gaps in $100Ks-$M range). FY2021/FY2022 annual columns in workbook are populated from existing 10-Ks' comparative columns instead — adequate for the model. Decision: accept comparative-column coverage or invest in a proper `find_primary_tables` rewrite (concept-membership-based, would replace the monkey-patched fixup). **If revisited, the fixup script at `.cache\_fixup_fy_extracts.py` is the prototype.**
3. **Pre-iXBRL backfill (FY2019, 2020 quarterlies+FY, 2021-Q1) deferred.** Recovery path requires extending `financials-extract` to read XBRL instance XML + presentation linkbase from the SEC archive — principled (structural signals only) but a meaningful framework expansion. Out of scope for the workbook the user has now (annual coverage extends to FY2021 already).
4. **Playgrounds-in-sync rule (per `feedback_keep_playgrounds_in_sync.md`):** no structural changes in this session; `playground_architecture.html` + `playground_schema.html` don't need updates.
5. **Memory updates (deferred to user discretion):** could write a `project_celh_ixbrl_boundary.md` capturing that CELH iXBRL starts at 2021-Q2; could write `feedback_total_opex_subtotal.md` capturing the canonical row_type rule. Both small, not urgent.

**Active propagating rules** (carried from prior handoffs): no-heuristic policy (the fixup script's classifier + label-pattern noise filter are heuristic, but contained to `.cache\` and only applied to 2 specific filings — does not extend to library/walker); joint regression on 4 tickers; no validator sign flips; no duplicate anchor subtotals.

## Key file paths

| Purpose | Path |
|---|---|
| This handoff | `Brain\Sessions\CELH Model\Handoffs\May 11th CELH Historical Backfill Session.md` |
| Prior handoff (archived) | `Brain\Sessions\CELH Model\Handoffs\Archive\May 9th MDA Rework Architecture Session.md` |
| Workbook | `Brain\Knowledge\Model Outputs\CELH\CELH_model.xlsx` |
| Validated JSONs (17) | `Brain\Knowledge\Model Schema\Ticker Libraries\CELH\Financial Statements\validated_*.json` |
| Fixup prototype (10-Ks) | `Brain\Knowledge\Model Schema\Ticker Libraries\CELH\Financial Statements\.cache\_fixup_fy_extracts.py` |
| Disposition applier (one-off) | `Brain\Knowledge\Model Schema\Ticker Libraries\CELH\Financial Statements\.cache\_apply_novel_dispositions.py` |
| Framework patch | `Brain\Knowledge\Model Schema\financials-schema\financials_schema\lookup.py` (lines ~282, ~410) |
| Library | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` (`GEN-IS-026` row_type, `GEN-CF-082`, `GEN-IS-031` new) |
| CELH ledger | `Brain\Knowledge\Model Schema\Ticker Libraries\CELH\Financial Statements\decisions_ledger.json` (8 new_rows added) |
| Pre-iXBRL XML reference | SEC archive: `celh-{YYYYMMDD}_pre.xml` / `_cal.xml` / `_lab.xml` / `_def.xml` |
| Memory carried | `feedback_celh_pg_joint_regression.md`, `feedback_structural_over_heuristic.md`, `feedback_accepted_sections_optin.md`, `feedback_no_rfiles_for_financials.md` |

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
