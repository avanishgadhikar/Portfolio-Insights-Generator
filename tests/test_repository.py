from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from portfolio_insights.models import RawTransactionRow, TradeAction, Transaction
from portfolio_insights.repository import InMemoryTransactionRepository


def _transaction(
    source_row: int,
    timestamp: str,
    ticker: str,
    action: TradeAction = TradeAction.BUY,
) -> Transaction:
    raw = RawTransactionRow(timestamp, ticker, action.value, "10", "100.00", "T001")
    return Transaction(
        source_row=source_row,
        timestamp=datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S"),
        ticker=ticker,
        action=action,
        quantity=10,
        price=Decimal("100.00"),
        trader_id="T001",
        raw_row=raw,
    )


def test_repository_orders_globally_and_within_ticker() -> None:
    later = _transaction(2, "2024-01-15 12:00:00", "AAPL")
    earlier = _transaction(3, "2024-01-15 10:00:00", "MSFT")
    tied_later_source_row = _transaction(5, "2024-01-15 11:00:00", "AAPL")
    tied_earlier_source_row = _transaction(4, "2024-01-15 11:00:00", "AAPL")

    repository = InMemoryTransactionRepository(
        [later, earlier, tied_later_source_row, tied_earlier_source_row]
    )

    assert [item.source_row for item in repository.get_all_chronological()] == [3, 4, 5, 2]
    assert [item.source_row for item in repository.get_by_ticker(" aapl ")] == [4, 5, 2]
    assert repository.get_tickers() == ("AAPL", "MSFT")


def test_date_filter_is_inclusive() -> None:
    transactions = [
        _transaction(2, "2024-01-15 10:00:00", "AAPL"),
        _transaction(3, "2024-01-15 11:00:00", "AAPL"),
        _transaction(4, "2024-01-15 12:00:00", "AAPL"),
    ]
    repository = InMemoryTransactionRepository(transactions)
    boundary = datetime(2024, 1, 15, 11, 0, 0)

    result = repository.get_by_ticker("AAPL", start=boundary, end=boundary)

    assert [item.source_row for item in result] == [3]


def test_unknown_ticker_returns_empty_tuple() -> None:
    repository = InMemoryTransactionRepository([])

    assert repository.get_by_ticker("AAPL") == ()


def test_invalid_date_range_is_rejected() -> None:
    repository = InMemoryTransactionRepository([])

    with pytest.raises(ValueError, match="Start"):
        repository.get_all_chronological(
            start=datetime(2024, 1, 16),
            end=datetime(2024, 1, 15),
        )

