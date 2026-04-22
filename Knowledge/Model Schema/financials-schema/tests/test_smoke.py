"""Smoke tests — every schema class can be constructed and validators fire correctly."""
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from financials_schema import (
    Citation,
    FilingType,
    MappedFiling,
    MappedLineItem,
    NovelItem,
    NumericNotation,
    PatternEntry,
    PatternLibrary,
    Period,
    RawFiling,
    RawLineItem,
    Section,
    Statement,
    StatementType,
    Unit,
    ValidatedFiling,
    ValidationResult,
)


# ---------- fixture helpers ----------

def _citation() -> Citation:
    return Citation(
        source_path=Path("tests/fixtures/dummy.pdf"),
        page=50,
        line_hint="Cash and cash equivalents 890,190",
    )


def _period() -> Period:
    return Period(
        fiscal_year=2024,
        fiscal_quarter=None,
        period_end_date=date(2024, 12, 31),
        raw_period_label="December 31, 2024",
        is_comparative=False,
    )


def _raw_line_item() -> RawLineItem:
    return RawLineItem(
        raw_filing_label="Cash and cash equivalents",
        value=Decimal("890190"),
        raw_numeric_text="$ 890,190",
        notation_flags=NumericNotation.DOLLAR_SIGN,
        section=Section.CURRENT_ASSETS,
        citation=_citation(),
    )


def _statement() -> Statement:
    return Statement(
        statement_type=StatementType.BALANCE_SHEET,
        period=_period(),
        unit=Unit.THOUSANDS,
        raw_unit_phrase="(in thousands, except per share and share amounts)",
        unit_detection_source="explicit_header",
        unit_detection_confidence=0.95,
        line_items=[_raw_line_item()],
    )


def _raw_filing() -> RawFiling:
    return RawFiling(
        ticker="CELH",
        filing_type=FilingType.TEN_K,
        filing_date=date(2025, 2, 21),
        source_path=Path("tests/fixtures/dummy.pdf"),
        statements=[_statement()],
    )


# ---------- enum tests ----------

def test_enums_have_expected_values():
    assert Unit.THOUSANDS == "thousands"
    assert StatementType.BALANCE_SHEET == "BS"
    assert FilingType.TEN_K == "10-K"
    assert Section.CURRENT_ASSETS == "current_assets"


def test_numeric_notation_is_flag_combinable():
    combined = NumericNotation.DOLLAR_SIGN | NumericNotation.PARENS_NEGATIVE
    assert NumericNotation.DOLLAR_SIGN in combined
    assert NumericNotation.PARENS_NEGATIVE in combined
    assert NumericNotation.ZERO_DASH not in combined


# ---------- citation tests ----------

def test_citation_requires_page_at_least_one():
    with pytest.raises(ValidationError):
        Citation(source_path=Path("x.pdf"), page=0)


def test_citation_happy_path():
    c = _citation()
    assert c.page == 50


# ---------- statement tests ----------

def test_statement_rejects_unknown_unit():
    with pytest.raises(ValidationError):
        Statement(
            statement_type=StatementType.BALANCE_SHEET,
            period=_period(),
            unit=Unit.UNKNOWN,
            raw_unit_phrase="???",
            unit_detection_source="plausibility_inferred",
            unit_detection_confidence=0.0,
            line_items=[],
        )


def test_statement_happy_path():
    s = _statement()
    assert s.unit == Unit.THOUSANDS
    assert len(s.line_items) == 1


# ---------- filing tests ----------

def test_raw_filing_rejects_zero_statements():
    with pytest.raises(ValidationError):
        RawFiling(
            ticker="CELH",
            filing_type=FilingType.TEN_K,
            filing_date=date(2025, 2, 21),
            source_path=Path("x.pdf"),
            statements=[],
        )


def test_raw_filing_rejects_press_release_with_balance_sheet():
    with pytest.raises(ValidationError):
        RawFiling(
            ticker="CELH",
            filing_type=FilingType.PRESS_RELEASE,
            filing_date=date(2025, 2, 21),
            source_path=Path("pr.pdf"),
            statements=[_statement()],
        )


def test_raw_filing_accepts_10k_with_balance_sheet():
    f = _raw_filing()
    assert f.ticker == "CELH"
    assert f.filing_type == FilingType.TEN_K


# ---------- inheritance tests ----------

def test_mapped_line_item_inherits_from_raw_line_item():
    raw = _raw_line_item()
    mapped = MappedLineItem(
        **raw.model_dump(),
        model_sheet="BALANCE SHEET",
        model_row=9,
        model_label="Cash & Cash Equivalents",
        mapping_source="ledger_auto",
        ledger_rule_id="MAP-BS-001",
    )
    # Inherited fields
    assert mapped.raw_filing_label == raw.raw_filing_label
    assert mapped.value == raw.value
    assert mapped.citation.page == 50
    # New fields
    assert mapped.model_row == 9
    assert mapped.mapping_source == "ledger_auto"


# ---------- mapped filing tests ----------

def test_mapped_filing_rejects_unresolved_novel_items():
    novel = NovelItem(raw_item=_raw_line_item(), nearest_matches=[])
    with pytest.raises(ValidationError):
        MappedFiling(
            raw=_raw_filing(),
            mapped_line_items=[],
            novel_items=[novel],
        )


# ---------- validated filing tests ----------

def test_validated_filing_rejects_passed_true_with_failures():
    mapped = MappedFiling(
        raw=_raw_filing(),
        mapped_line_items=[],
        novel_items=[],
    )
    result = ValidationResult(
        rule_id="BS-1",
        expected=Decimal("1000"),
        actual=Decimal("900"),
        gap=Decimal("100"),
        severity="fail",
        message="Gap too large",
    )
    with pytest.raises(ValidationError):
        ValidatedFiling(mapped=mapped, results=[result], passed=True)


def test_validated_filing_happy_path():
    mapped = MappedFiling(
        raw=_raw_filing(),
        mapped_line_items=[],
        novel_items=[],
    )
    pass_result = ValidationResult(
        rule_id="BS-1",
        expected=Decimal("1000"),
        actual=Decimal("1000"),
        gap=Decimal("0"),
        severity="pass",
        message="TCA sum matches",
    )
    v = ValidatedFiling(mapped=mapped, results=[pass_result], passed=True)
    assert v.passed is True


# ---------- pattern library tests ----------

def test_pattern_entry_happy_path():
    e = PatternEntry(
        canonical="THOUSANDS",
        keywords=["thousand", "thousands"],
        variants=["(in thousands"],
    )
    assert e.fuzzy_threshold == 85


def test_pattern_library_rejects_duplicate_variants():
    lib_data = {
        "entries": {
            "thousands": PatternEntry(
                canonical="THOUSANDS",
                keywords=["thousand"],
                variants=["(in thousands"],
            ),
            "millions": PatternEntry(
                canonical="MILLIONS",
                keywords=["million"],
                variants=["(in thousands"],  # duplicate!
            ),
        },
        "file_path": Path("unit_phrases.json"),
        "last_updated": datetime(2026, 4, 22),
    }
    with pytest.raises(ValidationError):
        PatternLibrary(**lib_data)


# ---------- end-to-end ----------

def test_end_to_end_construction():
    f = _raw_filing()
    assert f.ticker == "CELH"
    assert len(f.statements) == 1
    assert f.statements[0].line_items[0].value == Decimal("890190")
    # Round-trip through JSON
    as_json = f.model_dump_json()
    reconstructed = RawFiling.model_validate_json(as_json)
    assert reconstructed.ticker == "CELH"
    assert reconstructed.statements[0].line_items[0].value == Decimal("890190")
