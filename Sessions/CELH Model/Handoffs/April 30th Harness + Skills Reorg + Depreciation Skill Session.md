---
type: session-handoff
date: 2026-04-30
topic: Harness parallelized + cached; 5-ticker baseline (87 filings) including GOOG; BS-001/002 cash consolidation; YTD sheets hidden; all 10 financials skills moved to project-local scope (`Brain/Knowledge/Model Schema/.claude/skills/`); new analytical-layer skill `depreciation-amortization-impairment-projections` shipped at phase 1 (extractor + R-file reconcile, hybrid validated_*.json + companyfacts.json input, 91% reconcile match across 502 checks); canonical catalog generated + ~70 rows annotated; 4 framework bugs caught + fixed via reconcile cross-check; per-ticker R-file label variants memorized.
tags: [session, harness-parallel, harness-cache, project-scoped-skills, depreciation-skill, rfile-reconcile, bs-001-002-merge, canonical-catalog]
---

# April 30th — Harness + Skills Reorg + Depreciation Skill Session

Picks up from `Archive\April 29th Inventory Breakdown Session.md`. That handoff was stale by the time this session opened — between it and now the user had run a full GOOG onboarding session that crashed mid-Excel-review. This session wrapped up GOOG, parallelized + cached the regression harness, locked the 5-ticker baseline, consolidated the BS cash row, moved every financials skill to project-local scope, generated the canonical catalog and made a first pass at projection-class annotations, and built phase 1 of a new analytical skill (`depreciation-amortization-impairment-projections`) with end-to-end R-file reconciliation. Next session opens with **finishing the remaining ~30 reconcile drifts** (mostly accumulated-depreciation row pattern conflicts on GOOG / PG) using the per-ticker label catalog now in memory, then phase 2 (class-level breakdowns from R-files).

## Starting state

- 4-ticker harness baseline (CELH 12 + PG 14 + PEP 13 + MNST 20 = 59 filings) clean against 148-entry library, but all golden re-locks happened pre-GOOG.
- GOOG onboarding mid-flight from prior crashed session: 28 validated files written, workbook built, 14 new generic library entries shipped (148 → 162) but with GOOG-centric prose notes; ledger essentially empty.
- Excel was open on `GOOG_model.xlsx` at moment of crash (`~$GOOG_model.xlsx` lock file present).
- Library notes for the 14 GOOG-era entries hadn't been genericized.

## Work done this session

### 1. GOOG onboarding wrap-up

Verified all 28 GOOG validated files clean (0 novels, 0 fails, 0 warns; 4,320 mapped + 941 subtotal/memo line items, 0 unmapped). The 14 new generic entries + alias additions to existing ones collapsed all 57 unique GOOG novels (Class A/B/C share-count label variants all route via concept). Cleared stale Excel lock file. Genericized 13 of the 14 entries' prose notes (GEN-BS-055 already clean).

### 2. Snapshot harness — parallelization + extract caching

`run.py` `main()` split into Phase A (parallel `run_pipeline` per ticker via `ThreadPoolExecutor`) + Phase B (serial post-processing). New `--max-workers N` flag, default `min(cpu_count, n_tickers)`. Threading works because `_run` blocks on `subprocess.run` (releases GIL). Cold runtime 264s sequential → 77s parallel (3.4x).

Plus extract cache at `_regression/_extract_cache/{sha256(source + library + extract.py)}.json` — skips the extract subprocess on cache hit, atomically writes via temp+rename. Warm-cache run: 41s (further 1.9x; reconcile/validate now the long pole). New `--no-cache` flag for forced fresh extract. Per-ticker errors no longer abort the whole run; failures summarized at end.

### 3. GOOG locked into 5-ticker baseline

Fixed source_path format on 28 GOOG raw_*.json files (relative → absolute, matching CELH/PG/PEP/MNST). Added GOOG to `WORKBOOK_FILENAME` and `--ticker` choices. `_regression/goldens/GOOG/` populated via `--accept`. New baseline: 87 filings, all clean. Per `feedback_celh_pg_joint_regression.md` carried forward to **5 tickers** going forward.

### 4. GEN-BS-001/002 consolidation

Merged Restricted Cash (GEN-BS-002) into Cash & Cash Equivalents → renamed to "Cash, Cash Equivalents & Restricted Cash" (GEN-BS-001). Concepts promoted to `us_gaap_concepts` list with all three forms (`CashAndCashEquivalentsAtCarryingValue`, `RestrictedCash`, `CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents`). 6 aliases. Library 162 → 161. No ticker ledgers referenced GEN-BS-002, so no downstream cleanup. Re-locked all 5 tickers clean.

