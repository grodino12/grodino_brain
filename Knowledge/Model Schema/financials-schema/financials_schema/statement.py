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
