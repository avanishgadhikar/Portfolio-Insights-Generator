from __future__ import annotations

from decimal import Decimal
from io import StringIO

from portfolio_insights.analytics import calculate_analytics
from portfolio_insights.presentation import (
    execution_activity_dataframe,
    format_notional,
    quality_issues_dataframe,
    ticker_activity_dataframe,
    trader_ticker_activity_dataframe,
    transactions_dataframe,
)
from portfolio_insights.processing import load_transactions_csv


HEADER = "timestamp,ticker,action,quantity,price,trader_id\n"
ROWS = """2024-01-15 10:20:00,AAPL,SELL,4,110.00,
2024-01-15 10:05:00,AAPL,BUY,10,100.00,T001
2024-01-15 10:05:00,AAPL,BUY,10,100.00,T001
"""


def _result():
    return load_transactions_csv(StringIO(HEADER + ROWS))


def test_transaction_frame_is_ordered_and_labels_unknown_trader() -> None:
    frame = transactions_dataframe(_result().transactions)

    assert list(frame["Source Row"]) == [3, 2]
    assert list(frame["Trader ID"]) == ["T001", "UNKNOWN"]
    assert list(frame["Signed Quantity"]) == [10, -4]


def test_execution_activity_has_side_volume_and_weighted_price() -> None:
    frame = execution_activity_dataframe(_result().transactions)

    assert len(frame) == 1
    assert frame.iloc[0]["Buy Volume"] == 10
    assert frame.iloc[0]["Sell Volume"] == 4
    assert frame.iloc[0]["Gross Volume"] == 14
    assert frame.iloc[0]["Execution VWAP"] == 1440 / 14


def test_trader_ticker_activity_calculates_filtered_net_flow() -> None:
    frame = trader_ticker_activity_dataframe(
        _result().transactions,
        {"AAPL": Decimal("125.50")},
    )

    assert len(frame) == 1
    assert frame.iloc[0]["Ticker"] == "AAPL"
    assert frame.iloc[0]["Buy Volume"] == 10
    assert frame.iloc[0]["Sell Volume"] == 4
    assert frame.iloc[0]["Gross Volume"] == 14
    assert frame.iloc[0]["Gross Notional"] == 1440.0
    assert frame.iloc[0]["Net Traded Quantity"] == 6
    assert frame.iloc[0]["Latest Observed Price"] == 125.5
    assert frame.iloc[0]["Marked Net Flow Value"] == 753.0


def test_ticker_frame_uses_numeric_chart_values() -> None:
    analytics = calculate_analytics(_result())
    frame = ticker_activity_dataframe(analytics.ticker_activity)

    assert frame.iloc[0]["Ticker"] == "AAPL"
    assert frame.iloc[0]["Gross Notional"] == 1440.0


def test_quality_frame_preserves_duplicate_traceability() -> None:
    frame = quality_issues_dataframe(_result().issues)
    duplicate = frame[frame["Issue Code"] == "exact_duplicate"].iloc[0]

    assert duplicate["Source Row"] == 4
    assert duplicate["Related Source Row"] == 3
    assert duplicate["Raw ticker"] == "AAPL"


def test_notional_format_omits_currency_symbol() -> None:
    formatted = format_notional(12345.6)

    assert formatted == "12,345.60"
    assert "$" not in formatted

