"""financials-extract CLI — dispatches to the PDF or iXBRL parser by source extension.

Both paths emit the same RawFiling JSON shape; downstream skills (reconcile,
validate, playground, model-write) consume that shape format-agnostically.

Routing:
    .pdf            -> pdf_path.extract_filing  (pdfplumber + pattern libraries)
    .htm / .html    -> ixbrl_path.build_raw_filing  (lxml + presentation linkbase)

CLI:
    financials-extract \\
        --ticker-root  <path-to-ticker-folder-with-config.json> \\
        --source       <path-to-pdf-or-htm> \\
        --out          <output-RawFiling-JSON> \\
        [--filing-type 10-K|10-Q|8-K|press_release]   # PDF only; iXBRL reads form from .meta.json
        [--filing-date YYYY-MM-DD]                    # PDF only
        [--only        BS,CF,IS]                      # PDF only
        [--library     <generic-library.json>]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from financials_schema import FilingType, StatementType

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts import ixbrl_path, pdf_path, xbrl_xml_path
else:
    from . import ixbrl_path, pdf_path, xbrl_xml_path


FILING_TYPE_FROM_ARG = {
    "10-K": FilingType.TEN_K,
    "10-Q": FilingType.TEN_Q,
    "8-K": FilingType.EIGHT_K,
    "press_release": FilingType.PRESS_RELEASE,
}

ONLY_TYPE_FROM_ARG = {
    "BS": StatementType.BALANCE_SHEET,
    "CF": StatementType.CASH_FLOW,
    "IS": StatementType.INCOME_STATEMENT,
}


def detect_source_kind(source: Path) -> str:
    """Return 'pdf', 'ixbrl', or 'xbrl-xml' for the source.

    PDFs route by extension. For .htm/.html, the file is inline-iXBRL only if
    it actually carries `<ix:>` tags — pre-iXBRL filings (CELH through fiscal
    2020) have none, and their XBRL lives in sidecar XML, so they route to the
    'xbrl-xml' path. SystemExit on unknown extension."""
    ext = source.suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in (".htm", ".html"):
        return "ixbrl" if b"<ix:" in source.read_bytes() else "xbrl-xml"
    raise SystemExit(
        f"ERROR: unsupported source extension {ext!r} (got {source}). "
        f"Expected .pdf, .htm, or .html."
    )


def load_ticker_from_config(ticker_root: Path) -> str:
    config_path = ticker_root / "Financial Statements" / "config.json"
    if not config_path.exists():
        raise SystemExit(f"ERROR: no config.json at {config_path}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config = {k: v for k, v in config.items() if not k.startswith("_")}
    return config["ticker"]


# ============================================================================
# Tax sign correction
# ============================================================================
#
# The library entry GEN-IS-010 ("Income Tax (Expense) Benefit") carries
# `sign_convention="negative"` because tax-as-expense is the modal case. But
# in LOSS periods, filers report tax as a BENEFIT — same magnitude, opposite
# economic sign. CELH FY2021 had pre-tax loss of $4,059 and a tax benefit
# of $7,996 → NI = +$3,937. Forcing -abs(tax) onto a benefit row breaks the
# IS cascade in the workbook.
#
# Per-period derivation: after extract collects each IS statement's items,
# look at filer-reported PT and NI. If NI > PT, tax was beneficial — flip
# the tax sign_convention to "positive" so `_signed_value()` returns +abs.
# Otherwise leave the library default in place (expense-period rendering).
# Generalizes to any filer who reports a tax benefit in any period.

_PRETAX_CANONICALS = {"Pre-Tax Income (Loss)"}
_NI_CANONICALS = {
    "Net Income (Loss)",
    "Net Income (Loss) Including NCI",
    "Net Income (Loss) Less NCI",
}
_TAX_CANONICALS = {"Income Tax (Expense) Benefit"}


def correct_tax_signs(raw_filing) -> int:
    """Per IS statement, flip tax `sign_convention` to 'positive' when the
    filer's NI is greater than PT (tax was a benefit). Returns the count of
    items adjusted. No-op for filings without IS statements or when PT/NI
    can't be located. RawLineItem is frozen — uses model_copy + list-slot
    replacement to update."""
    n_flipped = 0
    for stmt in raw_filing.statements:
        if stmt.statement_type != StatementType.INCOME_STATEMENT:
            continue
        pt_item = next(
            (li for li in stmt.line_items if (li.canonical_label or "") in _PRETAX_CANONICALS),
            None,
        )
        ni_item = next(
            (li for li in stmt.line_items if (li.canonical_label or "") in _NI_CANONICALS),
            None,
        )
        if pt_item is None or ni_item is None:
            continue
        if ni_item.value > pt_item.value:
            for i, li in enumerate(stmt.line_items):
                if (li.canonical_label or "") in _TAX_CANONICALS and li.sign_convention != "positive":
                    stmt.line_items[i] = li.model_copy(update={"sign_convention": "positive"})
                    n_flipped += 1
    return n_flipped


def main():
    parser = argparse.ArgumentParser(
        description="Extract an SEC filing into a RawFiling JSON. "
                    "Auto-dispatches to the PDF or iXBRL parser by file extension."
    )
    parser.add_argument("--ticker-root", required=True, type=Path,
                        help="Per-ticker folder containing config.json.")
    parser.add_argument("--source", required=True, type=Path,
                        help="Path to the source filing (.pdf, .htm, or .html).")
    parser.add_argument("--out", required=True, type=Path,
                        help="Output path for the RawFiling JSON.")
    parser.add_argument("--filing-type", default="10-K",
                        choices=list(FILING_TYPE_FROM_ARG.keys()),
                        help="(PDF only) Filing form type. iXBRL reads form from .meta.json sidecar.")
    parser.add_argument("--filing-date", default=None,
                        help="(PDF only) Filing date YYYY-MM-DD; defaults to today.")
    parser.add_argument("--only", default=None,
                        help="(PDF only) Comma-separated statement types to extract (BS,CF,IS).")
    parser.add_argument("--library", type=Path, default=None,
                        help="Path to generic_line_item_mappings.json. When set, each line item gets "
                             "canonical_label + ledger_rule_id populated at extract time.")
    parser.add_argument("--path", default="auto",
                        choices=["auto", "pdf", "ixbrl", "xbrl-xml"],
                        help="Override the extractor path. 'auto' (default) routes by file "
                             "extension + iXBRL-tag presence. Force 'xbrl-xml' to extract an "
                             "iXBRL filing from its sidecar XBRL instead of its HTM tables "
                             "(e.g. CELH 2021/2022 10-Ks whose table layout defeats the HTM walker).")
    args = parser.parse_args()

    ticker = load_ticker_from_config(args.ticker_root)
    kind = args.path if args.path != "auto" else detect_source_kind(args.source)

    if kind == "pdf":
        filing_date_ = (date.fromisoformat(args.filing_date)
                        if args.filing_date else date.today())
        filing_type = FILING_TYPE_FROM_ARG[args.filing_type]
        only_types: set[StatementType] | None = None
        if args.only:
            only_types = set()
            for s in args.only.split(","):
                s = s.strip().upper()
                if s in ONLY_TYPE_FROM_ARG:
                    only_types.add(ONLY_TYPE_FROM_ARG[s])

        raw_filing = pdf_path.extract_filing(
            pdf_path=args.source,
            ticker=ticker,
            filing_type=filing_type,
            filing_date_=filing_date_,
            only_types=only_types,
            library_path=args.library,
        )
    else:  # ixbrl or xbrl-xml — both produce an identical RawFiling shape
        builder = (xbrl_xml_path if kind == "xbrl-xml" else ixbrl_path).build_raw_filing
        raw_filing = builder(
            htm_path=args.source,
            ticker=ticker,
            library_path=args.library,
        )
        # Ticker guard: meta-derived ticker must match config.
        if raw_filing.ticker != ticker:
            raise SystemExit(
                f"Ticker mismatch: config says {ticker!r}, filing meta says {raw_filing.ticker!r}"
            )

    # Per-period tax sign correction. Library default (negative) is wrong
    # for benefit periods; this re-derives sign from filer's PT→NI delta.
    correct_tax_signs(raw_filing)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(raw_filing.model_dump_json(indent=2), encoding="utf-8")

    n_items = sum(len(s.line_items) for s in raw_filing.statements)
    print(f"\n[extract] Wrote RawFiling -> {args.out}")
    print(f"           ticker={raw_filing.ticker} form={raw_filing.filing_type.value} "
          f"filing_date={raw_filing.filing_date}")
    print(f"           {len(raw_filing.statements)} Statement(s), {n_items} line items total")


if __name__ == "__main__":
    main()
