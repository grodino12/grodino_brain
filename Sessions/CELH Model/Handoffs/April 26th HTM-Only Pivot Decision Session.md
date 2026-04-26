---
type: session-handoff
date: 2026-04-26
topic: Implemented dimensioned-only-concept synthesis to recover CELH FY2025 Intangibles ($1.39B); discovered the precondition (concept has a defref anchor on a primary R-file) is unsound because R-files conflate primary statement rows with footnote disclosure tables, producing phantom synthesized values; reverted the synthesis and decided to pivot the iXBRL extractor to HTM-only walking — drop R-files entirely from the primary-statements pipeline.
tags: [session, celh, ixbrl-extractor, dimensioned-synthesis, htm-only-pivot, architecture]
---

# April 26th — HTM-Only Pivot Decision Session

Picks up from `Archive\April 26th CELH Onboarding + Visual Label + Section Scanning + Bucket A B Triage Session.md`. That earlier session shipped 9 framework fixes onboarding CELH (3 10-Ks + 9 10-Qs) and got 11 of 12 filings clean — only CELH FY2025 still failing on a $1,391,915 BS-2 gap from missing Alani Nu intangibles tagged in dimensioned-only iXBRL facts. This session implemented the planned synthesis fix to recover those breakouts, found that the synthesis precondition (R-file defref anchor presence) systematically pulls in footnote/disclosure facts and routes them onto primary statements, reverted the synthesis cleanly, and pivoted the strategy: **next session opens with rewriting the iXBRL extractor to walk the primary HTM directly and drop R-file dependence entirely.**

## Starting state

- PG: 14 filings clean — `PG_model_v15.xlsx` canonical, per-period dedup architecture stable.
- Library: 119 entries, 10 filer-tie validators, paren-of-value sign authority, variant collapse.
- CELH: 0 novels across 12 filings, but 2025-FY validation 10-FAIL on BS-2 + CF-3/CF-4. Prior session identified the dimensioned-only-concept extraction gap as root cause of BS-2.
- Outstanding: BS-2 closure, then OCI 4th statement, then quarterly model-calc.

## Work done this session

### 1. Dimensioned-only-concept synthesis — implemented and reverted
Added `synthesize_dimensioned_only_facts(facts, concept_map)` between `parse_facts` and `group_into_statements` in `ixbrl_path.py`. Algorithm: per (concept, period), if every fact is segment-dimensioned AND the concept appears in `concept_map` (R-file defref anchors), sum single-axis members on the most-populous axis and synthesize a default-context `IxFact`. Restricted to "real reporting periods" — periods where some non-dimensioned fact already exists somewhere in the filing — to filter out acquisition-disclosure dates (2025-04-01, 2025-08-28, 2025-08-31, 2024-11-01) that hold ONLY dimensioned facts. Surfaced the synthesis count + concept list in `extraction_metadata.dimensioned_only_synthesis`. **Reverted at end of session.**

### 2. Verified the Intangibles case worked
Ran extract on CELH 2025-FY 10-K. Synthesized `IntangibleAssetsNetExcludingGoodwill = $1,391,915` (CustomerRelationships $111,604 + Brands $1,280,311 from `FiniteLivedIntangibleAssetsByMajorClassAxis`). Manually verified BS-2 closure: TCA ($1,811,154) + sum(NCA = $3,308,467) = $5,119,621 ✓ matches reported Total Assets exactly. Goodwill correctly skipped (default-context fact existed). The narrow case the synthesis was DESIGNED for worked.

### 3. Discovered the precondition is unsound
Of 17 synthesized facts surfaced after the period-key filter, only Intangibles was legitimate. Inspecting facts directly in the iXBRL revealed:
- `ReceivablesNetCurrent` ($349,100K synthesized) — single dimensioned fact on `RelatedPartyTransactionAxis=RelatedPartyMember`. This is **related-party AR from a footnote disclosure table**, not the primary BS AR row (which is `AccountsReceivableNetCurrent` = $755,499K, separately tagged). Synthesis put a phantom row labeled "Accounts receivable-net" on the BS at $349,100K alongside the real $755,499K row.
- `BusinessCombinationConsiderationTransferredEquityInterestsIssuedAndIssuable` ($721,964K synthesized) — only Alani Nu's portion. Rockstar/Pepsi Series B fact ($907,920K) was excluded because it's multi-axis. Even the "correct" sum ($1.6B+) is from a per-acquisition footnote breakdown, not a value displayed on the primary CF.
- `Stock*Shares*` concepts — SE roll-forward dimensioned facts, not primary statements.

Root cause: the R-file's defref anchor list mixes primary statement rows with footnote disclosure tables. "Concept has anchor on BS R-file" is NOT the same as "concept is a primary BS row." User reaction: this is the 5th time R-file dependence has caused phantom data.

