# Model Schema

Framework design for a generic, ticker-agnostic financial-modeling pipeline. A chain of 6 Claude Code skills glued together by Pydantic contracts, per-ticker configuration folders, and YAML pattern libraries.

**Status:** design phase. No skills built yet.

---

## Read in order

| # | File | What it is |
|---|------|------------|
| 01 | `01_architecture_map.html` | Interactive pipeline map. Click nodes for details. |
| 02 | `02_pydantic_schema.html` | Interactive class diagram. Click cards for fields + Python source. |
| 03 | `03_schema_spec.md` | Full Pydantic schema spec (text version of the class diagram). |
| 04 | `04_pipeline_design.md` | The 6 skills × 5 layers — what each skill does. |
| 05 | `05_ticker_folder_spec.md` | Per-ticker folder structure. How CELH-specific stuff is kept out of the generic skills. |
| 06 | `06_pattern_library_design.md` | YAML pattern files + rapidfuzz matching ladder. |
| — | `examples/celh/` | CELH-specific config + anomalies + decisions ledger. |

---

## Design principles

1. **Generic skills, ticker data in folders.** No `if ticker == "CELH"` anywhere.
2. **Pydantic contracts at every boundary.** Bad data fails at the boundary, not three steps downstream.
3. **Progressive learning via append-only stores.** Ledger + pattern YAMLs get smarter with each run.
4. **Audit trail preserved end-to-end.** Each layer wraps the prior output — you can always trace a value back to the source PDF.
5. **One pattern library per enum.** `Unit`, `StatementType`, `FilingType`, `Section`, `NumericNotation` each get their own YAML file.
6. **Schema hosting = shared package.** All Pydantic models live in one importable Python package, not copied per-skill.

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
          pattern_libraries/*.yaml    (enum phrase matching)
          tickers/{ticker}/           (per-ticker config, ledger, sources)
```

---

## Current CELH work state

Session-handoff docs live separately at `Brain/Sessions/CELH Model/`. Those describe where CELH currently is in the Phase 0-5 workflow using the *old* skill, and are reference material for what the new framework needs to support.
