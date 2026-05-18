"""financials-extract — XBRL-XML path.

Builds a RawFiling from a standalone XBRL *instance* document plus the
*presentation* and *label* linkbases, instead of from inline-iXBRL HTM tables.

Why this path exists
--------------------
`ixbrl_path` reads facts from `<ix:nonFraction>` tags embedded in the primary
HTM and recovers statement structure by walking HTML tables. That fails for:

  * **Pre-iXBRL filings** — CELH was a non-accelerated filer through fiscal
    2020; filings before the 2021-Q2 10-Q carry ZERO `<ix:>` tags. Their XBRL
    lives in a separate instance file (`{ticker}-{date}.xml`).
  * **iXBRL filings whose HTM table layout defeats `find_primary_tables`**
    (CELH's 2021/2022 10-Ks). The SEC still generates a standalone instance
    (`{ticker}-{date}_htm.xml`) for these.

Both cases are handled here uniformly: the *presentation linkbase* gives the
statement structure (which concepts, in what order, which are totals); the
*label linkbase* gives the filer's row wording (`raw_filing_label`); the
*instance* gives the fact values and periods. No HTML scraping.

Output is the same `RawFiling` shape as `ixbrl_path.build_raw_filing`, so
reconcile / validate / model-write consume it unchanged.

Scale note: an XBRL instance always stores actual (un-scaled) values — the
"in thousands" / "in millions" presentation choice is not in the instance.
Statements are therefore emitted with `unit=Unit.ACTUAL`; model-write's
`collect_writes` normalizes every value to the workbook's thousands scale.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
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

# Reuse the proven helpers from the iXBRL path rather than re-deriving them.
from . import ixbrl_path as _ix

# ============================================================================
# Constants
# ============================================================================

_XBRLI = "http://www.xbrl.org/2003/instance"
_LINK = "http://www.xbrl.org/2003/linkbase"
_XLINK = "http://www.w3.org/1999/xlink"

_CACHE_ROOT = Path(__file__).resolve().parent.parent / ".cache" / "ixbrl_reports"

# Presentation-link role classification. A role URI's last path segment is
# matched case-insensitively. Statement detection is structural (the filer's
# own role taxonomy), not HTML-title scraping.
_ROLE_BS = re.compile(r"balancesheet|financialposition", re.I)
_ROLE_IS = re.compile(r"incomestatement|statementsofoperation|statementofoperation|"
                      r"resultsofoperation", re.I)
_ROLE_CF = re.compile(r"cashflow", re.I)
# Roles that look like a primary statement by keyword but must be excluded.
_ROLE_EXCLUDE = re.compile(r"parenthetical|comprehensive|stockholdersequity|"
                           r"shareholdersequity|changesinequity|equitytype|"
                           r"\bnote\b|disclosure|policies|detail|table", re.I)

# us-gaap standard label roles (last path segment).
_LABEL_ROLE_STANDARD = "label"

# ----------------------------------------------------------------------------
# Section assignment by subtotal transition
# ----------------------------------------------------------------------------
#
# A primary statement has no per-row section tag in XBRL. The filer's section
# structure is instead implied by ORDER + the standardized subtotal concepts.
# Walking the presentation-ordered rows, the "current section" advances each
# time a known subtotal concept closes a block. Keying the transition on the
# us-gaap concept's identity (not label text) keeps this a structural signal.

_SECTION_START = {
    StatementType.BALANCE_SHEET: Section.CURRENT_ASSETS,
    StatementType.INCOME_STATEMENT: Section.REVENUE_COST,
    StatementType.CASH_FLOW: Section.OPERATING,
}

# Per-statement: concept local-name -> section that takes effect for the rows
# AFTER it. Scoped by statement type because `NetIncomeLoss` is the closing
# subtotal on the IS but the OPENING row on the CF (indirect method) — a flat
# map would mis-transition the CF's whole operating block.
_SECTION_TRANSITIONS: dict[StatementType, dict[str, Section]] = {
    StatementType.BALANCE_SHEET: {
        "AssetsCurrent": Section.NON_CURRENT_ASSETS,
        "Assets": Section.CURRENT_LIABILITIES,
        "LiabilitiesCurrent": Section.NON_CURRENT_LIABILITIES,
        "Liabilities": Section.EQUITY,
    },
    StatementType.INCOME_STATEMENT: {
        "GrossProfit": Section.OPERATING_EXPENSES,
        "OperatingIncomeLoss": Section.NON_OPERATING,
        "NetIncomeLoss": Section.POST_NI_DEDUCTION,
        "ProfitLoss": Section.POST_NI_DEDUCTION,
    },
    StatementType.CASH_FLOW: {
        "NetCashProvidedByUsedInOperatingActivities": Section.INVESTING,
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations": Section.INVESTING,
        "NetCashProvidedByUsedInInvestingActivities": Section.FINANCING,
        "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations": Section.FINANCING,
        "NetCashProvidedByUsedInFinancingActivities": Section.CASH_OTHER,
        "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations": Section.CASH_OTHER,
    },
}

# Pre-tax subtotal concepts are long and vary by taxonomy year — match by
# prefix. The row after pre-tax income belongs to the TAX section.
_PRETAX_CONCEPT_PREFIX = "IncomeLossFromContinuingOperationsBeforeIncomeTax"

# A statement period with fewer line items than this is stray-fact noise
# (a handful of concepts tagged in an off-cycle context), not a rendered
# statement. Real primary statements carry 15+ rows.
_MIN_STATEMENT_ROWS = 5


def _assign_sections(local_names: list[str], stmt_type: StatementType) -> list[Section]:
    """Walk presentation-ordered concept names, returning each row's Section.

    The subtotal row itself keeps the section it closes; the transition takes
    effect for the rows after it. EPS / share-count concepts are forced to
    Section.EPS regardless of position (they trail Net Income)."""
    current = _SECTION_START.get(stmt_type, Section.UNCLASSIFIED)
    transitions = _SECTION_TRANSITIONS.get(stmt_type, {})
    out: list[Section] = []
    for name in local_names:
        if stmt_type == StatementType.INCOME_STATEMENT and _is_eps_concept(name):
            out.append(Section.EPS)
            continue
        out.append(current)
        nxt = transitions.get(name)
        if nxt is None and stmt_type == StatementType.INCOME_STATEMENT \
                and name.startswith(_PRETAX_CONCEPT_PREFIX):
            nxt = Section.TAX
        if nxt is not None:
            current = nxt
    return out


def _is_eps_concept(local_name: str) -> bool:
    return _ix._is_per_share_concept(local_name) or _ix._is_share_count_concept(local_name)


# ============================================================================
# XBRL file discovery
# ============================================================================

def _cache_dir_for(meta: dict) -> Path:
    """Cache dir holding this filing's XBRL XML: keyed by accession (no dashes)."""
    accession_nodash = meta["accession"].replace("-", "")
    return _CACHE_ROOT / accession_nodash


