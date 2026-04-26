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
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field
from rapidfuzz import fuzz, process

from financials_schema.enums import Section, StatementType
from financials_schema.line_item import RowType, SignConvention

# ============================================================================
# Label normalization
# ============================================================================

CLUTTER_RE = re.compile(
    r"(?:[,;]\s*)?\$?[\d.,]*\s*"
    r"(?:par\s+value|cumulative\s+dividends|liquidation\s+preference|aggregate\s+liquidation"
    # Require at least one DIGIT in the leading number — `[\d,]+` alone matches
    # a bare comma (since `,` is in the character class), which silently clobbers
    # labels like "Mezzanine equity, shares outstanding (in shares)" by matching
    # `, shares outstanding`. Use `\d[\d,]*` to require a digit anchor.
    r"|\d[\d,]*\s+shares\s+\w+)"
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


class LibraryEntry(BaseModel):
    """Pydantic-validated shape for a single generic-library entry.

    Catches typos in field names (extra keys forbidden), invalid section /
    sign_convention values, and missing required fields at LOAD time —
    pointing to the bad entry instead of failing later when an item happens
    to match it."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    model_sheet: str
    model_label: str
    aliases: list[str] = Field(default_factory=list)
    filing_section: Section | None = None
    filing_subsection: str | None = None
    sign_convention: SignConvention | None = None
    memo: bool = False
    row_type: RowType | None = None
    # Free-form documentation field — surfaces in novel triage / human review.
    # Not consumed by extract / reconcile / validate.
    note: str | None = None


def load_generic_library(library_path: Path) -> dict:
    """Load the cross-ticker generic line-item mappings file and validate
    every entry through `LibraryEntry`. Returns the same dict shape downstream
    code already consumes; validation is purely a load-time guard.

    Empty container returned if the file is missing (opt-in)."""
    if not library_path.exists():
        return {"mappings": []}
    data = json.loads(library_path.read_text(encoding="utf-8"))
    data = _strip_underscore_keys(data)
    # Validate every mapping. Loud failure on first bad entry — message names
    # the rule_id (or position) so the user knows where to look.
    for i, raw in enumerate(data.get("mappings", [])):
        try:
            LibraryEntry.model_validate(raw)
        except Exception as e:
            rid = raw.get("rule_id", f"<index {i}>")
            raise ValueError(f"Invalid library entry {rid} in {library_path.name}: {e}") from e
    return data


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
        # Collect normalized aliases unique to THIS entry. Multiple library
        # aliases can normalize to the same string (e.g. 'net income (loss)'
        # and 'net income loss' both → 'net income loss'). Without dedup the
        # same entry registers twice under one key, which forces select_entry
        # into its multi-candidate disambiguation branch — where the section
        # filter then rejects items whose iXBRL section came through as
        # 'unclassified' (a structural mismatch with the entry's filing_section).
        seen_norm: set[str] = set()
        for alias in entry.get("aliases", []):
            n = normalize_label(alias)
            if n in seen_norm:
                continue
            seen_norm.add(n)
            index[(n, sheet_grp)].append(canonical)
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
# Sign-from-keyword (IS only)
# ============================================================================
#
# IS canonicals encode their default sign in the parenthetical pattern:
#   "Income Tax (Benefit) Expense" → Expense outside = negative default;
#                                    Benefit inside = positive alternate
#   "Foreign Currency Gain (Loss)" → Gain outside = positive default;
#                                    Loss inside = negative alternate
#
# When the matched alias contains one of these keywords we can derive the
# sign without needing per-entry sign_convention. CF lines are EXCLUDED —
# on CF, "Depreciation expense" appears positive (non-cash add-back), so
# the keyword logic would mis-flip.

_NEGATIVE_KEYWORDS = ("expense", "loss", "cost of")
_POSITIVE_KEYWORDS = ("benefit", "gain", "income", "recovery")


def _derive_sign_from_label(label: str) -> str | None:
    """Detect 'positive' / 'negative' from keywords in a normalized IS label.
    Returns None if the label is ambiguous (contains both, or neither)."""
    L = label.lower()
    has_neg = any(kw in L for kw in _NEGATIVE_KEYWORDS)
    has_pos = any(kw in L for kw in _POSITIVE_KEYWORDS)
    if has_neg and not has_pos:
        return "negative"
    if has_pos and not has_neg:
        return "positive"
    return None


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

    Match order:
      1. Exact-normalized match on raw_filing_label
      2. Fuzzy match on raw_filing_label (rapidfuzz ≥ threshold; threshold
         drops to 70 when `concept` is in scope, since iXBRL CamelCase-split
         labels are inherently noisier vs library prose aliases)
      3. Exact-normalized match on concept (iXBRL us-gaap local name) —
         fallback for filers whose display wording isn't in the library yet

    On a hit, if `statement_type` is INCOME_STATEMENT and the entry has no
    explicit `sign_convention`, the sign is derived from keywords in the
    raw_filing_label ("expense"/"loss" → negative; "benefit"/"gain"/"income"
    → positive). Per-entry sign_convention always wins if set.
    """
    # iXBRL labels are CamelCase-split concept names — high baseline noise
    # vs library aliases written for human prose ("Depreciation Depletion And
    # Amortization" vs "depreciation and amortization" → ratio ~74).
    if concept is not None and fuzzy_threshold > 70:
        fuzzy_threshold = 70
    group = STMT_TO_GROUP[statement_type]
    normalized = normalize_label(raw_filing_label)

    entry: dict | None = None

    # (1) raw label exact
    candidates = index.get((normalized, group), [])
    entry = select_entry(candidates, subsection_context, section)

    # (2) fuzzy on raw label
    if entry is None:
        group_keys = [k for (k, sg) in index if sg == group]
        matches = process.extract(normalized, group_keys, scorer=fuzz.ratio, limit=3)
        if matches and matches[0][1] >= fuzzy_threshold:
            best_key = matches[0][0]
            entry = select_entry(index.get((best_key, group), []),
                                 subsection_context, section)

    # (3) concept fallback (iXBRL only — raw source of truth)
    if entry is None and concept:
        candidates = index.get((normalize_label(concept), group), [])
        entry = select_entry(candidates, subsection_context, section)

    if entry is None:
        return None

    # IS-only keyword sign-detection. Per-entry convention always wins.
    if (statement_type == StatementType.INCOME_STATEMENT
            and not entry.get("sign_convention")):
        derived = _derive_sign_from_label(raw_filing_label)
        if derived:
            entry = {**entry, "sign_convention": derived}

    return entry


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
