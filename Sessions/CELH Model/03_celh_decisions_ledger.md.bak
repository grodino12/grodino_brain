# CELH Model Update — Decisions Ledger

This file records every reconciliation, mapping, and structural decision made during CELH model updates. It is the **persistent memory** for the `celh-model-update` skill. Each time the skill runs Phase 1.5 (Reconciliation), it loads this file and auto-applies any matching rule before prompting the user.

**How rules are applied:**
1. At the start of Phase 1.5, parse this file into a lookup table keyed by `(statement, normalized_filing_term)`
2. For each extracted line item, check the lookup table FIRST
3. If a rule matches → apply automatically and log the auto-application in the citations doc (do NOT prompt user)
4. If no rule matches → prompt the user as usual, then APPEND the new decision to this file

**How rules are written:**
Append-only by default. To change a decision, add a new entry with a `superseded_by` note on the old one. Don't delete history — future audit may need to know "we used to do X, then changed to Y on date Z."

**Normalization for matching:** filing terms are matched case-insensitive, with whitespace and punctuation collapsed. So "Cost of revenue", "cost of revenue", and "Cost of Revenue" all match the same rule.

---

## Section A: Income Statement Rules

### A.1 Mapping rules (filing term → existing model row)

| Filing Term | Model Sheet | Model Row | Model Label | Decided | Notes |
|-------------|-------------|-----------|-------------|---------|-------|
| Cost of revenue | ANNL P&L / QTR P&L | 10 | COGS | 2026-04-15 | Direct synonym |
| Income from operations | ANNL P&L / QTR P&L | 15 | Operating Profit | 2026-04-15 | Direct synonym |
| Provision for income taxes | ANNL P&L / QTR P&L | 21 | Income Taxes | 2026-04-15 | Direct synonym |
| Foreign currency exchange (loss) gain | ANNL P&L / QTR P&L | 18 | Foreign exchange gain (loss) | 2026-04-15 | Sign convention preserved |
| Bad debt expense | CASH FLOW | 15 | Allowance for Credit Losses | 2026-04-15 | Renamed model row |
| Unrealized exchange losses | CASH FLOW | 19 | Foreign Exchange Loss | 2026-04-15 | Renamed model row |

### A.2 Structural decisions

| Decision | Detail | Decided | Reason |
|----------|--------|---------|--------|
| FY2024/FY2025 S&M vs G&A split | Estimated 72% / 28% based on FY2023 ratio when filing reports combined SG&A only | 2026-04-15 | Press releases don't break out S&M/G&A. Flag in Section 6 of citations doc |
| Distributor termination fees (FY2025+) | Roll into Selling and Marketing Expenses (row 12) consistent with prior treatment | 2026-04-15 | Filing footnote says historically classified as S&M |
| Stock split (3-for-1, Nov 2023) | Do NOT update share counts or EPS unless explicitly verified | 2026-04-15 | Pre/post split inconsistency across filings |

---

## Section B: Balance Sheet Rules

### B.1 Mapping rules (filing term → existing model row)

| Filing Term | Model Row | Model Label | Decided | Notes |
|-------------|-----------|-------------|---------|-------|
| Cash and cash equivalents | 9 | Cash & Cash Equivalents | 2026-04-16 | |
| Accounts receivable-net | 11 | Accounts Receivable | 2026-04-16 | |
| Note receivable-net (current) | 12 | Note Receivable | 2026-04-16 | |
| Inventories-net | 13 | Inventories | 2026-04-16 | |
| Deferred other costs-current | 14 | Deferred Other Costs (Current) | 2026-04-16 | |
| Prepaid expenses and other current assets | 15 | Prepaid Expenses | 2026-04-16 | |
| Property, plant and equipment-net | 19 | Net PP&E | 2026-04-16 | |
| Right of use assets-operating leases | 21 | ROU Assets - Operating | 2026-04-16 | |
| Right of use assets-finance leases-net | 22 | ROU Assets - Finance | 2026-04-16 | |
| Intangibles-net | 25 | Intangibles | 2026-04-16 | |
| Goodwill | 26 | Goodwill | 2026-04-16 | |
| Deferred other costs-non-current | 24 | Deferred Other Costs (NC) | 2026-04-16 | |
| Deferred tax assets | 20 | Deferred Tax Assets | 2026-04-16 | |
| Accrued promotional allowance | 32 | Accrued Promotional Allowance | 2026-04-16 | (post row inserts) |
| Lease liability operating (current) | 33 | Lease Liability - Operating Current | 2026-04-16 | |
| Lease liability finance (current) | 34 | Lease Liability - Finance Current | 2026-04-16 | |
| Deferred revenue (current) | 35 | Deferred Revenue (Current) | 2026-04-16 | |
| Other current liabilities | 36 | Other Current Liabilities | 2026-04-16 | |
| Lease liability operating (non-current) | 39 | Lease Liability - Operating NC | 2026-04-16 | |
| Lease liability finance (non-current) | 40 | Lease Liability - Finance NC | 2026-04-16 | |
| Deferred tax liability | 41 | Deferred Tax Liability | 2026-04-16 | |
| Deferred revenue (non-current) | 42 | Deferred Revenue (NC) | 2026-04-16 | |

