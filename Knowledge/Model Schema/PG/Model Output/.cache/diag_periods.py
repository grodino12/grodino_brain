"""List all CF statement period_ends across PG filings."""
import json
from pathlib import Path

OUT_DIR = Path("C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/PG/Model Output")
files = sorted(OUT_DIR.glob("validated_*.json"))

print(f"\n=== All CF statement periods, by filing ===\n")
for fp in files:
    with open(fp, encoding="utf-8") as f:
        vf = json.load(f)
    fdate = vf["mapped"]["raw"]["filing_date"]
    print(f"\n{fp.name} (filed {fdate}):")
    for stmt in vf["mapped"]["raw"]["statements"]:
        if stmt["statement_type"] != "cash_flow":
            continue
        p = stmt.get("period", {})
        print(f"  CF: start={p.get('period_start_date')}, end={p.get('period_end_date')}, weeks={p.get('period_length_weeks')}, fq={p.get('fiscal_quarter')}, fy={p.get('fiscal_year')}, n_items={len(stmt['line_items'])}")
