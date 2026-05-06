---
name: mda-disaggregation
description: |
  Extract MD&A disclosures from a ticker's 10-Q + 10-K filings and produce a standalone {TICKER}_MDA.xlsx workbook
  with revenue disaggregation, customer concentration, brand/segment contribution, pro forma analysis, SG&A walk,
  GP qualitative drivers, and Other Inc/Exp walk. All sections transposed (periods as columns, metrics as rows).
  Q4 columns derived from FY - 9M YTD where arithmetically possible (i.e., $ values, not percentages).
when_to_use:
  - User wants to build a clean revenue/P&L decomposition from filings for any covered ticker
  - User asks "where does revenue come from" / "show me the SG&A walk" / "is there a brand split"
  - Output workbook references a model workbook (do NOT modify the model workbook itself with openpyxl)
---

# MD&A Disaggregation skill

Builds a standalone `{TICKER}_MDA.xlsx` containing 8 sections of MD&A-extracted data, formatted for analyst review.

## Output workbook layout

Single sheet named `MD&A`. Periods as columns (typically 12-15: Q1 YYYY through FY YYYY for each year covered).
Q4 inserted between Q3 and FY of each year, derived as formula `=FY - Q1 - Q2 - Q3` for $ values.
Source citations as cell notes (Shift+F2 style) with default openpyxl Comment dimensions.

### Sections

| # | Section | Q4 derivable? |
|---|---|---|
| 1 | Geography ($ thousands, single-period) | ✓ formula |
| 2 | Customer concentration (% of revenue) | ✗ percentages cannot be subtracted |
| 3 | Functional / product concentration (% of revenue) | ✗ same |
| 4 | Brand contribution ($ thousands, post-acquisition periods only) | ✓ formula; Celsius/legacy = residual |
| 5 | Pro Forma vs As-Reported (custom layout) | n/a |
| 6 | SG&A walk ($ Δ, hierarchical M&S vs G&A grouping) | ✓ formula on totals; sub-rows derived from FY-9M where both disclosed |
| 7 | Gross profit + margin + qualitative drivers | ✓ GP $ formula; margin = GP$/Revenue; drivers stay blank for Q4 |
| 8 | Other Inc/Exp walk | ✓ formula |

## Critical engineering rules

These are non-negotiable — every one was learned the hard way:

1. **Standalone workbook only.** Do NOT add MD&A as a sheet inside a workbook that has external links (openpyxl re-renumbers external-link rIds on save and corrupts the file). Output is always `Brain\Knowledge\Model Outputs\{TICKER}\{TICKER}_MDA.xlsx`.

2. **Default comment box dimensions only.** Setting `comment.width` or `comment.height` triggers Excel's "we found a problem" repair warning. Use `Comment(text, author)` with no size kwargs.

3. **No merged cells.** Section headers / notes go in column A only.

4. **Periods as columns, metrics as rows.** Always. Period column order: `Q1 YYYY, Q2 YYYY, Q3 YYYY, Q4 YYYY, FY YYYY` for each year.

5. **Q4 derivation is for $ values only.** Customer % and product concentration % rows cannot be derived for Q4. Show `n/d` with cell note "Q4 NOT derivable: percentages cannot be subtracted."

6. **GP margin Q4** = `GP$_Q4 / Revenue$_Q4`, NOT `FY% - 9M%`.

7. **Cell notes always on hardcoded value cells** with format `{filing} {section}: {verbatim quote or short attribution}`. Formulas get notes only if the derivation is non-obvious.

8. **Number format for $thousands**: `'#,##0;(#,##0);"--"'`. For %: `'0.0%;(0.0%);"--"'`.

9. **Source values from MD&A narrative are rounded** to nearest $0.1M ($100K precision). The `validated_*.json` files have exact IS line values if a user asks to swap totals to dollar precision.

## SG&A walk hierarchy (Section 6)

Match the filer's natural disclosure structure. CELH (and most consumer staples) discloses:

```
Total SG&A
YoY Total Δ

  MARKETING & SELLING Δ          (subtotal — formula = sum of M&S sub-rows)
    Marketing investments / campaigns
    Storage / Distribution
    Sales/Marketing Employee
    Acquired-brand attributable (e.g., Alani Nu M&S)
    Other selling
    
  GENERAL & ADMIN Δ              (subtotal — formula = sum of G&A sub-rows)
    Administrative expenses (legacy general admin)
    Acquisition / Integration costs
    Acquired-brand attributable (e.g., Alani Nu G&A)
    Contingent consideration remeasurement
    Legal accrual / settlement
    Stock-based compensation (legacy era)
    Other admin

Distributor Termination Δ        (special — was inside SG&A in some eras; separate IS line in others)

Σ Buckets check                  (= M&S subtotal + G&A subtotal + Distrib Term)
```

