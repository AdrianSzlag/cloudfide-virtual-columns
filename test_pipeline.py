from pathlib import Path

import pandas as pd
import pytest

from pipeline import clean_sales, run_pipeline


@pytest.fixture
def raw_sales():
    return pd.DataFrame(
        [
            ["SO-1", "North", "Mouse", "2", "29.50", "", "2026-01-01"],
            ["SO-2", "South", "Mouse", "1", "29.50", "0.50", "2026-01-02"],
        ],
        columns=["Order ID", "Region", "Product", "Quantity ", "Unit Price", "Discount", "Order Date"],
    )


def test_cleans_export_artifacts_and_preserves_input(raw_sales):
    raw_sales.loc[0, ["Region", "Quantity ", "Unit Price"]] = [" north  ", "1 002", "29,50"]
    raw_sales.loc[1, "Unit Price"] = ""
    raw_sales = pd.concat([
        raw_sales,
        raw_sales.iloc[[0]],
        pd.DataFrame([list(raw_sales.columns)], columns=raw_sales.columns),
        pd.DataFrame([["TOTAL", "", "", "1003", "", "0.50", ""]], columns=raw_sales.columns),
    ], ignore_index=True)
    original = raw_sales.copy(deep=True)
    cleaned = clean_sales(raw_sales)
    assert cleaned["region"].tolist() == ["North", "South"]
    assert cleaned["quantity"].tolist() == [1002, 1]
    assert cleaned["unit_price"].tolist() == [2950, 2950]
    assert cleaned["discount"].tolist() == [0, 50]
    pd.testing.assert_frame_equal(raw_sales, original)


def test_keeps_distinct_lines_with_the_same_order_id(raw_sales):
    raw_sales.loc[1, "Order ID"] = "SO-1"
    assert len(clean_sales(raw_sales)) == 2


def test_fills_missing_prices_from_the_same_product(raw_sales):
    raw_sales.loc[1, ["Product", "Unit Price"]] = ["Keyboard", "89.00"]
    missing = raw_sales.copy()
    missing["Order ID"] = ["SO-3", "SO-4"]
    missing["Unit Price"] = ""
    data = pd.concat([raw_sales, missing], ignore_index=True)

    cleaned = clean_sales(data)

    assert cleaned["unit_price"].tolist() == [2950, 8900, 2950, 8900]


def test_aggregates_sales_and_returns_after_normalizing_regions(raw_sales, tmp_path):
    raw_sales.loc[1, "Region"] = " north "
    raw_sales.loc[2] = ["SO-3", "NORTH", "Mouse", "-1", "29.50", "", "2026-01-03"]
    raw_sales.loc[3] = ["SO-4", "South", "Mouse", "1", "29.50", "", "2026-01-04"]
    source = tmp_path / "sales.csv"
    output = tmp_path / "result.csv"
    raw_sales.to_csv(source, index=False)

    result = run_pipeline(source, output)

    # North: 2 * 29.50 + (29.50 - 0.50) - 29.50 = 58.50.
    expected = pd.DataFrame({
        "region": ["North", "South"],
        "revenue": ["58.50", "29.50"],
    })
    pd.testing.assert_frame_equal(result, expected)
    pd.testing.assert_frame_equal(pd.read_csv(output, dtype=str), expected)


@pytest.mark.parametrize("known_prices", [[], ["29.50", "30.00"]])
def test_does_not_guess_missing_prices(raw_sales, known_prices):
    rows = [raw_sales.iloc[0].copy() for _ in range(len(known_prices) + 1)]
    for index, row in enumerate(rows):
        row["Order ID"] = f"SO-{index}"
        row["Unit Price"] = known_prices[index] if index < len(known_prices) else ""
    with pytest.raises(ValueError, match="Cannot infer"):
        clean_sales(pd.DataFrame(rows).reset_index(drop=True))


