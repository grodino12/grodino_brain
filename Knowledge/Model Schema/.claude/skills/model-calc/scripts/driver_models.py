"""
Pydantic data models for the quarterly model-calc rebuild.

A `DriverSpec` is the fully-resolved output of the inference engine for one
workbook row. It says: "this row's forecast cells should compute via {kind};
historical-driver cells compute via {historical_formula_kind}."

The `kind` field drives the formula builders in `forecasts.py` / build code in
`calc.py`. When you add a new driver kind, the loop is:
    1. Add to `DriverKind` enum
    2. Add inference branch in `inference.py`
    3. Add formula builder in `forecasts.py` (or wherever forecasts are wired)
"""
from __future__ import annotations

from enum import Enum
from typing import Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field


class DriverKind(str, Enum):
    """All supported driver kinds. Each row in IS DRIVERS / BS DRIVERS / CF
    DRIVERS gets exactly one kind. SKIP rows produce no driver tab entry and
    no forecast cell on the source sheet."""

    # Inputs (user-editable forecast cells)
    GROWTH        = "growth"           # YoY growth %, per quarter (Q[Y] = Q[Y-1] * (1+g))
    RATIO_OF_REV  = "ratio_of_rev"     # line / Revenue %
    RATIO_OF_COGS = "ratio_of_cogs"    # line / COGS %
    DSO_RATIO     = "dso_ratio"        # AR-style: line / Revenue * 91
    DIO_RATIO     = "dio_ratio"        # Inventory-style: line / COGS * 91
    DPO_RATIO     = "dpo_ratio"        # AP-style: line / COGS * 91
    RATIO_OF_PARENT = "ratio_of_parent"  # detail / parent %; forecast = parent_forecast × rate
                                         # (RM/WIP/FG → Inventories Net)
    TAX_RATE      = "tax_rate"         # Tax / Pre-Tax %
    PAYOUT_RATIO  = "payout_ratio"     # Common Dividends / NI %
    DOLLAR_INPUT  = "dollar_input"     # analyst types each forecast quarter
    HOLD_LAST     = "hold_last"        # forecast = last historical value (constant)
    ZERO          = "zero"             # forecast = 0 (one-time / non-recurring lines)

    # Cross-sheet / linkage / derived (no user input)
    LINK_TO_IS    = "link_to_is"       # CF NI = IS NI for that quarter
    LINK_TO_CF    = "link_to_cf"       # IS Pref Div = CF Pref Div (single driver on CF side)
    BS_DELTA      = "bs_delta"         # CF WC item = -(BS[Q]-BS[Q-1]) for asset, +Δ for liability
    ROLLFORWARD   = "rollforward"      # running balance: prev + inputs - outputs (Cash, RE, PP&E)
    RESIDUAL_PLUG = "residual_plug"    # CF row absorbs Σ ΔBS of unmatched non-flat BS rows (BS-balance closure)
    DERIVED       = "derived"          # subtotal/cascade — already in workbook via SUM/+ formulas
    SKIP          = "skip"             # EPS, share count — not forecast in v1


class DriverSpec(BaseModel):
    """One row's driver. Sheet+excel_row identify the source workbook row;
    kind identifies how to fill its forecast cells; the optional anchor fields
    point at other rows the formula needs to reference."""

    model_config = ConfigDict(extra="forbid")

    sheet: str           # "QTR P&L" | "QTR BS" | "QTR CF"
    excel_row: int       # 1-indexed row on `sheet` (matches workbook layout)
    label: str           # row label (column A) — also the canonical model_label
    kind: DriverKind
    filing_section: Optional[str] = None   # mirrored from the library entry for traceability
    note: Optional[str] = None             # human-readable explanation of the inference

    # ROLLFORWARD anchors. Each tuple is (sheet, label) of another workbook
    # row. `inputs` add to the rolling balance; `outputs` subtract.
    # Example for Retained Earnings: inputs=[("QTR P&L","Net Income (Loss)")],
    # outputs=[("QTR CF","Common Dividends"), ("QTR CF","Preferred Dividends")]
    rollforward_inputs:  list[Tuple[str, str]] = Field(default_factory=list)
    rollforward_outputs: list[Tuple[str, str]] = Field(default_factory=list)

    # BS_DELTA anchor: which BS row's quarter-over-quarter change drives this
    # CF working-capital line. Sign handled by the asset/liability flag.
    bs_delta_source: Optional[Tuple[str, str]] = None  # (sheet, label) on QTR BS
    bs_delta_is_liability: bool = False                # True flips Δ sign

    # LINK_TO_IS anchor: which IS row this CF line equals (Net Income).
    is_link_source: Optional[Tuple[str, str]] = None

    # LINK_TO_CF anchor: which CF row this IS line equals (Preferred Dividends).
    # Mirrors the cash payment from the CF financing section onto the IS as a
    # deduction from common — single driver lives on the CF side, IS row reads
    # through. Override CF Pref Div once, IS PrefDiv updates everywhere.
    cf_link_source: Optional[Tuple[str, str]] = None

    # For sign-aware ratios: True if this row's historical values are typically
    # negative (parens). Forecast formulas use the historical ratio directly,
    # which carries the sign — but the inference engine notes it for clarity.
    is_signed_negative: bool = False

    # RESIDUAL_PLUG sources: list of (sheet, label, is_liability) tuples for
    # every non-flat BS row that this CF plug row absorbs. Sign rule: assets
    # contribute -(BS[t]-BS[t-1]); liabilities contribute +(BS[t]-BS[t-1]).
    # Populated in `infer_drivers` after BS specs and named BS_DELTA wirings
    # are settled — anything left over goes here.
    residual_plug_sources: list[Tuple[str, str, bool]] = Field(default_factory=list)

    # GROWTH-kind only: which prior-period to grow off — "yoy" (Q[Y-1, q]) or
    # "qoq" (prev quarter). Sourced from ticker config.json `growth_basis` at
    # build time; rendered into a "Basis" cell on the driver tab so the analyst
    # can flip it in Excel without rerunning model-calc. None for all other kinds.
    growth_basis: Optional[str] = None

    # RATIO_OF_PARENT-kind only: (sheet, label) of the parent row this child
    # is a detail of. Forecast formula = parent_forecast_cell × ratio_cell.
    # Historical driver formula = src / parent_value (same sheet, same period).
    parent_source: Optional[Tuple[str, str]] = None
