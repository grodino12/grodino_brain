# Pipeline Design — 6 Skills × 5 Layers

Every skill is ticker-agnostic. Ticker-specific state (CELH anomalies, ledger entries, source PDFs) flows in via `--ticker-root`.

---

## Layer 1 · Raw Data + Unit Validation

### `financials-extract`

- **Purpose:** Parse SEC filing PDFs into Pydantic `RawFiling` objects with page citations and detected currency unit.
- **Input:** PDF path + `--ticker-root`
- **Output:** `RawFiling`
- **Key operations:**
  1. Locate BS/CF/IS pages by heading match (pattern library, not hardcoded page numbers)
  2. Detect currency unit via phrase library + plausibility fallback
  3. Extract table rows with pdfplumber; preserve raw filing labels verbatim
  4. Attach `(page, line_hint)` citation to every value
  5. Classify each line's section and row_type via pattern libraries
- **Dependencies:** `pymupdf`, `pdfplumber`, `pydantic`, `rapidfuzz`
- **Fails loudly on:** Unit.UNKNOWN, press releases with BS/CF sections, empty filings

---

## Layer 2 · Reconciliation

### `financials-reconcile`

- **Purpose:** Map raw filing labels to canonical Excel model rows via the decisions ledger. Auto-apply known rules, prompt only on novel items.
- **Input:** `RawFiling` + `tickers/{ticker}/decisions_ledger.json`
- **Output:** `MappedFiling`
- **Key operations:**
  1. Normalize labels (case, whitespace, punctuation collapsed)
  2. Lookup ledger → auto-apply on match
  3. rapidfuzz-score novel items against ledger; surface top 3 candidates
  4. Prompt user for novel items only
  5. Append confirmed new decisions back to ledger (append-only, dated)
- **Dependencies:** `pydantic`, `rapidfuzz`
- **Fails loudly on:** any unresolved novel item reaching `MappedFiling` construction

---

## Layer 3 · Integrity Validation

### `financials-validate`

- **Purpose:** Accounting identities + cross-statement ties as Pydantic validators. Blocks downstream on fail.
- **Input:** `MappedFiling`
- **Output:** `ValidatedFiling`
- **Key operations:**
  1. Run BS-1..BS-7 (subtotal sums, accounting equation, RE roll-forward)
  2. Run CF-1/CF-2 (CFO+CFI+CFF+FX=ΔCash; Cash End = Beg + Δ)
  3. Run X-1..X-4 (CF NI = P&L NI, CF CashEnd = BS Cash, pref div ties)
  4. Raise `ValidationError` with structured gap list on any fail
  5. Honor overrides from `tickers/{ticker}/anomalies.json` (e.g. cash convention per year)
- **Dependencies:** `pydantic`, `decimal`
- **Tolerance:** $1K absolute, 0.1% relative

---

## Layer 4 · Viz · Write · Calc

Three parallel skills, all consuming `ValidatedFiling`.

### `financials-playground`

- **Purpose:** Self-contained HTML explorer for QA before Excel write.
- **Input:** `ValidatedFiling[]` (one or more periods)
- **Output:** `explorer.html`
- **Key operations:**
  1. Render BS/CF/IS tables with period columns
  2. Highlight YoY changes >20%
  3. Toggle raw filing label vs canonical model row
  4. Per-line citation tooltip on hover
  5. Copy-out button emits model-write scaffold prompt
- **Dependencies:** `jinja2`, `pydantic`

### `model-write`

- **Purpose:** Write `ValidatedFiling` into the `.xlsm` model. Preserves macros, honors cross-sheet formulas via Path 3 manual inserts.
- **Input:** `ValidatedFiling` + target xlsm path
- **Output:** `*_updated.xlsm` + `*.bak`
- **Key operations:**
  1. Backup original to `.bak` before any write
  2. openpyxl load with `keep_vba=True`; never `cell.fill = None`
  3. Emit `ManualInsertPlan` for new rows (user performs manual inserts first)
  4. Write values only, not formulas
  5. Verify-after-save: reload + spot-check 10 known cells + grep for `#REF!`
- **Dependencies:** `openpyxl`, `shutil`, `pydantic`

### `model-calc`

- **Purpose:** Derived calcs + scenario overlay. Where GLP-1 and SNAP models feed in as scenario headwinds.
- **Input:** `ValidatedFiling` (multi-period) + `ScenarioInputs`
- **Output:** `DerivedCalcs`
- **Key operations:**
  1. YoY/QoQ growth, margins, DSO/DIO/CCC
  2. GLP-1 consumption headwind curve overlay
  3. SNAP state-weighted volume drag overlay
  4. Base / bull / bear sensitivity grid
  5. Emit JSON for downstream charting
- **Dependencies:** `pydantic`, `pandas`, `numpy`

---

## Layer 5 · Contracts + External

Not skills — supporting infrastructure.

- **`financials-schema/`** — shared Pydantic package. Imported by all six skills.
- **`pattern_libraries/*.json`** — per-enum phrase matching (read by `financials-extract`, appended to on confirmed novel matches).
- **`tickers/{ticker}/`** — per-ticker config, ledger, source PDFs, Excel target. See `03_ticker_folder_spec.md`.
- **External model inputs** — GLP-1 and SNAP model outputs feed `model-calc` as scenario inputs.

---

## Data flow at a glance

```
source PDF
    ↓ (+ pattern libraries)
financials-extract → RawFiling
    ↓ (+ decisions_ledger)
financials-reconcile → MappedFiling
    ↓
financials-validate → ValidatedFiling
    ↓
    ├→ financials-playground → explorer.html
    ├→ model-write           → xlsm
    └→ model-calc (+ GLP-1, SNAP) → DerivedCalcs
```

---

## Skill invocation example

```bash
# 1. Extract
financials-extract \
    --ticker-root tickers/celh/ \
    --pdf tickers/celh/sources/10-K/2025_CELH_10-K.pdf \
    --out tickers/celh/derived/raw_2024.json

# 2. Reconcile
financials-reconcile \
    --ticker-root tickers/celh/ \
    --in tickers/celh/derived/raw_2024.json \
    --out tickers/celh/derived/mapped_2024.json

# 3. Validate
financials-validate \
    --ticker-root tickers/celh/ \
    --in tickers/celh/derived/mapped_2024.json \
    --out tickers/celh/derived/validated_2024.json

# 4a. QA via HTML explorer
financials-playground \
    --in tickers/celh/derived/validated_2024.json \
                  tickers/celh/derived/validated_2023.json \
    --out tickers/celh/derived/explorer.html

# 4b. Write to Excel
model-write \
    --ticker-root tickers/celh/ \
    --in tickers/celh/derived/validated_2024.json \
    --xlsm tickers/celh/derived/CELH Financial Model.xlsm

# 4c. Scenario calcs
model-calc \
    --ticker-root tickers/celh/ \
    --validated tickers/celh/derived/validated_*.json \
    --scenarios scenarios.json \
    --out tickers/celh/derived/derived_calcs.json
```
