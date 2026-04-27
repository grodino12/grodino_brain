---
type: session-handoff
date: 2026-04-26
topic: Built the HTM-only iXBRL walker from scratch (drops R-files entirely from primary statements), drove all 12 CELH filings to 0 novels / 0 validate fails / clean integration into one workbook, fixed a long-standing class of sign-detection holes via multi-cell paren handling + IS-1/IS-2/IS-3/IS-5 cascade validators, and codified two user directives — convertible preferred folds into Equity at model-write layout (filer renders mezzanine per ASC 480, but the model presents under SE) and "Net Change in Cash" subtotal is always synthesized in the workbook even when filers don't break it out.
tags: [session, celh, ixbrl-extractor, htm-walker, paren-detection, is-cascade-validators, mezzanine-fold, cf-net-change-synth]
---

# April 26th — HTM Walker Build-Out + 12 Filing Clean Session

Picks up from `Archive\April 26th HTM-Only Pivot Decision Session.md`. That session reverted the failed dimensioned-only-concept synthesis and decided to drop R-files entirely from primary-statement extraction; this session built the HTM-only walker from scratch, drove all 12 CELH filings to 0 novels / 0 validate fails / 1,182 cells in one workbook, and fixed several classes of sign-detection holes that surfaced along the way. Next session opens with carrying the same architecture across PG (regression confirmation) then onboarding a third ticker (PEP/KO) to validate cross-ticker generality.

## Starting state

- HTM-only walker design committed; R-file-feeds-statements path deleted from `_pre.xml` as primary signal per `feedback_no_rfiles_for_financials.md`.
- CELH FY2025 BS-2 still failing $1,391,915 (Intangibles missing) — the original target.
- 12 CELH filings on disk: 3 10-Ks + 9 10-Qs.
- PG 14 filings clean from prior sessions (not re-tested this session).
- ROADMAP listed "next session opens with HTM-only iXBRL extractor rewrite" as Active §12.

## Work done this session

### 1. New `ixbrl_path.py` from scratch (~830 lines)
Full HTM-walking architecture. `find_primary_tables()` walks the document in order, pairing each `Consolidated Statements of <X>` / `Balance Sheets` heading with the following `<table>` containing `ix:nonFraction`. Multi-table primary statements supported — CELH's CF spans 3 sub-tables under repeated titles, all accumulate into one CF cluster. `walk_statement_table()` walks rows in document order; first non-empty `<td>` gives the row label, subsequent cells with `ix:nonFraction` emit IxFacts. Statement classification by heading text; section walking via in-table header rows (`_HEADER_PATTERNS`) + subtotal-driven transitions (`_HTM_SUBTOTAL_TRANSITIONS`). All R-file machinery deleted — `build_concept_statement_map`, `extract_anchors_from_report`, `extract_sections_from_report`, FilingSummary.xml fetch, `R{n}.htm` parse, `_pre.xml` linkbase as primary, `requests` import — gone. Linkbase still kept accessible if a future session needs it as a tie-breaker, but never primary.

### 2. CELH FY2025 BS-2 closes — gap $0
The motivating target. Customer relationships-net ($111,604) and Brands-net ($1,280,311) emit naturally as plain BS rows from the primary table (the filer renders them with `FiniteLivedIntangibleAssetsByMajorClassAxis`-dimensioned facts — visible on the rendered page, so the walker emits them). TCA $1,811,154 + Σ(NCA = $3,308,467) = $5,119,621 = filer's TA. Per user direction the walker is purely visual: "If the page shows a row, emit a row" — no synthesis, no inference about iXBRL dimensions.

### 3. Title detection bounded (3-layer guard)
Initial cluster logic over-collected footnote tables; iteratively tightened to:
- Anchored regex `^(consolidated|condensed\s+consolidated)\s+(statements?|balance\s+sheets?)`
- ≤150 char length cap (real headings are short; footnote prose like "...is classified within investing activities in the Consolidated Statements of Cash Flows for the year ended..." is rejected by length + by the trailing-period check)
- Notes-section terminator (`^notes?\s+to\s+...financial\s+statements`) gated on `primary_collected` — fires only AFTER the first primary table has been collected, so the 10-Q TOC's "Notes to..." entry doesn't terminate the cluster prematurely.

