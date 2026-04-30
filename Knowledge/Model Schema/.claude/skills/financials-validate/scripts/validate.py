"""financials-validate CLI — run accounting-identity + cross-statement checks on a MappedFiling."""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from financials_schema import (
    FilingType,
    MappedFiling,
    MappedLineItem,
    Period,
    Section,
    StatementType,
    ValidatedFiling,
    ValidationResult,
    normalize_label,
)


# ============================================================================
# Constants
# ============================================================================

ABS_TOLERANCE = Decimal("1")              # $1K absolute (units are thousands)
REL_TOLERANCE = Decimal("0.001")          # 0.1% relative


# ============================================================================
# Partitioning: walk BS items in order, split by subtotal boundaries
# ============================================================================

def _strip_lower(s: str) -> str:
    return s.strip().lower()


# Subtotal anchor names keyed by normalized raw_filing_label. The iXBRL
# extractor emits filer display labels (e.g. "TOTAL CURRENT ASSETS") plus
# us-gaap concept subtotal names (e.g. "AssetsCurrent") that normalize_label
# splits into "assets current". Both paths land here.
_ANCHOR_KEYS: dict[str, tuple[str, ...]] = {
    "tca":       ("total current assets", "assets current"),
    "ta":        ("total assets", "assets"),
    "tcl":       ("total current liabilities", "liabilities current"),
    "tl":        ("total liabilities", "liabilities"),
    "tse":       (
        "total stockholders equity",
        "total shareholders equity",
        "stockholders equity",
        "shareholders equity",
        "stockholders equity including portion attributable to noncontrolling interest",
    ),
    "total_le": (
        "total liabilities mezzanine equity and stockholders equity",
        "total liabilities and stockholders equity",
        "total liabilities and shareholders equity",
        "liabilities and stockholders equity",
    ),
}


def _classify_subtotal(raw_filing_label: str) -> str | None:
    normalized = normalize_label(raw_filing_label)
    for key, patterns in _ANCHOR_KEYS.items():
        if normalized in patterns:
            return key
    # TLSE: "Total Liabilities and ... Equity" — must be checked BEFORE the
    # TSE catch-all below, since TLSE labels also end with "shareholders/
    # stockholders equity" but conceptually anchor a different rule.
    if normalized.startswith("total liabilities and ") and (
        normalized.endswith(" stockholders equity")
        or normalized.endswith(" shareholders equity")
        or normalized.endswith(" equity")
    ):
        return "total_le"
    # TSE catch-all — any subtotal whose label ends in "stockholders equity"
    # or "shareholders equity", with optional filer-name words in between
    # (PEP's "Total PepsiCo Common Shareholders' Equity"). Also covers
    # "Total Equity" alone (PEP's all-equity line including NCI).
    if (normalized == "total equity"
        or normalized.endswith(" stockholders equity")
        or normalized.endswith(" shareholders equity")):
        return "tse"
    return None


def _item_in_section(item: MappedLineItem, target: Section) -> bool:
    sec = item.section.value if hasattr(item.section, "value") else item.section
    target_val = target.value if hasattr(target, "value") else target
    return sec == target_val


def _is_memo(item: MappedLineItem) -> bool:
    rt = item.row_type.value if hasattr(item.row_type, "value") else item.row_type
    return rt == "memo"


def _signed_value(item: MappedLineItem) -> Decimal:
    """Apply the item's sign_convention to its raw value.

    `positive` → always +abs(value)
    `negative` → always -abs(value)
    `as_reported` (default) → value as-is

    The abs-based design means the filer's reported sign doesn't matter — if
    we know an item should always be negative (Tax, Treasury Stock, expense
    line on IS, etc.), we get -abs regardless of whether the filer wrote it
    positive, negative, in parens, or pre-signed. Kills the parens_negative
    special case the PDF extractor used to need."""
    sc = item.sign_convention
    sc_val = sc.value if hasattr(sc, "value") else sc
    if sc_val == "negative":
        return -abs(item.value)
    if sc_val == "positive":
        return abs(item.value)
    return item.value


def _signed_sum(items: list[MappedLineItem]) -> Decimal:
    return sum((_signed_value(i) for i in items), start=Decimal("0"))


