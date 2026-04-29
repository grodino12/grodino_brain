---
type: session-handoff
date: 2026-04-29
topic: Inventory breakdown shipped — RM/WIP/FG render as detail line_items beneath Inventories Net (parent =SUM(detail) historical, DIO forecast); children = RATIO_OF_PARENT (% of parent). New `parent_canonical` field on LibraryEntry; new `RATIO_OF_PARENT` driver kind; validate.py + model-write tie-out skip children when parent present. PG (14) + PEP (13) now expose disclosed breakdown; CELH (12) + MNST (20) unchanged. Library 146 → 148 entries (3 new, 1 deleted). 4-ticker regression locked; 1 new memory rule.
tags: [session, inventory-breakdown, parent-canonical, ratio-of-parent, four-ticker-clean]
---

# April 29th — Inventory Breakdown Session

Picks up from `Archive\April 29th MNST Onboarding Session.md`. Roadmap's next-objective was the inventory breakdown (RM/WIP/FG); user added two clarifications during the session (Net Inventories forecast stays DIO regardless; parent cell historically should be `=SUM(children)` and section sums should use parent value not children). Plan extended to a generic `parent_canonical` mechanism on LibraryEntry — first instance: GEN-BS-051/052/053 → GEN-BS-005. Next session opens with **playground architecture/schema sync verification + systematic driver-kind determination** (replace remaining `_label_contains` substring checks in `inference.py` with structural canonical metadata, per the carried roadmap item).

## Starting state

- 4 tickers (CELH 12 / PG 14 / PEP 13 / MNST 20 = 59 filings) BS-tied at $0; library 146 entries; snapshot harness clean.
- GEN-BS-038 was a memo bucket absorbing RM/WIP/FG concepts but rendering nothing — PG (full disclosure) and PEP (full disclosure) collapsed into single Inventories Net line in the workbook.
- CELH and MNST disclose only Net (no breakdown). Mixed-rendering case must be supported.

## Work done this session

### 1. Library schema + JSON (`generic_line_item_mappings.json`, 146 → 148 entries)

New `parent_canonical: str | None` field on `LibraryEntry` (`financials_schema/lookup.py:228`). When set, the canonical is a "detail of" the named parent rule_id. Deleted GEN-BS-038 memo bucket; added GEN-BS-051 Raw Materials, GEN-BS-052 Work in Process, GEN-BS-053 Finished Goods — all `parent_canonical: "GEN-BS-005"`, all line_items in current_assets. Concepts split out from the old memo: `InventoryRawMaterials*` → 051, `InventoryWorkInProcess*` → 052, `InventoryFinishedGoods*` → 053. Aliases harvested from PG ("Materials and supplies") and PEP ("Raw materials and packaging" / "Work-in-process") observed in validated outputs.

### 2. model-write parent SUM rendering (`write.py`)

New `_collect_parent_children(generic)` builds (parent_to_children, child_to_parent) maps. After base value-write pass on each BS sheet (`build_workbook` per-sheet loop): for each parent canonical present on the sheet, walk `(sheet, period)` and detect any child with non-zero data; if yes, overwrite parent's cell with `=SUM(child rows)` and apply subtotal styling (bold + top border + SUBTOTAL_FMT). Per-period gating preserves filer's reported value for periods where breakdown wasn't disclosed. Bolds the parent's column-A label if any period flipped.

### 3. model-write `validate_workbook_ties` skip-children-when-parent-present

Added `child_to_parent_row: dict[(sheet, child_row), parent_row]` parameter. Inside section_sums loop: if the row is a child AND the parent has data for the same (sheet, period), skip the child. Built at call site from pre-mutation row_map ⊗ child_to_parent rule_id map. Avoids double-count BS-1 / TCA when both parent + children are in `sheet_cells`.

### 4. financials-validate library-aware BS-1 (`validate.py`)

`partition_balance_sheet` now takes `child_to_parent` and skips children from the section bucket when the parent canonical is also present in the same items list. `validate.py:main` loads the generic library at startup, builds child→parent rule_id map, threads through `validate_filing(...)`. Without this, BS-1 would FAIL on every PG/PEP filing (over by sum of detail = filer Net = double-count).

### 5. model-calc — new `RATIO_OF_PARENT` kind

