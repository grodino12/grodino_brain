---
type: session-handoff
date: 2026-04-24
topic: Verified model-calc end-to-end, diagnosed and fixed the forecast BS balance gap via zero + aoci_rollforward kinds, propagated number formats to forecast cells, reintroduced Allowance for Credit Losses as a ratio_of_rev driver, and pivoted project focus to universal model creation architecture.
tags: [session, celh, model-calc, forecast-balance, aoci, allowance, universal-architecture]
---

# April 24th — Model-Calc Forecast Balance Session

Picks up from `April 23rd Generic Migration Phases 3-7 Session.md`. That session shipped Phases 3–7 of the generic-library migration. This session verified `model-calc` end-to-end, fixed a forecast BS balance gap, tightened output formatting, re-enabled the Allowance for Credit Losses line with a proper driver, and reframed the project priority toward universal architecture.

## Starting state (beginning of this session)

- Prior handoff's roadmap listed `model-calc` as the active objective and implied it was unbuilt. On inspection, `scripts/calc.py` was fully built (1,158 lines): ASSUMPTIONS tab, 3 driver tabs (28 drivers total), full three-statement forecast formulas across 27 distinct `kind` dispatches. No session handoff had captured this work — the user referenced "lost data" and suspected progress had happened without documentation.
- CELH pipeline: reconcile clean (0 novels), validate 48/48 PASS, model-write produces 327 cells, model-calc layer never end-to-end verified against a computed workbook.
- Forecast BS never had a rigorous balance check.

## Work done this session

### 1. Pipeline end-to-end verification

Ran the full chain on both CELH filings:
- reconcile on `raw_2024_10K.json` + `raw_2025_10K.json` → 0 novels each.
- validate → **48 PASS / 0 WARN / 0 FAIL** on both filings.
- model-write → `CELH_model.xlsx` with 18 IS rows / 40 BS rows / 41 CF rows, 327 cells across historicals + forecast skeleton.
- model-calc → ASSUMPTIONS + 3 driver tabs (63 + 135 + 60 cells) + statement forecasts (72 + 204 + 216 cells).
- Evaluated workbook through the `formulas` package (92 cells compile; 1,476 keys in solution). Confirmed no circular refs or broken references.

### 2. Diagnosed the forecast BS balance gap

BS balances perfectly at FY2024 (historical, validated), then develops a gap that grows linearly: +$13,710 at FY2025E, +$82,260 by FY2030E. Gap grew at exactly $13,710/yr.

Row-level delta analysis (FY2024 → FY2025E) showed the asset side gaining $154,731 while equity side gained $141,021. Initial hypothesis (amort of Deferred Other Costs) turned out to be a red herring — **amort cancels correctly** because the CFO addback increases Cash by +Amort while BS DefCosts drops by -Amort, netting to zero on the asset side, and NI (with embedded amort expense in COGS/SG&A ratios) mirrors -Amort on the equity side.

Empirically summed the nine "flat" CF items with no BS offset in the forecast:

| CF item | FY2024 value |
|---|---|
| Allowance for Credit Losses | +3,294 |
| Inventory Write-Down | +19,086 |
| Gain (Loss) on Disposal of PP&E | +173 |
| (Benefit) Provision for Deferred Income Taxes | −9,730 |
| Foreign Currency Gain (Loss) on CFO | +1,734 |
| Gain (Loss) on Lease Cancellations | 0 |
| Other Operating Items | −324 |
| ROU & Lease Liability, Net | +535 |
| Finance Lease Payments | −61 |
| FX Effect on Cash | −997 |
| **Sum** | **+13,710** |

Exact match to the observed gap. Root cause: every non-cash CFO addback and every financing-activity cash flow needs a matching BS rollforward in the forecast. These items were `flat` (hold-last), bleeding real cash each year without an equity-side offset.

### 3. Fix: added `zero` and `aoci_rollforward` forecast kinds

Two new kinds in `build_statement_forecast_formula` (`calc.py`):

```python
if kind == "zero":
    return "=0"

if kind == "aoci_rollforward":
    if col_prev_here is None: return None
    prior = f"{get_column_letter(col_prev_here)}{row}"
    fx = rowref("CASH FLOW", "FX Effect on Cash", here_on("CASH FLOW"))
    if fx is None: return f"={prior}"
    return f"={prior}+{fx}"
```

Spec updates in `FORECAST_STATEMENT_SPECS`:

| Line | Was | Now |
|---|---|---|
| IS: Foreign Currency Gain (Loss) | `dollar_driver` | `zero` |
| CF: Allowance for Credit Losses | `flat` | `zero` (later re-enabled as `ratio_of_rev` — see §5) |
| CF: Inventory Write-Down | `flat` | `zero` |
| CF: Gain (Loss) on Disposal of PP&E | `flat` | `zero` |
| CF: (Benefit) Provision for Deferred Income Taxes | `flat` | `zero` |
| CF: Foreign Currency Gain (Loss) | `flat` | `zero` |
| CF: Gain (Loss) on Lease Cancellations | `flat` | `zero` |
| CF: Other Operating Items | `flat` | `zero` |
| CF: ROU & Lease Liability, Net | `flat` | `zero` |
| CF: Finance Lease Payments | `flat` | `zero` |
| BS: Accumulated Other Comprehensive Income (Loss) | `flat` | `aoci_rollforward` |

**Rationale for AOCI rollforward rather than zeroing FX Effect on Cash:** the AOCI rollforward is the economically correct pairing for translation FX (change in AOCI ≈ CF!FX Effect on Cash for companies whose foreign-sub net assets are cash-dominated). It's the same eight lines of code as the zero option but generalizes to tickers with meaningful FX exposure (KO, PEP, CL). For CELH at ~$1k/yr FX Effect, the distinction is immaterial.

Verified: **BS gap = $0 across FY2022 → FY2030E.** Historicals untouched (zero rule only applies to forecast columns); validate still 48/48 PASS.

### 4. Number format propagation fix

On inspection: every forecast cell on ANNL P&L / BALANCE SHEET / CASH FLOW had `number_format = 'General'` while historical cells had `'#,##0;(#,##0);"--"'`. Model-calc was writing forecast formulas without setting a format; model-write hadn't seeded forecast-column formats either.