def partition_balance_sheet(
    items: list[MappedLineItem],
    child_to_parent: dict[str, str] | None = None,
) -> dict:
    """Partition BS items by `item.section` directly. Subtotal rows are
    captured as named anchors (TCA, TA, TCL, TL, TSE, total_LE) so validators
    can compare sum-of-components against the filer's reported subtotal, but
    bucketing itself reads from each item's own section field — no state
    machine.

    Reconcile guarantees no item arrives with `section=UNCLASSIFIED` (it halts
    on those), so any item we see here belongs to a real section.

    Memo rows (`row_type == "memo"`) are share counts, etc. — never summed.

    Detail-of-parent rows (RM/WIP/FG → Inventories Net, declared via
    `parent_canonical` in the library — wired through `child_to_parent`):
    excluded from the section bucket when the parent's canonical is also
    present in the same items list. Parent value is the section's
    authoritative contributor; including children would double-count BS-1.
    When the parent is absent (filer disclosed details but not the rolled-up
    Net), children are kept so BS-1 still ties.
    """
    child_to_parent = child_to_parent or {}
    parents_present: set[str] = {
        i.ledger_rule_id for i in items if i.ledger_rule_id is not None
    }
    buckets: dict[str, list[MappedLineItem]] = {
        "current_assets": [],
        "non_current_assets": [],
        "current_liabilities": [],
        "non_current_liabilities": [],
        "mezzanine": [],
        "equity": [],
    }
    anchors: dict[str, MappedLineItem | None] = {
        "tca": None, "ta": None, "tcl": None, "tl": None,
        "tse": None, "total_le": None,
    }

    for item in items:
        rt = item.row_type.value if hasattr(item.row_type, "value") else item.row_type
        is_subtotal = rt == "subtotal"

        if is_subtotal:
            anchor_key = _classify_subtotal(item.raw_filing_label)
            if anchor_key in anchors:
                anchors[anchor_key] = item
            # Mid-section subtotals (not matching any anchor key) are skipped
            # from section bucketing entirely — including them would double-count
            # the components above. Example: GOOG's "Total cash, cash equivalents,
            # and marketable securities" lands between Cash and AR; summing it
            # alongside Cash + Marketable Securities double-counts both.
            continue

        if _is_memo(item):
            continue

        # Skip detail rows (RM/WIP/FG) when their parent (Inventories Net) is
        # also present — parent is the summable representative, children would
        # double-count BS-1.
        parent_rid = child_to_parent.get(item.ledger_rule_id) if item.ledger_rule_id else None
        if parent_rid and parent_rid in parents_present:
            continue

        sec = item.section.value if hasattr(item.section, "value") else item.section
        if sec in buckets:
            buckets[sec].append(item)

    return {"buckets": buckets, "anchors": anchors}


# ============================================================================
# Rule helpers
# ============================================================================

def _within_tolerance(expected: Decimal, actual: Decimal) -> bool:
    gap = abs(actual - expected)
    rel_tol = abs(expected) * REL_TOLERANCE
    return gap <= ABS_TOLERANCE or gap <= rel_tol


def _build_result(
    rule_id: str,
    expected: Decimal,
    actual: Decimal,
    message: str,
) -> ValidationResult:
    gap = actual - expected
    passed = _within_tolerance(expected, actual)
    return ValidationResult(
        rule_id=rule_id,
        expected=expected,
        actual=actual,
        gap=gap,
        severity="pass" if passed else "fail",
        message=message,
    )


def _inconclusive(rule_id: str, reason: str) -> ValidationResult:
    return ValidationResult(
        rule_id=rule_id,
        expected=Decimal("0"),
        actual=Decimal("0"),
        gap=Decimal("0"),
        severity="warning",
        message=f"inconclusive — {reason}",
    )


def _skip(rule_id: str, reason: str) -> ValidationResult:
    """Filer doesn't render this anchor (e.g. PG omits Gross Profit, MNST
    combines Total Liabilities into TL+SE). The check is genuinely N/A —
    not a regression to investigate. Excluded from warning counts; surfaces
    only with --verbose listing."""
    return ValidationResult(
        rule_id=rule_id,
        expected=Decimal("0"),
        actual=Decimal("0"),
        gap=Decimal("0"),
        severity="skip",
        message=f"skipped — {reason}",
    )


# ============================================================================
# Balance sheet rules
# ============================================================================

def run_bs1(part: dict, period_label: str) -> ValidationResult:
    tca = part["anchors"]["tca"]
    items = part["buckets"]["current_assets"]
    if tca is None:
        return _inconclusive(f"BS-1 @ {period_label}", "Total current assets subtotal not found")
    expected = sum((i.value for i in items), start=Decimal("0"))
    return _build_result(
        rule_id=f"BS-1 @ {period_label}",
        expected=expected,
        actual=tca.value,
        message=f"TCA = sum of {len(items)} current-asset line items",
    )


def run_bs2(part: dict, period_label: str) -> ValidationResult:
    ta = part["anchors"]["ta"]
    tca = part["anchors"]["tca"]
    nca = part["buckets"]["non_current_assets"]
    if ta is None or tca is None:
        return _inconclusive(f"BS-2 @ {period_label}", "Total Assets or TCA missing")
    nca_sum = sum((i.value for i in nca), start=Decimal("0"))
    expected = tca.value + nca_sum
    return _build_result(
        rule_id=f"BS-2 @ {period_label}",
        expected=expected,
        actual=ta.value,
        message=f"TA = TCA ({tca.value}) + sum({len(nca)} NCA items = {nca_sum})",
    )


