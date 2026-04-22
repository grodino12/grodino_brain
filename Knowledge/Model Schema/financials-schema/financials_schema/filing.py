from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from financials_schema.enums import FilingType, StatementType
from financials_schema.statement import Statement


class RawFiling(BaseModel):
    """Top-level output of financials-extract — a full extracted filing."""

    ticker: str = Field(pattern=r"^[A-Z\.]{1,6}$")
    filing_type: FilingType
    filing_date: date
    source_path: Path
    statements: list[Statement]
    extraction_metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def at_least_one_statement(self) -> "RawFiling":
        if not self.statements:
            raise ValueError(
                f"RawFiling for {self.source_path} has zero statements"
            )
        return self

    @model_validator(mode="after")
    def press_release_has_only_income_statement(self) -> "RawFiling":
        if self.filing_type == FilingType.PRESS_RELEASE:
            non_is = [
                s for s in self.statements
                if s.statement_type != StatementType.INCOME_STATEMENT
            ]
            if non_is:
                raise ValueError(
                    f"Press release {self.source_path} has non-IS statements: "
                    f"{[s.statement_type.value for s in non_is]}. "
                    "Press releases should contain IS only."
                )
        return self
