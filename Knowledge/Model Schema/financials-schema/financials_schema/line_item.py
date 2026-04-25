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
    "as_reported",   # default: pass value through as-is
    "positive",      # always render as +abs(value), regardless of filer's sign
    "negative",      # always render as -abs(value), regardless of filer's sign
]

MappingSource = Literal["ledger_auto", "user_decision", "novel"]


class RawLineItem(BaseModel):
    """A single extracted line item in the native unit of its parent Statement.

    `raw_filing_label` holds the filer's literal wording (the audit trail —
    what the filer actually wrote). `canonical_label` holds the canonical
    label from the generic library (populated at extract time via library
    lookup). Unmatched items keep `canonical_label=None` → surface as novels
    downstream."""

    model_config = ConfigDict(frozen=True)

    raw_filing_label: str
    canonical_label: str | None = None      # universal across filings (library lookup)
    ledger_rule_id: str | None = None       # generic-library or ticker-ledger rule_id that matched
    value: Decimal
    raw_numeric_text: str
    notation_flags: NumericNotation = NumericNotation.NONE
    footnote_markers: list[str] = []
    indent_level: int = 2
    row_type: RowType = "line_item"
    section: Section = Section.UNCLASSIFIED
    subsection_context: str | None = None
    sign_convention: SignConvention = "as_reported"
    citation: Citation


class MappedLineItem(RawLineItem):
    """RawLineItem plus mapping to a specific Excel model row.

    `model_label` is the rendered row label — usually == canonical_label,
    but ticker-ledger overrides can replace it. `model_sheet` + `model_row`
    are Excel-positioning metadata set by reconcile based on filing_type."""

    model_sheet: str
    model_row: int
    model_label: str
    mapping_source: MappingSource
