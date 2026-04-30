"""PDF extraction path for financials-extract.

Parses an SEC filing PDF (10-K / 10-Q / press release) into a RawFiling. Uses
pdfplumber for table extraction, pymupdf for page text, and the pattern
libraries under references/ for unit/period/section/statement-heading
recognition via the 4-layer adaptation ladder (normalize → keyword → fuzzy →
append).
"""
from __future__ import annotations

import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from financials_schema import (
    Citation,
    FilingType,
    NumericNotation,
    Period,
    RawFiling,
    RawLineItem,
    Section,
    Statement,
    StatementType,
    Unit,
    build_generic_index,
    load_generic_library,
    match_raw_item,
)

# Sibling imports (skill's scripts package)
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.pattern import load_pattern_library, match_phrase, match_regex
    from scripts.pdf_reader import extract_tables, get_all_page_texts
else:
    from .pattern import load_pattern_library, match_phrase, match_regex
    from .pdf_reader import extract_tables, get_all_page_texts


# ============================================================================
# Pattern-library locations
# ============================================================================

REFERENCES = Path(__file__).parent.parent / "references"

STATEMENT_PATTERNS_PATH = REFERENCES / "statement_heading_patterns.json"
UNIT_PATTERNS_PATH = REFERENCES / "unit_phrases.json"
PERIOD_PATTERNS_PATH = REFERENCES / "period_phrase_patterns.json"
NUMERIC_PATTERNS_PATH = REFERENCES / "numeric_notation_patterns.json"
SECTION_PATTERNS_PATH = REFERENCES / "section_heading_patterns.json"


# ============================================================================
# Canonical → enum mapping
# ============================================================================

STATEMENT_TYPE_BY_CANONICAL = {
    "BALANCE_SHEET": StatementType.BALANCE_SHEET,
    "CASH_FLOW": StatementType.CASH_FLOW,
    "INCOME_STATEMENT": StatementType.INCOME_STATEMENT,
}

UNIT_BY_CANONICAL = {
    "THOUSANDS": Unit.THOUSANDS,
    "MILLIONS": Unit.MILLIONS,
    "BILLIONS": Unit.BILLIONS,
    "ACTUAL": Unit.ACTUAL,
}

SECTION_BY_CANONICAL = {m.name: m for m in Section}

NOTATION_BY_CANONICAL = {m.name: m for m in NumericNotation}

MONTH_BY_NAME = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

QUARTER_WORD_MAP = {"first": 1, "second": 2, "third": 3, "fourth": 4}


# ============================================================================
# Numeric parsing + notation detection
# ============================================================================

def parse_value(text: str) -> Decimal | None:
    """Parse a cell's text into Decimal. Returns None if unparseable or empty."""
    if text is None:
        return None
    clean = text.strip().replace("$", "").replace(",", "").replace(" ", "")
    if not clean:
        return None
    if clean in ("-", "—", "–"):
        return Decimal("0")
    negative = False
    if clean.startswith("(") and clean.endswith(")"):
        negative = True
        clean = clean[1:-1]
    if clean.startswith("-"):
        negative = True
        clean = clean[1:]
    clean = re.sub(r"[\*]+$", "", clean)
    clean = re.sub(r"\([a-zA-Z0-9]{1,2}\)$", "", clean)
    clean = clean.strip()
    try:
        value = Decimal(clean)
    except (InvalidOperation, ValueError):
        return None
    return -value if negative else value


def detect_notation(text: str) -> NumericNotation:
    """Return NumericNotation flag bitmap for a raw cell text."""
    flags = NumericNotation.NONE
    if not text:
        return flags
    t = text.strip()
    if "$" in t:
        flags |= NumericNotation.DOLLAR_SIGN
    if t.startswith("(") and t.endswith(")"):
        flags |= NumericNotation.PARENS_NEGATIVE
    if t.startswith("-"):
        flags |= NumericNotation.NEGATIVE_MINUS
    if t in ("-", "—", "–"):
        flags |= NumericNotation.ZERO_DASH
    if t.endswith("*"):
        flags |= NumericNotation.TRAILING_ASTERISK
    if re.search(r"\([a-zA-Z0-9]{1,2}\)\s*$", t):
        flags |= NumericNotation.HAS_FOOTNOTE
    if re.match(r"^\$?[\d,\.]+\s*[KMB]$", t):
        flags |= NumericNotation.SUPERSCRIPT_SUFFIX
    return flags


