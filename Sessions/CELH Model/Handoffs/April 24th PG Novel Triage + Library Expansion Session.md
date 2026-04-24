---
type: session-handoff
date: 2026-04-24
topic: PG novel triage (107 → 0), generic library expansion (92 → 109), reconcile normalization fixes, playground scaffold refresh.
tags: [session, pg, novel-triage, generic-library, reconcile]
---

# April 24th — PG Novel Triage + Library Expansion Session

Picks up from `April 24th SEC EDGAR + Quarterly Pipeline Session.md`. That session smoke-tested PG Q2 FY2026 10-Q → 107 novels. This session drove that to 0 and cleaned up stale playground text. **Next session**: run PG through validate → playground → model-write to produce first QTR xlsx.

## Starting state

- PG reconcile against the generic library: 107 novels, 0 mapped (library was loaded, nothing matched).
- Generic library: 92 entries, PDF-label aliases only.
- PG `decisions_ledger.json`: empty scaffold.
- CELH FY2024 + FY2025 10-Ks: clean end-to-end from prior sessions.
- `playground_architecture.html` LS_KEY v5; scaffold text throughout reflected the pre-library CELH-only era.

## Work done this session

### 1. Root-caused the 107 novels — five issues

- **Variant bug**: `build_lookup_index` indexed every generic entry under `ANNL` only; 10-Q lookups (`target_variant=QTR`) got empty results.
- **CamelCase ≠ PDF text**: `normalize_label` didn't split `AccountsReceivableNetCurrent` into tokens, so PDF-label aliases (`"accounts receivable"`) couldn't match.
- **iXBRL subtotals missed**: `is_subtotal_label` regex required `"Total"` prefix; us-gaap concept names like `Assets` / `LiabilitiesAndStockholdersEquity` bypassed it.
- **Library gaps**: PG exposed missing canonical rows — Long-Term Debt, Short-Term Debt, Treasury Stock, Other NC Liabilities, NCI (BS + IS), OCI components, CI-attribution rows. CELH never surfaced these.
- **Subsection filter too strict for iXBRL**: library entries with `filing_subsection: "eps"` rejected iXBRL items with `subsection_context=None`, even on unambiguous single-candidate alias keys.

### 2. Reconcile fixes (`reconcile.py`)

- `normalize_label`: added CamelCase splitter (lower→upper + acronym→word).
- `build_lookup_index`: generic entries now index under BOTH variants; ticker entries stay variant-specific.
- `is_subtotal_label`: added `IXBRL_SUBTOTAL_CONCEPTS` frozenset (9 concept names).
- `select_entry`: single-candidate fallback when item has no subsection context — unblocks iXBRL EPS matching without breaking PDF disambiguation.

### 3. Generic library 92 → 109 entries

Added us-gaap concept aliases to ~15 existing entries. Added 15 new canonical entries: `GEN-BS-032/033/034/035/036/037/038/041` (Short-Term Debt, Current Portion LT Debt, Other NC Liab, Treasury Stock, NCI BS, Shares Issued memo, Inventory detail memo, Long-Term Debt), `GEN-IS-022/023/024/025/026/027/028` (NI Including NCI, NI Attributable to NCI, OCI Total, OCI AFS, OCI Pension, CI Attributable to NCI, CI Including NCI). **Non-obvious choices driven by user decision**:

- **Short-Term Debt vs Current Portion LT Debt split into two rows** (not one combined). `DebtCurrent` aggregate aliased under Current Portion by convention.
- **NCI structure kept three rows split** (GEN-IS-011 / GEN-IS-022 / GEN-IS-023) even though ProfitLoss = NetIncomeLoss + NCI.
- **Inventory detail collapsed into one memo entry** (`GEN-BS-038`) with label `"Inventories"` — intentionally duplicates `GEN-BS-005`'s label since detail concepts conceptually belong to the same line.
- **OCI Total (`GEN-IS-024`) renders on IS as temporary placeholder**; all other CI/OCI rows memo. Full OCI statement as 4th worksheet is deferred (see Open §3).
- **`ReserveForEsopDebtRetirement` is PG-specific, not generic** — went to PG ledger (`NEW-BS-001`), not library. User's reason: PG-only legacy ESOP (also JNJ/KO historically). Most filers don't have this line.

### 4. PG ticker ledger gained `NEW-BS-001`

`"ESOP Debt Retirement Reserve"`, `QTR BS`, `filing_section: equity`, `sign_convention: expense_positive`. Note flags that a parallel ANNL BS entry is needed when PG's first 10-K is run.

### 5. Architectural tangent — reverted

User proposed moving the generic library to extract-time so `RawFiling` carries already-canonical labels. Scoped the refactor (4 skills, new `source_label`/`canonical_label` fields, ~half-day). **Reverted before any code changes** — symmetry argument won: library and ticker ledger are peer inputs to reconcile (both reference-data dicts, neither Pydantic-validated on load, both contribute to the Pydantic-validated `MappedFiling`). Splitting across pipeline stages created asymmetry without semantic justification. No code touched; tasks deleted.

### 6. Playground scaffold refresh

All 8 `scaffoldBody()` entries in `playground_architecture.html` rewritten — the text was stale from the CELH-only pre-library bootstrap. `schemaLine()` + `scopeLine()` + `updatePrompt()` ledgerNote updated. `pattern-libraries` node consolidated (single node reflects the physical single-folder reality, with dual role: 6 files feed PDF extract, 1 file feeds reconcile). `LS_KEY` bumped v5 → v8 across the session.

### 7. Two new persistent memory entries

