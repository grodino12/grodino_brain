---
name: depreciation-amortization-impairment-projections
description: Build a per-ticker asset-depreciation dataset that feeds three downstream forecasts in tandem — Net PP&E rollforward (GEN-BS-007), Intangibles rollforward (GEN-BS-012), and D&A on CF (GEN-CF-002). Hybrid input — primary-statement values reuse the framework's existing canonical mappings (validated_*.json), footnote-only values lift from companyfacts.json. Output is an `AssetDepreciationFiling` Pydantic JSON keyed by period. Use when the user asks to build, refresh, or analyze the asset-depreciation projection layer for one or more tickers.
---

# depreciation-amortization-impairment-projections

Analytical-layer skill that consolidates D&A / amortization / impairment data into one source-of-truth object, then feeds it to the three forecast rows that share a driver: PP&E rollforward, Intangibles rollforward, and CF D&A. By pulling the driver from one place, BS and CF stay arithmetically consistent — depreciation taken on PP&E equals D&A added back on CF, by construction.

## Architecture

The asset depreciation sheet is **upstream** of three forecast rows. They project in tandem from a single driver set:

```
                 AssetDepreciationFiling (per ticker)
                              │
            ┌─────────────────┼──────────────────┐
            ↓                 ↓                  ↓
    PP&E rollforward     Intangibles RF      CF D&A add-back
    (GEN-BS-007)         (GEN-BS-012)        (GEN-CF-002)
    PP&E[t] = PP&E[t-1]  Intang[t] = beg     = depreciation
    + CapEx              − amortization        + amortization
    − depreciation       − impairment          (matches BS rollforward
                                                outputs exactly)
```

Single source means:
- Depreciation taken on PP&E rollforward = depreciation portion of CF D&A — **mechanically equal**
- Amortization on Intangibles rollforward = amortization portion of CF D&A — **mechanically equal**
- Impairment events flow through both BS and CF without separate forecasting

This replaces the current "GEN-CF-002 D&A as % of revenue" heuristic with structural integrity.

## Hybrid input — reuse the framework, lift footnotes