### 5. YTD sheets hidden + auto-chain path bug fixed

`model-qtr-derive/build.py` now sets `sheet_state="hidden"` on YTD P&L / YTD BS / YTD CF after rename. QTR sheets stay visible; YTD data still resolvable from QTR formulas. Snapshot harness doesn't capture sheet visibility, so no spurious diffs.

Bug exposed: `model-write/write.py:1704` hardcoded `Path.home() / ".claude" / "skills" / "model-qtr-derive"` for auto-chain — broke after the skills move (#6 below). Fixed to sibling-relative: `Path(__file__).resolve().parent.parent.parent / "model-qtr-derive" / ...` with `~/.claude/skills/` fallback. Pattern to use for any future inter-skill references.

### 6. Skills moved to project-local scope

Per user direction. All 10 financials skills moved from `~/.claude/skills/` → `Brain/Knowledge/Model Schema/.claude/skills/`: `financials-extract`, `financials-reconcile`, `financials-validate`, `financials-playground`, `model-write`, `model-qtr-derive`, `model-calc`, `sec-edgar-fetch`, `investor-relations-data-scraper`, `depreciation-amortization-impairment-projections`. `audio-transcription` + `analyze-earnings-transcript` stay at user-level. Skills now only visible when claude code launches from project root. Harness `SKILLS_ROOT` updated. **Working from `C:\Users\rodin` no longer sees the financials skills** — must launch from `Brain\Knowledge\Model Schema\`.

### 7. Canonical catalog generated + annotated

`Brain/Knowledge/Model Schema/canonical_catalog.md` — 161 entries grouped by sheet (29 IS / 52 BS / 80 CF). Renamed column `subclass` → `projection model class` per user. D&A-related CF rows clustered together at top of CF section (per user; GEN-CF-058 Non-Cash Lease excluded after user pushback). First pass annotated 39 derived rows (subtotals, parent/child, BS↔CF deltas, cross-sheet links, rollforwards, EPS, memos). User added projection annotations for ~30 more rows (DSO, DPO, DIO, % of revenue, hold-last variants); a few open questions flagged.

### 8. New skill — `depreciation-amortization-impairment-projections` (phase 1)

New analytical-layer skill at project-local scope. Hybrid input — primary-statement values reuse `validated_*.json` canonical mappings (D&A on CF, impairments on IS/CF), footnote-only values lift from `companyfacts.json` (PP&E gross, accumulated depreciation, intangibles by class, future amortization schedule, goodwill rollforward, ROU asset balances, lease costs). Per-ticker output `asset_depreciation.json`. Schema includes `*_combined` fields for filers that don't split D&A. Unit-normalized to filer's reporting unit (CELH/MNST thousands, GOOG/PG/PEP millions). Fiscal-year end month derived empirically from companyfacts. All 5 tickers produced clean outputs. Future phases (per SKILL.md): R-file class-level breakdowns; ASSET DEPRECIATION SCHEDULE workbook tab; rewire GEN-BS-007 PP&E + GEN-BS-012 Intangibles + GEN-CF-002 D&A to source from this tab via rollforward (so all three move in tandem).

### 9. R-file reconciliation framework + 4 framework bugs

`scripts/reconcile.py` cross-checks asset_depreciation.json against `*_financial_report.xlsx` for every filing on disk. 502 checks across 111 R-files; 91% match (455 OK / 30 DRIFT / 17 MISSING). Drove four real fixes:

- `_select_per_period` was picking prior-year-comparable instead of current-period when companyfacts ambiguously tagged the same `(fy, fp)` twice — fixed to prefer latest `end` date per (fy, fp). CELH FY2024 PP&E went from 24868 (wrong, was FY2023's value) to 55602 (correct, matches R-file).
- `INTANGIBLES_NET` mapping favored definite-lived only — flipped to broader `IntangibleAssetsNetExcludingGoodwill` first. Saved 17 CELH drifts.
- `derive_fy_end_month` defaulted to December — now derived from companyfacts `fp=FY` end-dates. PG (June fiscal) went from 0 OK / 171 DRIFT to 178 OK / 20 DRIFT.
- PP&E pattern matched gross-PP&E row on PEP's 3-row BS sequence — split into preferred (net-explicit) + fallback (bare label). PEP went from 14 drifts to 0.

### 10. Per-ticker R-file label variants memorized

Surveyed all 5 tickers' most-recent 10-K R-files; cataloged label variants per concept (PP&E net, accumulated depreciation, intangibles net, goodwill, D&A) and per-ticker disclosure sheet locations. Saved as `project_rfile_label_variants.md`, indexed in MEMORY.md. Includes remaining-drift analysis (GOOG/PG accumulated-depreciation row pattern, MNST "and amortization" suffix, PG's `TRADEMARKS AND OTHER INTANGIBLE ASSETS, NET` quirk) so next iteration starts from this catalog rather than re-discovering.

## Current state

- **Library:** 161 entries (was 162; BS-002 merged into BS-001).
- **Snapshot harness:** 5 tickers, 87 filings, all clean. Cold 77s, warm 41s. Cache + parallel ticker workers.
- **New skill `depreciation-amortization-impairment-projections`:** phase 1 shipped. Per-ticker asset_depreciation.json for all 5 tickers. R-file reconcile: 91% OK across 502 checks.
- **Canonical catalog:** 161 entries with ~70 annotated. Column = `projection model class`. D&A cluster at top of CF section.
- **Skill location:** all 10 financials skills at project-local scope. `audio-transcription` + `analyze-earnings-transcript` stay user-level.
- **Memory:** 1 new entry — `project_rfile_label_variants.md`.

## Open decisions / pending work

1. **NEXT SESSION OPENS WITH** — finish reconcile drift cleanup. Per-ticker label catalog already in memory; remaining ~30 drifts are mechanical fixes to `RECONCILE_PATTERNS` in `reconcile.py` (mostly GOOG/PG accumulated depreciation, MNST's "and amortization" suffix variant). Then phase 2 of the new skill — parse `*_financial_report.xlsx` for class-level breakdowns (per-asset-class depreciation rates, useful-life ranges).
2. **Phase 3 + 4 of new skill** — model-write extension to emit ASSET DEPRECIATION SCHEDULE workbook tab; model-calc rewires PP&E + Intangibles + D&A to source from this tab via rollforward.
3. **Catalog annotation continues** — user mid-way through `projection model class` column. Once complete, this becomes input for the deferred driver-kind sprint (replacing `_label_contains` heuristics in `inference.py` with structural canonical metadata).
4. **`cf_delta_target` extension on BS canonicals** — declare for AR / Inv / Prepaid / AP / Other CA / etc. so `inference.py` doesn't runtime-match BS↔CF working-capital pairs by label. Aligns with no-heuristic policy.
5. **Active propagating rules** carried: playground sync, no-heuristic policy, no validator sign flips, no duplicate anchor subtotals, **joint regression on 5 tickers** (CELH+PG+PEP+MNST+GOOG = 87 filings).
6. **Working directory awareness** — financials skills only visible when claude code launches from `Brain\Knowledge\Model Schema\`.

## Key file paths

| Purpose | Path |
|---|---|
| This handoff | `Brain\Sessions\CELH Model\Handoffs\April 30th Harness + Skills Reorg + Depreciation Skill Session.md` |
| Prior handoff (archived) | `Brain\Sessions\CELH Model\Handoffs\Archive\April 29th Inventory Breakdown Session.md` |
| Roadmap | `Brain\Sessions\CELH Model\ROADMAP.md` |
| Library (161 entries) | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` |
| Canonical catalog (annotated) | `Brain\Knowledge\Model Schema\canonical_catalog.md` |
| Snapshot harness | `Brain\Knowledge\Model Schema\_regression\run.py`; goldens at `_regression\goldens\{TICKER}\`; cache at `_regression\_extract_cache\` |
| Project-local skills | `Brain\Knowledge\Model Schema\.claude\skills\{financials-extract,financials-reconcile,financials-validate,financials-playground,model-write,model-qtr-derive,model-calc,sec-edgar-fetch,investor-relations-data-scraper,depreciation-amortization-impairment-projections}\` |
| New skill | `Brain\Knowledge\Model Schema\.claude\skills\depreciation-amortization-impairment-projections\` (`SKILL.md`, `scripts\extract.py`, `scripts\reconcile.py`, `scripts\concept_catalog.py`, `scripts\models.py`) |
| Per-ticker D&A output | `Brain\Knowledge\Model Schema\Ticker Libraries\{TICKER}\asset_depreciation.json` (5 files) |
| Memory (new) | `~/.claude/projects/.../memory/project_rfile_label_variants.md` |

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
