---
type: session-handoff
date: 2026-04-27
topic: Onboarded PEP (PepsiCo) end-to-end as the third ticker through the post-Tier-C-hardened framework — 13 filings (3 10-Ks + 10 10-Qs since FY2023) reach 0 novels and 0 validate fails; framework picked up two new structural rules along the way (validators trust as-mapped values, cascade-injection skips already-rendered anchors); harness now locks CELH (12) + PG (14) + PEP (13) = 39 filings.
tags: [session, pep-onboarding, third-ticker, no-validator-sign-flips, no-duplicate-anchor-subtotals, regression-harness]
---

# April 27th — PEP Onboarding Session

Picks up from `Archive\April 27th Tier C Heuristic Hardening Sprint Session.md` (Tier C sprint shipped the snapshot harness + concept-fallback + NCI detection + presentation-linkbase subtotal detection). This session validates the hardened framework against a third ticker — PEP — and shipped two additional structural fixes prompted by what PEP's filings exposed. Next session opens with rebuilding `model-calc` to cover quarterly drivers + line-item-type-aware driver inference (see Open §1).

## Starting state

- CELH (12 filings) + PG (14 filings) clean; Tier C hardening sprint complete; snapshot regression harness locked.
- Generic library 121 entries, 91 declaring `us_gaap_concept`.
- No-heuristic policy active per `feedback_structural_over_heuristic.md`.
- No PEP folder, no PEP source filings on disk beyond pre-existing `2026-Q1\transcripts\`.

## Work done this session

### 1. PEP source pull + ticker scaffold

Ran `sec-edgar-fetch --ticker PEP --all --since 2023-01-01 --forms 10-K,10-Q` → 13 filings to `Brain\Sources\PEP\` (3 10-Ks FY2023/FY2024/FY2025 + 10 10-Qs Q1-Q3 of FY2023/FY2024/FY2025 + Q1 FY2026), plus `companyfacts.json`. Scaffolded `Brain\Knowledge\Model Schema\PEP\` with `config.json` (CIK 0000077476, NASDAQ, 52/53-week FYE last Sat of December, $millions, expected ranges 85-100B revenue / 90-110B TA), empty `decisions_ledger.json`, empty `anomalies.json`. The four most recent filings lack SEC-generated `Financial_Report.xlsx` (still pending publication) but the iXBRL extractor reads HTM directly so this didn't block.

### 2. Generic library widening (Path B template applied 8 times)

Per `feedback_structural_over_heuristic.md`, replaced fuzzy alias gaps with structural concept-fallback widenings on existing canonicals: GEN-BS-035 Treasury Stock (+`TreasuryStockValue`), GEN-BS-038 Inventories memo bucket (+3 inventory sub-concepts), GEN-BS-016 Accrued Expenses (+`AccountsPayableAndAccruedLiabilitiesCurrent`), GEN-BS-041 Long-Term Debt (+`LongTermDebtAndCapitalLeaseObligations`), GEN-BS-032 Short-Term Debt → "Short-Term Debt Obligations" rename (+`ShortTermBorrowings` concept), GEN-BS-003 Accounts Receivable (+`AccountsNotesAndLoansReceivableNetCurrent`), GEN-IS-006 Interest Income (Expense) (+`InterestExpense` concept), GEN-CF-008 Deferred Tax (+`DeferredIncomeTaxesAndTaxCredits`), GEN-CF-014 Accounts Payable (+concept), GEN-CF-024 Purchase of PP&E (+`PaymentsToAcquireProductiveAssets`), GEN-CF-042 Acquisitions (+`PaymentsToAcquireBusinessesAndInterestInAffiliates`), GEN-CF-043 Other Investing (+`PaymentsForProceedsFromOtherInvestingActivities`), GEN-CF-048 Repayments of LT Debt (+`ProceedsFromRepaymentsOfOtherLongTermDebt`), GEN-IS-012 Intangible Assets (+`FiniteLivedIntangibleAssetsNet` + `IndefiniteLivedIntangibleAssetsExcludingGoodwill`). Required schema widening on `LibraryEntry`: new optional `us_gaap_concepts: list[str]` field paired with the existing singular `us_gaap_concept`; `build_concept_index` iterates both. Per `feedback_structural_over_heuristic.md`.

### 3. Generic library — new canonicals (12)

GEN-BS-044 Short-Term Investments, GEN-BS-046 Net PP&E memo (gross + accumulated depreciation, per Group 3 user decision to render only Net), GEN-BS-047 Equity Method Investments. CF: GEN-CF-057 reframed as "Net Change in Short-Term Investments" (option B — single rolled-up canonical, four sub-concepts collapse to one workbook row), GEN-CF-058 Operating Lease ROU Asset Amortization, GEN-CF-059 Pension Expense, GEN-CF-060 Pension Contributions, GEN-CF-061 Restructuring Charges, GEN-CF-062 Cash Payments for Restructuring, GEN-CF-063 Tax Withholdings on RSU/PSU Settlement, GEN-CF-064 Payments of Contingent Consideration, GEN-CF-065 Proceeds from Divestitures, GEN-CF-066 Acquisition/Divestiture-Related Charges, GEN-CF-067 Cash Payments for Acquisition/Divestiture, GEN-CF-068 ROU Assets Obtained for Lease (memo). IS: GEN-IS-025 Other Pension and OPEB Benefits Income/Expense (ASC 715-20 non-service-cost line), GEN-CI-001 Other Comprehensive Income (Loss) memo bucket (stop-gap until §21 OCI 4th statement build).

### 4. PEP ticker ledger — 11 filer-specific entries

`PEP-IS-001` Gain on Juice Transaction (filing_section=non_operating per us-gaap concept), `PEP-CF-001..010` for Juice Transaction CF lines, Product Recall, TCJ Act payments/expense, Impairment and Other Charges (`pep:` namespace), Indirect Tax Impact, Debt Discharged via Legal Defeasance (memo), Investment Obtained for Celsius Stake (memo). All use modern `aliases` list field (not legacy `filing_term_normalized`).

### 5. Reconcile improvement — ticker-ledger row_type override

`reconcile.py` previously didn't apply ticker-entry `row_type` to the mapped item — only sign_convention and section. Extended override block to also set row_type when declared. Required for filer-specific supplemental disclosures like PEP's `Debt Discharged via Legal Defeasance` ($94 in Q2 FY2023) declared `memo: true, row_type: "memo"` in the ledger but which previously rendered as `line_item` and broke CF-1 by $94.

### 6. Match-order swap — concept before fuzzy

Swapped `match_raw_item` order from `exact → fuzzy → concept` to `exact → concept → fuzzy`. PEP's gross PP&E label "Property, plant and equipment" fuzzy-matches GEN-BS-007 Net PP&E (alias "property, plant and equipment, net" at 0.92), even though `PropertyPlantAndEquipmentGross` concept declares it belongs on GEN-BS-046 memo. With concept-before-fuzzy, the deterministic XBRL signal beats label fuzz. CELH+PG harness 0 diffs.

### 7. Validator IS-2 / IS-5 — drop `-abs()` force-flip (per user "without adding a heuristic")

PEP's FY2022 Juice line `(3,321)` (parens-negative) lives in the opex bucket per filer rendering. The IS-2 validator's `opex_signed = sum(-abs(o.value))` force-flipped it to -3,321 in the opex sum, treating a gain as an expense and double-counting. Replaced with `sum(-o.value)` — trust as-mapped values; sign correctness lives at extract+library+ledger, not at validate. CELH+PG harness 0 diffs (extract was already correctly signing every opex row). Per `feedback_no_validator_sign_flips.md`.

### 8. model-write cascade injection — global anchor lookup, not 4-row look-back

PEP-IS-001 Juice (declared non_operating but rendered between SG&A and Impairment) tripped a 4-row look-back guard in cascade injection: section walker observed `op_exp → non_op (Juice) → op_exp (Impairment)` as a fake transition, force-injected an Income from Operations cascade BEFORE Juice, then dedup-merged the cascade-injected IFO with the filer's real IFO at the wrong row. Replaced 4-row look-back with global already-rendered set lookup: skip injection for any cascade label the filer already rendered ANYWHERE in document order. CELH+PG harness 0 diffs. Per `feedback_no_duplicate_anchor_subtotals.md`.

### 9. PEP regression harness bootstrap

Extended `_regression\run.py` `WORKBOOK_FILENAME` and `--ticker` choices to include PEP. Bootstrapped from a model-write-only xlsx (`model-calc` skipped, since CELH/PG goldens are model-write-only — model-calc forecasts would diff against an empty fresh-pipeline run). Re-extracted PEP raw_*.json from `C:\Users\rodin\` cwd so source_path stores as `Desktop\Brain\Sources\PEP\...` (USER_HOME-relative, matching CELH/PG convention). Final state: ALL CLEAN across CELH (12) + PG (14) + PEP (13).

### 10. Memory rules saved

`feedback_no_validator_sign_flips.md` and `feedback_no_duplicate_anchor_subtotals.md` — both indexed in MEMORY.md.

## Current state

- **Harness**: CELH 12 + PG 14 + PEP 13 = 39 filings clean. 0 novels, 0 validate fails, 0 harness diffs.
- **Library**: 121 → 137 entries. New `us_gaap_concepts` plural field. Match order is exact → concept → fuzzy.
- **Validator**: IS-2 / IS-5 trust as-mapped values (no force-flip).
- **model-write**: cascade injection uses global anchor lookup, not 4-row look-back. Ticker-ledger row_type override applies.
- **PEP workbook**: `PEP_model_v3.xlsx` (model-write only — no model-calc). 1,415 cells. All 6 sheets present + QTR family.
- **Memory**: 2 new feedback rules.

## Open decisions / pending work

1. **NEXT SESSION OPENS WITH**: rebuild `model-calc` from scratch with quarterly support + line-item-type-aware driver inference. The current model-calc is annual-only and has hand-curated driver specs. The new design should: (a) emit drivers for QTR sheets too, with quarterly-appropriate ratios; (b) infer driver type from line-item type/section (revenue → growth; opex → % of revenue; AR/AP/Inventory → days ratio; PP&E → rollforward; etc.) so adding a new ticker doesn't require new driver specs; (c) keep IS/BS/CF intertwined so a forecast change in one sheet flows through to the others via formulas, not duplicated assumptions.
2. **Active propagating rule** (carry every handoff): playground-sync. `playground_architecture.html` + `playground_schema.html` both need updates for: `us_gaap_concepts` plural field (LibraryEntry schema), match-order swap (concept before fuzzy), validator no-abs(), cascade global anchor lookup, ticker-ledger row_type override, concept-fallback on inventory/treasury/PP&E memo buckets. Bump LS_KEY v9 → v10.
3. **No-heuristic policy** (active propagating rule per Tier C 2026-04-27). Carry every handoff.
4. **OCI 4th statement build** — still deferred; OCI items currently absorbed by GEN-CI-001 memo bucket as a stop-gap. Replace when `StatementType.COMPREHENSIVE_INCOME` ships.
5. **`financials-validate/SKILL.md` description stale** — still says "10 filer-tie rules". Now 14 + the no-abs() change in IS-2/IS-5.
6. **PEP source_path convention.** PEP raw_*.json files now use `Desktop\Brain\Sources\PEP\...` USER_HOME-relative paths (matching CELH/PG). If extract is re-run from a different cwd, harness source discovery breaks — same lesson learned this session.

## Key file paths

| Purpose | Path |
|---|---|
| This handoff | `Brain\Sessions\CELH Model\Handoffs\April 27th PEP Onboarding Session.md` |
| Prior handoffs | `Brain\Sessions\CELH Model\Handoffs\Archive\` |
| Roadmap | `Brain\Sessions\CELH Model\ROADMAP.md` |
| **Regression harness** | `Brain\Knowledge\Model Schema\_regression\run.py` (now: CELH/PG/PEP) |
| **PEP ticker root** | `Brain\Knowledge\Model Schema\PEP\` (config.json + decisions_ledger.json with 11 entries + anomalies.json) |
| **PEP filings (13)** | `Brain\Sources\PEP\{2023-FY,2023-Q1..Q3,...,2026-Q1}\filings\PEP_*.htm` |
| **PEP workbook (model-write only — harness golden)** | `Brain\Knowledge\Model Schema\PEP\Model Output\PEP_model_v3.xlsx` |
| Lookup module (us_gaap_concepts plural, match-order swap) | `Brain\Knowledge\Model Schema\financials-schema\financials_schema\lookup.py` |
| Validate module (no-abs IS-2/IS-5) | `~\.claude\skills\financials-validate\scripts\validate.py` |
| Reconcile module (ticker row_type override) | `~\.claude\skills\financials-reconcile\scripts\reconcile.py` |
| Model-write (global anchor lookup) | `~\.claude\skills\model-write\scripts\write.py` |
| Generic library (137 entries, +new BS/CF/IS canonicals) | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` |
| Memory: no validator sign flips | `~\.claude\projects\C--Users-rodin\memory\feedback_no_validator_sign_flips.md` |
| Memory: no duplicate anchor subtotals | `~\.claude\projects\C--Users-rodin\memory\feedback_no_duplicate_anchor_subtotals.md` |
| Playgrounds (need LS_KEY v9 → v10) | `Brain\Knowledge\Model Schema\playground_{architecture,schema}.html` |

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
