---
type: session-handoff
date: 2026-04-22
topic: FY2024 10-K end-to-end validation (35/35) + multi-filing playground polish (period dedup, canonical section ordering, CF-3/4/5 section-sum validators, supplemental/mezzanine/FX display remaps, architecture + schema playgrounds updated)
tags: [session, celh, multi-skill, playground, validate, cf-section-sums]
---

# April 22nd — Playground Polish Session

Third handoff of the day. Picks up from `April 22nd Novels Disambiguation Session.md`, which ended with 16 ledger entries committed for all 14 FY2024 10-K novels but the pipeline not yet re-run. This session ran end-to-end, then iterated on playground rendering quality and added three new CF validators.

## Starting state

- 16 ledger entries freshly committed to `CELH/decisions_ledger.json` covering all 14 unique novels from the FY2024 10-K walkthrough (MAP-BS-029..033, MAP-IS-031/032, MAP-CF-073..078, NEW-IS-003, NEW-CF-009/010).
- Pipeline code updated during the prior session: `subsection_context` field on RawLineItem, subtotal-driven BS section flips in extract, `filing_section` discriminator in reconcile, footnote-marker stripping.
- FY2023 10-K (`validated_2024_10K.json`) validated 26/26. FY2024 10-K mapped+validated JSONs either stale or blocked by novels — pipeline had not been re-run with the new entries.
- Playground (`financials-playground`) built in the first session, showed FY2023 10-K only with all 14 novels in the NOVELS tab.
- User explicitly deferred FY2025 work at the end of the prior session.

## Work done this session

### 1. Pipeline re-run end-to-end on FY2024 10-K

All 14 novels cleared with the new ledger entries. Results:
- Extract: 8 Statement objects, 263 line items
- Reconcile: 193 mapped to existing rows + 55 new_rows + 15 subtotals + **0 novels**
- Validate: 35/35 PASS (was 26 before CF-3/4/5 added — see §4)

FY2023 10-K also re-validated against the updated pipeline: 35/35 PASS. Both filings clean end-to-end.

### 2. Period dedup across filings in the playground

Walking buckets from both the FY2023 and FY2024 10-Ks produced duplicate `FY2023` and `FY2022` columns (those periods appear in both filings as comparatives). Added `dedupe_buckets_by_period` that groups buckets by `(statement_type, period_end_date)` and keeps the one from the filing with the latest `filing_date`. Newer filings win for overlapping periods, consistent with GAAP restatement convention.

Columns now render uniquely as `FY2024 / FY2023 / FY2022 / FY2021` (FY2021 only appears via the FY2023 10-K's oldest comparative since BS doesn't span back that far).

### 3. Canonical section ordering (prevented duplicate section dividers)

Before: rows that only appeared in the older filing got high `first_seen` and sorted last, landing *after* whichever section was last rendered — which triggered a fresh section divider for the "same" section. Screenshot showed CF ending with duplicate "OPERATING ACTIVITIES" and "FINANCING ACTIVITIES" headers at the bottom.

Added a `SECTION_ORDER` map keyed by canonical section slugs (BS 10-60, CF 100-140, IS 200-240, unclassified 999) and made `ordered_keys.sort` use `(SECTION_ORDER[section], ...)` as the primary key. Each section now renders exactly once, with items grouped under their canonical section regardless of which filing they came from.

### 4. CF-3 / CF-4 / CF-5 section-sum validators

User request: "There should be a validation rule for CF that the sum of all items within each section (operating, investing, financing) equal the reported figure from their financials."

Added `partition_cash_flow(items)` to `validate.py` — walks items in document order, using the "Net cash provided by / used in X activities" rows as section-boundary anchors. Everything after the financing sum (FX effect, Net Change in Cash, Cash at Beg/End, Supplementals) is classified as below-the-line and excluded.

Three new rules:
- **CF-3:** sum(operating items) = Net Cash from Operating Activities
- **CF-4:** sum(investing items) = Net Cash from Investing Activities
- **CF-5:** sum(financing items) = Net Cash from Financing Activities

All 9 new rule instances (3 rules × 3 CF periods per filing) PASS on both filings. This catches extraction errors where a row is missed or duplicated: e.g. if pdfplumber drops one financing line, CF-5 fails by exactly that row's value.

### 5. Visual subtotal promotion in the playground

CF "sum" rows were rendering as plain line items, making each section's total visually indistinguishable from its activities. Added logic in `pivot_statement` to promote rows whose `model_label` starts with "Cash Flow from " (or equals "Net Change in Cash", or starts with "Cash at ") from `kind: "item"` to `kind: "subtotal"` for display — they now render bold with the `tr.subtotal` blue-tinted styling. The underlying MappedLineItem stays `row_type: "line_item"` so model-write still knows the `model_row`.

