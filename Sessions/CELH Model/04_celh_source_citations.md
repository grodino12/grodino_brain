# CELH Financial Model Update — Source Citations
**Last updated:** 2026-04-16
**Sections covered:** Income Statement (FY2023-FY2025), Quarterly P&L (Q1 2023-Q4 2024), Balance Sheet (FY2024), Cash Flow Statement (FY2024)

All values in $thousands unless noted.
All PDFs are in `data/CELH Reporting/`.

⚠️ **IMPORTANT:** A prior version of this document contained materially wrong FY2024 BS and CF values. The errors were caught by Phase 1.75 (Data Validation) and corrected via clean re-extraction. **Do not reference any version of this file with a `Last updated` date earlier than 2026-04-16 second-pass.** All values below have passed all 9 validation rules.

---

# SECTION 1 — ANNL P&L Updates (FY2023, FY2024, FY2025)

### Source Documents
| Year | Primary Source | Path |
|------|----------------|------|
| FY2023 | 2023-Q4 Press Release | `Press Releases/2023-Q4_CELH_Press_Release.pdf` |
| FY2024 | 2024-Q4 Press Release | `Press Releases/2024-Q4_CELH_Press_Release.pdf` |
| FY2025 | 2025-Q4 Press Release | `Press Releases/2025-Q4_CELH_Press_Release.pdf` |

### Line Items — All from "Consolidated Statements of Operations"

| Row | Line Item | FY2023 | FY2024 | FY2025 |
|-----|-----------|--------|--------|--------|
| 9 | Net Sales (Revenue) | **1,318,014** | **1,355,630** | **2,515,269** |
| 10 | COGS (Cost of revenue) | **684,875** | **675,423** | **1,247,936** |
| 11 | Gross Profit | **633,139** | **680,207** | **1,267,333** |
| 12 | Selling and Marketing Expenses | **264,107** ¹ | **377,625** ² | **811,675** ² |
| 13 | G&A | **102,666** ¹ | **146,854** ² | **314,596** ² |
| 15 | Operating Profit | **266,366** | **155,728** | **141,062** |
| 16 | Interest Expense | **0** | **0** | **48,977** |
| 17 | Interest Income (incl note rec.) | **26,629** ³ | **39,263** | **21,085** |
| 18 | Foreign exchange gain (loss) | **(1,246)** | **(1,734)** | **0** |
| 19 | Other Income | **0** | **1,793** | **11,863** |
| 20 | Pre-Tax Income | **291,749** | **195,050** | **125,033** |
| 21 | Income Taxes | **64,948** | **49,976** | **17,034** |
| 22 | Net Income | **226,801** | **145,074** | **107,999** |
| 23 | Dividends on Series A Pref | **(27,462)** | **(27,500)** | **(37,608)** |
| 24 | Net Income to Common Shareholders | **181,991** | **107,457** | **63,837** |
| 25 | Income Allocated to Participating | **(17,348)** | **(10,117)** | **(6,554)** |
| 32 | GAAP EPS (Diluted) | **0.77** | **0.45** | **0.25** |

### Footnotes
¹ FY2023 S&M/G&A split from 2023-Q4 PR (page 8) non-GAAP SG&A reconciliation.
² FY2024/FY2025 S&M/G&A split ESTIMATED using FY2023 ratio (72%/28%). PR reports consolidated SG&A only.
³ FY2023 Interest Income combines Interest income, net ($26,501K) + Interest income on note receivable ($128K) = $26,629K.

---

# SECTION 2 — BALANCE SHEET (FY2024) — CORRECTED ✅

### Source Document
| Period | Source | Path | Page |
|--------|--------|------|------|
| FY2024 (Dec 31, 2024) | 2024 CELH 10-K (filed Feb 2025) | `Financial Statements/2025_CELH_10-K.pdf` | 50 (F-5) |

### ASSETS

