---
name: financials-extract
description: Extract balance sheet, cash flow, and income statement line items from SEC filings (10-K / 10-Q / press releases) into a Pydantic RawFiling. Auto-dispatches by source extension — .pdf goes through pdfplumber + pattern libraries; .htm/.html iXBRL goes through lxml + SEC's presentation linkbase. Both paths emit the same RawFiling shape so downstream skills work format-agnostically. Use when the user asks to parse, extract, or pull data from any SEC filing.
---

# financials-extract

Layer 1 of the multi-skill financials pipeline. Parses an SEC filing into a
structured `RawFiling` Pydantic object. Two parser paths share one CLI:

| Source extension | Path | Library |
|---|---|---|
| `.pdf` | pdfplumber + pattern libraries (4-layer adaptation ladder) | `pdf_path.py` |
| `.htm` / `.html` (iXBRL) | lxml + SEC presentation linkbase | `ixbrl_path.py` |

Both paths converge on the same `RawFiling` shape — downstream
(`financials-reconcile`, `financials-validate`, `financials-playground`,
`model-write`) is unaware of the source format.

## CLI

```
financials-extract \
    --ticker-root <path-to-ticker-folder-with-config.json> \
    --source      <path-to-pdf-or-htm> \
    --out         <path-for-RawFiling-JSON> \
    [--filing-type 10-K|10-Q|8-K|press_release]   # PDF only; iXBRL reads form from .meta.json
    [--filing-date YYYY-MM-DD]                    # PDF only
    [--only        BS,CF,IS]                      # PDF only; iXBRL emits all
    [--library     <generic-library.json>]
```

### PDF example

```
financials-extract \
    --ticker-root "Brain/Knowledge/Model Schema/Ticker Libraries/CELH/" \
    --source      "Brain/Sources/CELH/2025-FY/filings/2025_CELH_10-K.pdf" \
    --out         "Brain/Knowledge/Model Schema/Ticker Libraries/CELH/.cache/raw_2024.json" \
    --library     "Brain/Knowledge/Model Schema/pattern_libraries/generic_line_item_mappings.json"
```

### iXBRL example

```
financials-extract \
    --ticker-root "Brain/Knowledge/Model Schema/Ticker Libraries/PG/" \
    --source      "Brain/Sources/PG/2026-Q2/filings/PG_2025-12-31_10-Q.htm" \
    --out         "Brain/Knowledge/Model Schema/Ticker Libraries/PG/.cache/raw_2026-Q2.json" \
    --library     "Brain/Knowledge/Model Schema/pattern_libraries/generic_line_item_mappings.json"
```

## Inputs

### Ticker root

Per-ticker folder containing:
- `config.json` — ticker metadata (ticker, fiscal year end, expected magnitude
  ranges, stock split history). Required. The CLI guards that
  `config.ticker` matches the filing's ticker (PDF: trusts the user; iXBRL:
  reads ticker from `.meta.json`, raises `SystemExit` on mismatch).
- `anomalies.json` — ticker-specific quirks. Optional at extract stage; used
  by downstream skills.

### Source file

- **`.pdf`** — IR-site press release, scanned filing, or analyst-distributed
  PDF. Pattern-library machinery handles filer-idiosyncratic layouts.
- **`.htm` / `.html`** — SEC EDGAR iXBRL primary document downloaded by
  `sec-edgar-fetch`. Requires a sibling `.meta.json` sidecar
  (accession + archive_base_url + form + report_date + quarter label) so
  the iXBRL path can locate `FilingSummary.xml` and the per-role `R{n}.htm`
  sidecars.

### Generic library

Optional `--library` argument pointing at `generic_line_item_mappings.json`.
When supplied, each `RawLineItem` gets `canonical_label`, `ledger_rule_id`,
and `sign_convention` populated at extract time via
`financials_schema.lookup.match_raw_item()`. Items with no library match keep
`canonical_label=None` and surface as novels in `financials-reconcile`.

## Outputs

A `RawFiling` Pydantic object serialized to JSON at `--out`. Contains one
`Statement` per `(statement_type, period)` combination:
- 10-K with two comparative BS columns → two BS Statements.
- 10-Q with H1 YTD CF → one CF Statement tagged with `fiscal_quarter` matching
  the filing quarter, so downstream column labels render `Q{N} FY{YYYY}`.