def _find_xbrl_files(cache_dir: Path) -> tuple[Path, Path, Path]:
    """Locate (instance, presentation_linkbase, label_linkbase) in cache_dir.

    Instance: `*_pre.xml` / `*_lab.xml` / `*_cal.xml` / `*_def.xml` / `*.xsd`
    are linkbases/schema; the instance is the remaining `*.xml` — either the
    pre-iXBRL `{ticker}-{date}.xml` or the SEC-generated `{ticker}-{date}_htm.xml`.
    """
    if not cache_dir.is_dir():
        raise SystemExit(
            f"XBRL cache dir not found: {cache_dir}. Fetch the filing's "
            f"instance + _pre.xml + _lab.xml into this directory first."
        )
    pre = next(iter(cache_dir.glob("*_pre.xml")), None)
    lab = next(iter(cache_dir.glob("*_lab.xml")), None)
    if pre is None or lab is None:
        raise SystemExit(
            f"Missing presentation/label linkbase in {cache_dir} "
            f"(_pre.xml={pre}, _lab.xml={lab})."
        )
    linkbase_suffixes = ("_pre.xml", "_lab.xml", "_cal.xml", "_def.xml", "_ref.xml")
    instance: Path | None = None
    for p in sorted(cache_dir.glob("*.xml")):
        if any(p.name.endswith(s) for s in linkbase_suffixes):
            continue
        instance = p
        break
    if instance is None:
        raise SystemExit(f"No XBRL instance document found in {cache_dir}.")
    return instance, pre, lab


