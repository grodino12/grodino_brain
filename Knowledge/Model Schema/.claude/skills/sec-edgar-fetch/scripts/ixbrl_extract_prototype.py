"""Prototype iXBRL extractor for SEC filings.

Reads an inline-XBRL HTML file (the primary document of a 10-K or 10-Q) and
produces a structured list of tagged financial facts. Intended as a
replacement for the PDF-based financials-extract pipeline when the source is
an SEC EDGAR filing.

Usage:
    python ixbrl_extract_prototype.py <path-to-iXBRL.htm> [--segments] [--statement IS|BS|CF]

Output: grouped by statement (Income Statement / Balance Sheet / Cash Flow),
one row per (concept, period) tuple, consolidated-only by default.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import requests
from lxml import etree

SKILL_DIR = Path(__file__).resolve().parent
CACHE_DIR = SKILL_DIR / ".cache" / "reports"
USER_AGENT = "rodinogj12@gmail.com sec-edgar-fetch/1.0 (ixbrl extractor)"

# iXBRL / XBRL namespaces --------------------------------------------------------
NS = {
    "ix":    "http://www.xbrl.org/2013/inlineXBRL",
    "xbrli": "http://www.xbrl.org/2003/instance",
    "xbrldi": "http://xbrl.org/2006/xbrldi",
}

# Concept-prefix heuristics for statement classification. Not authoritative --
# the presentation linkbase is -- but good enough to show what an HTML-native
# extractor can produce without touching PDFs.
IS_PREFIXES = (
    "Revenues", "Revenue", "SalesRevenue", "CostOf", "GrossProfit",
    "OperatingExpenses", "OperatingIncome", "ResearchAndDevelopment",
    "SellingGeneralAndAdministrative", "NetIncome", "IncomeTax",
    "IncomeLoss", "InterestExpense", "InterestIncome", "EarningsPerShare",
    "WeightedAverageNumberOf", "ComprehensiveIncome",
)
BS_PREFIXES = (
    "Assets", "Liabilities", "StockholdersEquity", "Cash", "Inventory",
    "AccountsReceivable", "AccountsPayable", "Goodwill", "PropertyPlant",
    "LongTermDebt", "ShortTermBorrowings", "CommonStock", "RetainedEarnings",
    "TreasuryStock", "AdditionalPaidInCapital", "AccumulatedOther",
    "DeferredTax", "IntangibleAssets", "OperatingLease", "NotesPayable",
)
CF_PREFIXES = (
    "NetCashProvided", "NetCashUsed", "PaymentsFor", "PaymentsTo",
    "ProceedsFrom", "Depreciation", "Amortization", "ShareBased",
    "IncreaseDecrease", "CashAndCashEquivalentsPeriodIncreaseDecrease",
)


@dataclass
class Period:
    kind: str              # "instant" or "duration"
    start: str | None      # YYYY-MM-DD
    end: str | None        # YYYY-MM-DD (or the instant date)

    def label(self) -> str:
        if self.kind == "instant":
            return f"as of {self.end}"
        return f"{self.start} to {self.end}"


@dataclass
class Fact:
    concept: str           # "us-gaap:Revenues"
    local_name: str        # "Revenues"
    period: Period
    value: float           # scaled, signed
    raw_value: str         # as displayed in the doc
    unit: str              # "USD", "shares", "USD/shares"
    scale: int             # 0, 3, 6, 9
    decimals: str | None
    segments: list[str] = field(default_factory=list)


def parse_contexts(root) -> dict[str, tuple[Period, list[str]]]:
    """{contextRef: (Period, [segment_labels])}"""
    out = {}
    for ctx in root.iter(f"{{{NS['xbrli']}}}context"):
        cid = ctx.get("id")
        period_el = ctx.find(f"{{{NS['xbrli']}}}period")
        period: Period
        instant = period_el.find(f"{{{NS['xbrli']}}}instant")
        if instant is not None:
            period = Period(kind="instant", start=None, end=instant.text.strip())
        else:
            s = period_el.find(f"{{{NS['xbrli']}}}startDate").text.strip()
            e = period_el.find(f"{{{NS['xbrli']}}}endDate").text.strip()
            period = Period(kind="duration", start=s, end=e)

        segments = []
        seg_el = ctx.find(f".//{{{NS['xbrli']}}}segment")
        if seg_el is not None:
            for m in seg_el.iter(f"{{{NS['xbrldi']}}}explicitMember"):
                # dimension like "us-gaap:StatementBusinessSegmentsAxis"
                # member like "pg:BeautyMember"
                dim = m.get("dimension", "").split(":")[-1]
                mem = (m.text or "").strip().split(":")[-1]
                segments.append(f"{dim}={mem}")
        out[cid] = (period, segments)
    return out


def parse_units(root) -> dict[str, str]:
    """{unitRef: 'USD' | 'shares' | 'USD/shares' | ...}"""
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


def parse_facts(root, contexts: dict, units: dict) -> list[Fact]:
    facts: list[Fact] = []
    for el in root.iter(f"{{{NS['ix']}}}nonFraction"):
        concept = el.get("name", "")
        if not concept:
            continue
        ctx_id = el.get("contextRef")
        unit_id = el.get("unitRef", "")
        scale = int(el.get("scale", "0") or "0")
        sign = el.get("sign", "")
        decimals = el.get("decimals")
        raw = (el.text or "").strip()
        if not raw or ctx_id not in contexts:
            continue

        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        value *= 10 ** scale
        if sign == "-":
            value = -value

        period, segments = contexts[ctx_id]
        facts.append(Fact(
            concept=concept,
            local_name=concept.split(":")[-1],
            period=period,
            value=value,
            raw_value=raw,
            unit=units.get(unit_id, unit_id),
            scale=scale,
            decimals=decimals,
            segments=segments,
        ))
    return facts


def classify_by_prefix(local_name: str) -> str:
    """Heuristic fallback when the presentation linkbase isn't available."""
    for p in IS_PREFIXES:
        if local_name.startswith(p):
            return "IS"
    for p in BS_PREFIXES:
        if local_name.startswith(p):
            return "BS"
    for p in CF_PREFIXES:
        if local_name.startswith(p):
            return "CF"
    return "OTHER"


