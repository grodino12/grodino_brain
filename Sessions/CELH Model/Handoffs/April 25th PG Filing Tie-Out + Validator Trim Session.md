---
type: session-handoff
date: 2026-04-25
topic: PG Q2 FY2026 10-Q ran end-to-end on the new architecture; surfaced + fixed CI→IS merge bug, iXBRL concept-to-statement first-wins bug, preferredLabel parsing for visual signs, IS canonical NI semantics (true NI vs NI-Less-NCI), Pre-Tax canonical mis-tagging override for PG, IS cascade row injection + formula switch (MINUS-SUM → PLUS-SUM), CF Net Change in Cash formula, EPS format matcher, validator trim from 18 → 7 filer-tie rules.
tags: [session, pg-tie-out, ixbrl-linkbase, cascade-formulas, validator-trim, archive-rotation]
---

# April 25th — PG Filing Tie-Out + Validator Trim Session

Picks up from `Archive\April 25th Framework Audit + Section-Driven Architecture Session.md`. That session shipped the framework audit but never ran end-to-end against PG. This session ran the regression and worked the long tail it surfaced (mostly latent bugs, not framework-audit fallout). End state: PG H1 FY2026 10-Q workbook ties to PG's filed IS/BS/CF; validators trimmed to a 7-rule "tie to filer's reported subtotals" set. **Next**: CELH regression on the new architecture, then OCI 4th-statement build.

## Starting state

- April 25 Framework Audit shipped extract-merge, sign-3-value, section-driven validators, LibraryEntry guard — none re-run on PG.
- PG outputs from prior session were stale (pre-audit shape); workbook had wrong-sign CF lines, hardcoded subtotals, missing Gross Profit row, summed-instead-of-netted interest, and an IS cascade that disagreed with PG's reported NI.
- 18 Pydantic validators in place — many overlapping cascade-checks the user later flagged as overkill.

## Work done this session

### 1. Dead-code purge + playgrounds refreshed

Explore agent found 9 stale CELH `Model Output\*.json` files (~1MB, pre-audit shape) + 7 `__pycache__` dirs — deleted. `playground_architecture.html` + `playground_schema.html` updated for framework-audit collapse (one extract dispatcher, LibraryEntry validation, CASH_OTHER section, sign 3-value, section-driven validators, RawLineItem field updates, new LibraryEntry class). LS_KEY v8 → v9.

### 2. iXBRL extractor — CI dropped + multi-statement attribution + regex fix + preferredLabel parsing

Four extractor fixes:
- `STATEMENT_CODE_MAP["CI"]` removed; CI now skipped like SE/DETAIL pending OCI 4th-statement build (CI is a peer of IS, not a continuation). Saved `feedback_oci_separate_statement.md`.
- `build_concept_statement_map` returns `dict[concept, set[codes]]` instead of first-wins string. The old logic was dropping `us-gaap:NetIncomeLoss` from CF (because IS R-file processed first locked the concept to IS). `group_into_statements` adds each fact to every matching bucket.
- `canonical_statement_code` regex switched literal spaces → `\s*` so it matches both R-file ShortNames ("Consolidated Statements of Cash Flows") AND presentation-linkbase role URIs ("ConsolidatedStatementsofCashFlows"). This bug was hiding the entire preferredLabel feature.
- New `parse_presentation_negations()` fetches `*_pre.xml`, parses arcs with `preferredLabel="...negated*"`, returns `{(stmt_type, concept): True}`. Applied at line-item construction to negate values whose visual sign differs from the iXBRL fact's natural sign. Fixes PG's working-capital lines + capex / dividends / repayments to match PG's parens-negative visuals. Saved `feedback_cf_visual_sign.md`.

### 3. Library + ticker-ledger updates

- GEN-IS-022 renamed `"Net Income (Loss) Including NCI"` → `"Net Income (Loss)"` (the TRUE NI). GEN-IS-011 renamed → `"Net Income (Loss) Less NCI"` (post-NCI parent). GEN-IS-023 gets new `Section.POST_NI_DEDUCTION`. GEN-IS-022 + GEN-CF-001 + GEN-IS-011 flagged `row_type: "subtotal"`; extract honors library row_type now.
- GEN-IS-010 (Tax) gets explicit `sign_convention: "negative"` — IS keyword detection sees both "expense"+"benefit" → ambiguous → was falling back to as_reported.
- GEN-IS-009 gets "earnings before income taxes" alias.
- PG ticker `MAP-IS-001` override routes `IncomeLossIncludingPortionAttributableToNoncontrollingInterest` to "Pre-Tax Income (Loss)" — PG mis-uses this concept for EBT (FASB taxonomy reserves it for post-tax NI). Saved `feedback_ebt_pretax_canonical.md`.

### 4. Reconcile + model-write

