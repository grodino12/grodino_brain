---
type: session-handoff
date: 2026-04-22
topic: FY2023 10-K reporting-style fixes (EPS/shares disambiguation, IS section classifier, subtotal-driven BS section flips) plus novels review flow — 5 of 14 FY2024 10-K novels designated
tags: [session, celh, multi-skill, novels, reconcile, extract, playground]
---

# April 22nd — Novels Disambiguation Session

Picks up from `April 22nd Multi-Skill Framework Session.md`. That session built the 3-layer pipeline (extract / reconcile / validate) + playground. This session tackled two correctness issues the FY2023 10-K exposed, then started walking through the FY2024 10-K novels.

## Starting state

- 3 of 6 skills built + shared schema + playground rendering FY2023 10-K cleanly (26/26 validation rules PASS).
- Playground had EPS/shares rows collapsed: `"Basic"`/`"Diluted"` EPS values and weighted-avg share counts were BOTH mapping to rows 31/32 (GAAP EPS Basic/Diluted), silently overwriting each other.
- `Section.EPS` was the only IS section being populated — everything else was `unclassified`, so the playground IS tab had one giant "Unclassified" group instead of proper Top Line / OpEx / Non-Operating groups.
- Pattern libraries + Model Schema docs had been renamed earlier in the day (`playground_architecture.html`, `playground_schema.html`; design docs renumbered 01-04).

## Work done this session

### 1. EPS / shares_outstanding disambiguation (end-to-end)

Root cause: both "Basic"/"Diluted" rows under "Earnings per share:" AND both "Basic"/"Diluted" under "Weighted average shares outstanding" were extracted with `section=eps` and no sub-context, so reconcile collapsed all 4 to rows 31/32.

Changes:
- **Schema** (`financials-schema/financials_schema/line_item.py`): added `subsection_context: str | None = None` field to `RawLineItem`.
- **Extract** (`financials-extract/scripts/extract.py`):
  - When the section-heading detector fires `Section.EPS`, also set `current_subsection="eps"`.
  - Detect `"Weighted average shares outstanding..."` as a subsection header → `current_subsection="shares_outstanding"`.
  - Parse unit-phrase exclusions (`derive_share_eps_units`): `"(in thousands, except per share amounts)"` → `share_unit=thousands, eps_unit=actual`; `"except share and per share"` → both ACTUAL.
  - Populate `Statement.share_unit` and `Statement.eps_unit` from the parsed exclusions.
- **Reconcile** (`financials-reconcile/scripts/reconcile.py`):
  - Lookup index now stores a LIST of candidates per `(label, sheet)` key.
  - `select_entry()` picks explicit `filing_subsection` match > wildcard.
- **Ledger** (`CELH/decisions_ledger.json`):
  - MAP-IS-020/021 now have `"filing_subsection": "eps"`.
  - Added NEW-IS-001/002 for shares Basic/Diluted with `filing_subsection="shares_outstanding"` → "Weighted Avg Shares Outstanding (Basic/Diluted)" as new_rows.
- **Playground** (`financials-playground/scripts/build_playground.py`):
  - Per-row effective unit computed from the parent Statement's `unit` / `share_unit` / `eps_unit`.
  - Orange `(actual)` / `(thousands)` suffix on rows whose unit differs from the statement's main unit.
  - Tooltip now includes `Unit: X`.

### 2. IS section classifier ("Top Line", "Operating Expenses", "Non-Operating", "Per Share & Shares Outstanding")

Added `classify_is_row(label, current_section)` in extract:
- Keywords routing to `Section.REVENUE_COST` (Top Line): revenue, net sales, cost of revenue/goods/sales, gross profit/margin
- Keywords routing to `Section.OPERATING_EXPENSES`: selling general, SG&A, R&D, operating expenses/costs, income/loss from operations, operating income/loss
- Everything else on IS (interest, FX, tax, NI, comprehensive, dividends) → `Section.NON_OPERATING`
- `Section.EPS` preserved when current_section is already EPS (set by section_heading)

Updated `SECTION_LABEL` in playground:
- `revenue_cost → "Top Line"`, `operating_expenses → "Operating Expenses"`, `non_operating → "Non-Operating"`, `eps → "Per Share & Shares Outstanding"` (renamed from "EPS" since this block now holds both EPS and shares rows).

