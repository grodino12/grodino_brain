# Regression harness

Locks current CELH (12 filings) + PG (14 filings) outputs as **goldens**. Any
framework change that produces different outputs surfaces as an explicit
diff. Replaces the manual "rerun both tickers and eyeball" backstop.

## What it does

1. Discovers each ticker's filings by reading the source paths embedded in
   the existing `raw_*.json` files under `{TICKER}/Model Output/.cache/`.
2. Re-runs the full pipeline (extract -> reconcile -> validate -> model-write)
   on each filing into a temporary directory.
3. Compares the fresh outputs against the goldens stored under
   `goldens/{TICKER}/`:
   - Each `validated_*.json` is deep-diffed (numbers within $1 tolerance,
     strings exact).
   - The workbook is loaded with openpyxl and compared as a cell-map
     (`{sheet} -> {row_label_in_col_A} -> {col_label_in_row_1} -> value`),
     skipping nondeterministic xlsx binary metadata.
4. Exits 0 on no diffs, 1 on diffs, 2 on pipeline failure.

## Usage

```
# One-time bootstrap from current Model Output (the locked baseline)
python run.py --bootstrap

# Verify a code change didn't regress CELH/PG
python run.py

# Single ticker
python run.py --ticker CELH

# Diff is intentional improvement -- accept it as the new golden
python run.py --accept

# Keep the temp pipeline directory for inspection
python run.py --keep-temp
```

## When to use

After any change to:

- `~/.claude/skills/financials-extract/`
- `~/.claude/skills/financials-reconcile/`
- `~/.claude/skills/financials-validate/`
- `~/.claude/skills/model-write/`
- `Brain/Knowledge/Model Schema/financials-schema/`
- `Brain/Knowledge/Model Schema/pattern_libraries/generic_line_item_mappings.json`
- Either ticker's `decisions_ledger.json`

Run `python run.py` before claiming the change is done.

## Adding a new ticker

After onboarding a third ticker (e.g. PEP) clean:

1. Add an entry to `WORKBOOK_FILENAME` in `run.py`.
2. Run `python run.py --bootstrap --ticker PEP`.
3. From then on, `python run.py` covers all three.