- Reconcile UNCLASSIFIED halt skip extended from "memo" to also skip "subtotal"/"total" — bottom-of-IS rollup rows (NI flavors) without `filing_section` don't trigger halt.
- model-write reads `item.sign_convention` first (per-item from extract), falls back to library `sign_by_rule_id`. Net interest now correctly nets (-417+222=-195) instead of summing positives. Sign convention skipped entirely on CF sheets (preferredLabel already negated at extract).
- IS cascade overhaul: `_is_subtotal_formula` switched MINUS-SUM → PLUS-SUM (works with natural-sign items). Cascade subtotals (Gross Profit / Op Income / Pre-Tax / NI) auto-injected at section transitions when filer omits them — PG gets a Gross Profit row injected. Op Income / Pre-Tax / NI rows are formulas that overwrite filer values. NI Less NCI = `=B(NI)-B(NCI)` special case. EPS format matcher switched from `"EPS"` substring to `"per share"` (matches PG's "Basic Earnings (Loss) per Share").
- CF Net Change in Cash formula: `=B(CFO)+B(CFI)+B(CFF)+SUM(cash_other)` written after section subtotals.

### 5. Validator trim 18 → 7

User: "30 validators is overkill and doesn't account for nuance." Kept only filer-tie checks: BS-1 (TCA), BS-2 (TA), BS-3 (TCL), BS-4 (TL), BS-5 (TSE), IS-4 (NI), CF-1 (Net Change in Cash) — each compares computed sum/cascade against filer's reported subtotal. Deleted BS-6, BS-7, IS-1/2/3, CF-2/3/4/5, X-1/2/4, M-1, `_find_by_canonical_label`. Added `--allow-fails` flag. CF-1 fixes: model_sheet match handles "QTR CF"; cash_other bucket summed when no subtotal exists. validate.py 960 → 650 lines.

### 6. Archive rotation rule

Workflow change: when writing a new handoff, all prior `*.md` in the task's `Handoffs\` root move to `Handoffs\Archive\`. Saved into `feedback_session_handoffs.md` and baked into the template below.

## Current state

- **PG H1 FY2026 pipeline runs end-to-end clean**: 0 novels, 0 unclassified, 13 PASS / 9 inconclusive WARN / 0 FAIL. The 9 warns are duplicate / partial CF + IS statements per period (3-month variants where PG only reports YTD CF) — inconclusive, not failures.
- **PG IS** matches PG visual: Net Sales 44,594 → Gross Profit 22,873 (formula) → Op Income 11,222 (formula) → Pre-Tax 11,455 (formula) → NI 9,112 (formula) → NI Less NCI 9,070 (formula) → EPS Basic $3.82 / Diluted $3.73.
- **PG CF** signs all mirror PG visual; Net Change in Cash formula sums to 1,269 = PG actual; subtotals tie within $1 (rounding).
- **PG BS** TCA / TA / TCL / TL / TSE all tie within $1.
- **Library: 109 entries** (unchanged in count; renames only). Sign_convention now on 8 entries.
- **Workbook output**: `PG_model_v6.xlsx` is the latest clean build; v1–v5 are intermediate versions left on disk.

## Open decisions / pending work

1. **CELH regression** — overdue. All architecture changes today need a CELH FY2024 + FY2025 10-K run to confirm no regression.
2. **Period-label fiscal_year mis-tagging** — duplicate/partial CF + IS statements per period get inconclusive WARNs (3-month variants where PG only reports YTD). Inconclusive, not fail; noisy.
3. **OCI 4th statement** (roadmap §7) — restore the 7 OCI library entries when the sheet ships.
4. **PG full 10-K onboarding** — add ANNL parallels for `MAP-IS-001` and `NEW-BS-001` when first PG 10-K runs.
5. **iXBRL label linkbase parsing** (long-term) — would eliminate need for ticker-specific overrides like `MAP-IS-001`.
6. **PG_model_v* cleanup** — `v1..v6` on disk; consolidate once user closes Excel.
7. **`financials-validate/SKILL.md` stale** — description still mentions "BS-1..BS-7, CF-1/CF-2, X-1..X-4". Update to 7-rule reality.
8. **Active propagating rules** — playground sync (`feedback_keep_playgrounds_in_sync.md`) + archive rotation (`feedback_session_handoffs.md`).

## Key file paths

| Purpose | Path |
|---|---|
| This handoff | `Brain\Sessions\CELH Model\Handoffs\April 25th PG Filing Tie-Out + Validator Trim Session.md` |
| Prior handoffs (rotated) | `Brain\Sessions\CELH Model\Handoffs\Archive\` |
| Roadmap | `Brain\Sessions\CELH Model\ROADMAP.md` |
| iXBRL extractor | `~\.claude\skills\financials-extract\scripts\ixbrl_path.py` |
| PDF extractor | `~\.claude\skills\financials-extract\scripts\pdf_path.py` |
| Generic library | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` |
| PG ticker ledger | `Brain\Knowledge\Model Schema\PG\decisions_ledger.json` |
| Section enum | `Brain\Knowledge\Model Schema\financials-schema\financials_schema\enums.py` |
| Validate (7 rules) | `~\.claude\skills\financials-validate\scripts\validate.py` |
| Reconcile | `~\.claude\skills\financials-reconcile\scripts\reconcile.py` |
| model-write | `~\.claude\skills\model-write\scripts\write.py` |
| PG workbook | `Brain\Knowledge\Model Schema\PG\Model Output\PG_model_v6.xlsx` |
| New memory feedbacks | `~\.claude\projects\C--Users-rodin\memory\feedback_{oci_separate_statement,cf_visual_sign,ebt_pretax_canonical}.md` |
| Updated memory (archive rotation) | `~\.claude\projects\C--Users-rodin\memory\feedback_session_handoffs.md` |

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
