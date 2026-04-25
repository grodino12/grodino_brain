from typing import Literal

from pydantic import BaseModel, Field, model_validator

from financials_schema.enums import StatementType, Unit
from financials_schema.line_item import RawLineItem
from financials_schema.period import Period


UnitDetectionSource = Literal[
    "explicit_header",
    "plausibility_inferred",
    "ledger_override",
]

Dialect = Literal["US_GAAP", "IFRS", "foreign_20F"]


class Statement(BaseModel):
    """A single financial statement (BS / CF / IS) for one period."""

    statement_type: StatementType
    period: Period
    unit: Unit
    raw_unit_phrase: str
    unit_detection_source: UnitDetectionSource
    unit_detection_confidence: float = Field(ge=0, le=1)
    share_unit: Unit = Unit.ACTUAL
    eps_unit: Unit = Unit.ACTUAL
    currency: str = "USD"
    dialect: Dialect = "US_GAAP"
    line_items: list[RawLineItem]

    @model_validator(mode="after")
    def reject_unknown_unit(self) -> "Statement":
        if self.unit == Unit.UNKNOWN:
            raise ValueError(
                f"Statement {self.statement_type} for fiscal_year="
                f"{self.period.fiscal_year} has Unit.UNKNOWN. "
                "Extraction must resolve the unit before construction."
            )
        return self


def keep_statement_for_pipeline(
    stmt: "Statement",
    filing_type: FilingType,
    all_stmts: "list[Statement] | None" = None,
) -> bool:
    """Whether downstream (reconcile / model-write) should keep this Statement.

    For 10-Qs, IS/CF facts come at multiple durations (3-month + YTD) for the
    same period_end. Keep the longest (YTD) and drop shorter same-period_end
    duplicates — filers report CF only as YTD, so picking the 3-month would
    leave CF empty for H1/9M filings.

    BS instants always kept (no duration choice).
    Non-10-Q (10-K / 8-K / press release): all kept.

    Single source of truth — both reconcile and model-write call this.
    """
    if filing_type != FilingType.TEN_Q:
        return True
    if stmt.statement_type == StatementType.BALANCE_SHEET:
        return True
    weeks = stmt.period.period_length_weeks
    if weeks is None:
        return False
    if all_stmts is None:
        return True
    competitors = [
        s for s in all_stmts
        if s.statement_type == stmt.statement_type
        and s.period.period_end_date == stmt.period.period_end_date
    ]
    max_weeks = max((s.period.period_length_weeks or 0) for s in competitors)
    return weeks == max_weeks
