"""Catalog all novels across CELH filings + dedupe."""
import json
from pathlib import Path
from collections import defaultdict

CACHE = Path("C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/CELH/Model Output/.cache")
files = sorted(CACHE.glob("novels_*.json"))

# Group key: (raw_filing_label, statement_type)
novel_to_filings = defaultdict(set)
novel_top_candidates = {}
novel_value_sample = {}
novel_section = {}

for fp in files:
    label = fp.stem.replace("novels_", "")
    with open(fp, encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("novels", []) if isinstance(data, dict) else []
    for n in items:
        raw = n.get("raw_filing_label", "")
        stmt = n.get("statement_type", "?")
        sec = n.get("section", "?")
        key = (raw, stmt)
        novel_to_filings[key].add(label)
        if key not in novel_top_candidates:
            nm = n.get("nearest_matches", []) or []
            # nearest_matches is a list of [label, score] pairs
            cands = []
            for entry in nm[:3]:
                if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    cands.append((entry[0], entry[1]))
                elif isinstance(entry, dict):
                    cands.append((entry.get("canonical_label") or entry.get("label"), entry.get("score")))
            novel_top_candidates[key] = cands
            novel_value_sample[key] = n.get("value")
            novel_section[key] = sec

print(f"Total unique novel entries (raw_label × stmt_type): {len(novel_to_filings)}\n")
print(f"{'raw_filing_label':<60} {'stmt':<5} {'sec':<22} {'#flgs':<5} value          top candidates")
print("-" * 200)
for key in sorted(novel_to_filings.keys(), key=lambda k: (-len(novel_to_filings[k]), k[0])):
    raw, stmt = key
    n_flg = len(novel_to_filings[key])
    cands = novel_top_candidates.get(key, [])
    cand_str = ", ".join(f"'{c[0]}'@{c[1]:.2f}" for c in cands if c[0] is not None and c[1] is not None)
    val = novel_value_sample.get(key)
    sec = novel_section.get(key, "")
    print(f"{raw[:60]:<60} {stmt:<5} {sec:<22} {n_flg:<5} {str(val)[:14]:<14}  {cand_str[:100]}")