# --- Presentation linkbase (FilingSummary.xml + R{n}.htm) ---------------------

def _throttled_get(url: str) -> bytes:
    """SEC-polite GET — we don't hammer, this is a prototype."""
    import time as _t
    _t.sleep(0.2)
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.content


def fetch_with_cache(url: str, cache_path: Path) -> bytes:
    if cache_path.exists():
        return cache_path.read_bytes()
    data = _throttled_get(url)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(data)
    return data


# Map from FilingSummary ShortName patterns to canonical statement codes.
# Matched case-insensitive, longest-specific-match-wins.
STATEMENT_MATCHERS = [
    (re.compile(r"comprehensive income", re.I), "CI"),
    (re.compile(r"balance sheet", re.I), "BS"),
    (re.compile(r"financial position", re.I), "BS"),
    (re.compile(r"cash flow", re.I), "CF"),
    (re.compile(r"shareholders.?\s*equity", re.I), "SE"),
    (re.compile(r"stockholders.?\s*equity", re.I), "SE"),
    (re.compile(r"earnings|operations|income\b", re.I), "IS"),
]


def canonical_statement(short_name: str) -> str:
    """Map a FilingSummary ShortName (e.g. 'Consolidated Statements of Earnings')
    to a canonical code (IS/BS/CF/CI/SE). Parenthetical reports get the same
    code as their parent — they describe share counts, par values, etc.
    """
    for rx, code in STATEMENT_MATCHERS:
        if rx.search(short_name):
            return code
    return "OTHER"


_CONCEPT_ID_RE = re.compile(r"(us-gaap|dei|srt|ifrs-full|[a-z]{1,8})_([A-Za-z][A-Za-z0-9]+)")


def extract_concepts_from_report(html_bytes: bytes) -> set[str]:
    """Return the set of concept local names referenced in an R{n}.htm.

    Concepts appear as identifiers like `us-gaap_Revenues` in the rendered
    HTML (typical in data attributes / link targets). We match a generic
    `{prefix}_{LocalName}` pattern; the set gets filtered against the real
    facts later so noise is harmless.
    """
    text = html_bytes.decode("utf-8", errors="replace")
    out = set()
    for m in _CONCEPT_ID_RE.finditer(text):
        local = m.group(2)
        # Skip abstract placeholders and common non-concept tokens.
        if local.endswith("Abstract") or local.endswith("TextBlock"):
            continue
        out.add(local)
    return out


def build_concept_statement_map(
    archive_base_url: str,
    accession_nodash: str,
    include_details: bool = False,
) -> tuple[dict[str, str], dict[str, str]]:
    """Fetch FilingSummary.xml + the Statements R-files for a filing.

    Returns two maps:
      - {concept_local_name: statement_code}       IS/BS/CF/CI/SE/OTHER
      - {concept_local_name: short_name}           human-readable source
    """
    cache = CACHE_DIR / accession_nodash
    fs_bytes = fetch_with_cache(archive_base_url + "FilingSummary.xml", cache / "FilingSummary.xml")
    fs_root = etree.fromstring(fs_bytes)

    wanted_categories = {"Statements"}
    if include_details:
        wanted_categories.add("Details")

    concept_to_code: dict[str, str] = {}
    concept_to_source: dict[str, str] = {}

    for report in fs_root.iter("Report"):
        menu = (report.findtext("MenuCategory") or "").strip()
        if menu not in wanted_categories:
            continue
        short = (report.findtext("ShortName") or "").strip()
        html_file = (report.findtext("HtmlFileName") or "").strip()
        if not html_file:
            continue
        try:
            r_bytes = fetch_with_cache(archive_base_url + html_file, cache / html_file)
        except requests.HTTPError:
            continue
        concepts = extract_concepts_from_report(r_bytes)
        code = canonical_statement(short) if menu == "Statements" else "DETAIL"
        for c in concepts:
            # Primary-statement concepts win if a concept is referenced in both
            # a Statements and Details report — don't overwrite a real statement
            # classification with DETAIL.
            if c not in concept_to_code or (concept_to_code[c] == "DETAIL" and code != "DETAIL"):
                concept_to_code[c] = code
                concept_to_source[c] = short

    return concept_to_code, concept_to_source


