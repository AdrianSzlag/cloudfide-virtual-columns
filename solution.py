import ast
import operator
import re

import pandas as pd
from pandas.api.types import is_numeric_dtype


MAX_EXPRESSION_LENGTH = 4096


def add_virtual_column(df: pd.DataFrame, role: str, new_column: str) -> pd.DataFrame:
    """Return a copy with a calculated column, or an empty frame for invalid input.

    Expressions use column names, +, -, *, and optional parentheses.
    Column names contain only ASCII letters and underscores.
    Referenced columns must be numeric; expressions are limited to 4096 characters.
    """
    labels = [*df.columns, new_column]
    if any(
        not isinstance(label, str) or not re.fullmatch(r"[A-Za-z_]+", label)
        for label in labels
    ):
        return pd.DataFrame()
    if not df.columns.is_unique or new_column in df.columns:
        return pd.DataFrame()
    if (
        not isinstance(role, str)
        or len(role) > MAX_EXPRESSION_LENGTH
        or not re.fullmatch(r"[A-Za-z_+*()\s-]+", role, flags=re.ASCII)
    ):
        return pd.DataFrame()

    operations = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul}

    def calculate(node):
        if isinstance(node, ast.Name):
            column = df[node.id]
            if not is_numeric_dtype(column):
                raise ValueError("Referenced columns must be numeric")
            return column
        if isinstance(node, ast.BinOp) and type(node.op) in operations:
            operation = operations[type(node.op)]
            return operation(calculate(node.left), calculate(node.right))
        raise ValueError("Unsupported expression")

    try:
        expression = ast.parse(role.strip(), mode="eval")
        values = calculate(expression.body)
        result = df.copy()
        result[new_column] = values
        return result
    except (SyntaxError, KeyError, TypeError, ValueError, RecursionError):
        return pd.DataFrame()
