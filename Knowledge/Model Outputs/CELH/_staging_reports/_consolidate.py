"""Build a 'KPI Consolidated' sheet in CELH_disclosures.xlsx.

Reads the 69 staging digest JSONs, normalizes metric + period, and writes a
metric-time-series matrix: rows = normalized KPI, columns = period (chrono),
cell = the 'Current' reported value. Quantitative KPIs only.

Period can live in the row label ('Total Revenue Q4 2018') or in the column
header ('Q1 2022' / 'Q1 2021'); both styles are handled. Value/Period-only
color tables (channel stats, China items, guidance) are skipped.
On a (metric, period) collision, an earnings-call source wins over a
conference source; earnings sources never overwrite each other (first wins).
"""
import json, glob, re, os
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

HERE = os.path.dirname(os.path.abspath(__file__))
WB_PATH = os.path.join(os.path.dirname(HERE), "CELH_disclosures.xlsx")
SHEET = "KPI Consolidated"

PER_RE = re.compile(
    r'\b(Q[1-4])\s*[\'’]?\s*(20\d\d)\b'      # Q1 2022 / Q1'22-ish
    r'|\bFY\s*(20\d\d)\b'                          # FY2018
    r'|\b(9M)\s*(20\d\d)\b'                        # 9M 2018
    r'|\b(H[12])\s*(20\d\d)\b'                     # H1 2019
    r'|\bDec(?:ember)?\s*31?,?\s*(20\d\d)\b',      # Dec 31 2018 -> FYxxxx
    re.I)

ORD = {'Q1': 1, 'Q2': 2, 'H1': 2.5, 'Q3': 3, '9M': 3.5, 'H2': 3.5, 'Q4': 4, 'FY': 5}

UNIT_RE = re.compile(r'\s*\((?:\$M|\$|%|\$ ?M|in \$M|M)\)\s*$', re.I)

# light canonicalization of obvious synonyms
ALIAS = {
    'domestic / north american revenue': 'North America Revenue',
    'domestic / north america revenue': 'North America Revenue',
    'north american revenue': 'North America Revenue',
    'north america revenue': 'North America Revenue',
    'us / north america revenue': 'North America Revenue',
    'international revenue (total)': 'International Revenue',
    'total international revenue': 'International Revenue',
    'europe / nordics': 'Europe Revenue',
    'europe / nordics revenue': 'Europe Revenue',
    'europe revenue': 'Europe Revenue',
    'asia (incl. china royalties)': 'Asia Revenue',
    'asia revenue': 'Asia Revenue',
    'total revenue': 'Total Revenue',
    'revenue': 'Total Revenue',
    'gross profit': 'Gross Profit',
    'gross margin': 'Gross Margin',
    'net income': 'Net Income',
    'net income (loss)': 'Net Income',
    'adjusted ebitda': 'Adjusted EBITDA',
    'adj. ebitda': 'Adjusted EBITDA',
    'selling & marketing': 'Selling & Marketing',
    'sales & marketing': 'Selling & Marketing',
    'g&a': 'General & Administrative',
    'general & administrative': 'General & Administrative',
}

# core metrics surfaced at the top of the matrix, in this order
CORE = [
    'Total Revenue', 'North America Revenue', 'International Revenue',
    'Europe Revenue', 'Asia Revenue', 'Amazon Revenue',
    'Gross Profit', 'Gross Margin', 'Selling & Marketing',
    'General & Administrative', 'Net Income', 'Adjusted EBITDA',
    'Cash', 'Working Capital',
]

HEADER_TOKENS = {'prior yr', 'prior year', 'current', 'change', 'yoy', 'yoy %',
                 'value', 'period', 'qoq', 'qoq %', 'metric'}


def parse_period(text):
    """Return (canonical_label, sort_key) or None."""
    if text is None:
        return None
    m = PER_RE.search(str(text))
    if not m:
        return None
    g = m.groups()
    if g[0]:                       # Qn YYYY
        q, y = g[0].upper(), int(g[1])
        return (f"{q} {y}", y * 10 + ORD[q])
    if g[2]:                       # FY YYYY
        y = int(g[2]); return (f"FY{y}", y * 10 + ORD['FY'])
    if g[3]:                       # 9M YYYY
        y = int(g[4]); return (f"9M {y}", y * 10 + ORD['9M'])
    if g[5]:                       # Hn YYYY
        h, y = g[5].upper(), int(g[6])
        return (f"{h} {y}", y * 10 + ORD.get(h, 2.5))
    if g[7]:                       # Dec 31 YYYY -> fiscal year end
        y = int(g[7]); return (f"FY{y}", y * 10 + ORD['FY'])
    return None


def norm_metric(label):
    s = str(label)
    s = PER_RE.sub('', s)                       # drop any period token
    s = UNIT_RE.sub('', s)
    s = re.sub(r'\bex[- ]?(China|Asia|one-time|outbound freight)\b', '', s, flags=re.I)
    s = re.sub(r'\s{2,}', ' ', s).strip(' -/,')
    key = s.lower().strip()
    return ALIAS.get(key, s)


def is_number(v):
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str):
        return bool(re.fullmatch(r'-?\d[\d,]*\.?\d*%?', v.strip()))
    return False