Fix in `write_statement_forecasts` (`calc.py`):
- Compute `last_hist_col` per sheet.
- For each row, sample the historical format from that column's cell.
- Apply that format to **every forecast cell in the row, including subtotal rows** whose forecast formulas were written by model-write (the spec's `kind == "subtotal"` entries hit the loop even though `build_statement_forecast_formula` returns `None`).

Post-fix diagnostic: 0 format mismatches across all three sheets. Every forecast cell renders `$-- / ( )` accounting format consistently with historicals.

### 5. Allowance for Credit Losses as `ratio_of_rev` (user request)

Zeroing Allowance for Credit Losses was a v1 simplification. User requested it be tied to Revenue so the forecast CF reflects realistic steady-state credit losses.

Changes:
- Added `Allowance for Credit Losses % of Revenue` to `DRIVER_SPECS["CF DRIVERS"]` as a `ratio` driver (num = CF!Allowance, den = Revenue). Inserted as the first CF driver (above D&A % of PP&E). Historical ratio for CELH: 0.243%.
- Flipped CF forecast spec for `Allowance for Credit Losses` from `zero` to `ratio_of_rev` pointing at the new driver. Excel formula becomes `='CF DRIVERS'!F2 * 'ANNL P&L'!F2`.

**Accepted tradeoff:** BS gap reopens at $3,294/yr at flat revenue, growing linearly to ~$19,764 at FY2030E — ~1.1% of the FY2024 balance sheet. The gap is fundamental (BDE is in SG&A implicitly, CF addback adds it back to Cash, but BS has no contra-AR Allowance line to absorb it). Documented in the roadmap as "Known v1 simplification." Fixing properly requires either (a) adding an explicit Allowance-for-Doubtful-Accounts contra-AR BS line that accumulates BDE, or (b) subtracting the forecast Allowance from the SG&A forecast formula so NI rises to match. Neither is blocking.

### 6. FX relationship context

Discussed with user: IS/CFO "Foreign Currency Gain (Loss)" is **transaction FX** (ASC 830-20) — remeasurement of the USD parent's non-USD AR/AP. BS AOCI / CF FX Effect on Cash is **translation FX** (ASC 830-30) — consolidation of foreign subs at closing rates. They share the same underlying FX-rate driver but hit different exposures on different parts of the financials. Current v1 treatment (zero transaction FX, pair translation FX to AOCI) is correct; linking both to a single FX-rate assumption would require per-category exposure estimates not in the filings. User declined a comment annotation for now — will revisit when the next ticker with meaningful FX exposure (KO, PEP, CL) comes online.

### 7. Project priority pivot

User reframed the active objective: **cross-model integration (GLP-1 + SNAP into CELH Revenue Growth %) is deferred indefinitely.** Focus is now **universal model creation architecture** — making the pipeline work for any consumer-staples ticker, not just CELH.

Agreed critical path:
1. Run a second ticker through the existing pipeline as-is — recommended PEP (debt-heavy, dividend payer, real FX exposure). Each failure or hardcoded-CELH-label becomes a concrete TODO.
2. Extract `generic_forecast_rules.json` from `calc.py` based on the two-ticker surface of variation. Mirror the existing `generic_line_item_mappings.json` pattern (generic library + per-ticker overrides, ticker-wins precedence).
3. Formalize a one-page ticker onboarding doc (scaffold, pipeline invocation, novel triage, forecast review).

No code shipped yet on this pivot — the concrete next step is a PEP PDF pull + first pipeline run.

## Current state

### Shipped this session
- **Pipeline verified end-to-end**: 0 novels, 48/48 PASS both filings, model-write 327 cells, model-calc 258 driver cells + 492 forecast cells. Workbook computes cleanly via `formulas`.
- **Forecast BS balances at $0 gap** across every forecast year (FY2025E → FY2030E), modulo ~$3.3k/yr from re-enabled Allowance (flagged, acceptable for v1).
- **calc.py** gained two new forecast kinds (`zero`, `aoci_rollforward`), 10 spec flips (9 flat→zero, 1 flat→aoci_rollforward), plus the Allowance driver + ratio_of_rev rewire.
- **Number formats** propagate from historical cells to forecast cells, including subtotals — no more `General` cells in the forecast.
- **ROADMAP** updated: 6-of-6 skills shipped, balance gap fix documented, active objective switched to universal architecture.

### Known quirks
- ~$3.3k/yr BS gap at FY2025E from re-enabled Allowance for Credit Losses (~$20k by FY2030E). ~1.1% of FY2024 TA. Fix requires either a BS Allowance contra-AR line or an SG&A forecast offset; neither blocks the case study.
- `model-calc` forecast specs reference canonical labels hardcoded in Python. Some labels (Deferred Other Costs, Accrued Distributor Termination Fees, Note Receivable) are CELH-specific and will fail on other tickers. This is the primary surface for the universal-architecture pivot.
- No session handoff captured the original `model-calc` build (the bulk of `calc.py`). This handoff is the first written record of its existence.

### Files touched
| Path | Change |
|---|---|
| `~\.claude\skills\model-calc\scripts\calc.py` | Added `zero` + `aoci_rollforward` kinds (both in kind-docstring comment + dispatcher). Flipped 10 statement forecast specs. Added `Allowance for Credit Losses % of Revenue` driver to `DRIVER_SPECS["CF DRIVERS"]`. Rewired CF `Allowance for Credit Losses` spec from `zero` → `ratio_of_rev`. Added `last_hist_col` + format propagation loop in `write_statement_forecasts`. |
| `Brain\Sessions\CELH Model\ROADMAP.md` | Moved balance gap fix from Active to Shipped. Documented model-calc state. Switched active objective to universal architecture. Updated pipeline workstream status to 6-of-6. |
| `Brain\Knowledge\Model Schema\CELH\Model Output\CELH_model.xlsx` | Rebuilt fresh from validated JSONs. |
| `Brain\Knowledge\Model Schema\CELH\Model Output\mapped_*.json` / `validated_*.json` | Re-regenerated from raw JSONs. |

## Open decisions / pending work

1. **Pick the second ticker and run it through the pipeline as-is.** Recommended: PEP (debt, dividends, share repurchases, meaningful international FX — a different shape from CELH). Alternative: KO or CL. The output of this run — novels, broken formulas, missing canonical labels — is the evidence base for what goes into the generic forecast library and what stays as ticker-specific override.
2. **Extract `pattern_libraries/generic_forecast_rules.json`** after step 1 produces real divergence evidence. Ticker-override file at `{TICKER}/forecast_overrides.json`. Precedence: ticker override → generic → engine fallback. Only mechanical; new kinds still require `calc.py` dispatcher changes.
3. **Formalize ticker onboarding doc** — short, one page. Covers: `mkdir tickers/{NEW}/`, config.json scaffold, run extract/reconcile/validate/model-write/model-calc, triage novels, review forecast. Doc lives at `Brain\Knowledge\Model Schema\05_ticker_onboarding.md`.
4. **Close the Allowance-driven BS gap** — optional polish. Either add a BS contra-AR `Allowance for Doubtful Accounts` line or override SG&A forecast formula to subtract the allowance. Low priority (<1% of TA at CELH).
5. **Cross-model integration (GLP-1 + SNAP → CELH Revenue)** — deferred indefinitely per user. Revenue Growth % input cells on IS DRIVERS are already user-editable (yellow-tinted). When the user is ready, wire external models into those cells.
6. **FY2025 10-K from EDGAR.** Accession `0001341766-26-000024`, HTML-only. Needs weasyprint HTML→PDF branch or HTML-aware extract. Deferred.

## Key file paths

| Purpose | Path |
|---|---|
| **This handoff** | `C:/Users/rodin/Desktop/Brain/Sessions/CELH Model/Handoffs/April 24th Model-Calc Forecast Balance Session.md` |
| Prior handoff | `C:/Users/rodin/Desktop/Brain/Sessions/CELH Model/Handoffs/April 23rd Generic Migration Phases 3-7 Session.md` |
| Roadmap | `C:/Users/rodin/Desktop/Brain/Sessions/CELH Model/ROADMAP.md` |
| model-calc skill | `C:/Users/rodin/.claude/skills/model-calc/scripts/calc.py` |
| Generic cross-ticker mappings library | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/pattern_libraries/generic_line_item_mappings.json` |
| CELH ledger | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/CELH/decisions_ledger.json` |
| CELH model xlsx (built) | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/CELH/Model Output/CELH_model.xlsx` |
| CELH raw / mapped / validated JSONs | `C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema/CELH/Model Output/` |

## Pipeline invocation (unchanged)

```bash
cd "C:/Users/rodin/Desktop/Brain/Knowledge/Model Schema"
source financials-schema/.venv/Scripts/activate

PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/financials-reconcile/scripts/reconcile.py" \
    --ticker-root "CELH/" \
    --in "CELH/Model Output/raw_2024_10K.json" \
    --out "CELH/Model Output/mapped_2024_10K.json"

PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/financials-validate/scripts/validate.py" \
    --ticker-root "CELH/" \
    --in "CELH/Model Output/mapped_2024_10K.json" \
    --out "CELH/Model Output/validated_2024_10K.json"

PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/model-write/scripts/write.py" \
    --ticker-root "CELH/" \
    --in "CELH/Model Output/validated_2024_10K.json" \
    --in "CELH/Model Output/validated_2025_10K.json" \
    --out "CELH/Model Output/CELH_model.xlsx"

PYTHONIOENCODING=utf-8 python "C:/Users/rodin/.claude/skills/model-calc/scripts/calc.py" \
    --ticker-root "CELH/" \
    --in "CELH/Model Output/CELH_model.xlsx"
```

---

## How to create the next handoff

At the end of every session, write a new handoff under `C:/Users/rodin/Desktop/Brain/Sessions/{Task-Theme}/Handoffs/` following the exact structure below. This keeps every future "cold start" predictable — the next session picks up one file and knows everything it needs.

### Naming
`{Month-name} {Day-ordinal} {short-topic} Session.md`
e.g. `April 20th IR Scraper v1 Session.md`, `April 25th CELH Backend Session.md`.

Ordinal = `st` / `nd` / `rd` / `th`. One or two topic words. Keep the filename short.

### Required sections (in this order)

1. **YAML frontmatter** — `type: session-handoff`, `date: YYYY-MM-DD` (absolute, never relative), `topic: {one-line}`, `tags: [session, ...]`.
2. **`# {Title}`** heading matching the filename.
3. **`## Starting state`** — what was true at session start. Reference the prior handoff filename explicitly so the chain is walkable.
4. **`## Work done this session`** — grouped by logical chunks (numbered `### 1.` subsections work well). Each subsection should say *what changed* and *why*, not just the surface action. Capture root-cause insights.
5. **`## Current state`** — bullet list of what's working, what's partially working, what's not. Include concrete file paths for artifacts produced.
6. **`## Open decisions / pending work`** — numbered list of unresolved items. Each one should state the *decision* or *action* needed, not just a vague "look into X". If a decision is blocked on user input, say so.
7. **`## Key file paths`** — two-column table: Purpose | Path. Use absolute paths. Include scheduled task names and external system references.
8. **`## How to create the next handoff`** — paste this exact section verbatim. Never drop it; never let the template drift without updating all copies forward.

### Quality bar

- Write so the next session (cold, no conversation history) can act without re-asking you questions.
- Prefer concrete over abstract.
- Capture *why* a design choice was made when it's non-obvious. Code shows what; handoffs should show why.
- If you deleted, renamed, or moved files, explicitly mention it — the next session will otherwise hunt for the old paths.
- Keep it self-contained. Don't say "as discussed" — write out the discussion outcome.