### 3. Subtotal-driven BS section flips (FY2024 10-K specifically)

On the FY2024 10-K the BS had rows like `"Right of use assets-operating leases"` and `"Deferred revenue[2]"` mistagged as `current_assets`/`current_liabilities` because the filing doesn't have an explicit "Non-current assets:" section header. Added to extract:

```
# After emitting a row:
if statement_type == BS:
    if current_section == CURRENT_ASSETS and "total current assets" in label_low:
        current_section = NON_CURRENT_ASSETS
    elif current_section == CURRENT_LIABILITIES and "total current liabilities" in label_low:
        current_section = NON_CURRENT_LIABILITIES
```

### 4. Footnote-marker stripping in normalize_label

`"Deferred revenue[2]"` was normalizing to `"deferred revenue 2"` — the `[2]` footnote was corrupting fuzzy matches. Added `FOOTNOTE_RE = re.compile(r"\[\d+\]|\(\d+\)")` applied BEFORE the clutter regex. Now `"Deferred revenue[2]"` → `"deferred revenue"`.

### 5. `filing_section` discriminator in reconcile

Extends the `filing_subsection` mechanism to also filter by BS/IS/CF section. Ledger entries can optionally specify `"filing_section": "current_liabilities"` to only match items in that section.

`select_entry(candidates, item_subsection, item_section)` scores each candidate:
- +2 for explicit subsection match
- +1 for explicit section match
- Rejects candidates whose explicit field doesn't match the item
- Wildcards (field is None in the entry) are compatible but lowest priority

### 6. Novels visualization (NOVELS tab in playground)

- `reconcile.py` gained `--novels-out <path>` flag that writes a NovelReport JSON regardless of pass/fail or dry-run.
- `build_playground.py` gained `--novels-in <path>` flag (repeatable) + a NOVELS tab with a red badge.
- Each unique novel label (grouped by `(sheet, label, subsection_context)`) shows as a numbered row with sheet badge, section/subsection, raw label + page citation, all period occurrences + raw numeric values, and top 3 fuzzy candidates with scores.

### 7. Naming convention fix (memory-level)

User corrected: "stop referring to them as the year in which they were filed. Financials are always always always referred to regarding the period they are reporting for." Saved to memory at `~/.claude/projects/C--Users-rodin/memory/feedback_financial_period_naming.md` and indexed in `MEMORY.md`. From now on: FY2023 10-K (not 2024 10-K), FY2024 10-K (not 2025 10-K), etc.

## User's novel designations (FY2024 10-K — 5 of 14 given)

Apply these as ledger entries in `CELH/decisions_ledger.json`:

| # | Raw label (sheet) | User's rule | New ledger entries |
|---|---|---|---|
| #1 | `Deferred revenue[2]` (BS) | Above TCL → current; below TCL → NC | MAP-BS-029 `"deferred revenue"` + `filing_section: "current_liabilities"` → row 35 "Deferred Revenue (Current)"; MAP-BS-030 same term + `filing_section: "non_current_liabilities"` → row 42 "Deferred Revenue (NC)" |
| #2 | `Lease liability finance leases` (BS) | Same above/below TCL rule | MAP-BS-031 `"lease liability finance leases"` + `filing_section: "current_liabilities"` → row 34 "Lease Liability - Finance Current"; MAP-BS-032 same + `"non_current_liabilities"` → row 40 "Lease Liability - Finance NC" |
| #3 | `Note receivable-net` (BS) | Same row as the existing "Note Receivable-Net Current" / "Note Receivable-Current-net" | MAP-BS-033 `"note receivable-net"` (no filing_section) → row 12 "Note Receivable" |
| #4 | `Interest income, net` (IS) | Same as existing "Interest income (expense), net" — paren denotes negative = expense, positive = income | MAP-IS-031 `"interest income net"` → row 17 "Interest Income" |
| #5 | `Other income` (IS) | New line item (its own row) | NEW-IS-003 `"other income"` → new_row "Other Income" in `non_operating`, position after "Foreign exchange gain (loss)" at row 18 |

