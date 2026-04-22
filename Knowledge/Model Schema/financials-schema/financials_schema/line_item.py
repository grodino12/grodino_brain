from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from financials_schema.citation import Citation
from financials_schema.enums import NumericNotation, Section


RowType = Literal[
    "section_header",
    "subsection_header",
    "line_item",
    "subtotal",
    "total",
    "memo",
]

SignConvention = Literal[
    "as_reported",
    "parens_negative",
    "expense_positive",
    "contra_account",
    "absolute_from_section_header",
]

MappingSource = Literal["ledger_auto", "user_decision", "novel"]


class RawLineItem(BaseModel):
    """A single extracted line item in the native unit of its parent Statement."""

    model_config = ConfigDict(frozen=True)

    raw_filing_label: str
    value: Decimal
    raw_numeric_text: str
    notation_flags: NumericNotation = NumericNotation.NONE
    footnote_markers: list[str] = []
    indent_level: int = 2
    row_type: RowType = "line_item"
    section: Section = Section.UNCLASSIFIED
    sign_convention: SignConvention = "as_reported"
    citation: Citation


class MappedLineItem(RawLineItem):
    """RawLineItem plus mapping to a specific Excel model row."""

    model_sheet: str
    model_row: int
    model_label: str
    mapping_source: MappingSource
    ledger_rule_id: str | None = None
