---
type: session-handoff
date: 2026-05-20
topic: Shipped the pre-iXBRL XBRL-XML extractor path in financials-extract, fixed the workbook-wide units normalization bug that left CELH's 2020-2021 columns at 1000x scale, triaged the 2020-era novels, rebuilt the CELH model with ANNL P&L and BALANCE SHEET aligned to FY2019 (fixing the original BS-starts-FY2022 misalignment and the missing Q4 FY2020 quarter); CASH FLOW backfill blocked at FY2021 by a $127K self-inconsistency in the 2020 10-K's XBRL.
tags: [session, celh-backfill, ixbrl-xml-extractor, units-normalization, novel-triage, model-rebuild, framework-regression-pending]
---

# May 20th — Pre-iXBRL Backfill + Units Fix Session

Prior handoff: `Archive\May 18th Transcript-KPI Skill Build Session.md`. Back to the financials pipeline after the transcript detour. User opened with "something is busted" on `CELH_model.xlsx` (visible symptom: negative Q4 FY2021 revenue); the root cause was framework-wide (no unit normalization across the pipeline) and the deeper need was the pre-iXBRL backfill the May 11 handoff had deferred. Next session: run the **CELH+PG+PEP+MNST joint regression** against the changes shipped here before locking, and decide whether to chase the FY2019/FY2020 CASH FLOW gap (a filer XBRL inconsistency, not an extractor bug).

## Starting state

