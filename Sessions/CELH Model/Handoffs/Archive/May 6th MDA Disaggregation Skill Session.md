---
type: session-handoff
date: 2026-05-06
topic: New analytical skill `mda-disaggregation` shipped — extracts MD&A disclosures from a ticker's 10-Q + 10-K filings and emits a standalone `{TICKER}_MDA.xlsx` with 8 sections (geography, customer concentration, product concentration, brand contribution, pro forma, SG&A walk, GP + drivers, Other Inc/Exp). First reference instance is CELH (FY2023 → FY2025 incl. Alani Nu + Rockstar acquisitions). Handoff reconstructed 2026-05-09 from on-disk artifacts — original session ended without a written handoff.
tags: [session, recovery-handoff, mda-disaggregation-skill, celh-mda-data, q4-derivation, sga-walk-taxonomy, brand-contribution]
---

# May 6th — MDA Disaggregation Skill Session

**Recovery handoff** — reconstructed 2026-05-09 from filesystem state. Picks up from `Archive\April 30th Harness + Skills Reorg + Depreciation Skill Session.md`. The April 30 session shipped phase 1 of `depreciation-amortization-impairment-projections`; this session pivoted to a new analytical layer — MD&A narrative disaggregation — and built the `mda-disaggregation` skill end-to-end with CELH as the reference instance. No live session record was written, so this handoff captures what is observable on disk only. Next session opens with the user's choice between resuming the depreciation skill drift cleanup (April 30 unfinished) or extending MD&A disaggregation to a second ticker.

## Starting state

