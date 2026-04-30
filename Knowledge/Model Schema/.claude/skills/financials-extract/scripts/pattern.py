"""Pattern library loader + 4-layer matching ladder."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from financials_schema import (
    PatternEntry,
    PatternLibrary,
    RegexPattern,
    RegexPatternEntry,
)


def _strip_underscore_keys(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if not k.startswith("_")}


def load_pattern_library(json_path: Path) -> tuple[PatternLibrary, dict]:
    """Load a JSON pattern file. Returns (PatternLibrary, normalization_config)."""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    normalization = data.get("normalization", {})
    raw_entries = data.get("entries", {})

    entries: dict[str, PatternEntry | RegexPatternEntry] = {}
    for key, entry_data in raw_entries.items():
        clean = _strip_underscore_keys(entry_data)
        if "regex_patterns" in clean:
            regex_patterns = [RegexPattern(**rp) for rp in clean["regex_patterns"]]
            entries[key] = RegexPatternEntry(
                canonical=clean["canonical"],
                regex_patterns=regex_patterns,
            )
        else:
            entries[key] = PatternEntry(
                canonical=clean["canonical"],
                keywords=clean.get("keywords", []),
                variants=clean.get("variants", []),
                fuzzy_threshold=clean.get("fuzzy_threshold", 85),
            )

    lib = PatternLibrary(
        entries=entries,
        file_path=json_path,
        last_updated=datetime.now(),
    )
    return lib, normalization


def normalize_text(text: str, rules: dict) -> str:
    """Apply normalization rules (case, whitespace, punctuation, prefixes)."""
    if rules.get("case_insensitive", False):
        text = text.lower()
    if rules.get("collapse_whitespace", False):
        text = " ".join(text.split())
    for prefix in rules.get("strip_prefixes", []):
        text = re.sub(
            r"^\s*" + re.escape(prefix.lower() if rules.get("case_insensitive") else prefix) + r"[\s:]*",
            "",
            text,
            flags=re.IGNORECASE if rules.get("case_insensitive") else 0,
        )
    if rules.get("strip_punctuation", False):
        text = re.sub(r"[^\w\s\-]", "", text)
    return text.strip()


def match_phrase(
    text: str,
    library: PatternLibrary,
    normalization: dict,
) -> dict | None:
    """Run the 4-layer ladder on free-form text.

    Returns a dict with keys: entry_key, canonical, confidence, source, matched_variant.
    Returns None if no match at all.
    """
    if not text:
        return None

    normalized = normalize_text(text, normalization)
    if not normalized:
        return None

    # Layer 2 — keyword match
    for key, entry in library.entries.items():
        if not isinstance(entry, PatternEntry):
            continue
        for keyword in entry.keywords:
            kw_norm = normalize_text(keyword, normalization)
            if kw_norm and kw_norm in normalized:
                return {
                    "entry_key": key,
                    "canonical": entry.canonical,
                    "confidence": 0.9,
                    "source": "keyword_match",
                    "matched_variant": keyword,
                }

    # Layer 3 — fuzzy match against variants
    best: dict | None = None
    for key, entry in library.entries.items():
        if not isinstance(entry, PatternEntry):
            continue
        for variant in entry.variants:
            v_norm = normalize_text(variant, normalization)
            score = fuzz.ratio(normalized, v_norm)
            if best is None or score > best["score"]:
                best = {
                    "entry_key": key,
                    "canonical": entry.canonical,
                    "score": score,
                    "variant": variant,
                    "threshold": entry.fuzzy_threshold,
                }

    if best and best["score"] >= best["threshold"]:
        return {
            "entry_key": best["entry_key"],
            "canonical": best["canonical"],
            "confidence": best["score"] / 100.0,
            "source": "fuzzy_match",
            "matched_variant": best["variant"],
        }

    return None


def match_regex(
    text: str,
    library: PatternLibrary,
    normalization: dict,
) -> dict | None:
    """Run regex-based patterns on text. Returns match + captures, or None.

    Used for patterns that extract structured data (periods, numeric notation).
    Returns the FIRST pattern that matches across all entries.
    """
    if not text:
        return None

    normalized = normalize_text(text, normalization)

    for key, entry in library.entries.items():
        if not isinstance(entry, RegexPatternEntry):
            continue
        for rp in entry.regex_patterns:
            flags = re.IGNORECASE if normalization.get("case_insensitive", False) else 0
            m = re.search(rp.pattern, normalized, flags=flags)
            if not m:
                continue
            captures: dict[str, str] = {}
            for group_idx_str, field_name in rp.captures.items():
                try:
                    captures[field_name] = m.group(int(group_idx_str))
                except (IndexError, ValueError):
                    continue
            return {
                "entry_key": key,
                "canonical": entry.canonical,
                "pattern": rp.pattern,
                "captures": captures,
                "matched_text": m.group(0),
            }

    return None