- `CELH_model.xlsx`: ANNL P&L + CASH FLOW started FY2021, BALANCE SHEET started FY2022 (misaligned by one year); YTD sheets had **4 columns at 1000× scale** because CELH's 2020-2021 10-Qs were filed in whole dollars and the framework didn't normalize; Q4 FY2020 missing entirely from QTR P&L / QTR CF.
- 17 validated filings (2021-Q2 → 2025-FY). Pre-iXBRL filings (FY2020 10-K, all 2020 10-Qs, 2021-Q1 10-Q, FY2021 10-K) blocked — `financials-extract`'s iXBRL HTM path returns zero statements on them (the May 11 handoff and `project_celh_ixbrl_boundary.md` flagged this as needing a new extractor + its own session).
- Source HTM + `.meta.json` for every backfill filing already cached locally under `Brain\Sources\CELH\{period}\filings\`.

## Work done this session

### 1. Units-normalization bug — root cause + fix
Validated JSONs carry the filer's scale per `Statement.unit` (`actual`/`thousands`/`millions`/`billions`). `collect_writes` was reading `item.value` raw without consulting `stmt.unit` — so CELH's 2021-Q2/Q3 (filed `actual`) landed 1000× too large, and PG/PEP (filed `millions`) silently sat at millions in workbooks labelled thousands. Fixed via `_scaled_value(item, stmt)` (skips EPS/share rows) routed through all 3 read sites: `collect_writes`, `_collect_filer_subtotals`, `_collect_filer_mezzanine_sums`. The workbook's canonical scale is now uniformly THOUSANDS. `CF_TIE_OUT_WARN_MIN` / `_ERROR_MIN` rescaled to 2000 / 4000 thousand-units (were calibrated against the implicit-millions assumption). Existing `CELH_model.xlsx` got a surgical 363-cell ÷1000 patch before the rebuild superseded it.

### 2. `xbrl_xml_path.py` — new third extractor path
Sibling of `ixbrl_path.py` / `pdf_path.py`, same `RawFiling` output. Reads standalone XBRL instance + `_pre.xml` + `_lab.xml` from `.cache/ixbrl_reports/{accession_nodash}/`. Sections assigned **once per presentation role** (not per period — comparative periods can omit a transition subtotal) by a concept-keyed `_SECTION_TRANSITIONS` table per `StatementType` — purely structural, no label regex. Sign handling follows `preferredLabel=negatedLabel`. OCI rows dropped via `_is_oci_concept`; net-change-in-cash forces row_type=subtotal and tags everything after as `memo`. Concept-level dedup per statement (SEC-generated `_htm.xml` instances point multiple locators at one concept). Wired into `extract.py` via auto-routing (`<ix:` tag count) + `--path xbrl-xml` override for iXBRL 10-Ks whose HTM defeats `find_primary_tables`. Verified clean on all 6 backfill filings.

### 3. Novel triage — 24 → 0
24 unique novels from the 6 new filings (CELH's 2020-era chart). Cross-ticker-safe items aliased onto existing canonicals: `GEN-IS-006` (interest), `GEN-IS-007` (FX), `GEN-CF-004` (bad-debt), `GEN-CF-035` (net-change), `GEN-CF-042` (acquisition payments), `GEN-CI-001` (OCI). `GEN-CI-001` opted into `accepted_sections=[non_operating, post_ni_deduction, equity]` (OCI rows land in either non_operating or post_ni_deduction depending on the filer's NI placement on combined IS+CI roles). CELH quirks went into the ticker ledger (per `feedback_novel_triage_protocol.md`): 6 mappings (amortization of intangibles/financial leases + China note-repayment → Other Income (Expense); European deferred tax → Income Tax) and 3 new_rows (Bonds Payable Net; Proceeds from Related-Party Notes; Cash Paid for RSU Tax Withholding). `NEW-CF-101` got `accepted_sections=[financing, investing]` (CELH reclassified the related-party proceeds across filings) — required a one-line `reconcile._register` fix to propagate `accepted_sections` for ticker entries.

### 4. CF data-quality gates — two filings' CF surgically dropped
Two real `model-write` tie-out failures. **(a)** 2021-FY 10-K tags FY2021 financing concepts dimensionally — `ProceedsFromIssuanceOfCommonStock` has `val=None` consolidated and real values only in two June-2021 offering-tranche segmented contexts. xbrl-xml correctly filters dimensional facts, so 4 financing lines were silently absent (CFF off by $67.7M). **(b)** 2020-FY 10-K's tagged CFO (3,395,084) is internally inconsistent with its tagged operating line items (sum 3,522,347) — gap is exactly the depreciation fact (127,263), and the presentation linkbase says Depreciation IS a rendered child, so the filer's XBRL is self-contradictory. Both CFs dropped from their validated JSONs (kept BS + IS); FY2021 CF flows in via `validated_2023-FY`'s 3-year comparative (ties clean). FY2019/FY2020 annual CF + Q4 FY2020 remain absent. Also dropped FY2019 comparative CFs from the three 2020 10-Qs (not model columns; one had a $48K gap).

### 5. Model rebuild + qtr-derive + calc — end to end
23 validated filings, 1857 cells written. ANNL P&L + BALANCE SHEET now `FY2019..FY2025` (BS-starts-FY2022 misalignment **fixed**). QTR P&L contiguous Q1 FY2019 → Q4 FY2025 (28 quarters; **missing Q4 FY2020 restored**). QTR BS contiguous Q4 FY2019 → Q4 FY2025. CASH FLOW annual FY2021 → FY2025; QTR CF Q1 FY2020 → Q4 FY2025 with Q4 FY2020 gap. `model-calc` layered 120 driver specs × 20 forecast quarters. 0 cached formula errors. Backup `CELH_model.prerebuild-2026-05-20.bak.xlsx`.

## Current state

- **Framework** — `xbrl_xml_path.py` new; `extract.py` auto-routes by `<ix:>` count + `--path xbrl-xml` override; `model-write` uses `_scaled_value()`; `reconcile._register` propagates `accepted_sections`. Memory `project_celh_ixbrl_boundary.md` updated (RESOLVED).
- **Validated filings (CELH)** — 23 (was 17). `validated_2020-FY.json` and `validated_2021-FY.json` have CF statements dropped (filer data-quality); originals retained at `*.withCF.bak.json` in the same folder.
- **Generic library** — 163 canonicals; aliases on 6 entries; `GEN-CI-001` +3 `accepted_sections`. **Cross-ticker.**
- **CELH ledger** — 12 mappings, 24 new_rows, 7 structural decisions.
- **Workbook** — rebuilt; columns above.
- **Harness baseline** — NOT re-locked. 87-filing 4-ticker regression pending.

## Open decisions / pending work

1. **4-ticker joint regression PENDING** — `_scaled_value` rescales PG/PEP outputs ×1000 (millions→thousands); library aliases are cross-ticker; `reconcile._register` accepted-sections propagation can change ticker overlay matches. Per `feedback_celh_pg_joint_regression.md`, run the 87-filing snapshot harness against all four tickers. **Open the next session here.**
2. **CASH FLOW FY2019/FY2020 + Q4 FY2020** — recoverable only by deciding which side of the 2020-FY filer XBRL self-inconsistency to trust (tagged CFO $3,395K vs line items summing $3,522K; gap = Depreciation fact exactly). Decide + `validation_overrides`, or accept.
3. **Playgrounds-in-sync rule** (per `feedback_keep_playgrounds_in_sync.md`) — no structural change touched playground concerns; `playground_*.html` don't need updates.
4. **Carryover from May 11** — pre-iXBRL backfill resolved; 2021-FY/2022-FY `find_primary_tables` rewrite obsolete (new path bypasses HTM tables); MDA Phase 2 rework untouched.

**Carried rules:** structural-over-heuristic; no validator sign flips; no R-files; CF visual sign from preferredLabel.

## Key file paths

| Purpose | Path |
|---|---|
| This handoff | `Brain\Sessions\CELH Model\Handoffs\May 20th Pre-iXBRL Backfill + Units Fix Session.md` |
| Prior handoff (archived) | `Brain\Sessions\CELH Model\Handoffs\Archive\May 18th Transcript-KPI Skill Build Session.md` |
| Roadmap | `Brain\Sessions\CELH Model\ROADMAP.md` |
| New extractor | `Brain\Knowledge\Model Schema\.claude\skills\financials-extract\scripts\xbrl_xml_path.py` |
| Dispatch wiring | `Brain\Knowledge\Model Schema\.claude\skills\financials-extract\scripts\extract.py` (`detect_source_kind`, `--path`) |
| Units normalization | `Brain\Knowledge\Model Schema\.claude\skills\model-write\scripts\write.py` (`_scaled_value`, `_UNIT_TO_THOUSANDS`, `CF_TIE_OUT_*`) |
| Accepted-sections fix | `Brain\Knowledge\Model Schema\.claude\skills\financials-reconcile\scripts\reconcile.py` (`_register`) |
| Workbook | `Brain\Knowledge\Model Outputs\CELH\CELH_model.xlsx` (backup `CELH_model.prerebuild-2026-05-20.bak.xlsx`) |
| Validated JSONs (23) | `Brain\Knowledge\Model Schema\Ticker Libraries\CELH\Financial Statements\validated_*.json` |
| Cached XBRL XML | `Brain\Knowledge\Model Schema\.claude\skills\financials-extract\.cache\ixbrl_reports\{accession_nodash}\` |
| Generic library | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` (backup `*.bak.json`) |
| CELH ledger | `Brain\Knowledge\Model Schema\Ticker Libraries\CELH\Financial Statements\decisions_ledger.json` (backup `*.bak.json`) |
| Memory updated | `~\.claude\projects\C--Users-rodin\memory\project_celh_ixbrl_boundary.md` |

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
