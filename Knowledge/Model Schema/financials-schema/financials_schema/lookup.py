"""Shared generic-library lookup used by extract skills and reconcile.

Extract-time flow:
  1. Load generic library (`generic_line_item_mappings.json`)
  2. Build a lookup index keyed by (normalized_alias, sheet_group)
  3. For each RawLineItem, call `match_raw_item(item, concept, stmt_type, index)`
     → returns (rule_id, canonical_label) or (None, None)
  4. Extract sets canonical_label + ledger_rule_id on the RawLineItem.

Reconcile-time flow (ticker ledger only):
  1. Load the per-ticker decisions_ledger.json (mappings + new_rows)
  2. Build a ticker-only index (with ANNL/QTR variant axis preserved)
  3. For each item, apply ticker overrides on top of what extract produced.
  4. If canonical_label is still None → novel.

Vocabulary:
  - "alias"     — a raw filer string or us-gaap concept name from the library
  - "canonical" — the library entry's model_label ("Cash & Cash Equivalents")
  - "group"     — BS / IS / CF (coarse statement type)
  - "variant"   — ANNL / QTR (fine-grained; only matters for ticker entries)
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from rapidfuzz import fuzz, process

from financials_schema.enums import StatementType

# ============================================================================
# Label normalization
# ============================================================================

CLUTTER_RE = re.compile(
    r"(?:[,;]\s*)?\$?[\d.,]*\s*"
    r"(?:par\s+value|cumulative\s+dividends|liquidation\s+preference|aggregate\s+liquidation"
    r"|[\d,]+\s+shares\s+\w+)"
    r".*$",
    re.IGNORECASE | re.DOTALL,
)
FOOTNOTE_RE = re.compile(r"\[\d+\]|\(\d+\)")
# Split CamelCase (iXBRL us-gaap concept names like "AccountsReceivableNetCurrent"
# → "Accounts Receivable Net Current"). Insert space at lower→upper transitions
# and at Acronym→Word transitions (e.g. "XBRLData" → "XBRL Data").
CAMEL_SPLIT_LOWER_UPPER = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
CAMEL_SPLIT_ACRONYM = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")


def normalize_label(label: str) -> str:
    """Lowercase, drop footnote markers + filing clutter, normalize punctuation.
    Splits CamelCase so us-gaap concept names tokenize identically to English
    phrases (`AccountsReceivableNetCurrent` ↔ `accounts receivable net current`).
    """
    label = FOOTNOTE_RE.sub("", label)
    label = CLUTTER_RE.sub("", label)
    label = CAMEL_SPLIT_ACRONYM.sub(" ", label)
    label = CAMEL_SPLIT_LOWER_UPPER.sub(" ", label)
    label = label.lower()
    label = re.sub(r"\b(the|our)\b", " ", label)
    label = re.sub(r"[^\w\s\-]", " ", label)
    label = " ".join(label.split())
    return label.strip()


# ============================================================================
# Subtotal detection
# ============================================================================

SUBTOTAL_RE = re.compile(r"^(total|subtotal)\b", re.IGNORECASE)

# iXBRL us-gaap concept names that represent standard statement subtotals.
# These don't start with "Total" so SUBTOTAL_RE misses them.
IXBRL_SUBTOTAL_CONCEPTS = frozenset({
    "Assets",
    "AssetsCurrent",
    "AssetsNoncurrent",
    "Liabilities",
    "LiabilitiesCurrent",
    "LiabilitiesNoncurrent",
    "LiabilitiesAndStockholdersEquity",
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
})


def is_subtotal_label(raw_filing_label: str, concept: str | None = None) -> bool:
    """Rows starting with 'Total' or 'Subtotal' are subtotals. Also catches
    iXBRL us-gaap subtotal concept names (via the optional `concept` arg from
    the iXBRL extractor's citation; the label itself may be 'TOTAL ASSETS'
    which already matches the regex, so `concept` is belt-and-suspenders)."""
    if SUBTOTAL_RE.match(raw_filing_label.strip()):
        return True
    if concept and concept in IXBRL_SUBTOTAL_CONCEPTS:
        return True
    return False


# ============================================================================
# Library loading + index building
# ============================================================================

STMT_TO_GROUP: dict[StatementType, str] = {
    StatementType.BALANCE_SHEET:    "BS",
    StatementType.CASH_FLOW:        "CF",
    StatementType.INCOME_STATEMENT: "IS",
}


def _strip_underscore_keys(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


def load_generic_library(library_path: Path) -> dict:
    """Load the cross-ticker generic line-item mappings file. Returns an
    empty container if the file is missing (opt-in)."""
    if not library_path.exists():
        return {"mappings": []}
    data = json.loads(library_path.read_text(encoding="utf-8"))
    return _strip_underscore_keys(data)


def _sheet_group(model_sheet: str) -> str:
    ml = model_sheet.lower()
    if "balance sheet" in ml or ml == "qtr bs":
        return "BS"
    if "cash flow" in ml or ml == "qtr cf":
        return "CF"
    if "p&l" in ml:
        return "IS"
    return "OTHER"


def build_generic_index(
    library: dict,
) -> dict[tuple[str, str], list[dict]]:
    """Build {(normalized_alias, sheet_group): [entry, ...]} from the generic
    library. Drops the ANNL/QTR variant axis — generic entries are canonical
    cross-ticker concepts, applicable to both annual and quarterly statements
    (the variant gets resolved at reconcile-time via model_sheet routing).
    """
    index: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for entry in library.get("mappings", []):
        sheet_grp = _sheet_group(entry["model_sheet"])
        canonical = {
            "rule_id": entry["rule_id"],
            "model_sheet": entry["model_sheet"],
            "model_label": entry["model_label"],
            "filing_subsection": entry.get("filing_subsection"),
            "filing_section": entry.get("filing_section"),
            "sign_convention": entry.get("sign_convention"),
            "memo": entry.get("memo", False),
            "row_type": entry.get("row_type"),
            "_source": "generic",
        }
        for alias in entry.get("aliases", []):
            index[(normalize_label(alias), sheet_grp)].append(canonical)
    return index


# ============================================================================
# Candidate selection (subsection + section disambiguation)
# ============================================================================

def select_entry(
    candidates: list[dict],
    item_subsection: str | None,
    item_section: str | None,
) -> dict | None:
    """Pick the best library entry for an item given its subsection + section
    context.

    Subsection filter is always applied (EPS vs shares_outstanding is a hard
    semantic split). Section filter is applied only when necessary to
    disambiguate. Single-candidate fallback unblocks iXBRL items whose
    subsection_context is None.
    """
    pool = [c for c in candidates
            if c.get("filing_subsection") is None
            or c.get("filing_subsection") == item_subsection]
    if not pool and item_subsection is None and len(candidates) == 1:
        pool = list(candidates)
    if not pool:
        return None
    if len(pool) == 1:
        return pool[0]
    best, best_score = None, -1
    for c in pool:
        c_sec = c.get("filing_section")
        if c_sec is not None and c_sec != item_section:
            continue
        score = 0
        c_sub = c.get("filing_subsection")
        if c_sub is not None and c_sub == item_subsection:
            score += 2
        if c_sec is not None and c_sec == item_section:
            score += 1
        if score > best_score:
            best, best_score = c, score
    return best


# ============================================================================
# Match API (extract-time entry point)
# ============================================================================

def match_raw_item(
    raw_filing_label: str,
    concept: str | None,
    subsection_context: str | None,
    section: str | None,
    statement_type: StatementType,
    index: dict[tuple[str, str], list[dict]],
    fuzzy_threshold: int = 85,
) -> dict | None:
    """Look up a raw line item in the generic library.

    Returns the matching library entry dict (with keys `rule_id`,
    `model_label`, `model_sheet`, `filing_section`, `filing_subsection`,
    `sign_convention`, `memo`, `row_type`, ...) on match, or None on miss.

    Match order (display label is semantically authoritative — the filer
    chose it for human readers. us-gaap concept names can be mis-tagged or
    overloaded, so they're the LAST resort):
      1. Exact-normalized match on raw_filing_label (filer display)
      2. Fuzzy match on raw_filing_label (rapidfuzz ≥ threshold)
      3. Exact-normalized match on concept (iXBRL us-gaap local name) —
         fallback for filers whose display wording isn't in the library yet

    Example of why display > concept: PG tags "EARNINGS BEFORE INCOME TAXES"
    with us-gaap concept `IncomeLossIncludingPortionAttributableToNoncontrollingInterest`,
    which other filers use for consolidated net income. The display label
    disambiguates — we follow it.
    """
    group = STMT_TO_GROUP[statement_type]
    normalized = normalize_label(raw_filing_label)

    # (1) raw label exact
    candidates = index.get((normalized, group), [])
    entry = select_entry(candidates, subsection_context, section)
    if entry is not None:
        return entry

    # (2) fuzzy on raw label
    group_keys = [k for (k, sg) in index if sg == group]
    matches = process.extract(normalized, group_keys, scorer=fuzz.ratio, limit=3)
    if matches and matches[0][1] >= fuzzy_threshold:
        best_key = matches[0][0]
        entry = select_entry(index.get((best_key, group), []),
                             subsection_context, section)
        if entry is not None:
            return entry

    # (3) concept fallback (iXBRL only — raw source of truth)
    if concept:
        candidates = index.get((normalize_label(concept), group), [])
        entry = select_entry(candidates, subsection_context, section)
        if entry is not None:
            return entry

    return None


def nearest_matches(
    raw_filing_label: str,
    statement_type: StatementType,
    index: dict[tuple[str, str], list[dict]],
    limit: int = 3,
    min_score: int = 50,
) -> list[tuple[str, float]]:
    """Return top-N nearest library aliases for a raw label, as (alias, score)
    tuples with score in [0,1]. Used by novel-reporting to hint nearest
    candidates to the user."""
    group = STMT_TO_GROUP[statement_type]
    normalized = normalize_label(raw_filing_label)
    group_keys = [k for (k, sg) in index if sg == group]
    matches = process.extract(normalized, group_keys, scorer=fuzz.ratio, limit=limit)
    return [(m, s / 100.0) for m, s, _ in matches if s >= min_score]
