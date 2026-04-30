---
name: depreciation-amortization-impairment-projections
description: Build a per-ticker asset-depreciation dataset from SEC iXBRL footnote data (PP&E, intangibles, goodwill, leases, impairments) sourced from `companyfacts.json`. Output is a structured `AssetDepreciationFiling` Pydantic JSON keyed by period. Feeds an analytical "ASSET DEPRECIATION SCHEDULE" workbook tab and is consumed by `model-calc` to derive D&A / amortization / impairment forecasts from BS rollforward outputs rather than independent drivers. Use when the user asks to build, refresh, or analyze the asset-depreciation projection layer for one or more tickers.
---

# depreciation-amortization-impairment-projections

Analytical-layer skill, parallel to the primary-statement extraction stack. Pulls concept-tagged data from the cumulative `companyfacts.json` cached by `sec-edgar-fetch` and assembles it into a structured per-ticker dataset that drives a dedicated workbook tab and replaces label-driven D&A heuristics in the forecast layer.

## Why this skill exists

D&A, amortization, and impairment values are typically **embedded** inside COGS / SG&A on the IS and only broken out in footnotes. The primary-statement pipeline (`financials-extract`) sees them as CFO non-cash add-backs but has no visibility into:

- Per-asset-class depreciation rates
- Useful-life ranges by asset class
- Accumulated depreciation by class
- Intangibles-by-class amortization expense
- 5-year forward amortization schedule (already disclosed in every 10-K)
- Goodwill rollforward (BoP + acquisitions − impairment − FX − divestitures = EoP)
- Operating + finance lease cost components

All of those are tagged in iXBRL and cached in `companyfacts.json`. This skill lifts them into a structured object.

The forecast layer (`model-calc`) currently treats `GEN-CF-002 D&A` as a single % of revenue or hold-last driver. After this skill ships, model-calc can instead source D&A from a rollforward driven by per-class PP&E base × per-class depreciation rate, and amortization from the disclosed forward schedule. That's strictly more faithful and aligns with the no-heuristic policy (`feedback_structural_over_heuristic.md`) — every value comes from a concept-tagged disclosure, not a label scan.

## Pipeline position

```
sec-edgar-fetch  →  companyfacts.json
                          │
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
           model-calc (D&A driver sources from this tab)
```

Runs **per-ticker**, not per-filing — `companyfacts.json` is cumulative, so one pass over it produces the full historical dataset for that ticker. Re-run when `sec-edgar-fetch` refreshes the companyfacts file.

## Source data

- **Primary:** `Brain\Sources\{TICKER}\companyfacts.json` — populated by `sec-edgar-fetch`.
- **Secondary (planned):** `Brain\Sources\{TICKER}\{PERIOD}\filings\*_financial_report.xlsx` for class-level breakdowns that aren't in `companyfacts.json`'s top-level facts (axis-member dimensions like asset-class). Phase 2.

## Concept catalog

The skill consumes ~30 us-gaap concepts. Source-of-truth list lives in `scripts/concept_catalog.py`. Major buckets:

| Bucket | Sample concepts |
|---|---|
| **PP&E totals** | `PropertyPlantAndEquipmentGross`, `PropertyPlantAndEquipmentNet`, `AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment` |
| **Depreciation expense** | `Depreciation`, `DepreciationAndAmortization`, `DepreciationDepletionAndAmortization` |
| **Intangibles** | `FiniteLivedIntangibleAssetsNet`, `FiniteLivedIntangibleAssetsAccumulatedAmortization`, `IndefiniteLivedIntangibleAssetsExcludingGoodwill` |
| **Amortization expense** | `AmortizationOfIntangibleAssets` |
| **Forward amortization** | `FiniteLivedIntangibleAssetsAmortizationExpenseNextTwelveMonths`, `...NextRollingTwelveMonths`, `...YearTwo` … `YearFive` |
| **Goodwill rollforward** | `Goodwill`, `GoodwillAcquiredDuringPeriod`, `GoodwillImpairmentLoss`, `GoodwillForeignCurrencyTranslationGainLoss`, `GoodwillWrittenOffRelatedToSaleOfBusinessUnit` |
| **LLA impairment** | `ImpairmentOfLongLivedAssetsHeldForUse`, `AssetImpairmentCharges`, `RestructuringChargesImpairment` |
| **Lease cost** | `OperatingLeaseCost`, `FinanceLeaseRightOfUseAssetAmortization`, `FinanceLeaseInterestExpense`, `ShortTermLeaseCost`, `VariableLeaseCost` |
| **ROU assets** | `OperatingLeaseRightOfUseAsset`, `FinanceLeaseRightOfUseAsset` |

