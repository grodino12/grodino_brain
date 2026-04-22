# Pydantic Schema Spec

Canonical text version of `02_pydantic_schema.html`. Every class in the `financials-schema/` shared package, grouped by layer.

---

## Shared · Enums

Closed sets of allowed values. Every variant phrase from a filing resolves to one of these via a pattern library.

```python
class Unit(str, Enum):
    THOUSANDS = "thousands"
    MILLIONS  = "millions"
    BILLIONS  = "billions"
    ACTUAL    = "actual"
    UNKNOWN   = "unknown"  # detection failed; triggers validator error

class StatementType(str, Enum):
    BALANCE_SHEET    = "BS"
    CASH_FLOW        = "CF"
    INCOME_STATEMENT = "IS"

class FilingType(str, Enum):
    TEN_K         = "10-K"
    TEN_Q         = "10-Q"
    PRESS_RELEASE = "press_release"
    EIGHT_K       = "8-K"

class Section(str, Enum):
    # Balance sheet
    CURRENT_ASSETS = "current_assets"
    NON_CURRENT_ASSETS = "non_current_assets"
    CURRENT_LIABILITIES = "current_liabilities"
    NON_CURRENT_LIABILITIES = "non_current_liabilities"
    MEZZANINE = "mezzanine"
    EQUITY = "equity"
    # Cash flow
    OPERATING = "operating"
    INVESTING = "investing"
    FINANCING = "financing"
    FX_RECONCILIATION = "fx_reconciliation"
    # Income statement
    REVENUE_COST = "revenue_cost"
    OPERATING_EXPENSES = "operating_expenses"
    NON_OPERATING = "non_operating"
    TAX = "tax"
    EPS = "eps"
    # Fallback
    UNCLASSIFIED = "unclassified"

class NumericNotation(Flag):
    NONE                 = 0
    PARENS_NEGATIVE      = auto()  # $(1,234)
    NEGATIVE_MINUS       = auto()  # -1,234
    ZERO_DASH            = auto()  # — or -
    DOLLAR_SIGN          = auto()  # $1,234
    TRAILING_ASTERISK    = auto()  # 1,234*
    HAS_FOOTNOTE         = auto()  # (1)(2)
    SUPERSCRIPT_SUFFIX   = auto()  # "$1.3B"
```

---

## Shared · Pattern libraries

Pydantic models that validate the YAML pattern files. One pattern library per enum.

```python
class PatternEntry(BaseModel):
    """Phrase-match entry. Output: a canonical enum key (string)."""
    canonical: str
    keywords: list[str] = []          # Layer 2 keyword match
    variants: list[str] = []          # Layer 3 fuzzy match
    fuzzy_threshold: int = Field(ge=0, le=100, default=85)

class RegexPattern(BaseModel):
    """One regex with named capture groups mapped to target field names."""
    pattern: str
    captures: dict[int, str]  # capture group index → target field name

class RegexPatternEntry(BaseModel):
    """Regex-match entry for structured extraction (e.g. periods)."""
    canonical: str
    regex_patterns: list[RegexPattern]

class PatternLibrary(BaseModel):
    """A loaded YAML pattern file. One file per enum."""
    entries: dict[str, PatternEntry | RegexPatternEntry]
    file_path: Path
    last_updated: datetime

    @model_validator(mode="after")
    def no_duplicate_variants(self):
        # every variant string appears in at most one entry
        ...
```

---

## Layer 1 · Raw Filing

Output of `financials-extract`.

```python
class Citation(BaseModel):
    source_path: Path
    page:        int = Field(ge=1)
    line_hint:   str | None = None   # raw PDF row text for audit
    note:        str | None = None

class Period(BaseModel):
    fiscal_year:        int = Field(ge=1990, le=2100)
    fiscal_quarter:     int | None = Field(default=None, ge=1, le=4)
    period_end_date:    date
    raw_period_label:   str         # "52 weeks ended Dec 30, 2023"
    period_length_weeks: int | None = None  # 52/53-week fiscal years
    is_comparative:     bool = False

class RawLineItem(BaseModel):
    raw_filing_label:  str       # verbatim from PDF
    value:             Decimal   # in the native Unit of the parent Statement
    raw_numeric_text:  str       # "(101,726)" or "—" as originally written
    notation_flags:    NumericNotation = NumericNotation.NONE
    footnote_markers:  list[str] = []
    indent_level:      int = 2
    row_type:          Literal[
        "section_header", "subsection_header",
        "line_item", "subtotal", "total", "memo"
    ] = "line_item"
    section:           Section = Section.UNCLASSIFIED
    sign_convention:   Literal[
        "as_reported", "parens_negative", "expense_positive",
        "contra_account", "absolute_from_section_header"
    ] = "as_reported"
    citation:          Citation

    model_config = ConfigDict(frozen=True)

class Statement(BaseModel):
    statement_type:             StatementType
    period:                     Period
    unit:                       Unit
    raw_unit_phrase:            str    # "(in thousands, except per share...)"
    unit_detection_source:      Literal["explicit_header", "plausibility_inferred", "ledger_override"]
    unit_detection_confidence:  float = Field(ge=0, le=1)
    share_unit:                 Unit = Unit.ACTUAL
    eps_unit:                   Unit = Unit.ACTUAL
    currency:                   str = "USD"
    dialect:                    Literal["US_GAAP", "IFRS", "foreign_20F"] = "US_GAAP"
    line_items:                 list[RawLineItem]

    @model_validator(mode="after")
    def reject_unknown_unit(self): ...

    @model_validator(mode="after")
    def plausibility_check_unit(self): ...

class RawFiling(BaseModel):
    ticker:       str = Field(pattern=r"^[A-Z\.]{1,6}$")
    filing_type:  FilingType
    filing_date:  date
    source_path:  Path
    statements:   list[Statement]
    extraction_metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def at_least_one_statement(self): ...

    @model_validator(mode="after")
    def press_release_has_only_income_statement(self): ...
```