# ============================================================================
# Period construction from regex captures
# ============================================================================

def build_period_from_captures(canonical: str, captures: dict[str, str], raw_text: str) -> Period:
    """Build a Period object from regex capture groups."""
    raw_fy = captures.get("fiscal_year", "")
    fiscal_year = int(raw_fy) if raw_fy else 0
    if 0 < fiscal_year < 100:
        fiscal_year += 2000

    fiscal_quarter: int | None = None
    if "fiscal_quarter" in captures:
        try:
            fiscal_quarter = int(captures["fiscal_quarter"])
        except ValueError:
            fiscal_quarter = None
    elif "fiscal_quarter_word" in captures:
        fiscal_quarter = QUARTER_WORD_MAP.get(captures["fiscal_quarter_word"].lower())

    if "month_name" in captures and "day" in captures:
        month = MONTH_BY_NAME.get(captures["month_name"].lower(), 12)
        try:
            day = int(captures["day"])
        except ValueError:
            day = 31
        period_end_date = date(fiscal_year, month, day)
    else:
        period_end_date = date(fiscal_year, 12, 31)

    period_length_weeks: int | None = None
    if "period_length_weeks" in captures:
        try:
            period_length_weeks = int(captures["period_length_weeks"])
        except ValueError:
            period_length_weeks = None

    return Period(
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        period_end_date=period_end_date,
        raw_period_label=raw_text,
        period_length_weeks=period_length_weeks,
        is_comparative=False,
    )


# ============================================================================
# Statement + line-item extraction
# ============================================================================

def find_statement_pages(
    page_texts: list[str],
    stmt_lib,
    stmt_norm: dict,
    unit_lib,
    unit_norm: dict,
) -> list[dict]:
    """Scan pages for statement headings.

    Title-line filters (must-start-with-Consolidated/Statement + no prose
    markers) are strong enough on their own to weed out MD&A and TOC noise.
    """
    found: list[dict] = []
    seen_types: set[str] = set()

    prose_indicators = re.compile(
        r"\b(our|their|the company|that|which|because|however|therefore)\b",
        re.IGNORECASE,
    )

    for page_idx, text in enumerate(page_texts, start=1):
        lines = text.split("\n")
        for line_idx, raw_line in enumerate(lines[:30]):
            line = raw_line.strip()
            if not line:
                continue
            if not (10 <= len(line) <= 80):
                continue
            if line.endswith(".") or line.endswith(","):
                continue
            if not line[0].isupper():
                continue
            if prose_indicators.search(line):
                continue
            first_word = line.split()[0].lower() if line.split() else ""
            if first_word not in ("consolidated", "statement", "statements", "condensed"):
                continue
            if re.search(r"\bfor the (years?|period)\b|\byears?\s+ended\b|\bas\s+of\b", line, re.IGNORECASE):
                continue

            result = match_phrase(line, stmt_lib, stmt_norm)
            if not result:
                continue
            canonical = result["canonical"]
            if canonical in seen_types:
                break

            found.append({
                "page": page_idx,
                "heading_line": line,
                "line_index": line_idx,
                "canonical": canonical,
                "confidence": result["confidence"],
                "source": result["source"],
            })
            seen_types.add(canonical)
            break  # next page
    return found


def detect_unit_on_page(
    page_text: str,
    unit_lib,
    unit_norm: dict,
) -> dict | None:
    """Look for the unit phrase within the top 30 lines of a page."""
    for line in page_text.split("\n")[:30]:
        line = line.strip()
        if not line:
            continue
        low = line.lower()
        if not any(k in low for k in ("thousand", "million", "billion", "actual", "whole dollar")):
            continue
        result = match_phrase(line, unit_lib, unit_norm)
        if result:
            return {
                "line": line,
                "canonical": result["canonical"],
                "confidence": result["confidence"],
                "source": result["source"],
            }
    return None


