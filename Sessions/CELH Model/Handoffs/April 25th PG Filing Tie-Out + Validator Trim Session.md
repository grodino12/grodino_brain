---
type: session-handoff
date: 2026-04-25
topic: PG Q2 FY2026 10-Q ran end-to-end on the new architecture; surfaced + fixed CI→IS merge bug, iXBRL concept-to-statement first-wins bug, preferredLabel parsing for visual signs, IS canonical NI semantics (true NI vs NI-Less-NCI), Pre-Tax canonical mis-tagging override for PG, IS cascade row injection + formula switch (MINUS-SUM → PLUS-SUM), CF Net Change in Cash formula, EPS format matcher, validator trim from 18 → 7 filer-tie rules.
tags: [session, pg-tie-out, ixbrl-linkbase, cascade-formulas, validator-trim, archive-rotation]
---

# April 25th — PG Filing Tie-Out + Validator Trim Session

Picks up from `Archive\April 25th Framework Audit + Section-Driven Architecture Session.md`. That session shipped the framework audit but never ran end-to-end against PG. This session ran the regression and worked the long tail of issues it surfaced — most of which were latent bugs from before today, not framework-audit fallout. End state: PG H1 FY2026 10-Q workbook ties to PG's filed values across IS, BS, and CF. Validators trimmed to a 7-rule "tie to the filer's reported subtotals" set. **Next session**: CELH regression on the new architecture, then OCI 4th-statement build (roadmap §8) or move on to model-calc QTR drivers.

## Starting state

- April 25 Framework Audit shipped extract-merge, sign-3-value, section-driven validators, LibraryEntry guard — none re-run on PG.
- PG outputs from prior session were stale (pre-audit shape); workbook had wrong-sign CF lines, hardcoded subtotals, missing Gross Profit row, summed-instead-of-netted interest, and an IS cascade that disagreed with PG's reported NI.
- 18 Pydantic validators in place — many overlapping cascade-checks the user later flagged as overkill.

## Work done this session

### 1. Dead-code purge

Explore agent found 9 stale CELH `Model Output\*.json` files (~1MB, contained pre-audit `parens_negative` strings) + 7 `__pycache__` dirs. Deleted both.

### 2. Playgrounds refreshed

`playground_architecture.html` updated for the framework-audit collapse (one extract dispatcher, LibraryEntry validation, CASH_OTHER section, sign 3-value, section-driven validators, decisions-ledger reflects PG state); LS_KEY bumped v8 → v9. `playground_schema.html` got Section.CASH_OTHER (was FX_RECONCILIATION), SignConvention 3-value Literal, RawLineItem `canonical_label` + `ledger_rule_id` fields, MappedLineItem stripped of inherited fields, new LibraryEntry class. Title de-CELHed.

### 3. iXBRL CI dropped from IS merge

`STATEMENT_CODE_MAP["CI"]` removed; CI statements now skipped like SE/DETAIL pending the OCI 4th-statement build. The previous CI→IS merge was always a v1 mistake (CI is a peer of IS, not a continuation). Saved `feedback_oci_separate_statement.md`.

### 4. Multi-statement concept attribution

`build_concept_statement_map` returns `dict[concept, set[codes]]` instead of `dict[concept, str]`. The first-wins logic was silently dropping `us-gaap:NetIncomeLoss` from the CF (because IS R-file processed first locked it to IS). `group_into_statements` adds each fact to every matching bucket. Net effect: NetIncomeLoss now reaches CF as the operating-section starting line.

### 5. canonical_statement_code regex fix

`re.compile(r"cash flow")` couldn't match presentation-linkbase role URI `"ConsolidatedStatementsofCashFlows"` (no spaces). Switched all matchers to `\s*` so they handle both R-file ShortNames (spaced) and role URIs (concatenated CamelCase). This bug was masking the entire preferredLabel feature on CF.

### 6. iXBRL preferredLabel parsing for visual signs

New `parse_presentation_negations()` fetches `*_pre.xml` from the filing archive, parses `<link:presentationArc preferredLabel="...negated*">` elements, builds `dict[(stmt_type, concept), True]`. Applied at line-item construction to negate values whose visual sign differs from the iXBRL fact's natural sign. Fixes PG's working-capital lines (AR / Inventories / Other Op Items / Gain Loss on Disposal) and capex / acquisitions / dividends / repayments — all now match PG's parens-negative visual presentation. Saved `feedback_cf_visual_sign.md`.