---

## Layer 2 · Mapped Filing

Output of `financials-reconcile`.

```python
class MappedLineItem(RawLineItem):
    """RawLineItem plus mapping to a specific Excel model row."""
    model_sheet:      str
    model_row:        int
    model_label:      str
    mapping_source:   Literal["ledger_auto", "user_decision", "novel"]
    ledger_rule_id:   str | None = None

class NovelItem(BaseModel):
    """A raw item with no ledger match. Surfaces fuzzy candidates for user decision."""
    raw_item:        RawLineItem
    nearest_matches: list[tuple[str, float]]  # (ledger rule key, rapidfuzz score)

class MappedFiling(BaseModel):
    raw:                 RawFiling          # wrapped for provenance
    mapped_line_items:   list[MappedLineItem]
    novel_items:         list[NovelItem] = []

    @model_validator(mode="after")
    def no_unresolved_novel_items(self): ...
```

---

## Layer 3 · Validated Filing

Output of `financials-validate`.

```python
class ValidationResult(BaseModel):
    rule_id:   str                                             # "BS-6", "CF-1", "X-2", ...
    expected:  Decimal
    actual:    Decimal
    gap:       Decimal
    severity:  Literal["pass", "warning", "fail"]
    message:   str

class ValidatedFiling(BaseModel):
    mapped:   MappedFiling                                     # wrapped for provenance
    results:  list[ValidationResult]
    passed:   bool

    @model_validator(mode="after")
    def all_results_pass_or_override(self): ...
```

### Validation rules implemented

| ID | Check |
|---|---|
| BS-1 | Total current assets = sum of current-asset line items |
| BS-2 | Total assets = TCA + sum of non-current assets |
| BS-3 | Total current liabilities = sum of current-liability line items |
| BS-4 | Total liabilities = TCL + sum of non-current liabilities |
| BS-5 | Total stockholders' equity = sum of equity components |
| BS-6 | Accounting equation: Total assets = Total liabilities + Mezzanine + Equity |
| BS-7 | RE roll-forward: RE(t) = RE(t-1) + NI(t) − PrefDiv(t) |
| CF-1 | CFO + CFI + CFF + FX effect = Net change in cash |
| CF-2 | Cash end of period = Cash beginning + Net change |
| X-1 | CF Net income = P&L Net income |
| X-2 | CF Cash end = Balance sheet Cash (with ledger-based cash convention) |
| X-4 | CF Preferred dividends paid = P&L Preferred dividends |

---

## Layer 4 · Derived Calcs

Output of `model-calc`.

```python
class ScenarioInputs(BaseModel):
    glp1_share_curve:      list[tuple[int, float]]   # [(year, share_%), ...]
    snap_ban_drag_by_state: dict[str, float]         # state → volume drag %
    terminal_growth:       float
    wacc:                  float

class DerivedCalcs(BaseModel):
    growth:           GrowthTable       # YoY + CAGR
    margins:          MarginTable       # GP, OP, NI margins
    working_capital:  WcRatios          # DSO, DIO, DPO, CCC
    scenarios:        ScenarioGrid      # base / bull / bear
```

---

## Design notes

### Native-unit values

RawLineItem's `value` is stored in the **native unit** of the parent Statement, not pre-converted to $thousands. Rationale: preserve audit fidelity from the PDF. Conversion to a single canonical unit happens once in the validate layer via `Statement.as_thousands()`.

### Russian-doll wrapping

Each layer **wraps** the prior output rather than replacing it.

```
ValidatedFiling  ⊃  MappedFiling  ⊃  RawFiling  ⊃  Statement[]  ⊃  RawLineItem[]  ⊃  Citation
```

From a final `ValidatedFiling`, you can walk backward to any source PDF citation with zero detective work.

### Open questions

1. Whether to split `RegexPatternEntry` and `PatternEntry` or unify into one class with optional regex field. Current spec keeps them separate.
2. Whether `DerivedCalcs` sub-models (`GrowthTable`, `MarginTable`, `WcRatios`, `ScenarioGrid`) live in `financials-schema/` or inside `model-calc` itself.
3. Comprehensive income / equity roll-forward statements — out of scope for v1.