def load_filing_meta(htm_path: Path) -> dict | None:
    meta_path = htm_path.with_suffix(".meta.json")
    if not meta_path.exists():
        return None
    return json.loads(meta_path.read_text(encoding="utf-8"))


def pretty_value(v: float, unit: str) -> str:
    if unit == "USD":
        if abs(v) >= 1e9:
            return f"${v/1e9:,.2f}B"
        if abs(v) >= 1e6:
            return f"${v/1e6:,.2f}M"
        if abs(v) >= 1e3:
            return f"${v/1e3:,.1f}K"
        return f"${v:,.2f}"
    if unit == "shares":
        return f"{v:,.0f} sh"
    if "/shares" in unit:
        return f"${v:,.4f}/sh"
    return f"{v:,.2f} {unit}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("htm", help="Path to iXBRL primary document (.htm)")
    ap.add_argument("--segments", action="store_true", help="Include segment-dimensioned facts")
    ap.add_argument("--statement", choices=["IS", "BS", "CF", "CI", "SE", "DETAIL", "OTHER"],
                    help="Filter to one statement code")
    ap.add_argument("--concept", help="Filter to a concept substring (case-insensitive)")
    ap.add_argument("--summary", action="store_true", help="Summary counts only")
    ap.add_argument("--no-linkbase", action="store_true",
                    help="Skip presentation linkbase lookup; fall back to prefix heuristics")
    ap.add_argument("--details", action="store_true",
                    help="Also pull Details reports (footnote disclosures) for classification")
    args = ap.parse_args()

    path = Path(args.htm)
    raw_bytes = path.read_bytes()
    # iXBRL files are XHTML-compliant; the XML parser preserves namespaces,
    # which the HTML parser does not.
    parser = etree.XMLParser(recover=True, huge_tree=True)
    root = etree.fromstring(raw_bytes, parser)

    contexts = parse_contexts(root)
    units = parse_units(root)
    facts = parse_facts(root, contexts, units)

    print(f"File:     {path.name}")
    print(f"Contexts: {len(contexts)}")
    print(f"Units:    {dict(list(units.items())[:10])}")
    print(f"Facts:    {len(facts)} total")

    # Presentation-linkbase-based classification (authoritative).
    concept_map: dict[str, str] = {}
    concept_source: dict[str, str] = {}
    if not args.no_linkbase:
        meta = load_filing_meta(path)
        if meta is None:
            print("  [warn] no .meta.json sidecar — falling back to prefix heuristics")
        else:
            accession_nodash = meta["accession"].replace("-", "")
            try:
                concept_map, concept_source = build_concept_statement_map(
                    meta["archive_base_url"], accession_nodash, include_details=args.details,
                )
                print(f"  [info] linkbase: {len(concept_map)} concepts classified from FilingSummary")
            except Exception as e:
                print(f"  [warn] linkbase lookup failed ({e}); falling back to prefix heuristics")

    def classify(name: str) -> str:
        if concept_map:
            return concept_map.get(name, "OTHER")
        return classify_by_prefix(name)

    # Filter to consolidated (no segment dimensions) unless --segments passed.
    if not args.segments:
        facts = [f for f in facts if not f.segments]

    # Optional filters
    if args.statement:
        facts = [f for f in facts if classify(f.local_name) == args.statement]
    if args.concept:
        needle = args.concept.lower()
        facts = [f for f in facts if needle in f.local_name.lower()]

    # Dedup: (concept, period, segments) — same fact may appear multiple times
    # when rendered across several tables in the HTML.
    seen = set()
    unique = []
    for f in facts:
        key = (f.concept, f.period.start, f.period.end, tuple(f.segments))
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    facts = unique

    # Group by statement
    by_stmt: dict[str, list[Fact]] = defaultdict(list)
    for f in facts:
        by_stmt[classify(f.local_name)].append(f)

    print(f"Consolidated unique facts (post-dedup): {len(facts)}")
    print("  " + "  ".join(f"{k}: {len(by_stmt[k])}" for k in ("IS", "CI", "BS", "CF", "SE", "DETAIL", "OTHER") if by_stmt[k]))

    if args.summary:
        return 0

    for stmt in ("IS", "CI", "BS", "CF", "SE", "DETAIL", "OTHER"):
        if not by_stmt[stmt]:
            continue
        print(f"\n=== {stmt} ===")
        # Sort: concept alphabetical, then period
        rows = sorted(by_stmt[stmt], key=lambda f: (f.local_name, f.period.end or "", f.period.start or ""))
        for f in rows:
            seg_str = f"  [{'; '.join(f.segments)}]" if f.segments else ""
            print(f"  {f.local_name:55s}  {f.period.label():30s}  {pretty_value(f.value, f.unit):>18s}{seg_str}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
