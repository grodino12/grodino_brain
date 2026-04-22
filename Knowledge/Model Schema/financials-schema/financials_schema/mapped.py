from pydantic import BaseModel, model_validator

from financials_schema.filing import RawFiling
from financials_schema.line_item import MappedLineItem, RawLineItem


class NovelItem(BaseModel):
    """A raw line item with no matching ledger rule — needs a user decision."""

    raw_item: RawLineItem
    nearest_matches: list[tuple[str, float]] = []


class MappedFiling(BaseModel):
    """Output of financials-reconcile. Wraps a RawFiling + mapping decisions."""

    raw: RawFiling
    mapped_line_items: list[MappedLineItem]
    novel_items: list[NovelItem] = []

    @model_validator(mode="after")
    def no_unresolved_novel_items(self) -> "MappedFiling":
        if self.novel_items:
            raise ValueError(
                f"MappedFiling has {len(self.novel_items)} unresolved novel items. "
                "Resolve all novel items before constructing a MappedFiling."
            )
        return self