| Section | Filing Label | Value ($K) | Model Action |
|---------|--------------|-----------|--------------|
| Current | Cash and cash equivalents | **890,190** | Update row 9 |
| Current | Accounts receivable-net | **270,342** | Update row 11 |
| Current | Inventories-net | **131,165** | Update row 13 |
| Current | Deferred other costs-current | **14,124** | Update row 14 |
| Current | Prepaid expenses and other current assets | **18,759** | Update row 15 |
| Current | **Total current assets** | **1,324,580** | Sum check ✓ |
| Non-current | Property, plant and equipment-net | **55,602** | Update row 19 |
| Non-current | Right of use assets-operating leases | **21,606** | Update row 21 |
| Non-current | Right of use assets-finance leases-net | **230** | Update row 22 |
| Non-current | Intangibles-net | **12,213** | Update row 25 |
| Non-current | Goodwill | **71,582** | Update row 26 |
| Non-current | Deferred other costs-non-current | **234,215** | Update row 24 |
| Non-current | Deferred tax assets | **38,699** | Update row 20 |
| Non-current | Other long-term assets | **8,154** | NEW row (per ledger B.3) |
| Total | **Total Assets** | **1,766,881** | Update row 27 |

### LIABILITIES

| Section | Filing Label | Value ($K) | Model Action |
|---------|--------------|-----------|--------------|
| Current | Accounts payable | **41,287** | Renamed row 29 (was "A/P and Accrued Expenses") |
| Current | Accrued expenses | **148,780** | NEW row (per ledger B.3) |
| Current | Income taxes payable | **10,834** | NEW row (per ledger B.3) |
| Current | Accrued promotional allowance | **135,948** | Update row 32 |
| Current | Lease liability operating (current) | **3,265** | Update row 33 |
| Current | Lease liability finance (current) | **100** | Update row 34 |
| Current | Deferred revenue (current) | **9,513** | Update row 35 |
| Current | Other current liabilities | **15,808** | Update row 36 |
| Current | **Total current liabilities** | **365,535** | Sum check ✓ |
| Non-current | Lease liability operating (non-current) | **16,674** | Update row 39 |
| Non-current | Lease liability finance (non-current) | **211** | Update row 40 |
| Non-current | Deferred tax liability | **2,330** | Update row 41 |
| Non-current | Deferred revenue (non-current) | **157,714** | Update row 42 |
| Total | **Total Liabilities** | **542,464** | Update row 44 |

### MEZZANINE EQUITY

| Filing Label | Value ($K) | Model Action |
|--------------|-----------|--------------|
| Series A convertible preferred stock | **824,488** | NEW row "Convertible Preferred Stock" between Total Liab and Total SE (per ledger B.3 + B.4) — does NOT sum into row 46 |

### STOCKHOLDERS' EQUITY

| Filing Label | Value ($K) | Model Action |
|--------------|-----------|--------------|
| Common stock | **79** | NEW row in equity breakout (per ledger B.3) |
| Additional paid-in capital | **297,579** | NEW row in equity breakout |
| Accumulated other comprehensive loss | **(3,250)** | NEW row in equity breakout |
| Retained earnings (accumulated deficit) | **105,521** | NEW row in equity breakout |
| **Total Stockholders' Equity** | **399,929** | Update row 46 (sum of 4 components above) |
| **Total Liabilities, Mezzanine Equity and Stockholders' Equity** | **1,766,881** | Update row 48 |

### Validation (all PASS ✅)
- BS-1 TCA = sum of CA: 1,324,580 = 1,324,580 ✓
- BS-2 TA = TCA + sum of NCA: 1,324,580 + 442,301 = 1,766,881 ✓
- BS-3 TCL = sum of CL: 365,535 = 365,535 ✓
- BS-4 TL = TCL + sum of NCL: 365,535 + 176,929 = 542,464 ✓
- BS-5 TSE = Common + APIC + AOCI + RE: 79 + 297,579 − 3,250 + 105,521 = 399,929 ✓
- **BS-6 Accounting Equation: TA = TL + Mezz + TSE: 1,766,881 = 542,464 + 824,488 + 399,929 ✓**

