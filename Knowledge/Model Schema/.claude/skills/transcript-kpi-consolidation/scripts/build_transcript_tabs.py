"""STEP 2 — add one worksheet tab per transcript to {TICKER}_disclosures.xlsx.

Usage:  python build_transcript_tabs.py {TICKER}

Reads the per-transcript digest JSONs and writes one worksheet each (4-section
layout: Event/Date header, QUANTITATIVE, QUALITATIVE, Q&A). Idempotent — any
existing transcript tabs (A1 == 'Event') are removed and rebuilt; the KPI
Consolidated sheet, the MDA Disclosures tab and any user tabs are preserved.
"""
import json, glob, re, os, sys
import openpyxl
from openpyxl.styles import Font, PatternFill

if len(sys.argv) < 2:
    sys.exit("usage: python build_transcript_tabs.py {TICKER}")
TICKER = sys.argv[1].upper()

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_SCHEMA = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
BRAIN_ROOT = os.path.abspath(os.path.join(MODEL_SCHEMA, "..", ".."))
DIGESTS = os.path.join(MODEL_SCHEMA, "Ticker Libraries", TICKER, "MDA and Other",
                       "transcript_digests")
WB_PATH = os.path.join(BRAIN_ROOT, "Knowledge", "Model Outputs", TICKER,
                       f"{TICKER}_disclosures.xlsx")

ILLEGAL = re.compile(r'[\[\]:\*\?/\\]')


def clean_label(sn):
    s = re.sub(r'^\d{4}-\d{2}-\d{2}\s+', '', str(sn))
    s = re.sub(r'^\d{1,3}\s+', '', s)
    return s.strip()


def cell(v):
    return v if v is None or isinstance(v, (str, int, float)) else str(v)


def is_section(v):
    return isinstance(v, str) and v.strip().upper().split()[0:1] in (
        ['QUANTITATIVE'], ['QUALITATIVE'], ['Q&A'])


def main():
    files = sorted(glob.glob(os.path.join(DIGESTS, "*.json")))
    if not files:
        sys.exit(f"no digests at {DIGESTS} — run STEP 1 (extract) first")
    if not os.path.exists(WB_PATH):
        sys.exit(f"workbook not found: {WB_PATH}")

    frags = [json.load(open(f, encoding='utf-8')) for f in files]
    frags.sort(key=lambda d: (str(d.get('date', '')), d.get('index', 0)))

    wb = openpyxl.load_workbook(WB_PATH)
    # drop existing transcript tabs (A1 == 'Event'); keep everything else
    for sn in list(wb.sheetnames):
        if str(wb[sn].cell(1, 1).value).strip().lower() == 'event':
            del wb[sn]
    kept = list(wb.sheetnames)

    hdr_fill = PatternFill('solid', fgColor='D9D9D9')
    used, new_titles = set(), []
    for r, d in enumerate(frags, 1):
        name = ILLEGAL.sub('', f"{r:02d} {clean_label(d.get('sheet_name', d.get('event', '')))}")[:31].strip()
        base, k = name, 2
        while name.lower() in used:
            suf = f" ({k})"
            name = base[:31 - len(suf)] + suf
            k += 1
        used.add(name.lower())
        new_titles.append(name)
        ws = wb.create_sheet(title=name)
        for row in d.get('rows', []):
            ws.append([cell(x) for x in row] if row else [])
        for cr in ws.iter_rows():
            v = cr[0].value
            if is_section(v):
                for c in cr:
                    c.font = Font(bold=True, size=11)
                    c.fill = hdr_fill
            elif v in ('Event', 'Date'):
                cr[0].font = Font(bold=True)
        ws.column_dimensions['A'].width = 46
        for col in 'BCDEFGH':
            ws.column_dimensions[col].width = 15

    # newest-first ordering is finalized by build_kpi_sheet.py; here just append
    wb._sheets = [wb[t] for t in kept] + [wb[t] for t in new_titles]
    wb.save(WB_PATH)
    print(f"[{TICKER}] wrote {len(new_titles)} transcript tabs; "
          f"total sheets: {len(wb.sheetnames)}")


if __name__ == "__main__":
    main()