def split_label_and_values(row: list[str | None]) -> tuple[str, list[str]]:
    cells = [("" if c is None else str(c)).strip() for c in row]
    if not cells:
        return "", []
    return cells[0], cells[1:]


def extract_periods_from_text(
    header_lines: list[str],
    period_lib,
    period_norm: dict,
) -> list[tuple[Period, str]]:
    """Scan header lines for period column headers.

    Three passes for three filing layouts:
      (a) single-line: 'December 31, 2024' or 'Year ended December 31, 2024'
      (b) split anchor + bare years: 'For the years ended December 31,' /
          '2023' / '2022' / '2021'
      (c) interleaved bare-date + bare-year (CELH 2022 10-K style):
          'December 31,' / '2021' / 'December 31,' / '2020'
    """
    periods: list[tuple[Period, str]] = []

    # Pass 1: single-line date patterns
    for line in header_lines:
        candidates = re.findall(r"[A-Za-z]+\s+\d{1,2},?\s+\d{4}", line)
        if not candidates:
            candidates = [line.strip()] if line.strip() else []
        for cand in candidates:
            m = match_regex(cand, period_lib, period_norm)
            if not m:
                continue
            period = build_period_from_captures(
                canonical=m["canonical"],
                captures=m["captures"],
                raw_text=cand,
            )
            if any(p.fiscal_year == period.fiscal_year and p.period_end_date == period.period_end_date
                   for p, _ in periods):
                continue
            periods.append((period, cand))

    if periods:
        return periods

    # Pass 2: "For the years ended <Month> <Day>," anchor + bare year lines
    anchor_re = re.compile(
        r"for\s+the\s+years?\s+ended\s+(\w+)\s+(\d{1,2})",
        re.IGNORECASE,
    )
    anchor_month: str | None = None
    anchor_day: int | None = None
    anchor_idx: int = -1
    for idx, line in enumerate(header_lines):
        m = anchor_re.search(line)
        if m:
            anchor_month = m.group(1)
            try:
                anchor_day = int(m.group(2))
            except ValueError:
                anchor_day = 31
            anchor_idx = idx
            break

    if anchor_month and anchor_day is not None:
        for line in header_lines[anchor_idx + 1 : anchor_idx + 12]:
            year_match = re.match(r"^\s*(\d{4})\s*$", line)
            if not year_match:
                continue
            year = int(year_match.group(1))
            if not (1990 <= year <= 2100):
                continue
            month_num = MONTH_BY_NAME.get(anchor_month.lower(), 12)
            period_end = date(year, month_num, anchor_day)
            if any(p.fiscal_year == year and p.period_end_date == period_end for p, _ in periods):
                continue
            period = Period(
                fiscal_year=year,
                fiscal_quarter=None,
                period_end_date=period_end,
                raw_period_label=f"For the year ended {anchor_month} {anchor_day}, {year}",
                period_length_weeks=None,
                is_comparative=False,
            )
            periods.append((period, str(year)))

    if periods:
        return periods

    # Pass 3: '<Month> <day>,' anchor immediately followed by a bare year
    bare_date_re = re.compile(r"^\s*([A-Za-z]+)\s+(\d{1,2})\s*,?\s*$")
    bare_year_re = re.compile(r"^\s*(\d{4})\s*$")
    i = 0
    while i < len(header_lines) - 1:
        anchor = bare_date_re.match(header_lines[i])
        if anchor:
            month_name = anchor.group(1)
            try:
                day = int(anchor.group(2))
            except ValueError:
                i += 1
                continue
            for j in range(i + 1, min(i + 7, len(header_lines))):
                peek = header_lines[j]
                if not peek.strip() or peek.strip() == " ":
                    continue
                y_m = bare_year_re.match(peek)
                if y_m:
                    year = int(y_m.group(1))
                    if not (1990 <= year <= 2100):
                        break
                    month_num = MONTH_BY_NAME.get(month_name.lower(), 12)
                    period_end = date(year, month_num, day)
                    if not any(p.fiscal_year == year and p.period_end_date == period_end for p, _ in periods):
                        periods.append((
                            Period(
                                fiscal_year=year,
                                fiscal_quarter=None,
                                period_end_date=period_end,
                                raw_period_label=f"{month_name} {day}, {year}",
                                period_length_weeks=None,
                                is_comparative=False,
                            ),
                            f"{month_name} {day}, {year}",
                        ))
                    i = j
                    break
                else:
                    break
        i += 1

    return periods