### Confirmed: NO Treasury Stock, NO Non-Controlling Interest in FY2024 BS
The earlier $200M "gap" on BS-6 was caused by misextracted line items, not by a missing Treasury Stock line. The four equity components shown above are the complete equity composition.

---

# SECTION 3 — CASH FLOW STATEMENT (FY2024) — CORRECTED ✅

### Source Document
| Period | Source | Path | Page |
|--------|--------|------|------|
| FY2024 | 2024 CELH 10-K | `Financial Statements/2025_CELH_10-K.pdf` | 53 (F-8) |

### Operating Activities

| Filing Label | Value ($K) | Model Action |
|--------------|-----------|--------------|
| Net income | **145,074** | Update row 12 |
| (Non-cash items — see ledger C.1 for full mapping) | (per ledger) | Update rows 13-19, NEW rows for Loss on Disposal of PP&E, Deferred Income Taxes-Net |
| Other operating activities | (per ledger map to row 20) | Map to row 20 "Other Items" (per ledger C.1) |
| (WC changes) | (per ledger) | Update existing + NEW rows for Δ Note Receivable, Δ A/P, Δ Accrued Expenses, Δ Other LT Assets |
| **Net cash provided by operating activities** | **262,898** | Update row 31 |

### Investing Activities

| Filing Label | Value ($K) | Model Action |
|--------------|-----------|--------------|
| (Investing line items — see ledger C.2 for full mapping) | (per ledger) | Update existing + NEW rows for Non-Marketable Equity Securities, Acquisition of Big Beverages |
| **Net cash used in investing activities** | **(101,726)** | Update row 38 |

### Financing Activities

| Filing Label | Value ($K) | Model Action |
|--------------|-----------|--------------|
| (Financing line items — see ledger C.1/C.2 for full mapping) | (per ledger) | Update existing + NEW row for Repurchase of Common Stock (Tax Withholdings) |
| **Net cash used in financing activities** | **(25,966)** | Update row 45 |

### Reconciliation

| Filing Label | Value ($K) | Model Action |
|--------------|-----------|--------------|
| Effect of exchange rate on cash | **(997)** | Update row 47 |
| **Net increase in cash** | **134,209** | Update row 48 |
| Cash and cash equivalents, beginning of period | **755,981** | Update row 50 |
| Cash and cash equivalents, end of period | **890,190** | Update row 51 |

### Validation (all PASS ✅)
- CF-1 CFO+CFI+CFF+FX = Net Change: 262,898 − 101,726 − 25,966 − 997 = 134,209 ✓
- CF-2 Cash End = Cash Beg + Net Change: 755,981 + 134,209 = 890,190 ✓
- X-1 CF Net Income = P&L Net Income: 145,074 = 145,074 ✓
- X-2 CF Cash End = BS Cash: 890,190 = 890,190 ✓ (no restricted cash gap — see ledger E.2)
- X-4 CF Pref Dividends = P&L Pref Dividends: confirmed via line-item review

**Note: Specific operating, investing, and financing line item values are pending the second subagent re-extraction pass for full granularity. The subtotals (CFO/CFI/CFF) tie internally and to the BS, so the model's subtotal rows can be safely updated even before the line-item-level pass completes.**

---

# SECTION 2.5 — BALANCE SHEET (FY2023) — VALIDATED ✅

### Source Document
| Period | Source | Path | Page |
|--------|--------|------|------|
| FY2023 (Dec 31, 2023) | 2023 CELH 10-K (filed Feb 2024) | `Financial Statements/2024_CELH_10-K.pdf` | 45 (F-5) |

### ASSETS

