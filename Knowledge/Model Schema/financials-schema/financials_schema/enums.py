from enum import Enum, Flag, auto


class Unit(str, Enum):
    THOUSANDS = "thousands"
    MILLIONS = "millions"
    BILLIONS = "billions"
    ACTUAL = "actual"
    UNKNOWN = "unknown"


class StatementType(str, Enum):
    BALANCE_SHEET = "BS"
    CASH_FLOW = "CF"
    INCOME_STATEMENT = "IS"


class FilingType(str, Enum):
    TEN_K = "10-K"
    TEN_Q = "10-Q"
    PRESS_RELEASE = "press_release"
    EIGHT_K = "8-K"


class Section(str, Enum):
    CURRENT_ASSETS = "current_assets"
    NON_CURRENT_ASSETS = "non_current_assets"
    CURRENT_LIABILITIES = "current_liabilities"
    NON_CURRENT_LIABILITIES = "non_current_liabilities"
    MEZZANINE = "mezzanine"
    EQUITY = "equity"
    OPERATING = "operating"
    INVESTING = "investing"
    FINANCING = "financing"
    CASH_OTHER = "cash_other"
    REVENUE_COST = "revenue_cost"
    OPERATING_EXPENSES = "operating_expenses"
    NON_OPERATING = "non_operating"
    TAX = "tax"
    EPS = "eps"
    UNCLASSIFIED = "unclassified"


class NumericNotation(Flag):
    NONE = 0
    PARENS_NEGATIVE = auto()
    NEGATIVE_MINUS = auto()
    ZERO_DASH = auto()
    DOLLAR_SIGN = auto()
    TRAILING_ASTERISK = auto()
    HAS_FOOTNOTE = auto()
    SUPERSCRIPT_SUFFIX = auto()
