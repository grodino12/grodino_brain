"""Phase 3 migration: move generic-covered CELH ledger entries into the
generic library (decisions_ledger.json -> pattern_libraries/generic_line_item_mappings.json).

For each CELH mapping/new_row that is NOT in CELH_SPECIFIC_KEEP:
  1. Resolve its corresponding generic rule_id (by model_label match, then by alias match).
  2. If the CELH entry's filing_term_normalized is not in the generic's aliases, ADD it.
  3. Delete the CELH entry from decisions_ledger.json.

For CELH-specific KEEP entries:
  - Strip `model_row`.
  - Apply label rename.

Also strip `model_row` from the `renames` section (now audit-only).
Also strip `model_row` from any remaining structural_decisions that reference rows (none today).

Run from: C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema
Pipeline smoke test after: reconcile -> validate both filings, confirm 48/48 PASS.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(r"C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema")
LEDGER_PATH = ROOT / "CELH" / "decisions_ledger.json"
GENERIC_PATH = ROOT / "pattern_libraries" / "generic_line_item_mappings.json"

# Matches reconcile.normalize_label (needs to stay in sync).
CLUTTER_RE = re.compile(
    r"(?:[,;]\s*)?\$?[\d.,]*\s*"
    r"(?:par\s+value|cumulative\s+dividends|liquidation\s+preference|aggregate\s+liquidation"
    r"|[\d,]+\s+shares\s+\w+)"
    r".*$",
    re.IGNORECASE | re.DOTALL,
)
FOOTNOTE_RE = re.compile(r"\[\d+\]|\(\d+\)")

def normalize_label(label: str) -> str:
    label = FOOTNOTE_RE.sub("", label)
    label = CLUTTER_RE.sub("", label)
    label = label.lower()
    label = re.sub(r"\b(the|our)\b", " ", label)
    label = re.sub(r"[^\w\s\-]", " ", label)
    label = " ".join(label.split())
    return label.strip()


def sheet_group(sheet: str) -> str:
    s = sheet.lower()
    if "balance sheet" in s: return "BS"
    if "cash flow" in s: return "CF"
    if "p&l" in s: return "IS"
    return "OTHER"


# CELH ticker-specific entries to KEEP (not in generic library).
CELH_KEEP = {
    "MAP-IS-011",  # Interest Income on Note Receivable (maps to Interest Income row)
    "MAP-BS-005",  # Deferred Other Costs - Current
    "MAP-BS-012",  # Deferred Other Costs - Non-Current
    "NEW-BS-009",  # Accrued Distributor Termination Fees (BS)
    "MAP-CF-005",  # Amortization of Deferred Other Costs (CF)
    "MAP-CF-038",  # Accrued Distributor Termination (CF)
    "NEW-CF-009",  # Acquisition of Big Beverages
    "MAP-CF-060",  # Gain (Loss) on Lease Cancellations
    "MAP-CF-036",  # LEGACY: Change in A/P and Accrued (pre-FY2023 combined row). Keep to
                   #         preserve the legacy memo separation per STRUCT-CF-001.
}

# Sign-agnostic label renames for KEEP entries only (generic-library labels win for superseded).
KEEP_RENAMES: dict[str, str] = {
    "MAP-IS-011": "Interest Income (Expense)",  # match generic canonical label
    "MAP-BS-005": "Deferred Other Costs - Current",
    "MAP-BS-012": "Deferred Other Costs - Non-Current",
    "MAP-CF-060": "Gain (Loss) on Lease Cancellations",
}

# Also rename new_row labels where applicable (none today — NEW-BS-009 + NEW-CF-009 already have final labels).


def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def save_json(p: Path, data: dict) -> None:
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def build_generic_key_index(generic: dict) -> dict[tuple[str, str], dict]:
    """{(normalized_alias, sheet_group): generic_entry_dict} — mutable refs for inline alias add."""
    idx: dict[tuple[str, str], dict] = {}
    for entry in generic["mappings"]:
        sg = sheet_group(entry["model_sheet"])
        for alias in entry.get("aliases", []):
            idx[(normalize_label(alias), sg)] = entry
    return idx


def resolve_generic_entry(
    celh_entry: dict, generic: dict, generic_key_idx: dict[tuple[str, str], dict],
    label_key: str,
) -> dict | None:
    """Pick the generic entry that covers a CELH entry. Priority:
      1. Exact normalized-alias match on (filing_term, sheet_group) via key index.
      2. Label match on (model_label, sheet_group).
    """
    sg = sheet_group(celh_entry["model_sheet"])
    ft_norm = celh_entry["filing_term_normalized"]

    hit = generic_key_idx.get((normalize_label(ft_norm), sg))
    if hit is not None:
        return hit

    # Fallback: match by label match against generic label-set
    celh_label = celh_entry.get(label_key, "")
    for gen in generic["mappings"]:
        if sheet_group(gen["model_sheet"]) == sg and gen["model_label"].lower() == celh_label.lower():
            return gen
    return None


def ensure_alias(generic_entry: dict, filing_term_normalized: str) -> bool:
    """Add filing_term_normalized as an alias on generic_entry if no existing alias normalizes
    to the same key. Returns True if alias was added."""
    existing = {normalize_label(a) for a in generic_entry.get("aliases", [])}
    key = normalize_label(filing_term_normalized)
    if key in existing:
        return False
    generic_entry.setdefault("aliases", []).append(filing_term_normalized)
    return True


def main() -> None:
    ledger = load_json(LEDGER_PATH)
    generic = load_json(GENERIC_PATH)
    generic_key_idx = build_generic_key_index(generic)

    kept_mappings: list[dict] = []
    kept_new_rows: list[dict] = []
    kept_renames: list[dict] = []

    aliases_added: list[str] = []
    dropped: list[str] = []
    unresolved: list[str] = []  # entries we couldn't match to any generic (need manual attention)

    # --- mappings ---
    for entry in ledger["mappings"]:
        rid = entry["rule_id"]
        entry.pop("model_row", None)

        # Respect previously-superseded entries: drop outright (audit trail in prior handoffs).
        if "superseded_by" in entry:
            dropped.append(f"{rid} (prior superseded_by={entry['superseded_by']})")
            continue

        if rid in CELH_KEEP:
            if rid in KEEP_RENAMES:
                entry["model_label"] = KEEP_RENAMES[rid]
            kept_mappings.append(entry)
            continue

        # Generic-covered: verify generic has an alias (or add one), then drop.
        gen = resolve_generic_entry(entry, generic, generic_key_idx, label_key="model_label")
        if gen is None:
            unresolved.append(f"{rid}: {entry['filing_term_normalized']!r} -> {entry['model_label']!r}")
            kept_mappings.append(entry)  # conservative: keep for now
            continue
        if ensure_alias(gen, entry["filing_term_normalized"]):
            aliases_added.append(f"{gen['rule_id']} += {entry['filing_term_normalized']!r}  (from {rid})")
        dropped.append(f"{rid} -> merged into {gen['rule_id']}")

    # --- new_rows ---
    for entry in ledger["new_rows"]:
        rid = entry["rule_id"]
        entry.pop("model_row", None)

        if "superseded_by" in entry:
            dropped.append(f"{rid} (prior superseded_by={entry['superseded_by']})")
            continue

        if rid in CELH_KEEP:
            kept_new_rows.append(entry)
            continue

        gen = resolve_generic_entry(entry, generic, generic_key_idx, label_key="new_row_label")
        if gen is None:
            unresolved.append(f"{rid}: {entry['filing_term_normalized']!r} -> {entry['new_row_label']!r}")
            kept_new_rows.append(entry)
            continue
        if ensure_alias(gen, entry["filing_term_normalized"]):
            aliases_added.append(f"{gen['rule_id']} += {entry['filing_term_normalized']!r}  (from {rid})")
        dropped.append(f"{rid} -> merged into {gen['rule_id']}")

    # --- renames (cleanup: strip model_row; keep for audit only unless we want to purge) ---
    for entry in ledger.get("renames", []):
        entry.pop("model_row", None)
        kept_renames.append(entry)

    # --- structural_decisions (no model_row fields today, but future-proof) ---
    for entry in ledger.get("structural_decisions", []):
        entry.pop("model_row", None)

    ledger["mappings"] = kept_mappings
    ledger["new_rows"] = kept_new_rows
    ledger["renames"] = kept_renames

    # Update metadata
    ledger["last_updated"] = "2026-04-23T00:00:00Z"
    ledger["_last_updated"] = "2026-04-23"
    phase3_note = (
        " | Phase 3 (2026-04-23): generic-covered mappings moved to pattern_libraries/"
        "generic_line_item_mappings.json; model_row stripped throughout; CELH-specific entries "
        "retained with sign-agnostic labels."
    )
    if phase3_note not in ledger.get("notes", ""):
        ledger["notes"] = ledger.get("notes", "") + phase3_note

    generic["last_updated"] = "2026-04-23"

    save_json(LEDGER_PATH, ledger)
    save_json(GENERIC_PATH, generic)

    # --- Summary ---
    print(f"=== Phase 3 migration complete ===")
    print(f"Kept (CELH-specific)       : {len(kept_mappings)} mappings + {len(kept_new_rows)} new_rows")
    print(f"Dropped (moved to generic) : {len(dropped)}")
    print(f"Aliases added to generic   : {len(aliases_added)}")
    print(f"Unresolved (kept, check)   : {len(unresolved)}")
    print()
    if aliases_added:
        print("--- Aliases added ---")
        for a in aliases_added:
            print(f"  {a}")
    print()
    if unresolved:
        print("--- UNRESOLVED (review needed) ---")
        for u in unresolved:
            print(f"  {u}")
    print()
    print("--- Kept (CELH-specific) ---")
    for e in kept_mappings:
        print(f"  {e['rule_id']:12s}  {e['filing_term_normalized']!r:60s}  -> {e['model_label']!r}")
    for e in kept_new_rows:
        print(f"  {e['rule_id']:12s}  {e['filing_term_normalized']!r:60s}  -> {e['new_row_label']!r}  (new_row)")


if __name__ == "__main__":
    main()
