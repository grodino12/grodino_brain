---
name: mda-disaggregation
description: |
  Extract structural footnote disclosure tables from a ticker's 10-K / 10-Q iXBRL filings and produce a
  standalone {TICKER}_disclosures.xlsx workbook. Axis-driven extraction — no label heuristics, no static
  taxonomies. Each disclosure table reads from XBRL axes the filer already tagged; output shape mirrors
  whatever members the filer disclosed. Per-ticker quirks (member aliases, skip flags, filer-extension
  concepts) live in `Ticker Libraries/{TICKER}/MDA and Other/disclosure_overrides.json`. Hand-curated
  filer-specific narrative content (SG&A walks, GP qualitative drivers — content with no XBRL substrate)
  lives in `Ticker Libraries/{TICKER}/MDA and Other/mda_narrative.json` and gets rendered as a
  filer-specific section, never enforced cross-ticker.
when_to_use:
  - User wants to extract / compare disclosure tables (segments, geography, customer concentration,
    M&A pro forma, debt schedule, SBC awards, tax disclosure, PP&E by class, intangibles by class,
    goodwill rollforward, future amortization, ROU assets) across one or more tickers.
  - User asks to refresh `{TICKER}_disclosures.xlsx` after onboarding a new filing.
  - User needs to triage a filer-specific axis or extension concept that the generic library
    doesn't yet cover (surface as novel; user adds to disclosure_overrides.json).
---

# MDA Disaggregation skill

Builds a standalone `{TICKER}_disclosures.xlsx` containing axis-driven structural disclosure tables, plus
a per-ticker filer-specific section rendered from `mda_narrative.json`. Designed to grow as new
disclosure tables are added to the generic library.

## Architecture

Three library surfaces (mirrors the existing financials library pattern):

| Library | Path | Role |
|---|---|---|
| **Generic disclosure tables** | `Brain\Knowledge\Model Schema\pattern_libraries\MDA and Other\generic_disclosure_tables.json` | Cross-ticker canonical disclosure-table definitions: required axes, concept priority lists, render shape. **No filer knowledge.** |
| **Per-ticker structural overrides** | `Brain\Knowledge\Model Schema\Ticker Libraries\{TICKER}\MDA and Other\disclosure_overrides.json` | Member alias normalization (e.g. PEP's `pep:PFNAMember` → "PepsiCo Foods NA"), skip flags (filer doesn't disclose this table), filer-extension concepts to treat as us-gaap-equivalent. **Auto-populated** by skill when novels are surfaced and user triages. |
| **Per-ticker filer-specific narrative** | `Brain\Knowledge\Model Schema\Ticker Libraries\{TICKER}\MDA and Other\mda_narrative.json` | Hand-curated content with no XBRL substrate (SG&A walks, GP qualitative drivers, Other Inc/Exp filer-specific decomposition). Filer-specific by design — never enforced cross-ticker. |

## Critical rules (carried from `feedback_structural_over_heuristic.md`)

1. **No new label-text regexes, keyword scans, or static concept allowlists** for cross-ticker logic. Generic library decisions must be derivable from XBRL structural signals (concept name, axis, member, label linkbase).
2. **Per-ticker overrides do NOT extend the generic library's taxonomy** — they handle member-level normalization, skip flags, and extension concepts only. New disclosure tables go in the generic library.
3. **Per-ticker narrative entries are explicitly heuristic-tolerant** because they don't drive automated routing — they're analyst captures, rendered as a filer-specific section labeled "Not standardized cross-ticker."

## Extraction flow

For each filing's iXBRL htm:

1. **Parse iXBRL** — extract every fact with `(concept, contextRef)`; resolve contextRef to `(period, [(axis, member), ...])`.
2. **For each disclosure table in the generic library:**
   a. Filter facts to those whose context carries the table's required axes.
   b. For each metric in the table's concept dict, walk the concept list left-to-right (first-match priority). Bucket by `(metric, member, period)`.
   c. Apply per-ticker overrides: skip if `skip: true`, alias members, accept extension concepts.
   d. Render to xlsx as a table block.
3. **Surface novels** — any axis the filing uses that the generic library doesn't cover, OR any member that doesn't match a canonical normalization, gets surfaced as a `NovelItem` for user triage. User decides: extend generic library (if cross-ticker) or extend per-ticker overrides (if filer-specific).
4. **Render per-ticker narrative** — read `mda_narrative.json`; render its content as a final clearly-labeled filer-specific section.

## Output workbook layout

Single sheet `Disclosures`. One section per disclosure table from the generic library, rendered in `section_order`. Each section: section header, period column headers, member rows × metric blocks (or table-specific shape). Source citations as cell notes (Shift+F2 style) with default openpyxl Comment dimensions.

Final section "Filer-Specific (Not Standardized)" rendered from `mda_narrative.json` if it exists.

**Engineering rules** (carried from prior implementation, all earned the hard way):

- **Standalone workbook only.** Never a sheet inside a workbook with external links — openpyxl renumbers external-link rIds on save and corrupts the file.
- **Default Comment dimensions.** Setting `comment.width`/`comment.height` triggers Excel's "we found a problem" repair warning.
- **No merged cells.** Section headers go in column A only.
- **Number format:** `'#,##0;(#,##0);"--"'` for $ thousands, `'0.0%;(0.0%);"--"'` for %.

## Files

| File | Purpose |
|---|---|
| `SKILL.md` | This document |
| `scripts/build_disclosures_workbook.py` | Generic builder. Reads library + per-ticker overrides + per-ticker narrative; outputs xlsx |

## Roadmap (per ROADMAP.md)

| Phase | Scope | Status |
|---|---|---|
| 0 | Folder reorganization | ✓ shipped 2026-05-09 |
| 1 | Library scaffold + Segment P&L on CELH | **active** |
| 2 | Port 4 original sections (geography, customer, pro forma, brand — axis-driven) | pending |
| 3 | Add 3 new structural sections (debt, SBC, tax) | pending |
| 4 | Absorb depreciation extraction (PP&E, intangibles, goodwill, future amort, ROU) | pending |
| 5 | Cross-ticker validation (PEP, MNST end-to-end) | pending |
| 6 | Cleanup + handoff | pending |
| 7+ | (Future) Model-feeding bridge — model-calc consumes rollforwards from this skill's output | future |