## Output schema

`AssetDepreciationFiling` Pydantic model (`scripts/models.py`). Top-level fields are `dict[period_label, value]` time series — period_label format follows the existing `Period` model (`FY{year}` for annual, `Q{N} FY{year}` for quarterly).

```python
class AssetDepreciationFiling(BaseModel):
    ticker: str
    cik: str
    last_refreshed: str

    # PP&E
    ppe_gross: dict[str, Decimal]
    ppe_accumulated_depreciation: dict[str, Decimal]
    ppe_net: dict[str, Decimal]
    depreciation_expense: dict[str, Decimal]

    # Intangibles
    intangibles_gross: dict[str, Decimal]
    intangibles_accumulated_amortization: dict[str, Decimal]
    intangibles_net: dict[str, Decimal]
    amortization_expense: dict[str, Decimal]
    future_amortization_schedule: Optional[FutureAmortizationSchedule]

    # Goodwill
    goodwill_balance: dict[str, Decimal]
    goodwill_rollforward: list[GoodwillRollforward]

    # Impairments
    goodwill_impairment: dict[str, Decimal]
    intangibles_impairment: dict[str, Decimal]
    long_lived_asset_impairment: dict[str, Decimal]

    # Leases
    operating_lease_rou_asset: dict[str, Decimal]
    finance_lease_rou_asset: dict[str, Decimal]
    operating_lease_cost: dict[str, Decimal]
    finance_lease_cost: dict[str, Decimal]
```

`extra="forbid"` per the schema-sync rule.

## CLI

```
depreciation-amortization-impairment-projections \
    --ticker            CELH \
    --companyfacts      "Brain/Sources/CELH/companyfacts.json" \
    --out               "Brain/Knowledge/Model Schema/Ticker Libraries/CELH/asset_depreciation.json"
```

Or run on every ticker that has a `companyfacts.json`:

```
depreciation-amortization-impairment-projections --all
```

## Phases

- **Phase 1 (initial)** — companyfacts.json → `AssetDepreciationFiling` JSON. Totals only (no asset-class breakdowns). Sufficient for a flat asset-depreciation tab.
- **Phase 2** — class-level breakdowns by parsing `*_financial_report.xlsx` footnote sheets (axis-member dimensions). Gives per-class depreciation rates.
- **Phase 3** — workbook integration: model-write extension that writes an `ASSET DEPRECIATION` tab from the JSON; model-calc rewires `GEN-CF-002 D&A` to source from this tab via rollforward.
- **Phase 4** — projection logic: forward depreciation = PP&E base × class-weighted depreciation rate; forward amortization sourced from disclosed schedule; impairment defaulted to zero with analyst-override input.

Phase 1 ships first; later phases land incrementally as the structure stabilizes.

## When to invoke

- User asks to build, refresh, or analyze the asset-depreciation layer for a ticker
- User asks about D&A / amortization / impairment forecasting that's not based on % of revenue
- User mentions an "asset depreciation sheet" or "asset depreciation schedule"
- After `sec-edgar-fetch` refreshes a ticker's companyfacts (re-run to pick up new periods)

## Key conventions

- **No label scans.** Every value comes from a concept-tagged fact. Per the no-heuristic policy.
- **Period labels match the existing `Period` model** in `financials-schema/financials_schema/period.py`. No ad-hoc keys.
- **Decimal-typed values throughout** to avoid float drift on rollforward arithmetic.
- **`extra="forbid"`** on every Pydantic model. Schema-sync rule applies to this skill's `models.py` the same way it does to `LibraryEntry`.