### 7. PG-specific Pre-Tax canonical override

PG tags Earnings Before Income Taxes (11,455 H1 FY26) with `us-gaap:IncomeLossIncludingPortionAttributableToNoncontrollingInterest` — non-standard; FASB taxonomy reserves that concept for post-tax NI. Added `MAP-IS-001` to PG's `decisions_ledger.json` routing this concept to "Pre-Tax Income (Loss)". Added "earnings before income taxes" alias to GEN-IS-009 for filers who tag it correctly. Saved `feedback_ebt_pretax_canonical.md`. Long-term fix: parse iXBRL label linkbase to recover filer's visual labels.

### 8. NI canonical renames + POST_NI_DEDUCTION section

GEN-IS-022 renamed `"Net Income (Loss) Including NCI"` → `"Net Income (Loss)"` (the TRUE NI line, before NCI split). GEN-IS-011 renamed `"Net Income (Loss)"` → `"Net Income (Loss) Less NCI"` (post-NCI parent line). GEN-IS-023 (NCI deduction) gets new `Section.POST_NI_DEDUCTION`. GEN-IS-022 + GEN-CF-001 + GEN-IS-011 flagged `row_type: "subtotal"` in library; extract honors library row_type now (was only honoring `memo`).

### 9. Tax sign explicit-negative

Added `sign_convention: "negative"` to GEN-IS-010 because IS keyword detection sees both "expense" + "benefit" → ambiguous → falls back to as_reported. Tax now stored -|abs|.

### 10. Reconcile UNCLASSIFIED halt softened

Extended row_type skip from "memo" only to also skip "subtotal" + "total". Bottom-of-IS rollup rows (NI flavors) without `filing_section` no longer trigger the halt.

### 11. model-write per-item sign_convention

Reads `item.sign_convention` first (set by extract via library or IS keyword detection), falls back to library `sign_by_rule_id`. Net interest items now correctly net (-417 + 222 = -195) instead of summing positives. Sign convention skipped entirely on CF sheets per the visual-sign rule (preferredLabel already handled it at extract).

### 12. IS cascade formulas overhaul

`_is_subtotal_formula` switched MINUS-SUM → PLUS-SUM to work with natural-sign items. Cascade subtotals (Gross Profit / Op Income / Pre-Tax / NI) auto-injected at section transitions when the filer doesn't break them out. PG gets a Gross Profit row injected (PG omits it natively). Op Income / Pre-Tax / NI rows are now formulas that overwrite filer values. NI Less NCI = NI − NI Attributable to NCI as a special-case formula. EPS format matcher switched from `"EPS"` substring to `"per share"` (matches PG's "Basic Earnings (Loss) per Share" canonical).

### 13. CF Net Change in Cash formula

`=B(CFO) + B(CFI) + B(CFF) + SUM(cash_other rows)` written after the section subtotals.

### 14. Validator trim 18 → 7

User: "30 validators is overkill and doesn't account for nuance." Kept only filer-tie checks: BS-1 (TCA), BS-2 (TA), BS-3 (TCL), BS-4 (TL), BS-5 (TSE), IS-4 (NI), CF-1 (Net Change in Cash). Deleted BS-6 (accounting equation), BS-7 (deferred), IS-1/2/3 (cascades), CF-2/3/4/5 (cash beg/end + section sums), X-1/2/4 (cross-statement), M-1 (mapping consistency), `_find_by_canonical_label`. Added `--allow-fails` flag. CF-1 fixes: model_sheet match handles "QTR CF"; cash_other bucket summed when no subtotal exists. validate.py shrunk 960 → 650 lines.

### 15. Archive rotation rule added