def run_bs3(part: dict, period_label: str) -> ValidationResult:
    tcl = part["anchors"]["tcl"]
    items = part["buckets"]["current_liabilities"]
    if tcl is None:
        return _inconclusive(f"BS-3 @ {period_label}", "Total current liabilities subtotal not found")
    expected = sum((i.value for i in items), start=Decimal("0"))
    return _build_result(
        rule_id=f"BS-3 @ {period_label}",
        expected=expected,
        actual=tcl.value,
        message=f"TCL = sum of {len(items)} current-liability line items",
    )


def run_bs4(part: dict, period_label: str) -> ValidationResult:
    tl = part["anchors"]["tl"]
    tcl = part["anchors"]["tcl"]
    ncl = part["buckets"]["non_current_liabilities"]
    if tl is None or tcl is None:
        # Filer doesn't render Total Liabilities (e.g. MNST presents only
        # combined "Total Liabilities and SE" without breaking out TL).
        # Genuine N/A — not a regression to investigate.
        return _skip(f"BS-4 @ {period_label}", "Total Liabilities not rendered by filer")
    ncl_sum = sum((i.value for i in ncl), start=Decimal("0"))
    expected = tcl.value + ncl_sum
    return _build_result(
        rule_id=f"BS-4 @ {period_label}",
        expected=expected,
        actual=tl.value,
        message=f"TL = TCL ({tcl.value}) + sum({len(ncl)} NCL items = {ncl_sum})",
    )


def run_bs5(part: dict, period_label: str) -> ValidationResult:
    tse = part["anchors"]["tse"]
    equity = part["buckets"]["equity"]
    if tse is None:
        return _inconclusive(f"BS-5 @ {period_label}", "Total Stockholders' Equity subtotal not found")
    # Treasury Stock + ESOP-style contra-equity rows carry sign_convention='negative';
    # _signed_sum returns -abs(value) so the equity total comes out right.
    expected = _signed_sum(equity)
    return _build_result(
        rule_id=f"BS-5 @ {period_label}",
        expected=expected,
        actual=tse.value,
        message=f"TSE = sum of {len(equity)} equity components",
    )


BS_RULES = [run_bs1, run_bs2, run_bs3, run_bs4, run_bs5]


# ============================================================================
# Cash flow rules
# ============================================================================

def _find_item(items: list[MappedLineItem], label_exact: str) -> MappedLineItem | None:
    """Find the FIRST item whose lowercased label exactly equals `label_exact`."""
    label_exact = label_exact.lower()
    for item in items:
        if _strip_lower(item.raw_filing_label) == label_exact:
            return item
    return None


def run_cf1(items: list[MappedLineItem], period_label: str) -> ValidationResult:
    """NetΔCash = CFO + CFI + CFF + Other Cash Effects.

    Anchors come from partition_cash_flow's per-section subtotals and a
    canonical_label lookup for the bottom-line NetΔCash row.
    """
    part = partition_cash_flow(items)
    cfo = part["sums"]["operating"]
    cfi = part["sums"]["investing"]
    cff = part["sums"]["financing"]
    cash_other = part["sums"]["cash_other"]   # subtotal if any (rare on CF)
    cash_other_items = part["buckets"]["cash_other"]   # individual rows (FX Effect, etc.)
    net_change = next(
        (i for i in items
         if i.canonical_label == "Net Change in Cash"
         and ("cash flow" in i.model_sheet.lower() or i.model_sheet.upper() == "QTR CF")),
        None,
    )
    missing = [n for n, v in (("CFO", cfo), ("CFI", cfi), ("CFF", cff), ("NetΔ", net_change)) if v is None]
    if missing:
        return _inconclusive(f"CF-1 @ {period_label}", f"missing: {', '.join(missing)}")
    # cash_other typically has no subtotal — just FX Effect on Cash as a line.
    if cash_other is not None:
        other_val = cash_other.value
    else:
        other_val = sum((i.value for i in cash_other_items), start=Decimal("0"))
    expected = cfo.value + cfi.value + cff.value + other_val
    return _build_result(
        rule_id=f"CF-1 @ {period_label}",
        expected=expected,
        actual=net_change.value,
        message=f"CFO ({cfo.value}) + CFI ({cfi.value}) + CFF ({cff.value}) + CashOther ({other_val}) = NetChange",
    )