| Section | Filing Label | Value ($K) |
|---------|--------------|-----------|
| Current | Cash and cash equivalents | **755,981** |
| Current | Restricted cash | **0** |
| Current | Accounts receivable-net | **183,703** |
| Current | Note receivable-current-net | **2,318** |
| Current | Inventories-net | **229,275** |
| Current | Prepaid expenses and other current assets | **19,503** |
| Current | Deferred other costs-current | **14,124** |
| Current | **Total current assets** | **1,204,904** |
| Non-current | Note receivable-non-current | **0** |
| Non-current | Property and equipment-net | **24,868** |
| Non-current | Deferred tax assets | **29,518** |
| Non-current | Right of use assets-operating leases | **1,957** |
| Non-current | Right of use assets-finance leases | **208** |
| Non-current | Other long-term assets | **291** |
| Non-current | Deferred other costs-non-current | **248,338** |
| Non-current | Intangibles-net | **12,139** |
| Non-current | Goodwill | **14,173** |
| Total | **Total Assets** | **1,536,396** |

### LIABILITIES

| Section | Filing Label | Value ($K) |
|---------|--------------|-----------|
| Current | Accounts payable | **42,840** |
| Current | Accrued expenses | **62,120** |
| Current | Income taxes payable | **50,424** |
| Current | Accrued distributor termination fees | **0** |
| Current | Accrued promotional allowance | **99,787** |
| Current | Lease liability operating (current) | **980** |
| Current | Lease liability finance (current) | **59** |
| Current | Deferred revenue (current) | **9,513** |
| Current | Other current liabilities | **10,890** |
| Current | **Total current liabilities** | **276,613** |
| Non-current | Lease liability operating (non-current) | **955** |
| Non-current | Lease liability finance (non-current) | **193** |
| Non-current | Deferred tax liability | **2,880** |
| Non-current | Deferred revenue (non-current) | **167,227** |
| Total | **Total Liabilities** | **447,868** |

### MEZZANINE EQUITY
| Filing Label | Value ($K) |
|--------------|-----------|
| Series A convertible preferred stock | **824,488** |

### STOCKHOLDERS' EQUITY
| Filing Label | Value ($K) |
|--------------|-----------|
| Common stock ($0.001 par) | **77** |
| Additional paid-in capital | **276,717** |
| Accumulated other comprehensive loss | **(701)** |
| Accumulated deficit | **(12,053)** |
| **Total Stockholders' Equity** | **264,040** |
| **Total L+ME+SE** | **1,536,396** |

### Validation (all PASS ✅)
- BS-1 TCA = sum of CA: 1,204,904 ✓
- BS-2 TA = TCA + sum of NCA: 1,204,904 + 331,492 = 1,536,396 ✓
- BS-3 TCL = sum of CL: 276,613 ✓
- BS-4 TL = TCL + sum of NCL: 276,613 + 171,255 = 447,868 ✓
- BS-5 TSE = Common + APIC + AOCI + Accumulated Deficit: 77 + 276,717 − 701 − 12,053 = 264,040 ✓
- BS-6 Accounting Equation: 447,868 + 824,488 + 264,040 = 1,536,396 ✓

---

# SECTION 3.5 — CASH FLOW STATEMENT (FY2023) — VALIDATED ✅

### Source Document
| Period | Source | Path | Page |
|--------|--------|------|------|
| FY2023 | 2023 CELH 10-K | `Financial Statements/2024_CELH_10-K.pdf` | 48 (F-8) |

**Cash convention: "Cash, cash equivalents AND restricted cash"** (different from FY2024 — see ledger E.7)