# ============================================================================
# Instance parsing — contexts, units, facts
# ============================================================================

@dataclass(frozen=True)
class _Ctx:
    kind: str            # "instant" | "duration"
    start: date | None
    end: date
    has_segment: bool


@dataclass(frozen=True)
class _Fact:
    concept_id: str      # "us-gaap_Assets" — matches presentation loc concept ids
    local_name: str      # "Assets"
    context_ref: str
    unit_ref: str | None
    value: Decimal
    raw_text: str


def _parse_contexts(root) -> dict[str, _Ctx]:
    out: dict[str, _Ctx] = {}
    for c in root.findall(f"{{{_XBRLI}}}context"):
        cid = c.get("id")
        per = c.find(f"{{{_XBRLI}}}period")
        if per is None:
            continue
        inst = per.find(f"{{{_XBRLI}}}instant")
        ent = c.find(f"{{{_XBRLI}}}entity")
        has_seg = ent is not None and ent.find(f"{{{_XBRLI}}}segment") is not None
        if inst is not None:
            d = _ix._parse_date(inst.text.strip())
            out[cid] = _Ctx("instant", None, d, has_seg)
        else:
            sd = per.find(f"{{{_XBRLI}}}startDate")
            ed = per.find(f"{{{_XBRLI}}}endDate")
            if sd is None or ed is None:
                continue
            out[cid] = _Ctx("duration",
                             _ix._parse_date(sd.text.strip()),
                             _ix._parse_date(ed.text.strip()),
                             has_seg)
    return out


def _parse_facts(root) -> dict[str, list[_Fact]]:
    """Return concept_id -> list of numeric facts (segment-free or not; the
    caller filters by context)."""
    ns_to_prefix = {v: k for k, v in root.nsmap.items() if k}
    facts: dict[str, list[_Fact]] = defaultdict(list)
    for el in root.iter():
        tag = el.tag
        if not isinstance(tag, str) or tag.startswith("{" + _XBRLI + "}"):
            continue
        ctx_ref = el.get("contextRef")
        if ctx_ref is None:
            continue
        qn = etree.QName(el)
        prefix = ns_to_prefix.get(qn.namespace)
        if prefix is None or prefix in ("dei", "xbrli", "link", "xlink"):
            continue
        text = (el.text or "").strip()
        if text == "":
            continue
        try:
            value = Decimal(text)
        except (InvalidOperation, ValueError):
            continue  # non-numeric fact (DocumentType etc.)
        concept_id = f"{prefix}_{qn.localname}"
        facts[concept_id].append(_Fact(
            concept_id=concept_id,
            local_name=qn.localname,
            context_ref=ctx_ref,
            unit_ref=el.get("unitRef"),
            value=value,
            raw_text=text,
        ))
    return facts


# ============================================================================
# Label linkbase
# ============================================================================

