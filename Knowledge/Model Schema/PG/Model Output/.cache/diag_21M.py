"""Diagnostic: find which row introduces the $21M Investing gap at 2024-03-31."""
import json
from pathlib import Path

OUT_DIR = Path("C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/PG/Model Output")
TARGET = "2024-03-31"

files = sorted(OUT_DIR.glob("validated_*.json"))

# Step 1: find every CF statement across all filings whose period_end == TARGET.
print(f"\n=== Step 1: CF statements ending {TARGET} ===\n")
for fp in files:
    with open(fp, encoding="utf-8") as f:
        vf = json.load(f)
    fdate = vf["mapped"]["raw"]["filing_date"]
    for stmt in vf["mapped"]["raw"]["statements"]:
        if stmt["statement_type"] != "cash_flow":
            continue
        p = stmt.get("period", {})
        if p.get("period_end_date") == TARGET:
            print(f"  {fp.name} (filed {fdate}): start={p.get('period_start_date')}, weeks={p.get('period_length_weeks')}, fq={p.get('fiscal_quarter')}")

# Step 2: dump Investing items per (filing, period_end=TARGET) — both raw and mapped views
print(f"\n=== Step 2: Investing items @ {TARGET} ===\n")
for fp in files:
    with open(fp, encoding="utf-8") as f:
        vf = json.load(f)
    fdate = vf["mapped"]["raw"]["filing_date"]
    statements = vf["mapped"]["raw"]["statements"]
    mapped = vf["mapped"]["mapped_line_items"]

    # Walk statements and the mapped slice that aligns to each
    idx = 0
    for stmt in statements:
        n = len(stmt["line_items"])
        if stmt["statement_type"] != "cash_flow":
            idx += n
            continue
        p = stmt.get("period", {})
        if p.get("period_end_date") != TARGET:
            idx += n
            continue
        # Found the target CF statement
        slice_ = mapped[idx:idx + n]
        print(f"\n  {fp.name} (filed {fdate}, weeks={p.get('period_length_weeks')}):")
        total = 0.0
        for raw_li, m_li in zip(stmt["line_items"], slice_):
            sec = str(raw_li.get("section", "")).lower()
            if "investing" not in sec:
                continue
            lbl = m_li.get("model_label") or raw_li.get("canonical_label") or raw_li.get("raw_filing_label") or "?"
            val = float(raw_li.get("value") or 0)
            rt = raw_li.get("row_type", "line_item")
            rid = m_li.get("ledger_rule_id") or raw_li.get("ledger_rule_id") or "—"
            sheet = m_li.get("model_sheet") or "—"
            marker = "[SUB]" if rt == "subtotal" else "     "
            print(f"    {marker} {lbl[:48]:48s}  rid={rid:18s} sheet={sheet:14s} val={val:>12,.0f}")
            if rt != "subtotal" and sheet != "_subtotal":
                total += val
        print(f"    --- SUM(line_items, sheet != _subtotal) = {total:,.0f}")
        idx += n
