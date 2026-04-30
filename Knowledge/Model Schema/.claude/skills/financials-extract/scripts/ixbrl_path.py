"""iXBRL extraction path — HTM-only walker.

Walks the primary `.htm` filing as rendered HTML. Each `<table>` element is
checked against a primary-statement title pattern; tables that pair with a
"Consolidated Statements of <X>" / "Consolidated Balance Sheets" heading are
classified into IS / BS / CF (SE skipped; CI deferred to 4th-statement build,
filtered out from IS even when the filer combines them in one table).

For each primary table we walk rows in document order. The first non-empty
`<td>` gives the row label (the same text the human reader sees). Each
subsequent cell containing an `<ix:nonFraction>` emits one fact: concept and
context come from the `ix:nonFraction` attributes; value comes from the cell's
text content; sign comes from the surrounding HTML's parens-around-value
(authoritative — `_is_parens_negative()`). The cell IS the value — no
synthesis, no inference, no R-file dependency. Rows with a section-header
label match against `_HEADER_PATTERNS` to set the active section; subtotal
rows advance section per `_HTM_SUBTOTAL_TRANSITIONS`.

Per-share concepts and share-count concepts are exempted from statement-unit
scaling (PG's $1.94 EPS on a "in millions" IS stays $1.94, not $1.94e-6).
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from lxml import etree

from financials_schema import (
    Citation,
    FilingType,
    Period,
    RawFiling,
    RawLineItem,
    Section,
    Statement,
    StatementType,
    Unit,
    build_concept_index,
    build_generic_index,
    load_generic_library,
    match_raw_item,
)
from financials_schema.lookup import IXBRL_SUBTOTAL_CONCEPTS


# --- Constants -----------------------------------------------------------------

NS = {
    "ix":    "http://www.xbrl.org/2013/inlineXBRL",
    "xbrli": "http://www.xbrl.org/2003/instance",
    "xbrldi": "http://xbrl.org/2006/xbrldi",
}

FILING_TYPE_MAP = {
    "10-K": FilingType.TEN_K,
    "10-Q": FilingType.TEN_Q,
    "8-K": FilingType.EIGHT_K,
}

# CI is its own statement (peer of IS) per OCI memory rule. Skipped here pending
# the 4th-statement build; we filter OCI rows out of combined IS+CI tables at
# walk time so they don't leak into the IS.
STATEMENT_CODE_MAP = {
    "IS": StatementType.INCOME_STATEMENT,
    "BS": StatementType.BALANCE_SHEET,
    "CF": StatementType.CASH_FLOW,
}

STATEMENT_TYPE_TO_CODE = {v: k for k, v in STATEMENT_CODE_MAP.items()}

SCALE_TO_UNIT = {
    0: Unit.ACTUAL,
    3: Unit.THOUSANDS,
    6: Unit.MILLIONS,
    9: Unit.BILLIONS,
}

# Heading text that anchors a primary statement. Anchored at start of the
# element's text — real headings are short standalone strings, not long
# footnote sentences that happen to mention "Consolidated Statements of Cash
# Flows" mid-paragraph. Combined with a hard length cap on title text in
# `find_primary_tables` to filter out paragraph-long matches.
_PRIMARY_TITLE_RE = re.compile(
    r"^(consolidated|condensed\s+consolidated)\s+(statements?|balance\s+sheets?)",
    re.I,
)

# Notes section header — text after the last primary statement. When matched,
# resets the active primary title so subsequent footnote tables don't get
# attributed to the previous statement code.
_NOTES_SECTION_RE = re.compile(
    r"^\s*notes?\s+to\s+(the\s+)?(consolidated\s+|condensed\s+consolidated\s+)?financial\s+statements",
    re.I,
)


def classify_title(title: str) -> str:
    """Map a primary-statement title to a code. Returns one of IS/BS/CF/SE/CI/?

    Combined "Statements of Operations and Comprehensive Income" tables route
    to IS — the trailing "Comprehensive Income" portion is filtered at row-walk
    time so OCI doesn't leak into the IS. Pure CI tables (just "Statements of
    Comprehensive Income") return CI and are skipped entirely (deferred 4th-
    statement build).
    """
    t = title.lower()
    if "balance sheet" in t or "financial position" in t:
        return "BS"
    if "cash flow" in t:
        return "CF"
    if "stockholders" in t or ("shareholders" in t and "equity" in t):
        return "SE"
    has_is = bool(re.search(r"\b(operations|earnings|income)\b", t))
    has_ci = "comprehensive income" in t
    if has_is:
        return "IS"
    if has_ci:
        return "CI"
    return "?"


# --- iXBRL parse helpers (contexts + units stay; visual-sign authority stays) -

@dataclass
class IxPeriod:
    kind: str            # "instant" | "duration"
    start: date | None
    end: date            # instant date or duration end


@dataclass
class IxFact:
    concept: str         # "us-gaap:Revenues"
    local_name: str      # "Revenues"
    namespace: str       # "us-gaap" / "dei" / ticker-prefix
    ctx_period: IxPeriod
    ctx_segments: list[str] = field(default_factory=list)
    raw_value: str = ""
    value_scaled: Decimal = Decimal(0)  # value already scaled to actual $
    scale: int = 0
    unit: str = ""
    decimals: str | None = None

    @property
    def has_segments(self) -> bool:
        return bool(self.ctx_segments)


def _parse_date(s: str) -> date:
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


def parse_contexts(root) -> dict[str, tuple[IxPeriod, list[str]]]:
    out = {}
    for ctx in root.iter(f"{{{NS['xbrli']}}}context"):
        cid = ctx.get("id")
        per_el = ctx.find(f"{{{NS['xbrli']}}}period")
        if per_el is None:
            continue
        instant = per_el.find(f"{{{NS['xbrli']}}}instant")
        if instant is not None:
            p = IxPeriod(kind="instant", start=None, end=_parse_date(instant.text))
        else:
            s = _parse_date(per_el.find(f"{{{NS['xbrli']}}}startDate").text)
            e = _parse_date(per_el.find(f"{{{NS['xbrli']}}}endDate").text)
            p = IxPeriod(kind="duration", start=s, end=e)
        segs: list[str] = []
        seg_el = ctx.find(f".//{{{NS['xbrli']}}}segment")
        if seg_el is not None:
            for m in seg_el.iter(f"{{{NS['xbrldi']}}}explicitMember"):
                dim = (m.get("dimension") or "").split(":")[-1]
                mem = (m.text or "").strip().split(":")[-1]
                segs.append(f"{dim}={mem}")
        out[cid] = (p, segs)
    return out


def parse_units(root) -> dict[str, str]:
    out = {}
    for u in root.iter(f"{{{NS['xbrli']}}}unit"):
        uid = u.get("id")
        measure = u.find(f"{{{NS['xbrli']}}}measure")
        divide = u.find(f"{{{NS['xbrli']}}}divide")
        if measure is not None:
            out[uid] = measure.text.strip().split(":")[-1]
        elif divide is not None:
            num = divide.find(f".//{{{NS['xbrli']}}}unitNumerator/{{{NS['xbrli']}}}measure")
            den = divide.find(f".//{{{NS['xbrli']}}}unitDenominator/{{{NS['xbrli']}}}measure")
            out[uid] = f"{num.text.strip().split(':')[-1]}/{den.text.strip().split(':')[-1]}"
    return out


def _is_parens_negative(elem) -> bool:
    """True iff this iXBRL fact element is wrapped in accounting parens
    `(VALUE)` per US filer convention.

    Three rendering patterns observed across SEC iXBRL:
      (A) Single-cell, parens-in-text: `<td>(<ix>VALUE</ix>)</td>`. Cell's
          full text content reads `(VALUE)`.
      (B) Single-cell, parens-as-sibling-spans:
          `<td><p><span>(</span><span><ix>VALUE</ix></span></p></td>`
          (and its closing `)` in another span sibling). Cell's full text
          still reads `(VALUE)` after concatenation.
      (C) Multi-cell: `<td>(</td><td><ix>VALUE</ix></td><td>)</td>` — the
          parens sit in their own `<td>` siblings (CELH 2023-Q1+ 10-Q
          renderer). Cell text is just `VALUE`; the `(` and `)` are in
          adjacent cells.

    The unified detection: find the enclosing `<td>`, take its full text
    content, plus the visible text of the immediate previous/next non-blank
    `<td>` siblings. Apply the patterns in order. Per
    `feedback_cf_visual_sign.md`, CF values MUST honor the filer's visual
    sign — extracted values must match the parens-negative convention the
    human reader sees.
    """
    td = elem
    while td is not None and etree.QName(td).localname != "td":
        td = td.getparent()
    if td is None:
        return False

    def _td_text(td_el):
        return " ".join(td_el.itertext()).strip()

    def _adj_td(start, direction: str) -> str | None:
        """Visible text of the nearest non-blank sibling `<td>`. Skip blank
        spacer cells. Return None if no such sibling within 6 hops."""
        s = start
        for _ in range(6):
            s = s.getprevious() if direction == "prev" else s.getnext()
            if s is None:
                return None
            if etree.QName(s).localname != "td":
                continue
            t = _td_text(s)
            if not t:
                continue
            return t
        return None

    cell_text = _td_text(td)
    prev_text = _adj_td(td, "prev")
    next_text = _adj_td(td, "next")

    # Strip leading currency / whitespace decoration so `$ ( 1,278,691 )`
    # matches Pattern A. Trailing whitespace already handled by .rstrip().
    cell_lstripped = re.sub(r"^[\s$ ]+", "", cell_text)

    # Pattern (A) + (B): paren-bracketed within the cell.
    if cell_lstripped.startswith("(") and cell_text.rstrip().endswith(")"):
        return True

    # Pattern (C): multi-cell. `(` cell -> value cell -> `)` cell.
    if prev_text == "(" and next_text == ")":
        return True

    # Hybrid: open paren inline in this cell, close paren in next cell.
    if cell_lstripped.startswith("(") and next_text == ")":
        return True

    # Hybrid: open paren in prev cell, close paren inline in this cell.
    if prev_text == "(" and cell_text.rstrip().endswith(")"):
        return True

    return False


def _build_ixfact(nf_el, contexts: dict, units: dict) -> IxFact | None:
    """Construct an IxFact from one `<ix:nonFraction>` element. Sign comes from
    surrounding HTML parens (authoritative). Returns None if context/value is
    missing or unparseable."""
    concept = nf_el.get("name", "")
    if not concept:
        return None
    ctx_id = nf_el.get("contextRef", "")
    if ctx_id not in contexts:
        return None
    unit_id = nf_el.get("unitRef", "")
    scale = int(nf_el.get("scale", "0") or "0")
    decimals = nf_el.get("decimals")
    raw = (nf_el.text or "").strip()
    if not raw:
        return None
    try:
        base = Decimal(raw.replace(",", "").lstrip("-"))
    except Exception:
        return None
    magnitude = base * (Decimal(10) ** scale)
    val = -magnitude if _is_parens_negative(nf_el) else magnitude
    period, segments = contexts[ctx_id]
    ns, local = concept.split(":", 1) if ":" in concept else ("", concept)
    return IxFact(
        concept=concept, local_name=local, namespace=ns,
        ctx_period=period, ctx_segments=segments,
        raw_value=raw, value_scaled=val, scale=scale,
        unit=units.get(unit_id, unit_id),
        decimals=decimals,
    )


# --- HTM table walker ---------------------------------------------------------

def _localname(el) -> str:
    tag = el.tag
    if not isinstance(tag, str):
        return ""
    return etree.QName(el).localname


def _text(el) -> str:
    """Concatenated visible text of an element (trimmed, single-spaced).

    Returns "" for non-element nodes (comments, processing instructions) —
    lxml's `itertext()` rejects those as roots. Older filings (e.g. GOOG
    pre-2019) embed HTML comments at the document level that surface from
    `root.iter()`."""
    if not isinstance(el.tag, str):
        return ""
    return " ".join(el.itertext()).strip()


_NUM_ONLY_RE = re.compile(r"^[\s$()\-—–.\d,%]*$")

# Pure date-only label (month + year, or year alone). Some filers — notably
# PG's quarterly BS — split equity rows across two `<tr>`s, with the second
# row labeled only by a date stamp ("June 2025") while carrying the primary
# equity dollar concept (CommonStockValue, PreferredStockValue, etc.). When
# the label is JUST a date, fall back to the concept-derived friendly name
# so the row matches a canonical alias instead of becoming a novel.
_DATE_ONLY_LABEL_RE = re.compile(
    r"^\s*(?:"
    r"(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}"
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\.?\s+\d{4}"
    r"|\d{4}"
    r")\s*$",
    re.IGNORECASE,
)


def _is_date_only_label(label: str) -> bool:
    return bool(_DATE_ONLY_LABEL_RE.match(label or ""))


def _row_label(tr) -> str:
    """First `<td>` / `<th>` whose text isn't purely numeric/decoration.

    The label cell SOMETIMES contains inline `ix:nonFraction` tags inline
    in the description (e.g. equity-class rows: "Series A convertible
    preferred stock, $0.001 par value per share, 1,467 shares issued..."
    with par-value and shares-issued tagged inside the text). A simpler
    'skip cells with ix' heuristic misses these. Treating cells as label
    candidates by text-shape (substantial non-numeric content) handles
    both pure-label and mixed cells.

    Pure-decoration cells skipped: '$', '—', '(48,226)', '0.001',
    'colspan=2 spacer', etc. Returns '' for blank / purely-decorative
    rows (header rows, blank spacers between sections)."""
    for td in tr.xpath("./*[local-name()='td' or local-name()='th']"):
        txt = _text(td)
        if not txt:
            continue
        # Pure-numeric or symbol-only cell: $, em-dash, digits, parens, %.
        # These are value cells or column separators, not labels.
        if _NUM_ONLY_RE.match(txt):
            continue
        return txt
    return ""


def find_primary_tables(root) -> list[tuple[str, etree._Element]]:
    """Walk the document; return [(code, table_el)] for every table that
    belongs to a primary statement. Long statements that page-break in the
    rendered HTML span multiple consecutive `<table>` elements under the
    SAME repeated title (e.g., CELH's CF = 3 tables: CFO+CFI / CFF+ending /
    supplemental disclosure). All tables under one primary-statement code
    accumulate; the walker dumps their rows into the same bucket downstream.

    A primary title (anything matching `_PRIMARY_TITLE_RE`) becomes the
    "active" title and STAYS active across subsequent tables until a title
    classified to a DIFFERENT primary code arrives. Repeated titles for the
    same statement (e.g., "Consolidated Statements of Cash Flows" appearing
    above each split sub-table) keep the same active code without dropping
    the cluster.

    SE skipped (out of scope), CI deferred to 4th-statement build, "?"
    classifications dropped."""
    pairings: list[tuple[str, etree._Element]] = []
    last_title: str | None = None
    last_code: str | None = None
    # The Notes-to-Financial-Statements heading also appears in the TOC at the
    # top of every 10-Q/10-K — fires BEFORE the actual primary tables. To
    # distinguish, only treat the notes-terminator as final once we've actually
    # collected at least one primary statement table.
    primary_collected = False
    notes_section_entered = False
    for el in root.iter():
        name = _localname(el)
        if name == "table":
            if notes_section_entered or last_code is None:
                continue
            nfs = el.xpath(".//ix:nonFraction", namespaces=NS)
            if len(nfs) < 5:
                continue
            rows = el.xpath(".//*[local-name()='tr']")
            if len(rows) < 3:
                continue
            if last_code in {"IS", "BS", "CF"}:
                pairings.append((last_code, el))
                primary_collected = True
            continue
        txt = _text(el)
        if not txt:
            continue
        # Notes section terminator — once we enter the notes section, no more
        # primary tables can be added. Gate on `primary_collected` to skip the
        # TOC's notes entry which fires before any tables.
        if (
            primary_collected
            and not notes_section_entered
            and _NOTES_SECTION_RE.match(txt)
            and len(txt) < 200
        ):
            notes_section_entered = True
            last_title = None
            last_code = None
            continue
        # Title detection. Real headings:
        #   - Start with the primary keyword.
        #   - Don't end with a period (sentence vs heading).
        #   - Are short (< 150 chars).
        # Footnote prose like "...the consolidated balance sheets. Any amounts
        # not utilized..." starts with "consolidated balance sheets" and would
        # match a naive regex; the trailing-period check rejects it.
        if len(txt) > 150:
            continue
        if txt.rstrip().endswith("."):
            continue
        if _PRIMARY_TITLE_RE.match(txt):
            new_code = classify_title(txt)
            # Take over only when the title belongs to a different statement
            # OR there's no active title yet. Repeated same-code titles keep
            # the cluster active so multi-page-break statements accumulate.
            if last_code is None or new_code != last_code:
                last_title = txt
                last_code = new_code
    return pairings


# Section header text patterns inside a primary table. Matched against the
# row label (first non-empty td). Sets the active section for subsequent rows
# until another header / reset / subtotal-transition fires.
_HEADER_PATTERNS: list[tuple[re.Pattern, Section]] = [
    # BS sections — header rows like "Current assets:", "ASSETS", "LIABILITIES",
    # "Stockholders' equity"
    (re.compile(r"\bcurrent\s+assets\b", re.I),                                Section.CURRENT_ASSETS),
    (re.compile(r"\b(non.current|noncurrent|long.term)\s+assets\b", re.I),     Section.NON_CURRENT_ASSETS),
    (re.compile(r"\bcurrent\s+liabilities\b", re.I),                           Section.CURRENT_LIABILITIES),
    (re.compile(r"\b(non.current|noncurrent|long.term)\s+liabilities\b", re.I), Section.NON_CURRENT_LIABILITIES),
    (re.compile(r"\b(mezzanine|temporary)\s+equity\b", re.I),                  Section.MEZZANINE),
    (re.compile(r"\b(stockholders|shareholders)['’]?\s*(deficit|equity)\b", re.I), Section.EQUITY),
    # CF sections
    (re.compile(r"\b(cash\s+flows?\s+(from|used\s+in)\s+)?operating\s+activities\b", re.I), Section.OPERATING),
    (re.compile(r"\b(cash\s+flows?\s+(from|used\s+in)\s+)?investing\s+activities\b", re.I), Section.INVESTING),
    (re.compile(r"\b(cash\s+flows?\s+(from|used\s+in)\s+)?financing\s+activities\b", re.I), Section.FINANCING),
]


# Header phrases that RESET the section to UNCLASSIFIED — used for the
# supplemental-disclosure block following the main CF activities. Without this
# reset, the walker would inherit the previous section (typically Financing)
# and pollute the financing subtotal with non-cash disclosure amounts.
_HEADER_RESET_PATTERNS: list[re.Pattern] = [
    re.compile(r"supplemental\s+(schedule|disclosure)s?\s+of\s+(non.cash|noncash)", re.I),
    re.compile(r"(non.cash|noncash)\s+(investing|financing)\s+(and|&)\s+(financing|investing)", re.I),
    re.compile(r"supplemental\s+(disclosure|disclosures)s?(\s+of\s+cash\s+flow\s+information)?", re.I),
]


# OCI section header inside a combined IS+CI table. When we hit this, stop
# emitting IS rows entirely — the rest of the table is OCI, deferred to the
# 4th-statement build per `feedback_oci_separate_statement.md`. Catches both
# "Other comprehensive income:" headers AND filers that drop "other" and just
# write "Comprehensive income:" / "Foreign currency translation adjustments..."
# after the IS bottom line. The bare-comprehensive-income-line variant is
# riskier (could match the IS subtotal "Comprehensive income" itself), but the
# guard fires AFTER NetIncome by virtue of document order.
_OCI_HEADER_RE = re.compile(
    r"^(other\s+comprehensive\s+(income|loss)|"
    r"(foreign\s+currency\s+translation|comprehensive\s+income)\b)",
    re.I,
)

# CF non-cash supplemental block — once we hit this header, stop emitting
# rows from the CF table. The block contains "Fair value of share
# consideration issued in the X Acquisition", "Fair value of Series B
# Preferred Stock issued to Pepsi", etc. — these are NON-CASH disclosures
# rendered inside the CF table but they aren't cash flows and shouldn't be
# included in CFO/CFI/CFF subtotals.
_CF_NONCASH_STOP_RE = re.compile(
    r"^(supplemental\s+(schedule|disclosure)s?\s+of\s+(non.cash|noncash)|"
    r"(non.cash|noncash)\s+(investing|financing))",
    re.I,
)


# Subtotal labels that mark a section transition. When emitted, the
# SUBSEQUENT rows pick up the listed section. Filers don't always use a
# proper section-header for non-current liabilities; many render Items
# directly between "Total current liabilities" and "Total liabilities".
_HTM_SUBTOTAL_TRANSITIONS: list[tuple[re.Pattern, Section]] = [
    (re.compile(r"^total\s+current\s+assets\b", re.I),                          Section.NON_CURRENT_ASSETS),
    (re.compile(r"^total\s+current\s+liabilit", re.I),                          Section.NON_CURRENT_LIABILITIES),
    (re.compile(r"^total\s+liabilit", re.I),                                    Section.EQUITY),
    (re.compile(r"^total\s+(stockholders|shareholders)['’]?\s*equity", re.I), Section.UNCLASSIFIED),
    # CF: financing subtotal → cash-other (FX effect, net change in cash, ending cash).
    # Both wordings supported — "Net cash provided by financing activities" (CELH-
    # style) and "TOTAL FINANCING ACTIVITIES" (PG-style).
    (re.compile(r"^net\s+cash\s+(provided\s+by|used\s+in)?.*financing", re.I), Section.CASH_OTHER),
    (re.compile(r"^total\s+financing\s+activities\b", re.I),                   Section.CASH_OTHER),
]


# Per-row section override: if the row label matches one of these patterns,
# the row's section is FORCED to the given Section regardless of the walker's
# current state. Used for cash-flow tail rows ("Effect of exchange rate
# changes on cash", "Net change in cash") that always belong to CASH_OTHER
# even when no header reset preceded them.
_HTM_ROW_SECTION_OVERRIDE: list[tuple[re.Pattern, Section]] = [
    (re.compile(r"^effect\s+(of|on)\s+exchange\s+rate", re.I),                  Section.CASH_OTHER),
    (re.compile(r"^net\s+(\([^)]*\)\s+)?(increase|decrease)\s+in\s+cash", re.I), Section.CASH_OTHER),
    (re.compile(r"^cash[, ].*(beginning|end)\s+of", re.I),                       Section.CASH_OTHER),
]


def _match_section_header(label: str) -> Section | None:
    """Return Section if the label matches a section-header pattern; None if
    not. Reset patterns return Section.UNCLASSIFIED. Order matters — reset
    patterns checked first so a CF supplemental block doesn't get caught by
    the bare 'financing activities' matcher."""
    if any(pat.search(label) for pat in _HEADER_RESET_PATTERNS):
        return Section.UNCLASSIFIED
    for pat, sec in _HEADER_PATTERNS:
        if pat.search(label):
            return sec
    return None


def _match_subtotal_transition(label: str) -> Section | None:
    """If the row label matches a subtotal-transition pattern, return the
    section that takes effect for subsequent rows. None if no match."""
    for pat, sec in _HTM_SUBTOTAL_TRANSITIONS:
        if pat.search(label):
            return sec
    return None


@dataclass
class WalkRow:
    """Output of walking one row in a primary table. Equity-class rows
    sometimes have inline `ix:nonFraction` memo facts (par value, shares
    issued/outstanding) embedded inside the descriptive label cell — those
    emit as separate line items with per-concept synthesized labels and
    `row_type="memo"`. The row's primary facts (in value cells) carry the
    row's descriptive label and the row's resolved row_type."""
    label: str
    section: Section
    row_type: str           # primary row type: "line_item" | "subtotal"
    facts: list[IxFact]     # primary facts (one per period column)
    memo_facts: list[IxFact] = field(default_factory=list)  # inline memo facts in label cell


def walk_statement_table(
    table, stmt_type: StatementType, contexts: dict, units: dict,
    calc_subtotal_concepts: set[str] | None = None,
    subtotal_concepts: set[str] | None = None,
) -> list[WalkRow]:
    """Walk rows of a primary statement table in document order. Maintain
    section state via header rows + subtotal transitions. Return one WalkRow
    per data row (rows with at least one ix:nonFraction). Header / blank /
    label-only rows are consumed for state but produce no WalkRow.

    For combined IS+CI tables (CELH), stop emitting on the OCI header so
    OCI rows don't leak into the IS Statement (4th-statement build deferred).
    """
    rows: list[WalkRow] = []
    current_section = Section.UNCLASSIFIED
    pending_section_after_subtotal: Section | None = None

    for tr in table.xpath(".//*[local-name()='tr']"):
        label = _row_label(tr)

        # Walk cells in order; partition ix:nonFraction tags by cell kind:
        #   - label cell: substantial non-numeric text (the row's description).
        #     ix tags inside are inline memo facts (par value, shares issued,
        #     percentages embedded in the prose).
        #   - value cell: pure numeric/symbol text. ix tags here are the row's
        #     primary values, one per period column.
        label_cell_nfs: list = []
        value_cell_nfs: list = []
        for td in tr.xpath("./*[local-name()='td' or local-name()='th']"):
            td_nfs = td.xpath(".//ix:nonFraction", namespaces=NS)
            if not td_nfs:
                continue
            txt = _text(td)
            if txt and not _NUM_ONLY_RE.match(txt):
                label_cell_nfs.extend(td_nfs)
            else:
                value_cell_nfs.extend(td_nfs)
        all_nfs = label_cell_nfs + value_cell_nfs

        # OCI guard for combined IS+CI tables — once we hit the OCI block,
        # everything below is comprehensive-income content. Stop walking.
        if stmt_type == StatementType.INCOME_STATEMENT and _OCI_HEADER_RE.search(label):
            break
        # CF non-cash supplemental disclosure block — stop emitting CF rows
        # once we hit "Supplemental schedule of non-cash investing and
        # financing activities" / "Non-cash investing and financing
        # activities". These rows are NOT cash flows; they're informational
        # disclosures rendered inside the CF table for convenience and
        # would pollute CFO/CFI/CFF subtotals if summed.
        if stmt_type == StatementType.CASH_FLOW and _CF_NONCASH_STOP_RE.search(label):
            break

        # Section state updates — done BEFORE row emission so a header row's
        # section applies to it (a "Current assets:" header doesn't have facts
        # but it sets the section for the rows below).
        if label and not all_nfs:
            sec = _match_section_header(label)
            if sec is not None:
                current_section = sec
                pending_section_after_subtotal = None
            continue  # header / blank — no data emission

        if not all_nfs:
            continue  # purely decorative row

        # Apply pending section transition if any (set by previous row's
        # subtotal). The CURRENT row picks up the new section, and we stay in
        # the new section until the next transition.
        if pending_section_after_subtotal is not None:
            current_section = pending_section_after_subtotal
            pending_section_after_subtotal = None

        # Per-row override: certain row labels always force a specific section
        # regardless of walker state. Used for CF tail rows (Effect of FX, Net
        # Change in Cash, Cash beg/end of period) that belong to CASH_OTHER.
        row_override_section: Section | None = None
        for pat, sec in _HTM_ROW_SECTION_OVERRIDE:
            if pat.search(label):
                row_override_section = sec
                break
        emit_section = row_override_section if row_override_section is not None else current_section

        # Row type detection. Subtotal rows get row_type="subtotal" so reconcile
        # routes them to the _subtotal sheet. Detection: label keyword OR
        # primary-fact concept in IXBRL_SUBTOTAL_CONCEPTS allowlist. Use the
        # FIRST value-cell concept for subtotal detection — label-cell concepts
        # are memo context, not the row's primary fact.
        #
        # NOTE (§18e attempt 2026-04-27): we tried replacing the allowlist with
        # the iXBRL calc linkbase (calc-tree parents = subtotals). The premise
        # was too broad — calc-tree parents include mid-statement aggregations
        # like `IncomeLossFromContinuingOperationsBeforeIncomeTaxes...` which
        # the pipeline currently treats as line items and SUM-formulas at
        # model-write time. Tagging those as subtotal at extract time forces
        # strict-mode alias lookup, which then fails on filer label variations
        # ("Net income before income taxes" with no exact alias). The proper
        # structural signal would be the presentation linkbase's
        # `preferredLabel="totalLabel"` (only flags rows the filer chose to
        # render as totals). The calc linkbase is still loaded into
        # `calc_subtotal_concepts` for future use — subtotal synthesis when a
        # filer reports only summands without a parent (the linkbase declares
        # exactly which children sum to which parent and with what weight).
        is_subtotal_label = bool(re.match(r"^total\b", label, re.I))
        primary_nfs = value_cell_nfs or all_nfs
        first_concept = (primary_nfs[0].get("name", "") or "").split(":", 1)[-1]
        # Subtotal-concept set comes from the caller: union of the static
        # IXBRL_SUBTOTAL_CONCEPTS allowlist (floor) with concepts the filer
        # tagged `preferredLabel=totalLabel` in the presentation linkbase
        # (filer-declared rendering intent). Falls back to the static
        # allowlist alone when the caller didn't supply a set (e.g. no
        # cached `*_pre.xml`).
        active_subtotal_concepts = subtotal_concepts if subtotal_concepts is not None else IXBRL_SUBTOTAL_CONCEPTS
        is_subtotal_concept = first_concept in active_subtotal_concepts
        row_type = "subtotal" if (is_subtotal_label or is_subtotal_concept) else "line_item"

        # Build IxFacts. Label-cell facts go to memo_facts; value-cell facts
        # are the row's primary facts.
        primary_facts: list[IxFact] = []
        memo_facts: list[IxFact] = []
        for nf_el in value_cell_nfs:
            f = _build_ixfact(nf_el, contexts, units)
            if f is not None:
                primary_facts.append(f)
        for nf_el in label_cell_nfs:
            f = _build_ixfact(nf_el, contexts, units)
            if f is not None:
                memo_facts.append(f)
        if not primary_facts and not memo_facts:
            continue

        rows.append(WalkRow(
            label=label, section=emit_section, row_type=row_type,
            facts=primary_facts, memo_facts=memo_facts,
        ))

        # Subtotal-transition: the SUBSEQUENT row picks up the new section.
        # Detection by label (matches any "Total current assets" wording across
        # filers) plus concept-based fallback (when label says e.g. just
        # "TOTAL" but the concept is unmistakable).
        next_sec = _match_subtotal_transition(label)
        if next_sec is None and first_concept in {"AssetsCurrent"}:
            next_sec = Section.NON_CURRENT_ASSETS
        elif next_sec is None and first_concept in {"LiabilitiesCurrent"}:
            next_sec = Section.NON_CURRENT_LIABILITIES
        elif next_sec is None and first_concept in {"Liabilities"}:
            next_sec = Section.EQUITY
        if next_sec is not None:
            pending_section_after_subtotal = next_sec

    return rows


# --- Statement assembly -------------------------------------------------------

@dataclass(frozen=True)
class PeriodKey:
    """One Statement is one (statement_type, period). Multiple period columns
    in a single primary table produce multiple Statements."""
    stmt_type: StatementType
    period_kind: str          # "instant" | "duration"
    period_start: date | None
    period_end: date


def detect_statement_unit(facts: list[IxFact]) -> tuple[Unit, str, float]:
    """Pick the Unit for a Statement based on the dominant scale of its USD
    facts. Returns (unit, raw_phrase, confidence)."""
    scale_counts: dict[int, int] = defaultdict(int)
    for f in facts:
        if f.unit == "USD":
            scale_counts[f.scale] += 1
    if not scale_counts:
        return Unit.ACTUAL, "no USD facts", 0.5
    dominant, count = max(scale_counts.items(), key=lambda kv: kv[1])
    total = sum(scale_counts.values())
    unit = SCALE_TO_UNIT.get(dominant, Unit.ACTUAL)
    phrase = {
        Unit.THOUSANDS: "in thousands",
        Unit.MILLIONS: "in millions",
        Unit.BILLIONS: "in billions",
        Unit.ACTUAL: "",
    }[unit]
    return unit, phrase, count / total


def fiscal_quarter_from_key(
    key: PeriodKey, filing_fq: int | None, filing_end: date, fye_month: int,
) -> int | None:
    if filing_fq is None and key.stmt_type == StatementType.BALANCE_SHEET:
        return None
    m = key.period_end.month
    month_idx = ((m - fye_month - 1) % 12) + 1
    q = (month_idx + 2) // 3
    return max(1, min(4, q))


def value_in_unit(val_actual: Decimal, unit: Unit) -> Decimal:
    if unit == Unit.THOUSANDS:
        return val_actual / Decimal(1000)
    if unit == Unit.MILLIONS:
        return val_actual / Decimal(1_000_000)
    if unit == Unit.BILLIONS:
        return val_actual / Decimal(1_000_000_000)
    return val_actual


_PER_SHARE_CONCEPT_PREFIXES = (
    "EarningsPerShare",
    "IncomeLossFromContinuingOperationsPerBasicAndDilutedShare",
    "IncomeLossFromContinuingOperationsPerBasicShare",
    "IncomeLossFromContinuingOperationsPerDilutedShare",
    "IncomeLossPerOutstandingLimitedPartnershipAndGeneralPartnershipUnit",
    "CommonStockDividendsPerShareDeclared",
    "CommonStockDividendsPerShareCashPaid",
)


def _is_per_share_concept(local_name: str) -> bool:
    return any(local_name.startswith(p) for p in _PER_SHARE_CONCEPT_PREFIXES)


def _is_share_count_concept(local_name: str) -> bool:
    return (
        local_name.startswith("WeightedAverageNumberOf")
        or local_name.endswith("SharesIssued")
        or local_name.endswith("SharesOutstanding")
        or local_name == "CommonStockSharesIssued"
        or local_name == "CommonStockSharesOutstanding"
    )


# --- Section heuristic (last-resort fallback when walker section is UNCLASSIFIED)

_SECTION_BY_CONCEPT_FRAGMENT_BS = [
    (re.compile(r"^(Assets|Cash|AccountsReceivable|Inventory|Prepaid|PropertyPlant|Goodwill|Intangible|Investments)", re.I),
     lambda n: Section.CURRENT_ASSETS if "Current" in n else Section.NON_CURRENT_ASSETS),
    (re.compile(r"^(Liabilities|AccountsPayable|AccruedLiab|Notes|LongTerm|ShortTerm|Debt|DeferredTax)", re.I),
     lambda n: Section.CURRENT_LIABILITIES if "Current" in n else Section.NON_CURRENT_LIABILITIES),
    (re.compile(r"^(Stockholders|Shareholders|CommonStock|PreferredStock|RetainedEarn|TreasuryStock|AdditionalPaid|AccumulatedOther|NoncontrollingInterest)", re.I),
     lambda n: Section.EQUITY),
]
_SECTION_BY_CONCEPT_FRAGMENT_CF = [
    (re.compile(r"^(NetCash.*Operating|Depreciation|Amortization|ShareBasedComp|IncreaseDecreaseIn|DeferredIncomeTax|GainLoss|OtherNoncash)", re.I),
     lambda n: Section.OPERATING),
    (re.compile(r"^(NetCash.*Investing|PaymentsToAcquire|ProceedsFromSale|PaymentsForProceeds)", re.I),
     lambda n: Section.INVESTING),
    (re.compile(r"^(NetCash.*Financing|PaymentsOfDividends|PaymentsForRepurchase|ProceedsFromIssuance|RepaymentsOf|ProceedsFromStockOptions|ProceedsFromRepayments)", re.I),
     lambda n: Section.FINANCING),
    (re.compile(r"^EffectOfExchange", re.I), lambda n: Section.CASH_OTHER),
]
_SECTION_BY_CONCEPT_FRAGMENT_IS = [
    (re.compile(r"^(Revenues|SalesRevenue|CostOf|GrossProfit)", re.I),
     lambda n: Section.REVENUE_COST),
    (re.compile(r"^(SellingGeneralAndAdmin|ResearchAndDevelopment|OperatingExpenses|OperatingIncome)", re.I),
     lambda n: Section.OPERATING_EXPENSES),
    (re.compile(r"^(InterestExpense|InterestIncome|InvestmentIncome|OtherNonoperating)", re.I),
     lambda n: Section.NON_OPERATING),
    (re.compile(r"^(IncomeTax|DeferredIncomeTax)", re.I), lambda n: Section.TAX),
    (re.compile(r"^(EarningsPerShare|WeightedAverageNumberOf)", re.I), lambda n: Section.EPS),
]


def classify_section(local_name: str, stmt_type: StatementType) -> Section:
    """Walker fallback when in-table section can't be inferred from headers /
    subtotal transitions. Patterns are stmt-type-scoped — IS sections like
    TAX / NON_OPERATING never fire on CF concepts (PG's `IncomeTaxesPaid` on
    the CF would otherwise tag as TAX, then the lookup would reject the
    operating-section CF supplemental canonical)."""
    if stmt_type == StatementType.BALANCE_SHEET:
        patterns = _SECTION_BY_CONCEPT_FRAGMENT_BS
    elif stmt_type == StatementType.CASH_FLOW:
        patterns = _SECTION_BY_CONCEPT_FRAGMENT_CF
    elif stmt_type == StatementType.INCOME_STATEMENT:
        patterns = _SECTION_BY_CONCEPT_FRAGMENT_IS
    else:
        return Section.UNCLASSIFIED
    for rx, resolver in patterns:
        if rx.match(local_name):
            return resolver(local_name)
    return Section.UNCLASSIFIED


# CamelCase split for synthesizing display labels from concept local names —
# fallback only, fires when the row label is empty (extremely rare in primary
# statements; included for defensive behavior).
_CAMEL_SPLIT_LOWER_UPPER = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_CAMEL_SPLIT_ACRONYM = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")


def concept_to_display(concept_local_name: str) -> str:
    s = _CAMEL_SPLIT_ACRONYM.sub(" ", concept_local_name)
    s = _CAMEL_SPLIT_LOWER_UPPER.sub(" ", s)
    return s.strip()


# --- Top-level entry ----------------------------------------------------------

def load_meta(htm_path: Path) -> dict:
    meta_path = htm_path.with_suffix(".meta.json")
    if not meta_path.exists():
        raise SystemExit(
            f"No .meta.json sidecar at {meta_path}. "
            f"Re-fetch the filing via sec-edgar-fetch so metadata is available."
        )
    return json.loads(meta_path.read_text(encoding="utf-8"))


# ============================================================================
# Calculation linkbase loader — structural subtotal detection
# ============================================================================
#
# The iXBRL calculation linkbase (`*_cal.xml`) declares parent-of-summands
# relationships explicitly: each `<link:calculationArc xlink:from="X" xlink:to="Y">`
# means Y is a child of X (and X is a subtotal). This is the filer's own
# FASB-blessed declaration of what's a subtotal, replacing the static
# `IXBRL_SUBTOTAL_CONCEPTS` allowlist.
#
# Cache layout: `~/.claude/skills/financials-extract/.cache/ixbrl_reports/{accession_nodash}/{ticker}-{date}_cal.xml`
# When the cal.xml isn't on disk we return None and the caller falls back to
# the static allowlist.

_IXBRL_REPORTS_CACHE = Path(__file__).resolve().parent.parent / ".cache" / "ixbrl_reports"
_LINK_NS = "http://www.xbrl.org/2003/linkbase"
_XLINK_NS = "http://www.w3.org/1999/xlink"
_HREF_CONCEPT_RE = re.compile(r"#[\w-]+_([A-Za-z]\w+)$")


_PRESENTATION_TOTAL_LABEL_SUFFIX = "/totalLabel"


def _load_presentation_total_concepts(meta: dict) -> set[str] | None:
    """Read the filing's presentation linkbase from cache and return the set
    of concept LOCAL NAMES whose `preferredLabel` ends in `/totalLabel` —
    i.e., concepts the FILER chose to render as totals (bold, top border,
    section-end styling).

    This is the right structural signal for routing-time subtotal detection:
    it captures the filer's own rendering intent, not just our hardcoded
    allowlist (which can lag new filers' subtotal concepts).

    Used as an EXPANDER on top of `IXBRL_SUBTOTAL_CONCEPTS`, which stays as
    the floor (covers concepts that are mathematically always subtotals
    even if a filer skips the `totalLabel` flag).

    Returns None when:
      - the accession's cache directory doesn't exist
      - no `*_pre.xml` file is in the cache directory
      - the file fails to parse
    """
    accession_nodash = meta.get("accession", "").replace("-", "")
    if not accession_nodash:
        return None
    cache_dir = _IXBRL_REPORTS_CACHE / accession_nodash
    if not cache_dir.is_dir():
        return None
    pre_files = list(cache_dir.glob("*_pre.xml"))
    if not pre_files:
        return None
    try:
        tree = etree.parse(str(pre_files[0]))
    except (etree.XMLSyntaxError, OSError):
        return None
    root = tree.getroot()

    # Pre-build locator label -> concept local name (concepts referenced from
    # different presentationLink roles share locator labels per role; we walk
    # arc-by-arc within their parent presentationLink so the loc lookup is
    # scoped correctly).
    totals: set[str] = set()
    for plink in root.iter(f"{{{_LINK_NS}}}presentationLink"):
        loc_to_concept: dict[str, str] = {}
        for loc in plink.iter(f"{{{_LINK_NS}}}loc"):
            label = loc.get(f"{{{_XLINK_NS}}}label")
            href = loc.get(f"{{{_XLINK_NS}}}href", "")
            m = _HREF_CONCEPT_RE.search(href)
            if label and m:
                loc_to_concept[label] = m.group(1)
        for arc in plink.iter(f"{{{_LINK_NS}}}presentationArc"):
            preferred = arc.get("preferredLabel", "")
            if not preferred.endswith(_PRESENTATION_TOTAL_LABEL_SUFFIX):
                continue
            to_label = arc.get(f"{{{_XLINK_NS}}}to")
            concept = loc_to_concept.get(to_label or "")
            if concept:
                totals.add(concept)
    return totals


def _load_calc_subtotal_concepts(meta: dict) -> set[str] | None:
    """Read the filing's calculation linkbase from cache and return the set
    of concept LOCAL NAMES that appear as `xlink:from` on any calculationArc
    (i.e., declared subtotals / parents-of-summands).

    Returns None when:
      - the accession's cache directory doesn't exist
      - no `*_cal.xml` file is in the cache directory
      - the file fails to parse

    Callers must treat None as "fall back to the static allowlist".
    """
    accession_nodash = meta.get("accession", "").replace("-", "")
    if not accession_nodash:
        return None
    cache_dir = _IXBRL_REPORTS_CACHE / accession_nodash
    if not cache_dir.is_dir():
        return None
    cal_files = list(cache_dir.glob("*_cal.xml"))
    if not cal_files:
        return None
    try:
        tree = etree.parse(str(cal_files[0]))
    except (etree.XMLSyntaxError, OSError):
        return None
    root = tree.getroot()

    # locator label -> concept local name (from xlink:href fragment).
    loc_to_concept: dict[str, str] = {}
    for loc in root.iter(f"{{{_LINK_NS}}}loc"):
        label = loc.get(f"{{{_XLINK_NS}}}label")
        href = loc.get(f"{{{_XLINK_NS}}}href", "")
        m = _HREF_CONCEPT_RE.search(href)
        if label and m:
            loc_to_concept[label] = m.group(1)

    # Concepts that appear as `from` on any calculationArc are subtotals.
    parents: set[str] = set()
    for arc in root.iter(f"{{{_LINK_NS}}}calculationArc"):
        f_label = arc.get(f"{{{_XLINK_NS}}}from")
        if f_label and f_label in loc_to_concept:
            parents.add(loc_to_concept[f_label])
    return parents


_CASH_BEG_LABEL_RE = re.compile(r"\bbeginning\s+of\b", re.I)
_CASH_END_LABEL_RE = re.compile(r"\b(end|ending)\s+of\b", re.I)


def _fold_cf_instants_into_durations(buckets: dict, memo_pair_ids: set) -> None:
    """Reassign instant-period CF facts (cash beginning/ending balance rows
    rendered at the bottom of the Cash Flow table) into the matching
    duration's CF bucket. Cash-beginning instants match `period_start` of a
    CF duration; cash-ending instants match `period_end`. Once all facts are
    moved, the empty instant bucket is dropped. Mutates `buckets` in place."""
    cf_durations = {
        k: k for k in buckets
        if k.stmt_type == StatementType.CASH_FLOW and k.period_kind == "duration"
    }
    if not cf_durations:
        return
    cf_instants = [
        k for k in buckets
        if k.stmt_type == StatementType.CASH_FLOW and k.period_kind == "instant"
    ]
    # Cash-beginning rows carry the instant of the PRIOR fiscal year-end
    # (e.g. 2024-12-31), but the matching CF duration starts on the next day
    # (2025-01-01). Allow a 1-day tolerance so the fold matches. The folded
    # facts are tagged as memo (via folded_memo_pair_ids) so the build step
    # synthesizes a memo row_type — they're cash-position bookends, NOT
    # flow components, so validate must not sum them into CashOther.
    for ik in cf_instants:
        keep: list = []
        for wr, f in buckets[ik]:
            target_key = None
            if _CASH_BEG_LABEL_RE.search(wr.label):
                for dk in cf_durations:
                    if dk.period_start is not None and (
                        dk.period_start == ik.period_end
                        or dk.period_start - timedelta(days=1) == ik.period_end
                    ):
                        target_key = dk
                        break
            elif _CASH_END_LABEL_RE.search(wr.label):
                for dk in cf_durations:
                    if dk.period_end == ik.period_end:
                        target_key = dk
                        break
            if target_key is not None:
                buckets[target_key].append((wr, f))
                memo_pair_ids.add(id(f))
            else:
                keep.append((wr, f))
        if keep:
            buckets[ik] = keep
        else:
            del buckets[ik]


def build_raw_filing(
    htm_path: Path,
    ticker: str | None = None,
    library_path: Path | None = None,
) -> RawFiling:
    meta = load_meta(htm_path)
    ticker = (ticker or meta["ticker"]).upper()

    raw_bytes = htm_path.read_bytes()
    root = etree.fromstring(raw_bytes, etree.XMLParser(recover=True, huge_tree=True))

    contexts = parse_contexts(root)
    units = parse_units(root)

    # 1. Find primary tables (BS / IS / CF). SE skipped; CI deferred.
    primary_tables = find_primary_tables(root)

    # Load the filing's calculation linkbase — currently used only as a
    # future hook for subtotal SYNTHESIS (when filer reports only summands
    # without a parent). NOT used for subtotal DETECTION; that signal comes
    # from the presentation linkbase below.
    calc_subtotal_concepts = _load_calc_subtotal_concepts(meta)

    # Load the filing's presentation linkbase to drive subtotal detection
    # structurally — concepts the filer tagged with `preferredLabel=totalLabel`
    # are the rows the filer chose to render as totals. Combined with the
    # static IXBRL_SUBTOTAL_CONCEPTS as a floor, this catches both filer-
    # specific subtotal concepts AND well-known concepts even when a filer
    # skips the totalLabel flag.
    presentation_subtotal_concepts: set[str] | None = _load_presentation_total_concepts(meta)
    walker_subtotal_concepts: set[str] = set(IXBRL_SUBTOTAL_CONCEPTS)
    if presentation_subtotal_concepts is not None:
        walker_subtotal_concepts |= presentation_subtotal_concepts

    library_index: dict | None = None
    concept_index: dict | None = None
    if library_path is not None:
        library = load_generic_library(library_path)
        library_index = build_generic_index(library)
        concept_index = build_concept_index(library)

    # 2. Walk each table, collect WalkRows per (PeriodKey).
    # buckets: PeriodKey -> ordered list of (WalkRow, IxFact). One WalkRow per
    # row label; we expand it into one (row, fact) pair per period column.
    buckets: dict[PeriodKey, list[tuple[WalkRow, IxFact]]] = defaultdict(list)
    # Track which (WalkRow, IxFact) pairs are memo facts vs primary facts so
    # the build step can synthesize per-concept labels and tag row_type=memo.
    memo_pair_ids: set[int] = set()
    for code, tbl in primary_tables:
        stmt_type = STATEMENT_CODE_MAP[code]
        walked = walk_statement_table(
            tbl, stmt_type, contexts, units,
            calc_subtotal_concepts=calc_subtotal_concepts,
            subtotal_concepts=walker_subtotal_concepts,
        )
        for wr in walked:
            for f in wr.facts:
                key = PeriodKey(
                    stmt_type=stmt_type,
                    period_kind=f.ctx_period.kind,
                    period_start=f.ctx_period.start,
                    period_end=f.ctx_period.end,
                )
                buckets[key].append((wr, f))
            for f in wr.memo_facts:
                key = PeriodKey(
                    stmt_type=stmt_type,
                    period_kind=f.ctx_period.kind,
                    period_start=f.ctx_period.start,
                    period_end=f.ctx_period.end,
                )
                buckets[key].append((wr, f))
                memo_pair_ids.add(id(f))

    # Cash beginning/ending facts on the CF table use INSTANT contexts (a
    # point-in-time balance), but they belong to the CF as flow-period
    # bookends — beginning matches a duration's period_start, ending matches
    # a duration's period_end. Without this fold, they orphan into 1-2 item
    # mini-Statements instead of joining the main CF for that period. Folded
    # facts are tagged as memo so they don't get summed into CashOther.
    _fold_cf_instants_into_durations(buckets, memo_pair_ids)

    # Filing metadata
    filing_end = date.fromisoformat(meta["report_date"])
    q_label = meta["quarter"]
    filing_fq: int | None = None
    m = re.match(r"(\d{4})-Q([1-4])", q_label)
    if m:
        filing_fq = int(m.group(2))
    if filing_fq is None:
        fye_month = filing_end.month
    else:
        fye_month = ((filing_end.month - filing_fq * 3 - 1) % 12) + 1

    # 3. Build Statements.
    statements: list[Statement] = []
    label_synthesis_misses: list[str] = []
    for key, pairs in buckets.items():
        # Detect statement unit from the bucket's USD facts.
        bucket_facts = [p[1] for p in pairs]
        stmt_unit, raw_phrase, confidence = detect_statement_unit(bucket_facts)
        period_fy = key.period_end.year if key.period_end.month <= fye_month else key.period_end.year + 1

        # fiscal_quarter:
        #   * BS instants: match to Q1/Q2/Q3 by month, None for FYE.
        #   * Full-year durations: None.
        #   * 10-Q IS/CF (3-month or YTD): tagged with filing_fq so column
        #     label renders "Q{N} FY{YYYY}".
        weeks = (
            round((key.period_end - key.period_start).days / 7)
            if key.period_kind == "duration" and key.period_start else None
        )
        is_full_year_duration = (
            key.period_kind == "duration" and weeks is not None and 48 <= weeks <= 54
        )
        if key.stmt_type == StatementType.BALANCE_SHEET:
            fq = fiscal_quarter_from_key(key, filing_fq, filing_end, fye_month)
        elif filing_fq is None or is_full_year_duration:
            fq = None
        else:
            fq = fiscal_quarter_from_key(key, filing_fq, filing_end, fye_month)

        period = Period(
            fiscal_year=period_fy,
            fiscal_quarter=fq,
            period_end_date=key.period_end,
            raw_period_label=(
                f"as of {key.period_end.isoformat()}" if key.period_kind == "instant"
                else f"{key.period_start.isoformat()} to {key.period_end.isoformat()} ({weeks}wk)"
            ),
            period_length_weeks=weeks,
            is_comparative=(key.period_end != filing_end),
        )

        line_items: list[RawLineItem] = []
        for wr, f in pairs:
            # Per-share / share-count concepts always render in actual units.
            if _is_per_share_concept(f.local_name) or _is_share_count_concept(f.local_name):
                value_in_stmt_unit = f.value_scaled
            else:
                value_in_stmt_unit = value_in_unit(f.value_scaled, stmt_unit)

            citation = Citation(
                source_path=htm_path,
                page=1,  # schema requires >=1; iXBRL has no pagination
                line_hint=f"{f.concept} | ctx:{f.ctx_period.kind}:{f.ctx_period.end.isoformat()}",
                note=f"iXBRL HTM | {STATEMENT_TYPE_TO_CODE.get(key.stmt_type, '?')}",
            )

            is_memo_fact = id(f) in memo_pair_ids
            if is_memo_fact:
                # Inline memo fact (par value, shares issued/outstanding etc.
                # rendered inside an equity-class label cell). Synthesize a
                # per-concept label so the BS doesn't have N rows with the
                # same filer-prose label. Format: "{row label trimmed} -
                # {CamelCase split}".
                concept_part = concept_to_display(f.local_name)
                row_prefix = wr.label.split(",", 1)[0].strip() if wr.label else ""
                display_label = (
                    f"{row_prefix} - {concept_part}" if row_prefix else concept_part
                )
            else:
                display_label = wr.label
                if not display_label or _is_date_only_label(display_label):
                    display_label = concept_to_display(f.local_name)
                    label_synthesis_misses.append(f.local_name)

            section = wr.section
            if section == Section.UNCLASSIFIED:
                section = classify_section(f.local_name, key.stmt_type)

            row_type = "memo" if (is_memo_fact or wr.row_type == "memo") else wr.row_type
            rule_id: str | None = None
            canonical: str | None = None
            sign_convention: str = "as_reported"
            # Subtotal rows skip the library lookup (fuzzy match would route
            # them to a sibling line-item canonical and double-count). Reconcile
            # picks them up via row_type="subtotal".
            # Memo rows also skip — synthesized labels ("Series A convertible
            # preferred shares - Preferred Stock Par Or Stated Value Per Share")
            # would fuzzy-match real canonicals and pollute downstream rule_id
            # assignment. Reconcile's _memo passthrough handles unmatched memos.
            if row_type == "memo":
                pass
            elif library_index is not None:
                section_str = section.value if hasattr(section, "value") else section
                # Derive subsection_context from concept type so the EPS vs
                # shares-outstanding alias collision (`basic` / `diluted` map
                # to both GEN-IS-016/017 and GEN-IS-018/019) resolves cleanly.
                if _is_per_share_concept(f.local_name):
                    subsection_ctx = "eps"
                elif _is_share_count_concept(f.local_name):
                    subsection_ctx = "shares_outstanding"
                else:
                    subsection_ctx = None
                # Strict-mode lookup (exact alias match only) prevents subtotal
                # rows from fuzzy-matching sibling line-item canonicals (the
                # "Total current liabilities" 88%-fuzz "Other current liabilities"
                # collision risk on the BS). On the IS, that collision risk
                # doesn't apply — IS canonicals (Pre-Tax Income, Operating Income,
                # Net Income, etc.) are semantically distinct and their aliases
                # don't 85%+ fuzz against unrelated siblings. Dropping IS strict
                # lets filer-rendered totalLabel rows whose label varies slightly
                # from the alias list (e.g. CELH's "Net income before income
                # taxes" vs alias "income before income taxes") still route via
                # fuzzy match to the correct subtotal canonical.
                strict = (row_type == "subtotal"
                          and key.stmt_type != StatementType.INCOME_STATEMENT)
                entry = match_raw_item(
                    raw_filing_label=display_label,
                    concept=f.local_name,
                    subsection_context=subsection_ctx,
                    section=section_str,
                    statement_type=key.stmt_type,
                    index=library_index,
                    strict=strict,
                    concept_index=concept_index,
                )
                # Subtotal-row library matches: SUBTOTAL canonicals keep the
                # subtotal row_type. LINE-ITEM canonicals promote the row to
                # line_item — this catches sub-section rollups that ARE the
                # model's primary row (PG's "Total inventories" sums Materials
                # / WIP / FG memo components and IS the BS Inventories line).
                # Without the promotion, the row stays canonical=None and the
                # workbook line is missing entirely.
                if entry is not None and row_type == "subtotal":
                    if entry.get("row_type") != "subtotal":
                        row_type = "line_item"
                if entry is not None:
                    rule_id = entry["rule_id"]
                    canonical = entry["model_label"]
                    if entry.get("row_type"):
                        row_type = entry["row_type"]
                    elif entry.get("memo"):
                        row_type = "memo"
                    if entry.get("sign_convention"):
                        sign_convention = entry["sign_convention"]
                    # Walker section (rendered location in primary table) is
                    # authoritative — reflects the filer's actual rendering
                    # which is what validate ties to. Library `filing_section`
                    # only fills in when walker said UNCLASSIFIED. Layout-time
                    # reclassification (e.g. fold mezzanine into equity for
                    # workbook presentation) is a model-write concern, not
                    # an extract concern.
                    if section == Section.UNCLASSIFIED and entry.get("filing_section"):
                        section = Section(entry["filing_section"])

            line_items.append(RawLineItem(
                raw_filing_label=display_label,
                canonical_label=canonical,
                ledger_rule_id=rule_id,
                value=value_in_stmt_unit,
                raw_numeric_text=f.raw_value,
                row_type=row_type,
                section=section,
                sign_convention=sign_convention,
                citation=citation,
            ))

        statement = Statement(
            statement_type=key.stmt_type,
            period=period,
            unit=stmt_unit,
            raw_unit_phrase=raw_phrase,
            unit_detection_source="explicit_header",  # XBRL scale is explicit
            unit_detection_confidence=confidence,
            share_unit=Unit.ACTUAL,
            eps_unit=Unit.ACTUAL,
            currency="USD",
            line_items=line_items,
        )
        statements.append(statement)

    # Order: BS -> IS -> CF, newest period first within each type
    order = {StatementType.BALANCE_SHEET: 0, StatementType.INCOME_STATEMENT: 1, StatementType.CASH_FLOW: 2}
    statements.sort(key=lambda s: (order[s.statement_type], -s.period.period_end_date.toordinal()))

    filing_type = FILING_TYPE_MAP.get(meta["form"])
    if filing_type is None:
        raise SystemExit(f"Unsupported form {meta['form']!r}; only 10-K/10-Q/8-K handled.")
    filing_date_val = date.fromisoformat(meta["filing_date"])

    # Detect NCI presence structurally. Match only concepts that have NCI
    # as their semantic subject — naive `contains "NoncontrollingInterest"`
    # over-matches because the FASB pre-tax concept name
    # `IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest`
    # contains the word "NoncontrollingInterest" in a "BEFORE NCI" sense
    # (used by every filer, NCI or not). Likewise `AttributableToParent`
    # appears on mezzanine/temporary-equity concepts unrelated to NCI.
    #
    # Reliable NCI-only patterns:
    #   - `us-gaap:MinorityInterest` (BS line-item, classic NCI tag)
    #   - `*AttributableToNoncontrollingInterest*` (NCI is the subject)
    #   - `*IncludingPortionAttributableToNoncontrollingInterest*` (subtotal
    #      explicitly including NCI — `StockholdersEquityIncluding...`,
    #      `ComprehensiveIncomeIncluding...`, etc.)
    #   - `*IncludingNoncontrollingInterest*` (a few legacy variants)
    #
    # PG (NCI filer) → all 7 of these patterns appear; CELH (single-NI) → 0.
    nci_concepts = root.xpath(
        "//ix:nonFraction["
        "@name='us-gaap:MinorityInterest' "
        "or contains(@name, 'AttributableToNoncontrollingInterest') "
        "or contains(@name, 'IncludingPortionAttributableToNoncontrollingInterest') "
        "or contains(@name, 'IncludingNoncontrollingInterest')"
        "]",
        namespaces=NS,
    )
    is_nci_filer = bool(nci_concepts)

    return RawFiling(
        ticker=ticker,
        filing_type=filing_type,
        filing_date=filing_date_val,
        source_path=htm_path,
        statements=statements,
        is_nci_filer=is_nci_filer,
        extraction_metadata={
            "extractor": "financials-extract/ixbrl-htm",
            "accession": meta["accession"],
            "report_date": meta["report_date"],
            "quarter_label": meta["quarter"],
            "primary_tables_found": [code for code, _t in primary_tables],
            "fact_counts": {
                "consolidated_used": sum(len(p) for p in buckets.values()),
                "label_synthesis_misses": len(label_synthesis_misses),
            },
            "label_synthesis_concepts": sorted(set(label_synthesis_misses)),
        },
    )
