"""financials-reconcile CLI — maps RawFiling labels to Excel model rows via decisions ledger.

Under the Option-B architecture, generic-library lookup happens at extract time:
RawLineItem.canonical_label + ledger_rule_id are already set when a library
alias matched the filer's label. Reconcile's residual job is:

  1. Detect subtotals via is_subtotal_label (row_type + label heuristic).
  2. Apply per-ticker decisions_ledger overrides — ticker entries can override
     the canonical mapping set by extract (e.g. PG's ESOP reserve).
  3. Route every mapped item to a model_sheet based on (filing_type, statement_type):
     10-K → ANNL sheet family (ANNL P&L / BALANCE SHEET / CASH FLOW)
     10-Q → QTR  sheet family (QTR P&L  / QTR BS        / QTR CF)
  4. Flag any item whose canonical_label is still None as a novel.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from financials_schema import (
    FilingType,
    MappedFiling,
    MappedLineItem,
    NovelItem,
    RawFiling,
    RawLineItem,
    StatementType,
    build_generic_index,
    is_subtotal_label,
    keep_statement_for_pipeline,
    load_generic_library,
    nearest_matches,
    normalize_label,
    select_entry,
)


# ============================================================================
# Sheet-name routing: pure function of (filing_type, statement_type)
# ============================================================================

SHEET_NAME: dict[tuple[FilingType, StatementType], str] = {
    (FilingType.TEN_K,         StatementType.BALANCE_SHEET):    "BALANCE SHEET",
    (FilingType.TEN_K,         StatementType.INCOME_STATEMENT): "ANNL P&L",
    (FilingType.TEN_K,         StatementType.CASH_FLOW):        "CASH FLOW",
    (FilingType.EIGHT_K,       StatementType.BALANCE_SHEET):    "BALANCE SHEET",
    (FilingType.EIGHT_K,       StatementType.INCOME_STATEMENT): "ANNL P&L",
    (FilingType.EIGHT_K,       StatementType.CASH_FLOW):        "CASH FLOW",
    (FilingType.PRESS_RELEASE, StatementType.BALANCE_SHEET):    "BALANCE SHEET",
    (FilingType.PRESS_RELEASE, StatementType.INCOME_STATEMENT): "ANNL P&L",
    (FilingType.PRESS_RELEASE, StatementType.CASH_FLOW):        "CASH FLOW",
    (FilingType.TEN_Q,         StatementType.BALANCE_SHEET):    "QTR BS",
    (FilingType.TEN_Q,         StatementType.INCOME_STATEMENT): "QTR P&L",
    (FilingType.TEN_Q,         StatementType.CASH_FLOW):        "QTR CF",
}

STMT_TO_GROUP = {
    StatementType.BALANCE_SHEET:    "BS",
    StatementType.CASH_FLOW:        "CF",
    StatementType.INCOME_STATEMENT: "IS",
}


def _sheet_group(model_sheet: str) -> str:
    """BS / IS / CF group of a model_sheet string. Variant prefix (ANNL/QTR)
    is informational only — the actual sheet name on the workbook comes from
    SHEET_NAME[(filing_type, statement_type)] at reconcile time, so one ledger
    entry serves both 10-K and 10-Q runs."""
    ml = model_sheet.lower()
    if "balance sheet" in ml or ml == "qtr bs":
        return "BS"
    if "cash flow" in ml or ml == "qtr cf":
        return "CF"
    if "p&l" in ml:
        return "IS"
    return "OTHER"


# ============================================================================
# Ledger loading + ticker-only lookup index
# ============================================================================

def _strip_underscore_keys(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


def load_ledger(ledger_path: Path) -> dict:
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    return _strip_underscore_keys(data)


def _entry_aliases(entry: dict) -> list[str]:
    """Return the alias list for a ledger entry, supporting both schemas:
      - modern: `aliases` field (list of strings)
      - legacy: `filing_term_normalized` field (single string)
    A ledger may mix both forms across entries; both are first-class.
    Returns at least one alias when the entry is well-formed; an empty list
    means the entry is malformed (won't be indexed)."""
    aliases = entry.get("aliases")
    if isinstance(aliases, list) and aliases:
        return [a for a in aliases if isinstance(a, str) and a]
    legacy = entry.get("filing_term_normalized")
    if isinstance(legacy, str) and legacy:
        return [legacy]
    return []


def build_ticker_index(
    ledger: dict,
) -> dict[tuple[str, str], list[dict]]:
    """Build {(normalized_alias, sheet_group): [entry, ...]} from the ticker
    decisions_ledger. Ticker-specific — these entries OVERRIDE whatever
    canonical_label extract already set on matching items.

    Both schemas are supported per entry: the modern `aliases` list (preferred —
    matches the generic library shape so a single entry can carry multiple
    filer-label variants) and the legacy `filing_term_normalized` single
    string (so older ledgers keep working without rewrite). Each alias
    becomes a separate index key; alias-level dedup mirrors the generic
    library so two aliases that normalize to the same string don't double-
    register the same entry.

    Variant axis dropped: one ticker entry serves both 10-K and 10-Q runs.
    The actual sheet (ANNL P&L vs QTR P&L, etc.) is derived from
    SHEET_NAME[(filing_type, statement_type)] at item-reconcile time.
    """
    index: dict[tuple[str, str], list[dict]] = defaultdict(list)

    def _register(entry: dict, model_label: str) -> None:
        canonical = {
            "rule_id": entry["rule_id"],
            "model_row": entry.get("model_row", 0),
            "model_label": model_label,
            "filing_subsection": entry.get("filing_subsection"),
            # Accept both `filing_section` (modern, matches generic library schema)
            # and `section` (legacy, used historically by ticker new_rows entries).
            # When both are absent the ticker overlay won't override the extract-
            # time section — fine when the extract-time section is correct.
            "filing_section": entry.get("filing_section") or entry.get("section"),
            "sign_convention": entry.get("sign_convention"),
            "memo": entry.get("memo", False),
            "row_type": entry.get("row_type"),
        }
        sheet_grp = _sheet_group(entry["model_sheet"])
        seen_norm: set[str] = set()
        for alias in _entry_aliases(entry):
            n = normalize_label(alias)
            if n in seen_norm:
                continue
            seen_norm.add(n)
            index[(n, sheet_grp)].append(canonical)

    for entry in ledger.get("mappings", []):
        _register(entry, entry["model_label"])

    for entry in ledger.get("new_rows", []):
        _register(entry, entry["new_row_label"])

    return index


# ============================================================================
# Per-item reconcile
# ============================================================================

def _item_section_str(item: RawLineItem) -> str | None:
    if item.section is None:
        return None
    return item.section.value if hasattr(item.section, "value") else item.section


def _extract_concept_from_citation(item: RawLineItem) -> str | None:
    """Pull the us-gaap concept local name out of citation.line_hint for iXBRL
    items. line_hint shape (from financials-extract's iXBRL path):
    'us-gaap:ConceptName | ctx:duration:2025-12-31'. PDF items don't have this;
    return None."""
    hint = item.citation.line_hint if item.citation else None
    if not hint or "us-gaap:" not in hint:
        return None
    first = hint.split("|", 1)[0].strip()
    if ":" not in first:
        return None
    return first.split(":", 1)[1].strip()


def reconcile_item(
    item: RawLineItem,
    statement_type: StatementType,
    filing_type: FilingType,
    ticker_lookup: dict[tuple[str, str], list[dict]],
    novel_index: dict[tuple[str, str], list[dict]] | None,
) -> tuple[MappedLineItem | None, NovelItem | None]:
    """Return (mapped, None) or (None, novel).

    Precedence:
      1. is_subtotal_label → subtotal pseudo-row
      2. Ticker-ledger override on raw_filing_label → apply override
      3. canonical_label already set by extract → use it
      4. Nothing matched → NovelItem

    For paths (2) and (3), the actual model_sheet on the MappedLineItem comes
    from SHEET_NAME[(filing_type, statement_type)] — never from a stored
    ticker-entry field. This keeps one ledger entry valid across both 10-K
    and 10-Q runs.
    """
    section_str = _item_section_str(item)
    concept = _extract_concept_from_citation(item)

    # (1) Subtotal — only when extract didn't already match to a canonical.
    # PG's "TOTAL OPERATING ACTIVITIES" looks like a subtotal (starts with
    # "TOTAL"), but extract matched it to GEN-CF-022 → "Cash Flow from
    # Operations" (an actual sheet row, not the `_subtotal` pseudo-bucket).
    # Letting the canonical match flow through path (3) puts these on the
    # CASH FLOW sheet where model-write's CF subtotal logic finds them.
    if item.canonical_label is None and is_subtotal_label(item.raw_filing_label, concept=concept):
        item_dict = item.model_dump()
        item_dict["row_type"] = "subtotal"
        return (
            MappedLineItem(
                **item_dict,
                model_sheet="_subtotal",
                model_row=0,
                model_label=item.raw_filing_label,
                mapping_source="ledger_auto",
            ),
            None,
        )

    # (2) Ticker-ledger override
    normalized = normalize_label(item.raw_filing_label)
    group = STMT_TO_GROUP[statement_type]
    candidates = ticker_lookup.get((normalized, group), [])
    ticker_entry = select_entry(candidates, item.subsection_context, section_str)
    if ticker_entry is not None:
        item_dict = item.model_dump()
        # Ticker override replaces extract's generic canonical_label + sign_convention.
        item_dict["canonical_label"] = ticker_entry["model_label"]
        item_dict["ledger_rule_id"] = ticker_entry["rule_id"]
        if ticker_entry.get("sign_convention"):
            item_dict["sign_convention"] = ticker_entry["sign_convention"]
        # Ticker ledger is authoritative for section when set — fixes the
        # UNCLASSIFIED case where extract's heuristic missed (typical for
        # taxonomy extensions like pg:*, ko:*).
        if ticker_entry.get("filing_section"):
            from financials_schema import Section
            item_dict["section"] = Section(ticker_entry["filing_section"])
        # Ticker ledger row_type override — promotes a walker-classified
        # line_item to memo (or subtotal/total) when the ledger entry says so.
        # Required for filer-specific supplemental disclosures like PEP's
        # "Debt discharged via legal defeasance" that should NOT contribute
        # to the CFO/CFI/CFF/CashOther reconciliation but the walker can't
        # know that without an explicit ledger declaration.
        if ticker_entry.get("row_type"):
            item_dict["row_type"] = ticker_entry["row_type"]
        model_sheet = SHEET_NAME[(filing_type, statement_type)]
        return (
            MappedLineItem(
                **item_dict,
                model_sheet=model_sheet,
                model_row=ticker_entry["model_row"],
                model_label=ticker_entry["model_label"],
                mapping_source="ledger_auto",
            ),
            None,
        )

    # (3) Extract-time generic match
    if item.canonical_label is not None:
        # No fallback — every (filing_type, statement_type) combo must be in
        # SHEET_NAME. KeyError here means a new combo was added without
        # registering its sheet routing; the silent "BALANCE SHEET" default
        # used to mask 8-K IS routing bugs etc.
        model_sheet = SHEET_NAME[(filing_type, statement_type)]
        return (
            MappedLineItem(
                **item.model_dump(),
                model_sheet=model_sheet,
                model_row=0,
                model_label=item.canonical_label,
                mapping_source="ledger_auto",
            ),
            None,
        )

    # (4) Memo passthrough — extract-time row_type="memo" facts (par value,
    # shares issued, etc. inline-tagged in equity-class label cells) that
    # don't match anything in the library. They're not part of any subtotal
    # and are informational only, so route to a `_memo` sheet rather than
    # surfacing as novels. Same pattern as `_subtotal` rows.
    rt_str = item.row_type.value if hasattr(item.row_type, "value") else str(item.row_type)
    if rt_str == "memo":
        return (
            MappedLineItem(
                **item.model_dump(),
                model_sheet="_memo",
                model_row=0,
                model_label=item.raw_filing_label,
                mapping_source="ledger_auto",
            ),
            None,
        )

    # (5) Novel — include nearest-match hints from generic library if available
    hints: list[tuple[str, float]] = []
    if novel_index is not None:
        hints = nearest_matches(item.raw_filing_label, statement_type, novel_index, limit=3)
    return (None, NovelItem(raw_item=item, nearest_matches=hints))


# ============================================================================
# Per-filing driver
# ============================================================================

def reconcile_filing(
    raw_filing: RawFiling,
    ledger: dict,
    novel_hint_index: dict[tuple[str, str], list[dict]] | None = None,
) -> tuple[list[MappedLineItem], list[NovelItem], list[dict]]:
    """Returns (mapped_items, novel_items, novel_contexts)."""
    ticker_lookup = build_ticker_index(ledger)

    mapped_items: list[MappedLineItem] = []
    novel_items: list[NovelItem] = []
    novel_contexts: list[dict] = []

    for statement in raw_filing.statements:
        if not keep_statement_for_pipeline(statement, raw_filing.filing_type, raw_filing.statements):
            continue
        period = statement.period
        period_label = (
            f"Q{period.fiscal_quarter} FY{period.fiscal_year}"
            if period.fiscal_quarter else f"FY{period.fiscal_year}"
        )
        for item in statement.line_items:
            mapped, novel = reconcile_item(
                item,
                statement.statement_type,
                raw_filing.filing_type,
                ticker_lookup,
                novel_hint_index,
            )
            if mapped is not None:
                mapped_items.append(mapped)
            else:
                assert novel is not None
                novel_items.append(novel)
                novel_contexts.append({
                    "statement_type": statement.statement_type.value,
                    "period_label": period_label,
                    "period_end_date": period.period_end_date.isoformat(),
                    "fiscal_year": period.fiscal_year,
                })

    return mapped_items, novel_items, novel_contexts


def write_novel_report(
    raw_filing: RawFiling,
    novel_items: list[NovelItem],
    novel_contexts: list[dict],
    out_path: Path,
) -> None:
    report = {
        "filing": {
            "ticker": raw_filing.ticker,
            "filing_type": raw_filing.filing_type.value,
            "filing_date": raw_filing.filing_date.isoformat(),
            "source_path": str(raw_filing.source_path),
        },
        "novels": [
            {
                **ctx,
                "raw_filing_label": novel.raw_item.raw_filing_label,
                "value": str(novel.raw_item.value),
                "raw_numeric_text": novel.raw_item.raw_numeric_text,
                "section": (novel.raw_item.section.value
                            if hasattr(novel.raw_item.section, "value")
                            else novel.raw_item.section),
                "subsection_context": novel.raw_item.subsection_context,
                "citation": json.loads(novel.raw_item.citation.model_dump_json()),
                "nearest_matches": [[m, s] for m, s in novel.nearest_matches],
            }
            for novel, ctx in zip(novel_items, novel_contexts)
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Apply ticker-ledger overrides + sheet-name routing to a RawFiling "
                    "(generic library has already been applied at extract time).",
    )
    parser.add_argument("--ticker-root", required=True, type=Path,
                        help="Per-ticker folder containing config.json + decisions_ledger.json")
    parser.add_argument("--in", dest="in_path", required=True, type=Path,
                        help="Input RawFiling JSON (from financials-extract — PDF or iXBRL path)")
    parser.add_argument("--out", required=True, type=Path,
                        help="Output MappedFiling JSON")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print report only; do not write output or fail on novel items")
    parser.add_argument("--novels-out", type=Path, default=None,
                        help="If set, write a NovelReport JSON to this path (regardless of --dry-run)")
    parser.add_argument("--generic-library", type=Path, default=None,
                        help="(Optional) Path to generic_line_item_mappings.json — only used to produce "
                             "nearest-match hints in novel reports. Auto-resolves from ticker-root if omitted.")
    args = parser.parse_args()

    # CLI guard: ticker from config matches the filing
    config_path = args.ticker_root / "Financial Statements" / "config.json"
    if not config_path.exists():
        sys.exit(f"ERROR: no config.json at {config_path}")
    config = _strip_underscore_keys(json.loads(config_path.read_text(encoding="utf-8")))
    config_ticker = config["ticker"]

    raw_filing = RawFiling.model_validate_json(args.in_path.read_text(encoding="utf-8"))
    if raw_filing.ticker != config_ticker:
        sys.exit(
            f"ERROR: ticker mismatch. config.json says {config_ticker!r} "
            f"but input filing says {raw_filing.ticker!r}"
        )

    ledger_path = args.ticker_root / "Financial Statements" / "decisions_ledger.json"
    if not ledger_path.exists():
        sys.exit(f"ERROR: no decisions_ledger.json at {ledger_path}")
    ledger = load_ledger(ledger_path)

    mappings_count = len(ledger.get("mappings", []))
    new_rows_count = len(ledger.get("new_rows", []))
    structural_count = len(ledger.get("structural_decisions", []))
    print(f"[reconcile] Loaded ticker ledger: {mappings_count} mappings, "
          f"{new_rows_count} new_rows, {structural_count} structural decisions")

    # Optional generic library — only for nearest-match hints in novel reports.
    novel_hint_index: dict[tuple[str, str], list[dict]] | None = None
    generic_path = args.generic_library
    if generic_path is None:
        generic_path = args.ticker_root.parent.parent / "pattern_libraries" / "generic_line_item_mappings.json"
    if generic_path.exists():
        novel_hint_index = build_generic_index(load_generic_library(generic_path))

    # Tally how many items already have canonical_label set by extract
    total_items = sum(len(s.line_items) for s in raw_filing.statements)
    pre_matched = sum(
        1 for s in raw_filing.statements for li in s.line_items
        if li.canonical_label is not None
    )
    print(f"[reconcile] Input: {raw_filing.ticker} {raw_filing.filing_type.value} "
          f"({len(raw_filing.statements)} statements, {total_items} line items, "
          f"{pre_matched} pre-matched by extract)")

    mapped_items, novel_items, novel_contexts = reconcile_filing(
        raw_filing, ledger, novel_hint_index,
    )
    subtotal_count = sum(1 for m in mapped_items if m.model_sheet == "_subtotal")

    print("\n[reconcile] Results:")
    print(f"  Ticker-ledger overrides : {sum(1 for m in mapped_items if m.model_sheet != '_subtotal' and m.model_row > 0)}")
    print(f"  Extract-time library    : {sum(1 for m in mapped_items if m.model_sheet != '_subtotal' and m.model_row == 0)}")
    print(f"  Subtotals (carry-through): {subtotal_count}")
    print(f"  Novel (unresolved)      : {len(novel_items)}")

    if novel_items:
        print("\n[reconcile] Novel items — label | top suggestions:")
        for novel in novel_items[:25]:
            lbl = novel.raw_item.raw_filing_label[:55]
            sugg = ", ".join(f"{k!r}@{s:.2f}" for k, s in novel.nearest_matches[:3])
            print(f"  {lbl:55s} | {sugg}")
        if len(novel_items) > 25:
            print(f"  ... and {len(novel_items) - 25} more")

    if args.novels_out is not None:
        write_novel_report(raw_filing, novel_items, novel_contexts, args.novels_out)
        print(f"\n[reconcile] Wrote NovelReport ({len(novel_items)} novels) -> {args.novels_out}")

    if args.dry_run:
        print("\n[reconcile] --dry-run: no MappedFiling output written")
        return

    if novel_items:
        sys.exit(
            f"\n[reconcile] ERROR: {len(novel_items)} novel items unresolved. "
            "Re-run with --dry-run --novels-out <path> to capture them for the playground, "
            f"then either add aliases to the generic library or append a ticker entry to {ledger_path} and re-run."
        )

    # Section-enforcement: every non-subtotal, non-memo item must have a real
    # section. UNCLASSIFIED at this stage means neither extract heuristic, the
    # generic library's filing_section, nor the ticker overlay placed it. The
    # fix is to add `filing_section` to the matching library entry — generic
    # if cross-ticker, ticker ledger if filer-specific.
    unclassified = []
    for item in mapped_items:
        if item.model_sheet == "_subtotal":
            continue
        rt = item.row_type.value if hasattr(item.row_type, "value") else item.row_type
        # Subtotal/total rows are by-definition rollups (Net Income, Total
        # Assets, etc.) — they don't belong to a single section. The validators
        # capture them as named anchors instead. Memos (share counts, etc.) are
        # never summed.
        if rt in ("memo", "subtotal", "total"):
            continue
        sec = item.section.value if hasattr(item.section, "value") else str(item.section)
        if sec == "unclassified":
            unclassified.append(item)
    if unclassified:
        msg = [f"\n[reconcile] ERROR: {len(unclassified)} items have section=UNCLASSIFIED."]
        msg.append("  Add `filing_section` to the matching library entry (generic or ticker)")
        msg.append(f"  and re-run. Generic library: {generic_path}")
        msg.append(f"  Ticker ledger: {ledger_path}\n")
        for item in unclassified[:25]:
            rid = item.ledger_rule_id or "(novel)"
            lbl = item.raw_filing_label[:55]
            cn = (item.canonical_label or "?")[:40]
            msg.append(f"  {rid:14s} {cn:40s}  raw={lbl!r}")
        if len(unclassified) > 25:
            msg.append(f"  ... and {len(unclassified) - 25} more")
        sys.exit("\n".join(msg))

    # Section-consistency guard: one rule_id → one section.
    # Canonicals can opt out via the `accepted_sections` field — a structural
    # declaration that this canonical absorbs items from multiple filer-
    # classified sections (e.g. GEN-BS-008 absorbs both `non_current_assets`
    # PG-style DTA and `current_assets` MNST-style Prepaid Income Taxes).
    # The library is the source of truth for opt-ins; reconcile loads it
    # above for novel-hint indexing, so we read accepted_sections from the
    # same load.
    multi_section_rules: set[str] = set()
    if generic_path.exists():
        _lib = load_generic_library(generic_path)
        for _e in _lib.get("mappings", []):
            if _e.get("accepted_sections"):
                multi_section_rules.add(_e["rule_id"])

    sections_by_rule: dict[str, dict[str, list]] = {}
    for item in mapped_items:
        if item.ledger_rule_id is None or item.model_sheet == "_subtotal":
            continue
        sec = item.section.value if hasattr(item.section, "value") else str(item.section)
        sections_by_rule.setdefault(item.ledger_rule_id, {}).setdefault(sec, []).append(item)
    collisions = {rid: d for rid, d in sections_by_rule.items()
                  if len(d) > 1 and rid not in multi_section_rules}
    if collisions:
        msg = ["\n[reconcile] ERROR: section-collision — one rule_id matched items across multiple sections."]
        msg.append("  Each collision below means reconcile can't tell the items apart — split the ledger")
        msg.append("  entry into per-section entries and add `filing_section` to disambiguate.\n")
        for rid, by_sec in sorted(collisions.items()):
            secs = sorted(by_sec.keys())
            msg.append(f"  {rid}: sections={secs}")
            for sec, items in by_sec.items():
                ex = items[0]
                msg.append(f"    • section={sec}: raw={ex.raw_filing_label!r} (first of {len(items)})")
        sys.exit("\n".join(msg))

    mapped_filing = MappedFiling(
        raw=raw_filing,
        mapped_line_items=mapped_items,
        novel_items=[],
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(mapped_filing.model_dump_json(indent=2), encoding="utf-8")
    print(f"\n[reconcile] Wrote MappedFiling -> {args.out}")


if __name__ == "__main__":
    main()