Each `RawLineItem` carries: `raw_filing_label`, `canonical_label`,
`ledger_rule_id`, `value`, `raw_numeric_text`, `notation_flags`, `row_type`,
`section`, `subsection_context`, `sign_convention`, `citation`.

## Architecture

```
scripts/
├── extract.py        # CLI entry; dispatches on file extension
├── pdf_path.py       # PDF parser (pdfplumber + pattern libraries)
├── ixbrl_path.py     # iXBRL parser (lxml + presentation linkbase)
├── pattern.py        # 4-layer adaptation ladder (used by pdf_path.py)
└── pdf_reader.py     # pdfplumber + pymupdf wrappers (used by pdf_path.py)

references/           # PDF pattern libraries (used by pdf_path.py only)
├── statement_heading_patterns.json
├── unit_phrases.json
├── period_phrase_patterns.json
├── numeric_notation_patterns.json
└── section_heading_patterns.json

.cache/ixbrl_reports/ # iXBRL FilingSummary + R-file cache, keyed by accession
```

## Sign-convention resolution

Both paths populate `RawLineItem.sign_convention` from the library entry's
`sign_convention` field. Three values:

- **`negative`** — value should always render as `-abs(value)`. Used for
  contra accounts (Treasury Stock, ESOP reserve), expense lines on the IS,
  Tax, etc.
- **`positive`** — value should always render as `+abs(value)`.
- **`as_reported`** (default) — pass value through unchanged.

The `abs()`-based design means the filer's reported sign is irrelevant — if
we know an item should be negative, `_signed_value()` returns `-abs(value)`
regardless of whether the filer wrote `100`, `-100`, `(100)`, or pre-signed
the value via `xbrli:balance`. No special-casing for parens-negation needed.

## Pattern-library 4-layer ladder (PDF only)

Each library is an instance of `PatternLibrary` (validated by the Pydantic
schema on load).

| JSON file | Resolves to |
|-----------|-------------|
| `unit_phrases.json` | `Unit` enum |
| `statement_heading_patterns.json` | `StatementType` enum |
| `section_heading_patterns.json` | `Section` enum |
| `numeric_notation_patterns.json` | `NumericNotation` flag bitmap |
| `period_phrase_patterns.json` | `Period` model (via regex capture) |

Matching:
1. **Normalize** — lowercase, collapse whitespace, strip configured
   prefixes/punctuation.
2. **Keyword match** — scan for distinctive tokens in each entry's `keywords`.
3. **Fuzzy match** (rapidfuzz) — score the phrase against `variants`;
   ≥95 auto-append, 85–94 accept, 70–84 prompt user, <70 fail loudly.
4. **Append** — confirmed novel variants get written back to the JSON.

## iXBRL classification (HTM only)

Statement classification uses SEC's **presentation linkbase** —
`FilingSummary.xml` lists each `Report` with a `MenuCategory` (Statements,
Notes, etc.) and a `ShortName` ("Consolidated Statements of Earnings",
"Consolidated Balance Sheets"). The `R{n}.htm` sidecar for each Report lists
its concepts. We map each Report to a statement code via
`canonical_statement_code(short_name)`, then assign every fact to its
statement based on which Report contains its concept.

CI is merged into IS on the fact side. SE / Details / unmapped concepts are
dropped (schema restricts `statement_type` to BS/CF/IS).

Per-share concepts (EPS, dividend-per-share) and share-count concepts
(weighted-average / shares issued) are exempted from the statement's
unit scaling — they're always actual dollars/shares regardless of an
"in millions" header.

## Dependencies

- `financials-schema` (shared Pydantic package, includes the lookup module)
- `pdfplumber` (PDF table extraction)
- `pymupdf` (PDF page-text extraction)
- `rapidfuzz` (fuzzy phrase matching)
- `lxml` (iXBRL XML parsing)
- `requests` (FilingSummary.xml + R-file fetching)
- `pydantic >= 2.6` (data validation)

## Status

**Built and verified.** End-to-end on CELH FY2024 10-K (PDF) and PG FY2026-Q2
10-Q (iXBRL) both produce clean `RawFiling` JSONs that drive the rest of the
pipeline through to `model-write`.