The framework has already done the filer-specific naming work. Every `validated_*.json` carries:
- `raw_filing_label` (filer's exact wording)
- `canonical_label` (canonical mapped to)
- `ledger_rule_id` (which canonical)
- `citation.line_hint` (us-gaap concept)
- `value` per period

For canonicals that already live on the primary statements, the skill **reuses** those values rather than re-deriving them from companyfacts. That preserves the framework's sign-convention handling, period dedup, and cross-filing reconciliation.

For footnote-only data the primary pipeline never sees, the skill **lifts** from `companyfacts.json` (already cached by `sec-edgar-fetch`).

| Source | What it provides | Why |
|---|---|---|
| `validated_*.json` (per filing) | D&A on CF, Amortization on CF, Impairment lines on IS/CF, lease cost on CF | Already canonicalized; filer naming/sign already resolved |
| `companyfacts.json` (per ticker, cumulative) | PP&E gross, accumulated depreciation, gross/net intangibles, accumulated amortization, future amortization schedule, goodwill rollforward components, ROU asset balances | Footnote disclosures not in the primary statements |

Validated files are the **first** lookup; companyfacts is the **gap-filler**. If a value appears in both, validated wins (it's gone through reconcile/validate).

## Pipeline position

```
sec-edgar-fetch                    financials-extract
        │                                  │
        ↓                                  ↓
companyfacts.json              validated_*.json (per filing)
        │                                  │
        └──────────────┬───────────────────┘
                       ↓
   depreciation-amortization-impairment-projections
                       │
                       ↓
            asset_depreciation.json
                       │
                       ↓
       model-write (ASSET DEPRECIATION tab)
                       │
                       ↓
       model-calc — three forecasts source from this tab:
         · PP&E rollforward (GEN-BS-007)
         · Intangibles rollforward (GEN-BS-012)
         · CF D&A (GEN-CF-002)
```

Runs **per-ticker**, not per-filing. Re-run when:
- `sec-edgar-fetch` refreshes the companyfacts file (new period available), OR
- `financials-validate` produces a new `validated_*.json` (existing period's primary-statement values changed)

## Canonicals consumed from validated_*.json

Read directly by `ledger_rule_id`:

| rule_id | canonical | feeds field |
|---|---|---|
| `GEN-CF-002` | D&A | depreciation_expense + amortization_expense (combined) |
| `GEN-CF-052` | Depreciation | depreciation_expense (when filer splits) |
| `GEN-CF-053` | Amortization | amortization_expense (when filer splits) |
| `GEN-CF-003` | Impairment of Intangibles | intangibles_impairment |
| `GEN-CF-058` | Non-Cash Lease Expense | operating_lease_cost (CF-side reconciliation) |
| `GEN-CF-061` | Restructuring + Asset Impairment | partial signal for long_lived_asset_impairment |
| `GEN-CF-071` | Impairment of Long-Lived Assets (PP&E) | long_lived_asset_impairment |
| `GEN-CF-079` | Amortization + Impairment of Intangibles | amortization_expense + intangibles_impairment (combined) |
| `GEN-CF-080` | Depreciation + Impairment of PP&E | depreciation_expense + long_lived_asset_impairment (combined) |
| `GEN-IS-024` | Impairment of Intangibles | intangibles_impairment (IS side; should match CF-003) |

When the same conceptual value is captured by two canonicals (e.g., a filer that uses GEN-CF-002 D&A combined and a filer that splits GEN-CF-052 + GEN-CF-053), the extractor aggregates appropriately.

## Concepts pulled from companyfacts.json

Footnote-only values not represented in the primary statements:

- PP&E: `PropertyPlantAndEquipmentGross`, `PropertyPlantAndEquipmentNet`, `AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment`
- Intangibles: `FiniteLivedIntangibleAssetsGross`, `FiniteLivedIntangibleAssetsAccumulatedAmortization`, `FiniteLivedIntangibleAssetsNet`, `IndefiniteLivedIntangibleAssetsExcludingGoodwill`
- Forward amortization: `FiniteLivedIntangibleAssetsAmortizationExpenseNextTwelveMonths` … `YearFive` … `AfterYearFive`
- Goodwill rollforward components: `GoodwillAcquiredDuringPeriod`, `GoodwillForeignCurrencyTranslationGainLoss`, `GoodwillWrittenOffRelatedToSaleOfBusinessUnit`, `GoodwillPeriodIncreaseDecrease`, `GoodwillImpairmentLoss`
- ROU assets: `OperatingLeaseRightOfUseAsset`, `FinanceLeaseRightOfUseAsset`
- Lease cost split: `OperatingLeaseCost`, `FinanceLeaseRightOfUseAssetAmortization`, `ShortTermLeaseCost`, `VariableLeaseCost`

Source-of-truth lives in `scripts/concept_catalog.py`.

## CLI

```
depreciation-amortization-impairment-projections \
    --ticker            CELH \
    --ticker-root       "Brain/Knowledge/Model Schema/Ticker Libraries/CELH/" \
    --companyfacts      "Brain/Sources/CELH/companyfacts.json" \
    --out               "Brain/Knowledge/Model Schema/Ticker Libraries/CELH/asset_depreciation.json"
```

Or run on every ticker that has a `companyfacts.json`:

```
depreciation-amortization-impairment-projections --all
```

The `--ticker-root` flag is where the validated_*.json files live; `--companyfacts` supplies the footnote layer.

## Output schema

`AssetDepreciationFiling` Pydantic model in `scripts/models.py`. All time-series fields are `dict[period_label, Decimal]`; period labels follow the existing `Period` model (`FY{year}` for annual, `Q{N} FY{year}` for quarterly). `extra="forbid"` per the schema-sync rule.

## Phases

- **Phase 1 (initial)** — extractor + JSON output. Totals only (no asset-class breakdowns). Sufficient for a flat asset-depreciation tab plus the three downstream rollforward consumers.
- **Phase 2** — class-level breakdowns by parsing `*_financial_report.xlsx` footnote sheets (axis-member dimensions). Per-class depreciation rates, weighted-avg useful lives.
- **Phase 3** — `model-write` extension that emits an `ASSET DEPRECIATION SCHEDULE` tab from the JSON.
- **Phase 4** — `model-calc` rewires `GEN-BS-007 Net PP&E`, `GEN-BS-012 Intangibles`, and `GEN-CF-002 D&A` to source from the new tab via rollforward, so the three forecasts move in tandem.

Phase 1 ships first; later phases land incrementally as the structure stabilizes.

## When to invoke

- User asks to build, refresh, or analyze the asset-depreciation layer for a ticker
- User asks about D&A / amortization / impairment forecasting that's not based on % of revenue
- User mentions an "asset depreciation sheet" or "asset depreciation schedule"
- User asks to project PP&E or Intangibles via rollforward (this skill produces the depreciation/amortization driver they need)
- After `sec-edgar-fetch` or `financials-validate` refreshes a ticker's input data

## Key conventions

- **No label scans.** Values come from `ledger_rule_id` lookups (validated files) or us-gaap concept matches (companyfacts). Per the no-heuristic policy.
- **Validated files first, companyfacts second.** The framework's canonical mappings already encode filer-specific naming; reuse them.
- **Period labels match the existing `Period` model.**
- **Decimal-typed values** to avoid float drift on rollforward arithmetic.
- **`extra="forbid"`** on every Pydantic model.
