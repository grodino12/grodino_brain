"""Pydantic contracts for the financials-pipeline skills."""
from financials_schema.enums import (
    FilingType,
    NumericNotation,
    Section,
    StatementType,
    Unit,
)
from financials_schema.citation import Citation
from financials_schema.period import Period
from financials_schema.line_item import MappedLineItem, RawLineItem
from financials_schema.statement import Statement, keep_statement_for_pipeline
from financials_schema.filing import RawFiling
from financials_schema.mapped import MappedFiling, NovelItem
from financials_schema.validated import ValidatedFiling, ValidationResult
from financials_schema.patterns import (
    PatternEntry,
    PatternLibrary,
    RegexPattern,
    RegexPatternEntry,
)
from financials_schema.lookup import (
    IXBRL_SUBTOTAL_CONCEPTS,
    LibraryEntry,
    build_generic_index,
    is_subtotal_label,
    load_generic_library,
    match_raw_item,
    nearest_matches,
    normalize_label,
    select_entry,
)

__all__ = [
    "Citation",
    "FilingType",
    "IXBRL_SUBTOTAL_CONCEPTS",
    "LibraryEntry",
    "MappedFiling",
    "MappedLineItem",
    "NovelItem",
    "NumericNotation",
    "PatternEntry",
    "PatternLibrary",
    "Period",
    "RawFiling",
    "RawLineItem",
    "RegexPattern",
    "RegexPatternEntry",
    "Section",
    "Statement",
    "StatementType",
    "Unit",
    "ValidatedFiling",
    "ValidationResult",
    "build_generic_index",
    "is_subtotal_label",
    "keep_statement_for_pipeline",
    "load_generic_library",
    "match_raw_item",
    "nearest_matches",
    "normalize_label",
    "select_entry",
]

__version__ = "0.1.0"
