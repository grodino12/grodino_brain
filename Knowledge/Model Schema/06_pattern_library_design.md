# Pattern Library Design

How the pipeline absorbs notation variance across filings without needing code changes every time a new company uses a slightly different phrase.

---

## Core principle

**One pattern library (YAML file) per enum.**

| Enum | Pattern library |
|---|---|
| `Unit` | `unit_phrases.yaml` |
| `StatementType` | `statement_heading_patterns.yaml` |
| `FilingType` | `filing_type_patterns.yaml` |
| `Section` | `section_heading_patterns.yaml` |
| `NumericNotation` | `numeric_notation_patterns.yaml` |
| `Period` (not an enum but same pattern) | `period_phrase_patterns.yaml` |

All live in `~/.claude/skills/financials-extract/references/`.

---

## The 4-layer adaptation ladder

When `financials-extract` encounters a raw phrase, it resolves it to a canonical enum value through four layers in order.

### Layer 1 — Normalization
- lowercase, collapse whitespace, strip common punctuation
- strip prefixes like "consolidated", "condensed", "unaudited", "the"
- absorbs micro-variance without any YAML edit

### Layer 2 — Keyword match
- scan for distinctive tokens defined in each entry's `keywords` list
- e.g. `"operations"` / `"income"` / `"cash flows"` / `"balance sheet"`
- highest-confidence match; skips fuzzy scoring entirely

### Layer 3 — Fuzzy match (rapidfuzz)
- score the phrase against all `variants` across all entries
- **Graduated thresholds:**

| Score | Action |
|---|---|
| ≥ 95 | Silent auto-append to YAML |
| 85-94 | Accept + flag for periodic review |
| 70-84 | Prompt user with top 3 candidates |
| < 70 | Fail loudly; mark as novel |

### Layer 4 — User prompt + append
- On confirmed novel match, write the new variant back to the YAML
- Git tracks the history of phrases seen
- Next filing with the same phrase is an exact match (never re-prompts)

---

## Two kinds of pattern entries

### Phrase match — `PatternEntry`

For simple enums (Unit, StatementType, FilingType, Section, NumericNotation). Output is a canonical enum key.

```yaml
income_statement:
  canonical: INCOME_STATEMENT
  keywords: [operations, income]
  variants:
    - Consolidated Statements of Operations
    - Statement of Operations
    - Statement of Income
    - Statement of Consolidated Income
    - Consolidated Statements of Comprehensive Income
  fuzzy_threshold: 85
```

### Regex match — `RegexPatternEntry`

For structured data extraction (Period: year + quarter from a phrase). Uses regex with named capture groups.

```yaml
quarterly:
  canonical: QUARTERLY
  regex_patterns:
    - pattern: "q(\\d)\\s*[\\'']?(\\d{2,4})"           # "Q1'25", "Q1 2025"
      captures: { 1: fiscal_quarter, 2: fiscal_year }
    - pattern: "(\\d)q\\s*[\\'']?(\\d{2,4})"            # "1Q25"
      captures: { 1: fiscal_quarter, 2: fiscal_year }
    - pattern: "quarter\\s+(\\d)\\s*,?\\s+(\\d{4})"    # "Quarter 1, 2025"
      captures: { 1: fiscal_quarter, 2: fiscal_year }
    - pattern: "(first|second|third|fourth)\\s+quarter\\s+(\\d{4})"
      captures: { 1: fiscal_quarter_word, 2: fiscal_year }
```

---

## Shared normalization config

```yaml
# top-level of each pattern YAML file
normalization:
  case_insensitive: true
  collapse_whitespace: true
  strip_prefixes: [consolidated, condensed, unaudited, the]
  strip_punctuation: true
```

---

## Worked example — new variant never seen before

Filing says: `"Statement of Consolidated Income"` — not in the YAML yet.

1. **Normalize** → `"statement of consolidated income"`
2. **Keyword scan** → token `"income"` matches `income_statement.keywords: [operations, income]` → classified as `StatementType.INCOME_STATEMENT` with confidence 0.9
3. **Auto-append** the new phrase to the `variants` list in `statement_heading_patterns.yaml`
4. **Next run** with the same phrase is an exact match — zero compute

---

## Why the YAML itself is validated by Pydantic

Pattern files are loaded through `PatternLibrary.model_validate_json()` (or the YAML equivalent). This:
1. Rejects malformed YAML at load time, not mid-extraction
2. Enforces `no_duplicate_variants` — the same phrase can't appear in two entries
3. Enforces `fuzzy_threshold` is in range 0-100
4. Provides clear error messages if someone hand-edits the YAML badly

---

## Pattern libraries vs decisions ledger — related but different

| | Pattern libraries | Decisions ledger |
|---|---|---|
| **Input** | phrases (unit, heading, section) | line-item labels |
| **Output** | enum values | Excel model row numbers |
| **Scope** | shared across all tickers | per-ticker |
| **Location** | `financials-extract/references/` | `tickers/{ticker}/decisions_ledger.json` |
| **Used by** | `financials-extract` | `financials-reconcile` |
| **Mechanism** | fuzzy match + append-only | fuzzy match + append-only |

Same underlying pattern (fuzzy matching + progressive learning), applied at two different layers of the pipeline for two different jobs.

---

## Convergence expectations

1. **First filing from a new company**: a handful of user prompts, mostly for foreign issuers or unusual phrasings
2. **Second filing from same company**: zero prompts (everything auto-appended last time)
3. **New company later, different phrasing**: keyword match catches most of it without any YAML edit
4. **After 20-30 filings**: user prompts become rare — limited to genuinely novel IFRS / 20-F phrasings

Same progressive-learning arc the decisions ledger went through for CELH line items.