Also extended the within-section sort to `(SECTION_ORDER[section], is_subtotal, model_row_or_first_seen)` — regular activity items first (by first-seen order), then subtotals sorted by `model_row` ascending. This puts Cash Flow from X at the end of its section, followed by the cash rollup rows (Net Change → Cash Beg → Cash End) in proper order.

### 6. Supplemental Disclosures carved into their own section

Raw-label rows starting with `"Supplemental:"` on the CF get their display section remapped from `financing` (which is how extract tagged them) to a new `supplemental` section (SECTION_ORDER 140, label "Supplemental Disclosures"). This is GAAP convention — supplementals are below-the-line memo items, not part of any activity. `SECTION_LABEL` + `SECTION_ORDER` extended accordingly.

### 7. Mezzanine displayed inside Stockholders' Equity

User request: mezzanine preferred stock should show under Stockholders' Equity, not as its own section. Added a display-only remap in `pivot_statement`: if statement is BS and item's section is "mezzanine", override to "equity" for display. **BS-6 (accounting equation) still treats Mezzanine as a separate term** for the TA = TL + Mezz + TSE math, honoring `anomalies.json`'s `mezzanine_equity.excluded_from_total_se: true`.

### 8. FX Effect on Cash moved into Financing section (display)

User: "FX Effect on cash needs to actually be in the Cash Flow from financing section above the subtotal." Added a playground remap: CF items with section `fx_reconciliation` get display-remapped to `financing`. With the subtotal-last within-section sort from §5, FX Effect now lands above the Cash Flow from Financing subtotal. The CF-1/CF-5 validators still treat FX as a separate reconciling item for arithmetic (matches GAAP: `CFO + CFI + CFF + FX = ΔCash`).

### 9. NOVELS tab in the playground

Added earlier in the session before the walkthrough. `reconcile.py` gained `--novels-out <path>` flag that writes a NovelReport JSON (per-novel raw item + period context + fuzzy candidates) regardless of pass/fail/dry-run state. `build_playground.py` gained `--novels-in <path>` (repeatable) that renders a red-badged NOVELS tab grouping novels by `(statement_type, raw_filing_label, subsection_context)` — shows sheet badge, section/subsection, raw label, period occurrences with values, top 3 fuzzy candidates with scores, and first-occurrence page citation. User walks the list by `#N` and designates targets by chat.

### 10. MAP-CF-063 → NEW-CF-011 conversion ("Proceeds from Common")

User: "Create it as a new row above Proceeds from Preferred and call it Proceeds from Common." The existing MAP-CF-063 was a placeholder mapping with `model_row: 0` and label "Net Proceeds from Common Stock Sale (new)". Kept for backward compat but renamed its `model_label` to "Proceeds from Common", and added NEW-CF-011 as the canonical new-row entry with `position_note`: *"Insert as new row immediately ABOVE Proceeds from Preferred (currently row 42). After insert, model-write should bump existing rows 42+ down by 1 and assign model_row to this entry."* When model-write runs, NEW-CF-011 becomes a ManualInsertPlan entry.

### 11. Naming-convention memory + EDGAR FY2025 discovery

User corrected "stop referring to them as the year in which they were filed. Financials are always always always referred to regarding the period they are reporting for." Saved to `~/.claude/projects/C--Users-rodin/memory/feedback_financial_period_naming.md` and indexed in MEMORY.md. FY2023 10-K (not 2024 10-K), FY2024 10-K (not 2025 10-K), etc.

Briefly attempted to pull FY2025 10-K from EDGAR. Found it: accession `0001341766-26-000024`, filed 2026-03-02, primary doc `celh-20251231.htm`. EDGAR hosts it as HTML only — no PDF. Would need an HTML→PDF conversion step (weasyprint / playwright — neither installed). User then pointed out we already have `2025_CELH_10-K.pdf` locally (which is the FY2024 10-K), so deferred FY2025 for this session.

### 12. Architecture + schema playgrounds updated

Both meta-playgrounds (`playground_architecture.html` and `playground_schema.html`) refreshed to reflect everything shipped:

Architecture:
- `financials-playground` node flagged `built: true`, deps `['python stdlib only']`, ops updated (5 tabs incl. NOVELS, period dedup, subtotal promotion, unit hints)
- `financials-extract` ops updated: unit-phrase exclusion parsing, subsection-header detection, BS subtotal section flips, IS keyword classifier
- `financials-reconcile` ops updated: list-of-candidates lookup, `select_entry` subsection/section scoring, footnote stripping, `--novels-out`
- `financials-validate` ops updated: BS-1..6, CF-1/2, CF-3/4/5, X-1/2/4
- `decisions-ledger` purpose updated: 124 mappings + 24 new rows + 7 structural + 1 rename (up from 29/17/7/0), explicit mention of `filing_subsection` / `filing_section` discriminators
- `MappedFiling` note mentions `subsection_context` on RawLineItem

