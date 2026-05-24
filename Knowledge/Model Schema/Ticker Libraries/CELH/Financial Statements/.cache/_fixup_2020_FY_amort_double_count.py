"""Idempotent fixup: restate 2020-FY 10-K's CFO Amortization line from 1,611,566 -> 1,484,303.

WHY
---
CELH's 2020-FY 10-K (filed 2021-03-11, accession 0001829126-21-001412) reports
its CFO indirect-method add-backs as:

    Net income          8,523,849
    Depreciation          127,263
    Amortization        1,611,566   <-- combined D+A despite separate Depreciation row
    ...
    CFO                 3,395,084   (filer's printed subtotal)

Summing the 14 tagged operating line items gives $3,522,347 -- exactly $127,263
higher than the printed CFO subtotal. The gap equals the Depreciation amount,
and the 2021-FY 10-K's restated FY2020 comparative column confirms the cause:
the comparative reports Amortization = $1,484,303 (= 1,611,566 - 127,263). The
2020-FY line was implicitly combined D+A; breaking Depreciation out separately
caused double-counting in the as-tagged value.

HOW
---
Run AFTER `extract.py --path xbrl-xml` against the 2020-FY 10-K HTM and BEFORE
`reconcile.py`. Idempotent: if the Amortization line is already 1,484,303, the
script is a no-op.

    python _fixup_2020_FY_amort_double_count.py [path/to/raw_2020-FY.json]

Default path is the sibling raw_2020-FY.json in this .cache folder.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent / "raw_2020-FY.json"


def apply(path: Path) -> int:
    d = json.loads(path.read_text(encoding="utf-8"))
    n_patched = 0
    n_noop = 0
    for s in d["statements"]:
        if s.get("statement_type") != "CF":
            continue
        for li in s["line_items"]:
            if li.get("raw_filing_label") != "Amortization":
                continue
            if str(li.get("value")) == "1611566":
                li["value"] = "1484303"
                li["raw_numeric_text"] = "1484303"
                cit = li.setdefault("citation", {})
                note = cit.get("note", "")
                if "RESTATED" not in note:
                    cit["note"] = (note +
                                   " | RESTATED per 2021-FY 10-K comparative "
                                   "(original line was combined D+A; separate "
                                   "Depreciation row already broken out, causing "
                                   "double-count). See _fixup_2020_FY_amort_double_count.py.")
                n_patched += 1
            elif str(li.get("value")) == "1484303":
                n_noop += 1
    path.write_text(json.dumps(d, indent=2), encoding="utf-8")
    return n_patched if n_patched else (-1 if n_noop else 0)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    if not target.exists():
        raise SystemExit(f"ERROR: raw filing not found at {target}")
    n = apply(target)
    if n > 0:
        print(f"[fixup] Patched {n} Amortization line(s) in {target.name}: "
              f"1,611,566 -> 1,484,303 (FY2020 CFO column)")
    elif n < 0:
        print(f"[fixup] No-op: Amortization already at restated value (1,484,303)")
    else:
        print(f"[fixup] No-op: no matching Amortization line found in {target.name}")
