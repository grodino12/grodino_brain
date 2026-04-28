# Celsius HF Case Study — 3-Model Overview

**Project:** `C:\Users\rodin\Desktop\Pl3 Celsius Case Study`
**Purpose:** Hedge fund final-round interview case study on Celsius Holdings (CELH). Three interlocking models analyze (1) GLP-1 drug impact on energy drink consumption, (2) SNAP energy drink ban impact, (3) CELH's financial trajectory.

---

## 1. CELH Financial Model (current active work)

**File:** `data/derived/CELH Financial Model.xlsm` (10 sheets, has macros — must use `keep_vba=True` in openpyxl)

**Sheets:** NA Revenue Build, SGMT DATA, QTR P&L, ANNL P&L, BALANCE SHEET, CASH FLOW, Sensitivity Analysis, GUIDANCE, Valuation, BlueMatrix

**Status:** Mid-Phase 2 → Phase 3 of the `celh-model-update` skill workflow. ANNL P&L FY2023-FY2025 actuals updated. QTR P&L Q1 2023-Q4 2024 updated. FY2023 + FY2024 BS/CF re-extracted cleanly (Phase 1.75 validation caught ~$394M of misstatement in original extraction). Awaiting Excel write.

**Source PDFs:** `data/CELH Reporting/Financial Statements/`, `Press Releases/`, `Earnings Presentations/`, `Earnings Transcripts/` (~58 PDFs covering 2022-2025)

**Key findings:**
- Retained earnings flipped to positive in FY2024 (-$12M → +$105M) — first cumulatively profitable year
- Inventory drawdown of $98M in FY2024 alongside flat revenue (+3%) — likely distributor destocking
- PEP convertible preferred ($824M) sits as mezzanine equity, recognizing straight-line into deferred revenue ($9,513K/year for ~17.5 more years)
- Big Beverages acquisition ($75M) added $57M goodwill in FY2024
- FY2025 had Alani Nu acquisition + $327M distributor termination + first Interest Expense year ($49M)

**See files in this folder:**
- `02_celh_session_state.md` — current pending decisions
- `03_celh_decisions_ledger.md` — progressive learning rules store
- `04_celh_source_citations.md` — definitive data values being written
- `skill/SKILL.md` — full workflow definition

---

## 2. GLP-1 Projection Model

**File:** `data/derived/GLP1_Projection Data.xlsx` (47K)

**Tabs:** US Population, GLP-1 Usage, Coverage & Affordability, User Base Composition, Persistence, Sources & Notes, Raw Data, GLP1 Share Impact

**Methodology:**
- Drug analogs: Insulin (T2D curve) and Botox (weight loss curve) for backward-facing price-volume elasticity precedents
- PWBM (Penn Wharton Budget Model) take-up curve layered on insurance coverage
- Survival curves model GLP-1 drop-off rates over 1-3 years
- Net effect on energy drink consumption: sugar-free energy drinks see only ~4% consumption reduction from GLP-1 users

**Source data:** Postgres (`demographic_data` DB on localhost:5432, Docker)

**Recent rebuild:** File was corrupted earlier from `cell.fill = None`. Recovered from git HEAD then rebuilt via scripts in `python_scripts/`: `sync_glp1_demographics.py`, `build_raw_data_tab.py`, `link_raw_data.py`, `link_weighted_avg.py`, `add_normalized_insurance.py`, `pwbm_curve.py`. **Lesson baked in:** Never use `cell.fill = None` — always use `PatternFill(fill_type=None)`.

---

## 3. SNAP / Demographics / Energy Drink Model

**File:** `data/derived/Celsius_SNAP Data_GR.xlsx` (887K)

**Tabs:** Male, Female, Growth by Race, SNAP Base Case, SNAP Recession, TAM & Brand Share, Demographic Data, Snap Usage, Energy Drink Consumption, SNAP Ban Impact, COVID SNAP Impact, National Summary

**Postgres backing data (`demographic_data` DB):**
- `us_population` (198 rows), `us_population_race` (924), `state_population_race` (47,124)
- `state_snap` (572), `national_snap_baseline` (11), `snap_participation` (7), `snap_eligibility` (31), `snap_takeup` (11), `snap_recession_params` (13)
- `energy_drink_consumption` (21)
- GLP-1 tables (shared with GLP-1 model)
- Views: `v_state_snap_by_race_age` (raked race×age×gender SNAP rates), `v_state_demographics` (master join)

**pgAdmin:** `celsius-pgadmin` Docker container on localhost:5050 (login: gabe@celsius.com / postgres)

**Key analytical findings:**
- 18 states have SNAP energy drink bans rolling out in 2026 (FL, TX, VA, etc.)
- OBBBA cuts ~2.4M SNAP participants through 2034
- Energy drink consumption: Male 66% / Female 34%; ages 30-49 highest at 42.3%; Black odds ratio 2.10× vs White
- Celsius brand: 50/50 gender (unique vs Monster's 65% male), core demo 25-44, 11% volume share

---

## Cross-Model Linkages

The three models converge to answer: **"What's the net impact on Celsius revenue from GLP-1 + SNAP bans + demographic trends?"**

- **GLP-1 model** outputs % of energy drink consumers using GLP-1 drugs over time → consumption headwind
- **SNAP model** outputs # of SNAP-funded energy drink purchases that go away under state bans → volume headwind, weighted by Celsius's share in those states/demographics
- **CELH financial model** is where these flow into the revenue forecast (rows 2026E-2028E, then extending to 2029E-2030E per the original plan)

**This integration step has not yet been built.** Currently each model runs standalone.

---

## Project-Wide Conventions / Lessons Learned

### Excel safety (encoded in `skill/references/excel_safety.md`)
1. `keep_vba=True` for .xlsm files
2. Never `cell.fill = None` (corrupts styles.xml — caused GLP-1 file corruption)
3. Hide columns, never delete (preserves cross-sheet formulas)
4. Save to `_updated` filename, not the original
5. Verify-after-save (reload with openpyxl)
6. Backup to `.bak` before any write
7. Watch for `~$` lock files (file open in Excel)
8. Use valid number formats (`'0.00"x"'` not `'0.00\x'`)
9. Don't insert rows in cross-linked sheets via openpyxl (formulas in OTHER sheets won't update — use Path 3: manual Excel insert)
10. Read-then-write atomicity

### Source citation requirement
Every value updated in any model needs PDF + page citation in a markdown doc. The CELH skill enforces this as Phase 2.

### Progressive learning (NEW pattern)
The `celh_decisions_ledger.md` pattern is now a project convention. Persistent decisions store, loaded at start of reconciliation phase, append-as-you-go after each user decision. Could be replicated for GLP-1 and SNAP model updates if they become recurring workflows.

### Validation phase (NEW pattern)
The Phase 1.75 arithmetic-identity validation pattern is a project convention. Caught $394M of FY2024 misstatement that would otherwise have entered the model. Replicate for any future financial extraction work.
