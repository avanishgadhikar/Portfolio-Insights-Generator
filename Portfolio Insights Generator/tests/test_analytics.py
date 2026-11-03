from __future__ import annotations

from decimal import Decimal
from io import StringIO

from portfolio_insights.analytics import calculate_analytics, latest_prices_by_ticker
from portfolio_insights.processing import load_transactions_csv


HEADER = "timestamp,ticker,action,quantity,price,trader_id\n"


def _result():
    rows = "".join(
        [
            "2024-01-15 10:05:00,AAPL,BUY,10,100.00,T001\n",
            "2024-01-15 10:20:00,AAPL,SELL,4,110.00,T002\n",
            "2024-01-15 11:00:00,MSFT,BUY,5,200.00,\n",
            "2024-01-15 10:05:00,AAPL,BUY,10,100.00,T001\n",
        ]
    )
    return load_transactions_csv(StringIO(HEADER + rows))


def test_calculates_portfolio_totals_from_canonical_rows() -> None:
    analytics = calculate_analytics(_result())

    assert analytics.transaction_count == 3
    assert analytics.ticker_count == 2
    assert analytics.named_trader_count == 2
    assert analytics.gross_share_volume == 19
    assert analytics.gross_notional == Decimal("2440.00")
    assert analytics.buy_volume == 15
    assert analytics.sell_volume == 4
    assert analytics.net_traded_quantity == 11
    assert analytics.duplicates_quarantined == 1
    assert analytics.missing_trader_warnings == 1


def test_calculates_ticker_vwap_and_orders_by_notional() -> None:
    analytics = calculate_analytics(_result())

    aapl = analytics.ticker_activity[0]
    assert aapl.ticker == "AAPL"
    assert aapl.gross_notional == Decimal("1440.00")
    assert aapl.net_traded_quantity == 6
    assert aapl.buy_vwap == Decimal("100.00")
    assert aapl.sell_vwap == Decimal("110.00")
    assert aapl.named_trader_count == 2


def test_unknown_trader_is_separate_from_named_leaderboard() -> None:
    analytics = calculate_analytics(_result())

    assert [trader.trader_id for trader in analytics.trader_activity] == ["T001", "T002"]
    assert analytics.unknown_trader_transaction_count == 1
    assert analytics.unknown_trader_volume == 5
    assert analytics.unknown_trader_notional == Decimal("1000.00")


def test_peak_hour_uses_gross_share_volume() -> None:
    analytics = calculate_analytics(_result())

    assert analytics.peak_hour_by_volume is not None
    assert analytics.peak_hour_by_volume.hour.hour == 10
    assert analytics.peak_hour_by_volume.gross_share_volume == 14


def test_empty_dataset_is_supported() -> None:
    analytics = calculate_analytics(load_transactions_csv(StringIO(HEADER)))

    assert analytics.transaction_count == 0
    assert analytics.period_start is None
    assert analytics.period_end is None
    assert analytics.ticker_activity == ()
    assert analytics.peak_hour_by_volume is None


def test_latest_price_uses_source_row_to_break_timestamp_ties() -> None:
    result = load_transactions_csv(
        StringIO(
            HEADER
            + "2024-01-15 12:00:00,AAPL,BUY,10,100.00,T001\n"
            + "2024-01-15 12:00:00,AAPL,SELL,5,101.25,T002\n"
            + "2024-01-15 11:00:00,MSFT,BUY,2,300.00,T001\n"
        )
    )

    assert latest_prices_by_ticker(result.transactions) == {
        "AAPL": Decimal("101.25"),
        "MSFT": Decimal("300.00"),
    }