- `feedback_novel_triage_protocol.md` — triage order: library → ticker ledger → escalate user with scope/disposition/model_label/render questions. Claude does NOT pick canonical labels.
- `feedback_token_efficiency.md` — 8 habits for long sessions (short defaults, one question at a time, no unilateral decisions needing retroactive review, Grep before Read, trim command output, no intermediate artifacts on disk).

## Current state

- **PG reconcile**: 107 → 0 novels. 95 mapped + 12 subtotals. `mapped_2026_Q2.json` on disk, ready for validate.
- **CELH regression**: FY2024 + FY2025 10-Ks both clean (0 novels).
- **Generic library**: 109 entries.
- **PG ledger**: 1 entry (NEW-BS-001).
- **Playground**: LS_KEY v8, scaffolds refreshed across all 8 skills.
- **Skill state**: 7 of 8 built unchanged; `model-calc` still annual-only.

## Open decisions / pending work

1. **Active propagating rule** (carry every handoff): structural changes update both playgrounds; bump LS_KEY on NODES/EDGES changes.
2. **Run PG end-to-end** (next session's main work): validate → playground → model-write → first PG QTR xlsx.
3. **OCI as 4th statement** — deferred follow-up. Scope: `COMPREHENSIVE_INCOME` enum + un-merge CI in iXBRL extractor + move OCI library entries to `ANNL OCI` / `QTR OCI` variants + new `OCI-1` / `X-5` validators + OCI sheet family in model-write + cross-sheet pull on IS. ~Half-day. `GEN-IS-024` is a placeholder until this ships.
4. **LTM-period validation question** (user raised mid-session, pump-the-brakes'd): does validate need LTM-reconstructed IS comparisons against quarterly BS items? Would be a cross-filing validation mode — doesn't exist today. Needs decision next session before validate runs.
5. **PG first 10-K onboarding**: when PG's annual flow runs, add parallel ANNL BS entry for ESOP reserve to PG ledger.
6. **`model-calc` quarterly drivers**: not implemented. Deferred until PG has ≥2 quarters modeled.
7. **`generic_forecast_rules.json` extract** from calc.py: blocked on §2.
8. **Ticker onboarding doc**: blocked on §2.
9. **Active protocol memories** (apply automatically): `feedback_novel_triage_protocol.md` + `feedback_token_efficiency.md`.

## Key file paths

| Purpose | Path |
|---|---|
| This handoff | `Brain\Sessions\CELH Model\Handoffs\April 24th PG Novel Triage + Library Expansion Session.md` |
| Prior handoff | `Brain\Sessions\CELH Model\Handoffs\April 24th SEC EDGAR + Quarterly Pipeline Session.md` |
| Reconcile (4 fixes) | `~\.claude\skills\financials-reconcile\scripts\reconcile.py` |
| Generic library (109 entries) | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` |
| PG ledger (NEW-BS-001) | `Brain\Knowledge\Model Schema\PG\decisions_ledger.json` |
| PG MappedFiling (ready for validate) | `Brain\Knowledge\Model Schema\PG\Model Output\mapped_2026_Q2.json` |
| Architecture playground (v8) | `Brain\Knowledge\Model Schema\playground_architecture.html` |
| Roadmap | `Brain\Sessions\CELH Model\ROADMAP.md` |
| Python venv | `Brain\Knowledge\Model Schema\financials-schema\.venv\Scripts\python.exe` |

## How to create the next handoff

Write at end of session under `Brain\Sessions\{Task-Theme}\Handoffs\{Month} {Day}{ord} {topic} Session.md`. **Target length: ~800-1200 words; hard ceiling 1500.** Longer handoffs burn tokens on cold start and repeat what's in the code.

### Structure (exact order, don't skip sections)

1. **YAML frontmatter** — `type`, `date` (absolute YYYY-MM-DD), `topic` (one sentence), `tags`.
2. **Title** matching filename.
3. **One-paragraph intro**: prior handoff reference + one sentence on what this session did + one sentence on what the next session should do.
4. **Starting state** — 3-5 bullet points. What was true at session start. Reference prior handoff.
5. **Work done this session** — numbered `### 1.` subsections grouped by subsystem (not by chronological order). Each subsection: one-sentence summary, then bullet-per-change or tight paragraph. **Write *why* decisions were made, not *what* the code does** — the code and git diff already show what. Capture non-obvious user choices and design rationale.
6. **Current state** — bullet list, one line per subsystem. Numbers and status, not prose.
7. **Open decisions / pending work** — numbered list, 1-2 lines each. State the decision/action needed, not background. Always include the active playground-sync rule. Flag unresolved user questions explicitly.
8. **Key file paths** — two-column table. Absolute paths. Only load-bearing files; skip ones derivable from convention (e.g. skip `raw_*.json` if `mapped_*.json` is listed in the same folder).
9. **How to create the next handoff** — paste this section verbatim. Update the word-target + any protocol changes forward.

### Consolidation rules

- **Don't list every library entry or ledger row added** — cite the file, cite the count, call out only the non-obvious / user-driven choices. Details are in the JSON.
- **Don't re-explain what's in the code** — skill scaffold text, reconcile internals, validator rules. Reference by name; the scaffold/code is authoritative.
- **Don't recap architectural discussions that didn't ship code** — one line: "proposed X, reverted, reason Y." Spare paragraphs of exploration.
- **Don't repeat prose across sections** — if it's in Current State, don't re-state in Open Decisions.
- **Memory rules referenced, not duplicated** — say "per `feedback_X.md`", not the rule content.

### Quality bar

- Cold-start reader picks up this one file and can act. No re-asking.
- Concrete over abstract.
- Capture *why* non-obvious choices were made. *What* is in the code.
- Mention deletions/renames explicitly — otherwise the next session hunts for old paths.
- Self-contained. Don't say "as discussed."