User asked the workflow to rotate prior handoffs into `Handoffs\Archive\` every session. Saved into `feedback_session_handoffs.md` and baked into the template below.

## Current state

- **PG H1 FY2026 pipeline runs end-to-end clean**: 0 novels, 0 unclassified, 13 PASS / 9 inconclusive WARN / 0 FAIL. The 9 warns are duplicate / partial CF + IS statements per period (3-month variants where PG only reports YTD CF) — inconclusive, not failures.
- **PG IS** matches PG visual: Net Sales 44,594 → Gross Profit 22,873 (formula) → Op Income 11,222 (formula) → Pre-Tax 11,455 (formula) → NI 9,112 (formula) → NI Less NCI 9,070 (formula) → EPS Basic $3.82 / Diluted $3.73.
- **PG CF** signs all mirror PG visual; Net Change in Cash formula sums to 1,269 = PG actual; subtotals tie within $1 (rounding).
- **PG BS** TCA / TA / TCL / TL / TSE all tie within $1.
- **Library: 109 entries** (unchanged in count; renames only). Sign_convention now on 8 entries.
- **Workbook output**: `PG_model_v6.xlsx` is the latest clean build; v1–v5 are intermediate versions left on disk.

## Open decisions / pending work

1. **CELH regression** — overdue. All architecture changes today (multi-statement attribution, preferredLabel parsing, IS canonical renames, cascade formula switch, validator trim) need a CELH FY2024 + FY2025 10-K run to confirm no regression.
2. **Period-label fiscal_year mis-tagging** — duplicate / partial CF + IS statements per period get inconclusive WARNs. Some statements (3-month variants where PG only reports YTD CF) carry a wrong fiscal_year tag. Inconclusive only; noisy.
3. **OCI 4th statement** (roadmap §8) — pending. CI statements are skipped today. When sheet ships, restore the 7 OCI library entries pulled in the framework-audit session.
4. **PG full 10-K onboarding** — when first PG 10-K runs, add ANNL parallels for `MAP-IS-001` (Pre-Tax override; currently QTR P&L only) and `NEW-BS-001` (ESOP Debt Retirement Reserve; currently QTR BS only).
5. **iXBRL label linkbase parsing** (long-term) — would let us recover filer's actual visual labels per concept, eliminating the need for ticker-specific overrides like `MAP-IS-001`.
6. **PG_model_v* file cleanup** — `PG_model.xlsx` (locked by Excel during session) + `v2..v6` all on disk. Once user closes Excel, consolidate to single `PG_model.xlsx`.
7. **Validator catalog docs stale** — `financials-validate/SKILL.md` description still mentions "BS-1..BS-7, CF-1/CF-2, X-1..X-4". Update to the 7-rule reality.
8. **Active propagating rule** — playground sync on every structural change, per `feedback_keep_playgrounds_in_sync.md`.

## Key file paths

| Purpose | Path |
|---|---|
| This handoff | `Brain\Sessions\CELH Model\Handoffs\April 25th PG Filing Tie-Out + Validator Trim Session.md` |
| Prior handoff (archived this session) | `Brain\Sessions\CELH Model\Handoffs\Archive\April 25th Framework Audit + Section-Driven Architecture Session.md` |
| Roadmap | `Brain\Sessions\CELH Model\ROADMAP.md` |
| iXBRL extractor (preferredLabel parsing, multi-stmt attribution, regex fix, CI skip) | `~\.claude\skills\financials-extract\scripts\ixbrl_path.py` |
| PDF extractor (library row_type honored) | `~\.claude\skills\financials-extract\scripts\pdf_path.py` |
| Generic library (NI canonical renames, Tax sign, Pre-Tax aliases, row_type tags) | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` |
| PG ticker ledger (`MAP-IS-001` Pre-Tax override added) | `Brain\Knowledge\Model Schema\PG\decisions_ledger.json` |
| Section enum (POST_NI_DEDUCTION added) | `Brain\Knowledge\Model Schema\financials-schema\financials_schema\enums.py` |
| Validate (trimmed to 7 filer-tie rules; --allow-fails added; CF-1 fixes) | `~\.claude\skills\financials-validate\scripts\validate.py` |
| Reconcile (UNCLASSIFIED halt softened to skip subtotal/total) | `~\.claude\skills\financials-reconcile\scripts\reconcile.py` |
| model-write (per-item sign_convention; IS cascade injection + PLUS-SUM; NI Less NCI formula; CF Net Change formula; EPS matcher) | `~\.claude\skills\model-write\scripts\write.py` |
| PG workbook (latest clean build) | `Brain\Knowledge\Model Schema\PG\Model Output\PG_model_v6.xlsx` |
| New memory feedback files | `~\.claude\projects\C--Users-rodin\memory\feedback_oci_separate_statement.md`, `feedback_cf_visual_sign.md`, `feedback_ebt_pretax_canonical.md` |
| Updated memory feedback (archive rotation rule added) | `~\.claude\projects\C--Users-rodin\memory\feedback_session_handoffs.md` |

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