def _parse_labels(lab_root) -> dict[str, dict[str, str]]:
    """concept_id -> {label_role_last_segment: text}."""
    out: dict[str, dict[str, str]] = defaultdict(dict)
    for ll in lab_root.iter(f"{{{_LINK}}}labelLink"):
        # loc: xlink:label -> concept_id (from href fragment)
        loc_to_concept: dict[str, str] = {}
        for loc in ll.findall(f"{{{_LINK}}}loc"):
            href = loc.get(f"{{{_XLINK}}}href", "")
            concept_id = href.split("#")[-1]
            loc_to_concept[loc.get(f"{{{_XLINK}}}label")] = concept_id
        # arc: loc-label -> label-label
        loclbl_to_lbllbl: dict[str, list[str]] = defaultdict(list)
        for arc in ll.findall(f"{{{_LINK}}}labelArc"):
            loclbl_to_lbllbl[arc.get(f"{{{_XLINK}}}from")].append(
                arc.get(f"{{{_XLINK}}}to"))
        # label: label-label -> (role, text)
        lbllbl_to_roletext: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for lb in ll.findall(f"{{{_LINK}}}label"):
            role = (lb.get(f"{{{_XLINK}}}role") or "").rsplit("/", 1)[-1]
            lbllbl_to_roletext[lb.get(f"{{{_XLINK}}}label")].append(
                (role, (lb.text or "").strip()))
        for loclbl, concept_id in loc_to_concept.items():
            for lbllbl in loclbl_to_lbllbl.get(loclbl, []):
                for role, text in lbllbl_to_roletext.get(lbllbl, []):
                    if text:
                        out[concept_id][role] = text
    return out


# ============================================================================
# Presentation linkbase
# ============================================================================

@dataclass
class _PresRow:
    concept_id: str
    preferred_role: str   # last path segment of preferredLabel, or ""
    order: float


def _classify_role(role_uri: str) -> StatementType | None:
    """Map a presentationLink role URI to a primary statement type, or None."""
    seg = role_uri.rsplit("/", 1)[-1]
    if _ROLE_EXCLUDE.search(seg):
        return None
    if _ROLE_BS.search(seg):
        return StatementType.BALANCE_SHEET
    if _ROLE_CF.search(seg):
        return StatementType.CASH_FLOW
    if _ROLE_IS.search(seg):
        return StatementType.INCOME_STATEMENT
    return None


def _parse_presentation(pre_root) -> list[tuple[StatementType, list[_PresRow]]]:
    """Return [(statement_type, ordered presentation rows)] for primary roles.

    Rows are a depth-first flatten of the presentation tree, ordered by the
    `order` attribute. Abstract grouping concepts are dropped (they carry no
    fact); their position still orders their children."""
    results: list[tuple[StatementType, list[_PresRow]]] = []
    for plink in pre_root.iter(f"{{{_LINK}}}presentationLink"):
        role_uri = plink.get(f"{{{_XLINK}}}role", "")
        stmt_type = _classify_role(role_uri)
        if stmt_type is None:
            continue
        # loc: xlink:label -> concept_id
        loc_to_concept: dict[str, str] = {}
        for loc in plink.findall(f"{{{_LINK}}}loc"):
            href = loc.get(f"{{{_XLINK}}}href", "")
            loc_to_concept[loc.get(f"{{{_XLINK}}}label")] = href.split("#")[-1]
        # arcs: parent loc-label -> [(child loc-label, order, preferredLabel)]
        children: dict[str, list[tuple[str, float, str]]] = defaultdict(list)
        all_to: set[str] = set()
        all_from: set[str] = set()
        for arc in plink.findall(f"{{{_LINK}}}presentationArc"):
            frm = arc.get(f"{{{_XLINK}}}from")
            to = arc.get(f"{{{_XLINK}}}to")
            try:
                order = float(arc.get("order") or 0)
            except ValueError:
                order = 0.0
            pref = (arc.get("preferredLabel") or "").rsplit("/", 1)[-1]
            children[frm].append((to, order, pref))
            all_to.add(to)
            all_from.add(frm)
        roots = [lbl for lbl in all_from if lbl not in all_to]
        rows: list[_PresRow] = []
        seen: set[str] = set()

        def _walk(loc_label: str, preferred: str) -> None:
            if loc_label in seen:
                return
            seen.add(loc_label)
            concept_id = loc_to_concept.get(loc_label, loc_label)
            # Abstract concepts are headers — no fact; skip the row, keep order.
            if not concept_id.endswith("Abstract"):
                rows.append(_PresRow(concept_id, preferred, 0.0))
            for child_lbl, _order, child_pref in sorted(
                children.get(loc_label, []), key=lambda t: t[1]
            ):
                _walk(child_lbl, child_pref)

        for r in sorted(roots):
            _walk(r, "")
        if rows:
            results.append((stmt_type, rows))
    return results