### B.2 Rename rules (existing model row → new label)

| Current Label | New Label | Row | Decided | Reason |
|---------------|-----------|-----|---------|--------|
| Acc't Payable and Accrued Expenses | Accounts Payable | 29 | 2026-04-16 | Splitting into A/P + Accrued separately to match filing |

### B.3 New row rules (filing term → new model row)

| Filing Term | New Row Label | Position | Section | Decided | Notes |
|-------------|---------------|----------|---------|---------|-------|
| Other long-term assets | Other Long-Term Assets | Between Goodwill (row 26) and Total Assets | Non-current Assets | 2026-04-16 | |
| Accrued expenses | Accrued Expenses | After Accounts Payable (row 29) | Current Liabilities | 2026-04-16 | Created by splitting old combined row |
| Income taxes payable | Income Taxes Payable | After Accrued Expenses | Current Liabilities | 2026-04-16 | |
| Series A convertible preferred stock | Convertible Preferred Stock | Between Total Liabilities and Total Stockholders' Equity | **Mezzanine Equity** | 2026-04-16 | New section added to model. Do NOT include in Total SE sum (row 46). Flows into Total L&E (row 48) only |
| Common stock | Common Stock | First row in equity breakout | Stockholders' Equity | 2026-04-16 | Full equity breakout requested |
| Additional paid-in capital | Additional Paid-in Capital | After Common Stock | Stockholders' Equity | 2026-04-16 | |
| Accumulated other comprehensive loss | Accumulated Other Comprehensive Loss | After APIC | Stockholders' Equity | 2026-04-16 | |
| Retained earnings (accumulated deficit) | Retained Earnings (Accumulated Deficit) | After AOCI | Stockholders' Equity | 2026-04-16 | |

### B.4 Structural decisions

| Decision | Detail | Decided | Reason |
|----------|--------|---------|--------|
| Convertible Preferred Stock placement | Mezzanine row between L and SE. Total SE (row 46) sums equity components ONLY ($399,929 for FY2024), excludes preferred. Total L&E (row 48) includes Liab + Mezz + SE | 2026-04-16 | Matches CELH's filed BS structure. Sell-side standard. (Was Open Question; user confirmed) |
| Equity section structure | Show 4 component rows (Common, APIC, AOCI, RE) summing to Total SE row 46 | 2026-04-16 | User requested full breakout |

---

## Section C: Cash Flow Rules

### C.1 Mapping rules (filing term → existing model row)

