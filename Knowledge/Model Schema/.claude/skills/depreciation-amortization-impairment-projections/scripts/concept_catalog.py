"""Declarative mapping from us-gaap concept names to fields on
AssetDepreciationFiling. Multiple concepts can map to one field — different
filers tag the same line with different concepts. The first match wins.

Treat this as the source of truth. Adding a concept is a matter of editing this
file; the extractor consumes it generically.

Style: keep `is_instant` accurate. Balance-sheet concepts are "instant"
(disclosed at a point in time — only `end` date on the fact). Income-statement
and cash-flow concepts are "duration" (period-of-time — both `start` and `end`).
The extractor uses this flag to choose which date is the period anchor."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConceptMapping:
    """One field on AssetDepreciationFiling, with the concept(s) that supply it."""
    field: str                      # AssetDepreciationFiling field name
    concepts: tuple[str, ...]        # us-gaap concept names, in priority order
    is_instant: bool                 # True for BS items, False for IS/CF flows
    note: str = ""                  # explanatory note


# ---------------------------------------------------------------------------
# PP&E
# ---------------------------------------------------------------------------
PPE_GROSS = ConceptMapping(
    field="ppe_gross",
    concepts=("PropertyPlantAndEquipmentGross",),
    is_instant=True,
)
PPE_ACC_DEPRECIATION = ConceptMapping(
    field="ppe_accumulated_depreciation",
    concepts=("AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment",),
    is_instant=True,
)
PPE_NET = ConceptMapping(
    field="ppe_net",
    concepts=("PropertyPlantAndEquipmentNet",),
    is_instant=True,
)
DEPRECIATION_EXPENSE = ConceptMapping(
    field="depreciation_expense",
    concepts=(
        # Pure depreciation (PP&E only) — when the filer splits D&A. Some
        # filers also tag this in the PP&E footnote even when the CF rolls D&A.
        "Depreciation",
    ),
    is_instant=False,
    note="Pure depreciation. Filers who report D&A combined go to depreciation_and_amortization_combined instead.",
)
DA_COMBINED = ConceptMapping(
    field="depreciation_and_amortization_combined",
    concepts=(
        "DepreciationAndAmortization",
        "DepreciationDepletionAndAmortization",
    ),
    is_instant=False,
    note="Combined D&A — filer reports as one CF row. Companion to GEN-CF-002 from validated layer.",
)

# ---------------------------------------------------------------------------
# Intangibles (excl. goodwill)
# ---------------------------------------------------------------------------
INTANGIBLES_GROSS = ConceptMapping(
    field="intangibles_gross",
    concepts=(
        "FiniteLivedIntangibleAssetsGross",
        "IntangibleAssetsGrossExcludingGoodwill",
    ),
    is_instant=True,
)
INTANGIBLES_ACC_AMORTIZATION = ConceptMapping(
    field="intangibles_accumulated_amortization",
    concepts=("FiniteLivedIntangibleAssetsAccumulatedAmortization",),
    is_instant=True,
)
INTANGIBLES_NET = ConceptMapping(
    field="intangibles_net",
    concepts=(
        "FiniteLivedIntangibleAssetsNet",
        "IntangibleAssetsNetExcludingGoodwill",
    ),
    is_instant=True,
)
AMORTIZATION_EXPENSE = ConceptMapping(
    field="amortization_expense",
    concepts=(
        "AmortizationOfIntangibleAssets",
        "AdjustmentForAmortization",
    ),
    is_instant=False,
)

# ---------------------------------------------------------------------------
# Forward amortization schedule (5-year disclosure, 10-K only)
# These are duration-style facts disclosed annually with end_date = FYE.
# Captured as a single FutureAmortizationSchedule object (not a time series).
# ---------------------------------------------------------------------------
FUTURE_AMORTIZATION_CONCEPTS = {
    "year_1": "FiniteLivedIntangibleAssetsAmortizationExpenseNextTwelveMonths",
    "year_2": "FiniteLivedIntangibleAssetsAmortizationExpenseYearTwo",
    "year_3": "FiniteLivedIntangibleAssetsAmortizationExpenseYearThree",
    "year_4": "FiniteLivedIntangibleAssetsAmortizationExpenseYearFour",
    "year_5": "FiniteLivedIntangibleAssetsAmortizationExpenseYearFive",
    "thereafter": "FiniteLivedIntangibleAssetsAmortizationExpenseAfterYearFive",
}

# ---------------------------------------------------------------------------
# Goodwill
# ---------------------------------------------------------------------------
GOODWILL_BALANCE = ConceptMapping(
    field="goodwill_balance",
    concepts=("Goodwill",),
    is_instant=True,
)

# Goodwill rollforward components — these populate the GoodwillRollforward
# objects, not a flat dict. Handled specially by the extractor.
GOODWILL_ROLLFORWARD_CONCEPTS = {
    "acquisitions": (
        "GoodwillAcquiredDuringPeriod",
        "GoodwillPurchaseAccountingAdjustments",
    ),
    "impairments": ("GoodwillImpairmentLoss",),
    "fx_effects": ("GoodwillForeignCurrencyTranslationGainLoss",),
    "divestitures": (
        "GoodwillWrittenOffRelatedToSaleOfBusinessUnit",
        "GoodwillDivestiture",
    ),
    "measurement_period_adjustments": ("GoodwillPeriodIncreaseDecrease",),
}

# ---------------------------------------------------------------------------
# Impairments (separate time series for non-goodwill, non-intangibles classes)
# ---------------------------------------------------------------------------
GOODWILL_IMPAIRMENT = ConceptMapping(
    field="goodwill_impairment",
    concepts=("GoodwillImpairmentLoss",),
    is_instant=False,
)
INTANGIBLES_IMPAIRMENT = ConceptMapping(
    field="intangibles_impairment",
    concepts=(
        "ImpairmentOfIntangibleAssetsExcludingGoodwill",
        "ImpairmentOfIntangibleAssetsFinitelived",
        "ImpairmentOfIntangibleAssetsIndefinitelivedExcludingGoodwill",
    ),
    is_instant=False,
)
LLA_IMPAIRMENT = ConceptMapping(
    field="long_lived_asset_impairment",
    concepts=(
        "ImpairmentOfLongLivedAssetsHeldForUse",
        "ImpairmentOfLongLivedAssetsToBeDisposedOf",
        "AssetImpairmentCharges",
    ),
    is_instant=False,
)

# ---------------------------------------------------------------------------
# Leases (ASC 842 — FY2019+ for most filers)
# ---------------------------------------------------------------------------
OPERATING_LEASE_ROU = ConceptMapping(
    field="operating_lease_rou_asset",
    concepts=("OperatingLeaseRightOfUseAsset",),
    is_instant=True,
)
FINANCE_LEASE_ROU = ConceptMapping(
    field="finance_lease_rou_asset",
    concepts=(
        "FinanceLeaseRightOfUseAsset",
        # Some filers tag FL ROU within PP&E; the line below catches that variant
        "FinanceLeaseRightOfUseAssetAfterAccumulatedAmortization",
    ),
    is_instant=True,
)
OPERATING_LEASE_COST = ConceptMapping(
    field="operating_lease_cost",
    concepts=("OperatingLeaseCost",),
    is_instant=False,
)
FINANCE_LEASE_COST = ConceptMapping(
    field="finance_lease_cost",
    concepts=(
        "FinanceLeaseRightOfUseAssetAmortization",
        # Combined with finance lease interest at some filers; less ideal but
        # we capture and leave allocation to the consumer
        "FinanceLeaseCost",
    ),
    is_instant=False,
)
SHORT_TERM_LEASE_COST = ConceptMapping(
    field="short_term_lease_cost",
    concepts=("ShortTermLeaseCost",),
    is_instant=False,
)
VARIABLE_LEASE_COST = ConceptMapping(
    field="variable_lease_cost",
    concepts=("VariableLeaseCost",),
    is_instant=False,
)


# ---------------------------------------------------------------------------
# Master list — extractor iterates this
# ---------------------------------------------------------------------------
ALL_MAPPINGS: tuple[ConceptMapping, ...] = (
    PPE_GROSS,
    PPE_ACC_DEPRECIATION,
    PPE_NET,
    DEPRECIATION_EXPENSE,
    DA_COMBINED,
    INTANGIBLES_GROSS,
    INTANGIBLES_ACC_AMORTIZATION,
    INTANGIBLES_NET,
    AMORTIZATION_EXPENSE,
    GOODWILL_BALANCE,
    GOODWILL_IMPAIRMENT,
    INTANGIBLES_IMPAIRMENT,
    LLA_IMPAIRMENT,
    OPERATING_LEASE_ROU,
    FINANCE_LEASE_ROU,
    OPERATING_LEASE_COST,
    FINANCE_LEASE_COST,
    SHORT_TERM_LEASE_COST,
    VARIABLE_LEASE_COST,
)
