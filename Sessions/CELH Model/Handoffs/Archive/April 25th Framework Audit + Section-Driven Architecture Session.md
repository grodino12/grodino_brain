---
type: session-handoff
date: 2026-04-25
topic: Merged extract paths into one skill; ripped state machines + English-prose anchors out of validators in favor of `item.section` + `canonical_label`; reduced sign_convention to a 3-value abs-based system with IS-only keyword detection; added LibraryEntry Pydantic guard; surfaced `Section.UNCLASSIFIED` as a hard reconcile failure; ran the framework audit that drove most of these changes.
tags: [session, framework-audit, sign-convention, section-driven, library-validation, extract-merge]
---

# April 25th — Framework Audit + Section-Driven Architecture Session

Picks up from `April 24th Option B Migration + PG YTD Quarterly Session.md`. That session shipped Option B + the PG YTD pivot but left a long tail of contract drift, stale conventions, and recurring-bug shapes. This session ran an end-to-end audit (general-purpose agent) and worked the findings, plus several user-driven architectural simplifications: extract paths merged, sign convention reduced from a fragile 5-value scheme to abs-based positive/negative/as_reported, BS+CF validators rewritten to bucket by `item.section` instead of state-machine label walks. **Next session**: refresh playgrounds (substantial backlog), run CELH + PG regressions against the new architecture, then PG xlsx polish (NI subtotal, CF subtotal row insertion).

## Starting state

- Prior session shipped Option B but model-write was still keying on the old `expense_positive` string — every contra row writing wrong sign to xlsx (silent live bug).
- Two extract skills (`financials-extract` + `financials-extract-ixbrl`), nominally drop-in, diverging on small details.
- Library lookup keyed on display labels scraped from R-files; sign_convention enum had 5 values with overlapping semantics; filing_section unset on 80+ entries.
- Validators used English-prose anchors (`_find_item_contains("net cash", "operating activities")`) and a state machine for BS bucketing.

## Work done this session

### 1. Merged the two extract skills

`financials-extract-ixbrl` deleted; `financials-extract/scripts/extract.py` is now a CLI dispatcher routing on file extension (`.pdf` → `pdf_path.py`, `.htm`/`.html` → `ixbrl_path.py`). Single `--source` flag replaces `--pdf` / `--htm`. Both paths share `lookup.match_raw_item()` for library hits and emit identical `RawFiling` shape. Downstream comment references updated.

### 2. Dropped R-file label scrape; synthesize from concept name

Per user pushback on the redundancy ("we just change it to our own dictionary nomenclature anyway"). `extract_labels_from_report()` deleted; iXBRL `raw_filing_label` is now `concept_to_display(local_name)` — a CamelCase split. The label is just a matching key now; `canonical_label` from the library is the user-facing name. Side benefit: no second SEC fetch per concept.

### 3. Sign-convention overhaul — abs-based with 3 values

Old enum: `as_reported / parens_negative / expense_positive / contra_account / absolute_from_section_header`. Replaced with `as_reported / positive / negative`. `_signed_value()` now does `±abs(value)` instead of multiplying by ±1. Filer's reported sign is irrelevant — if we say "negative," we get -abs regardless of whether the filer wrote `100`, `-100`, `(100)`, or pre-signed. Killed the `parens_negative` branch in `pdf_path.py` (no longer needed). Migrated 8 generic entries + 1 PG ticker entry (`expense_positive`/`contra_account` → `negative`).

### 4. IS-only keyword sign-detection in match_raw_item

Per user observation that canonical labels encode sign via parens (e.g. `Income Tax (Expense) Benefit`). New helper `_derive_sign_from_label()` checks raw_filing_label keywords: `expense`/`loss`/`cost of` → negative; `benefit`/`gain`/`income`/`recovery` → positive. Gated to `statement_type==INCOME_STATEMENT` (CF "depreciation expense" is a positive add-back — would mis-flip without the gate). Per-entry sign_convention always wins. Lets us drop explicit flags on tax (which can swing benefit/expense) while keeping COGS/SG&A/Interest Expense etc. flagged for short aliases ("COGS" alone has no keyword).

### 5. Recombined Interest / FX / Other Non-Op split entries

Last session split `GEN-IS-006/007/008` (net) into `029/030`, `031/032`, `033/034` (separate gain vs loss canonicals). With keyword detection now driving sign, that split is unnecessary. Donors deleted, aliases merged into the survivors (006/007/008). Income Tax canonical renamed `(Benefit) Expense` → `(Expense) Benefit` so positive direction sits outside parens (matches the convention used by every other split canonical).

### 6. filing_section backfill + OCI removal

Backfilled 80 CF + IS entries with `filing_section` (BS already populated last session). Intentionally left null on 3 CF bottom-of-statement rows (`Net Change in Cash`, `Cash at Beg/End`) and 4 NI/NCI bottom-of-IS rows — they don't fit the section enum buckets. Removed 7 OCI/CI entries from the library entirely per user ("OCI shouldn't be on the IS"). Will be re-added when an OCI sheet ships.

### 7. Section enum overhaul + section-driven validators

`Section.FX_RECONCILIATION` → `Section.CASH_OTHER`. CF is now genuinely 4 sections (operating/investing/financing/cash_other); FX Effect on Cash sits in cash_other; `NetΔCash = sum of all 4 section subtotals`. **`partition_balance_sheet` and `partition_cash_flow` rewritten** to bucket by `item.section` directly — state machines + English-prose anchor walks both gone. Subtotal rows still captured as named anchors via `row_type=="subtotal"`. CF-1 + X-4 rewritten to use `canonical_label` / partition output instead of `_find_item_contains` (which is now deleted).

