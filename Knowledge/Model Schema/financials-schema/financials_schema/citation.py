from pathlib import Path

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """Pointer back to a specific location in the source PDF."""

    source_path: Path
    page: int = Field(ge=1)
    line_hint: str | None = None
    note: str | None = None
