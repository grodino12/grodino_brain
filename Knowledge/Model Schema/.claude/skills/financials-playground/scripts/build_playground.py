"""Render a self-contained HTML QA explorer over one or more ValidatedFiling JSON files.

Inputs assumed valid (produced by financials-validate). Layout: tabs per
statement type (BS / IS / CF) plus a Validation tab. Stdlib-only.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

# ---------- model bucketing ----------

STMT_LABEL = {
    "BS": "BALANCE SHEET",
    "IS": "INCOME STATEMENT",
    "CF": "CASH FLOW",
}

SECTION_ORDER = {
    # BS
    "current_assets": 10,
    "non_current_assets": 20,
    "current_liabilities": 30,
    "non_current_liabilities": 40,
    "mezzanine": 50,
    "equity": 60,
    # CF
    "operating": 100,
    "investing": 110,
    "financing": 120,
    "cash_other": 130,
    "supplemental": 140,
    # IS
    "revenue_cost": 200,
    "operating_expenses": 210,
    "non_operating": 220,
    "tax": 230,
    "eps": 240,
    # Fallback
    "unclassified": 999,
}

SECTION_LABEL = {
    "current_assets": "Current Assets",
    "non_current_assets": "Non-Current Assets",
    "current_liabilities": "Current Liabilities",
    "non_current_liabilities": "Non-Current Liabilities",
    "mezzanine": "Mezzanine",
    "equity": "Stockholders' Equity",
    "operating": "Operating Activities",
    "investing": "Investing Activities",
    "financing": "Financing Activities",
    "cash_other": "Other Effects on Cash",
    "supplemental": "Supplemental Disclosures",
    "revenue_cost": "Top Line",
    "operating_expenses": "Operating Expenses",
    "non_operating": "Non-Operating",
    "tax": "Tax",
    "eps": "Per Share & Shares Outstanding",
    "unclassified": "Unclassified",
}


def period_key(period: dict) -> str:
    fy = period["fiscal_year"]
    fq = period.get("fiscal_quarter")
    return f"Q{fq} FY{fy}" if fq else f"FY{fy}"


def index_by_period(filing: dict) -> list[dict]:
    """Walk statements + mapped_line_items in parallel; return per-statement buckets."""
    statements = filing["mapped"]["raw"]["statements"]
    items = filing["mapped"]["mapped_line_items"]
    filing_date = filing["mapped"]["raw"].get("filing_date", "")
    cursor = 0
    buckets = []
    for s in statements:
        n = len(s["line_items"])
        bucket = {
            "statement_type": s["statement_type"],
            "period_label": period_key(s["period"]),
            "period_end_date": s["period"]["period_end_date"],
            "fiscal_year": s["period"]["fiscal_year"],
            "unit": s["unit"],
            "share_unit": s.get("share_unit", s["unit"]),
            "eps_unit": s.get("eps_unit", s["unit"]),
            "items": items[cursor:cursor + n],
            "source_path": filing["mapped"]["raw"]["source_path"],
            "filing_date": filing_date,
        }
        buckets.append(bucket)
        cursor += n
    return buckets


def dedupe_buckets_by_period(buckets: list[dict]) -> list[dict]:
    """When the same (statement_type, period_end_date) appears in multiple filings,
    keep only the bucket from the filing with the most recent filing_date. Newer
    filings may carry restated comparatives — we trust the latest."""
    by_key: dict[tuple, dict] = {}
    for b in buckets:
        key = (b["statement_type"], b["period_end_date"])
        existing = by_key.get(key)
        if existing is None or b["filing_date"] > existing["filing_date"]:
            by_key[key] = b
    return list(by_key.values())


def effective_unit_for_item(item: dict, bucket: dict) -> str:
    """Pick the right unit (statement / share / eps) for a given item.
    Items in the EPS subsection use bucket.eps_unit; items in the shares_outstanding
    subsection use bucket.share_unit; everything else uses bucket.unit.
    """
    sub = item.get("subsection_context")
    if sub == "eps":
        return bucket["eps_unit"]
    if sub == "shares_outstanding":
        return bucket["share_unit"]
    return bucket["unit"]


UNIT_SUFFIX = {
    "thousands": "thousands",
    "millions": "millions",
    "billions": "billions",
    "actual": "actual",
}


def collect_buckets(filings: list[dict]) -> list[dict]:
    out = []
    for f in filings:
        out.extend(index_by_period(f))
    return dedupe_buckets_by_period(out)


def pivot_statement(buckets: list[dict], stmt_type: str) -> tuple[list[dict], list[dict]]:
    """For one statement type, return (periods, rows).

    periods: [{label, end_date, fiscal_year, unit, source_path}, ...] most recent first
    rows:    [{kind: 'section'|'item'|'subtotal', label, sheet, row, section, cells: {period_label: item}}]
    """
    type_buckets = [b for b in buckets if b["statement_type"] == stmt_type]
    if not type_buckets:
        return [], []
    type_buckets.sort(key=lambda b: b["period_end_date"], reverse=True)
    periods = [{
        "label": b["period_label"],
        "end_date": b["period_end_date"],
        "fiscal_year": b["fiscal_year"],
        "unit": b["unit"],
        "source_path": b["source_path"],
    } for b in type_buckets]

    # Use the newest period as the row-order template; backfill rows from older periods
    # that don't appear in the newest (e.g. items dropped between filings).
    # Include subsection_context in the dedup key — same (sheet, row, label) under
    # different subsections (e.g. EPS-Basic vs shares-Basic) are distinct rows.
    seen_keys: dict[tuple, dict] = {}
    ordered_keys: list[tuple] = []
    for b in type_buckets:
        for it in b["items"]:
            k = (it["model_sheet"], it["model_row"], it["model_label"], it.get("subsection_context"))
            if k not in seen_keys:
                kind = "subtotal" if it.get("row_type") == "subtotal" else "item"
                model_label = it["model_label"]
                # Visually promote CF section sums + cash rollup rows to subtotal styling.
                # Underlying MappedLineItem stays a line_item so model-write keeps model_row.
                if kind == "item" and stmt_type == "CF":
                    if (model_label.startswith("Cash Flow from ")
                            or model_label == "Net Change in Cash"
                            or model_label.startswith("Cash at ")):
                        kind = "subtotal"
                # Carve "Supplemental:" rows on the CF into a dedicated below-the-line
                # section (GAAP convention — they're memo items, not part of the activities).
                section = it.get("section") or "unclassified"
                if stmt_type == "CF" and model_label.startswith("Supplemental:"):
                    section = "supplemental"
                # FX Effect on Cash + other bottom-of-statement reconciliation rows
                # render in their own "Other Effects on Cash" group (Section.CASH_OTHER).
                # Display mezzanine items inside the Stockholders' Equity section.
                # The accounting-equation validator (BS-6) still treats Mezzanine separately
                # since anomalies.json sets excluded_from_total_se=true.
                if stmt_type == "BS" and section == "mezzanine":
                    section = "equity"
                seen_keys[k] = {
                    "kind": kind,
                    "sheet": it["model_sheet"],
                    "row": it["model_row"],
                    "label": model_label,
                    "section": section,
                    "subsection": it.get("subsection_context"),
                    "first_seen": len(ordered_keys),
                }
                ordered_keys.append(k)

    # Within each section, regular items come first (by first-seen order), then
    # subtotal-styled rows sorted by model_row so the CF section sum lands above
    # Net Change / Cash at Beg / Cash at End in that order.
    def sort_key(k):
        meta = seen_keys[k]
        is_sub = 1 if meta["kind"] == "subtotal" else 0
        # For subtotals: sort by model_row (fall back to first_seen if row=0).
        # For regular items: sort by first_seen so extract's natural order wins.
        if is_sub:
            secondary = meta["row"] if meta["row"] > 0 else 10_000 + meta["first_seen"]
        else:
            secondary = meta["first_seen"]
        return (SECTION_ORDER.get(meta["section"], 999), is_sub, secondary)

    ordered_keys.sort(key=sort_key)

    rows = []
    last_section = None
    for k in ordered_keys:
        meta = seen_keys[k]
        section = meta["section"]
        if section != last_section and meta["kind"] != "subtotal":
            rows.append({"kind": "section", "label": SECTION_LABEL.get(section, section), "section": section})
            last_section = section
        cells = {}
        cell_units = {}
        for b in type_buckets:
            match = next(
                (it for it in b["items"]
                 if (it["model_sheet"], it["model_row"], it["model_label"],
                     it.get("subsection_context")) == k),
                None,
            )
            cells[b["period_label"]] = match
            cell_units[b["period_label"]] = effective_unit_for_item(match, b) if match else b["unit"]
        rows.append({**meta, "cells": cells, "cell_units": cell_units})
    return periods, rows


# ---------- formatting ----------

def fmt_value(item: dict | None) -> tuple[str, str]:
    """Return (display_string, css_class). Empty string + 'empty' if no item."""
    if item is None:
        return "—", "empty"
    raw = item.get("raw_numeric_text", "")
    val = Decimal(item["value"])
    if val == 0:
        return raw or "—", "zero"
    sign_neg = val < 0 or (raw.startswith("(") and raw.endswith(")"))
    abs_val = abs(val)
    if abs_val == abs_val.to_integral_value():
        formatted = f"{int(abs_val):,}"
    else:
        formatted = f"{abs_val:,.2f}"
    if sign_neg:
        return f"({formatted})", "neg"
    return formatted, "pos"


def yoy_class(current: dict | None, previous: dict | None) -> str:
    if current is None or previous is None:
        return ""
    cv = Decimal(current["value"])
    pv = Decimal(previous["value"])
    if pv == 0:
        return ""
    pct = abs((cv - pv) / pv) * 100
    if pct > 50:
        return "yoy-bad"
    if pct > 20:
        return "yoy-warn"
    return ""


def citation_tooltip(item: dict | None, unit: str | None = None) -> str:
    """Build a hover tooltip describing where a value came from.

    Dispatches on the source file extension:
      - .htm / .html → iXBRL filing: render concept + statement-role + period
        (the `page=1` in the Citation is a schema placeholder for iXBRL, not a
        real page — skip it). Concept + period come from `line_hint`; the R-file
        role comes from `note` (e.g. "iXBRL | Consolidated Statements of Earnings").
      - anything else → PDF / press release: render source filename + page +
        line hint, the original behavior.
    """
    if item is None:
        return ""
    cit = item.get("citation", {})
    src_path = cit.get("source_path", "")
    src = Path(src_path).name
    hint = cit.get("line_hint", "") or ""
    note = cit.get("note", "") or ""
    raw_label = item.get("raw_filing_label", "")

    is_ixbrl = src.lower().endswith((".htm", ".html"))

    if is_ixbrl:
        # line_hint format from financials-extract's iXBRL path:
        #   "us-gaap:Revenues | ctx:duration:2025-12-31" or "...ctx:instant:2025-12-31"
        concept = hint
        period_str = ""
        if " | ctx:" in hint:
            concept, _, ctx = hint.partition(" | ctx:")
            kind, _, date_str = ctx.partition(":")
            if kind == "instant":
                period_str = f"as of {date_str}"
            elif kind == "duration":
                period_str = f"ending {date_str}"
            else:
                period_str = ctx
        # note format: "iXBRL | Consolidated Statements of Earnings"
        role = note
        if role.startswith("iXBRL"):
            role = role.split("|", 1)[1].strip() if "|" in role else ""
        parts = [f"Concept: {concept or raw_label}"]
        if role:
            parts.append(f"From: {role}")
        if period_str:
            parts.append(f"Period: {period_str}")
        parts.append(f"Source: {src}")
        if unit:
            parts.append(f"Unit: {unit}")
        return " | ".join(parts)

    # PDF path (original)
    page = cit.get("page", "?")
    parts = [f"Raw label: {raw_label}", f"Source: {src} p.{page}"]
    if unit:
        parts.append(f"Unit: {unit}")
    if hint:
        parts.append(f"Line: {hint}")
    return " | ".join(parts)


# ---------- HTML ----------

CSS = """
:root {
  --bg: #0a0d14;
  --panel: #131824;
  --panel-2: #1a2030;
  --border: #2a3244;
  --text: #e6e8ef;
  --text-dim: #7b8294;
  --accent: #4f9eff;
  --good: #14b8a6;
  --warn: #e97c2b;
  --bad:  #ef4444;
  --mono: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
  --sys:  -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; }