- 5-ticker harness baseline (CELH 12 + PG 14 + PEP 13 + MNST 20 + GOOG 28 = 87 filings) clean against 161-entry generic library, post-BS-001/002 cash consolidation.
- All 10 financials skills at project-local scope (`Brain\Knowledge\Model Schema\.claude\skills\`).
- `depreciation-amortization-impairment-projections` phase 1 shipped: hybrid validated_*.json + companyfacts.json input; per-ticker `asset_depreciation.json`; R-file reconcile at 91% (455 OK / 30 DRIFT / 17 MISSING). Phase 2/3/4 + ~30 reconcile-drift cleanups deferred.
- Canonical catalog (`canonical_catalog.md`) at ~70 of 161 rows annotated.

## Work done this session

### 1. New skill `mda-disaggregation` (analytical layer, CELH reference instance)

New skill at `Brain\Knowledge\Model Schema\.claude\skills\mda-disaggregation\`. Purpose: lift the qualitative + quantitative disclosures buried inside MD&A narrative into a clean, source-cited analyst workbook — separate from the formal three-statement model. Output is **standalone** `{TICKER}_MDA.xlsx`, never a sheet inside the model workbook (openpyxl renumbers external-link rIds on save and corrupts files with cross-workbook references — learned the hard way).

Skill files:

| File | Role |
|---|---|
| `SKILL.md` | 8-section spec + 9 critical engineering rules + workflow + grep anchor terms for narrative extraction |
| `data/schema.md` | JSON shape — periods, ytd_periods, source-cited tuples `[value, "src note"]`, canonical SG&A driver-bucket keys |
| `scripts/build_mda_workbook.py` | Generic builder — reads `data/{TICKER}.json`, emits xlsx. Periods as columns, metrics as rows, Q4 derived as `=FY-Q1-Q2-Q3` for $ values |
| `data/CELH.json` | First reference instance, 15 periods (Q1 2023 → FY2025) |

### 2. Eight workbook sections — what's in `{TICKER}_MDA.xlsx`

Single sheet `MD&A`, 12-15 period columns (Q1/Q2/Q3/Q4/FY for each year), source citations as cell notes (Shift+F2 style):

1. **Geography** — Revenue $thousands by region, single-period; Q4 derived by formula.
2. **Customer concentration** — % of revenue, only customers >10% disclosed; Q4 = `n/d` (percentages don't subtract).
3. **Functional / product concentration** — % of revenue (e.g., CELH "functional energy drink product" share); Q4 = `n/d`.
4. **Brand contribution** — $thousands by acquired brand + residual (legacy), post-acquisition periods only. Acquired-brand Q4 = formula; residual = `Total Revenue - Σ acquired`.
5. **Pro Forma vs As-Reported** — ASC 805 mandatory disclosure when material acquisition closes. As-reported / pro-forma / implied "missing" / pro-forma YoY %.
6. **SG&A walk** — $ Δ rows (period-over-period change), hierarchical M&S vs G&A subtotals. Sub-row Q4 derived from FY-9M YTD where both walks disclose the bucket; otherwise blank.
7. **Gross Profit + margin + qualitative drivers** — GP$ formula, margin = GP$/Revenue link to Section 1, YoY pts Δ, plus 7 qualitative `+`/`-` driver columns (raw/promo/freight/mix/brand/inv/tariffs) with verbatim quote in cell note.
8. **Other Inc/Exp walk** — interest income/expense, FX, transition agency income, other.

### 3. Critical engineering rules (encoded in SKILL.md, all earned the hard way)

- **Standalone workbook only** — never a sheet inside a workbook with external links (openpyxl rId renumbering corrupts the file on save).
- **Default Comment dimensions only** — setting `comment.width`/`comment.height` triggers Excel's "we found a problem" repair warning.
- **No merged cells.**
- **Q4 derivation for $ values only** — `n/d` with cell note for percentages.
- **GP margin Q4** = `GP$_Q4 / Revenue$_Q4`, NOT `FY% - 9M%` (would compound rounding error).
- **MD&A narrative values are rounded to $0.1M** ($100K precision); validated_*.json holds exact line values if user wants dollar precision later.

### 4. SG&A walk taxonomy — driver-bucket keys

Canonical keys live in `schema.md` and the builder script:
- **M&S:** `mkt_invest`, `storage`, `employee_ms`, `<acq_brand>_ms`, `other_selling`
- **G&A:** `admin`, `acq_integ`, `<acq_brand>_ga`, `contingent`, `legal_accrual`, `stock_comp`, `other_admin`
- **Special:** `distrib_term` (in-SG&A era; post-2025 CELH split it to a separate IS line — tracked in `distributor_term_separate`)

The builder dynamically inserts acquired-brand sub-rows (e.g. `alani_ms`, `alani_ga`, `rockstar_ms`) when keys ending in `_ms`/`_ga` appear in any period. Pre-acquisition / pre-2025-disclosure-shift periods that report a flat list (Marketing/Storage/Employee/Admin/Stock comp) map to the closest M&S vs G&A bucket — a `taxonomy_notes` field documents the per-ticker mapping decisions.

### 5. CELH reference instance — `data/CELH.json`

15 periods (Q1 2023 → FY2025) populated:
- Geography: NA / Europe / APAC / Other across all periods (some Q1-Q3 2023 backfilled from comparable columns of the 2024 10-Q since the original 2023 10-Q didn't disclose disaggregation).
- Brand contribution: Alani Nu (closed April 1, 2025) and Rockstar (closed Aug 28, 2025) populated for active periods Q2 2025+; Celsius residual = Total − Alani − Rockstar.
- Pro forma: Q3 2024/2025, 9M 2024/2025, FY 2024/2025 from the FY2025 10-K Note 5.
- SG&A walk: full quarterly + 9M YTD walks 2023-2025; `distributor_term_separate` populated for Q3 2025+ (post-relocation era).
- GP qualitative drivers: every quarter has the verbatim narrative quote attached.
- Other Inc/Exp: FY2025 full walk (interest income/expense, Rockstar agency income, FX/other).

Output workbook: `Brain\Knowledge\Model Outputs\CELH\CELH_MDA.xlsx` (22 KB, generated 2026-05-06).

### 6. Workflow encoded in SKILL.md

Steps for adding a new ticker: identify filings under `Brain\Sources\{TICKER}\{YYYY-Qn}\filings\*.htm`; grep MD&A regions + Note 4 (Revenue) + Note 5 (Acquisitions) + Concentrations of Risk + Item 9A — anchor terms documented in SKILL.md (e.g., `"Revenue from customers accounting for more than"`, `"contributed approximately"`, `"[Pp]ro forma" + "Revenue $"`); populate `data/{TICKER}.json`; run `python scripts/build_mda_workbook.py --ticker {TICKER}`.

## Current state

- **New skill:** `mda-disaggregation` shipped at project-local scope. CELH reference instance complete (15 periods). Output workbook at `Model Outputs\CELH\CELH_MDA.xlsx`.
- **Skill count:** 11 financials skills at project-local scope (was 10; new analytical skill added alongside `depreciation-amortization-impairment-projections`).
- **Library / harness / depreciation skill:** unchanged from April 30 baseline. 161 entries; 87-filing 5-ticker harness still clean; phase 1 of depreciation skill still at 91% R-file reconcile match.
- **Memory:** no new entries this session.

## Open decisions / pending work

1. **Open with user choice of two parallel threads:**
   - **(a) Resume April 30 plan** — finish ~30 reconcile drifts in `depreciation-amortization-impairment-projections` (per `project_rfile_label_variants.md`), then phases 2/3/4.
   - **(b) Extend MDA skill to a second ticker** — natural candidates are PEP or MNST (broader segment disclosure), or PG (multi-segment June fiscal year). PG/PEP would test the SG&A taxonomy on a non-CELH disclosure structure.
2. **MD&A skill refinements pending observation across more tickers:** the SG&A bucket taxonomy was tuned to CELH. Adding a multi-segment filer (PEP) may expose missing buckets — `taxonomy_notes` is the documented escape hatch but may motivate canonical-key extensions.
3. **Cell-note source citations are free-form strings.** No structured filing/section/page schema yet. Acceptable for v1; revisit if cross-ticker analytics over notes is ever needed.
4. **Catalog annotation continues** — ~70 of 161 rows done as of April 30 (input for the deferred driver-kind structural-metadata sprint that replaces `_label_contains` heuristics in `inference.py`).
5. **`cf_delta_target` extension on BS canonicals** — declare for AR / Inv / Prepaid / AP / Other CA so `inference.py` doesn't runtime-match BS↔CF working-capital pairs by label (no-heuristic policy).
6. **Active propagating rules** (carried verbatim from April 30): playground sync, no-heuristic policy, no validator sign flips, no duplicate anchor subtotals, **joint regression on 5 tickers** (CELH+PG+PEP+MNST+GOOG = 87 filings).
7. **Working directory awareness** — financials skills only visible when claude code launches from `Brain\Knowledge\Model Schema\`.
8. **Recovery-handoff caveat:** this handoff was reconstructed from on-disk artifacts on 2026-05-09. Anything not visible in source files (decisions discussed but not committed, partial drafts, rejected approaches) is lost. If the user remembers anything that should be captured, add a memory entry rather than retroactively editing this handoff.

## Key file paths

| Purpose | Path |
|---|---|
| This handoff (recovery) | `Brain\Sessions\CELH Model\Handoffs\May 6th MDA Disaggregation Skill Session.md` |
| Prior handoff (archived) | `Brain\Sessions\CELH Model\Handoffs\Archive\April 30th Harness + Skills Reorg + Depreciation Skill Session.md` |
| Roadmap | `Brain\Sessions\CELH Model\ROADMAP.md` |
| New skill | `Brain\Knowledge\Model Schema\.claude\skills\mda-disaggregation\` (`SKILL.md`, `scripts\build_mda_workbook.py`, `data\schema.md`, `data\CELH.json`) |
| MDA workbook output | `Brain\Knowledge\Model Outputs\CELH\CELH_MDA.xlsx` |
| Library (unchanged, 161 entries) | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` |
| Snapshot harness | `Brain\Knowledge\Model Schema\_regression\run.py`; goldens at `_regression\goldens\{TICKER}\` |

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
