"""Catalog all novels across CELH filings + dedupe."""
import json
from pathlib import Path
from collections import defaultdict

CACHE = Path("C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/CELH/Model Output/.cache")
files = sorted(CACHE.glob("novels_*.json"))

# unique novel keys: (raw_filing_label_normalized, sheet_group)
novel_to_filings = defaultdict(set)  # (raw_label, sheet) -> {filing_labels}
novel_top_candidates = {}            # (raw_label, sheet) -> list of (label, score) from first appearance
novel_value_sample = {}              # (raw_label, sheet) -> a sample value
novel_section = {}                   # (raw_label, sheet) -> section

for fp in files:
    label = fp.stem.replace("novels_", "")
    with open(fp, encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("novels", []) if isinstance(data, dict) else []
    for n in items:
        raw = n.get("raw_filing_label", "")
        sheet = n.get("sheet_group", "?")
        sec = n.get("section", "?")
        key = (raw, sheet)
        novel_to_filings[key].add(label)
        if key not in novel_top_candidates:
            cands = n.get("top_candidates", []) or []
            novel_top_candidates[key] = [(c.get("canonical_label"), c.get("score")) for c in cands[:3]]
            novel_value_sample[key] = n.get("value")
            novel_section[key] = sec

# Print sorted by frequency (most filings affected first)
print(f"Total unique novel entries (raw_label × sheet_group): {len(novel_to_filings)}\n")
print(f"{'raw_filing_label':<60} {'sheet':<10} {'sec':<22} {'#flgs':<5} value          top candidates")
print("-" * 180)
for key in sorted(novel_to_filings.keys(), key=lambda k: (-len(novel_to_filings[k]), k[0])):
    raw, sheet = key
    n_flg = len(novel_to_filings[key])
    cands = novel_top_candidates.get(key, [])
    cand_str = ", ".join(f"'{c[0]}'@{c[1]:.2f}" for c in cands if c[0])
    val = novel_value_sample.get(key)
    sec = novel_section.get(key, "")
    print(f"{raw[:60]:<60} {sheet:<10} {sec:<22} {n_flg:<5} {str(val):<14}  {cand_str[:80]}")
