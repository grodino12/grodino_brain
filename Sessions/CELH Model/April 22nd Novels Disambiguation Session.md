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

## User's novel designations (FY2024 10-K — all 14 given, all committed to ledger)

All entries were written to `CELH/decisions_ledger.json` before session end. Order matches the playground's NOVELS tab numbering (BS first alphabetical, then IS, then CF).

| # | Raw label (sheet · section) | User rule | Ledger entry written |
|---|---|---|---|
| #1 | `Deferred revenue[2]` (BS · current_liabilities) | Above TCL → current; below TCL → NC | MAP-BS-029 `"deferred revenue"` + `filing_section: "current_liabilities"` → row 35; MAP-BS-030 + `"non_current_liabilities"` → row 42 |
| #2 | `Lease liability finance leases` (BS · current_liabilities) | Same above/below TCL rule | MAP-BS-031 + current → row 34; MAP-BS-032 + NC → row 40 |
| #3 | `Note receivable-net` (BS · current_assets) | Same row as existing Note Receivable-Net Current | MAP-BS-033 → row 12 "Note Receivable" |
| #4 | `Interest income, net` (IS · non_operating) | Same as `Interest income (expense), net` — paren denotes sign convention | MAP-IS-031 `"interest income net"` → row 17 "Interest Income" |
| #5 | `Net income (loss) before provision for income taxes` (IS · non_operating) | Top fuzzy (implied — user batched with #8-#12) | MAP-IS-032 → row 20 "Pre-Tax Income" |
| #6 | `Other income` (IS · non_operating) | New line item | NEW-IS-003 → new_row "Other Income" in non_operating, position after row 18 |
| #7 | `Acquisition of Big Beverages Contract Manufacturing L.L.C., net of cash acquired` (CF · investing) | New row | NEW-CF-009 → new_row "Acquisition of Big Beverages" in investing |
| #8 | `Cash and cash equivalents at beginning of the period` (CF · financing) | Top fuzzy | MAP-CF-073 → row 50 "Cash at Beginning" |
| #9 | `Cash and cash equivalents at end of the period` (CF · financing) | Top fuzzy | MAP-CF-074 → row 51 "Cash at End" |
| #10 | `Cash dividends paid on Series A convertible preferred stock[2]` (CF · financing) | Top fuzzy | MAP-CF-075 → row 43 "Dividends Paid on Preferred" |
| #11 | `Change in right of use asset and lease liability-net` (CF · operating) | Top fuzzy | MAP-CF-076 → row 28 "Delta ROU/Lease" |
| #12 | `Inventories` (CF · operating) | Top fuzzy | MAP-CF-077 → row 22 "Delta Inventories" |
| #13 | `Net increase in cash and cash equivalents` (CF · financing) | Third fuzzy (the `net increase decrease in cash ... and restricted cash` candidate — first/second were FX Effect and Cash End which are wrong) | MAP-CF-078 → row 48 "Net Change in Cash" |
| #14 | `Note receivable-net` (CF · operating) | First fuzzy (`note receivable-net change` = existing NEW-CF-003 Δ Note Receivable) | NEW-CF-010 → new_row "Delta Note Receivable" (same concept as NEW-CF-003; kept separate since normalized forms differ) |

Note `#5` and `#6` were not mentioned verbatim by the user — but the flow was "#7 should be a new row. #8 and 9,10,11,12 should be the top fuzzy match" + earlier "Other Income should be its own new line item". I filled in #5 → top fuzzy (consistent with the batch rule) and #6 → new line item (matching "Other Income" note). If either is wrong the next session should correct MAP-IS-032 or NEW-IS-003.

**Next session first task:** re-extract + re-reconcile + re-validate the FY2024 10-K (pipeline commands below), then re-render the playground merging both filings. If reconcile still flags novels after these 16 entries, walk through them.

## Current state

### Built / verified
- All 4 skills (extract, reconcile, validate, playground) updated with the new disambiguation mechanisms
- Shared schema updated (`subsection_context` on RawLineItem) — 16/16 pytest pass
- FY2023 10-K still passes 26/26 validation with new IS classifier + section labels
- Playground renders BS · IS · CF · VALIDATION · **NOVELS** tabs correctly

### Pending
- **Pipeline not yet re-run on FY2024 10-K after the 16 new ledger entries.** Next session must re-extract + re-reconcile + re-validate + re-render (commands below). If reconcile clears 0 novels, great — validators should run and playground will merge both filings.
- **Extract side fix pending for `Acquisition of Big Beverages`**: pdfplumber truncated the raw label to `"... L.L.C., net of cash acquired"`. The normalized form used in NEW-CF-009 is the full version. If the next extract pulls a different truncation, the entry may need adjustment. Root cause is probably pdfplumber table-cell width limit — not urgent.
- **X-2 validator** may need a fresh check once FY2024 is validated. `anomalies.json` already has `cash_convention_per_year[2024]=cash_only` which is correct for FY2024 (the 10-K no longer separates restricted cash). No action needed unless X-2 fails.
- **No quarterly filings (10-Q) run yet** — the pipeline assumes annual periods. FY2024 quarter data would require a separate 10-Q pass.

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

1. **Run the pipeline end-to-end on the FY2024 10-K with the new ledger entries.** Commands in the section below. Expected outcome: reconcile clears to 0 novels, validate runs, playground merges both filings showing FY2024 + FY2023 + FY2022 across all tabs.
2. **Verify user's implied designations for #5 and #6** — the user batched "#8-#12 top fuzzy" but #5 and #6 fell between explicit instructions. I interpreted: #5 → top fuzzy (row 20 Pre-Tax Income) and #6 → new row "Other Income" (matching user's earlier message about Other Income). If either is wrong, correct MAP-IS-032 or NEW-IS-003.
3. **FY2024 BS section-header detection for 2nd-half transitions**. The subtotal-flip fix handles CA→NCA and CL→NCL but not TL→Mezz or Mezz→Equity. Not blocking on FY2024 10-K — CELH's equity section has explicit headers the existing pattern lib catches. Flag for older-era filings.
4. **`Acquisition of Big Beverages` label truncation** — pdfplumber column-width artifact. Not blocking. Future: look at adjusting pdfplumber table settings.
5. **BIG ARCHITECTURAL TODO (carry-forward from prior handoff)**: multi-era reporting-style drift. Partially addressed this session (filing_section / filing_subsection / footnote stripping), but long-term still want a filing-era adapter or multi-variant ledger design. Re-read section 10 of the prior handoff.
6. **BS-7 RE roll-forward validator** still not implemented.
7. **Model-write (Layer 4 part 2)** — next milestone after FY2024 10-K fully validates.
8. **FY2025 data** — the 2026-filed 10-K (reporting FY2025) is on EDGAR (accession 0001341766-26-000024, primary doc `celh-20251231.htm`) but EDGAR only hosts it as HTML, no PDF. Would need an HTML→PDF conversion step (weasyprint / playwright) or HTML-aware extract to process. Not urgent — user deferred FY2025 in this session.

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