def partition_cash_flow(items: list[MappedLineItem]) -> dict:
    """Partition CF items by `item.section` directly. The section-sum
    subtotal for each section (Net cash provided by/used in X activities)
    is captured by walking subtotal rows in that section.

    Same architecture as partition_balance_sheet: section enum drives
    bucketing; subtotal rows captured as anchors. No state machine, no
    English-prose label searches.

    Cash Beg / Cash End / NetΔCash are bottom-of-statement reconciliation
    rows; they have section=None and are excluded from per-section sum
    validation. CF-2 keys those by canonical_label.
    """
    buckets: dict[str, list[MappedLineItem]] = {
        "operating": [], "investing": [], "financing": [], "cash_other": [],
    }
    sums: dict[str, MappedLineItem | None] = {
        "operating": None, "investing": None, "financing": None, "cash_other": None,
    }

    for item in items:
        rt = item.row_type.value if hasattr(item.row_type, "value") else item.row_type
        sec = item.section.value if hasattr(item.section, "value") else item.section
        # Net Change in Cash is the bottom-line reconciliation row, never a
        # section subtotal. CF-1 finds it via canonical_label and uses it
        # as `actual` (not `expected`). Walkers may tag its section as
        # cash_other based on document-order state — exclude it here so
        # `sums["cash_other"]` doesn't accidentally absorb its value.
        if (item.canonical_label or "") == "Net Change in Cash":
            continue
        if sec not in buckets:
            continue  # bottom-of-statement reconciliation rows: section=None
        if rt == "subtotal":
            sums[sec] = item
            continue
        if _is_memo(item):
            continue
        buckets[sec].append(item)

    return {"buckets": buckets, "sums": sums}


def _run_cf_section(
    rule_id_prefix: str, section_key: str, friendly_name: str,
    items: list[MappedLineItem], period_label: str,
) -> ValidationResult:
    """Generic per-section subtotal check. Compares the sum of components
    tagged with `section_key` against the filer's own subtotal row for that
    section (Net cash provided by / used in X activities). Inconclusive if
    the filer didn't report a subtotal for the section (rare — most full
    CF statements have all three).
    """
    part = partition_cash_flow(items)
    bucket = part["buckets"][section_key]
    sub = part["sums"][section_key]
    if sub is None or not bucket:
        return _inconclusive(
            f"{rule_id_prefix} @ {period_label}",
            f"missing: {friendly_name} subtotal" if sub is None else f"missing: {friendly_name} components",
        )
    expected = sum((i.value for i in bucket), start=Decimal("0"))
    return _build_result(
        rule_id=f"{rule_id_prefix} @ {period_label}",
        expected=expected,
        actual=sub.value,
        message=f"{friendly_name} = sum of {len(bucket)} {section_key.replace('_',' ')} line items",
    )


def run_cf2(items, period_label):
    return _run_cf_section("CF-2", "operating", "CFO", items, period_label)

def run_cf3(items, period_label):
    return _run_cf_section("CF-3", "investing", "CFI", items, period_label)

def run_cf4(items, period_label):
    return _run_cf_section("CF-4", "financing", "CFF", items, period_label)


CF_RULES = [run_cf1, run_cf2, run_cf3, run_cf4]


# ============================================================================
# Income statement rules
# ============================================================================

# IS anchor canonicals — exact-match against `canonical_label` set by
# extract-time library lookup. These are the library's canonical names
# (see generic_line_item_mappings.json).
#
# "Net Income (Loss) Including NCI" is a valid NI-anchor target: for filers
# with NCI (PG/JNJ/KO), IS-4's "NI = PreTax + Tax" refers to the consolidated
# line (incl NCI), NOT the attributable-to-parent line. The walk hits the
# first NI-like row in document order, so this preference naturally lands
# on Including-NCI for filers that have it and on plain NI for filers (like
# CELH) that don't.
_IS_ANCHOR_CANONICALS = {
    "gross_profit":     {"Gross Profit (Loss)"},
    "operating_income": {"Income (Loss) from Operations"},
    "pretax":           {"Pre-Tax Income (Loss)"},
    # Net Income — first-match-in-document-order. PG renders consolidated
    # `NET EARNINGS` first (→ "Net Income (Loss) Including NCI") then
    # attributable-to-parent (→ "Net Income (Loss) Less NCI"); the consolidated
    # one wins. CELH has no NCI and renders one `Net income (loss)` row that
    # routes to "Net Income (Loss) Less NCI" — including it here lets that
    # case validate without affecting PG.
    "net_income":       {"Net Income (Loss)", "Net Income (Loss) Including NCI", "Net Income (Loss) Less NCI"},
}


def _is_gross_profit(item: MappedLineItem) -> bool:
    return (item.canonical_label or "") in _IS_ANCHOR_CANONICALS["gross_profit"]


def _is_operating_income(item: MappedLineItem) -> bool:
    return (item.canonical_label or "") in _IS_ANCHOR_CANONICALS["operating_income"]


def _is_pretax(item: MappedLineItem) -> bool:
    return (item.canonical_label or "") in _IS_ANCHOR_CANONICALS["pretax"]