### 4. OCI exclusion in combined IS+CI tables
CELH renders "Statements of Operations and Comprehensive Income" as ONE table (filer choice). Walker classifies as IS, walks top-down, stops on the OCI section header (`other\s+comprehensive\s+(income|loss)` OR bare `comprehensive\s+income` / `foreign\s+currency\s+translation`) so OCI rows don't pollute the IS. Per `feedback_oci_separate_statement.md`, the proper 4th-statement build is still future work — until then OCI rows are dropped at extract.

### 5. CF non-cash supplemental STOP
`_CF_NONCASH_STOP_RE` matches `(supplemental\s+(schedule|disclosure)s?\s+of\s+(non.cash|noncash))` and `((non.cash|noncash)\s+(investing|financing))`; walker stops emitting CF rows past this header. Eliminates "Fair value of share consideration issued in the Alani Nu Acquisition" + similar non-cash disclosures bleeding into CFO/CFI/CFF subtotals.

### 6. Cash beginning/ending instant fold
CF rendered "Cash, cash equivalents at beginning of period" / "...at end of period" with INSTANT contexts vs the duration contexts on flow rows. Without folding, instants orphan into 1-2-item mini-Statements. Fix in `_fold_cf_instants_into_durations()`: re-key each instant fact to the matching duration's CF bucket (cash-beg matches duration's `period_start`; cash-end matches `period_end`), with a 1-day tolerance so 12-31 instants pair with 1-1 durations. Folded facts are re-tagged `row_type="memo"` so they don't get summed into CashOther.

### 7. Equity-class label-cell handling
Filers (CELH Series A/B preferred, PG common stock, others) render the equity row label cell with inline memo `ix:nonFraction` tags (par value, shares issued, shares outstanding) embedded in the descriptive prose: "Series A convertible preferred stock, $0.001 par value per share, 1,467 shares issued...". Walker now partitions row cells by content shape — cells with text+ix where text isn't pure numeric are LABEL CELLS (memo facts inside), cells with ix where text is num/`$`/dash are VALUE CELLS (primary fact). Label-cell ix tags emit as separate `row_type="memo"` line items with synthesized "{row prefix} - {CamelCase concept}" labels, skip library lookup entirely (no spurious fuzzy matches), and route through reconcile's `_memo` passthrough.

### 8. Reconcile `_memo` passthrough
New path 4 in `reconcile_item`: row_type="memo" items that don't match a library entry route to `model_sheet="_memo"` (parallel to `_subtotal`) instead of surfacing as novels. Memo rows (par value, shares issued, dividend percentage, redemption requirement) are informational — they're not part of any subtotal and shouldn't block the pipeline.

### 9. Multi-cell paren detection
Modern 10-Q renderer (CELH 2023-Q1+) splits accounting parens across `<td>` siblings: `<td>(</td><td>VALUE</td><td>)</td>`. Walker's previous `_is_parens_negative` only walked ancestors within ONE cell, so it missed these. Rewritten to handle 4 patterns:
  - **(A)** Single-cell parens-in-text: `<td>(<ix>VALUE</ix>)</td>` (older 10-Ks).
  - **(B)** Single-cell parens-as-sibling-spans: `<span>(</span><span><ix>VALUE</ix></span><span>)</span>`.
  - **(C)** Multi-cell: `<td>(</td><td><ix>VALUE</ix></td><td>)</td>` (modern 10-Q).
  - **Hybrid**: open paren in one cell, close paren in another.
Plus leading currency-symbol stripping (`$ ( 1,278,691 )` matches Pattern A after stripping `$ `). Detection is universal; CF values get visual-sign-as-rendered, BS/IS additionally apply library `sign_convention` overlays per the user's clarification.

### 10. Multi-table cross-filing dedup boundary fix
Cross-filing CF section tie-out check was failing on `2025-12-31 investing` with gap = -1,278,769 (the Alani Nu acquisition value, exactly doubled). Root cause: legacy `validated_2025_FY.json` (underscore-named, from prior session) co-existed with new `validated_2025-FY.json` (hyphen-named); both got globbed into `--in` args, and `aggregate_cell_totals` per-(sheet, row, period, fdate) sum doubled the FY2025 contribution. Removed all `validated_*_*.json` (underscore names) from Model Output.