def extract_statement(
    pdf_path: Path,
    page: int,
    page_text: str,
    statement_type: StatementType,
    unit_lib, unit_norm,
    period_lib, period_norm,
    section_lib, section_norm,
    library_index: dict | None = None,
) -> list[Statement]:
    """Extract one or more Statement objects (one per period column) from a page."""
    unit_match = detect_unit_on_page(page_text, unit_lib, unit_norm)
    if not unit_match:
        print(f"  [warn] no unit phrase found on page {page} — defaulting to ACTUAL dollars")
        unit = Unit.ACTUAL
        raw_unit_phrase = "(not detected; inferred ACTUAL)"
        detection_source = "plausibility_inferred"
        detection_confidence = 0.5
    else:
        unit = UNIT_BY_CANONICAL.get(unit_match["canonical"], Unit.UNKNOWN)
        raw_unit_phrase = unit_match["line"]
        detection_source = "explicit_header"
        detection_confidence = unit_match["confidence"]
        print(f"  unit: {unit.value} (from {unit_match['canonical']!r}, "
              f"source={unit_match['source']}, conf={unit_match['confidence']:.2f})")

    header_lines = page_text.split("\n")[:40]
    periods_with_text = extract_periods_from_text(header_lines, period_lib, period_norm)
    if not periods_with_text:
        print(f"  [warn] no period headers found on page {page}")
        return []

    print(f"  periods: {[(p.fiscal_year, p.period_end_date.isoformat()) for p, _ in periods_with_text]}")

    for i, (p, _) in enumerate(periods_with_text):
        if i > 0:
            p.is_comparative = True

    tables = extract_tables(pdf_path, page)
    if not tables:
        print(f"  [warn] no tables extracted from page {page}")
        return []

    main_table: list[list[str | None]] = []
    for t in tables:
        main_table.extend(t)
    print(f"  merged {len(tables)} table(s): {len(main_table)} rows total, "
          f"~{max((len(r) for r in main_table), default=0)} cols")

    derived_share_unit, derived_eps_unit = derive_share_eps_units(raw_unit_phrase, unit)
    current_section = Section.UNCLASSIFIED
    current_subsection: str | None = None
    detected_share_unit = derived_share_unit
    detected_eps_unit = derived_eps_unit
    items_per_period: dict[int, list[RawLineItem]] = {i: [] for i in range(len(periods_with_text))}

    for row_idx, row in enumerate(main_table):
        label, value_cells = split_label_and_values(row)
        if not label and not any(value_cells):
            continue

        # Section / subsection header detection
        if label and not any(parse_value(c) is not None for c in value_cells):
            section_match = match_phrase(label, section_lib, section_norm)
            if section_match:
                current_section = SECTION_BY_CANONICAL.get(section_match["canonical"], Section.UNCLASSIFIED)
                if section_match["canonical"] == "EPS":
                    current_subsection = "eps"
                    sub_unit = detect_subsection_unit(label, unit_lib, unit_norm)
                    if sub_unit:
                        detected_eps_unit = sub_unit
                continue

            label_low = label.lower()
            if "weighted average" in label_low and ("share" in label_low or "common stock" in label_low):
                current_subsection = "shares_outstanding"
                sub_unit = detect_subsection_unit(label, unit_lib, unit_norm)
                if sub_unit:
                    detected_share_unit = sub_unit
                continue

            continue

        numeric_cells = [c for c in value_cells if c and c.strip()]
        if not numeric_cells:
            continue

        parseable = [(c, parse_value(c)) for c in numeric_cells]
        parseable = [(txt, val) for txt, val in parseable if val is not None]
        if not parseable:
            continue

        if len(parseable) < len(periods_with_text):
            continue

        if statement_type == StatementType.INCOME_STATEMENT:
            row_section = classify_is_row(label, current_section)
        else:
            row_section = current_section

        rule_id: str | None = None
        canonical: str | None = None
        row_type: str = "line_item"
        library_sign: str | None = None
        if library_index is not None:
            section_str = row_section.value if hasattr(row_section, "value") else row_section
            entry = match_raw_item(
                raw_filing_label=label,
                concept=None,
                subsection_context=current_subsection,
                section=section_str,
                statement_type=statement_type,
                index=library_index,
            )
            if entry is not None:
                rule_id = entry["rule_id"]
                canonical = entry["model_label"]
                if entry.get("row_type"):
                    row_type = entry["row_type"]
                elif entry.get("memo"):
                    row_type = "memo"
                if entry.get("sign_convention"):
                    library_sign = entry["sign_convention"]
                # Library overrides heuristic-classified section when set.
                if entry.get("filing_section"):
                    row_section = Section(entry["filing_section"])

        for col_idx, (raw_text, val) in enumerate(parseable[: len(periods_with_text)]):
            citation = Citation(
                source_path=pdf_path,
                page=page,
                line_hint=f"{label} | {raw_text}",
            )
            notation = detect_notation(raw_text)
            # Sign convention is now abs-based (positive/negative). The library
            # decides what the sign should be in our model; we no longer care
            # whether pdfplumber pre-signed the value, since _signed_value uses
            # abs() as the input. as_reported stays the default for items
            # without an opinion.
            sign_convention = library_sign if library_sign else "as_reported"
            try:
                item = RawLineItem(
                    raw_filing_label=label,
                    canonical_label=canonical,
                    ledger_rule_id=rule_id,
                    value=val,
                    raw_numeric_text=raw_text,
                    notation_flags=notation,
                    row_type=row_type,
                    section=row_section,
                    subsection_context=current_subsection,
                    sign_convention=sign_convention,
                    citation=citation,
                )
            except Exception as e:
                print(f"    [skip row {row_idx}] {e}")
                continue
            items_per_period[col_idx].append(item)

        # Subtotal-driven BS section flips: many filings omit the explicit
        # "Non-current assets:" header, so we derive the boundary from the
        # "Total current X" subtotal row.
        if statement_type == StatementType.BALANCE_SHEET:
            label_low = label.lower().strip()
            if current_section == Section.CURRENT_ASSETS and "total current assets" in label_low:
                current_section = Section.NON_CURRENT_ASSETS
            elif current_section == Section.CURRENT_LIABILITIES and "total current liabilities" in label_low:
                current_section = Section.NON_CURRENT_LIABILITIES

    statements: list[Statement] = []
    for col_idx, (period, _) in enumerate(periods_with_text):
        items = items_per_period.get(col_idx, [])
        if not items:
            continue
        statement = Statement(
            statement_type=statement_type,
            period=period,
            unit=unit,
            raw_unit_phrase=raw_unit_phrase,
            unit_detection_source=detection_source,
            unit_detection_confidence=detection_confidence,
            share_unit=detected_share_unit,
            eps_unit=detected_eps_unit,
            line_items=items,
        )
        statements.append(statement)

    return statements


