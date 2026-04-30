# Generic Canonical Catalog

Source: `pattern_libraries/generic_line_item_mappings.json` (162 entries).

Use the **subclass** column to annotate forecast-projection treatment. Empty = TBD.

## Existing DriverKinds (`model-calc/driver_models.py`)

Inputs: `growth`, `ratio_of_rev`, `ratio_of_cogs`, `dso_ratio`, `dio_ratio`, `dpo_ratio`, `ratio_of_parent`, `tax_rate`, `payout_ratio`, `dollar_input`, `hold_last`, `zero`. 
Linkage / derived: `link_to_is`, `link_to_cf`, `bs_delta`, `rollforward`, `residual_plug`, `derived`, `skip`.

## Field legend

- **section** = `filing_section` field on `LibraryEntry`. Drives section-aware behavior in reconcile/validate/model-write.
- **type** = `row_type` (default `line_item`). `subtotal` and `memo` get special handling.
- **sign** = `sign_convention` (default `as_reported`). `negative` = renders as a charge.
- **parent** = `parent_canonical` rule_id. Detail lines that roll up to a parent (Inventories RM/WIP/FG → GEN-BS-005).
- **accept** = `accepted_sections` cross-section absorption (e.g. memo rows accepting both `operating` and `cash_other`).
- **concept** = `us_gaap_concept` — primary structural-match key.

## ANNL P&L (29 entries)

| rule_id | model_label | section | type | sign | parent | accept | concept | subclass |
|---------|-------------|---------|------|------|--------|--------|---------|----------|
| GEN-IS-004 | SG&A | operating_expenses | line_item | negative |  |  | `SellingGeneralAndAdministrativeExpense` | |
| GEN-IS-005 | Income (Loss) from Operations | operating_expenses | subtotal |  |  |  | `OperatingIncomeLoss` | |
| GEN-IS-024 | Impairment of Intangibles | operating_expenses | line_item | negative |  |  | `ImpairmentOfIntangibleAssetsIndefin…` | |
| GEN-IS-026 | Operating Expenses | operating_expenses | line_item | negative |  |  | `OperatingExpenses` | |
| GEN-IS-027 | Research and Development | operating_expenses | line_item | negative |  |  | `ResearchAndDevelopmentExpense` | |
| GEN-IS-028 | Sales and Marketing | operating_expenses | line_item | negative |  |  | `SellingAndMarketingExpense` | |
| GEN-IS-029 | General and Administrative | operating_expenses | line_item | negative |  |  | `GeneralAndAdministrativeExpense` | |
| GEN-IS-030 | Litigation and Regulatory Charges | operating_expenses | line_item | negative |  |  | `LossContingencyLossInPeriod` | |
| GEN-CI-001 | Other Comprehensive Income (Loss) | non_operating | line_item |  |  |  | `OtherComprehensiveIncomeLossNetOfTa…` | |
| GEN-IS-006 | Interest Income (Expense) | non_operating | line_item |  |  |  | `InterestExpense` | |
| GEN-IS-007 | Foreign Currency Gain (Loss) | non_operating | line_item |  |  |  | `ForeignCurrencyTransactionGainLossB…` | |
| GEN-IS-008 | Other Income (Expense) | non_operating | line_item |  |  |  | `OtherNonoperatingIncomeExpense` | |
| GEN-IS-009 | Pre-Tax Income (Loss) | non_operating | subtotal |  |  |  | `` | |
| GEN-IS-025 | Other Pension and OPEB Benefits Income (Expense) | non_operating | line_item |  |  |  | `NetPeriodicDefinedBenefitsExpenseRe…` | |
| GEN-IS-010 | Income Tax (Expense) Benefit | tax | line_item | negative |  |  | `IncomeTaxExpenseBenefit` | |
| GEN-IS-012 | Preferred Dividends | eps | line_item |  |  |  | `PreferredStockDividendsIncomeStatem…` | |
| GEN-IS-013 | Income Allocated to Participating Preferred | eps | line_item | negative |  |  | `UndistributedEarningsLossAllocatedT…` | |
| GEN-IS-016 | Basic Earnings (Loss) per Share | eps | line_item |  |  |  | `EarningsPerShareBasic` | |
| GEN-IS-017 | Diluted Earnings (Loss) per Share | eps | line_item |  |  |  | `EarningsPerShareDiluted` | |
| GEN-IS-018 | Weighted Average Shares Outstanding (Basic) | eps | line_item |  |  |  | `WeightedAverageNumberOfDilutedShare…` | |
| GEN-IS-019 | Weighted Average Shares Outstanding (Diluted) | eps | line_item |  |  |  | `` | |
| GEN-IS-021 | Common Dividends | eps | line_item |  |  |  | `` | |
| GEN-IS-011 | Net Income (Loss) Less NCI |  | subtotal |  |  |  | `NetIncomeLoss` | |
| GEN-IS-014 | Net Income (Loss) Attributable to Common Shareh… |  | subtotal |  |  |  | `NetIncomeLossAvailableToCommonStock…` | |
| GEN-IS-022 | Net Income (Loss) |  | subtotal |  |  |  | `` | |
| GEN-IS-023 | Net Income (Loss) Attributable to Noncontrollin… | post_ni_deduction | line_item |  |  |  | `NetIncomeLossAttributableToNoncontr…` | |
| GEN-IS-001 | Net Sales / Revenue | revenue_cost | line_item |  |  |  | `Revenues` | |
| GEN-IS-002 | COGS | revenue_cost | line_item | negative |  |  | `CostOfGoodsAndServicesSold` | |
| GEN-IS-003 | Gross Profit (Loss) | revenue_cost | subtotal |  |  |  | `GrossProfit` | |