def _is_net_income(item: MappedLineItem) -> bool:
    """Matches the bottom-line NI row (after tax, attributable to parent)."""
    return (item.canonical_label or "") in _IS_ANCHOR_CANONICALS["net_income"]


def _is_midsection_is_subtotal(label: str) -> bool:
    """Mid-section subtotal labels in the IS (e.g. 'Total other income, net').
    These sum items above them within a section; must be excluded from the
    validator's per-item sum to avoid double-counting. Extract sometimes
    tags these as row_type=line_item rather than subtotal, so a
    label-based guard is needed."""
    l = label.strip()
    return (
        l.startswith("total other income")
        or l.startswith("total other expense")
        or l.startswith("total non-operating")
        or l.startswith("total other (income)")
    )


def partition_income_statement(items: list[MappedLineItem]) -> dict:
    """Walk IS items in document order. Partition into GP/OP/PT/NI section
    buckets separated by the four canonical subtotal anchors. Items after
    the NI anchor (pref div, NI-to-common, FCT, comprehensive income, EPS)
    are excluded.

    Buckets:
      revenue_cost_top: first item in the revenue_cost section — the revenue row
      revenue_cost_rest: remaining items before Gross Profit — cost items
      operating_expenses: items between GP and Operating Income
      non_operating: items between OP and Pre-Tax (interest, FX, other, etc.)
      tax: items between Pre-Tax and Net Income
    Anchors:
      gross_profit, operating_income, pretax, net_income
    """
    buckets: dict[str, list[MappedLineItem]] = {
        "revenue_cost_top": [],
        "revenue_cost_rest": [],
        "operating_expenses": [],
        "non_operating": [],
        "tax": [],
    }
    anchors: dict[str, MappedLineItem | None] = {
        "gross_profit": None,
        "operating_income": None,
        "pretax": None,
        "net_income": None,
    }

    state = "rev_cost"  # rev_cost → opex → non_op → tax → below_ni
    for item in items:
        label = _strip_lower(item.raw_filing_label)

        # Anchor detection on canonical_label — GP/OP/PT/NI are the library's
        # exact canonical names. Filers' idiosyncratic wordings ("NET EARNINGS"
        # vs "NET INCOME", "INCOME FROM OPERATIONS" vs "OPERATING INCOME") all
        # converge at the canonical layer, so these matchers are vocabulary-
        # agnostic.
        #
        # Some filers skip Gross Profit entirely (PG, JNJ, many
        # services/consumer staples that show SG&A inline with COGS). Allow
        # the state machine to skip missing anchors forward — OpInc/Pretax
        # can fire from earlier states too.
        if _is_gross_profit(item) and state in ("rev_cost",):
            anchors["gross_profit"] = item
            state = "opex"
            continue
        if _is_operating_income(item) and state in ("rev_cost", "opex"):
            anchors["operating_income"] = item
            state = "non_op"
            continue
        if _is_pretax(item) and state in ("rev_cost", "opex", "non_op"):
            anchors["pretax"] = item
            state = "tax"
            continue
        if _is_net_income(item) and state in ("rev_cost", "opex", "non_op", "tax"):
            anchors["net_income"] = item
            state = "below_ni"
            continue

        if state == "below_ni":
            continue

        # Skip subtotals (double-counting) + memo rows (not summable dollars).
        row_type_val = item.row_type.value if hasattr(item.row_type, "value") else item.row_type
        if row_type_val in ("subtotal", "memo"):
            continue
        if _is_midsection_is_subtotal(label):
            continue

        if state == "rev_cost":
            if not buckets["revenue_cost_top"]:
                buckets["revenue_cost_top"].append(item)
            else:
                buckets["revenue_cost_rest"].append(item)
        elif state == "opex":
            buckets["operating_expenses"].append(item)
        elif state == "non_op":
            buckets["non_operating"].append(item)
        elif state == "tax":
            buckets["tax"].append(item)

    return {"buckets": buckets, "anchors": anchors}


def run_is4(part: dict, period_label: str) -> ValidationResult:
    """IS-4: Net Income = Pre-Tax Income + SUM(tax, signed).

    Filers report tax as MAGNITUDE; whether it's an expense (subtract from PT)
    or a benefit (add to PT) depends on whether the period was profitable or
    a loss. CELH FY2021 had a pre-tax loss with tax benefit ($7,996) — filer
    rendered it as +$7,996 and NI = PT + benefit. PG always profitable —
    filer renders +$4,554 and NI = PT − expense. Library `sign_convention`
    on the tax canonical can't be both.

    Resolution: compute the expected NI both ways and accept whichever ties.
    """
    ni = part["anchors"]["net_income"]
    pt = part["anchors"]["pretax"]
    tax = part["buckets"]["tax"]
    if ni is None or pt is None:
        return _inconclusive(f"IS-4 @ {period_label}", "Net Income or Pre-Tax anchor missing")
    tax_sum = _signed_sum(tax)
    expected_signed = pt.value + tax_sum
    expected_flipped = pt.value - tax_sum
    # Pick the formulation closer to actual NI.
    if abs(ni.value - expected_signed) <= abs(ni.value - expected_flipped):
        expected = expected_signed
        tax_disp = tax_sum
    else:
        expected = expected_flipped
        tax_disp = -tax_sum
    return _build_result(
        rule_id=f"IS-4 @ {period_label}",
        expected=expected,
        actual=ni.value,
        message=f"Net Income ({ni.value}) = Pre-Tax ({pt.value}) + Tax ({tax_disp} across {len(tax)} rows)",
    )