| Filing Term | Model Row | Model Label | Decided | Notes |
|-------------|-----------|-------------|---------|-------|
| Net income | 12 | Net Income | 2026-04-16 | |
| Depreciation and amortization | 13 | Depreciation & Amortization | 2026-04-16 | |
| Impairment of intangible assets | 14 | Impairment of Intangibles | 2026-04-16 | |
| Allowance for credit losses | 15 | Allowance for Credit Losses | 2026-04-16 | (renamed from Bad Debt Expense) |
| Amortization of deferred other costs | 16 | Amortization of Deferred Other Costs | 2026-04-16 | |
| Inventory excess and obsolescence | 17 | Inventory Obsolescence | 2026-04-16 | |
| Stock-based compensation expense | 18 | Stock-Based Compensation | 2026-04-16 | |
| Foreign exchange loss | 19 | Foreign Exchange Loss | 2026-04-16 | (renamed from Unrealized Exchange Losses) |
| Other operating activities | 20 | Other Items | 2026-04-16 | User decision: roll into "Other" instead of new row |
| Accounts receivable-net (Δ) | 21 | Δ Receivables | 2026-04-16 | |
| Inventories-net (Δ) | 22 | Δ Inventories | 2026-04-16 | |
| Prepaid expenses (Δ) | 23 | Δ Prepaids | 2026-04-16 | |
| Accrued promotional allowance (Δ) | 27a | Δ Accrued Promo Allowance | 2026-04-16 | |
| Other current liabilities (Δ) | 27 | Δ Other Current Liabilities | 2026-04-16 | |
| Right of use assets and lease liabilities, net (Δ) | 28 | Δ ROU/Lease | 2026-04-16 | |
| Deferred revenue (Δ) | 29 | Δ Deferred Revenue | 2026-04-16 | |
| Net cash provided by operating activities | 31 | Cash Flow from Operations | 2026-04-16 | |
| Collections from note receivable | 34 | Collections from Note Receivable | 2026-04-16 | |
| Purchase of property, plant and equipment | 35 | Purchase of PP&E | 2026-04-16 | |
| Net cash used in investing activities | 38 | Cash Flow from Investing | 2026-04-16 | |
| Principal payments on finance lease obligations | 40 | Finance Lease Payments | 2026-04-16 | |
| Proceeds from exercise of stock options | 41 | Proceeds from Stock Options | 2026-04-16 | |
| Proceeds from issuance of preferred shares | 42 | Proceeds from Preferred | 2026-04-16 | |
| Dividends paid on Series A preferred | 43 | Dividends Paid on Preferred | 2026-04-16 | |
| Net cash used in financing activities | 45 | Cash Flow from Financing | 2026-04-16 | |
| Effect of exchange rate on cash | 47 | FX Effect on Cash | 2026-04-16 | |
| Net increase in cash | 48 | Net Change in Cash | 2026-04-16 | |
| Cash and cash equivalents, beginning | 50 | Cash at Beginning | 2026-04-16 | |
| Cash and cash equivalents, end | 51 | Cash at End | 2026-04-16 | |

### C.2 New row rules

| Filing Term | New Row Label | Position | Section | Decided | Notes |
|-------------|---------------|----------|---------|---------|-------|
| Loss on disposal of property, plant and equipment | Loss on Disposal of PP&E | After SBC (row 18) | Operating non-cash | 2026-04-16 | |
| Deferred income taxes-net | Deferred Income Taxes-Net | After Loss on Disposal | Operating non-cash | 2026-04-16 | |
| Note receivable-net (Δ) | Δ Note Receivable | In WC changes block | Operating WC | 2026-04-16 | |
| Accounts payable (Δ) | Δ Accounts Payable | In WC changes block | Operating WC | 2026-04-16 | Replaces old combined row 24 |
| Accrued expenses (Δ) | Δ Accrued Expenses | After Δ A/P | Operating WC | 2026-04-16 | |
| Other long-term assets (Δ) | Δ Other Long-Term Assets | In WC changes block | Operating WC | 2026-04-16 | |
| Purchase of non-marketable equity securities | Purchase of Non-Marketable Equity Securities | In investing block | Investing | 2026-04-16 | |
| Acquisition of [entity], net of cash acquired | Acquisition of [entity] | In investing block | Investing | 2026-04-16 | Generic pattern: each acquisition gets its own row labeled "Acquisition of [name]" |
| Repurchase of common stock related to tax withholdings | Repurchase of Common Stock (Tax Withholdings) | In financing block | Financing | 2026-04-16 | |

### C.3 Structural decisions

| Decision | Detail | Decided | Reason |
|----------|--------|---------|--------|
| Old row 24 "Change in Accounts Payable and Accrued Expenses" | Zero out as memo line, add 2 new rows for split | 2026-04-16 | Cleaner audit trail than repurposing |
| Cash reconciliation convention (year-dependent) | **FY2023 10-K and earlier**: "Cash, cash equivalents AND restricted cash" (CF reconciles to combined). **FY2024 10-K and later**: "Cash and cash equivalents" only (restricted cash dropped to $0 at 12/31/23, so the labels are now interchangeable). For each year, check the CF heading and use the matching BS line(s) for the X-2 cross-statement tie. | 2026-04-16 | Confirmed via 2024 10-K (FY2023) and 2025 10-K (FY2024) extractions |
| Distributor termination fees on BS (FY2023+) | "Accrued distributor termination fees" appears as a current liability line in FY2023 10-K (zero at 12/31/23). When extracting any year where it's non-zero, use a NEW current liability row labeled "Accrued Distributor Termination Fees" | 2026-04-16 | Captures the structural placeholder even when zero |