`driver_models.py`: added `RATIO_OF_PARENT = "ratio_of_parent"` enum value + `parent_source: Optional[Tuple[str, str]]` field on DriverSpec. `inference.py`: when entry has `parent_label` (resolved from `parent_canonical` rule_id → parent's model_label in `load_label_section_map` 2-pass post-process), override the section default with RATIO_OF_PARENT; populate `spec.parent_source = (sheet, parent_label)`. `calc.py`: registered in DRIVER_TAB_KINDS, USER_INPUT_KINDS, RATIO_KINDS; suffix label "% of Parent"; PERCENT_FMT format. Historical formula: `=IFERROR(child / parent, "")` referencing parent on same sheet via `parent_src_row_by_label`. Forecast formula on source sheet: `=parent_forecast_cell × ratio_cell`. Parent canonical (Inventories Net) keeps its existing DIO_RATIO behavior — children sum to parent in forecast by construction (ratios sum to 1.0).

### 6. Production refresh + 4-ticker regression locked

Refreshed all 4 tickers' validated_*.json (Ticker Libraries/{T}/) via re-extract → reconcile → validate; rebuilt Model Outputs/{T}/{T}_model.xlsx; ran model-calc forecast layer on each. PG/PEP workbooks now render RM/WIP/FG as plain line_items with Inventories at SUM-formula subtotal style; CELH/MNST unchanged. Snapshot harness diff: PG 1156 + PEP 1067 expected diffs (canonical relabeling GEN-BS-038 → 051/052/053 + row_type memo→line_item). After `--accept`, `python run.py` returns ALL CLEAN.

## Current state

- **CELH**: 12 filings clean. Inventories renders single line_item (no detail).
- **PEP**: 13 filings clean. RM/WIP/FG line_items above Inventories `=SUM(B5,B6,B7)` subtotal.
- **PG**: 14 filings clean. Same as PEP layout.
- **MNST**: 20 filings clean. Inventories single line_item.
- **Library**: 148 entries (146 + 3 new − 1 deleted).
- **Snapshot harness**: 59-filing baseline locked; ALL CLEAN.
- **Memory**: `feedback_parent_canonical_pattern.md` saved (1 new rule).

## Open decisions / pending work

1. **NEXT SESSION OPENS WITH** — systematic driver-kind determination. Replace `_label_contains` substring checks in `inference.py` (`Cash & Cash Equivalents`, `Restricted Cash`, `inventor`, `accounts payable`, etc.) with structural canonical metadata. Now is the moment: `parent_canonical` was added this session; the same `LibraryEntry` flag pattern can express "this canonical IS Cash" / "...IS AR" without label scans. Per roadmap's queued item, plus the no-heuristic policy.
2. **Playground sync verification** — `playground_architecture.html` LS_KEY bumped v13 → v14; `parent_canonical` added to LibraryEntry node in `playground_schema.html`; inference doc line updated to mention RATIO_OF_PARENT. User-facing review owed: confirm node positions / arrows still read coherently after the schema delta.
3. **TickerLedgerEntry validator** (carried) — Pydantic model for per-ticker `decisions_ledger.json` to close the silent-typo gap.
4. **Active propagating rules** carried: playground sync, no-heuristic policy, no validator sign flips, no duplicate anchor subtotals, joint regression on **4 tickers** (CELH+PG+PEP+MNST = 59 filings).

## Key file paths

| Purpose | Path |
|---|---|
| This handoff | `Brain\Sessions\CELH Model\Handoffs\April 29th Inventory Breakdown Session.md` |
| Prior handoff (archived) | `Brain\Sessions\CELH Model\Handoffs\Archive\April 29th MNST Onboarding Session.md` |
| Roadmap | `Brain\Sessions\CELH Model\ROADMAP.md` |
| Library (148 entries) | `Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json` (GEN-BS-051/052/053 + parent_canonical field) |
| LibraryEntry schema | `Brain\Knowledge\Model Schema\financials-schema\financials_schema\lookup.py:228` |
| model-write parent SUM | `~\.claude\skills\model-write\scripts\write.py` (`_collect_parent_children`, BS post-process loop, `validate_workbook_ties` child skip) |
| financials-validate child skip | `~\.claude\skills\financials-validate\scripts\validate.py` (`partition_balance_sheet`, library load in main) |
| model-calc RATIO_OF_PARENT | `~\.claude\skills\model-calc\scripts\driver_models.py` (DriverKind + parent_source field), `inference.py` (override + parent_label resolution), `calc.py` (DRIVER_TAB_KINDS / RATIO_KINDS / suffix / historical formula / forecast formula) |
| Snapshot harness (4 tickers, locked) | `Brain\Knowledge\Model Schema\_regression\run.py`; goldens at `_regression\goldens\{TICKER}\` |
| Playgrounds (LS_KEY v14) | `Brain\Knowledge\Model Schema\playground_architecture.html`, `playground_schema.html` |

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
