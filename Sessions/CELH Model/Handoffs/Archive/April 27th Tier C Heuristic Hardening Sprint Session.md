---
type: session-handoff
date: 2026-04-27
topic: Replaced ticker-tuned heuristics across the iXBRL extract path with structural signals (concept→canonical fallback, NCI presence detection, presentation-linkbase subtotal flags) gated by a new snapshot regression harness — sprint completed in five stages with CELH (12) + PG (14) verified clean throughout.
tags: [session, tier-c-hardening, snapshot-harness, concept-fallback, nci-detection, presentation-linkbase, calc-linkbase]
---

# April 27th — Tier C Heuristic Hardening Sprint Session

Picks up from `Archive\April 26th PG Onboarding + Workbook Tie-Out Validator Session.md`. That session brought PG end-to-end clean; this session pivoted away from immediate PEP onboarding and instead executed a five-stage hardening sprint to replace ticker-tuned heuristics (regex / keyword / allowlist patterns added during CELH+PG hardening) with structural signals from the iXBRL filings themselves — gated end-to-end by a new mechanical regression harness so any framework change is auto-verified against the locked CELH+PG baseline. Next session opens with onboarding the third ticker (PEP) to validate the now-bombproof framework.

## Starting state

- CELH 12 filings + PG 14 filings clean from prior sessions (0 novels, 0 fails, 0 workbook tie-out errors).
- Drift surface flagged in conversation: regex-on-label-clutter, `"charge"` keyword scan, `IXBRL_SUBTOTAL_CONCEPTS` allowlist, library-author-time NI alias placement, `_DATE_ONLY_LABEL_RE` walker fallback.
- ROADMAP §18 listed "NEXT SESSION OPENS WITH: onboard a third ticker." Pivoted to hardening sprint based on user concern that adding new tickers without first replacing heuristics compounds drift risk.

## Work done this session

### 1. Snapshot regression harness (§18a)

`Brain\Knowledge\Model Schema\_regression\run.py` (~310 lines) + README. Auto-discovers each ticker's filings by reading `source_path` from existing `raw_*.json` cache files, re-runs extract → reconcile → validate → model-write per filing into a temp dir, diffs against frozen goldens at `_regression\goldens\{TICKER}\`. Workbook compared as `{sheet, row_label, col_label} → value` cell map, not xlsx binary (nondeterministic metadata). Numeric tolerance $1. `citation/source_path` excluded from diff (relative-vs-absolute path noise). UTF-8 stdout (Δ / em-dash safe). Modes: default = run+diff, `--bootstrap` = lock current state, `--accept` = rerun then overwrite goldens, `--ticker X` = scope, `--keep-temp` = preserve for inspection. Goldens locked: CELH 12 validated_*.json + workbook snapshot; PG 14 validated_*.json + workbook snapshot.

### 2. Concept-derived canonical label fallback (§18b)