Pre-2025 (or pre-acquisition) periods often DON'T split between M&S and G&A — the disclosure is flat (Marketing + Storage + Employee + Admin + Stock comp). Map those values into the closest M&S vs G&A bucket. Pre-acquisition Employee costs typically go under M&S.

## Q4 derivation logic

The 9M YTD walk lives in each filer's Q3 10-Q (the "Nine months ended ... compared to nine months ended ..." section). Pull it for each year. Then Q4 = FY - 9M for any bucket that BOTH disclosures break out separately. If 9M lumps into "all other SG&A" but FY breaks out, leave the Q4 cell blank — don't synthesize from incomplete data.

Distributor termination behaves specially: when the prior comparable year had termination fees and the current year doesn't, a NEGATIVE delta appears (e.g., FY2023 distrib_term = -$181M because FY2022 had +$193.8M one-time). In recent years (CELH 2025), distributor termination became a separate IS line — track that on its own row outside the SG&A walk.

## Brand contribution (Section 4)

Only populate periods AFTER the acquisition closed. Pre-acquisition periods are 100% the legacy brand.

For the residual brand (e.g., Celsius for CELH), formula = `Total Revenue - Acquired Brand 1 - Acquired Brand 2 ...`.

Acquired brand contribution comes from:
- **Note 5 (Acquisitions)** — direct $ disclosure for partial periods ("contributed approximately $X.X million for the period from Closing Date through ...")
- **MD&A narrative** — "Alani Nu Acquisition contributed approximately $332.0 million of revenue" in Results of Operations
- **Item 9A (Controls and Procedures)** — "Alani Nu represented approximately X.X% of consolidated revenue for ..." (use as cross-check)

These three should agree to within rounding; cite all three in the cell note.

## Pro forma (Section 5)

Mandatory disclosure under ASC 805 when a material acquisition closes. Find in Note 5 of the filing covering the close period and subsequent ones. Format: as-if both acquisitions had closed Jan 1 of prior year. Disclosed for Q3, 9M, and FY periods at minimum.

## Workflow

```
1. Identify filings for ticker:
   Brain\Sources\{TICKER}\{YYYY-Qn or YYYY-FY}\filings\*.htm

2. Extract MD&A regions (Results of Operations) + footnote regions (Note 4 Revenue, Note 5 Acquisitions, Concentrations of Risk, Item 9A Controls).
   Anchor terms to grep:
     - "amount of revenue by geographical" / "amount of revenues by geographical"
     - "Revenue from customers accounting for more than"
     - "[Ff]unctional energy drink product revenue accounted"  (or analogous wording for non-CELH)
     - "Gross [Pp]rofit" + "increased by" / "decreased by"
     - "Selling, [Gg]eneral and [Aa]dministrative [Ee]xpenses" + "increase of" / "decrease of"
     - "Other (Income|Expense)" + "increased" / "primarily attributable"
     - Acquisition narrative: "Acquisition .{1,80}contributed approximately"
     - Pro forma: "[Pp]ro forma" + "Revenue $"
     - Item 9A: "represented approximately .{1,80}consolidated revenue"

3. Populate `data/{TICKER}.json` per the schema in `data/schema.md`.

4. Run `scripts/build_mda_workbook.py --ticker {TICKER}` to generate `Brain\Knowledge\Model Outputs\{TICKER}\{TICKER}_MDA.xlsx`.
```

## Iteration on disclosure variations

Different filers structure SG&A walks differently. The skill's bucket taxonomy (Section 6) is intentionally broad to accommodate variation. When a new ticker introduces a bucket not in the canonical list, add a row and document the mapping decision in `data/{TICKER}.json` with a `taxonomy_notes` field.

When CELH (or any ticker's) disclosure structure CHANGES across years (CELH did this in 2025 — moved from flat list to M&S/G&A split), preserve both views: pre-change rows go under the closest analog bucket; post-change rows use the canonical hierarchy.

## Files

| File | Purpose |
|---|---|
| `SKILL.md` | This document |
| `scripts/build_mda_workbook.py` | Generic builder. Reads `data/{TICKER}.json`, outputs xlsx |
| `data/schema.md` | JSON schema documentation |
| `data/CELH.json` | First reference instance |