body {
  font-family: var(--sys);
  background: var(--bg);
  color: var(--text);
  font-size: 13px;
  line-height: 1.5;
  display: flex;
  flex-direction: column;
}
header {
  padding: 14px 24px 0;
  border-bottom: 1px solid var(--border);
  background: var(--panel);
  flex: 0 0 auto;
}
header .row1 { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }
header h1 { margin: 0; font-size: 16px; font-weight: 600; }
header .sub { color: var(--text-dim); font-size: 12px; font-family: var(--mono); }
header .badge {
  display: inline-block; padding: 2px 9px; border-radius: 10px;
  font-size: 11px; font-weight: 500; font-family: var(--mono);
  border: 1px solid;
}
.badge.pass { color: var(--good); border-color: var(--good); background: rgba(20,184,166,0.08); }
.badge.fail { color: var(--bad);  border-color: var(--bad);  background: rgba(239,68,68,0.08); }

.tabs {
  display: flex; gap: 0; margin-top: 12px;
}
.tabs button {
  background: transparent;
  color: var(--text-dim);
  border: none;
  border-bottom: 2px solid transparent;
  padding: 9px 16px;
  font-family: var(--mono);
  font-size: 12px;
  letter-spacing: 0.5px;
  cursor: pointer;
}
.tabs button:hover { color: var(--text); }
.tabs button.active { color: var(--text); border-bottom-color: var(--accent); }

