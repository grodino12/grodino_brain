from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class PatternEntry(BaseModel):
    """Phrase-match entry. Output: a canonical enum key (string)."""

    canonical: str
    keywords: list[str] = []
    variants: list[str] = []
    fuzzy_threshold: int = Field(default=85, ge=0, le=100)


class RegexPattern(BaseModel):
    """A single regex with named capture-group mappings to target field names."""

    pattern: str
    captures: dict[int, str] = {}
    description: str | None = None


class RegexPatternEntry(BaseModel):
    """Regex-based pattern entry for structured extraction (e.g. periods)."""

    canonical: str
    regex_patterns: list[RegexPattern]


class PatternLibrary(BaseModel):
    """A loaded YAML pattern file. One library per enum it resolves to."""

    entries: dict[str, PatternEntry | RegexPatternEntry]
    file_path: Path
    last_updated: datetime

    @model_validator(mode="after")
    def no_duplicate_variants(self) -> "PatternLibrary":
        seen: dict[str, str] = {}
        for key, entry in self.entries.items():
            if isinstance(entry, PatternEntry):
                for variant in entry.variants:
                    norm = variant.lower().strip()
                    if norm in seen and seen[norm] != key:
                        raise ValueError(
                            f"Duplicate variant {variant!r} found in entries "
                            f"{seen[norm]!r} and {key!r}"
                        )
                    seen[norm] = key
        return self