@pytest.mark.parametrize(("column", "value"), [
    ("Quantity ", "1 2"),
    ("Quantity ", "1e309"),
    ("Quantity ", "__import__('os')"),
    ("Unit Price", "NaN"),
    ("Unit Price", "inf"),
    ("Unit Price", "0.001"),
    ("Discount", "=1+1"),
    ("Region", "=HYPERLINK(\"https://example.com\")"),
    ("Region", ""),
])
def test_invalid_data_does_not_replace_existing_output(raw_sales, tmp_path, column, value):
    raw_sales.loc[0, column] = value
    source = tmp_path / "sales.csv"
    output = tmp_path / "result.csv"
    raw_sales.to_csv(source, index=False)
    output.write_text("previous result\n")
    with pytest.raises(ValueError):
        run_pipeline(source, output)
    assert output.read_text() == "previous result\n"


@pytest.mark.parametrize(("quantity", "price"), [
    (str(2**63), "1.00"),
    ("1", str(2**63)),
    (str(2**62), "0.02"),
])
def test_rejects_integer_overflow(raw_sales, quantity, price):
    raw_sales.loc[0, ["Quantity ", "Unit Price"]] = [quantity, price]
    with pytest.raises(ValueError, match="integer range"):
        clean_sales(raw_sales)


def test_rejects_regional_sum_overflow_when_individual_rows_fit(raw_sales):
    raw_sales["Region"] = "North"
    raw_sales["Quantity "] = str(2**62)
    raw_sales["Unit Price"] = "0.01"
    raw_sales["Discount"] = ""
    for index in raw_sales.index:
        assert len(clean_sales(raw_sales.loc[[index]])) == 1
    with pytest.raises(ValueError, match="Revenue exceeds the supported integer range"):
        clean_sales(raw_sales)


@pytest.mark.parametrize("schema", ["missing_column", "extra_column"])
def test_rejects_unexpected_columns(raw_sales, schema):
    if schema == "missing_column":
        raw_sales = raw_sales.drop(columns="Region")
    else:
        raw_sales["Extra"] = "unused"
    with pytest.raises(ValueError, match="Unexpected sales CSV columns"):
        clean_sales(raw_sales)


@pytest.mark.parametrize("include_summary", [False, True])
def test_rejects_files_without_sales(raw_sales, tmp_path, include_summary):
    data = raw_sales.iloc[:0].copy()
    if include_summary:
        data.loc[0] = ["TOTAL", "", "", "0", "", "0.00", ""]
    source = tmp_path / "sales.csv"
    output = tmp_path / "result.csv"
    data.to_csv(source, index=False)
    with pytest.raises(ValueError, match="No sales rows found"):
        run_pipeline(source, output)
    assert not output.exists()


def test_calculates_exact_cents_and_keeps_returns(raw_sales, tmp_path):
    raw_sales.loc[0, ["Quantity ", "Unit Price", "Discount"]] = ["3", "0.10", "0.20"]
    raw_sales.loc[1, ["Quantity ", "Unit Price", "Discount"]] = ["-1", "1.25", ""]
    source = tmp_path / "sales.csv"
    output = tmp_path / "result.csv"
    raw_sales.to_csv(source, index=False)
    result = run_pipeline(source, output)
    assert result.to_dict("records") == [
        {"region": "North", "revenue": "0.10"},
        {"region": "South", "revenue": "-1.25"},
    ]
    assert output.read_text() == "region,revenue\nNorth,0.10\nSouth,-1.25\n"


def test_supplied_file_totals_and_repairs(tmp_path):
    source = Path(__file__).with_name("sales.csv")
    original = source.read_bytes()
    raw = pd.read_csv(source, dtype=str, keep_default_na=False)
    cleaned = clean_sales(raw)
    assert len(raw) == 1507
    assert len(cleaned) == 1500
    assert cleaned["quantity"].lt(0).sum() == 6
    assert cleaned["quantity"].ge(1000).sum() == 4
    prices = cleaned.set_index("order_id")["unit_price"]
    assert prices.loc[["SO-10610", "SO-11099", "SO-11350", "SO-11477"]].tolist() == [2100, 2100, 8900, 8900]

    output = tmp_path / "result.csv"
    result = run_pipeline(source, output)
    expected = pd.DataFrame({
        "region": ["Central", "East", "North", "South", "West"],
        "revenue": ["515824.67", "442219.91", "665897.52", "504036.04", "442268.89"],
    })
    pd.testing.assert_frame_equal(result, expected)
    pd.testing.assert_frame_equal(pd.read_csv(output, dtype=str), expected)
    assert source.read_bytes() == original