**Pending (9 novels not yet designated)**. User was mid-walkthrough when usage ran out. From the FY2024 10-K novels JSON at `CELH/derived/novels_FY2024_10K.json`, the remaining unique labels to surface in the playground NOVELS tab:

- #6 onward: `"Cash dividends paid on Series A convertible preferred s…"` (CF, closest: `dividends paid on series a preferred` @0.74 → row 43)
- `"Change in right of use asset and lease liability-net"` (CF, closest: `right of use assets and lease liabilities-net` @0.85 → row 28 Δ ROU/Lease)
- `"Acquisition of Big Beverages Contract Manufacturing L.L"` (CF, new — Big Beverages acquisition per `anomalies.json`)
- `"Net income (loss) before provision for income taxes"` (IS, closest: `net income loss before income taxes` @0.83 → row 20 Pre-Tax Income)
- `"Net increase in cash and cash equivalents"` (CF, closest: `net increase decrease in cash cash equivalents and restricted cash` @0.69 → row 48 Net Change in Cash)
- `"Inventories"` (BS, closest: `inventories-net` @0.85 → row 13 Inventories)
- `"Note receivable-net"` (CF context — change in note receivable; closest: `note receivable-net change` @0.84 → row 34 CF)
- Plus whichever ones got collapsed/expanded by the grouping key when re-rendered.

After all 14 are designated, re-extract + re-reconcile + re-validate FY2024 10-K → if validators pass, playground merges FY2024 data into the BS/IS/CF tabs alongside FY2023.

## Current state

### Built / verified
- All 4 skills (extract, reconcile, validate, playground) updated with the new disambiguation mechanisms
- Shared schema updated (`subsection_context` on RawLineItem) — 16/16 pytest pass
- FY2023 10-K still passes 26/26 validation with new IS classifier + section labels
- Playground renders BS · IS · CF · VALIDATION · **NOVELS** tabs correctly

### Pending
- **Ledger entries for user designations #1–#5 not yet written to disk** (session ran out before final write + pipeline re-run). See the table above — insert at mappings array end (after MAP-IS-030 at line ~927 of `CELH/decisions_ledger.json`) and new_rows array end.
- FY2024 10-K reconcile still blocks on 14 novels (5 designated, 9 pending user review)
- **`Acquisition of Big Beverages`** row label was truncated by pdfplumber (`L.L` instead of `L.L.C.`). Not blocking but worth an extraction-side fix later (table cell width limit?).
- **`Net increase in cash and cash equivalents`** — if user maps to CF row 48, X-2 validator may need a new anomaly entry: FY2024 CF reports cash-only (no restricted cash add-back), so X-2's `cash_convention_per_year` for 2024 must be `cash_only` (already is, per `anomalies.json`). No action needed if convention is already set — just validate after reconcile clears.

## Pipeline invocation (copy-paste to resume)

```bash
cd "C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema"
source financials-schema/.venv/Scripts/activate

# Re-extract FY2024 10-K (produces raw_2025_10K.json — kept old filename for sortability)
PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/financials-extract/scripts/extract.py" \
    --ticker-root "CELH/" \
    --pdf "C:/Users/rodin/Desktop/Pl3 Celsius Case Study/data/CELH Reporting/Financial Statements/2025_CELH_10-K.pdf" \
    --out "CELH/derived/raw_2025_10K.json" \
    --filing-type "10-K" --filing-date "2025-02-27"

# Reconcile with novels-out (dry-run doesn't write mapped JSON but DOES write novels)
PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/financials-reconcile/scripts/reconcile.py" \
    --ticker-root "CELH/" \
    --in "CELH/derived/raw_2025_10K.json" \
    --out "CELH/derived/mapped_2025_10K.json" \
    --dry-run --novels-out "CELH/derived/novels_FY2024_10K.json"

# Render playground with FY2023 validated + FY2024 novels (current state of the UI)
python "C:/Users/rodin/.claude/skills/financials-playground/scripts/build_playground.py" \
    --in "CELH/derived/validated_2024_10K.json" \
    --novels-in "CELH/derived/novels_FY2024_10K.json" \
    --out "CELH/derived/explorer_2024_10K.html"
```

