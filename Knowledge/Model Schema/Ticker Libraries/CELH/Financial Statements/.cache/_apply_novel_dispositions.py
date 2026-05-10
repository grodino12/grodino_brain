"""Apply triage dispositions for CELH 2021-FY / 2022-FY backfill onboarding.

Touches:
  - generic_line_item_mappings.json (alias adds + 2 new canonicals)
  - Ticker Libraries/CELH/.../decisions_ledger.json (8 new ticker-specific rows)

Decisions per user batch triage 2026-05-10. See handoff doc for rationale.
"""
import json
from datetime import date
from pathlib import Path

LIB = Path(r"C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\pattern_libraries\generic_line_item_mappings.json")
LEDGER = Path(r"C:\Users\rodin\Desktop\Brain\Knowledge\Model Schema\Ticker Libraries\CELH\Financial Statements\decisions_ledger.json")
TODAY = "2026-05-10"

# Aliases to add to existing canonicals. key = rule_id; value = list of new aliases.
ALIAS_ADDS = {
    "GEN-CF-001": ["net (loss) income"],  # Net Income (Loss) on CF
    "GEN-BS-014": ["long-term security deposits", "long term security deposits"],  # Other Non-Current Assets BS
    "GEN-CF-008": [
        "deferred tax-net", "deferred tax liability-net", "deferred tax asset-net",
        "deferred tax liability net",
    ],  # (Benefit) Provision for Deferred Income Taxes CF
    "GEN-CF-017": [
        "deposits and other current liabilities",
        "deposits/deferred revenue and other current liabilities",
    ],  # Other Current Liabilities CF
    "GEN-CF-031": ["proceeds from capital raise"],  # Proceeds from Issuance of Common Stock CF
    "GEN-IS-006": [
        "amortization of discount on bonds payable",
        "interest expense on bonds",
        "interest on other obligations",
    ],  # Interest Income (Expense) IS
    "GEN-IS-012": ["less: dividends paid to series a convertible preferred stockholders"],  # Preferred Dividends IS
}

# New canonicals to add to the generic library.
NEW_CANONICALS = [
    {
        "rule_id": "GEN-CF-082",
        "model_sheet": "CASH FLOW",
        "model_label": "Goodwill Impairment",
        "aliases": ["goodwill impairment", "impairment of goodwill", "goodwill"],
        "filing_section": "operating",
        "sign_convention": "negative",
        "us_gaap_concept": "GoodwillImpairmentLoss",
        "_note": "Added 2026-05-10 from CELH 2021/2022 backfill. Skip the bare 'goodwill' alias if it appears on BS — CF-only.",
    },
    {
        "rule_id": "GEN-IS-031",
        "model_sheet": "ANNL P&L",
        "model_label": "Gain (Loss) on Lease Cancellations",
        "aliases": ["gain on lease cancellations", "gain (loss) on lease cancellations", "gain on lease termination"],
        "filing_section": "non_operating",
        "us_gaap_concept": "GainLossOnTerminationOfLease",
        "_note": "Added 2026-05-10. IS surface of the lease-termination gain. CF surface remains on MAP-CF-060 in CELH ledger.",
    },
]