### 8. Reconcile halts on UNCLASSIFIED + LibraryEntry Pydantic model

Per `feedback_novel_triage_protocol.md` — extract was silently emitting `Section.UNCLASSIFIED` for items that missed every layer. Reconcile now fails loudly with the offending items + their `ledger_rule_id` / `canonical_label`, pointing to where `filing_section` should be added. Plus added `LibraryEntry(BaseModel, extra="forbid")` validation at load time — catches field-name typos and invalid enum values immediately, not at use time. Library smoke-tested clean (109 entries).

### 9. Other audit cleanup

- `SHEET_NAME.get(..., "BALANCE SHEET")` fallback removed — now KeyError on missing combo (was masking 8-K IS misroute).
- `_keep_statement_for_reconcile` was duplicated in reconcile + write; promoted to `financials_schema.statement.keep_statement_for_pipeline`. Single source of truth.
- Library `filing_section` now overrides extract's heuristic in both PDF + iXBRL paths and reconcile's ticker overlay.
- Dead code removed: `_find_item_contains`, `test_any_regex_match`.

## Current state

- **Library: 109 entries** (was 122). Sign_convention now on 7 entries (4 IS expense lines + 2 BS contras + 1 PG ESOP). All others use as_reported or keyword-derived.
- **Validate**: BS + CF bucket by section; CF-1, X-4, BS-5 use canonical_label/partition; English prose only remains in CF-2 (Cash Beg/End — uses model_label which is canonical-equivalent) and a single `_find_item` call for "restricted cash" in X-2.
- **Section enum**: 16 values, includes new `CASH_OTHER`, removed `FX_RECONCILIATION`.
- **Pipeline NOT re-run on real data this session** — per user direction during the audit. Confidence rests on schema-load smoke tests + audit reasoning.

## Open decisions / pending work

1. **Refresh playgrounds** — substantial backlog: extract-merge collapses two nodes into one; lookup.py LibraryEntry model; CASH_OTHER section; sign_convention 3-value enum; section-driven partition; canonical_label-keyed validators. Per `feedback_keep_playgrounds_in_sync.md`. Bump LS_KEY.
2. **CELH + PG regressions** — overdue. Last clean run was before all of this. Expected to surface fuzzy-threshold edge cases (now 70 when concept set), library entries needing concept-name aliases, and possibly section-fix triages.
3. **PG xlsx polish** carried from prior handoff — NI subtotal formula self-reference, CF subtotal row insertion (`insert_cf_subtotal_slots`), EPS format branch, Convertible Preferred Stock canonical scope.
4. **IS D&A library entry** — deferred until we hit a filer that breaks out D&A on the IS (PG embeds it).
5. **OCI as 4th statement** — carried; OCI library entries pulled this session, will be restored when sheet exists.
6. **LTM-period validation** — still unresolved.
7. **PG ledger NEW-BS-001 note text** — still says "stored expense_positive"; file encoding quirks blocked auto-edit. Cosmetic.
8. **Active propagating rule** — every structural change must update `playground_architecture.html` + `playground_schema.html`. Carries forward.

## Key file paths

| Purpose | Path |
|---|---|
| This handoff | `Brain\Sessions\CELH Model\Handoffs\April 25th Framework Audit + Section-Driven Architecture Session.md` |
| Prior handoff | `Brain\Sessions\CELH Model\Handoffs\April 24th Option B Migration + PG YTD Quarterly Session.md` |
| Roadmap | `Brain\Sessions\CELH Model\ROADMAP.md` |
| Schema package (LibraryEntry, keep_statement_for_pipeline added) | `Brain\Knowledge\Model Schema\financials-schema\financials_schema\` |
| Section enum (CASH_OTHER added, FX_RECONCILIATION removed) | `Brain\Knowledge\Model Schema\financials-schema\financials_schema\enums.py` |
| SignConvention reduced to 3 values | `Brain\Knowledge\Model Schema\financials-schema\financials_schema\line_item.py` |
| Lookup module (LibraryEntry, IS keyword sign-detection) | `Brain\Knowledge\Model Schema\financials-schema\financials_schema\lookup.py` |
| Generic library (109 entries, sign cleanup) | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` |
| PG ledger | `Brain\Knowledge\Model Schema\PG\decisions_ledger.json` |
| Merged extract skill | `~\.claude\skills\financials-extract\` |
| Reconcile (UNCLASSIFIED halt, ticker section overlay) | `~\.claude\skills\financials-reconcile\scripts\reconcile.py` |
| Validate (section-driven partitions, canonical anchors) | `~\.claude\skills\financials-validate\scripts\validate.py` |
| model-write (sign-convention bug fixed) | `~\.claude\skills\model-write\scripts\write.py` |

## How to create the next handoff

Write at end of session under `Brain\Sessions\{Task-Theme}\Handoffs\{Month} {Day}{ord} {topic} Session.md`. **Target length: ~800-1200 words; hard ceiling 1500.**

### Structure

1. **YAML frontmatter** — `type`, `date` (absolute YYYY-MM-DD), `topic` (one sentence), `tags`.
2. **Title** matching filename.
3. **One-paragraph intro**: prior handoff reference + one sentence on what this session did + one sentence on what the next session should do.
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