## BALANCE SHEET (53 entries)

| rule_id | model_label | section | type | sign | parent | accept | concept | subclass |
|---------|-------------|---------|------|------|--------|--------|---------|----------|
| GEN-BS-001 | Cash & Cash Equivalents | current_assets | line_item |  |  |  | `` | |
| GEN-BS-002 | Restricted Cash | current_assets | line_item |  |  |  | `RestrictedCash` | |
| GEN-BS-003 | Accounts Receivable | current_assets | line_item |  |  |  | `AccountsReceivableNetCurrent` | |
| GEN-BS-004 | Note Receivable - Current | current_assets | line_item |  |  |  | `NotesAndLoansReceivableNetCurrent` | |
| GEN-BS-005 | Inventories | current_assets | line_item |  |  |  | `InventoryNet` | |
| GEN-BS-006 | Prepaid Expenses | current_assets | line_item |  |  |  | `PrepaidExpenseAndOtherAssetsCurrent` | |
| GEN-BS-044 | Short-Term Investments | current_assets | line_item |  |  |  | `ShortTermInvestments` | |
| GEN-BS-050 | Prepaid Income Taxes | current_assets | line_item |  |  |  | `PrepaidTaxes` | |
| GEN-BS-051 | Raw Materials | current_assets | line_item |  | GEN-BS-005 |  | `InventoryRawMaterials (+2)` | |
| GEN-BS-052 | Work in Process | current_assets | line_item |  | GEN-BS-005 |  | `InventoryWorkInProcess (+1)` | |
| GEN-BS-053 | Finished Goods | current_assets | line_item |  | GEN-BS-005 |  | `InventoryFinishedGoods (+1)` | |
| GEN-BS-055 | Other Current Assets | current_assets | line_item |  |  |  | `OtherAssetsCurrent` | |
| GEN-BS-007 | Net PP&E | non_current_assets | line_item |  |  |  | `PropertyPlantAndEquipmentNet` | |
| GEN-BS-008 | Deferred Tax Assets | non_current_assets | line_item |  |  |  | `DeferredIncomeTaxAssetsNet` | |
| GEN-BS-009 | ROU Assets - Operating - Non-Current | non_current_assets | line_item |  |  |  | `OperatingLeaseRightOfUseAsset` | |
| GEN-BS-010 | ROU Assets - Finance - Non-Current | non_current_assets | line_item |  |  |  | `FinanceLeaseRightOfUseAsset` | |
| GEN-BS-011 | Note Receivable - Non-Current | non_current_assets | line_item |  |  |  | `NotesAndLoansReceivableNetNoncurrent` | |
| GEN-BS-012 | Intangible Assets | non_current_assets | line_item |  |  |  | `IntangibleAssetsNetExcludingGoodwill` | |
| GEN-BS-013 | Goodwill | non_current_assets | line_item |  |  |  | `Goodwill` | |
| GEN-BS-014 | Other Non-Current Assets | non_current_assets | line_item |  |  |  | `` | |
| GEN-BS-046 | Net PP&E | non_current_assets | line_item |  |  |  | `PropertyPlantAndEquipmentGross (+1)` | |
| GEN-BS-047 | Equity Method Investments | non_current_assets | line_item |  |  |  | `EquityMethodInvestments` | |
| GEN-BS-048 | Long-Term Investments | non_current_assets | line_item |  |  |  | `LongTermInvestments` | |
| GEN-BS-015 | Accounts Payable | current_liabilities | line_item |  |  |  | `` | |
| GEN-BS-016 | Accrued Expenses | current_liabilities | line_item |  |  |  | `AccruedLiabilitiesCurrent` | |
| GEN-BS-017 | Income Taxes Payable | current_liabilities | line_item |  |  |  | `AccruedIncomeTaxesCurrent` | |
| GEN-BS-018 | Accrued Promotional Allowance | current_liabilities | line_item |  |  |  | `` | |
| GEN-BS-019 | Lease Liability - Operating - Current | current_liabilities | line_item |  |  |  | `OperatingLeaseLiabilityCurrent` | |
| GEN-BS-020 | Lease Liability - Finance - Current | current_liabilities | line_item |  |  |  | `FinanceLeaseLiabilityCurrent` | |
| GEN-BS-021 | Deferred Revenue - Current | current_liabilities | line_item |  |  |  | `ContractWithCustomerLiabilityCurrent` | |
| GEN-BS-022 | Other Current Liabilities | current_liabilities | line_item |  |  |  | `OtherLiabilitiesCurrent` | |
| GEN-BS-032 | Short-Term Debt Obligations | current_liabilities | line_item |  |  |  | `ShortTermBorrowings` | |
| GEN-BS-033 | Current Portion of Long-Term Debt | current_liabilities | line_item |  |  |  | `DebtCurrent` | |
| GEN-BS-045 | Contingent Consideration - Current | current_liabilities | line_item |  |  |  | `BusinessCombinationContingentConsid…` | |
| GEN-BS-049 | Accrued Compensation | current_liabilities | line_item |  |  |  | `EmployeeRelatedLiabilitiesCurrent` | |
| GEN-BS-056 | Accrued Revenue Share | current_liabilities | line_item |  |  |  | `goog:AccruedRevenueShare` | |
| GEN-BS-023 | Lease Liability - Operating - Non-Current | non_current_liabilities | line_item |  |  |  | `OperatingLeaseLiabilityNoncurrent` | |
| GEN-BS-024 | Lease Liability - Finance - Non-Current | non_current_liabilities | line_item |  |  |  | `FinanceLeaseLiabilityNoncurrent` | |
| GEN-BS-025 | Deferred Tax Liability | non_current_liabilities | line_item |  |  |  | `DeferredIncomeTaxLiabilitiesNet` | |
| GEN-BS-026 | Deferred Revenue - Non-Current | non_current_liabilities | line_item |  |  |  | `ContractWithCustomerLiabilityNoncur…` | |
| GEN-BS-034 | Other Non-Current Liabilities | non_current_liabilities | line_item |  |  |  | `OtherLiabilitiesNoncurrent` | |
| GEN-BS-041 | Long-Term Debt | non_current_liabilities | line_item |  |  |  | `LongTermDebtNoncurrent` | |
| GEN-BS-028 | Common Stock | equity | line_item |  |  |  | `CommonStockValue` | |
| GEN-BS-029 | Additional Paid-in Capital | equity | line_item |  |  |  | `AdditionalPaidInCapital` | |
| GEN-BS-030 | Accumulated Other Comprehensive Income (Loss) | equity | line_item |  |  |  | `AccumulatedOtherComprehensiveIncome…` | |
| GEN-BS-031 | Retained Earnings (Accumulated Deficit) | equity | line_item |  |  |  | `RetainedEarningsAccumulatedDeficit` | |
| GEN-BS-035 | Treasury Stock | equity | line_item | negative |  |  | `TreasuryStockCommonValue` | |
| GEN-BS-036 | Noncontrolling Interest | equity | line_item |  |  |  | `MinorityInterest` | |
| GEN-BS-037 | Common Stock - Shares Issued | equity | line_item |  |  |  | `CommonStockSharesIssued` | |
| GEN-BS-042 | Par Value of Equity | equity | line_item |  |  |  | `` | |
| GEN-BS-043 | Treasury Stock - Shares Outstanding | equity | line_item |  |  |  | `` | |
| GEN-BS-054 | Common Stock and Additional Paid-in Capital | equity | line_item |  |  |  | `CommonStocksIncludingAdditionalPaid…` | |
| GEN-BS-027 | Convertible Preferred Stock |  | line_item |  |  |  | `` | |