def detect_subsection_unit(header_text: str, unit_lib, unit_norm) -> Unit | None:
    """If a subsection header contains a unit phrase like '(in thousands)', return the Unit."""
    low = header_text.lower()
    if not any(k in low for k in ("thousand", "million", "billion", "actual", "whole dollar")):
        return None
    result = match_phrase(header_text, unit_lib, unit_norm)
    if result:
        return UNIT_BY_CANONICAL.get(result["canonical"])
    return None


IS_TOP_LINE_KEYWORDS = (
    "revenue", "net sales",
    "cost of revenue", "cost of goods", "cost of sales",
    "gross profit", "gross margin",
)
IS_OPEX_KEYWORDS = (
    "selling, general", "selling general", "sg&a", "general and administrative",
    "research and development", "r&d",
    "operating expenses", "operating costs",
    "income (loss) from operations", "income from operations",
    "loss from operations", "operating income", "operating loss",
)


def classify_is_row(label: str, current_section: Section) -> Section:
    """Refine an IS row's section based on its label."""
    if current_section == Section.EPS:
        return current_section
    low = label.lower()
    if any(k in low for k in IS_TOP_LINE_KEYWORDS):
        return Section.REVENUE_COST
    if any(k in low for k in IS_OPEX_KEYWORDS):
        return Section.OPERATING_EXPENSES
    return Section.NON_OPERATING