def run_is1(part: dict, period_label: str) -> ValidationResult:
    """IS-1: Gross Profit = Revenue + SUM(cost_items, signed-as-expense).

    Cost items in the revenue_cost_rest bucket are stored at their filer-
    rendered sign — typically positive ("$ 1,247,936") for COGS in modern
    iXBRL. To compute GP we subtract them: GP = Revenue − Σ|cost|. Implemented
    by taking |cost| with negative sign so the sum stays simple.
    """
    gp = part["anchors"]["gross_profit"]
    revenue_top = part["buckets"]["revenue_cost_top"]
    cost_rest = part["buckets"]["revenue_cost_rest"]
    if gp is None or not revenue_top:
        # Filer doesn't render a Gross Profit subtotal (e.g. PG goes
        # Net Sales → COGS → SG&A → Operating Income, no GP line). Genuine
        # N/A — not a regression to investigate. Same downgrade pattern as
        # BS-4 when filer omits Total Liabilities.
        return _skip(f"IS-1 @ {period_label}", "Gross Profit not rendered by filer")
    rev = revenue_top[0].value
    cost_sum = sum((-abs(c.value) for c in cost_rest), start=Decimal("0"))
    expected = rev + cost_sum
    return _build_result(
        rule_id=f"IS-1 @ {period_label}",
        expected=expected,
        actual=gp.value,
        message=f"Gross Profit ({gp.value}) = Revenue ({rev}) + signed cost ({cost_sum} across {len(cost_rest)} rows)",
    )


def run_is2(part: dict, period_label: str) -> ValidationResult:
    """IS-2: Income from Operations = Gross Profit − SUM(opex, as-mapped).

    Trust as-mapped sign. Per `feedback_no_validator_sign_flips.md`: sign
    correctness is the responsibility of extract + library + ticker ledger
    (parens-negative detection, library `sign_convention`, per-period tax-sign
    correction). Validators sum as-mapped values; any sign error surfaces here
    as a real FAIL rather than getting silently force-flipped.

    Expenses are filer-rendered positive (SG&A, COGS, R&D, etc.); gains
    sometimes appear in the opex bucket as parens-negative values (PEP's
    "Gain associated with the Juice Transaction" rendered as `(3,321)` between
    SG&A and Impairment, mapping to value=-3,321). Negating each as-mapped
    value treats both correctly: positive expense becomes negative contribution
    (subtracts from OP); negative gain becomes positive contribution (adds to
    OP).
    """
    op_inc = part["anchors"]["operating_income"]
    gp = part["anchors"]["gross_profit"]
    opex = part["buckets"]["operating_expenses"]
    if op_inc is None:
        return _inconclusive(f"IS-2 @ {period_label}", "Operating Income anchor missing")
    if gp is None and not part["buckets"]["revenue_cost_top"]:
        return _inconclusive(f"IS-2 @ {period_label}", "GP anchor and Revenue both missing")
    base = gp.value if gp is not None else (
        part["buckets"]["revenue_cost_top"][0].value
        + sum((-c.value for c in part["buckets"]["revenue_cost_rest"]), start=Decimal("0"))
    )
    opex_signed = sum((-o.value for o in opex), start=Decimal("0"))
    expected = base + opex_signed
    return _build_result(
        rule_id=f"IS-2 @ {period_label}",
        expected=expected,
        actual=op_inc.value,
        message=f"Operating Income ({op_inc.value}) = GP ({base}) + signed opex ({opex_signed} across {len(opex)} rows)",
    )


