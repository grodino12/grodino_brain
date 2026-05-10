"""Aggregate GOOG novels across 28 filings into a single deduped, ranked report.

Group key: (statement_type, raw_filing_label) — same label on the same statement
type is "the same novel" even if it appears in 28 separate filings.

Output: markdown report sorted by (statement_type bucket, count desc, label).
For each unique novel: count of filings, list of filings (sorted), section,
us-gaap concept (from line_hint), top 3 nearest matches, sample value.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

CACHE = Path(r"C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\Ticker Libraries\GOOG\.cache")
OUT = CACHE.parent / "novels_aggregate.md"


def load_all() -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for p in sorted(CACHE.glob("novels_*.json")):
        period = p.stem.removeprefix("novels_")
        with p.open(encoding="utf-8") as f:
            out.append((period, json.load(f)))
    return out


def main() -> None:
    reports = load_all()
    # group: (stmt, label) -> {filings: set[period], section, line_hints, nearest, samples}
    grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "filings": set(),
            "sections": set(),
            "line_hints": set(),
            "nearest": [],
            "values": [],
        }
    )

    total_novel_rows = 0
    for period, report in reports:
        for n in report.get("novels", []):
            total_novel_rows += 1
            key = (n["statement_type"], n["raw_filing_label"])
            g = grouped[key]
            g["filings"].add(period)
            if n.get("section"):
                g["sections"].add(n["section"])
            if n.get("citation", {}).get("line_hint"):
                g["line_hints"].add(n["citation"]["line_hint"].split("|")[0].strip())
            if not g["nearest"]:
                g["nearest"] = n.get("nearest_matches", [])
            if len(g["values"]) < 3:
                g["values"].append((period, n.get("value")))

    # Stats
    n_filings = len(reports)
    n_unique = len(grouped)

    # Order: BS, IS, CF (by section), then by count desc, then by label
    stmt_order = {"BS": 0, "IS": 1, "CF": 2}
    items = sorted(
        grouped.items(),
        key=lambda kv: (stmt_order.get(kv[0][0], 99), -len(kv[1]["filings"]), kv[0][1]),
    )

    lines: list[str] = []
    lines.append("# GOOG novel report — aggregated across 28 filings (2019-Q1 → 2025-Q3)")
    lines.append("")
    lines.append(f"- **Filings reconciled:** {n_filings}")
    lines.append(f"- **Total novel rows surfaced:** {total_novel_rows}")
    lines.append(f"- **Unique novels (by `statement_type` + `raw_filing_label`):** {n_unique}")
    lines.append(f"- **Pre-iXBRL gap:** 2018-Q1 / Q2 / Q3 / FY skipped (see roadmap Later horizon §9)")
    lines.append("")
    lines.append("Each novel below shows: filings hit / total, section, us-gaap concept(s),")
    lines.append("top-3 fuzzy candidates, sample values from earliest filings.")
    lines.append("")

    last_stmt = None
    for (stmt, label), g in items:
        if stmt != last_stmt:
            lines.append(f"## {stmt} novels ({sum(1 for k in grouped if k[0] == stmt)} unique)")
            lines.append("")
            last_stmt = stmt
        n_hit = len(g["filings"])
        sections = ", ".join(sorted(g["sections"])) or "—"
        concepts = ", ".join(sorted(g["line_hints"])) or "—"
        nearest = "; ".join(f"{m[0]} ({m[1]:.2f})" for m in g["nearest"][:3]) or "—"
        sample_str = ", ".join(f"{p}={v}" for p, v in g["values"])
        lines.append(f"### `{label}`  ({n_hit}/{n_filings} filings)")
        lines.append(f"- **Section:** {sections}")
        lines.append(f"- **us-gaap concept(s):** {concepts}")
        lines.append(f"- **Nearest library matches:** {nearest}")
        lines.append(f"- **Sample values:** {sample_str}")
        lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")
    print(f"  filings={n_filings}, total_novel_rows={total_novel_rows}, unique_novels={n_unique}")


if __name__ == "__main__":
    main()
