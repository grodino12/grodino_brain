# Model Schema

Framework design for a generic, ticker-agnostic financial-modeling pipeline. A chain of 6 Claude Code skills glued together by Pydantic contracts, per-ticker configuration folders, and JSON pattern libraries.

**Status:** 3 of 6 skills built (`financials-extract`, `financials-reconcile`, `financials-validate`). End-to-end CELH 2024 10-K run passes 26/26 validation rules.

---

## Read in order

| # | File | What it is |
|---|------|------------|
| 01 | `01_schema_spec.md` | Full Pydantic schema spec (text version of the class diagram). |
| 02 | `02_pipeline_design.md` | The 6 skills × 5 layers — what each skill does. |
| 03 | `03_ticker_folder_spec.md` | Per-ticker folder structure. How CELH-specific stuff is kept out of the generic skills. |
| 04 | `04_pattern_library_design.md` | JSON pattern files + rapidfuzz matching ladder. |
| — | `playground_architecture.html` | Interactive pipeline map. Click nodes for details. |
| — | `playground_schema.html` | Interactive class diagram. Click cards for fields + Python source. |
| — | `CELH/` | CELH-specific config + anomalies + decisions ledger. |

---

## Design principles

1. **Generic skills, ticker data in folders.** No `if ticker == "CELH"` anywhere.
2. **Pydantic contracts at every boundary.** Bad data fails at the boundary, not three steps downstream.
3. **Progressive learning via append-only stores.** Ledger + pattern libraries get smarter with each run.
4. **Audit trail preserved end-to-end.** Each layer wraps the prior output — you can always trace a value back to the source PDF.
5. **One pattern library per enum.** `Unit`, `StatementType`, `FilingType`, `Section`, `NumericNotation` each get their own JSON file.
6. **Schema hosting = shared package.** All Pydantic models live in one importable Python package, not copied per-skill.
7. **JSON for all persistent state.** No YAML anywhere — pattern libraries, ticker config, anomalies, decisions ledger are all JSON. Simpler stdlib handling, no `pyyaml` dependency.

---

## Pipeline at a glance

```
Layer 1 — RAW DATA + UNIT VALIDATION
          financials-extract          → RawFiling

Layer 2 — RECONCILIATION
          financials-reconcile        → MappedFiling

Layer 3 — INTEGRITY VALIDATION
          financials-validate         → ValidatedFiling

Layer 4 — VIZ · WRITE · CALC
          financials-playground       → explorer.html
          model-write                 → *_updated.xlsm
          model-calc                  → DerivedCalcs

Layer 5 — CONTRACTS + EXTERNAL
          financials-schema/          (shared Pydantic package)
          pattern_libraries/*.json    (enum phrase matching)
          tickers/{ticker}/           (per-ticker config, ledger, sources)
```

---

## Current CELH work state

Session-handoff docs live separately at `Brain/Sessions/CELH Model/`. The most recent handoff (`April 22nd Multi-Skill Framework Session.md`) describes the clean-slate rebuild that produced the current pipeline.