def derive_share_eps_units(unit_phrase: str, statement_unit: Unit) -> tuple[Unit, Unit]:
    """Parse exclusions out of phrases like '(in thousands, except per share amounts)'.

    Convention: items NOT explicitly excluded inherit the statement_unit.
    - 'except per share' (without 'share and') → only EPS excluded
    - 'except share and per share' / 'shares and per share' → both excluded
    - 'except share amounts' (alone) → shares excluded; EPS inherits
    """
    low = unit_phrase.lower()
    excludes_eps = "per share" in low
    excludes_shares = bool(
        re.search(r"\bshare\s+and\s+per\s+share\b", low)
        or re.search(r"\bshares\s+and\s+per\s+share\b", low)
        or (re.search(r"\bshare(?:\s+amounts?)?\b", low) and "per share" not in low)
    )
    eps_unit = Unit.ACTUAL if excludes_eps else statement_unit
    share_unit = Unit.ACTUAL if excludes_shares else statement_unit
    return share_unit, eps_unit


# ============================================================================
# Top-level entry — parses one PDF into a RawFiling
# ============================================================================

def extract_filing(
    pdf_path: Path,
    ticker: str,
    filing_type: FilingType,
    filing_date_: date,
    only_types: set[StatementType] | None = None,
    library_path: Path | None = None,
) -> RawFiling:
    """Parse a filing PDF into a RawFiling.

    `only_types` restricts which statements to extract. When `library_path` is
    supplied, each RawLineItem's `canonical_label` and `ledger_rule_id` are
    populated at extract time via the generic-library lookup; un-matched items
    surface as novels downstream (in reconcile).
    """
    stmt_lib, stmt_norm = load_pattern_library(STATEMENT_PATTERNS_PATH)
    unit_lib, unit_norm = load_pattern_library(UNIT_PATTERNS_PATH)
    period_lib, period_norm = load_pattern_library(PERIOD_PATTERNS_PATH)
    section_lib, section_norm = load_pattern_library(SECTION_PATTERNS_PATH)

    library_index: dict | None = None
    if library_path is not None:
        library_index = build_generic_index(load_generic_library(library_path))

    print(f"[extract] Reading {pdf_path.name}")
    page_texts = get_all_page_texts(pdf_path)
    page_count = len(page_texts)
    print(f"[extract] {page_count} pages")

    statement_pages = find_statement_pages(page_texts, stmt_lib, stmt_norm, unit_lib, unit_norm)
    print(f"[extract] Found {len(statement_pages)} statement headings:")
    for loc in statement_pages:
        print(f"  p.{loc['page']}: {loc['canonical']}  "
              f"({loc['source']} conf={loc['confidence']:.2f})  '{loc['heading_line']}'")

    all_statements: list[Statement] = []
    for loc in statement_pages:
        stmt_type = STATEMENT_TYPE_BY_CANONICAL[loc["canonical"]]
        if only_types and stmt_type not in only_types:
            continue
        print(f"\n[extract] Processing {stmt_type.value} on page {loc['page']}")
        statements = extract_statement(
            pdf_path=pdf_path,
            page=loc["page"],
            page_text=page_texts[loc["page"] - 1],
            statement_type=stmt_type,
            unit_lib=unit_lib, unit_norm=unit_norm,
            period_lib=period_lib, period_norm=period_norm,
            section_lib=section_lib, section_norm=section_norm,
            library_index=library_index,
        )
        print(f"  produced {len(statements)} Statement(s); "
              f"total line items = {sum(len(s.line_items) for s in statements)}")
        all_statements.extend(statements)

    return RawFiling(
        ticker=ticker,
        filing_type=filing_type,
        filing_date=filing_date_,
        source_path=pdf_path,
        statements=all_statements,
        extraction_metadata={
            "extractor": "financials-extract/pdf",
            "extracted_at": datetime.now().isoformat(timespec="seconds"),
            "page_count": page_count,
            "statement_pages": [
                {"page": loc["page"], "canonical": loc["canonical"],
                 "source": loc["source"], "confidence": loc["confidence"]}
                for loc in statement_pages
            ],
        },
    )