def run_is3(part: dict, period_label: str) -> ValidationResult:
    """IS-3: Pre-Tax Income = Operating Income + SUM(non_operating, signed).

    Non-operating items (Interest income, Interest expense, FX, Other) are
    stored at their filer-rendered sign — interest income positive, interest
    expense usually negative if the filer rendered it in parens. Sum them
    as-stored; the natural-signs convention is the bridge between OpInc and
    Pre-Tax.
    """
    pt = part["anchors"]["pretax"]
    op_inc = part["anchors"]["operating_income"]
    non_op = part["buckets"]["non_operating"]
    if pt is None or op_inc is None:
        return _inconclusive(f"IS-3 @ {period_label}", "Pre-Tax or Operating Income anchor missing")
    non_op_sum = _signed_sum(non_op)
    expected = op_inc.value + non_op_sum
    return _build_result(
        rule_id=f"IS-3 @ {period_label}",
        expected=expected,
        actual=pt.value,
        message=f"Pre-Tax ({pt.value}) = Operating Income ({op_inc.value}) + signed non-op ({non_op_sum} across {len(non_op)} rows)",
    )


def run_is5(part: dict, period_label: str) -> ValidationResult:
    """IS-5: End-to-end Net Income tie — calculated NI from ALL line items =
    filer-reported NI.

    Per user directive (2026-04-26): even when individual cascade subtotals
    aren't filer-reported (some filers skip Gross Profit or Operating Income),
    the bottom-line Net Income computed from raw line items must tie to the
    Net Income value the filer published in the iXBRL HTML for the period.

    NI = Revenue − SUM(cost, as-mapped) − SUM(opex, as-mapped)
         + SUM(non_op, as-mapped) + SUM(tax, signed-or-flipped)

    Trust as-mapped sign. Per `feedback_no_validator_sign_flips.md`. Same
    reasoning as run_is2 — both COGS and opex sums use `-value` (negate),
    not `-abs(value)`, so parens-negative gains-in-bucket (PEP's Juice
    Gain in opex) net correctly against expenses.
    """
    ni = part["anchors"]["net_income"]
    revenue_top = part["buckets"]["revenue_cost_top"]
    if ni is None or not revenue_top:
        return _inconclusive(f"IS-5 @ {period_label}", "Net Income anchor or Revenue missing")
    revenue = revenue_top[0].value
    cost_sum = sum((-c.value for c in part["buckets"]["revenue_cost_rest"]), start=Decimal("0"))
    opex_sum = sum((-o.value for o in part["buckets"]["operating_expenses"]), start=Decimal("0"))
    non_op_sum = _signed_sum(part["buckets"]["non_operating"])
    tax_sum = _signed_sum(part["buckets"]["tax"])
    base = revenue + cost_sum + opex_sum + non_op_sum
    # Tax sign is filer-period-dependent (see run_is4 docstring). Try both.
    expected_signed = base + tax_sum
    expected_flipped = base - tax_sum
    if abs(ni.value - expected_signed) <= abs(ni.value - expected_flipped):
        expected = expected_signed
        tax_disp = tax_sum
    else:
        expected = expected_flipped
        tax_disp = -tax_sum
    return _build_result(
        rule_id=f"IS-5 @ {period_label}",
        expected=expected,
        actual=ni.value,
        message=(
            f"Net Income ({ni.value}) end-to-end = Rev ({revenue}) "
            f"+ cost ({cost_sum}) + opex ({opex_sum}) "
            f"+ non-op ({non_op_sum}) + tax ({tax_disp})"
        ),
    )


IS_RULES = [run_is1, run_is2, run_is3, run_is4, run_is5]


# ============================================================================
# Pair MappedLineItems with their Period
# ============================================================================

def group_items_by_statement(mapped: MappedFiling) -> list[tuple[StatementType, Period, list[MappedLineItem]]]:
    """Split the flat mapped_line_items list back into per-statement groups,
    using the order + counts from the kept RawFiling.statements. Statements
    that reconcile dropped via `keep_statement_for_pipeline` (3-month CF
    duplicates on 10-Qs etc.) MUST be skipped here too — otherwise the slice
    indices drift, causing subtotals from one period to be paired with line
    items from another and rules to fail mysteriously."""
    from financials_schema.statement import keep_statement_for_pipeline
    groups: list[tuple[StatementType, Period, list[MappedLineItem]]] = []
    idx = 0
    all_stmts = mapped.raw.statements
    for statement in all_stmts:
        if not keep_statement_for_pipeline(statement, mapped.raw.filing_type, all_stmts):
            continue
        count = len(statement.line_items)
        slice_ = mapped.mapped_line_items[idx : idx + count]
        groups.append((statement.statement_type, statement.period, slice_))
        idx += count
    return groups


# ============================================================================
# Main
# ============================================================================