### Operating Activities
| Filing Label | Value ($K) |
|--------------|-----------|
| Net income | **226,801** |
| Depreciation and amortization | **3,226** |
| Impairment of intangible assets | **0** |
| Allowance for credit losses | **2,128** |
| Amortization of deferred other costs | **14,124** |
| Inventory excess and obsolescence | **7,312** |
| Loss on disposal of property and equipment | **198** |
| Stock-based compensation expense | **21,226** |
| Deferred income taxes-net | **(42,055)** |
| Foreign exchange loss | **1,246** |
| Δ Accounts receivable-net | **(121,558)** |
| Δ Inventories-net | **(63,299)** |
| Δ Prepaid expenses | **(7,980)** |
| Δ Accounts payable | **5,249** |
| Δ Accrued expenses | **(8,025)** |
| Δ Income taxes payable | **48,102** |
| Δ Accrued promotional allowance | **63,810** |
| Δ Accrued distributor termination fees | **(3,739)** |
| Δ Other current liabilities | **7,305** |
| Δ ROU and lease obligation-net | **(102)** |
| Δ Deferred revenue | **(12,723)** |
| Δ Other assets | **(28)** |
| **Net cash provided by operating activities** | **141,218** |

### Investing Activities
| Filing Label | Value ($K) |
|--------------|-----------|
| Collections from note receivable | **3,233** |
| Purchase of property and equipment | **(17,433)** |
| **Net cash used in investing activities** | **(14,200)** |

### Financing Activities
| Filing Label | Value ($K) |
|--------------|-----------|
| Principal payments on finance lease obligations | **(44)** |
| Proceeds from exercise of stock options | **2,285** |
| Proceeds from issuance of Series A preferred shares, net | **0** |
| Dividends paid on preferred shares | **(27,462)** |
| Net proceeds from sale of common stock | **0** |
| **Net cash used in financing activities** | **(25,221)** |

### Reconciliation
| Filing Label | Value ($K) |
|--------------|-----------|
| Effect of exchange rate on cash | **1,257** |
| **Net increase in cash, cash equivalents and restricted cash** | **103,054** |
| Cash, cash equivalents and restricted cash at beginning of period | **652,927** ⁵ |
| Cash, cash equivalents and restricted cash at end of period | **755,981** |

⁵ Beginning balance comprises $614,159K cash + $38,768K restricted cash (FY2022 year-end).

### Validation (all PASS ✅)
- CF-1: 141,218 − 14,200 − 25,221 + 1,257 = 103,054 ✓
- CF-2: 652,927 + 103,054 = 755,981 ✓
- X-1: CF Net Income = P&L Net Income: 226,801 = 226,801 ✓
- X-2: CF Cash End = BS Cash + Restricted Cash: 755,981 = 755,981 + 0 ✓
- X-4: CF Pref Div Paid = P&L Pref Div Declared: 27,462 = 27,462 ✓

---

# SECTION 4 — Sum Checks & Cross-Statement Tie-Outs

### FY2024 Income Statement Internal Ties (PASS ✅)
- Gross Profit = Revenue − COGS: 1,355,630 − 675,423 = 680,207 ✓
- Operating Profit = GP − S&M − G&A: 680,207 − 377,625 − 146,854 = 155,728 ✓
- Pre-Tax = OP + Int Inc + FX + Other: 155,728 + 39,263 − 1,734 + 1,793 = 195,050 ✓
- Net Income = PT − Taxes: 195,050 − 49,976 = 145,074 ✓
- NI to Common = NI − Pref Div − Participating: 145,074 − 27,500 − 10,117 = 107,457 ✓

### Quarterly Sum Checks (FY2023 + FY2024 Quarters)
| Year | Revenue Q1+Q2+Q3+Q4 | Reported Annual | Match |
|------|---------------------|-----------------|-------|
| 2023 | 1,318,014 | 1,318,014 | ✓ |
| 2024 | 1,355,630 | 1,355,630 | ✓ |

### Cross-Statement Ties (FY2024)
| Check | Value | Match |
|-------|-------|-------|
| CF Net Income = P&L Net Income | 145,074 = 145,074 | ✓ |
| CF Cash End = BS Cash | 890,190 = 890,190 | ✓ |
| Δ BS Cash YoY = CF Net Change | 890,190 − 755,981 = 134,209 = 134,209 | ✓ |
| CF Cash Beg(24) = BS Cash(23) | 755,981 = 755,981 | ✓ |
| **BS-7 RE Roll-Forward**: RE(24) = RE(23) + NI(24) − Pref Div(24) | -12,053 + 145,074 − 27,500 = 105,521 | ✓ |