Schema:
- `RawLineItem` card lists the new `subsection_context: str | None = None` field
- `Statement` doc explains how `share_unit` / `eps_unit` are derived from unit-phrase exclusions
- `ValidationResult` doc enumerates the current rule families (BS-1..6, CF-1/2, CF-3/4/5, X-1/2/4; BS-7 deferred)
- `NovelItem` doc mentions `--novels-out` + the playground NOVELS tab

### 13. Global Claude Code statusline configured

Added `statusLine` command at `~/.claude/settings.json` pointing to `~/.claude/statusline-command.sh`. Script reads JSON from stdin (hook protocol), shows context-window percentage + absolute tokens used + window size. Format: `ctx: 28% (554k/1M)` once API calls accumulate. Works in Git Bash on Windows.

## Current state

### Built and verified
- All 4 skills (`financials-extract`, `financials-reconcile`, `financials-validate`, `financials-playground`) in working order
- Shared schema package `financials-schema` — 16/16 pytest pass
- FY2023 10-K: 35/35 validation rules pass
- FY2024 10-K: 35/35 validation rules pass
- Multi-filing playground renders clean: unique period columns (FY2024/FY2023/FY2022/FY2021), canonical section ordering, subtotal styling, supplementals carved out, mezzanine in SE, FX in financing

### Not yet built
- **`model-write`** — the payoff step. Takes a ValidatedFiling + xlsm path, writes values into the CELH model (preserving macros + formulas), backs up original, emits ManualInsertPlan for new_rows entries.
- **`model-calc`** — derived calcs + scenario overlay. User previously scoped down to: growth/margins/WC ratios only; GLP-1 and SNAP overlays deferred.

### Rule coverage matrix (union across both filings)

| Period | BS rules | CF rules | X rules |
|---|---|---|---|
| FY2024 | BS-1..6 | CF-1..5 | X-1, X-2, X-4 |
| FY2023 | BS-1..6 | CF-1..5 | X-1, X-2, X-4 |
| FY2022 | BS-1..6 | CF-1..5 | X-1, X-2, X-4 |
| FY2021 | — | CF-1..5 | X-1, X-4 |

FY2021 BS gaps exist because no loaded filing contains FY2021 BS (the `2022_CELH_10-K.pdf` would — that's the FY2021 10-K — but it's blocked on 39 older-era-wording reconcile novels per the first handoff).

## Pipeline invocation (copy-paste to resume)

```bash
cd "C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema"
source financials-schema/.venv/Scripts/activate

# Extract + reconcile + validate FY2023 10-K (file: 2024_CELH_10-K.pdf)
PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/financials-extract/scripts/extract.py" \
    --ticker-root "CELH/" \
    --pdf "C:/Users/rodin/Desktop/Pl3 Celsius Case Study/data/CELH Reporting/Financial Statements/2024_CELH_10-K.pdf" \
    --out "CELH/Model Output/raw_2024_10K.json" \
    --filing-type "10-K" --filing-date "2024-02-29"
PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/financials-reconcile/scripts/reconcile.py" \
    --ticker-root "CELH/" --in "CELH/Model Output/raw_2024_10K.json" --out "CELH/Model Output/mapped_2024_10K.json"
PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/financials-validate/scripts/validate.py" \
    --ticker-root "CELH/" --in "CELH/Model Output/mapped_2024_10K.json" --out "CELH/Model Output/validated_2024_10K.json"

# Extract + reconcile + validate FY2024 10-K (file: 2025_CELH_10-K.pdf)
PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/financials-extract/scripts/extract.py" \
    --ticker-root "CELH/" \
    --pdf "C:/Users/rodin/Desktop/Pl3 Celsius Case Study/data/CELH Reporting/Financial Statements/2025_CELH_10-K.pdf" \
    --out "CELH/Model Output/raw_2025_10K.json" \
    --filing-type "10-K" --filing-date "2025-02-27"
PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/financials-reconcile/scripts/reconcile.py" \
    --ticker-root "CELH/" --in "CELH/Model Output/raw_2025_10K.json" --out "CELH/Model Output/mapped_2025_10K.json"
PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/financials-validate/scripts/validate.py" \
    --ticker-root "CELH/" --in "CELH/Model Output/mapped_2025_10K.json" --out "CELH/Model Output/validated_2025_10K.json"

# Multi-filing playground
python "C:/Users/rodin/.claude/skills/financials-playground/scripts/build_playground.py" \
    --in "CELH/Model Output/validated_2024_10K.json" \
    --in "CELH/Model Output/validated_2025_10K.json" \
    --out "CELH/Model Output/explorer_multi.html"
```