---

## Section D: Validation Override Log

When the user explicitly overrides a Phase 1.75 validation failure (e.g., "skip it, I know the gap is from XYZ"), record it here with the rule ID, the gap, and the user's stated reason.

| Date | Rule ID | Gap | User's Reason | Status |
|------|---------|-----|---------------|--------|
| (none yet) | | | | |

---

## Section E: Known Anomalies / Caveats Library

Recurring issues the skill should be aware of for any future CELH update:

1. **Press releases do NOT contain full balance sheet or cash flow statements** — only summary income statement. For BS/CF, always use the 10-K (annual) or 10-Q (quarterly).
2. **CELH's cash convention is "Cash and cash equivalents" only.** No restricted cash line. Skip the X-2 cross-statement restricted cash check.
3. **CELH 3-for-1 stock split (Nov 13, 2023).** Pre-split filings show smaller share counts and higher EPS. Don't update share counts or EPS without verifying the convention of the source filing.
4. **CELH FY2024 had a major Big Beverages acquisition** ($75M) — first appearance of M&A on the CF.
5. **CELH FY2025 had the Alani Nu acquisition.** Goodwill jumped materially. Intangibles expanded materially. New convertible debt issued (first non-zero Interest Expense year). New "Distributor Termination Fees" line on P&L.
6. **PEP investment ($1.1B+) Series A Convertible Preferred** sits as mezzanine equity, not in Total SE.
7. **Restricted cash convention changed between FY2023 and FY2024.** FY2023 10-K reports CF reconciliation to "Cash, cash equivalents and restricted cash"; FY2024 10-K simplified to "Cash and cash equivalents" (because restricted cash hit $0 at 12/31/23). For X-2 cross-statement check, match the convention of the CF being extracted.
8. **Common Stock par value is $0.001/share.** The $77K (FY2023) → $79K (FY2024) increase represents ~2M new shares issued (from option exercises and vesting), not a material event but a sanity check that par value math is consistent.
9. **Retained Earnings flipped from accumulated deficit to positive in FY2024.** RE(23) = -$12,053K, RE(24) = +$105,521K. The roll-forward (RE(24) = RE(23) + NI(24) - Pref Div Paid(24)) ties exactly: -12,053 + 145,074 - 27,500 = 105,521. Use BS-7 to validate this on every update going forward.
10. **Straight-line amortization patterns make some "current" portions identical year-over-year.** Two specific items:
    - **Deferred Other Costs (Current)** stays at $14,124K every year because that's the annual straight-line amortization. NC bucket drops by $14,124K each year as the next year's amortization migrates to Current. Cross-verify with CF "Amortization of deferred other costs" line — should match the Current portion exactly.
    - **Deferred Revenue (Current)** stays at $9,513K every year for the same reason — the PEP distribution agreement amortizes straight-line. NC drops by $9,513K each year. Total Deferred Revenue YoY change = $(9,513)K from this contract alone, plus any new contracts.
    - **DO NOT treat identical year-over-year values as extraction errors** for these specific line items. Verify by checking that NC bucket dropped by the same amount, and that CF amortization line ties.
11. **Inventory drawdown of $98M from FY2023 to FY2024** ($229M → $131M, -43%) alongside near-flat revenue (+3%) is a major working capital release. Sources of cash on the CF will reflect this. Worth investigating for the case study — likely destocking by distributors, but could be a reclassification. Flag in any future analysis.

---

## How to update this file

When you make a new decision in Phase 1.5:
1. Append a new row to the relevant section table (B.1, B.3, C.1, C.2, etc.)
2. Use today's date in `Decided` column
3. Add Notes if there's any nuance worth remembering
4. If superseding an old rule, mark the old row's Notes with `SUPERSEDED on [date] by [new rule]` and add the new row as a separate entry

Do not edit existing rows in place (except to add `SUPERSEDED` notes). The history is the audit trail.