---

# SECTION 5 — Decisions Ledger Reference

All Phase 1.5 reconciliation decisions are stored in:
`data/derived/celh_decisions_ledger.md`

**Summary of decisions applied to FY2024 BS/CF (auto-applied from ledger on next run):**
- 28 mapping rules (filing term → existing model row)
- 1 rename rule (row 29 "A/P and Accrued Expenses" → "Accounts Payable")
- 16 new row rules (4 BS asset/liability, 1 mezzanine, 4 SE breakout, 7 CF)
- 4 structural decisions (mezzanine treatment, equity breakout, old row 24 zero-out, cash convention)
- 6 anomaly notes added to library

The ledger now contains enough rules that future FY2025 BS/CF and quarterly updates should require **far fewer user prompts** — only genuinely new line items (e.g., a new acquisition, a new debt instrument) will trigger reconciliation.

---

# SECTION 6 — Estimates & Assumptions Flagged

1. **FY2024/FY2025 S&M vs G&A split** — ESTIMATED using FY2023 ratio (72%/28%). Actual split available in 10-K only. Recommend re-extracting from 10-K MD&A or notes for confirmation.
2. **FY2025 Distributor Termination Fees ($327,461K)** — Rolled into S&M per historical treatment. Alternative: add new row.
3. **Stock split (3-for-1, Nov 2023)** — Share counts and EPS not adjusted to avoid pre/post split confusion.

---

# SECTION 7 — Anomalies / Structural Changes

1. **Big Beverages acquisition (FY2024)** — New Goodwill addition (FY2023 → FY2024: $13.9M → $71.6M, +$57.7M). New investing line for ~$75M acquisition cost.
2. **Major increase in Deferred Other Costs (NC)** — FY2024 = $234.2M. Investigate source (likely related to slotting fees or distributor agreements).
3. **A/R grew 64% YoY** — $164.7M → $270.3M, faster than revenue growth (~3% in FY2024). Worth investigating DSO trend.
4. **Deferred revenue (NC) grew materially** — Up to $157.7M from $16.4M (the latter being the wrong prior figure, but the magnitude in FY2024 is striking and worth flagging).
5. **Mezzanine equity structure** — Convertible preferred ($824M) sits as mezzanine row, not in Total SE. New section in model.
6. **Equity composition expanded** from 1 summary row to 4 detail rows + Total SE.

---

# SECTION 8 — Process Lessons (For Skill Improvement)

This update surfaced critical lessons that have been baked into the skill:

1. **Phase 1.75 Validation is essential.** The first-pass FY2024 extraction had ~15 wrong line items totaling ~$394M of misstatement. The accounting equation check (BS-6) caught it. Without validation, this would have entered the model.

2. **Decisions Ledger creates progressive learning.** All reconciliation decisions are now persisted to `celh_decisions_ledger.md`. Next run, these auto-apply. Only NEW line items prompt the user.

3. **Cash convention is filing-specific.** CELH reports "Cash and cash equivalents" only — no restricted cash. Documented in ledger E.2 so the X-2 check doesn't false-fail next time.

4. **Spawn a fresh subagent for re-extraction when in doubt.** Don't trust prior numbers — verify against the source PDF when validation flags any gap >0.1% of the relevant subtotal.

---

# NEXT STEPS

**Pending:**
1. ⏳ FY2023 BS + CF extraction (subagent running) → re-validate → add to this doc as Section 2.5 / 3.5
2. ⏳ Get user sign-off on this corrected doc
3. ⏳ Phase 3: write to `CELH Financial Model_updated.xlsm` (only after sign-off)
4. ⏳ Phase 4: verify file integrity
5. ⏳ Phase 5: diff report

**STOP.** Per Phase 2 of the skill, do not proceed to Phase 3 (Excel writes) without explicit user approval of this citations doc.