### 4. Decision: pivot iXBRL extractor to HTM-only
User directive: extract financial statements from the **primary `.htm` filing only**. R-files are acceptable for future analytical/disclosure features (charts, dashboards, footnote browsers) but must not feed `RawFiling.statements`. The HTM has both the rendered HTML structure (visible labels, visible numbers in cells) AND the iXBRL inline tags (`<ix:nonFraction>`) embedded inside the same cells — single source of truth, no drift. Reverted the synthesis function, the call site in `build_raw_filing`, and the metadata key. Extractor returned to pre-session state.

### 5. Memory rule saved
`feedback_no_rfiles_for_financials.md` — BS/IS/CF/CI line items must come from the primary HTM only; R-files OK for non-primary-statement use cases (future analytical surfaces) but never for what flows into `RawFiling.statements`. User has flagged this multiple times across sessions; the rule is the durable fix.

## Current state

- **Extractor state**: `ixbrl_path.py` reverted to pre-session — no synthesis pass.
- **CELH FY2025 BS-2**: still failing +$1,391,915 (the original gap). Will be solved by the HTM-only pivot, not by patching the R-file approach.
- **CELH validation across 12 filings**: unchanged from prior handoff — 11 clean, 1 (FY2025) with the BS-2 + CF-3/CF-4 fails.
- **PG**: untouched — `PG_model_v15.xlsx` stable.
- **Library / ledgers**: unchanged.

## Open decisions / pending work

1. **NEXT SESSION OPENS WITH: HTM-only iXBRL extractor rewrite.** Drop the R-file pipeline entirely from `ixbrl_path.py`. New design: walk the primary HTM as rendered HTML — find statement tables by heading text matchers, walk rows in document order, pull the visual label from the row's first `<td>`, pull the displayed numeric value from each value cell's text content (parens-negative authoritative), pull concept name from the `<ix:nonFraction name="...">` inside the same cell when present. Statement classification from table headings; section walking from in-table `<td>` header rows + subtotal-driven transitions; period extraction from column header `<td>`s. Drop `build_concept_statement_map`, `extract_anchors_from_report`, `extract_sections_from_report`, the `R{n}.htm` / `FilingSummary.xml` fetch + parse. The dimensioned-only-synthesis problem dissolves — visible cell text is the value, no synthesis needed. See latest handoff §4 for full discussion.
2. **Regression test plan for HTM rewrite**: PG 14 filings (currently clean) + CELH 11 working filings + CELH 2025-FY (the BS-2 closure target). All must round-trip with no novels, all validators passing, before the rewrite is considered done.
3. **`_pre.xml` linkbase** — keep accessible as a tie-breaker only, never primary signal. Per the new memory rule. Today the linkbase provides `negate_map` (already redundant with `_is_parens_negative`), `order_map` (replaceable by HTM document order), and `section_map` (replaceable by HTM table walk). After the rewrite, evaluate whether linkbase still earns its dependency.
4. **Carry the playground sync rule** through the rewrite — `playground_architecture.html` currently shows R-file nodes feeding the iXBRL extractor; that node graph + scaffolding text needs to update, LS_KEY bumped (v9 → v10).
5. **Bucket C / remaining CF-3 + CF-4 gaps on CELH 2024 / 2023** — re-evaluate after HTM rewrite lands. Many of those gaps stem from the same dimensioned-only / R-file mis-routing class of bugs.
6. **OCI 4th statement** — still carried.
7. **`financials-validate/SKILL.md`** — still on the 10-rule reality update list.
8. **CELH workbook build** — gated on full validation pass.
9. **Migrate generic library `sign_convention` audit + the IS-only keyword detection split** — carried, not blocking.

## Key file paths

| Purpose | Path |
|---|---|
| This handoff | `Brain\Sessions\CELH Model\Handoffs\April 26th HTM-Only Pivot Decision Session.md` |
| Prior handoffs (rotated) | `Brain\Sessions\CELH Model\Handoffs\Archive\` |
| Roadmap | `Brain\Sessions\CELH Model\ROADMAP.md` |
| iXBRL extractor (target of next session's rewrite) | `~\.claude\skills\financials-extract\scripts\ixbrl_path.py` |
| Memory rule (new) | `~\.claude\projects\C--Users-rodin\memory\feedback_no_rfiles_for_financials.md` |
| Lookup module | `Brain\Knowledge\Model Schema\financials-schema\financials_schema\lookup.py` |
| Reconcile | `~\.claude\skills\financials-reconcile\scripts\reconcile.py` |
| Generic library (119 entries) | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` |
| CELH ledger (18 entries) | `Brain\Knowledge\Model Schema\CELH\decisions_ledger.json` |
| CELH source filings | `Brain\Sources\CELH\{2023-Q1..2025-FY}\filings\` |
| CELH 2025-FY 10-K (BS-2 target) | `Brain\Sources\CELH\2025-FY\filings\CELH_2025-12-31_10-K.htm` |
| CELH intermediates | `Brain\Knowledge\Model Schema\CELH\Model Output\.cache\` |
| PG canonical workbook (untouched) | `Brain\Knowledge\Model Schema\PG\Model Output\PG_model_v15.xlsx` |
| Playground (needs node-graph update post-rewrite) | `Brain\Knowledge\Model Schema\playground_architecture.html` |

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