# ============================================================================
# Build
# ============================================================================

def _row_label(labels: dict[str, str], preferred_role: str, local_name: str) -> str:
    """Pick the filer's row wording: preferredLabel role, else standard, else
    terse, else a CamelCase-split of the concept name."""
    for role in (preferred_role, _LABEL_ROLE_STANDARD, "terseLabel", "verboseLabel"):
        if role and labels.get(role):
            return labels[role]
    return _ix.concept_to_display(local_name)


def build_raw_filing(
    htm_path: Path,
    ticker: str | None = None,
    library_path: Path | None = None,
) -> RawFiling:
    """Build a RawFiling from the filing's standalone XBRL instance + linkbases.

    `htm_path` is the primary HTM (used only for its `.meta.json` sidecar and
    as the citation `source_path`); facts come from the cached XBRL XML."""
    meta = _ix.load_meta(htm_path)
    ticker = (ticker or meta["ticker"]).upper()

    cache_dir = _cache_dir_for(meta)
    instance_path, pre_path, lab_path = _find_xbrl_files(cache_dir)

    parser = etree.XMLParser(recover=True, huge_tree=True)
    inst_root = etree.fromstring(instance_path.read_bytes(), parser)
    pre_root = etree.fromstring(pre_path.read_bytes(), parser)
    lab_root = etree.fromstring(lab_path.read_bytes(), parser)

    contexts = _parse_contexts(inst_root)
    facts_by_concept = _parse_facts(inst_root)
    labels_by_concept = _parse_labels(lab_root)
    presentation = _parse_presentation(pre_root)

    # Filing metadata — fiscal-year / quarter resolution (mirrors ixbrl_path).
    filing_end = date.fromisoformat(meta["report_date"])
    q_label = meta.get("quarter", "")
    m = re.match(r"(\d{4})-Q([1-4])", q_label)
    filing_fq: int | None = int(m.group(2)) if m else None
    if filing_fq is None:
        fye_month = filing_end.month
    else:
        fye_month = ((filing_end.month - filing_fq * 3 - 1) % 12) + 1

    library_index = concept_index = None
    if library_path is not None:
        library = load_generic_library(library_path)
        library_index = build_generic_index(library)
        concept_index = build_concept_index(library)

    statements: list[Statement] = []

    for stmt_type, pres_rows in presentation:
        want_kind = "instant" if stmt_type == StatementType.BALANCE_SHEET else "duration"

        # Collect every period (segment-free) that this statement's concepts
        # report a fact in. One Statement per period column.
        period_facts: dict[tuple, list[tuple[_PresRow, _Fact]]] = defaultdict(list)
        for prow in pres_rows:
            for f in facts_by_concept.get(prow.concept_id, []):
                ctx = contexts.get(f.context_ref)
                if ctx is None or ctx.has_segment:
                    continue
                if ctx.kind != want_kind:
                    continue
                key = (ctx.kind, ctx.start, ctx.end)
                period_facts[key].append((prow, f))

        for (kind, p_start, p_end), pairs in period_facts.items():
            weeks = (round((p_end - p_start).days / 7)
                     if kind == "duration" and p_start else None)
            is_full_year = kind == "duration" and weeks is not None and 48 <= weeks <= 54
            period_fy = p_end.year if p_end.month <= fye_month else p_end.year + 1
            if stmt_type == StatementType.BALANCE_SHEET:
                fq = _ix.fiscal_quarter_from_key(
                    _ix.PeriodKey(stmt_type, kind, p_start, p_end),
                    filing_fq, filing_end, fye_month)
            elif filing_fq is None or is_full_year:
                fq = None
            else:
                fq = _ix.fiscal_quarter_from_key(
                    _ix.PeriodKey(stmt_type, kind, p_start, p_end),
                    filing_fq, filing_end, fye_month)

            period = Period(
                fiscal_year=period_fy,
                fiscal_quarter=fq,
                period_end_date=p_end,
                raw_period_label=(
                    f"as of {p_end.isoformat()}" if kind == "instant"
                    else f"{p_start.isoformat()} to {p_end.isoformat()} ({weeks}wk)"
                ),
                period_length_weeks=weeks,
                is_comparative=(p_end != filing_end),
            )

            sections = _assign_sections([f.local_name for _p, f in pairs], stmt_type)

            line_items: list[RawLineItem] = []
            for (prow, f), section in zip(pairs, sections):
                negate = "negated" in prow.preferred_role
                value = -f.value if negate else f.value

                labels = labels_by_concept.get(f.concept_id, {})
                display_label = _row_label(labels, prow.preferred_role, f.local_name)

                row_type = "subtotal" if prow.preferred_role.endswith(
                    "totalLabel") else "line_item"

                citation = Citation(
                    source_path=htm_path,
                    page=1,
                    line_hint=f"{f.concept_id.replace('_', ':', 1)} | "
                              f"ctx:{kind}:{p_end.isoformat()}",
                    note=f"XBRL XML | {_ix.STATEMENT_TYPE_TO_CODE.get(stmt_type, '?')}",
                )

                rule_id: str | None = None
                canonical: str | None = None
                sign_convention = "as_reported"

                if row_type != "memo" and library_index is not None:
                    if _ix._is_per_share_concept(f.local_name):
                        subsection_ctx = "eps"
                    elif _ix._is_share_count_concept(f.local_name):
                        subsection_ctx = "shares_outstanding"
                    else:
                        subsection_ctx = None
                    strict = (row_type == "subtotal"
                              and stmt_type != StatementType.INCOME_STATEMENT)
                    entry = match_raw_item(
                        raw_filing_label=display_label,
                        concept=f.local_name,
                        subsection_context=subsection_ctx,
                        section=section.value if hasattr(section, "value") else section,
                        statement_type=stmt_type,
                        index=library_index,
                        strict=strict,
                        concept_index=concept_index,
                    )
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
                        if section == Section.UNCLASSIFIED and entry.get("filing_section"):
                            section = Section(entry["filing_section"])

                line_items.append(RawLineItem(
                    raw_filing_label=display_label,
                    canonical_label=canonical,
                    ledger_rule_id=rule_id,
                    value=value,
                    raw_numeric_text=f.raw_text,
                    row_type=row_type,
                    section=section,
                    sign_convention=sign_convention,
                    citation=citation,
                ))

            if len(line_items) < _MIN_STATEMENT_ROWS:
                continue  # stray-fact noise, not a rendered statement
            statements.append(Statement(
                statement_type=stmt_type,
                period=period,
                unit=Unit.ACTUAL,            # XBRL instance values are un-scaled
                raw_unit_phrase="XBRL instance (actual)",
                unit_detection_source="explicit_header",
                unit_detection_confidence=1.0,
                share_unit=Unit.ACTUAL,
                eps_unit=Unit.ACTUAL,
                currency="USD",
                line_items=line_items,
            ))

    # Order: BS -> IS -> CF, newest period first within each type.
    order = {StatementType.BALANCE_SHEET: 0,
             StatementType.INCOME_STATEMENT: 1,
             StatementType.CASH_FLOW: 2}
    statements.sort(key=lambda s: (order[s.statement_type],
                                   -s.period.period_end_date.toordinal()))

    filing_type = _ix.FILING_TYPE_MAP.get(meta["form"])
    if filing_type is None:
        raise SystemExit(f"Unsupported form {meta['form']!r}; only 10-K/10-Q/8-K handled.")

    return RawFiling(
        ticker=ticker,
        filing_type=filing_type,
        filing_date=date.fromisoformat(meta["filing_date"]),
        source_path=htm_path,
        statements=statements,
        is_nci_filer=False,
        extraction_metadata={
            "extractor": "financials-extract/xbrl-xml",
            "accession": meta["accession"],
            "report_date": meta["report_date"],
            "quarter_label": q_label,
            "instance_file": instance_path.name,
            "primary_roles_found": sorted({
                _ix.STATEMENT_TYPE_TO_CODE[st] for st, _ in presentation
            }),
        },
    )