## CASH FLOW (80 entries)

| rule_id | model_label | section | type | sign | parent | accept | concept | subclass |
|---------|-------------|---------|------|------|--------|--------|---------|----------|
| GEN-CF-001 | Net Income (Loss) | operating | line_item |  |  |  | `` | |
| GEN-CF-002 | Depreciation & Amortization | operating | line_item |  |  |  | `DepreciationDepletionAndAmortization` | |
| GEN-CF-003 | Impairment of Intangibles | operating | line_item |  |  |  | `GoodwillAndIntangibleAssetImpairment` | |
| GEN-CF-004 | Allowance for Credit Losses | operating | line_item |  |  |  | `ProvisionForDoubtfulAccounts` | |
| GEN-CF-005 | Inventory Write-Down | operating | line_item |  |  |  | `InventoryWriteDown` | |
| GEN-CF-006 | Stock-Based Compensation | operating | line_item |  |  |  | `ShareBasedCompensation` | |
| GEN-CF-007 | Gain (Loss) on Disposal of PP&E | operating | line_item |  |  |  | `GainLossOnDispositionOfAssets1` | |
| GEN-CF-008 | (Benefit) Provision for Deferred Income Taxes | operating | line_item |  |  |  | `DeferredIncomeTaxExpenseBenefit` | |
| GEN-CF-009 | Foreign Currency Gain (Loss) | operating | line_item |  |  |  | `ForeignCurrencyTransactionGainLossU…` | |
| GEN-CF-010 | Other Operating Items | operating | line_item |  |  |  | `` | |
| GEN-CF-011 | Accounts Receivable | operating | line_item |  |  |  | `` | |
| GEN-CF-012 | Inventories | operating | line_item |  |  |  | `IncreaseDecreaseInInventories` | |
| GEN-CF-013 | Prepaid Expenses | operating | line_item |  |  |  | `IncreaseDecreaseInPrepaidDeferredEx…` | |
| GEN-CF-014 | Accounts Payable | operating | line_item |  |  |  | `IncreaseDecreaseInAccountsPayableAn…` | |
| GEN-CF-015 | Accrued Expenses | operating | line_item |  |  |  | `IncreaseDecreaseInAccruedLiabilities` | |
| GEN-CF-016 | Accrued Promotional Allowance | operating | line_item |  |  |  | `` | |
| GEN-CF-017 | Other Current Liabilities | operating | line_item |  |  |  | `` | |
| GEN-CF-018 | ROU & Lease Liability, Net | operating | line_item |  |  |  | `` | |
| GEN-CF-019 | Deferred Revenue | operating | line_item |  |  |  | `` | |
| GEN-CF-020 | Other Non-Current Assets | operating | line_item |  |  |  | `IncreaseDecreaseInOtherNoncurrentAs…` | |
| GEN-CF-021 | Note Receivable | operating | line_item |  |  |  | `IncreaseDecreaseInFinanceReceivables` | |
| GEN-CF-022 | Cash Flow from Operations | operating | subtotal |  |  |  | `NetCashProvidedByUsedInOperatingAct…` | |
| GEN-CF-038 | Cash Paid for Interest | operating | line_item |  |  | cash_other | `InterestPaidNet` | |
| GEN-CF-039 | Cash Paid for Taxes | operating | line_item |  |  | cash_other | `IncomeTaxesPaid` | |
| GEN-CF-050 | Gain (Loss) on Extinguishment of Debt | operating | line_item |  |  |  | `GainsLossesOnExtinguishmentOfDebt` | |
| GEN-CF-051 | Net Change in Other Working Capital | operating | line_item |  |  |  | `IncreaseDecreaseInOtherNoncurrentLi…` | |
| GEN-CF-052 | Depreciation | operating | line_item |  |  |  | `Depreciation` | |
| GEN-CF-053 | Amortization | operating | line_item |  |  |  | `AdjustmentForAmortization` | |
| GEN-CF-055 | Change in Fair Value of Contingent Consideration | operating | line_item |  |  |  | `LiabilitiesFairValueAdjustment` | |
| GEN-CF-058 | Non-Cash Lease Expense | operating | line_item |  |  |  | `OperatingLeaseRightOfUseAssetAmorti…` | |
| GEN-CF-059 | Pension and Postretirement Benefits Expense | operating | line_item |  |  |  | `PensionAndOtherPostretirementBenefi…` | |
| GEN-CF-060 | Pension and Postretirement Benefits Contributions | operating | line_item | negative |  |  | `PensionAndOtherPostretirementBenefi…` | |
| GEN-CF-061 | Restructuring and Asset Impairment Charges | operating | line_item |  |  |  | `RestructuringCostsAndAssetImpairmen…` | |
| GEN-CF-062 | Cash Payments for Restructuring | operating | line_item | negative |  |  | `PaymentsForRestructuring` | |
| GEN-CF-066 | Acquisition and Divestiture-Related Charges | operating | line_item |  |  |  | `BusinessCombinationSeparatelyRecogn…` | |
| GEN-CF-067 | Cash Payments for Acquisition and Divestiture C… | operating | line_item | negative |  |  | `PaymentsForMergerRelatedCosts` | |
| GEN-CF-071 | Impairment of Long-Lived Assets (PP&E) | operating | line_item |  |  |  | `ImpairmentOfLongLivedAssetsHeldForUse` | |
| GEN-CF-072 | Change in Accrued Compensation | operating | line_item |  |  |  | `IncreaseDecreaseInEmployeeRelatedLi…` | |
| GEN-CF-074 | Change in Prepaid Income Taxes | operating | line_item |  |  |  | `IncreaseDecreaseInPrepaidTaxes` | |
| GEN-CF-075 | Accrued Revenue Share | operating | line_item |  |  |  | `goog:IncreaseDecreaseInAccruedReven…` | |
| GEN-CF-076 | Change in Income Taxes | operating | line_item |  |  |  | `IncreaseDecreaseInIncomeTaxes` | |
| GEN-CF-079 | Amortization and Impairment of Intangibles | operating | line_item |  |  |  | `goog:AmortizationAndImpairmentOfInt…` | |
| GEN-CF-080 | Depreciation and Impairment of PP&E | operating | line_item |  |  |  | `goog:DepreciationAndImpairmentOnDis…` | |
| GEN-CF-081 | Loss (Gain) on Equity and Debt Securities, Net | operating | line_item |  |  |  | `DebtAndEquitySecuritiesGainLoss` | |
| GEN-CF-023 | Collections from Note Receivable | investing | line_item |  |  |  | `ProceedsFromCollectionOfNotesReceiv…` | |
| GEN-CF-024 | Purchase of PP&E | investing | line_item |  |  |  | `PaymentsToAcquirePropertyPlantAndEq…` | |
| GEN-CF-025 | Purchase of Non-Marketable Equity Securities | investing | line_item |  |  |  | `PaymentsToAcquireEquitySecuritiesFvNi` | |
| GEN-CF-026 | Cash Flow from Investing | investing | subtotal |  |  |  | `NetCashProvidedByUsedInInvestingAct…` | |
| GEN-CF-041 | Proceeds from Sale of Assets | investing | line_item |  |  |  | `ProceedsFromSaleOfProductiveAssets` | |
| GEN-CF-042 | Acquisitions, Net of Cash Acquired | investing | line_item |  |  |  | `PaymentsToAcquireBusinessesNetOfCas…` | |
| GEN-CF-043 | Other Investing Activities | investing | line_item |  |  |  | `PaymentsForProceedsFromInvestments` | |
| GEN-CF-057 | Net Change in Short-Term Investments | investing | line_item |  |  |  | `ProceedsFromSaleOfShortTermInvestments` | |
| GEN-CF-065 | Proceeds from Divestitures of Businesses | investing | line_item |  |  |  | `ProceedsFromDivestitureOfBusinesses…` | |
| GEN-CF-069 | Additions to Intangibles | investing | line_item |  |  |  | `PaymentsToAcquireIntangibleAssets` | |
| GEN-CF-070 | Net Change in Long-Term Investments | investing | line_item |  |  |  | `PaymentsToAcquireAvailableForSaleSe…` | |
| GEN-CF-027 | Finance Lease Payments | financing | line_item |  |  |  | `FinanceLeasePrincipalPayments` | |
| GEN-CF-028 | Proceeds from Exercise of Stock Options | financing | line_item |  |  |  | `ProceedsFromStockOptionsExercised` | |
| GEN-CF-029 | Proceeds from Issuance of Preferred Stock | financing | line_item |  |  |  | `ProceedsFromIssuanceOfPreferredStoc…` | |
| GEN-CF-030 | Preferred Dividends | financing | line_item |  |  |  | `PaymentsOfDividendsPreferredStockAn…` | |
| GEN-CF-031 | Proceeds from Issuance of Common Stock | financing | line_item |  |  |  | `ProceedsFromIssuanceOfCommonStock` | |
| GEN-CF-032 | Share Repurchases | financing | line_item |  |  |  | `PaymentsForRepurchaseOfCommonStock` | |
| GEN-CF-033 | Cash Flow from Financing | financing | subtotal |  |  |  | `NetCashProvidedByUsedInFinancingAct…` | |
| GEN-CF-040 | Common Dividends | financing | line_item |  |  |  | `PaymentsOfDividends` | |
| GEN-CF-044 | Proceeds from Short-Term Debt | financing | line_item |  |  |  | `ProceedsFromShortTermDebtMaturingIn…` | |
| GEN-CF-045 | Repayments of Short-Term Debt | financing | line_item |  |  |  | `RepaymentsOfShortTermDebtMaturingIn…` | |
| GEN-CF-046 | Net Change in Other Short-Term Debt | financing | line_item |  |  |  | `ProceedsFromRepaymentsOfShortTermDe…` | |
| GEN-CF-047 | Proceeds from Issuance of Long-Term Debt | financing | line_item |  |  |  | `ProceedsFromIssuanceOfLongTermDebt` | |
| GEN-CF-048 | Repayments of Long-Term Debt | financing | line_item |  |  |  | `RepaymentsOfLongTermDebt` | |
| GEN-CF-049 | Stock Options & Other Financing Activities | financing | line_item |  |  |  | `` | |
| GEN-CF-054 | Debt Issuance Fees | financing | line_item |  |  |  | `PaymentsOfDebtIssuanceCosts` | |
| GEN-CF-056 | Other Financing Activities | financing | line_item |  |  |  | `ProceedsFromPaymentsForOtherFinanci…` | |
| GEN-CF-063 | Tax Withholdings on RSU/PSU Settlement | financing | line_item | negative |  |  | `PaymentsRelatedToTaxWithholdingForS…` | |
| GEN-CF-064 | Payments of Contingent Consideration | financing | line_item | negative |  |  | `PaymentForContingentConsiderationLi…` | |
| GEN-CF-077 | Stock-Based Award Activities, Net | financing | line_item |  |  |  | `goog:NetProceedsPaymentsRelatedToSt…` | |
| GEN-CF-078 | Proceeds from Sale of Interest in Consolidated … | financing | line_item |  |  |  | `ProceedsFromMinorityShareholders` | |
| GEN-CF-034 | FX Effect on Cash | cash_other | line_item |  |  |  | `EffectOfExchangeRateOnCashCashEquiv…` | |
| GEN-CF-035 | Net Change in Cash | cash_other | subtotal |  |  |  | `CashCashEquivalentsRestrictedCashAn…` | |
| GEN-CF-068 | ROU Assets Obtained in Exchange for Lease Oblig… | cash_other | line_item |  |  |  | `RightOfUseAssetObtainedInExchangeFo…` | |
| GEN-CF-036 | Cash at Beginning of Period |  | line_item |  |  |  | `` | |
| GEN-CF-037 | Cash at End of Period |  | line_item |  |  |  | `` | |
