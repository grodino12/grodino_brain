---
type: session-handoff
date: 2026-04-24
topic: PG novel triage (107 → 0), generic library expansion (92 → 109), reconcile normalization fixes, playground scaffold refresh, architectural discussion on library placement (decided: keep at reconcile).
tags: [session, pg, novel-triage, generic-library, reconcile, playground-sync]
---

# April 24th — PG Novel Triage + Library Expansion Session

Picks up from `April 24th SEC EDGAR + Quarterly Pipeline Session.md`. That session shipped the 4-skill quarterly extension (sec-edgar-fetch, financials-extract-ixbrl, filing-type-aware reconcile/validate/model-write) and smoke-tested PG Q2 FY2026 10-Q → **107 novels**, flagged as suspiciously high. This session triaged and resolved that 107-novel count, rebuilt the generic library, and refreshed the playground scaffolding text.

## Starting state

- Reconcile on PG Q2 FY26 10-Q: **107 novels, 0 mapped** (with the generic library loaded via the default path fallback).
- Generic library: 92 entries, PDF-label aliases only (no us-gaap concept names).
- PG decisions_ledger.json: empty scaffold.
- CELH FY2024 + FY2025 10-Ks: end-to-end clean from prior session (0 novels each; validated; model-written; model-calc forecast formulas in place; BS balanced at $0 gap).
- `playground_architecture.html` LS_KEY at v5. Scaffold text throughout the file was stale — reflected the pre-library, pre-migration, CELH-only era.

## Work done this session

### 1. Root-causing the 107 novels

Ran reconcile with and without `--generic-library` flag — identical 107 novels both ways. The handoff's claim that "the dry-run did NOT pass `--generic-library`" was a misreading; reconcile.py:475 auto-resolves to `<ticker-root>/../pattern_libraries/generic_line_item_mappings.json` when the flag is omitted. The library was loaded; 0 mapped anyway.

Five distinct root causes surfaced:

