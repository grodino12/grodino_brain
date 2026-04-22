from datetime import date

from pydantic import BaseModel, Field


class Period(BaseModel):
    """Fiscal period identity, resolved from varied filing notations."""

    fiscal_year: int = Field(ge=1990, le=2100)
    fiscal_quarter: int | None = Field(default=None, ge=1, le=4)
    period_end_date: date
    raw_period_label: str
    period_length_weeks: int | None = None
    is_comparative: bool = False