.toolbar {
  padding: 8px 24px; border-bottom: 1px solid var(--border);
  background: var(--panel); display: flex; gap: 16px; align-items: center;
  font-size: 11px; color: var(--text-dim);
  font-family: var(--mono);
}
.toolbar label { display: flex; gap: 6px; align-items: center; cursor: pointer; }

main { flex: 1 1 auto; overflow: auto; padding: 16px 24px; }
.tab-panel { display: none; }
.tab-panel.active { display: block; }

table.statement {
  border-collapse: collapse;
  font-family: var(--mono);
  font-size: 12px;
  width: 100%;
  max-width: 1400px;
}
table.statement th, table.statement td {
  padding: 4px 10px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
table.statement th {
  text-align: right;
  color: var(--text-dim);
  font-weight: 500;
  font-size: 11px;
  letter-spacing: 0.4px;
  position: sticky; top: 0;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
}
table.statement th.label-col, table.statement td.label-col {
  text-align: left;
  white-space: normal;
}
table.statement td.row-num {
  color: var(--text-dim);
  text-align: right;
  font-size: 10px;
  width: 38px;
}
table.statement td.value {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
td.value.neg { color: var(--bad); }
td.value.zero, td.value.empty { color: var(--text-dim); }
td.value.yoy-warn { background: rgba(233,124,43,0.12); }
td.value.yoy-bad  { background: rgba(239,68,68,0.16); }

tr.section td {
  background: var(--panel-2);
  color: var(--accent);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1px;
  padding-top: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}
tr.subtotal td {
  background: rgba(79,158,255,0.05);
  font-weight: 600;
  border-top: 1px solid var(--border);
}
tr.subtotal td.label-col { color: var(--accent); }

.raw-label { display: none; color: var(--text-dim); font-size: 10px; }
body.show-raw .raw-label { display: block; }
body.show-raw .model-label { color: var(--text-dim); }
.unit-hint { color: var(--warn); font-size: 10px; font-weight: 400; margin-left: 4px; }

table.validation {
  border-collapse: collapse;
  font-family: var(--mono);
  font-size: 12px;
  width: 100%;
  max-width: 1400px;
}
table.validation th, table.validation td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  text-align: left;
}
table.validation th { color: var(--text-dim); font-weight: 500; font-size: 11px; }
table.validation td.gap { text-align: right; font-variant-numeric: tabular-nums; }
table.validation td.sev { font-weight: 600; }
td.sev.pass { color: var(--good); }
td.sev.warning { color: var(--warn); }
td.sev.fail { color: var(--bad); }
table.validation tr.fam-divider td {
  background: var(--panel-2);
  color: var(--accent);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.tab-badge {
  display: inline-block;
  padding: 0 6px;
  margin-left: 4px;
  border-radius: 8px;
  background: var(--bad);
  color: #fff;
  font-size: 10px;
  font-family: var(--mono);
}

table.novels {
  border-collapse: collapse;
  font-family: var(--mono);
  font-size: 12px;
  width: 100%;
  max-width: 1500px;
}
table.novels th, table.novels td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}
table.novels th {
  color: var(--text-dim);
  font-weight: 500;
  font-size: 11px;
  position: sticky; top: 0;
  background: var(--bg);
}
.novel-id { color: var(--accent); font-weight: 600; width: 38px; }
.novel-label { font-weight: 500; }
.sheet-tag {
  display: inline-block; padding: 2px 8px; border-radius: 4px;
  font-size: 11px; font-weight: 600;
  border: 1px solid;
}
.sheet-tag.sheet-BS { color: var(--c-pkg, #0ea5e9); border-color: var(--c-pkg, #0ea5e9); background: rgba(14,165,233,0.08); }
.sheet-tag.sheet-IS { color: var(--good); border-color: var(--good); background: rgba(20,184,166,0.08); }
.sheet-tag.sheet-CF { color: var(--warn); border-color: var(--warn); background: rgba(233,124,43,0.08); }
.section-tag { color: var(--text-dim); font-size: 11px; }
.occ-period { color: var(--accent); }
.occ-val { color: var(--text); font-variant-numeric: tabular-nums; }
.occ-cite { color: var(--text-dim); font-size: 10px; margin-left: 6px; }
.fuzzy-cand { color: var(--text); }
.fuzzy-score { color: var(--warn); font-variant-numeric: tabular-nums; margin-left: 4px; }
"""

JS = """
function showTab(tabId) {
  document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === tabId));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'tab-' + tabId));
}
function toggleRawLabels(checked) {
  document.body.classList.toggle('show-raw', checked);
}
"""


def render_statement_table(periods: list[dict], rows: list[dict]) -> str:
    if not periods:
        return '<p style="color: var(--text-dim);">No data for this statement.</p>'

    unit_phrase = periods[0]["unit"]
    head_cells = [
        '<th class="label-col">Line item</th>',
        '<th>Row</th>',
    ]
    for p in periods:
        head_cells.append(f'<th>{html.escape(p["label"])}</th>')
    head = "<tr>" + "".join(head_cells) + "</tr>"

    statement_unit = unit_phrase
    body_rows = []
    for r in rows:
        if r["kind"] == "section":
            body_rows.append(
                f'<tr class="section"><td colspan="{len(periods) + 2}">{html.escape(r["label"])}</td></tr>'
            )
            continue
        cls = "subtotal" if r["kind"] == "subtotal" else "item"
        # Determine the row's effective unit (from any non-empty cell)
        row_unit = None
        for p in periods:
            u = r.get("cell_units", {}).get(p["label"])
            if u:
                row_unit = u
                break
        # cells, in display order (newest first)
        cell_html = []
        for i, p in enumerate(periods):
            item = r["cells"].get(p["label"])
            cell_unit = r.get("cell_units", {}).get(p["label"])
            display, val_class = fmt_value(item)
            yoy = ""
            if i + 1 < len(periods):
                prev_item = r["cells"].get(periods[i + 1]["label"])
                yoy = yoy_class(item, prev_item)
            tip = citation_tooltip(item, cell_unit)
            tip_attr = f' title="{html.escape(tip)}"' if tip else ""
            cell_html.append(
                f'<td class="value {val_class} {yoy}"{tip_attr}>{html.escape(display)}</td>'
            )
        # raw label = first non-empty raw_filing_label across periods
        raw_label = ""
        for p in periods:
            it = r["cells"].get(p["label"])
            if it and it.get("raw_filing_label"):
                raw_label = it["raw_filing_label"]
                break
        row_num = "" if r["kind"] == "subtotal" else str(r["row"])
        sheet_tag = "" if r["kind"] == "subtotal" else f' · {html.escape(r["sheet"])}'
        # Show a unit hint inline only when the row's effective unit differs from the statement's
        unit_hint = ""
        if row_unit and row_unit != statement_unit:
            unit_hint = f' <span class="unit-hint">({html.escape(row_unit)})</span>'
        body_rows.append(
            f'<tr class="{cls}">'
            f'<td class="label-col">'
            f'  <div class="model-label">{html.escape(r["label"])}{unit_hint}</div>'
            f'  <div class="raw-label">{html.escape(raw_label)}{sheet_tag}</div>'
            f'</td>'
            f'<td class="row-num">{row_num}</td>'
            + "".join(cell_html) +
            f'</tr>'
        )

    return (
        f'<div style="margin-bottom: 8px; color: var(--text-dim); font-family: var(--mono); font-size: 11px;">'
        f'Values in {html.escape(unit_phrase)}. Hover a cell for source citation.'
        f'</div>'
        f'<table class="statement">'
        f'<thead>{head}</thead>'
        f'<tbody>{"".join(body_rows)}</tbody>'
        f'</table>'
    )


def render_novels_table(novel_reports: list[dict]) -> str:
    """Group novels across one or more reports by (statement_type, raw_filing_label, subsection_context).
    Display each unique novel as one numbered row showing all periods + values + fuzzy candidates,
    so the user can scan the list and designate target rows.
    """
    if not novel_reports:
        return ""
    groups: dict[tuple, dict] = {}
    for report in novel_reports:
        filing = report["filing"]
        for n in report["novels"]:
            key = (n["statement_type"], n["raw_filing_label"], n.get("subsection_context"))
            g = groups.setdefault(key, {
                "statement_type": n["statement_type"],
                "raw_filing_label": n["raw_filing_label"],
                "section": n.get("section"),
                "subsection_context": n.get("subsection_context"),
                "filing_source": Path(filing["source_path"]).name,
                "filing_label": filing.get("filing_type", "?"),
                "occurrences": [],
                "nearest_matches": n.get("nearest_matches", []),
            })
            g["occurrences"].append({
                "period_label": n["period_label"],
                "value": n["value"],
                "raw_numeric_text": n["raw_numeric_text"],
                "page": n.get("citation", {}).get("page"),
                "line_hint": n.get("citation", {}).get("line_hint", ""),
            })
    # Sort: BS first, then IS, then CF; within sheet, by raw label
    sheet_order = {"BS": 0, "IS": 1, "CF": 2}
    ordered = sorted(groups.values(),
                     key=lambda g: (sheet_order.get(g["statement_type"], 9),
                                    g["raw_filing_label"].lower()))

    head = (
        "<tr>"
        "<th class='novel-id'>#</th>"
        "<th>Sheet</th>"
        "<th>Section / Subsection</th>"
        "<th>Raw filing label</th>"
        "<th>Periods + values</th>"
        "<th>Top fuzzy matches</th>"
        "</tr>"
    )

    rows_html = []
    for i, g in enumerate(ordered, 1):
        # periods column: "FY2024 27,500 | FY2023 25,500 | FY2022 22,000"
        occ_html = "<br>".join(
            f'<span class="occ-period">{html.escape(o["period_label"])}</span>'
            f' <span class="occ-val">{html.escape(o["raw_numeric_text"])}</span>'
            for o in g["occurrences"]
        )
        # First citation
        first_page = g["occurrences"][0].get("page")
        cite_str = f' <span class="occ-cite">p.{first_page}</span>' if first_page else ""

        sub = g.get("subsection_context") or ""
        sub_str = f" / {html.escape(sub)}" if sub else ""
        section_str = html.escape(g.get("section") or "")

        # fuzzy matches column
        fm = g.get("nearest_matches", [])
        if fm:
            fm_html = "<br>".join(
                f'<span class="fuzzy-cand">{html.escape(m)}</span>'
                f' <span class="fuzzy-score">{float(s):.2f}</span>'
                for m, s in fm[:3]
            )
        else:
            fm_html = '<span class="fuzzy-cand" style="color: var(--text-dim);">no candidates ≥ 0.50</span>'

        rows_html.append(
            f'<tr class="novel-row">'
            f'<td class="novel-id">#{i}</td>'
            f'<td><span class="sheet-tag sheet-{g["statement_type"]}">{html.escape(g["statement_type"])}</span></td>'
            f'<td><span class="section-tag">{section_str}{sub_str}</span></td>'
            f'<td class="novel-label">{html.escape(g["raw_filing_label"])}{cite_str}</td>'
            f'<td>{occ_html}</td>'
            f'<td>{fm_html}</td>'
            f'</tr>'
        )

    summary = (
        f'<div style="margin-bottom: 12px; font-family: var(--mono); font-size: 12px;">'
        f'<span class="badge fail">{len(ordered)} unique novel labels</span> '
        f'<span style="color: var(--text-dim); margin-left: 8px;">'
        f'across {sum(len(g["occurrences"]) for g in ordered)} period-occurrences. '
        f'Tell the assistant the # and target row to add a ledger entry.'
        f'</span>'
        f'</div>'
    )
    return summary + (
        f'<table class="novels"><thead>{head}</thead>'
        f'<tbody>{"".join(rows_html)}</tbody></table>'
    )


def render_validation_table(filings: list[dict]) -> str:
    rows_html = []
    family_buckets: dict[str, list[dict]] = defaultdict(list)
    total = 0
    fails = 0
    warnings = 0
    for f in filings:
        for r in f["results"]:
            family = r["rule_id"].split("-")[0]  # 'BS', 'CF', 'X'
            family_buckets[family].append(r)
            total += 1
            if r["severity"] == "fail":
                fails += 1
            elif r["severity"] == "warning":
                warnings += 1
    fam_order = ["BS", "CF", "X"]
    head = (
        "<tr><th>Rule</th><th>Severity</th><th class='gap'>Expected</th>"
        "<th class='gap'>Actual</th><th class='gap'>Gap</th><th>Message</th></tr>"
    )
    for fam in fam_order:
        if fam not in family_buckets:
            continue
        rows_html.append(f'<tr class="fam-divider"><td colspan="6">{fam}-rules</td></tr>')
        for r in family_buckets[fam]:
            sev = r["severity"]
            gap = r["gap"]
            try:
                gap_disp = f'{int(Decimal(gap)):,}' if Decimal(gap) == Decimal(gap).to_integral_value() else gap
            except Exception:
                gap_disp = gap
            try:
                exp = f'{int(Decimal(r["expected"])):,}'
                act = f'{int(Decimal(r["actual"])):,}'
            except Exception:
                exp, act = r["expected"], r["actual"]
            rows_html.append(
                f'<tr>'
                f'<td>{html.escape(r["rule_id"])}</td>'
                f'<td class="sev {sev}">{sev.upper()}</td>'
                f'<td class="gap">{exp}</td>'
                f'<td class="gap">{act}</td>'
                f'<td class="gap">{gap_disp}</td>'
                f'<td>{html.escape(r["message"])}</td>'
                f'</tr>'
            )
    summary = (
        f'<div style="margin-bottom: 12px; font-family: var(--mono); font-size: 12px;">'
        f'<span class="badge {"fail" if fails else "pass"}">'
        f'{total - fails - warnings}/{total} PASS · {warnings} WARN · {fails} FAIL'
        f'</span>'
        f'</div>'
    )
    return summary + f'<table class="validation"><thead>{head}</thead><tbody>{"".join(rows_html)}</tbody></table>'


def render_html(filings: list[dict], novel_reports: list[dict] | None = None) -> str:
    buckets = collect_buckets(filings)
    bs_periods, bs_rows = pivot_statement(buckets, "BS")
    is_periods, is_rows = pivot_statement(buckets, "IS")
    cf_periods, cf_rows = pivot_statement(buckets, "CF")

    # header summary
    tickers = sorted(set(f["mapped"]["raw"]["ticker"] for f in filings))
    filing_descs = []
    for f in filings:
        ft = f["mapped"]["raw"]["filing_type"]
        fd = f["mapped"]["raw"]["filing_date"]
        src = Path(f["mapped"]["raw"]["source_path"]).name
        filing_descs.append(f"{ft} ({fd}) -> {src}")
    total_results = sum(len(f["results"]) for f in filings)
    total_fails = sum(1 for f in filings for r in f["results"] if r["severity"] == "fail")
    total_warnings = sum(1 for f in filings for r in f["results"] if r["severity"] == "warning")
    badge_cls = "fail" if total_fails else "pass"
    badge_text = f'{total_results - total_fails - total_warnings}/{total_results} validation rules pass'

    novels_button = ""
    novels_panel = ""
    if novel_reports:
        n_count = sum(len(r.get("novels", [])) for r in novel_reports)
        novels_button = (
            f'<button data-tab="novels" onclick="showTab(\'novels\')">'
            f'NOVELS <span class="tab-badge">{n_count}</span></button>'
        )
        novels_panel = (
            f'<div id="tab-novels" class="tab-panel">'
            f'{render_novels_table(novel_reports)}'
            f'</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{html.escape(", ".join(tickers))} — Financials Explorer</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <div class="row1">
    <h1>{html.escape(", ".join(tickers))} — Financials Explorer</h1>
    <span class="badge {badge_cls}">{html.escape(badge_text)}</span>
  </div>
  <div class="sub">{html.escape(" · ".join(filing_descs))}</div>
  <div class="tabs">
    <button class="active" data-tab="bs" onclick="showTab('bs')">BALANCE SHEET</button>
    <button data-tab="is" onclick="showTab('is')">INCOME STATEMENT</button>
    <button data-tab="cf" onclick="showTab('cf')">CASH FLOW</button>
    <button data-tab="val" onclick="showTab('val')">VALIDATION</button>
    {novels_button}
  </div>
</header>
<div class="toolbar">
  <label><input type="checkbox" onchange="toggleRawLabels(this.checked)"> Show raw filing labels + sheet tags</label>
  <span>·</span>
  <span>YoY shading: &gt;20% orange · &gt;50% red</span>
</div>
<main>
  <div id="tab-bs" class="tab-panel active">{render_statement_table(bs_periods, bs_rows)}</div>
  <div id="tab-is" class="tab-panel">{render_statement_table(is_periods, is_rows)}</div>
  <div id="tab-cf" class="tab-panel">{render_statement_table(cf_periods, cf_rows)}</div>
  <div id="tab-val" class="tab-panel">{render_validation_table(filings)}</div>
  {novels_panel}
</main>
<script>{JS}</script>
</body>
</html>
"""


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inputs", action="append", required=True,
                    help="Path to a validated_*.json (repeatable to merge filings)")
    ap.add_argument("--novels-in", dest="novel_inputs", action="append", default=[],
                    help="Path to a NovelReport JSON from reconcile --novels-out (repeatable). Adds a NOVELS tab.")
    ap.add_argument("--out", dest="output", required=True, help="Output HTML path")
    args = ap.parse_args()

    filings = []
    for p in args.inputs:
        with open(p, encoding="utf-8") as f:
            filings.append(json.load(f))

    novel_reports = []
    for p in args.novel_inputs:
        with open(p, encoding="utf-8") as f:
            novel_reports.append(json.load(f))

    html_str = render_html(filings, novel_reports if novel_reports else None)
    Path(args.output).write_text(html_str, encoding="utf-8")
    print(f"Wrote {len(html_str):,} bytes -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