## Open decisions / pending work

1. **Build `model-write` (Layer 4, part 2).** This is the payoff milestone — takes the two validated JSONs and writes values into `CELH Financial Model.xlsm`. Requirements from the original design (see `02_pipeline_design.md`): `keep_vba=True`, never `cell.fill = None`, `.bak` backup before any write, emit `ManualInsertPlan` for new_rows (user inserts rows in Excel first to preserve cross-sheet formulas), save to `_updated.xlsm` filename, verify-after-save with `#REF!` grep. NEW-CF-011 is a good first test case for the ManualInsertPlan flow.
2. **Assign `model_row` to NEW-CF-011 after first model-write run.** The position_note says "immediately ABOVE Proceeds from Preferred (currently row 42). After insert, model-write should bump existing rows 42+ down by 1 and assign model_row to this entry." model-write should prompt user, do the insert, then write back `model_row: 42` into NEW-CF-011 and bump downstream entries.
3. **Pull FY2025 10-K from EDGAR.** Accession `0001341766-26-000024`, HTML-only at `https://www.sec.gov/Archives/edgar/data/1341766/000134176626000024/celh-20251231.htm`. Need an HTML→PDF step. Options: `pip install weasyprint` (GTK deps on Windows painful) or `pip install playwright && playwright install chromium` (larger install but reliable). Alternatively teach extract to parse HTML directly — bigger refactor.
4. **FY2021 BS gap.** Would close if we process `2022_CELH_10-K.pdf` (the FY2021 10-K). Blocked on 39 older-era-wording reconcile novels per the first handoff's architectural TODO. Not urgent for current scope.
5. **BS-7 RE roll-forward validator** still deferred — needs prior-period BS data cross-filing.
6. **BS section-header detection still fragile for older-era filings.** The subtotal-flip fix (CA→NCA, CL→NCL) works for modern 10-Ks but doesn't handle filings that use explicit "Non-current assets:" headers differently, or that split TL→Mezz→Equity via different subtotal patterns. Non-blocking until older filings are loaded.
7. **`Acquisition of Big Beverages` label truncation** — pdfplumber column-width artifact truncates to `"... L.L.C., net of cash acquired"` or similar. NEW-CF-009 uses the full normalized form; if a future extract produces a different truncation, the entry may need adjustment. Not critical.
8. **Build `model-calc` (Layer 4, part 3).** Simplified scope per prior sessions: YoY/QoQ growth, margins (GP/OP/NI), working-capital ratios (DSO/DIO/DPO/CCC), base scenario only. GLP-1 and SNAP overlays explicitly deferred.

## Key file paths

| Purpose | Path |
|---|---|
| Pipeline architecture map (playground, updated this session) | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/playground_architecture.html` |
| Pydantic schema map (playground, updated this session) | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/playground_schema.html` |
| Design docs (01–04) | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/0{1..4}_*.md` |
| Shared Pydantic package | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/financials-schema/` |
| Shared pattern libraries | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/pattern_libraries/*.json` |
| CELH ticker config | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/CELH/config.json` |
| CELH anomalies | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/CELH/anomalies.json` |
| CELH decisions ledger | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/CELH/decisions_ledger.json` |
| CELH derived outputs (raw/mapped/validated/novels) | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/CELH/Model Output/` |
| Multi-filing explorer HTML (today's output) | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/CELH/Model Output/explorer_multi.html` |
| Extract skill | `C:/Users/rodin/.claude/skills/financials-extract/` |
| Reconcile skill | `C:/Users/rodin/.claude/skills/financials-reconcile/` |
| Validate skill | `C:/Users/rodin/.claude/skills/financials-validate/` |
| Playground skill | `C:/Users/rodin/.claude/skills/financials-playground/` |
| Claude Code statusline config | `C:/Users/rodin/.claude/settings.json` (`statusLine` field) + `C:/Users/rodin/.claude/statusline-command.sh` |
| Naming-convention memory | `C:/Users/rodin/.claude/projects/C--Users-rodin/memory/feedback_financial_period_naming.md` |
| FY2025 10-K on EDGAR (HTML-only) | `https://www.sec.gov/Archives/edgar/data/1341766/000134176626000024/celh-20251231.htm` |
| First session handoff | `C:/Users/rodin/Desktop/Brain/Sessions/CELH Model/April 22nd Multi-Skill Framework Session.md` |
| Second session handoff | `C:/Users/rodin/Desktop/Brain/Sessions/CELH Model/April 22nd Novels Disambiguation Session.md` |
| This handoff | `C:/Users/rodin/Desktop/Brain/Sessions/CELH Model/April 22nd Playground Polish Session.md` |

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
