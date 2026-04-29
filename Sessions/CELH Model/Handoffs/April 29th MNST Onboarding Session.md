---
type: session-handoff
date: 2026-04-29
topic: MNST onboarded as 4th ticker (20 filings, BS gap $0); accepted_sections opt-in framework + cross-section displacement in workbook tie-out; PLUG_LABELS generalization for residual plug; validate "skip" severity for filer-doesn't-disclose anchors; BS-5 TSE pattern loosened for filer-prefixed labels; snapshot harness expanded to 4 tickers + goldens re-locked. Three new memory rules saved.
tags: [session, mnst-onboarding, accepted-sections, plug-labels, validate-skip, snapshot-harness, four-ticker-clean]
---

# April 29th — MNST Onboarding Session

Picks up from `Archive\April 28th Forecast UX & Subtotal Hardening Session.md`. This session onboarded MNST (20 filings, 0 novels, 0 fails, BS gap $0) and fixed three architectural gaps the 3-ticker corpus hadn't exposed: cross-section canonicals where filer disagreement is structural, residual-plug detection assuming one canonical label, and filer-doesn't-disclose warnings polluting validation. All fixed structurally, no label-text heuristics. Next session opens with **inventory breakdown** — split RM / WIP / FG into separate workbook line items where filers disclose them (PG full breakdown, PEP partial; both currently collapsed).

## Starting state

- 3 tickers (CELH/PEP/PG) BS-tied at $0; library 137 entries; snapshot harness 39-filing baseline.
- MNST `Brain\Sources\MNST\` had 2025-Q4 transcript only; no ticker library yet.
- TSE pattern in `validate.py` only matched plain prefix — would miss filer-name-prefixed labels (PEP).

## Work done this session

### 1. MNST data ingest + novel triage

`sec-edgar-fetch --ticker MNST --forms 10-K,10-Q --all --since 2021-01-01` pulled 20 filings (5 10-Ks FY2021–FY2025 + 15 10-Qs). Ticker library scaffolded at `Knowledge\Model Schema\Ticker Libraries\MNST\` (Dec FYE, $thousands, `growth_basis: "yoy"`, 2-for-1 split 2023-02-23). First reconcile dry-run surfaced 54 unique novel labels (288 total occurrences); triaged per `feedback_novel_triage_protocol.md` into 4 groups before any library writes — library gaps for universal CPG concepts (~14), MNST-specific one-time events (5), OCI items folded into IS, and Common Stock par-value-with-shares label clutter (fixed structurally via `CommonStockValueOutstanding` concept on GEN-BS-028).

### 3. Library expansion (137 → 146 entries) + ticker ledger

8 new canonicals: GEN-BS-048 Long-Term Investments, GEN-BS-049 Accrued Compensation, GEN-BS-050 Prepaid Income Taxes, GEN-IS-026 Operating Expenses (single-line for filers without SG&A/R&D breakdown), GEN-CF-069 Additions to Intangibles, GEN-CF-070 Net Change in Long-Term Investments, GEN-CF-071 Impairment of Long-Lived Assets (PP&E), GEN-CF-072 Change in Accrued Compensation, GEN-CF-074 Change in Prepaid Income Taxes. GEN-CF-058 renamed/merged → "Non-Cash Lease Expense" with `mnst:NonCashLeaseExpense` + ROU concepts unified. Concept additions to ~12 existing canonicals. MNST ticker ledger: 6 `new_rows` for one-time events (CANarchy / Bang / Brewing acquisitions + Bang IS gain non-cash add-back + 2 distributor restructuring lines).

### 4. Prepaid Income Taxes — separate canonical, not absorbed

User initially confirmed routing `Prepaid income taxes` (CA) into GEN-BS-008 DTA (NCA) via `accepted_sections=["current_assets"]`. After workbook tie-out surfaced ~$30–90K CA/NCA gap, user reverted: "if it's a current asset it should not be dropped into an NCA row." Split into standalone GEN-BS-050 (CA) + GEN-CF-074 (CF op). Sets the precedent: cross-section absorption is for memo rows only; live rendered rows where filer-section preservation matters get their own canonical.

### 5. `accepted_sections` opt-in framework

Added `LibraryEntry.accepted_sections: list[Section]` (`financials_schema/lookup.py:204`). Reconcile's section-collision guard skips opted-in rule_ids. Model-write `_compute_section_displacement` walks items and tracks per-(sheet, period, section) net inflow when filer-section ≠ canonical-row-section; `validate_workbook_ties` adds the displacement to expected per-section sums so BS-1 / BS-2 / TLSE ties hold. Currently used only on GEN-CF-038/039 supplemental cash (memo, accept both `operating` and `cash_other`). Per `feedback_accepted_sections_optin.md`.

### 6. PLUG_LABELS generalization + cf_delta_target wiring

model-calc's residual plug used to require label `== "Other Operating Items"`. MNST uses GEN-CF-051 "Net Change in Other Working Capital" instead. Forecast BS gap grew $5.7K → $303K. Added `PLUG_LABELS = {"Other Operating Items", "Net Change in Other Working Capital"}`; either now absorbs ΔBS. Plus wired `cf_delta_target` on GEN-BS-048/049/050 → their CF counterparts. Result: MNST BS gap = $0 across all 20 forecast quarters. Per `feedback_plug_label_set.md`.

### 7. Validate severity "skip" for filer-doesn't-disclose

71 inconclusive warnings (PG IS-1 ×31, MNST BS-4 ×40) reflected filer reporting choices, not regressions. Extended `Severity = Literal["pass","warning","fail","skip"]`. `_skip()` helper distinct from `_inconclusive`; BS-4 + IS-1 downgraded when filer omits the anchor. **0 warnings across 59 filings; 71 skips properly categorized.** Per `feedback_skip_severity_filer_disclosure.md`.

### 8. BS-5 TSE pattern loosened + IS-006/008 disambiguation

PEP's `Total PepsiCo Common Shareholders' Equity` (filer name in middle) was missed by the prefix-only TSE pattern; loosened `_classify_subtotal` to accept any subtotal ending in `" stockholders equity"` or `" shareholders equity"`, plus exact `"total equity"` (PEP's all-equity incl-NCI). TLSE check kept distinct via `startswith("total liabilities and ")`. Removed 26 PEP BS-5 warnings. Separately, MNST Q3 FY2025 vs FY2025 10-K used different filer labels for the same combined-interest-and-other line; removed conflicting aliases from GEN-IS-006 so all variants route to GEN-IS-008 via concept (structural beats fuzz).

