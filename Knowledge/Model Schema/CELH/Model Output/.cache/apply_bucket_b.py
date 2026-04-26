"""Apply Bucket B + Mezzanine memo entries to CELH ledger."""
import json
from datetime import date

LEDGER = r'C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/CELH/decisions_ledger.json'
with open(LEDGER, encoding='utf-8') as f:
    led = json.load(f)

led.setdefault('mappings', [])
led.setdefault('new_rows', [])
today = date.today().isoformat()

new_entries = [
    # === Pepsi Mezzanine Equity memo entries ===
    {
        'rule_id': 'NEW-BS-MZ-PAR',
        'aliases': [
            'mezzanine equity, par value (in usd per share)',
            'mezzanine equity, par value (in usd per share) | $ / shares',
            'temporary equity par or stated value per share',
        ],
        'model_sheet': 'BALANCE SHEET',
        'new_row_label': 'Pepsi Mezzanine Equity - Par Value ($/share)',
        'section': 'mezzanine',
        'memo': True,
        'position_note': 'In mezzanine equity disclosure block.',
        'decided_date': today,
        'note': 'Pepsi Series A convertible preferred par value. Memo - per-share value, never sums.',
    },
    {
        'rule_id': 'NEW-BS-MZ-SHO',
        'aliases': [
            'mezzanine equity, shares outstanding (in shares)',
            'mezzanine equity, shares outatanding (in shares)',
            'temporary equity shares outstanding',
        ],
        'model_sheet': 'BALANCE SHEET',
        'new_row_label': 'Pepsi Mezzanine Equity - Shares Outstanding',
        'section': 'mezzanine',
        'memo': True,
        'position_note': 'In mezzanine equity disclosure block.',
        'decided_date': today,
        'note': 'Pepsi Series A convertible preferred shares outstanding. Memo. The "outatanding" alias covers a CELH typo.',
    },
    {
        'rule_id': 'NEW-BS-MZ-SHI',
        'aliases': [
            'mezzanine equity, shares issued (in shares)',
            'temporary equity, shares issued',
            'temporary equity shares issued',
        ],
        'model_sheet': 'BALANCE SHEET',
        'new_row_label': 'Pepsi Mezzanine Equity - Shares Issued',
        'section': 'mezzanine',
        'memo': True,
        'position_note': 'In mezzanine equity disclosure block. Older filings labeled this "Temporary Equity, Shares Issued".',
        'decided_date': today,
        'note': 'Pepsi Series A convertible preferred shares issued. Memo.',
    },
    {
        'rule_id': 'NEW-BS-MZ-RED',
        'aliases': [
            'mezzanine equity, redemption amount',
            'mezzanine equity, redemption amount | $',
            'preferred stock, redemption amount',
            'temporary equity aggregate amount of redemption requirement',
        ],
        'model_sheet': 'BALANCE SHEET',
        'new_row_label': 'Pepsi Mezzanine Equity - Redemption Amount',
        'section': 'mezzanine',
        'memo': True,
        'position_note': 'In mezzanine equity disclosure block.',
        'decided_date': today,
        'note': 'Pepsi Series A convertible preferred redemption value. Memo. Older filings tagged as Preferred Stock before mezzanine reclass.',
    },
    {
        'rule_id': 'NEW-BS-MZ-DIV',
        'aliases': [
            'mezzanine equity, cumulative dividend (percentage)',
            'mezzanine equity, cummulative dividend (percentage)',
            'mezzanine equity, cumulative dividend (as a percent)',
            'preferred stock, cumulative dividend percentage',
            'temporary equity cumulative dividend percentage',
        ],
        'model_sheet': 'BALANCE SHEET',
        'new_row_label': 'Pepsi Mezzanine Equity - Cumulative Dividend %',
        'section': 'mezzanine',
        'memo': True,
        'position_note': 'In mezzanine equity disclosure block.',
        'decided_date': today,
        'note': 'Pepsi Series A convertible preferred cumulative dividend rate. Memo. Aliases cover CELH typo "cummulative" + older Preferred Stock labeling.',
    },

    # === B11 — real investing CF line (Rockstar/Pepsi WC trueup) ===
    {
        'rule_id': 'NEW-CF-PEPSI-WC',
        'aliases': [
            'net working capital estimate received from pepsi related to the rockstar acquisition',
            'net working capital estimate received from pepsi',
            'working capital estimate received from pepsi',
        ],
        'model_sheet': 'CASH FLOW',
        'new_row_label': 'Working Capital Estimate from Pepsi (Rockstar)',
        'section': 'investing',
        'position_note': 'In Investing Activities section, after Alani Nu Acquisition net of cash. Real investing inflow.',
        'decided_date': today,
        'note': 'CELH-specific. Rockstar acquisition (2022) had a WC trueup mechanism with Pepsi as seller; CELH receiving cash counts as investing inflow.',
    },

    # === B7-B10, B12 — Alani Nu / Pepsi-pref supplemental noncash disclosures ===
    {
        'rule_id': 'NEW-CF-MZ-AC1',
        'aliases': [
            'acquisition date fair value of alani nu contingent consideration',
            'estimated fair value of contingent consideration in connection with the acquisition',
            'estimated fair value of contingent consideration in connection',
        ],
        'model_sheet': 'CASH FLOW',
        'new_row_label': 'Alani Nu Contingent Consideration',
        'section': 'cash_other',
        'memo': True,
        'position_note': 'In Supplemental schedule of noncash investing and financing activities.',
        'decided_date': today,
        'note': 'CELH-specific (Alani Nu acquisition 2025). Memo - non-cash purchase-price-allocation disclosure.',
    },
    {
        'rule_id': 'NEW-CF-MZ-AC2',
        'aliases': [
            'estimated fair value of share consideration issued in connection with the acquisition',
            'estimated fair value of share consideration issued in connection',
            'fair value of share consideration issued in connection with the acquisition',
        ],
        'model_sheet': 'CASH FLOW',
        'new_row_label': 'Fair Value of Alani Nu Shares',
        'section': 'cash_other',
        'memo': True,
        'position_note': 'In Supplemental schedule of noncash investing and financing activities. $721M+ stock issued to Alani Nu sellers - non-cash.',
        'decided_date': today,
        'note': 'CELH-specific (Alani Nu acquisition 2025). Memo - stock-component of acquisition consideration.',
    },
    {
        'rule_id': 'NEW-CF-MZ-AC3',
        'aliases': [
            'preliminary deferred payment owed to sellers in connection with the acquisition',
            'preliminary deferred payment owed to sellers in connection',
            'deferred payment owed to sellers in connection with the acquisition',
        ],
        'model_sheet': 'CASH FLOW',
        'new_row_label': 'Preliminary Deferred Payment to Sellers',
        'section': 'cash_other',
        'memo': True,
        'position_note': 'In Supplemental schedule of noncash investing and financing activities.',
        'decided_date': today,
        'note': 'CELH-specific (Alani Nu acquisition 2025). Memo - deferred-payment portion of acquisition consideration.',
    },
    {
        'rule_id': 'NEW-CF-MZ-PFV',
        'aliases': [
            'fair value of series a preferred stock modification',
        ],
        'model_sheet': 'CASH FLOW',
        'new_row_label': 'Series A Preferred Stock Modification',
        'section': 'cash_other',
        'memo': True,
        'position_note': 'In Supplemental schedule of noncash investing and financing activities.',
        'decided_date': today,
        'note': 'CELH-specific (Pepsi Series A pref). Memo - non-cash modification charge.',
    },
]

existing_rids = {e.get('rule_id') for e in led.get('mappings', []) + led.get('new_rows', [])}
added = 0
for entry in new_entries:
    if entry['rule_id'] in existing_rids:
        print(f'SKIP {entry["rule_id"]}: already present')
        continue
    led['new_rows'].append(entry)
    added += 1
    print(f'OK   {entry["rule_id"]}: {entry["new_row_label"]}')

led['_last_updated'] = today
led['last_updated'] = today

with open(LEDGER, 'w', encoding='utf-8') as f:
    json.dump(led, f, indent=2)
    f.write('\n')

print(f'\nCELH ledger: {len(led["mappings"])} mappings + {len(led["new_rows"])} new_rows. Added {added}.')
