# MD&A disaggregation JSON schema

Top-level structure of `{TICKER}.json`:

```json
{
  "ticker": "CELH",
  "periods": ["Q1 2023", "Q2 2023", "Q3 2023", "Q4 2023", "FY2023", "Q1 2024", ...],
  "ytd_periods": ["9M 2023", "9M 2024", "9M 2025"],
  "geography": { ... },
  "customer_concentration": { ... },
  "functional_concentration": { ... },
  "brand_contribution": { ... },
  "pro_forma": { ... },
  "sga_walk": { ... },
  "gp": { ... },
  "other_inc_exp": { ... },
  "taxonomy_notes": { ... }
}
```

## periods, ytd_periods

Lists. `periods` is the column sequence in the workbook (always include Q4 placeholders even if derived). `ytd_periods` are the 9M / 6M cumulative views used in Q4 derivation; not displayed as their own columns.

## Source-cited values

Throughout the JSON, hardcoded values are tuples/arrays of `[number, source_note]`:

```json
{ "Q1 2023": [248552, "Q1 2024 10-Q comparable column. Note 4 Revenue."] }
```

Use `null` to indicate "not disclosed for this period." Use `"n/d"` for percentages where derivation is impossible.

## geography

```json
"geography": {
  "regions": ["North America", "Europe", "Asia-Pacific", "Other"],
  "data": {
    "North America": {
      "Q1 2023": [248552, "Q1 2024 10-Q comparable column"],
      "Q2 2023": [310815, "..."],
      ...
    },
    "Europe": { ... },
    ...
  }
}
```

Q4 cells are NOT populated in JSON. The build script generates `=FY-Q1-Q2-Q3` formulas at Q4 column positions.

## customer_concentration

```json
"customer_concentration": {
  "customers": ["Pepsi", "Costco", "Amazon", "All others"],
  "data": {
    "Pepsi": {
      "Q1 2023": [0.602, "Q1 2023 10-Q"],
      ...
    },
    "Amazon": {
      "Q1 2023": [0.084, "Q1 2023 10-Q"],
      ...   // sparse — periods where below 10% threshold are omitted
    }
  }
}
```

Periods where a customer is below 10% threshold are simply omitted from that customer's dict. The build script renders `n/d` with a cell note "below 10% threshold" for missing periods.

## functional_concentration

```json
"functional_concentration": {
  "single_period": {
    "FY2023": [0.961, "FY2023 10-K"],
    "Q3 2024": [0.945, "Q3 2024 10-Q"],
    ...
  },
  "ytd": {
    "Q3 2024": [0.954, "Q3 2024 10-Q (9M)"],
    ...
  }
}
```

## brand_contribution

```json
"brand_contribution": {
  "active_periods": ["Q1 2025", "Q2 2025", "Q3 2025", "Q4 2025", "FY2025"],
  "residual_brand_label": "Celsius (residual)",
  "acquired_brands": [
    {
      "name": "Alani Nu",
      "data": {
        "Q1 2025": [0, "Pre-acquisition (closed April 1, 2025)."],
        "Q2 2025": [301200, "Q2 2025 10-Q Note 5."],
        ...
      }
    },
    {
      "name": "Rockstar",
      "data": { ... }
    }
  ]
}
```

Q4 cells for acquired brands are formula-derived (`=FY - Q1 - Q2 - Q3`). The residual brand is always a formula (`=Total Revenue - sum of acquired brands`).

## pro_forma

```json
"pro_forma": {
  "periods": ["Q3 2024", "Q3 2025", "9M 2024", "9M 2025", "FY2024", "FY2025"],
  "as_reported": {
    "Q3 2024": [265748, "Q3 2025 10-Q N5"],
    ...
  },
  "pro_forma_values": {
    "Q3 2024": [513912, "Q3 2025 10-Q N5"],
    ...
  }
}
```

## sga_walk

```json
"sga_walk": {
  "totals": {
    "Q1 2023": [68900, "Q1 2023 10-Q"],
    ...
  },
  "data": {
    "Q1 2023": {
      "mkt_invest": 16500,
      "storage": -3000,
      "employee_ms": 3600,
      "admin": 5500,
      "stock_comp": 1200,
      "other_admin": 1400,
      "src": "Q1 2023 10-Q MD&A: SG&A $68.9M (+$25.1M YoY). Marketing +$16.5M; Storage -$3.0M; Employee +$3.6M; Admin +$5.5M; Stock comp +$1.2M; Other +$1.4M."
    },
    ...
  },
  "ytd_data": {
    "9M 2023": { ...same shape... },
    ...
  },
  "distributor_term_separate": {
    "Q3 2025": [246700, "Q3 2025 10-Q. Separate IS line."],
    ...
  }
}
```

### Driver bucket keys (canonical taxonomy)

**Marketing & Selling:**
- `mkt_invest` — marketing investments / campaigns
- `storage` — storage / distribution
- `employee_ms` — sales/marketing employee costs (or generic "Employee" in pre-segregation eras)
- `<acquired_brand>_ms` — e.g., `alani_ms` for Alani Nu's M&S portion
- `other_selling` — other selling expenses

**General & Admin:**
- `admin` — administrative expenses (legacy general admin)
- `acq_integ` — acquisition and integration costs
- `<acquired_brand>_ga` — e.g., `alani_ga` for Alani Nu's G&A portion
- `contingent` — contingent consideration remeasurement
- `legal_accrual` — legal accrual booking (positive) or reversal (negative)
- `stock_comp` — stock-based compensation (legacy era)
- `other_admin` — other administrative

**Special:**
- `distrib_term` — distributor termination (when inside SG&A; pre-2025 era for CELH)

The build script knows which keys belong to which bucket. To add a new key for a ticker not covered, document in `taxonomy_notes`.

## gp

```json
"gp": {
  "totals": {
    "Q1 2023": [113800, "Q1 2023 10-Q"],
    ...
  },
  "drivers": ["raw", "promo", "freight", "mix", "brand", "inv", "tariffs"],
  "driver_data": {
    "Q1 2023": {
      "raw": "+",
      "freight": "-",
      "mix": "+",
      "src": "Q1 2023 10-Q",
      "q": "Volume leverage; reduced higher-cost intl can mix; offset by inventory write-offs and freight from Pepsi distribution integration."
    },
    ...
  }
}
```

Driver values: `"+"` (favorable) | `"-"` (unfavorable) | omitted (not mentioned). The verbatim quote `q` is the cell-note source.

## other_inc_exp

```json
"other_inc_exp": {
  "totals": {
    "Q1 2023": [4900, "Q1 2023 10-Q"],
    ...
  },
  "data": {
    "FY2025": {
      "int_inc": -18200,
      "int_exp": -49000,
      "rockstar_agency": 12600,
      "fx_other": -700,
      "src": "FY2025 10-K full walk: ..."
    }
  }
}
```

## taxonomy_notes

Per-ticker mapping decisions and quirks:

```json
"taxonomy_notes": {
  "sga_2023_to_2025_shift": "CELH 2023-2024 era: flat SG&A walk (Marketing/Storage/Employee/Admin/Stock comp). CELH 2025 era: hierarchical M&S vs G&A split. Pre-2025 'Employee' costs map to employee_ms (M&S bucket); pre-2025 'Stock comp' maps to stock_comp under G&A.",
  "distributor_term_relocation": "Pre-2025: Distributor Termination Fees were inside SG&A. Q3 2025+: split into separate IS line ($246.7M Q3 / $327.5M FY). Tracked in distributor_term_separate."
}
```