### 11. IS cascade validators IS-1 / IS-2 / IS-3 / IS-5
Per user directive: "There should be a Pydantic validation that compares Net Income calculated to Net Income found on the HTML file for the respective period". Added 4 new rules to `validate.py`:
  - **IS-1**: Gross Profit = Revenue + Σ(cost items, signed-as-expense)
  - **IS-2**: Income from Operations = GP + Σ(opex, signed-as-expense)
  - **IS-3**: Pre-Tax = Op Income + Σ(non_operating, signed)
  - **IS-5**: End-to-end Net Income = Revenue − cost − opex + non_op + tax, ties to filer-rendered NI canonical
The Distributor Termination Fees sign issue (filer renders +327,461 expense, was being added to OpInc instead of subtracted) would be caught by IS-2. Validate now runs 14 rules per filing instead of 10.

### 12. Convertible preferred → Equity fold at model-write
Per user directive: "convertible preferred stock should be a part of stockholders' equity for all companies if applicable". Walker keeps section=mezzanine (faithful to filer rendering — validate's BS-5 ties cleanly to filer's TSE which excludes mezzanine). Model-write's BS layout buckets `mezzanine` items into `equity` so the workbook shows convertible preferred under SE. Library `GEN-BS-027 Convertible Preferred Stock` augmented with concept-name aliases (`temporary equity carrying amount attributable to parent`, `series b convertible preferred stock`, `redeemable preferred stock value`) but does NOT carry `filing_section` (would override walker section, breaking BS-5).

### 13. Net Change in Cash always-present subtotal
Per user directive: "We are missing sum of cash flow effect which should be a subtotal column (regardless of whether or not it is shown in the company's filings) that sums all CF sections". Model-write now synthesizes a "Net Change in Cash" row at the bottom of the CF section if no filing emitted it, with formula `=CFO+CFI+CFF+CashOther`. Validate's CF-1 validator now ties cleanly across the fleet.

### 14. CELH ledger updates (3 new entries)
- `NEW-IS-001 Distributor Termination Fees`: section=operating_expenses, sign_convention=negative (filer renders +327,461; flipped to -327,461 for IS-cascade subtraction).
- `NEW-CF-MZ-PFV` carry-through (existing).
- `STRUCT-IS-002` carried (advisory note about historical Sales & Marketing classification).