Once all novels are resolved, drop `--dry-run` + `--novels-out` from reconcile and run validate:
```bash
PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/financials-validate/scripts/validate.py" \
    --ticker-root "CELH/" \
    --in "CELH/derived/mapped_2025_10K.json" \
    --out "CELH/derived/validated_2025_10K.json"
```

Then render playground merging both validated filings:
```bash
python "C:/Users/rodin/.claude/skills/financials-playground/scripts/build_playground.py" \
    --in "CELH/derived/validated_2024_10K.json" \
    --in "CELH/derived/validated_2025_10K.json" \
    --out "CELH/derived/explorer_multi.html"
```

## Open decisions / pending work

1. **Write user designations #1–#5 into the ledger** (before resuming novel walkthrough). Use the table in "User's novel designations" above. Rule IDs: MAP-BS-029/030/031/032/033, MAP-IS-031, NEW-IS-003.
2. **Resume novel walkthrough from #6**. Re-render the playground after writing the new entries (some novels will auto-resolve via the new fuzzy + footnote + filing_section mechanisms).
3. **FY2024 BS section-header detection for 2nd occurrences**. The subtotal-flip fix works for the Asset/Liabilities split but doesn't yet flip TL→Mezz or Mezz→Equity. Not blocking on FY2024 10-K but may surface if/when we load older filings.
4. **Acquisition of Big Beverages** label truncation — pdfplumber extracted `"L.L"` instead of `"L.L.C."`. Probably a column-width artifact. Not critical.
5. **BIG ARCHITECTURAL TODO (carry-forward from prior handoff)**: multi-era reporting-style drift. Partially addressed this session (filing_section / filing_subsection / footnote stripping reduce the problem), but long-term we still want a filing-era adapter or multi-variant ledger design. Re-read section 10 of the prior handoff.
6. **BS-7 RE roll-forward validator** still not implemented.
7. **Model-write (Layer 4 part 2)** — next milestone after FY2024 10-K fully validates.

## Key file paths

| Purpose | Path |
|---|---|
| Pipeline architecture map (playground) | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/playground_architecture.html` |
| Pydantic schema map (playground) | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/playground_schema.html` |
| Design docs (01–04) | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/0{1..4}_*.md` |
| Shared Pydantic package | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/financials-schema/` |
| Shared pattern libraries | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/pattern_libraries/*.json` |
| CELH ticker config | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/CELH/config.json` |
| CELH anomalies | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/CELH/anomalies.json` |
| CELH decisions ledger (needs 7 new entries) | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/CELH/decisions_ledger.json` |
| CELH derived outputs | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/CELH/derived/` |
| Extract skill | `C:/Users/rodin/.claude/skills/financials-extract/` |
| Reconcile skill | `C:/Users/rodin/.claude/skills/financials-reconcile/` |
| Validate skill | `C:/Users/rodin/.claude/skills/financials-validate/` |
| Playground skill | `C:/Users/rodin/.claude/skills/financials-playground/` |
| Prior handoff | `C:/Users/rodin/Desktop/Brain/Sessions/CELH Model/April 22nd Multi-Skill Framework Session.md` |
| This handoff | `C:/Users/rodin/Desktop/Brain/Sessions/CELH Model/April 22nd Novels Disambiguation Session.md` |

---

## How to create the next handoff

At the end of every session, write a new handoff under `C:/Users/rodin/Desktop/Brain/Sessions/{Task-Theme}/` following the exact structure below. This keeps every future "cold start" predictable — the next session picks up one file and knows everything it needs.

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
6. **`## Open decisions / pending work`** — numbered list of unresolved items. Each one should state the *decision* or *action* needed, not just a vague "look into X". If a decision is blocked on user input, say so.
7. **`## Key file paths`** — two-column table: Purpose | Path. Use absolute paths. Include scheduled task names and external system references.
8. **`## How to create the next handoff`** — paste this exact section verbatim. Never drop it; never let the template drift without updating all copies forward.

### Quality bar

- Write so the next session (cold, no conversation history) can act without re-asking you questions.
- Prefer concrete over abstract.
- Capture *why* a design choice was made when it's non-obvious. Code shows what; handoffs should show why.
- If you deleted, renamed, or moved files, explicitly mention it — the next session will otherwise hunt for the old paths.
- Keep it self-contained. Don't say "as discussed" — write out the discussion outcome.
