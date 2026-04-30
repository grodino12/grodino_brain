"""depreciation-amortization-impairment-projections — extractor.

Builds an `AssetDepreciationFiling` from a hybrid input:
  1. Validated files (`{ticker_root}/validated_*.json`) — for canonicals already
     on the primary statements. Reuses the framework's filer-naming work.
  2. companyfacts.json (`Brain/Sources/{TICKER}/companyfacts.json`) — for
     footnote-only data (PP&E gross, accumulated depreciation, future
     amortization schedule, goodwill rollforward components, ROU assets).

Validated wins on overlap. Output JSON is per-ticker (not per-filing) since
companyfacts is cumulative and validated_*.json are aggregated by period anyway.

CLI:
    python extract.py \
        --ticker        CELH \
        --ticker-root   "Brain/Knowledge/Model Schema/Ticker Libraries/CELH/" \
        --companyfacts  "Brain/Sources/CELH/companyfacts.json" \
        --out           "Brain/Knowledge/Model Schema/Ticker Libraries/CELH/asset_depreciation.json"
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Optional

from concept_catalog import (
    ALL_MAPPINGS,
    ConceptMapping,
    FUTURE_AMORTIZATION_CONCEPTS,
    GOODWILL_ROLLFORWARD_CONCEPTS,
)
from models import (
    AssetDepreciationFiling,
    FutureAmortizationSchedule,
    GoodwillRollforward,
)


# ---------------------------------------------------------------------------
# Period labels — mirror the framework's `Period` model
# ---------------------------------------------------------------------------

def period_label(fy: int, fp: str) -> Optional[str]:
    """Translate companyfacts.json (`fy`, `fp`) into the canonical label.
       fp == 'FY'        -> 'FY{year}'
       fp == 'Q1/Q2/Q3'  -> 'Q{n} FY{year}'
       fp == 'Q4'        -> SKIP (Q4 isn't reported standalone — the FY filing covers it)
       Anything else     -> None (skip)
    """
    if not isinstance(fy, int):
        return None
    if fp == "FY":
        return f"FY{fy}"
    if fp in ("Q1", "Q2", "Q3"):
        return f"{fp} FY{fy}"
    return None


# ---------------------------------------------------------------------------
# Validated-file ingestion — canonicals already on the primary statements
# ---------------------------------------------------------------------------

# rule_id -> field name on AssetDepreciationFiling.
# When a single canonical contributes to multiple fields (combined-form lines),
# include both targets in the value.
VALIDATED_RULE_TO_FIELDS: dict[str, tuple[str, ...]] = {
    # Split-form D&A (filer reports separately) — clean fields
    "GEN-CF-052": ("depreciation_expense",),
    "GEN-CF-053": ("amortization_expense",),
    # Standalone impairments (clean fields)
    "GEN-CF-003": ("intangibles_impairment",),
    "GEN-CF-071": ("long_lived_asset_impairment",),
    "GEN-IS-024": ("intangibles_impairment",),
    # Lease cost CF reconciliation
    "GEN-CF-058": ("operating_lease_cost",),
    # Restructuring + asset impairment combined — bundled with restructuring
    # cash payments at some filers; not strictly an impairment-only line.
    # Routed conservatively to long_lived_asset_impairment.
    "GEN-CF-061": ("long_lived_asset_impairment",),
    # Combined-form CF lines (filer doesn't split) — go to dedicated combined
    # fields. Consumers prefer split fields, fall back to combined when split
    # are empty.
    "GEN-CF-002": ("depreciation_and_amortization_combined",),
    "GEN-CF-079": ("amortization_and_intangibles_impairment_combined",),
    "GEN-CF-080": ("depreciation_and_lla_impairment_combined",),
}


def _detect_reporting_unit(ticker_root: Path) -> str:
    """Read any validated_*.json and return the filer's reporting unit
    ('thousands', 'millions', or 'ones'). Picks the most-recent FY file when
    available since 10-Ks are most likely to have unambiguous unit declaration.

    Falls back to 'thousands' if no validated file is found (rare — would mean
    the ticker hasn't been ingested yet)."""
    val_files = sorted(ticker_root.glob("validated_*-FY.json")) or sorted(ticker_root.glob("validated_*.json"))
    if not val_files:
        return "thousands"
    d = json.loads(val_files[-1].read_text(encoding="utf-8"))
    statements = d.get("mapped", {}).get("raw", {}).get("statements", [])
    for st in statements:
        unit = st.get("unit")
        if unit in ("thousands", "millions", "ones"):
            return unit
    return "thousands"


def _unit_divisor(reporting_unit: str) -> Decimal:
    """Convert raw-dollar companyfacts values into the filer's native unit."""
    return {
        "thousands": Decimal("1000"),
        "millions": Decimal("1000000"),
        "ones": Decimal("1"),
    }.get(reporting_unit, Decimal("1000"))


def _ingest_validated_files(ticker_root: Path) -> tuple[
    dict[str, dict[str, Decimal]],  # field -> period -> value
    dict[str, dict[str, set[str]]], # field -> period -> set of contributing rule_ids (for traceability)
]:
    """Read every validated_*.json under ticker_root and accumulate values into
    field-keyed dicts.

    Combined-form canonicals (GEN-CF-002, GEN-CF-079, GEN-CF-080) duplicate the
    same value into multiple fields — the consumer should know not to add them
    on top of split-form values from the same period. Cross-filing dedup: when
    multiple validated files cover the same period, the LAST one written wins
    (same convention as model-write's first-filing-wins-per-period — except
    here we keep the latest because validated files are already deduped by the
    primary pipeline).
    """
    field_period_value: dict[str, dict[str, Decimal]] = defaultdict(dict)
    field_period_sources: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    val_files = sorted(ticker_root.glob("validated_*.json"))
    for vf in val_files:
        d = json.loads(vf.read_text(encoding="utf-8"))
        mapped = d.get("mapped", {})
        line_items = mapped.get("mapped_line_items", [])
        # Period label is encoded in the filename: validated_2024-FY.json -> FY2024
        # validated_2024-Q3.json -> Q3 FY2024
        stem_period = vf.stem.removeprefix("validated_")  # "2024-FY" or "2024-Q3"
        period = _stem_to_period_label(stem_period)
        if period is None:
            continue

        for item in line_items:
            rid = item.get("ledger_rule_id")
            if rid not in VALIDATED_RULE_TO_FIELDS:
                continue
            try:
                value = Decimal(str(item.get("value", "0")))
            except Exception:
                continue
            for field in VALIDATED_RULE_TO_FIELDS[rid]:
                # Latest filing wins per period — for primary-statement values
                # this means the most recent restatement wins.
                field_period_value[field][period] = value
                field_period_sources[field][period].add(rid)

    return field_period_value, field_period_sources


def _stem_to_period_label(stem: str) -> Optional[str]:
    """'2024-FY' -> 'FY2024'; '2024-Q3' -> 'Q3 FY2024'."""
    if "-" not in stem:
        return None
    year_str, pp = stem.split("-", 1)
    try:
        year = int(year_str)
    except ValueError:
        return None
    if pp == "FY":
        return f"FY{year}"
    if pp in ("Q1", "Q2", "Q3"):
        return f"{pp} FY{year}"
    return None


# ---------------------------------------------------------------------------
# companyfacts.json ingestion — footnote layer
# ---------------------------------------------------------------------------

def _facts_for(facts_root: dict, concept: str) -> list[dict]:
    """Return every USD fact for a us-gaap concept. Empty list if absent."""
    block = facts_root.get(concept)
    if not block:
        return []
    return block.get("units", {}).get("USD", []) or []


def _select_per_period(facts: list[dict]) -> dict[str, Decimal]:
    """Walk facts, dedupe by period (fy + fp), return period_label -> Decimal.

    Dedup rule: when multiple facts target the same period, prefer the latest
    `filed` timestamp (most recent restatement)."""
    by_period: dict[str, dict] = {}
    for f in facts:
        fy = f.get("fy")
        fp = f.get("fp")
        period = period_label(fy, fp) if fy is not None and fp is not None else None
        if period is None:
            continue
        prior = by_period.get(period)
        if prior is None or (f.get("filed", "") > prior.get("filed", "")):
            by_period[period] = f
    out: dict[str, Decimal] = {}
    for period, f in by_period.items():
        try:
            out[period] = Decimal(str(f["val"]))
        except Exception:
            continue
    return out


def _ingest_companyfacts(
    companyfacts_path: Path,
    existing_field_values: dict[str, dict[str, Decimal]],
    unit_divisor: Decimal,
) -> tuple[dict[str, dict[str, Decimal]], Optional[FutureAmortizationSchedule], list[GoodwillRollforward]]:
    """Read companyfacts.json. Populate fields from concept_catalog.ALL_MAPPINGS,
    skipping (period, field) pairs that the validated layer already filled.

    Returns:
      - field -> period -> value (gap-fill layer)
      - future amortization schedule (or None)
      - goodwill rollforward (list of per-period objects, possibly empty)
    """
    data = json.loads(companyfacts_path.read_text(encoding="utf-8"))
    us_gaap = data.get("facts", {}).get("us-gaap", {})

    # ----- standard time-series fields -----
    gap_fill: dict[str, dict[str, Decimal]] = defaultdict(dict)
    for mapping in ALL_MAPPINGS:
        existing = existing_field_values.get(mapping.field, {})
        for concept in mapping.concepts:
            facts = _facts_for(us_gaap, concept)
            per_period = _select_per_period(facts)
            for period, val in per_period.items():
                if period in existing or period in gap_fill[mapping.field]:
                    continue
                # Scale raw-dollar companyfacts values into the filer's unit.
                gap_fill[mapping.field][period] = val / unit_divisor
            # Don't break — but successive concepts only add NEW periods (not
            # overwrite). First-mapping-wins per period is enforced by the
            # `if period in gap_fill[mapping.field]: continue` line above.

    # ----- future amortization schedule (10-K only — pick the latest) -----
    future_schedule = _build_future_amortization_schedule(us_gaap, unit_divisor)

    # ----- goodwill rollforward (component sums per period) -----
    goodwill_rollforward = _build_goodwill_rollforward(us_gaap, unit_divisor)

    return gap_fill, future_schedule, goodwill_rollforward


def _build_future_amortization_schedule(us_gaap: dict, unit_divisor: Decimal) -> Optional[FutureAmortizationSchedule]:
    """Pick the most recent FY disclosure of the 5-year forward amortization.
    Fields are tagged once a year on the 10-K. Returns the latest fy's snapshot."""
    component_facts: dict[str, list[dict]] = {}
    for slot, concept in FUTURE_AMORTIZATION_CONCEPTS.items():
        component_facts[slot] = _facts_for(us_gaap, concept)

    if not component_facts.get("year_1"):
        return None

    # Anchor on year_1 — pick the most recent fy where we have a year_1 fact.
    year_1_facts = [f for f in component_facts["year_1"] if f.get("fp") == "FY" and isinstance(f.get("fy"), int)]
    if not year_1_facts:
        return None
    year_1_facts.sort(key=lambda f: (f.get("fy") or 0, f.get("filed", "")))
    anchor = year_1_facts[-1]
    anchor_fy = anchor["fy"]
    anchor_period = f"FY{anchor_fy}"

    def _val_at_anchor(slot: str) -> Optional[Decimal]:
        for f in component_facts.get(slot, []):
            if f.get("fp") == "FY" and f.get("fy") == anchor_fy:
                try:
                    return Decimal(str(f["val"])) / unit_divisor
                except Exception:
                    return None
        return None

    y1 = _val_at_anchor("year_1")
    if y1 is None:
        return None
    return FutureAmortizationSchedule(
        as_of_period=anchor_period,
        year_1=y1,
        year_2=_val_at_anchor("year_2") or Decimal("0"),
        year_3=_val_at_anchor("year_3") or Decimal("0"),
        year_4=_val_at_anchor("year_4") or Decimal("0"),
        year_5=_val_at_anchor("year_5") or Decimal("0"),
        thereafter=_val_at_anchor("thereafter"),
    )


def _build_goodwill_rollforward(us_gaap: dict, unit_divisor: Decimal) -> list[GoodwillRollforward]:
    """Build a per-period rollforward by combining Goodwill balance with the
    component concepts. Filers don't always tag every component; missing legs
    default to zero, and the residual goes into measurement_period_adjustments
    if `GoodwillPeriodIncreaseDecrease` was tagged for that period."""
    bal_facts = _facts_for(us_gaap, "Goodwill")
    bal_by_period = {p: v / unit_divisor for p, v in _select_per_period(bal_facts).items()}
    if not bal_by_period:
        return []

    component_per_period: dict[str, dict[str, Decimal]] = {}
    for leg, concepts in GOODWILL_ROLLFORWARD_CONCEPTS.items():
        leg_total: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for concept in concepts:
            facts = _facts_for(us_gaap, concept)
            for period, val in _select_per_period(facts).items():
                leg_total[period] += (val / unit_divisor)
        component_per_period[leg] = leg_total

    # Need a beginning balance for each period: prior period's ending.
    # Sort periods chronologically (FY{year} sorts naturally; Q{n} FY{year}
    # comes after FY{year-1} but before FY{year}).
    periods = sorted(bal_by_period.keys(), key=_period_sort_key)
    rollforwards: list[GoodwillRollforward] = []
    for i, period in enumerate(periods):
        ending = bal_by_period[period]
        beginning = bal_by_period[periods[i - 1]] if i > 0 else Decimal("0")
        rf = GoodwillRollforward(
            period=period,
            beginning=beginning,
            acquisitions=component_per_period.get("acquisitions", {}).get(period, Decimal("0")),
            impairments=component_per_period.get("impairments", {}).get(period, Decimal("0")),
            fx_effects=component_per_period.get("fx_effects", {}).get(period, Decimal("0")),
            divestitures=component_per_period.get("divestitures", {}).get(period, Decimal("0")),
            measurement_period_adjustments=component_per_period.get("measurement_period_adjustments", {}).get(period, Decimal("0")),
            ending=ending,
        )
        rollforwards.append(rf)
    return rollforwards


def _period_sort_key(period: str) -> tuple[int, int]:
    """'FY2024' -> (2024, 4); 'Q3 FY2024' -> (2024, 3)."""
    if period.startswith("FY"):
        return (int(period[2:]), 4)
    # 'Q3 FY2024'
    parts = period.split()
    q = int(parts[0][1:])
    y = int(parts[1][2:])
    return (y, q)


# ---------------------------------------------------------------------------
# Assembly + main
# ---------------------------------------------------------------------------

def build_filing(
    ticker: str,
    ticker_root: Path,
    companyfacts_path: Path,
) -> AssetDepreciationFiling:
    # Detect filer's reporting unit so we can scale companyfacts (raw dollars)
    # into the same unit as validated_*.json values.
    reporting_unit = _detect_reporting_unit(ticker_root)
    unit_divisor = _unit_divisor(reporting_unit)

    # Phase 1: validated-files layer (primary statements)
    validated_values, _validated_sources = _ingest_validated_files(ticker_root)

    # Phase 2: companyfacts gap-fill (scaled into filer's unit)
    cf_data = json.loads(companyfacts_path.read_text(encoding="utf-8"))
    cik = str(cf_data.get("cik", ""))
    gap_fill, future_schedule, goodwill_rollforward = _ingest_companyfacts(
        companyfacts_path, validated_values, unit_divisor
    )

    # Merge: validated wins, companyfacts fills gaps.
    merged: dict[str, dict[str, Decimal]] = defaultdict(dict)
    for source in (gap_fill, validated_values):
        for field, period_map in source.items():
            for period, val in period_map.items():
                merged[field][period] = val

    # Build the filing object
    return AssetDepreciationFiling(
        ticker=ticker,
        cik=cik,
        last_refreshed=_dt.date.today().isoformat(),
        reporting_unit=reporting_unit,
        ppe_gross=merged.get("ppe_gross", {}),
        ppe_accumulated_depreciation=merged.get("ppe_accumulated_depreciation", {}),
        ppe_net=merged.get("ppe_net", {}),
        depreciation_expense=merged.get("depreciation_expense", {}),
        intangibles_gross=merged.get("intangibles_gross", {}),
        intangibles_accumulated_amortization=merged.get("intangibles_accumulated_amortization", {}),
        intangibles_net=merged.get("intangibles_net", {}),
        amortization_expense=merged.get("amortization_expense", {}),
        future_amortization_schedule=future_schedule,
        goodwill_balance=merged.get("goodwill_balance", {}),
        goodwill_rollforward=goodwill_rollforward,
        goodwill_impairment=merged.get("goodwill_impairment", {}),
        intangibles_impairment=merged.get("intangibles_impairment", {}),
        long_lived_asset_impairment=merged.get("long_lived_asset_impairment", {}),
        operating_lease_rou_asset=merged.get("operating_lease_rou_asset", {}),
        finance_lease_rou_asset=merged.get("finance_lease_rou_asset", {}),
        operating_lease_cost=merged.get("operating_lease_cost", {}),
        finance_lease_cost=merged.get("finance_lease_cost", {}),
        short_term_lease_cost=merged.get("short_term_lease_cost", {}),
        variable_lease_cost=merged.get("variable_lease_cost", {}),
        depreciation_and_amortization_combined=merged.get("depreciation_and_amortization_combined", {}),
        amortization_and_intangibles_impairment_combined=merged.get("amortization_and_intangibles_impairment_combined", {}),
        depreciation_and_lla_impairment_combined=merged.get("depreciation_and_lla_impairment_combined", {}),
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ticker", required=True)
    p.add_argument("--ticker-root", required=True, type=Path,
                   help="folder containing validated_*.json for this ticker")
    p.add_argument("--companyfacts", required=True, type=Path,
                   help="path to Brain/Sources/{TICKER}/companyfacts.json")
    p.add_argument("--out", required=True, type=Path,
                   help="output JSON path (asset_depreciation.json)")
    args = p.parse_args()

    if not args.ticker_root.exists():
        raise SystemExit(f"ERROR: ticker-root not found: {args.ticker_root}")
    if not args.companyfacts.exists():
        raise SystemExit(f"ERROR: companyfacts not found: {args.companyfacts}")

    filing = build_filing(args.ticker, args.ticker_root, args.companyfacts)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(filing.model_dump_json(indent=2), encoding="utf-8")

    # Summary print
    n_validated_periods = len(filing.depreciation_expense) + len(filing.amortization_expense)
    n_ppe_periods = len(filing.ppe_gross) + len(filing.ppe_net)
    print(f"[{args.ticker}] wrote {args.out}")
    print(f"  depreciation/amortization periods: {len(filing.depreciation_expense)} / {len(filing.amortization_expense)}")
    print(f"  ppe gross/net periods:             {len(filing.ppe_gross)} / {len(filing.ppe_net)}")
    print(f"  goodwill rollforward periods:      {len(filing.goodwill_rollforward)}")
    print(f"  future amortization schedule:      {'YES (' + filing.future_amortization_schedule.as_of_period + ')' if filing.future_amortization_schedule else 'NO'}")


if __name__ == "__main__":
    main()
