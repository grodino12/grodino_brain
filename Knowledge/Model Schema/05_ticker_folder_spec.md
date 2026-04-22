# Ticker Folder Spec

Every ticker gets its own folder. Generic skills receive `--ticker-root` and read everything they need from there. No ticker logic in Python code, ever.

---

## Folder structure

```
tickers/
└── {ticker}/                              ← e.g. tickers/celh/
    ├── config.yaml                        ← ticker metadata
    ├── anomalies.yaml                     ← quirks affecting validation
    ├── decisions_ledger.json              ← label → model row mappings
    ├── source_citations.json              ← per-value citation trail (output)
    ├── sources/
    │   ├── 10-K/
    │   │   ├── 2024_{TICKER}_10-K.pdf
    │   │   └── 2025_{TICKER}_10-K.pdf
    │   ├── 10-Q/
    │   ├── press_releases/
    │   ├── earnings_transcripts/
    │   └── earnings_presentations/
    └── derived/
        ├── {TICKER} Financial Model.xlsm
        ├── {TICKER} Financial Model.xlsm.bak
        ├── raw_{year}.json                ← extract output per filing
        ├── mapped_{year}.json             ← reconcile output
        └── validated_{year}.json          ← validate output
```

---

## `config.yaml` — ticker metadata

```yaml
ticker: CELH
company_name: Celsius Holdings, Inc.
cik: "0001341766"
fiscal_year_end: 12-31
currency: USD

# Plausibility ranges for unit detection fallback
expected_revenue_range_thousands: [1_000_000, 3_000_000]
expected_total_assets_range_thousands: [500_000, 2_500_000]

# Share split history — affects pre/post split comparability
stock_splits:
  - date: 2023-11-13
    ratio: 3         # 3-for-1
```

---

## `anomalies.yaml` — quirks affecting extraction/validation

```yaml
# Cash convention changes year-over-year — affects X-2 cross-statement check
cash_convention_per_year:
  2023: cash_plus_restricted    # FY2023 10-K reconciles to "Cash + restricted cash"
  2024: cash_only               # FY2024+ uses "Cash and cash equivalents" only
  2025: cash_only

# Mezzanine equity — sits between Total Liabilities and Total SE
mezzanine_equity:
  enabled: true
  line_items:
    - Series A convertible preferred stock
  excluded_from_total_se: true  # do NOT sum into Total Stockholders' Equity

# Line items whose values are intentionally identical YoY — do not flag as extraction error
identical_yoy_values:
  - line: Deferred Other Costs (Current)
    value: 14124
    reason: Annual straight-line amortization of deferred slotting fees
  - line: Deferred Revenue (Current)
    value: 9513
    reason: PEP distribution agreement straight-line recognition

# Validation overrides — per-rule exemptions with documented reasons
validation_overrides:
  # Example structure; empty at start
  # - rule_id: X-2
  #   period: 2023
  #   reason: Restricted cash convention differs between filings
  #   approved_by: user
  #   approved_date: 2026-04-22
```

---

## `decisions_ledger.json` — label → model row mappings

Converted from the existing markdown ledger. Append-only.

```json
{
  "version": "1.0",
  "ticker": "CELH",
  "last_updated": "2026-04-22T00:00:00Z",
  "mappings": [
    {
      "rule_id": "MAP-001",
      "filing_term_normalized": "cost of revenue",
      "model_sheet": "ANNL P&L",
      "model_row": 10,
      "model_label": "COGS",
      "decided_date": "2026-04-15",
      "note": "Direct synonym",
      "superseded_by": null
    },
    {
      "rule_id": "MAP-002",
      "filing_term_normalized": "income from operations",
      "model_sheet": "ANNL P&L",
      "model_row": 15,
      "model_label": "Operating Profit",
      "decided_date": "2026-04-15",
      "note": "Direct synonym",
      "superseded_by": null
    }
  ],
  "new_rows": [
    {
      "rule_id": "NEW-001",
      "filing_term_normalized": "series a convertible preferred stock",
      "new_row_label": "Convertible Preferred Stock",
      "new_row_section": "mezzanine",
      "decided_date": "2026-04-16",
      "note": "Mezzanine row between Total Liabilities and Total SE"
    }
  ],
  "structural_decisions": [
    {
      "decision_id": "STRUCT-001",
      "description": "Convertible Preferred excluded from Total SE sum",
      "decided_date": "2026-04-16",
      "reason": "Matches CELH's filed BS structure; sell-side standard"
    }
  ]
}
```

---

## `source_citations.json` — output artifact

Written by `financials-validate` at the end of each run. One entry per value written to the model.

```json
{
  "ticker": "CELH",
  "period": "FY2024",
  "run_timestamp": "2026-04-22T14:30:00Z",
  "citations": [
    {
      "model_sheet": "BALANCE SHEET",
      "model_row": 9,
      "model_label": "Cash & Cash Equivalents",
      "value_thousands": 890190,
      "raw_filing_label": "Cash and cash equivalents",
      "source_pdf": "2025_CELH_10-K.pdf",
      "page": 50,
      "line_hint": "Cash and cash equivalents                890,190"
    }
  ]
}
```

---

## Adding a new ticker

1. `mkdir tickers/mnst/`
2. Copy a blank `config.yaml` and `anomalies.yaml` template
3. Create an empty `decisions_ledger.json` with the version header
4. Drop source PDFs into `sources/`
5. Run the pipeline; user-prompt on novel items populates the ledger

**Zero Python changes required.**

---

## Why not just hardcode CELH?

1. **Reuse** — same pipeline runs every consumer staples ticker you add.
2. **Auditability** — all ticker-specific state is in version-controlled data files, not scattered through Python.
3. **Rollback** — broken ledger? Revert the JSON. No code revert needed.
4. **Testing** — each ticker folder is a self-contained test fixture.
5. **Onboarding** — a new analyst only needs to understand the folder structure, not the framework internals.