New optional `us_gaap_concept` field on `LibraryEntry` Pydantic model. New `build_concept_index(library)` in `lookup.py` builds `(concept, sheet_group) → canonical` map, raising at load time on duplicate keys. `match_raw_item` adds a third lookup step after fuzzy fails: if `concept` is provided and `concept_index` available, exact-match the concept against the index. Walker passes `f.local_name` and the concept index from `ixbrl_path.py`. Populated `us_gaap_concept` on 91 of 121 library entries — 47 clean 1:1 assignments + ~13 conservative dominant picks from multi-concept entries; sub-component / bucket / ambiguous canonicals deliberately skipped. Surfaced and flipped 112 CELH diffs (all benign improvements: CELH's `Net (decrease) increase in cash...` rows now route correctly to canonical "Net Change in Cash" via concept fallback; CF-1 validator flips warning→pass with real numbers; **0 workbook diffs**). Per `feedback_label_only_matching.md` — fallback uses an EXPLICIT field, not the dropped CamelCase concept-name fuzzy matching.

### 3. NCI structural detection (§18c)

`is_nci_filer: bool = False` field added to `RawFiling`. Walker scans iXBRL document for NCI-bearing concepts at filing-load time — patterns: `MinorityInterest`, `*AttributableToNoncontrollingInterest*`, `*IncludingPortionAttributableToNoncontrollingInterest*`, `*IncludingNoncontrollingInterest*`. Initial naive `contains "NoncontrollingInterest"` over-matched (CELH has `IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest` — "BEFORE NCI" sense, used by every filer). Tightened to require NCI as semantic subject (`AttributableTo...`, `Including...`). Result: CELH=False, PG=True. Routing-leverage of the flag deferred until a real edge case (NCI filer that uses bare-NI phrasing for parent-attributable) — for now, flag is preserved structural signal only.

### 4. Drop "charge" keyword scan (§18d)

Audited every `"charge"`-labeled item across CELH+PG: 14 hits, all `'Indefinite-lived intangible asset impairment charge'` routing to GEN-IS-024 (sign_convention=negative declared) or GEN-CF-003 (as_reported). The `_derive_sign_from_label` keyword scan only fires when canonical has no sign_convention, so `"charge"` was dead code on every observed item. Removed `"charge"` from `_NEGATIVE_KEYWORDS` in `lookup.py`. Updated `feedback_charge_means_expense.md` — sign now encoded structurally on canonicals, not via label-text scan.

### 5. Presentation-linkbase-driven subtotal detection (§18e)

Initial attempt used calc linkbase parents as subtotal signal — premise too broad (calc parents include mid-statement aggregations like Pre-Tax Income that the pipeline treats as line items). Reverted, but kept the `_load_calc_subtotal_concepts` loader and the 26 cached `*_cal.xml` files for the future synthesis use case. Pivoted to **presentation linkbase**: new `_load_presentation_total_concepts()` reads each filing's `*_pre.xml`, collects every concept tagged `preferredLabel=totalLabel` (filer's own rendering intent). Set is **unioned** with `IXBRL_SUBTOTAL_CONCEPTS` (kept as floor for filer-skip-totalLabel safety) and used in walker subtotal detection. **Strict-mode dropped for IS** in walker's `match_raw_item` call — IS canonicals are semantically distinct enough that the BS strict-mode fuzzy-collision risk doesn't apply. Result: zero diffs (existing `row_type=subtotal` declarations on GEN-IS-003/005/009/022 already drove the same outcome via canonical override; pre.xml just adds drift resistance for future filers).

### 6. Memory + roadmap updates

New: `feedback_structural_over_heuristic.md` — meta-rule for the sprint (sign from canonical not label, routing from concept not regex, subtotals from pre.xml not allowlist, NCI from structural scan; harness as safety net). Updated: `feedback_charge_means_expense.md` (canonical-level sign, not keyword scan). Roadmap critical path bumped through §18a-e, item 20 (`_pre.xml` cleanup pass) marked obsolete.

## Current state

- **Snapshot harness**: locked, both tickers round-trip clean.
- **CELH 12 filings + PG 14 filings**: 0 novels, 0 validate fails, 0 workbook tie-out errors, 0 harness diffs.
- **Library**: 121 entries, 91 with `us_gaap_concept`, IS aggregations declared `row_type=subtotal`.
- **Walker**: presentation-linkbase-driven subtotal detection active; concept-fallback active for label misses; calc linkbase loader retained for future synthesis use.
- **Memory**: 1 new + 1 updated feedback rule.

## Open decisions / pending work