# New ticker-specific rows for the CELH decisions ledger.
CELH_NEW_ROWS = [
    {
        "rule_id": "NEW-CF-CELH-CHINA",
        "filing_term_normalized": "gain on china transaction",
        "model_sheet": "CASH FLOW",
        "new_row_label": "Gain on China Transaction",
        "section": "operating",
        "sign_convention": "negative",  # non-cash gain add-back
        "position_note": "In operating-activities non-cash adjustments. CELH-specific (one-time 2021 transaction).",
        "decided_date": TODAY,
        "note": "us-gaap:GainLossOnInvestments concept on CF; backfill 2021-FY/Q2/Q3 only.",
    },
    {
        "rule_id": "NEW-CF-CELH-BONDS",
        "filing_term_normalized": "payments on bonds payable",
        "model_sheet": "CASH FLOW",
        "new_row_label": "Payments on Bonds Payable",
        "section": "financing",
        "sign_convention": "negative",
        "position_note": "In financing-activities. CELH-specific bond accounting pre-Pepsi.",
        "decided_date": TODAY,
        "note": "celh:PaymentsOnBondsPayable concept; backfill 2021-FY / 2022-FY.",
    },
    {
        "rule_id": "NEW-CF-CELH-S16B",
        "filing_term_normalized": "net proceeds from collection of section 16b short swing profit",
        "model_sheet": "CASH FLOW",
        "new_row_label": "Section 16(b) Short-Swing Profit Recovery",
        "section": "financing",
        "position_note": "In financing-activities other inflows. CELH-specific (one-time recoveries from insiders).",
        "decided_date": TODAY,
        "note": "celh:NetProceedsFromCollectionOfSectionShortSwingProfit; backfill 2021-FY / 2022-FY.",
    },
    {
        "rule_id": "NEW-BS-CELH-FREIGHT",
        "aliases": ["accrued freight", "freight"],
        "model_sheet": "BALANCE SHEET",
        "new_row_label": "Accrued Freight",
        "section": "current_liabilities",
        "position_note": "Current liabilities, accrued-expense detail.",
        "decided_date": TODAY,
        "note": "celh:AccruedFreight / celh:Freight; backfill 2021-FY / 2022-FY. Both aliases route to the same row.",
    },
    {
        "rule_id": "NEW-BS-CELH-PEPSI",
        "filing_term_normalized": "due to pepsi",
        "model_sheet": "BALANCE SHEET",
        "new_row_label": "Due to Pepsi",
        "section": "current_liabilities",
        "position_note": "Related-party payable to Pepsi (post-Aug 2022 distribution agreement).",
        "decided_date": TODAY,
        "note": "us-gaap:DueToRelatedPartiesCurrentAndNoncurrent; first appears 2022-FY.",
    },
    {
        "rule_id": "NEW-BS-CELH-DEPOSIT",
        "filing_term_normalized": "state beverage container deposit",
        "model_sheet": "BALANCE SHEET",
        "new_row_label": "State Beverage Container Deposit",
        "section": "current_liabilities",
        "position_note": "Accrued-liability detail unique to beverage manufacturers (state container-deposit programs).",
        "decided_date": TODAY,
        "note": "celh:StateBeverageContainerDeposit; appears 2022-FY.",
    },
    {
        "rule_id": "NEW-BS-CELH-UNBILLED",
        "filing_term_normalized": "unbilled purchases",
        "model_sheet": "BALANCE SHEET",
        "new_row_label": "Unbilled Purchases",
        "section": "current_liabilities",
        "position_note": "Accrued-liability detail; goods received not yet invoiced.",
        "decided_date": TODAY,
        "note": "celh:UnbilledPurchases; backfill 2021-FY / 2022-FY.",
    },
    {
        "rule_id": "NEW-BS-CELH-VAT",
        "filing_term_normalized": "vat payable",
        "model_sheet": "BALANCE SHEET",
        "new_row_label": "VAT Payable",
        "section": "current_liabilities",
        "position_note": "Accrued-liability detail; European VAT obligation.",
        "decided_date": TODAY,
        "note": "celh:ValueAddedTaxPayment; appears 2022-FY.",
    },
]


def main():
    # --- Apply library changes ---
    lib = json.loads(LIB.read_text(encoding="utf-8"))
    by_id = {r["rule_id"]: r for r in lib["mappings"]}
    alias_count = 0
    for rid, new_aliases in ALIAS_ADDS.items():
        if rid not in by_id:
            print(f"WARN: rule_id {rid} not found in library — skipping alias add")
            continue
        existing = set(a.lower() for a in by_id[rid].get("aliases", []))
        added = []
        for a in new_aliases:
            if a.lower() not in existing:
                by_id[rid].setdefault("aliases", []).append(a)
                added.append(a)
                alias_count += 1
        if added:
            print(f"  + {rid} aliases: {added}")
    # New canonicals
    existing_ids = {r["rule_id"] for r in lib["mappings"]}
    new_added = 0
    for nc in NEW_CANONICALS:
        if nc["rule_id"] in existing_ids:
            print(f"WARN: canonical {nc['rule_id']} already exists — skipping")
            continue
        lib["mappings"].append({k: v for k, v in nc.items() if not k.startswith("_")})
        print(f"  + new canonical: {nc['rule_id']} '{nc['model_label']}'")
        new_added += 1
    lib["last_updated"] = TODAY
    LIB.write_text(json.dumps(lib, indent=2), encoding="utf-8")
    print(f"library: added {alias_count} aliases + {new_added} new canonicals")

    # --- Apply ledger changes ---
    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    existing_ledger_ids = {r["rule_id"] for r in led.get("new_rows", [])}
    added = 0
    for row in CELH_NEW_ROWS:
        if row["rule_id"] in existing_ledger_ids:
            print(f"WARN: ledger row {row['rule_id']} already exists — skipping")
            continue
        led["new_rows"].append(row)
        print(f"  + ledger new_row: {row['rule_id']} '{row['new_row_label']}'")
        added += 1
    led["last_updated"] = TODAY
    led["_last_updated"] = TODAY
    LEDGER.write_text(json.dumps(led, indent=2), encoding="utf-8")
    print(f"ledger: added {added} new rows")


if __name__ == "__main__":
    main()
