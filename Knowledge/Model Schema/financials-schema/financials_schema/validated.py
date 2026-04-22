from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, model_validator

from financials_schema.mapped import MappedFiling


Severity = Literal["pass", "warning", "fail"]


class ValidationResult(BaseModel):
    """Outcome of one accounting-identity or cross-statement rule."""

    rule_id: str
    expected: Decimal
    actual: Decimal
    gap: Decimal
    severity: Severity
    message: str


class ValidatedFiling(BaseModel):
    """Output of financials-validate. MappedFiling + results + overall pass flag."""

    mapped: MappedFiling
    results: list[ValidationResult]
    passed: bool

    @model_validator(mode="after")
    def all_results_pass_or_override(self) -> "ValidatedFiling":
        fails = [r for r in self.results if r.severity == "fail"]
        if fails and self.passed:
            raise ValueError(
                f"ValidatedFiling marked passed=True but {len(fails)} rules failed: "
                f"{[r.rule_id for r in fails]}"
            )
        return self
