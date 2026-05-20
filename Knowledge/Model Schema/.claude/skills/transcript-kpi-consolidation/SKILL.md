---
name: transcript-kpi-consolidation
description: |
  Turn a ticker's earnings/conference transcript analyses into structured Excel output: per-transcript
  worksheet tabs, a consolidated KPI matrix (metric x period), and an automated audit. Sibling of
  mda-disaggregation — writes into the same {TICKER}_disclosures.xlsx. Input is the transcript .md
  analyses produced by the user-level analyze-earnings-transcript skill (each carrying a structured
  STEP-5 KPI block). Per-transcript digests (one JSON per transcript, strict schema) are the
  intermediate; the KPI sheet and audit are built from them deterministically. Per-ticker metric
  aliases and manual corrections live in
  Ticker Libraries/{TICKER}/MDA and Other/transcript_kpi_overrides.json.
when_to_use:
  - User wants to consolidate a ticker's transcript KPIs into one matrix sheet (metric rows x period
    columns) inside {TICKER}_disclosures.xlsx.
  - User wants per-transcript worksheet tabs added to {TICKER}_disclosures.xlsx.
  - User wants the consolidated figures audited against the source .md STEP-5 KPI blocks.
  - User onboards a new ticker's transcripts and wants the full transcript -> Excel pipeline run.
---

# Transcript KPI Consolidation skill

Builds the transcript side of `{TICKER}_disclosures.xlsx`: per-transcript worksheet tabs + a
`KPI Consolidated` matrix + an audit report. Sibling of `mda-disaggregation` (which builds the
filing-derived `Disclosures` tab in the same workbook); the two skills coordinate at the workbook,
not the skill — both append, neither overwrites the other's sheets.

## Pipeline

```
transcript PDFs
   |  analyze-earnings-transcript  (user-level skill, upstream — NOT part of this skill)
   v
{TICKER} transcript .md analyses          Brain/Sources/{TICKER}/{period}/transcripts/{TICKER}_*.md
   |  STEP 1: extract  (agent task, schema in data/schema.md)
   v
per-transcript digest JSONs               Ticker Libraries/{TICKER}/MDA and Other/transcript_digests/*.json
   |  build_transcript_tabs.py            STEP 2
   |  build_kpi_sheet.py                  STEP 3
   |  audit_kpi_sheet.py                  STEP 4
   v
{TICKER}_disclosures.xlsx  (NN transcript tabs + 'KPI Consolidated')  +  _audit_report.md
```

## STEP 1 — extract digests (agent task)

For each transcript `.md`, produce one digest JSON conforming to `data/schema.md`. This is the only
non-deterministic stage — it condenses the 11-step `.md` analysis into a 4-section digest
(Event/Date header, Quantitative KPI tables, Qualitative takeaways, Q&A summary). The `.md`'s
**STEP-5 KPI block is the spine** — copy its values verbatim; never restate or recompute. Channel /
distribution / market-share figures that the analysis did not formalize in STEP 5 are pulled from
STEP 7 (KPI Drivers) and STEP 9/10. Digests are written to
`Ticker Libraries/{TICKER}/MDA and Other/transcript_digests/`; STEP 1 is skipped for transcripts
already extracted. STEP 4's audit is the safety net for STEP-1 transcription errors.

## STEPS 2-4 — deterministic scripts

| Script | Does |
|---|---|
| `scripts/build_transcript_tabs.py {TICKER}` | Adds one worksheet tab per transcript (4-section layout), newest-first, to `{TICKER}_disclosures.xlsx`. Every populated cell deep-links via `obsidian://adv-uri` to the matching line in the source `.md` — STEP-5 KPI line for QUANTITATIVE data rows, STEP-10 `#### Question N` header for Q&A rows, best fuzzy match in STEPS 4 + 6-9 for QUALITATIVE takeaways. |
| `scripts/build_kpi_sheet.py {TICKER}` | Builds the `KPI Consolidated` sheet — metric rows x period columns. Numeric values only; cells deep-link to the source `.md`; Shift+F2 notes record provenance; prior-year values backfilled from STEP-5 `PriorYearValue`. |
| `scripts/audit_kpi_sheet.py {TICKER}` | Cross-checks every directly-reported cell against the source `.md` STEP-5; writes `_audit_report.md`. |
| `scripts/run.py {TICKER}` | Runs STEPS 2-4 in order. STEP 1 must already be done (digests present in `Ticker Libraries/{TICKER}/MDA and Other/transcript_digests/`). |

## Library architecture (mirrors mda-disaggregation)

| Library | Path | Role |
|---|---|---|
| **Generic** | `pattern_libraries/MDA and Other/transcript_kpi_library.json` | Cross-ticker metric canonicalization (alias -> canonical name), the standard-financials list, period-parsing rules. No filer knowledge. |
| **Per-ticker overrides** | `Ticker Libraries/{TICKER}/MDA and Other/transcript_kpi_overrides.json` | Ticker-specific metric aliases (e.g. CELH `Alani Nu net sales` -> `Alani Nu Revenue`), and a `corrections` list — `(metric, period) -> value/skip` with a note — where audit-surfaced fixes are recorded. Never hand-edit digests; record corrections here. |

## KPI Consolidated sheet — rules

- **Numeric only.** Text phrases, ranges are dropped; percentages stored as real fractions with `0.0%` format.
- **All datapoints kept**, including duplicates across transcripts — the cell shows the earnings-call figure (else earliest), the Shift+F2 note lists every source.
- **Cell colors:** blue = directly reported; gray italic = prior-year comparative backfilled from `.md`; black italic = computed formula (reconstructed when a `.md` prior conflicts with its own YoY%).
- **Period** comes from (in precedence): an explicit period in the row label -> a parenthetical qualifier in the label (`(H1)`) -> the column header -> the transcript's own reporting period.
- **Hyperlinks:** every cell deep-links via `obsidian://adv-uri` to the source `.md` STEP-5 line (requires the Advanced URI Obsidian plugin). Per-transcript tabs (STEP 2) carry the same deep-link decoration — see `build_transcript_tabs.py`'s anchor-kind table at the top of that script.
- **Comments:** use default openpyxl Comment dimensions — do NOT set `comment.width`/`height` (triggers Excel repair warnings; carried from `mda-disaggregation`).

## Critical rules

1. **Append, never overwrite.** Load the existing `{TICKER}_disclosures.xlsx` and add/replace only this skill's sheets. The MDA skill's `Disclosures` tab and any user tabs must survive.
2. **Digests are derived, corrections are not.** Audit-surfaced value fixes go in `transcript_kpi_overrides.json:corrections`, never as edits to digest JSONs (which are regenerable).
3. **STEP-5 is the spine.** The KPI sheet trusts STEP-5 values; the audit measures the digest/sheet against STEP-5. It cannot catch errors in the `.md` vs the source PDF — that is out of scope.

## Files

| File | Purpose |
|---|---|
| `SKILL.md` | This document |
| `data/schema.md` | Digest JSON schema for STEP 1 |
| `scripts/build_transcript_tabs.py` | STEP 2 |
| `scripts/build_kpi_sheet.py` | STEP 3 |
| `scripts/audit_kpi_sheet.py` | STEP 4 |
| `scripts/run.py` | Orchestrates STEPS 2-4 |
