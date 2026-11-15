import pytest

import pandas as pd
from solution import add_virtual_column


def test_sum_of_two_columns():
    df = pd.DataFrame([[1, 1]] * 2, columns = ["label_one", "label_two"])
    df_expected = pd.DataFrame([[1, 1, 2]] * 2, columns = ["label_one", "label_two", "label_three"])
    df_result = add_virtual_column(df, "label_one+label_two", "label_three")
    assert df_result.equals(df_expected), f"The function should sum the columns: label_one and label_two.\n\nResult:\n\n{df_result}\n\nExpected:\n\n{df_expected}"


def test_multiplication_of_two_columns():
    df = pd.DataFrame([[1, 1]] * 2, columns = ["label_one", "label_two"])
    df_expected = pd.DataFrame([[1, 1, 1]] * 2, columns = ["label_one", "label_two", "label_three"])
    df_result = add_virtual_column(df, "label_one * label_two", "label_three")
    assert df_result.equals(df_expected), f"The function should multiply the columns: label_one and label_two.\n\nResult:\n\n{df_result}\n\nExpected:\n\n{df_expected}"


def test_subtraction_of_two_columns():
    df = pd.DataFrame([[1, 1]] * 2, columns = ["label_one", "label_two"])
    df_expected = pd.DataFrame([[1, 1, 0]] * 2, columns = ["label_one", "label_two", "label_three"])
    df_result = add_virtual_column(df, "label_one - label_two", "label_three")
    assert df_result.equals(df_expected), f"The function should subtract the columns: label_one and label_two.\n\nResult:\n\n{df_result}\n\nExpected:\n\n{df_expected}"


def test_empty_result_when_invalid_labels():
    df = pd.DataFrame([[1, 2]] * 3, columns = ["label_one", "label_two"])
    df_result = add_virtual_column(df, "label_one + label_two", "label3")
    assert df_result.empty, f"Should return an empty df when the \"new_column\" is invalid.\n\nResult:\n\n{df_result}\n\nExpected:\n\nEmpty df"


def test_empty_result_when_invalid_rules():
    df = pd.DataFrame([[1, 1]] * 2, columns = ["label_one", "label_two"])
    df_result = add_virtual_column(df, "label&one + label_two", "label_three")
    assert df_result.empty, f"Should return an empty df when the role have invalid character: '&'.\n\nResult:\n\n{df_result}\n\nExpected:\n\nEmpty df"
    df_result = add_virtual_column(df, "label_five + label_two", "label_three")
    assert df_result.empty, f"Should return an empty df when the role have a column which isn't in the df: 'label_five'.\n\nResult:\n\n{df_result}\n\nExpected:\n\nEmpty df"


def test_when_extra_spaces_in_rules():
    df = pd.DataFrame([[1, 1]] * 2, columns = ["label_one", "label_two"])
    df_expected = pd.DataFrame([[1, 1, 2]] * 2, columns = ["label_one", "label_two", "label_three"])
    df_result = add_virtual_column(df, "label_one + label_two ", "label_three")
    assert df_result.equals(df_expected), f"Should work when the role have spaces between the operation and the column.\n\nResult:\n\n{df_result}\n\nExpected:\n\n{df_expected}"
    df_result = add_virtual_column(df, "  label_one + label_two ", "label_three")
    assert df_result.equals(df_expected), f"Should work when the role have extra spaces in the start/end.\n\nResult:\n\n{df_result}\n\nExpected:\n\n{df_expected}"


# Additional security and data preservation tests

@pytest.mark.parametrize("role", [
    "__import__('os').system('echo unsafe')",
    "a[0]",
    "a / b",
    "a ** b",
    "a + 1",
    "a + b # ignored payload",
])
def test_rejects_unsupported_expressions_without_changing_input(role):
    df = pd.DataFrame({"a": [2], "b": [3]})
    original = df.copy(deep=True)
    assert add_virtual_column(df, role, "total").empty
    pd.testing.assert_frame_equal(df, original)


def test_rejects_unicode_identifier_normalization():
    # Python normalizes the Kelvin sign to the ASCII identifier K.
    df = pd.DataFrame({"K": [2], "b": [3]})
    assert add_virtual_column(df, "\u212a + b", "total").empty


@pytest.mark.parametrize("label", ["a\n", "a.b", "a[0]", "a\x00", "\u212a"])
def test_rejects_invalid_column_labels(label):
    assert add_virtual_column(pd.DataFrame({label: [1]}), "a", "total").empty
    assert add_virtual_column(pd.DataFrame({"a": [1]}), "a", label).empty


def test_rejects_oversized_expression():
    role = "a + " * 1024 + "a"
    assert add_virtual_column(pd.DataFrame({"a": [1]}), role, "total").empty


def test_does_not_invoke_arithmetic_on_python_objects():
    calls = []

    class Payload:
        def __add__(self, other):
            calls.append("executed")
            return 0

    df = pd.DataFrame({"a": [Payload()], "b": [1]})
    result = add_virtual_column(df, "a + b", "total")
    assert calls == []
    assert result.empty


def test_does_not_repeat_strings():
    df = pd.DataFrame({"a": ["payload"], "b": [100]})
    assert add_virtual_column(df, "a * b", "total").empty


def test_rejects_duplicate_labels_and_overwriting():
    df = pd.DataFrame([[1, 2]], columns=["a", "a"])
    assert add_virtual_column(df, "a + a", "total").empty
    df = pd.DataFrame({"a": [1]})
    assert add_virtual_column(df, "a + a", "a").empty


def test_valid_calculation_preserves_original_data():
    df = pd.DataFrame({"a": [2, 4], "b": [3, 5]}, index=[10, 20])
    original = df.copy(deep=True)
    result = add_virtual_column(df, "a * b - a", "total")
    expected = original.assign(total=[4, 16])
    pd.testing.assert_frame_equal(result, expected)
    pd.testing.assert_frame_equal(df, original)


@pytest.mark.parametrize(("role", "expected"), [
    ("a + b * c", 14),
    ("(a + b) * c", 20),
    ("a - b - c", -5),
    ("a - (b - c)", 3),
])
def test_operation_precedence_and_parentheses(role, expected):
    df = pd.DataFrame({"a": [2], "b": [3], "c": [4]})
    result = add_virtual_column(df, role, "total")
    pd.testing.assert_series_equal(result["total"], pd.Series([expected], name="total"))


@pytest.mark.parametrize("role", ["", "  ", "a +", "(a + b", None, 123])
def test_rejects_empty_malformed_or_non_string_expressions(role):
    df = pd.DataFrame({"a": [2], "b": [3]})
    assert add_virtual_column(df, role, "total").empty