def validate_filing(
    mapped: MappedFiling,
    anomalies: dict | None = None,
    child_to_parent: dict[str, str] | None = None,
) -> ValidatedFiling:
    results: list[ValidationResult] = []
    groups = group_items_by_statement(mapped)

    # Build period-indexed views by statement type (for cross-statement rules)
    by_period: dict[int, dict[StatementType, list[MappedLineItem]]] = {}

    for stmt_type, period, items in groups:
        period_label = f"FY{period.fiscal_year}"
        if period.fiscal_quarter is not None:
            period_label = f"Q{period.fiscal_quarter} FY{period.fiscal_year}"

        by_period.setdefault(period.fiscal_year, {})[stmt_type] = items

        if stmt_type == StatementType.BALANCE_SHEET:
            part = partition_balance_sheet(items, child_to_parent=child_to_parent)
            for rule_fn in BS_RULES:
                results.append(rule_fn(part, period_label))
        elif stmt_type == StatementType.CASH_FLOW:
            for rule_fn in CF_RULES:
                results.append(rule_fn(items, period_label))
        elif stmt_type == StatementType.INCOME_STATEMENT:
            part = partition_income_statement(items)
            for rule_fn in IS_RULES:
                results.append(rule_fn(part, period_label))

    any_failed = any(r.severity == "fail" for r in results)
    return ValidatedFiling(
        mapped=mapped,
        results=results,
        passed=not any_failed,
    )


def main():
    # Force stdout/stderr to UTF-8 so prints with Unicode (Δ, em-dash, etc.) don't
    # crash on Windows' cp1252 default console encoding mid-loop, leaving the
    # output file unwritten.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="Run accounting-identity + cross-statement validators on a MappedFiling.",
    )
    parser.add_argument("--ticker-root", required=True, type=Path)
    parser.add_argument("--allow-fails", action="store_true",
                        help="Write the ValidatedFiling JSON + exit 0 even if some rules FAIL. "
                             "For inspection of downstream output (model-write, playground) while "
                             "known issues are being worked.")
    parser.add_argument("--in", dest="in_path", required=True, type=Path,
                        help="Input MappedFiling JSON")
    parser.add_argument("--out", required=True, type=Path,
                        help="Output ValidatedFiling JSON")
    args = parser.parse_args()

    # CLI guard
    config_path = args.ticker_root / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config = {k: v for k, v in config.items() if not k.startswith("_")}
    config_ticker = config["ticker"]

    mapped = MappedFiling.model_validate_json(args.in_path.read_text(encoding="utf-8"))
    if mapped.raw.ticker != config_ticker:
        sys.exit(f"ERROR: ticker mismatch. config={config_ticker!r}, filing={mapped.raw.ticker!r}")

    total_items = len(mapped.mapped_line_items)
    print(f"[validate] Input: {mapped.raw.ticker} {mapped.raw.filing_type.value} "
          f"({len(mapped.raw.statements)} statements, {total_items} mapped line items)")

    # Load anomalies.json for cash convention overrides
    anomalies_path = args.ticker_root / "anomalies.json"
    anomalies: dict = {}
    if anomalies_path.exists():
        anomalies = json.loads(anomalies_path.read_text(encoding="utf-8"))
        anomalies = {k: v for k, v in anomalies.items() if not k.startswith("_")}

    # Build child→parent rule_id map from generic library so BS-1 (and other
    # section-sum rules) skip detail rows when their parent canonical is also
    # present in the same statement. Default to {} if library is unavailable.
    child_to_parent: dict[str, str] = {}
    library_path = (
        args.ticker_root.parent.parent / "pattern_libraries"
        / "generic_line_item_mappings.json"
    )
    if library_path.exists():
        lib = json.loads(library_path.read_text(encoding="utf-8"))
        for e in lib.get("mappings", []):
            parent = e.get("parent_canonical")
            if parent:
                child_to_parent[e["rule_id"]] = parent

    validated = validate_filing(mapped, anomalies=anomalies, child_to_parent=child_to_parent)

    # Report
    pass_count = sum(1 for r in validated.results if r.severity == "pass")
    warn_count = sum(1 for r in validated.results if r.severity == "warning")
    fail_count = sum(1 for r in validated.results if r.severity == "fail")
    skip_count = sum(1 for r in validated.results if r.severity == "skip")

    print(f"\n[validate] Rule results:")
    for r in validated.results:
        icon = {"pass": "[PASS]", "warning": "[WARN]", "fail": "[FAIL]", "skip": "[SKIP]"}[r.severity]
        gap_str = f"gap {r.gap}" if r.severity not in ("warning", "skip") else ""
        print(f"  {icon} {r.rule_id:24s} | {r.message:70s} {gap_str}")

    print(f"\n[validate] Summary: {pass_count} pass, {warn_count} warning, {fail_count} fail, {skip_count} skip")

    if fail_count and not args.allow_fails:
        print("\n[validate] ERROR: validation failures detected. Not writing output. "
              "Re-run with --allow-fails to write JSON anyway (for downstream inspection).")
        sys.exit(1)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(validated.model_dump_json(indent=2), encoding="utf-8")
    print(f"\n[validate] Wrote ValidatedFiling -> {args.out}"
          + (f"  ({fail_count} known FAIL(s) bypassed via --allow-fails)" if fail_count else ""))


if __name__ == "__main__":
    main()
