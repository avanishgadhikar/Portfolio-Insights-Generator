from __future__ import annotations

from decimal import Decimal
from io import StringIO
from pathlib import Path

import pytest

from portfolio_insights.models import IssueDisposition, TradeAction
from portfolio_insights.processing import CSVSchemaError, load_transactions_csv


HEADER = "timestamp,ticker,action,quantity,price,trader_id\n"


def test_sample_file_produces_expected_clean_dataset() -> None:
    sample_path = Path(__file__).parents[1] / "sample_transactions.csv"

    result = load_transactions_csv(sample_path)

    assert result.raw_row_count == 1030
    assert result.accepted_row_count == 1000
    assert result.quarantined_row_count == 30
    assert result.rejected_row_count == 0
    assert result.warning_count == 50
    assert len(result.issues_with_code("exact_duplicate")) == 30
    assert len(result.issues_with_code("missing_trader_id")) == 50


def test_normalizes_fields_but_preserves_raw_row() -> None:
    stream = StringIO(
        HEADER + "2024-01-15 19:05:00, aapl , buy ,200,150.40, T001 \n"
    )

    result = load_transactions_csv(stream)
    transaction = result.transactions[0]

    assert transaction.source_row == 2
    assert transaction.ticker == "AAPL"
    assert transaction.action is TradeAction.BUY
    assert transaction.quantity == 200
    assert transaction.price == Decimal("150.40")
    assert transaction.trader_id == "T001"
    assert transaction.raw_row.ticker == " aapl "
    assert transaction.raw_row.trader_id == " T001 "


def test_missing_trader_is_retained_as_warning() -> None:
    stream = StringIO(HEADER + "2024-01-15 19:05:00,AAPL,BUY,10,150.00,\n")

    result = load_transactions_csv(stream)

    assert result.accepted_row_count == 1
    assert result.transactions[0].trader_id is None
    issue = result.issues_with_code("missing_trader_id")[0]
    assert issue.disposition is IssueDisposition.WARNING


def test_exact_duplicate_is_quarantined_with_traceability() -> None:
    row = "2024-01-15 19:05:00,AAPL,BUY,10,150.00,T001\n"

    result = load_transactions_csv(StringIO(HEADER + row + row))

    assert result.accepted_row_count == 1
    assert result.quarantined_row_count == 1
    duplicate = result.issues_with_code("exact_duplicate")[0]
    assert duplicate.source_row == 3
    assert duplicate.related_source_row == 2


@pytest.mark.parametrize(
    ("row", "expected_code"),
    [
        ("bad,AAPL,BUY,10,150.00,T001\n", "invalid_timestamp"),
        ("2024-01-15 19:05:00,,BUY,10,150.00,T001\n", "missing_ticker"),
        ("2024-01-15 19:05:00,AAPL,HOLD,10,150.00,T001\n", "invalid_action"),
        ("2024-01-15 19:05:00,AAPL,BUY,10.5,150.00,T001\n", "invalid_quantity"),
        ("2024-01-15 19:05:00,AAPL,BUY,10,NaN,T001\n", "invalid_price"),
    ],
)
def test_invalid_values_reject_the_row(row: str, expected_code: str) -> None:
    result = load_transactions_csv(StringIO(HEADER + row))

    assert result.accepted_row_count == 0
    assert result.rejected_row_count == 1
    assert len(result.issues_with_code(expected_code)) == 1


def test_missing_required_column_raises_schema_error() -> None:
    stream = StringIO("timestamp,ticker,action,quantity,price\n")

    with pytest.raises(CSVSchemaError, match="trader_id"):
        load_transactions_csv(stream)