### 15. Library updates (3 new generic entries + alias widening)
- `GEN-CF-056 Other Financing Activities` (CELH's "Other financing activities-net" was fuzzy-matching `Other Investing Activities` GEN-CF-043 with wrong section).
- CFO / CFI / CFF subtotal aliases widened with the `(used in) provided by` parenthetical phrasing CELH uses on early Q1/Q2 filings — fixes section-collision where one rule_id matched multiple sections.
- `GEN-BS-027` aliases (Temporary Equity carrying-amount, Series B preferred).

## Current state

- **CELH 12 filings**: 0 novels / 0 validate fails / 0 warnings on every filing. 28 rules pass on 10-Ks (BS-1..5 × 2 instants + IS-1..5 × 3 periods + CF-1..4 × 3 periods − warns), 22 rules on 10-Qs (fewer comparative periods).
- **`CELH_model.xlsx`**: 1,182 cells. ANNL P&L 16 rows × 5y, BS 44 × 4 instants, CF 47 × 5y, QTR P&L 16 × 12q, QTR BS 43 × 12q, QTR CF 45 × 12q.
- **`feedback_cf_visual_sign.md` re-confirmed**: zero CF library entries carry `sign_convention` overlay (audited). Paren-detection is the SOLE sign authority for CF; BS/IS additionally layer library overlays.
- **PG**: untouched — last clean run was prior session.
- **Library**: 119 → 122 entries (+ aliases on existing).
- **CELH ledger**: 19 entries (was 18; added NEW-IS-001).

## Open decisions / pending work

1. **NEXT SESSION OPENS WITH: PG 14-filing regression on the new HTM-walker.** Confirm the rewrite holds across PG (3 10-Ks + 11 10-Qs). PG is the canonical "filer that breaks every assumption" — Q2/Q3 FY2024 visual-ordering, ESOP reserve, redeemable preferred, etc. If PG re-validates clean, the architecture is generalized; if not, surface the remaining filer-quirks before onboarding a third ticker.
2. **Onboard a third ticker (PEP or KO)** after PG re-validation. Goal: confirm one-page onboarding flow holds — mkdir ticker root, drop config.json, run extract→reconcile→validate→model-write, surface novels for triage.
3. **OCI 4th-statement build** — still carried. Walker currently STOPS on OCI header in combined IS+CI tables; emit them as their own `StatementType.COMPREHENSIVE_INCOME` once that StatementType exists in the schema.
4. **`_pre.xml` linkbase** — drop entirely from `ixbrl_path.py` once PG also passes (current code keeps it commented-out / unimported but a cleanup pass would be cleaner). Per `feedback_no_rfiles_for_financials.md`.
5. **Refresh playgrounds + LS_KEY v9 → v10** — `playground_architecture.html` still shows R-file nodes feeding the iXBRL extractor; that node graph + scaffolding text needs to update for HTM-only walking. `playground_schema.html` doesn't change. Carried per active propagating rule.
6. **`financials-validate/SKILL.md` description** — still says "BS-1..BS-5, IS-4, CF-1..CF-4 — 10 filer-tie rules". Update to "14 filer-tie rules: BS-1..5, IS-1..3 + IS-5, IS-4 (NI=PT+tax), CF-1..4". Add IS-1..3+IS-5 cascade rationale.
7. **Extend `model-calc` to quarterly drivers** — annual-only today.
8. **Extract `pattern_libraries/generic_forecast_rules.json`** from `calc.py`. Blocked on §7.
9. **`CELH_model.xlsx`** ANNL columns FY2021–FY2025 + 6 forecast cols are pre-allocated empty for `model-calc` to fill. Run model-calc once PG generalization is confirmed.
10. **CELH 2023-Q1 BS-5 fix** — the multi-cell paren fix resolved the CF subtotal sign issues that were blocking validate; it now passes. Carry: confirm no PG regression from the new paren detection.
11. **Memory rule additions to consider** —
    - "convertible preferred → equity fold at model-write layout, not at extract section" (the walker faithfully renders mezzanine; the layout consolidates).
    - "Net Change in Cash subtotal must always synthesize in the workbook" (per user directive).
    - "CF rows: paren-detection only; BS/IS rows: paren-detection + library sign_convention overlay" (the user's clarification).

## Key file paths

| Purpose | Path |
|---|---|
| This handoff | `Brain\Sessions\CELH Model\Handoffs\April 26th HTM Walker Build-Out + 12 Filing Clean Session.md` |
| Prior handoffs | `Brain\Sessions\CELH Model\Handoffs\Archive\` |
| Roadmap | `Brain\Sessions\CELH Model\ROADMAP.md` |
| iXBRL extractor (HTM walker) | `~\.claude\skills\financials-extract\scripts\ixbrl_path.py` |
| Reconcile (`_memo` passthrough added) | `~\.claude\skills\financials-reconcile\scripts\reconcile.py` |
| Validate (IS-1..3 + IS-5 added) | `~\.claude\skills\financials-validate\scripts\validate.py` |
| Model-write (mezz→equity fold + NetChange synth + `_memo` filter) | `~\.claude\skills\model-write\scripts\write.py` |
| Lookup module | `Brain\Knowledge\Model Schema\financials-schema\financials_schema\lookup.py` |
| Generic library (122 entries) | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` |
| CELH ledger (19 entries; NEW-IS-001 added) | `Brain\Knowledge\Model Schema\CELH\decisions_ledger.json` |
| CELH source filings | `Brain\Sources\CELH\{2023-FY..2025-FY,2023-Q1..2025-Q3}\filings\` |
| **CELH built workbook** | `Brain\Knowledge\Model Schema\CELH\Model Output\CELH_model.xlsx` |
| CELH ValidatedFilings (12 files) | `Brain\Knowledge\Model Schema\CELH\Model Output\validated_*.json` |
| CELH intermediates | `Brain\Knowledge\Model Schema\CELH\Model Output\.cache\` |
| PG canonical workbook (untouched) | `Brain\Knowledge\Model Schema\PG\Model Output\PG_model_v15.xlsx` |
| Playground (needs node-graph update post-rewrite) | `Brain\Knowledge\Model Schema\playground_architecture.html` |

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