def main():
    files = sorted(glob.glob(os.path.join(HERE, "*.json")))
    # matrix[metric][period] = (value, is_earnings_source)
    matrix = {}
    periods = {}          # label -> sort_key
    skipped_no_period = 0
    placed = 0

    for f in files:
        d = json.load(open(f, encoding='utf-8'))
        event = str(d.get('event', ''))
        is_earn = 'earning' in event.lower()
        rows = d.get('rows', [])
        in_quant = False
        cur_col = None        # column index of the 'Current' value
        hdr_period = None     # period from a period-style header

        for r in rows:
            if not r:
                continue
            c0 = str(r[0]).strip()
            if c0 == 'QUANTITATIVE':
                in_quant = True
                continue
            if c0.startswith('QUALITATIVE') or c0.startswith('Q&A'):
                in_quant = False
                continue
            if not in_quant or len(r) < 2:
                continue

            vals = r[1:]
            low = [str(x).strip().lower() for x in vals]

            # --- header row detection ---
            is_header = any(t in HEADER_TOKENS for t in low)
            per_in_hdr = [parse_period(x) for x in vals]
            has_hdr_period = any(per_in_hdr)

            if is_header or has_hdr_period:
                cur_col = None
                hdr_period = None
                # skip pure color tables (Value / Period only)
                meaningful = [t for t in low if t]
                if meaningful and set(meaningful) <= {'value', 'period'}:
                    continue
                if 'current' in low:                       # Prior/Current style
                    cur_col = low.index('current') + 1
                elif has_hdr_period:                        # period-header style
                    best = None
                    for i, p in enumerate(per_in_hdr):
                        if p and (best is None or p[1] > best[1]):
                            best = p; cur_col = i + 1
                    hdr_period = best[0] if best else None
                continue

            # --- data row ---
            if cur_col is None or cur_col >= len(r):
                continue
            value = r[cur_col]
            if value in (None, '', 'n/a', 'N/A', 'n/d'):
                continue

            per = parse_period(c0)
            plabel = per[0] if per else hdr_period
            pkey = per[1] if per else (periods.get(hdr_period) if hdr_period else None)
            if not plabel:
                skipped_no_period += 1
                continue
            if pkey is None:
                pp = parse_period(plabel)
                pkey = pp[1] if pp else 0

            metric = norm_metric(c0)
            if not metric:
                continue

            periods[plabel] = pkey
            cell = matrix.setdefault(metric, {})
            prev = cell.get(plabel)
            # earnings source wins; first earnings source is kept
            if prev is None or (is_earn and not prev[1]):
                cell[plabel] = (value, is_earn)
                placed += 1

    # --- order axes ---
    ordered_periods = sorted(periods, key=lambda p: periods[p])
    core_present = [m for m in CORE if m in matrix]
    rest = sorted(m for m in matrix if m not in CORE)
    ordered_metrics = core_present + rest

    # --- write sheet ---
    wb = openpyxl.load_workbook(WB_PATH)
    if SHEET in wb.sheetnames:
        del wb[SHEET]
    ws = wb.create_sheet(SHEET, 0)   # first tab

    hdr_fill = PatternFill('solid', fgColor='1F4E78')
    hdr_font = Font(bold=True, color='FFFFFF')
    core_font = Font(bold=True)

    ws.cell(row=1, column=1, value="CELH KPI Consolidation — 'Current' reported value per period")
    ws.cell(row=1, column=1).font = Font(bold=True, size=12)
    ws.cell(row=2, column=1,
            value="Source: 69 transcript digests. Earnings-call figures take precedence over conference restatements.")
    ws.cell(row=2, column=1).font = Font(italic=True, size=9, color='808080')

    hrow = 4
    ws.cell(row=hrow, column=1, value="Metric")
    for j, p in enumerate(ordered_periods):
        ws.cell(row=hrow, column=2 + j, value=p)
    for c in ws[hrow]:
        c.fill = hdr_fill; c.font = hdr_font
        c.alignment = Alignment(horizontal='center')

    for i, m in enumerate(ordered_metrics):
        rr = hrow + 1 + i
        mc = ws.cell(row=rr, column=1, value=m)
        if m in CORE:
            mc.font = core_font
        for j, p in enumerate(ordered_periods):
            v = matrix[m].get(p)
            if v is not None:
                ws.cell(row=rr, column=2 + j, value=v[0])

    ws.freeze_panes = "B5"
    ws.column_dimensions['A'].width = 38
    for j in range(len(ordered_periods)):
        ws.column_dimensions[ws.cell(row=hrow, column=2 + j).column_letter].width = 11

    wb.save(WB_PATH)
    print(f"Wrote '{SHEET}': {len(ordered_metrics)} metrics x {len(ordered_periods)} periods")
    print(f"  core metrics present: {len(core_present)} / {len(CORE)}")
    print(f"  datapoints placed: {placed}; rows skipped (no period): {skipped_no_period}")
    print(f"  period span: {ordered_periods[0]} -> {ordered_periods[-1]}")
    print(f"  total sheets now: {len(wb.sheetnames)}")


if __name__ == "__main__":
    main()
