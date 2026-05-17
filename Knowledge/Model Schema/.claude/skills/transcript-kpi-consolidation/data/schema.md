# Digest JSON schema (STEP 1 output)

One JSON file per transcript, written to `<skill>/_work/{TICKER}/{NN}_{slug}.json`.
A digest condenses one transcript's 11-step `.md` analysis into a 4-section structure.

## Top-level object

```json
{
  "index": 1,                       // 1-based chronological order across the ticker's transcripts
  "sheet_name": "01 2018Q3 Earnings", // worksheet tab name: "{NN} {short event}"
  "event": "Q3 2018 Earnings Call",   // MUST equal the .md frontmatter event_title
  "date": "2018-11-09",               // MUST equal the .md frontmatter date (YYYY-MM-DD)
  "rows": [ ... ]                     // ordered list of row arrays — see below
}
```

`event` and `date` are the join key back to the source `.md` and the workbook tab — copy them
verbatim from the `.md` frontmatter.

## `rows` — ordered row arrays

Each row is an array. Three kinds:

1. **Section marker** — a single-element row whose text is exactly `QUANTITATIVE`,
   `QUALITATIVE`, or `Q&A`. Everything between `QUANTITATIVE` and the next marker is the
   quantitative block (the only block STEPS 2-4 read for the KPI sheet).
2. **Header row** — first cell is a sub-table title; remaining cells are column labels. Two styles:
   - period style: `["Revenue ($M)", "Q1 2022", "Q1 2021", "YoY %"]`
   - prior/current style: `["Margins", "Prior Yr", "Current", "YoY"]`
   A header whose value cells are only `Value` / `Period` marks a non-numeric color table.
3. **Data row** — first cell is the metric label, remaining cells are values aligned to the header.

## Rules for the quantitative block

- **Copy STEP-5 values verbatim.** The `.md` STEP-5 KPI block is the spine. Use the same numbers,
  same units. Do not recompute or restate.
- **One reported value per data row** under the header's current/most-recent column.
- A metric's **period** may be in the row label (`Total Revenue Q4 2018`), the column header
  (`Q1 2022`), or a parenthetical (`International (H1)`); any is fine — STEP 3 resolves it.
- Channel / distribution / market-share figures not in STEP 5 may be added as their own
  sub-tables; they are kept but cannot be audited against STEP 5.
- Do not annotate value cells with trailing prose (`$977M (pre-close)`) — the value cell must be
  just the value; put context in a separate column or omit it.

## STEP-5 reference fields

When extracting, each `.md` STEP-5 KPI line carries `Value`, `PriorYearValue`, `YoYChangePct`,
`Period`, `FiscalYear`, `FiscalQuarter`. These drive the KPI sheet's prior-year backfill and the
audit — keep STEP-5 intact in the `.md`; the digest need only carry the current `Value` per row.