### 9. Sources cleanup + snapshot harness expansion

Moved MNST `2025-Q4/transcripts/MNST_2026-02-26_press_release.pdf` → `2025-FY/transcripts/`; removed duplicate `2025-Q4` folder. Snapshot harness updated: MNST added to `WORKBOOK_FILENAME` and `--ticker` choices; workbook filenames simplified (`CELH_model_v5.xlsx` → `CELH_model.xlsx`, etc.); MNST raw_*.json re-extracted with absolute source paths (originally relative — broke `USER_HOME / rel` resolution). `python run.py --accept` locked new goldens; clean diff confirmed.

## Current state

- **CELH**: 12 filings, 363 pass / 0 warn / 0 fail / 0 skip. BS gap $0.
- **PEP**: 13 filings, 365 pass / 0 warn / 0 fail / 0 skip. BS gap $0.
- **PG**: 14 filings, 357 pass / 0 warn / 0 fail / 31 skip (IS-1 GP not rendered). BS gap $2 (rounding).
- **MNST**: 20 filings, 525 pass / 0 warn / 0 fail / 40 skip (BS-4 TL not rendered). BS gap $0.
- **Library**: 146 entries.
- **Snapshot harness**: 4 tickers locked (CELH 12 + PG 14 + PEP 13 + MNST 20 = 59 filings); `python run.py` returns ALL CLEAN.

## Open decisions / pending work

1. **NEXT SESSION OPENS WITH** — inventory breakdown. Split RM / WIP / FG into separate workbook line items where filers disclose them (PG full breakdown, PEP partial — both currently collapsed into GEN-BS-038's memo bucket). Plan: 3 new BS canonicals as line_items, model-write conditional layout (Net renders as `=SUM(detail)` subtotal when detail present, else single line_item), BS-1 subtotal-exclusion already exists, model-calc forecast (RATIO_OF_REV per detail). Estimated ~3–5 hours including regression.
2. **After inventory** — resume systematic driver-kind determination (replace `_label_contains` substring checks in `inference.py` with structural canonical metadata).
3. **TickerLedgerEntry validator** (carried) — Pydantic model for per-ticker `decisions_ledger.json` to close the silent-typo gap.
4. **Playground sync owed** — `accepted_sections`, `_compute_section_displacement`, PLUG_LABELS, `_skip` severity, BS-5 pattern. `playground_architecture.html` + `playground_schema.html` need refresh; LS_KEY v13 → v14.
5. **Active propagating rules** carried: playground sync, no-heuristic policy, no validator sign flips, no duplicate anchor subtotals, joint regression now expanded to **4 tickers** (CELH+PG+PEP+MNST).

## Key file paths

| Purpose | Path |
|---|---|
| This handoff | `Brain\Sessions\CELH Model\Handoffs\April 29th MNST Onboarding Session.md` |
| Prior handoff (archived) | `Brain\Sessions\CELH Model\Handoffs\Archive\April 28th Forecast UX & Subtotal Hardening Session.md` |
| Roadmap | `Brain\Sessions\CELH Model\ROADMAP.md` |
| MNST ticker root (config + ledger 6 entries + 20 validated_*.json) | `Brain\Knowledge\Model Schema\Ticker Libraries\MNST\` |
| MNST workbook | `Brain\Knowledge\Model Outputs\MNST\MNST_model.xlsx` |
| Generic library (146 entries) | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` |
| LibraryEntry schema (accepted_sections field) | `Brain\Knowledge\Model Schema\financials-schema\financials_schema\lookup.py:204` |
| ValidatedFiling Severity (skip added) | `Brain\Knowledge\Model Schema\financials-schema\financials_schema\validated.py:9` |
| reconcile collision opt-out | `~\.claude\skills\financials-reconcile\scripts\reconcile.py:528-546` |
| model-write displacement adjustment | `~\.claude\skills\model-write\scripts\write.py` (`_compute_section_displacement`, `validate_workbook_ties`) |
| model-calc PLUG_LABELS | `~\.claude\skills\model-calc\scripts\inference.py:386` |
| validate _skip + TSE pattern | `~\.claude\skills\financials-validate\scripts\validate.py` (`_classify_subtotal`, `_skip`, `run_bs4`, `run_is1`) |
| Snapshot harness (4 tickers) | `Brain\Knowledge\Model Schema\_regression\run.py` (goldens at `_regression\goldens\{TICKER}\`) |

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