1. **NEXT SESSION OPENS WITH: onboard third ticker (PEP).** Validate cross-ticker generality. Workflow: mkdir `Brain\Knowledge\Model Schema\PEP\`, drop `config.json` + empty `decisions_ledger.json` + empty `anomalies.json`, run sec-edgar-fetch, run extract→reconcile→validate→model-write, triage novels per `feedback_novel_triage_protocol.md`, then add PEP to the regression harness via `--bootstrap --ticker PEP`.
2. **NCI routing leverage (deferred §18c follow-up).** `is_nci_filer` flag is computed but not yet used in routing decisions. Activate when a real edge case forces it (PEP/KO are NCI filers — may surface).
3. **OCI 4th statement build.** Walker still STOPS on OCI header; emit as `StatementType.COMPREHENSIVE_INCOME` once that StatementType ships.
4. **Extend `model-calc` to quarterly drivers.** Currently annual-only.
5. **Extract `pattern_libraries/generic_forecast_rules.json`** from `calc.py`. Blocked on §4.
6. **Formalize ticker onboarding doc** at `Brain\Knowledge\Model Schema\05_ticker_onboarding.md`.
7. **`financials-validate/SKILL.md` description stale** — still says "10 filer-tie rules" / `extract.py`. Update to "14 rules" + correct file refs (sign rules now in `lookup.py` keyword scan + canonical declarations).
8. **Refresh playgrounds + LS_KEY v9 → v10** — `playground_architecture.html` needs nodes/edges for: snapshot harness, concept fallback (new `us_gaap_concept` field), NCI flag, presentation-linkbase loader, calc-linkbase loader (synthesis-pending). Carry per active propagating rule.
8a. **No-heuristic policy** (active propagating rule, added this session 2026-04-27). Going forward, do NOT introduce new label-text regexes, keyword scans, or static concept allowlists to handle filer-specific patterns. Every routing / sign / subtotal / classification decision must be derivable from a structural signal in the filing — XBRL concept, presentation linkbase, calculation linkbase, label linkbase, or canonical declaration in `generic_line_item_mappings.json`. Existing heuristics (`CLUTTER_RE`, `TRAILING_PAREN_RE`, walker visual heuristics) are tolerated but not extended. Carry into every future handoff. Per `feedback_structural_over_heuristic.md`.
9. **Walker visual heuristics still present** (`_PRIMARY_TITLE_RE`, `_HEADER_PATTERNS`, `_HTM_SUBTOTAL_TRANSITIONS`, `_HTM_ROW_SECTION_OVERRIDE`) — substantial refactor to drive section detection from presentation linkbase role hierarchy. Out of sprint scope; revisit after PEP onboarding if drift risk surfaces.

## Key file paths

| Purpose | Path |
|---|---|
| This handoff | `Brain\Sessions\CELH Model\Handoffs\April 27th Tier C Heuristic Hardening Sprint Session.md` |
| Prior handoffs | `Brain\Sessions\CELH Model\Handoffs\Archive\` |
| Roadmap | `Brain\Sessions\CELH Model\ROADMAP.md` |
| **Regression harness + goldens** | `Brain\Knowledge\Model Schema\_regression\run.py` + `_regression\goldens\{CELH,PG}\` |
| Lookup module (concept index, presentation/calc loaders consumed here, IS strict drop, charge keyword removed) | `Brain\Knowledge\Model Schema\financials-schema\financials_schema\lookup.py` |
| Walker (pre.xml + calc.xml loaders, NCI detection, IS strict drop, concept fallback wiring) | `~\.claude\skills\financials-extract\scripts\ixbrl_path.py` |
| RawFiling schema (is_nci_filer field) | `Brain\Knowledge\Model Schema\financials-schema\financials_schema\filing.py` |
| Library entry schema (us_gaap_concept field) | `Brain\Knowledge\Model Schema\financials-schema\financials_schema\lookup.py` (LibraryEntry) |
| Library JSON (91 entries with us_gaap_concept) | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` |
| Cached cal.xml + pre.xml linkbases (26 each) | `~\.claude\skills\financials-extract\.cache\ixbrl_reports\{accession}\` |
| **CELH built workbook** | `Brain\Knowledge\Model Schema\CELH\Model Output\CELH_model_v5.xlsx` |
| **PG built workbook** | `Brain\Knowledge\Model Schema\PG\Model Output\PG_model_v5.xlsx` |
| Playground (needs LS_KEY v9 → v10) | `Brain\Knowledge\Model Schema\playground_architecture.html` |

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