- **Variant bug.** `build_lookup_index` indexed all 462 generic library keys under variant `"ANNL"` only (because every library entry's `model_sheet` is `"ANNL P&L"` / `"BALANCE SHEET"` / `"CASH FLOW"` — never a `"QTR "` prefix). A 10-Q's `target_variant` is `"QTR"`, so `lookup[(…, "IS", "QTR")] = []` for every key. This alone accounted for 100% of the generic-library miss rate on quarterly filings.
- **CamelCase ≠ PDF text.** `"AccountsReceivableNetCurrent"` normalized to `"accountsreceivablenetcurrent"` (one word) under the pre-session `normalize_label`. No library alias (all space-separated PDF text) could fuzzy-match it even at the permissive 50-score nearest-match threshold.
- **iXBRL subtotals missed.** `is_subtotal_label` regex requires `"Total"` / `"Subtotal"` prefix. iXBRL us-gaap concept names for subtotals (`Assets`, `AssetsCurrent`, `Liabilities`, `LiabilitiesCurrent`, `LiabilitiesAndStockholdersEquity`, `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest`) don't prefix with "Total".
- **Library gaps.** CELH's single-entity structure meant the library had no canonical entries for Long-Term Debt, Short-Term Debt, Treasury Stock, Other Non-Current Liabilities, Noncontrolling Interest (BS + IS), OCI components (AFS / Pension / Translation sub-lines), Comprehensive Income attribution rows. PG surfaces all of these.
- **Subsection filter too strict for iXBRL.** Library entries for EPS (`filing_subsection: "eps"`) filtered out iXBRL items whose `subsection_context` is always None (iXBRL concept names like `EarningsPerShareBasic` are self-disambiguating — no subsection context needed).

### 2. Reconcile fixes (`~/.claude/skills/financials-reconcile/scripts/reconcile.py`)

- `normalize_label` now splits CamelCase at lower→upper and acronym→word transitions before lowercasing. New regexes `CAMEL_SPLIT_LOWER_UPPER` + `CAMEL_SPLIT_ACRONYM`. Doesn't affect PDF labels (no CamelCase in them).
- `build_lookup_index` — generic library entries now index under BOTH `ANNL` and `QTR` variants. Canonical concepts are variant-agnostic; model-write routes the rendered sheet by filing_type regardless of the ledger entry's model_sheet. Ticker-ledger entries stay variant-specific (preserves CELH behavior).
- `is_subtotal_label` extended with `IXBRL_SUBTOTAL_CONCEPTS` frozenset (9 concept names). PDF `"Total X"` path preserved.
- `select_entry` — when item has no subsection context AND the alias key has exactly one candidate, accept despite filing_subsection mismatch. Unblocks iXBRL EPS matching without breaking PDF subsection disambiguation.

### 3. Generic library expansion (92 → 109 entries)

**Path: `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json`.**

- Added us-gaap concept-name aliases to ~15 existing entries (GEN-IS-001/002/006/015/016/017/020 and GEN-BS-001/006/012/014/016/027/028).
- 15 NEW canonical entries:
  - `GEN-BS-032 Short-Term Debt` (separate from Current Portion LT Debt per user direction)
  - `GEN-BS-033 Current Portion of Long-Term Debt` (also catches PG's aggregate `DebtCurrent` tag by convention — aliased `"debt current"`)
  - `GEN-BS-034 Other Non-Current Liabilities`
  - `GEN-BS-035 Treasury Stock` (contra-equity, expense_positive)
  - `GEN-BS-036 Noncontrolling Interest` (BS equity section)
  - `GEN-BS-037 Common Stock - Shares Issued` (memo — share count, not dollar)
  - `GEN-BS-038 Inventories` (MEMO — collapsed from three separate entries for Raw/WIP/Finished into one memo entry per user direction; all 3 us-gaap detail concepts alias here; intentional duplicate model_label with GEN-BS-005 since they conceptually belong to the same line at finer granularity)
  - `GEN-BS-041 Long-Term Debt` (non-current; renumbered from GEN-BS-033 to avoid collision with Current Portion LT Debt)
  - `GEN-IS-022 Net Income (Loss) Including NCI` (for `ProfitLoss`, `IncomeLossIncludingPortionAttributableToNoncontrollingInterest`)
  - `GEN-IS-023 Net Income (Loss) Attributable to Noncontrolling Interest`
  - `GEN-IS-024 OCI - Total Net of Tax` — rendered (not memo) as a temporary placeholder on the IS until the OCI statement ships as its own worksheet
  - `GEN-IS-025 OCI - AFS Securities` (memo)
  - `GEN-IS-026 OCI - Pension & Postretirement` (memo)
  - `GEN-IS-027 Comprehensive Income Attributable to NCI` (memo)
  - `GEN-IS-028 Comprehensive Income Including NCI` (memo)
- **Not added to generic library:** `ReserveForEsopDebtRetirement` (user decision: PG-specific, went to ticker ledger instead). I initially added it as `GEN-BS-041`, the user corrected, and I reverted.

### 4. PG decisions_ledger.json

Added `NEW-BS-001 "ESOP Debt Retirement Reserve"`, `model_sheet: "QTR BS"`, `filing_section: "equity"`, `sign_convention: "expense_positive"`. Note flags that a parallel ANNL BS entry will be needed when PG's first 10-K runs through.

### 5. PG end-to-end reconcile result

**107 → 0 novels.** Final reconcile stats: 95 mapped + 12 subtotals + 0 novels + 0 fuzzy fallbacks. `mapped_2026_Q2.json` written. CELH regression check: FY2024 + FY2025 10-Ks both still clean (0 novels). No pipeline regression.

### 6. Retroactive library review (per triage protocol, one question at a time)

User reviewed each decision I'd made unilaterally during the bulk pass. Confirmed or adjusted:
- Short-Term Debt / Current Portion LT Debt: **split into two rows** (was combined in my initial add).
- `DebtCurrent` aggregate: alias under **GEN-BS-033 Current Portion of LT Debt** by convention.
- NCI structure on IS: **keep three rows split** (GEN-IS-011 / GEN-IS-022 / GEN-IS-023).
- Inventory detail rows: **collapse three entries into one memo entry** with label `"Inventories"` (matches GEN-BS-005; the detail concepts conceptually belong to the same line).
- OCI: **render GEN-IS-024 Total OCI on the IS as temporary placeholder**; keep GEN-IS-015/020/025/026/027/028 as memo. **Full OCI statement as its own worksheet is a queued follow-up** — when shipped, GEN-IS-024 becomes a cross-sheet pull from `OCI!TotalOCI`.
- Other labels (Treasury Stock, Noncontrolling Interest, Long-Term Debt, Other Non-Current Liabilities): kept as picked.

### 7. Architectural tangent — "move library to extract time?"

User proposed routing the generic library through the extractors (so `RawFiling` carries already-canonical labels) to anchor the library's effect to Pydantic validation. Scoped the refactor (4 skills touched, new `source_label`/`canonical_label` fields, shared helper in financials-schema, ~half-day of work). Then I pushed back with the **peer-inputs-to-reconcile symmetry argument**: library and ticker ledger are both reference data consumed side-by-side by reconcile, neither Pydantic-validated on load, both contribute to the Pydantic-validated `MappedFiling` output. Splitting them across pipeline stages creates asymmetry without semantic justification. **User agreed; refactor reverted.** Tasks deleted.

### 8. Playground scaffolding refresh

Most `scaffoldBody()` entries in `playground_architecture.html` were stale — relics from the CELH-only pre-library bootstrap era. Rewrote:

- `schemaLine()` — corrected path to `Brain/Knowledge/Model Schema/financials-schema/`, noted 13 Pydantic classes + 16/16 pytest.
- `scopeLine()` — replaced CELH-only language with multi-ticker description; both branches (celh/generic) now accurately describe the post-migration architecture.
- `scaffoldBody('financials-extract')` — PDF-only path; does NOT do semantic mapping; reference path corrected.
- `scaffoldBody('financials-reconcile')` — major rewrite: generic library load, variant routing, CamelCase normalize, iXBRL subtotal allowlist, subsection fallback, section-collision guard, 109 entries, post-migration CELH ledger counts, PG + CELH acceptance.
- `scaffoldBody('financials-validate')` — accurate rule list (BS-1..6 + CF-1..5 + IS-1..4 + X-1/2/4 + M-1, BS-7 deferred); Q{N} FY{Y} label format; 48/48 acceptance.
- `scaffoldBody('financials-playground')` — NOVELS tab, iXBRL tooltip dispatch, stdlib-only.
- `scaffoldBody('model-write')` — scratch build (no xlsm/VBA), ANNL+QTR sheet families, row layout from latest filing's document order, section-boundary subtotals + cascades, number formats, historical dedup.
- `scaffoldBody('model-calc')` — in-place driver tabs, ASSUMPTIONS + IS/BS/CF DRIVERS, 27 forecast kinds listed, quarterly drivers flagged as not-yet-implemented, scenario overlays deferred.
- `updatePrompt()` ledgerNote — removed stale `data/derived/celh_decisions_ledger.md` reference; now documents generic library + ticker ledger + tier scoring.
- Previously-separate `generic-library` store node consolidated back into the single `pattern-libraries` node (physical reality: all 7 files live in the same Brain folder, with dual roles — 6 feed PDF extract, 1 feeds reconcile).
- `LS_KEY` bumped v5 → v6 → v7 → v8 across the session (multiple architecture changes).

### 9. Memory feedback entries created

- `feedback_novel_triage_protocol.md` — when reconcile surfaces novels: check generic library → check ticker ledger → escalate to user with scope / disposition / model_label / render questions before editing any file. Claude does NOT pick canonical labels. Bulk-refactor exception allows skipping the scope question for clearly-generic GAAP items but disposition + model_label still apply.
- `feedback_token_efficiency.md` — 8 habits for keeping long sessions efficient: short responses by default, one question at a time on escalations, don't make unilateral decisions that need retroactive review, state architectural concerns before scoping, Grep before Read on large files, trim command output, no intermediate artifacts on user disk, suggest `/clear`/`/compact` at natural breakpoints.

Both indexed in `MEMORY.md`.

## Current state

**Pipeline, end-to-end:**
- ✅ `sec-edgar-fetch` — unchanged
- ✅ `financials-extract-ixbrl` — unchanged
- ✅ `financials-extract` (PDF) — unchanged
- ✅ `financials-reconcile` — 4 fixes this session (see §2). PG 10-Q + CELH 10-Ks all 0 novels.
- ✅ `financials-validate` — unchanged at code level
- ✅ `financials-playground` — unchanged
- ✅ `model-write` — unchanged
- ⏳ `model-calc` — still annual-only. Quarterly forecast drivers pending.

**Generic library:** 109 entries (was 92). All new entries have PG us-gaap concept aliases; existing entries gained aliases as needed.

**PG data on disk:**
- `raw_2026_Q2.json` — 10 statements / 199 line items (unchanged from prior session)
- `mapped_2026_Q2.json` — NEW (this session). 95 mapped + 12 subtotals + 0 novels.
- `novels_2026_Q2.json` — NEW (this session). Zero novels after final pass.
- `decisions_ledger.json` — 1 new_row entry (NEW-BS-001 ESOP Debt Retirement Reserve)
- 99 10-Q folders under `Brain\Sources\PG\` — unchanged from prior session.

**CELH data:** unchanged. Regression-tested on FY2024 + FY2025 10-Ks with the new reconcile; both 0 novels.

**Playgrounds:**
- `playground_architecture.html` — scaffold text across all 8 skills rewritten. `pattern-libraries` node consolidated. LS_KEY at v8.
- `playground_schema.html` — no changes needed (no Pydantic schema changes this session).

## Open decisions / pending work

1. **Active propagating rule (carry into every handoff until user retires it):** every structural change to the financials framework must update `playground_architecture.html` + `playground_schema.html`. Bump `LS_KEY` when NODES/EDGES change so the browser picks up fresh defaults instead of cached state.

2. **Run PG end-to-end to first QTR xlsx** — next major milestone. `mapped_2026_Q2.json` is ready; next steps are `financials-validate` (period-agnostic rules should pass), then `financials-playground` for QA, then `model-write` to produce `PG_model.xlsx` with QTR P&L / QTR BS / QTR CF sheets. Expect surface-area issues (number formats, NCI sign conventions, subsection handling) to surface.

3. **OCI statement as its own worksheet** — user-ratified follow-up. Scope (deferred, sized at ~half-day):
   - Add `COMPREHENSIVE_INCOME` to `StatementType` enum in financials-schema
   - Un-merge CI from IS in `financials-extract-ixbrl` (R-file role lookup already identifies CI linkbase separately; tagging change only)
   - Move GEN-IS-015 + GEN-IS-020 + GEN-IS-024..028 library entries from `"ANNL P&L"` → `"ANNL OCI"` + new `"QTR OCI"` variant
   - Add `OCI-1` validator: `OCI.Total = Σ components`. Add `X-5`: `IS.CI = IS.NI + OCI.Total`.
   - Add `ANNL OCI / QTR OCI` sheet family to `model-write`. Subtotal logic for "Total OCI"; cross-sheet formula on IS pulling `OCI!TotalOCI`.
   - Playground rewire + LS_KEY bump.
   Currently `GEN-IS-024 OCI - Total Net of Tax` renders on IS as a placeholder; when the OCI sheet ships, it becomes a cross-sheet pull.

4. **LTM-period validation on quarterlies (user raised, then "pump the brakes" — carry forward).** User asked whether validate needs LTM-period comparisons against BS items on quarterlies. Not yet answered. Concrete question: for a 10-Q, the IS carries 3-month duration but the BS is a point-in-time snapshot. Some analysts reconstruct LTM (last-twelve-months) IS by summing the current Q + prior 3 Qs. Does validate need to check anything that relies on LTM? If yes, it's a cross-filing validation mode that doesn't exist today. Flagged for next session.

5. **Extend `model-calc` to quarterly drivers.** Currently annual-only. Quarterly forecast needs either duplicate spec tables or a mode parameter. Likely deferred until PG accumulates ≥2 quarters.

6. **PG first 10-K onboarding** — when PG's annual flow is run, `NEW-BS-001 ESOP Debt Retirement Reserve` needs a parallel ANNL BS entry added to PG ledger (note embedded in the current entry flags this).

7. **Extract `pattern_libraries/generic_forecast_rules.json`** from `model-calc.py`'s `FORECAST_STATEMENT_SPECS` + `DRIVER_SPECS`. Blocked on PG producing at least one clean ValidatedFiling.

8. **Ticker onboarding doc** at `Brain\Knowledge\Model Schema\05_ticker_onboarding.md`. Blocked on PG end-to-end completing.

9. **Triage protocol memory is now active** (`feedback_novel_triage_protocol.md`). For every novel: check generic library → check ticker ledger → ask scope / disposition / model_label / render before editing. Claude does NOT pick labels.

10. **Token efficiency memory is now active** (`feedback_token_efficiency.md`). Short default responses, one question at a time, Grep before Read, etc.

## Key file paths

| Purpose | Path |
|---|---|
| Handoff (this file) | `Brain\Sessions\CELH Model\Handoffs\April 24th PG Novel Triage + Library Expansion Session.md` |
| Prior handoff (quarterly pipeline) | `Brain\Sessions\CELH Model\Handoffs\April 24th SEC EDGAR + Quarterly Pipeline Session.md` |
| **Generic library (109 entries)** | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` |
| **Reconcile skill (4 fixes)** | `~\.claude\skills\financials-reconcile\scripts\reconcile.py` |
| **PG decisions ledger (1 entry: NEW-BS-001)** | `Brain\Knowledge\Model Schema\PG\decisions_ledger.json` |
| PG RawFiling (Q2 FY26) | `Brain\Knowledge\Model Schema\PG\Model Output\raw_2026_Q2.json` |
| **PG MappedFiling (ready for validate)** | `Brain\Knowledge\Model Schema\PG\Model Output\mapped_2026_Q2.json` |
| PG NovelReport (0 novels) | `Brain\Knowledge\Model Schema\PG\Model Output\novels_2026_Q2.json` |
| **Architecture playground (scaffold rewrite, v8)** | `Brain\Knowledge\Model Schema\playground_architecture.html` |
| Schema playground (unchanged) | `Brain\Knowledge\Model Schema\playground_schema.html` |
| Pipeline roadmap | `Brain\Sessions\CELH Model\ROADMAP.md` |
| Python venv | `Brain\Knowledge\Model Schema\financials-schema\.venv\Scripts\python.exe` |
| Memory: novel triage protocol (new) | `~\.claude\projects\C--Users-rodin\memory\feedback_novel_triage_protocol.md` |
| Memory: token efficiency (new) | `~\.claude\projects\C--Users-rodin\memory\feedback_token_efficiency.md` |
| Memory: playground sync rule | `~\.claude\projects\C--Users-rodin\memory\feedback_keep_playgrounds_in_sync.md` |
| Memory: handoff convention | `~\.claude\projects\C--Users-rodin\memory\feedback_session_handoffs.md` |

## How to create the next handoff

At the end of every session, write a new handoff under `C:/Users/rodin/Desktop/Brain/Sessions/{Task-Theme}/Handoffs/` following the exact structure below. This keeps every future "cold start" predictable — the next session picks up one file and knows everything it needs.

### Naming
`{Month-name} {Day-ordinal} {short-topic} Session.md`
e.g. `April 20th IR Scraper v1 Session.md`, `April 25th CELH Backend Session.md`.

Ordinal = `st` / `nd` / `rd` / `th`. One or two topic words. Keep the filename short.

### Required sections (in this order)

1. **YAML frontmatter** — `type: session-handoff`, `date: YYYY-MM-DD` (absolute, never relative), `topic: {one-line}`, `tags: [session, ...]`.
2. **`# {Title}`** heading matching the filename.
3. **`## Starting state`** — what was true at session start. Reference the prior handoff filename explicitly so the chain is walkable.
4. **`## Work done this session`** — grouped by logical chunks (numbered `### 1.` subsections work well). Each subsection should say *what changed* and *why*, not just the surface action. Capture root-cause insights.
5. **`## Current state`** — bullet list of what's working, what's partially working, what's not. Include concrete file paths for artifacts produced.
6. **`## Open decisions / pending work`** — numbered list of unresolved items. Each one should state the *decision* or *action* needed, not just a vague "look into X". If a decision is blocked on user input, say so. **Always include the active architecture-playground sync rule** (user asked this propagate across every handoff) so the next session sees it before making structural changes.
7. **`## Key file paths`** — two-column table: Purpose | Path. Use absolute paths. Include scheduled task names and external system references.
8. **`## How to create the next handoff`** — paste this exact section verbatim. Never drop it; never let the template drift without updating all copies forward.

### Quality bar

- Write so the next session (cold, no conversation history) can act without re-asking you questions.
- Prefer concrete over abstract.
- Capture *why* a design choice was made when it's non-obvious. Code shows what; handoffs should show why.
- If you deleted, renamed, or moved files, explicitly mention it — the next session will otherwise hunt for the old paths.
- Keep it self-contained. Don't say "as discussed" — write out the discussion outcome.
