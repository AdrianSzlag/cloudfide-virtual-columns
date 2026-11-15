from decimal import Decimal
from pathlib import Path

import pandas as pd

from solution import add_virtual_column


PROJECT_DIR = Path(__file__).resolve().parent
COLUMNS = ["order_id", "region", "product", "quantity", "unit_price", "discount", "order_date"]


def _to_int64(values: pd.Series) -> pd.Series:
    """Convert validated strings or Decimal amounts; pandas rejects overflow."""
    try:
        return values.astype("int64")
    except OverflowError as error:
        raise ValueError("Number exceeds the supported integer range") from error


def _money_to_cents(values: pd.Series) -> pd.Series:
    values = values.str.replace(",", ".", regex=False)
    if not values.str.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?").all():
        raise ValueError("Prices and discounts must be non-negative amounts with at most two decimals")
    return _to_int64(values.map(lambda amount: Decimal(amount) * 100))


def _fill_missing_prices(data: pd.DataFrame) -> pd.Series:
    known = _money_to_cents(data.loc[data["unit_price"].ne(""), "unit_price"])
    prices = known.astype("Int64").reindex(data.index)
    by_product = prices.groupby(data["product"])
    if (prices.isna() & by_product.transform("nunique").ne(1)).any():
        raise ValueError("Cannot infer a missing price: product needs exactly one known price")
    return prices.fillna(by_product.transform("first")).astype("int64")


def clean_sales(data: pd.DataFrame) -> pd.DataFrame:
    """Clean the supplied export without changing the input frame."""
    data = data.loc[~data.eq(data.columns).all(axis=1)].copy()
    data.columns = data.columns.str.strip().str.lower().str.replace(" ", "_", regex=False)
    if list(data.columns) != COLUMNS:
        raise ValueError("Unexpected sales CSV columns")

    data = data.loc[data["order_id"].ne("TOTAL")].drop_duplicates().copy()
    if data.empty:
        raise ValueError("No sales rows found")
    data["region"] = data["region"].str.strip().str.title()
    # Restrict exported labels to plain names, including when opened in a spreadsheet.
    if not data["region"].str.fullmatch(r"[A-Za-z]+(?: [A-Za-z]+)*").all():
        raise ValueError("Region must be a non-empty name containing letters and spaces")

    quantity = data["quantity"]
    if not quantity.str.fullmatch(r"-?(?:[0-9]+|[0-9]{1,3}(?: [0-9]{3})+)").all():
        raise ValueError("Quantity must be an integer, optionally with spaces between thousands")
    data["quantity"] = _to_int64(quantity.str.replace(" ", "", regex=False))

    data["unit_price"] = _fill_missing_prices(data)
    data["discount"] = _money_to_cents(data["discount"].replace("", "0"))

    # Bound both row calculations and regional sums before using int64 arithmetic.
    bound = sum(
        abs(int(quantity)) * int(price) + int(discount)
        for quantity, price, discount in data[["quantity", "unit_price", "discount"]].itertuples(index=False, name=None)
    )
    if bound > 2**63 - 1:
        raise ValueError("Revenue exceeds the supported integer range")
    return data


def run_pipeline(
    input_path=PROJECT_DIR / "sales.csv",
    output_path=PROJECT_DIR / "revenue_by_region.csv",
) -> pd.DataFrame:
    raw = pd.read_csv(input_path, dtype=str, keep_default_na=False)
    sales = clean_sales(raw)
    sales = add_virtual_column(sales, "quantity * unit_price - discount", "revenue")
    if "revenue" not in sales:
        raise ValueError("Revenue calculation failed")
    totals = sales.groupby("region", as_index=False, sort=True)["revenue"].sum()
    totals["revenue"] = totals["revenue"].map(lambda cents: f"{Decimal(cents) / 100:.2f}")
    totals.to_csv(output_path, index=False)
    return totals


if __name__ == "__main__":
    run_pipeline()
