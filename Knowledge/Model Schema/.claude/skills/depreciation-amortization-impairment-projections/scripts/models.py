"""Pydantic models for the depreciation-amortization-impairment-projections skill.

`AssetDepreciationFiling` is the per-ticker output shape — one JSON file per
ticker holding the full historical time series for PP&E, intangibles, goodwill,
leases, and impairment values. Loaded by:

  - the upcoming model-write extension that adds an ASSET DEPRECIATION tab
  - model-calc, when wiring the D&A driver to source from rollforward

Every value is a concept-tagged us-gaap fact lifted from companyfacts.json — no
label heuristics. Period labels match the `Period` model in financials-schema:
`FY{year}` for annual, `Q{N} FY{year}` for quarterly.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class FutureAmortizationSchedule(BaseModel):
    """5-year forward amortization schedule disclosed in the intangibles footnote.
    Tagged via `FiniteLivedIntangibleAssetsAmortizationExpenseNext...` concepts.
    Filers disclose this as of fiscal-year-end only (10-K)."""

    model_config = ConfigDict(extra="forbid")

    as_of_period: str  # e.g. "FY2024"
    year_1: Decimal
    year_2: Decimal
    year_3: Decimal
    year_4: Decimal
    year_5: Decimal
    thereafter: Optional[Decimal] = None


class GoodwillRollforward(BaseModel):
    """One period's goodwill rollforward. Filers disclose the components in the
    Goodwill footnote — beginning balance, acquisitions, impairments, FX
    translation, divestitures, ending balance. Not all components are present
    every period; missing legs are zero-defaulted."""

    model_config = ConfigDict(extra="forbid")

    period: str
    beginning: Decimal
    acquisitions: Decimal = Decimal("0")
    impairments: Decimal = Decimal("0")
    fx_effects: Decimal = Decimal("0")
    divestitures: Decimal = Decimal("0")
    measurement_period_adjustments: Decimal = Decimal("0")
    ending: Decimal


class AssetDepreciationFiling(BaseModel):
    """Per-ticker D&A / amortization / impairment dataset.

    All time-series fields are `dict[period_label, Decimal]`. Empty dicts are
    valid (filer never disclosed that concept). Sparse keys are valid (concept
    only disclosed in 10-Ks, not 10-Qs).
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str
    cik: str
    last_refreshed: str  # ISO date when companyfacts.json was last pulled

    # All values are in the filer's native reporting unit. companyfacts values
    # (raw dollars) are scaled into this unit during extraction so the output
    # mixes cleanly with other framework data for the same ticker.
    reporting_unit: str  # "thousands" | "millions" | "ones"

    # ----- PP&E -----
    ppe_gross: dict[str, Decimal] = Field(default_factory=dict)
    ppe_accumulated_depreciation: dict[str, Decimal] = Field(default_factory=dict)
    ppe_net: dict[str, Decimal] = Field(default_factory=dict)
    depreciation_expense: dict[str, Decimal] = Field(default_factory=dict)

    # ----- Intangibles (excl. goodwill) -----
    intangibles_gross: dict[str, Decimal] = Field(default_factory=dict)
    intangibles_accumulated_amortization: dict[str, Decimal] = Field(default_factory=dict)
    intangibles_net: dict[str, Decimal] = Field(default_factory=dict)
    amortization_expense: dict[str, Decimal] = Field(default_factory=dict)
    future_amortization_schedule: Optional[FutureAmortizationSchedule] = None

    # ----- Combined-form CF lines (filer doesn't split) -----
    # Populated when the filer reports D&A or amortization+impairment as a
    # single CF row. Consumers should prefer the split fields above when
    # present and fall back to combined here when those are empty.
    depreciation_and_amortization_combined: dict[str, Decimal] = Field(default_factory=dict)  # GEN-CF-002
    amortization_and_intangibles_impairment_combined: dict[str, Decimal] = Field(default_factory=dict)  # GEN-CF-079
    depreciation_and_lla_impairment_combined: dict[str, Decimal] = Field(default_factory=dict)  # GEN-CF-080

    # ----- Goodwill -----
    goodwill_balance: dict[str, Decimal] = Field(default_factory=dict)
    goodwill_rollforward: list[GoodwillRollforward] = Field(default_factory=list)

    # ----- Impairments (often zero / sparse) -----
    goodwill_impairment: dict[str, Decimal] = Field(default_factory=dict)
    intangibles_impairment: dict[str, Decimal] = Field(default_factory=dict)
    long_lived_asset_impairment: dict[str, Decimal] = Field(default_factory=dict)

    # ----- Leases (ASC 842; FY2019+ for most filers) -----
    operating_lease_rou_asset: dict[str, Decimal] = Field(default_factory=dict)
    finance_lease_rou_asset: dict[str, Decimal] = Field(default_factory=dict)
    operating_lease_cost: dict[str, Decimal] = Field(default_factory=dict)
    finance_lease_cost: dict[str, Decimal] = Field(default_factory=dict)
    short_term_lease_cost: dict[str, Decimal] = Field(default_factory=dict)
    variable_lease_cost: dict[str, Decimal] = Field(default_factory=dict)
