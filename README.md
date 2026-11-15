# Virtual Columns and Sales Revenue

Python and pandas solution for calculating a column and aggregating sales revenue by region.

## Setup and Run

Requires Python 3.9 or newer. Tested with Python 3.9.6 and the versions in `requirements.txt`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python pipeline.py
python -m pytest -q
```

The pipeline reads `sales.csv` and writes `revenue_by_region.csv` next to `pipeline.py`.
It does not change the source file. The output contains `region` and `revenue`, sorted by region.

## Data Problems and Cleanup

The source has 1507 rows, excluding its first header. Cleanup leaves 1500 sales lines.
Counts below refer to the source unless stated otherwise. Some problems overlap.

| Problem | Count | Handling |
| --- | ---: | --- |
| Spaces and capital letters in column names | 7 column names; `Quantity ` also has a trailing space | Strip, lowercase, and replace spaces with underscores so labels meet the function's rules. |
| Header repeated inside the data | 1 row | Remove the row matching the complete CSV header. |
| Summary labelled `TOTAL` | 1 row | Remove it; it is an aggregate, not a sale. |
| Exact duplicate sales lines | 5 extra copies | Keep one copy of each complete row. Do not deduplicate by order ID alone. |
| Region whitespace or inconsistent case | 15 rows: 8 with whitespace, 10 with inconsistent case; 3 overlap | Strip surrounding whitespace and use title case. |
| Spaces separating thousands in quantity | 4 rows | Convert values such as `1 762` to the integer `1762`. |
| Decimal comma in unit price | 7 rows | Convert the comma to a decimal point. |
| Missing unit price on a sale | 4 rows | Use the only known price for that product. All eight products have one distinct known price in this file. |
| Empty discount | 963 rows in the source; 959 after deduplication | Set to zero, as specified in the task. |
| Negative quantity | 6 rows | Keep as returns. They reduce revenue. |

The missing prices are `21.00` for `SO-10610` and `SO-11099`, and `89.00` for `SO-11350` and `SO-11477`.
The blank price, region, product and date on the `TOTAL` row are part of the summary, not missing sale data.
The remaining sale dates are valid ISO dates. Dates and product names are not changed.

## Assumptions and Calculations

- Exact duplicate rows are repeated export records. Distinct lines sharing an order ID are kept.
- A missing price can be inferred only when that product has exactly one distinct known price. Otherwise the pipeline raises an error instead of guessing or dropping the row.
- Negative quantities represent returns. Quantities above 1000 are kept; there is no evidence they are errors.
- Discount is an amount for the entire line. Revenue is always `quantity * unit_price - discount`.
- Prices and discounts are non-negative amounts with at most two decimal places. All amounts use the same unspecified currency; no conversion is applied.
- Amounts are stored as integer hundredths during calculation. `add_virtual_column` calculates revenue in those units; the CSV formats totals with exactly two decimal places.
- `Decimal` converts amounts to integer hundredths and formats the totals without binary floating-point rounding.
- Region names contain letters and spaces. Invalid or empty names cause an error, including spreadsheet formula prefixes.
- Malformed numbers, unexpected columns, and values that could overflow integer calculations cause an error. Validation finishes before the output file is opened.

## Virtual Column Function

`solution.py` exports `add_virtual_column(df, role, new_column)`.
It supports column names, `+`, `-`, `*`, and parentheses with normal arithmetic precedence.
Labels must contain only ASCII letters and underscores. Referenced columns must be numeric.
Duplicate labels and overwriting an existing column are rejected.
Invalid expressions or labels return an empty DataFrame. The input is not modified.

The function interprets allowed AST nodes without `eval()` or `DataFrame.eval()`.
Expressions are limited to 4096 characters. Python object columns are rejected before arithmetic.
This is a restriction on expressions, not a sandbox for untrusted Python objects or custom pandas classes.

## Tests

`python -m pytest -q` runs all tests.

- `test_virtual_column.py`: the six supplied test functions, unchanged, plus arithmetic, validation and security cases.
- `test_pipeline.py`: cleanup, price recovery, exact amounts, returns, duplicate handling, invalid input, overflow and totals for the supplied CSV.

Tests write temporary output files. They do not overwrite the project result or edit `sales.csv`.
