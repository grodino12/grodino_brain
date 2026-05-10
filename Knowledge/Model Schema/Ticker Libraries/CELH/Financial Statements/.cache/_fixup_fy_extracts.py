"""One-off: re-extract CELH 2021-FY and 2022-FY 10-Ks using the presentation
linkbase for statement classification, bypassing the broken HTM-title walker
in ixbrl_path.find_primary_tables.

The presentation linkbase's role URIs (e.g. Role_StatementConsolidatedBalanceSheets)
are a structural signal — each role declares a concept set, which we map to
BS/IS/CF/SE. We then classify each iXBRL table by its dominant concept group
and replace ixbrl_path.find_primary_tables with this concept-based variant
before calling build_raw_filing.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path
from collections import Counter

import lxml.etree as et

SKILL = Path(r"C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\.claude\skills\financials-extract\scripts")
sys.path.insert(0, str(SKILL))
sys.path.insert(0, r"C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\financials-schema")

import ixbrl_path  # noqa

NS_LINK = {
    "link": "http://www.xbrl.org/2003/linkbase",
    "xlink": "http://www.w3.org/1999/xlink",
}
IX_NS = "http://www.xbrl.org/2013/inlineXBRL"

ROLE_TO_STMT = [
    (re.compile(r"BalanceSheet", re.I), "BS"),
    (re.compile(r"StatementsOfOperations|StatementsOfIncome|StatementsOfEarnings", re.I), "IS"),
    (re.compile(r"CashFlow", re.I), "CF"),
    (re.compile(r"StockholdersEquity|ShareholdersEquity", re.I), "SE"),
    (re.compile(r"ComprehensiveIncome", re.I), "CI"),
]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "rodinogj12@gmail.com"})
    with urllib.request.urlopen(req) as r:
        return r.read()


def build_concept_to_stmt(archive_base_url: str) -> dict[str, str]:
    # Find _pre.xml under the archive
    idx = fetch(archive_base_url).decode("utf-8", errors="ignore")
    pre_match = re.search(r'href="([^"]+_pre\.xml)"', idx)
    if not pre_match:
        raise RuntimeError(f"No _pre.xml found at {archive_base_url}")
    pre_url = "https://www.sec.gov" + pre_match.group(1) if pre_match.group(1).startswith("/") else pre_match.group(1)
    pre_bytes = fetch(pre_url)
    tree = et.fromstring(pre_bytes)
    concept_to_stmt: dict[str, str] = {}
    for link in tree.iter("{http://www.xbrl.org/2003/linkbase}presentationLink"):
        role_uri = link.get("{http://www.w3.org/1999/xlink}role", "")
        role_tail = role_uri.split("/role/")[-1] if "/role/" in role_uri else role_uri
        stmt = None
        # Only classify primary statements: role must start with "Role_Statement"
        # or "Statement" (filer-specific prefix conventions vary). Skip
        # Parenthetical/Notes/Details/Tables roles.
        if "Parenthetical" in role_tail or "Details" in role_tail or "Tables" in role_tail or "Disclosure" in role_tail:
            continue
        if not (role_tail.startswith("Role_Statement") or role_tail.startswith("Statement")):
            continue
        for rx, code in ROLE_TO_STMT:
            if rx.search(role_tail):
                stmt = code
                break
        if stmt is None or stmt in ("SE", "CI"):
            continue
        for loc in link.findall("link:loc", NS_LINK):
            h = loc.get("{http://www.w3.org/1999/xlink}href", "")
            if "#" not in h:
                continue
            concept = h.split("#")[1].replace("_", ":", 1)
            # First-wins: if a concept appears in multiple primary statements
            # (rare but happens with NetIncomeLoss appearing on both IS and CF),
            # keep its strongest signal. CF often has IS items rolled in at the
            # top, so prefer IS over CF; BS is unambiguous.
            existing = concept_to_stmt.get(concept)
            if existing is None:
                concept_to_stmt[concept] = stmt
            elif existing == "CF" and stmt == "IS":
                concept_to_stmt[concept] = "IS"
    return concept_to_stmt


def make_classifier(concept_to_stmt: dict[str, str]):
    """Return a `find_primary_tables`-compatible function classifying tables
    by the dominant statement assignment of their iXBRL concepts."""
    def find_primary_tables(root):
        pairings = []
        for el in root.iter():
            if et.QName(el).localname != "table":
                continue
            nfs = el.xpath(".//ix:nonFraction", namespaces={"ix": IX_NS})
            if len(nfs) < 5:
                continue
            rows = el.xpath(".//*[local-name()='tr']")
            if len(rows) < 3:
                continue
            votes = Counter()
            for nf in nfs:
                concept = nf.get("name", "")
                stmt = concept_to_stmt.get(concept)
                if stmt:
                    votes[stmt] += 1
            if not votes:
                continue
            top, top_count = votes.most_common(1)[0]
            # Require a clear majority (>= 60% of classified facts) so e.g. a
            # supplemental disclosure table near CF doesn't get misclassified
            # because it contains a couple BS lookups.
            total = sum(votes.values())
            if top_count / total < 0.6:
                continue
            if top in ("IS", "BS", "CF"):
                pairings.append((top, el))
        return pairings
    return find_primary_tables


def run(period: str, ticker_root: Path, library_path: Path):
    sources = Path(r"C:\Users\rodin\Desktop\Brain\Sources\CELH")
    htm = next((sources / period / "filings").glob("*.htm"))
    meta_path = htm.with_suffix(".meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    archive = meta["archive_base_url"]
    print(f"[{period}] fetching pre.xml from {archive}")
    c2s = build_concept_to_stmt(archive)
    bs = sum(1 for v in c2s.values() if v == "BS")
    is_ = sum(1 for v in c2s.values() if v == "IS")
    cf = sum(1 for v in c2s.values() if v == "CF")
    print(f"[{period}] concept→stmt map: BS={bs} IS={is_} CF={cf}")

    # Monkey-patch
    original = ixbrl_path.find_primary_tables
    ixbrl_path.find_primary_tables = make_classifier(c2s)
    try:
        raw = ixbrl_path.build_raw_filing(htm, ticker=meta["ticker"], library_path=library_path)
    finally:
        ixbrl_path.find_primary_tables = original

    # Post-filter: drop noise statements introduced by concept-overlap classification.
    # SE rollforward tables share BS concepts (CommonStock, RetainedEarnings, ...) so
    # the classifier votes them BS. Filter:
    #   - BS must be instant (BS proper). Duration BS = SE rollforward leak.
    #   - IS/CF in a 10-K must be full-year (>= 48 weeks). Sub-period IS = quarterly
    #     footnote cross-references that don't belong in the annual statement set.
    from datetime import timedelta
    is_annual = (raw.filing_type.value == "10-K") if hasattr(raw.filing_type, "value") else (str(raw.filing_type) == "FilingType.TEN_K" or "K" in str(raw.filing_type))
    keep = []
    dropped = []
    for s in raw.statements:
        per = s.period
        is_instant = per.raw_period_label.startswith("as of ")
        stype = s.statement_type.value if hasattr(s.statement_type, "value") else str(s.statement_type)
        if stype == "BS" and not is_instant:
            dropped.append((stype, per.raw_period_label, len(s.line_items)))
            continue
        # BS instant stubs: the SE rollforward emits 5-7-item instants for
        # quarterly intermediate balances (Q1/Q2/Q3) and prior-prior year
        # beginning balances. A real BS column has ~50+ items.
        if stype == "BS" and is_instant and len(s.line_items) < 20:
            dropped.append((stype, per.raw_period_label, len(s.line_items)))
            continue
        if is_annual and stype in ("IS", "CF") and not is_instant:
            # parse weeks from "yyyy-mm-dd to yyyy-mm-dd (Nwk)"
            m = re.search(r"\((\d+)wk\)", per.raw_period_label)
            if m and int(m.group(1)) < 48:
                dropped.append((stype, per.raw_period_label, len(s.line_items)))
                continue
        keep.append(s)
    raw.statements = keep
    print(f"[{period}] kept {len(keep)} / dropped {len(dropped)} stmts")
    for d in dropped:
        print(f"  drop: {d[0]} | {d[1]} | items={d[2]}")

    out = ticker_root / "Financial Statements" / ".cache" / f"raw_{period}.json"
    out.write_text(raw.model_dump_json(indent=2), encoding="utf-8")
    by_stmt = Counter()
    items = 0
    for s in raw.statements:
        by_stmt[s.statement_type.value] += 1
        items += len(s.line_items)
    print(f"[{period}] wrote {out.name}: {len(raw.statements)} stmts ({dict(by_stmt)}), {items} items")


if __name__ == "__main__":
    troot = Path(r"C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\Ticker Libraries\CELH")
    lib = Path(r"C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json")
    for p in ("2021-FY", "2022-FY"):
        run(p, troot, lib)
