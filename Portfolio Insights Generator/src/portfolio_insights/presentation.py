"""Presentation adapters for Streamlit tables, charts, and downloads."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal

import pandas as pd

from portfolio_insights.analytics import (
    TickerAnalytics,
    TraderAnalytics,
)
from portfolio_insights.models import DataQualityIssue, Transaction


def transactions_dataframe(transactions: Iterable[Transaction]) -> pd.DataFrame:
    """Return transactions in deterministic chronological display order."""

    ordered = sorted(transactions, key=lambda item: (item.timestamp, item.source_row))
    return pd.DataFrame.from_records(
        [
            {
                "Source Row": item.source_row,
                "Timestamp": item.timestamp,
                "Ticker": item.ticker,
                "Action": item.action.value,
                "Quantity": item.quantity,
                "Price": item.price,
                "Notional": item.notional,
                "Trader ID": item.trader_id or "UNKNOWN",
                "Signed Quantity": item.signed_quantity,
            }
            for item in ordered
        ],
        columns=[
            "Source Row",
            "Timestamp",
            "Ticker",
            "Action",
            "Quantity",
            "Price",
            "Notional",
            "Trader ID",
            "Signed Quantity",
        ],
    )


def ticker_activity_dataframe(items: Iterable[TickerAnalytics]) -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "Ticker": item.ticker,
                "Transactions": item.transaction_count,
                "Gross Volume": item.gross_share_volume,
                "Gross Notional": float(item.gross_notional),
                "Buy Volume": item.buy_volume,
                "Sell Volume": item.sell_volume,
                "Net Quantity": item.net_traded_quantity,
                "Buy VWAP": _optional_float(item.buy_vwap),
                "Sell VWAP": _optional_float(item.sell_vwap),
                "Named Traders": item.named_trader_count,
            }
            for item in items
        ]
    )


def trader_activity_dataframe(items: Iterable[TraderAnalytics]) -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "Trader ID": item.trader_id,
                "Transactions": item.transaction_count,
                "Gross Volume": item.gross_share_volume,
                "Gross Notional": float(item.gross_notional),
                "Distinct Tickers": item.ticker_count,
            }
            for item in items
        ]
    )


def trader_ticker_activity_dataframe(
    transactions: Iterable[Transaction],
    latest_prices: Mapping[str, Decimal],
) -> pd.DataFrame:
    """Aggregate one trader's filtered activity and mark it to latest prices."""

    records = [
        {
            "Ticker": item.ticker,
            "Buy Volume": item.quantity if item.action.value == "BUY" else 0,
            "Sell Volume": item.quantity if item.action.value == "SELL" else 0,
            "Gross Volume": item.quantity,
            "Gross Notional": float(item.notional),
            "Net Traded Quantity": item.signed_quantity,
        }
        for item in transactions
    ]
    columns = [
        "Ticker",
        "Buy Volume",
        "Sell Volume",
        "Net Traded Quantity",
        "Gross Volume",
        "Gross Notional",
        "Latest Observed Price",
        "Marked Net Flow Value",
    ]
    if not records:
        return pd.DataFrame(columns=columns)

    grouped = (
        pd.DataFrame.from_records(records)
        .groupby("Ticker", as_index=False, sort=True)
        .agg(
            {
                "Buy Volume": "sum",
                "Sell Volume": "sum",
                "Gross Volume": "sum",
                "Gross Notional": "sum",
                "Net Traded Quantity": "sum",
            }
        )
        .sort_values(["Gross Notional", "Ticker"], ascending=[False, True])
    )
    grouped["Latest Observed Price"] = [
        _optional_float(latest_prices.get(ticker)) for ticker in grouped["Ticker"]
    ]
    grouped["Marked Net Flow Value"] = [
        None if latest_prices.get(ticker) is None else float(latest_prices[ticker] * int(net_quantity))
        for ticker, net_quantity in zip(
            grouped["Ticker"], grouped["Net Traded Quantity"], strict=True
        )
    ]
    return grouped[columns].reset_index(drop=True)


def quality_issues_dataframe(issues: Iterable[DataQualityIssue]) -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "Source Row": issue.source_row,
                "Disposition": issue.disposition.value,
                "Issue Code": issue.code,
                "Message": issue.message,
                "Related Source Row": issue.related_source_row,
                **{f"Raw {key}": value for key, value in issue.raw_row.as_dict().items()},
            }
            for issue in issues
        ]
    )


def execution_activity_dataframe(
    transactions: Iterable[Transaction],
    *,
    frequency: str = "h",
) -> pd.DataFrame:
    """Aggregate buy/sell volume and execution VWAP into time buckets.

    This adapter is intended for a single ticker when the VWAP series is shown.
    Combining execution prices across securities would not be economically
    meaningful even though the volume columns remain additive.
    """

    records = [
        {
            "Timestamp": item.timestamp,
            "Buy Volume": item.quantity if item.action.value == "BUY" else 0,
            "Sell Volume": item.quantity if item.action.value == "SELL" else 0,
            "Gross Volume": item.quantity,
            "Weighted Notional": float(item.notional),
            "Transactions": 1,
        }
        for item in transactions
    ]
    columns = [
        "Time Bucket",
        "Buy Volume",
        "Sell Volume",
        "Gross Volume",
        "Execution VWAP",
        "Transactions",
    ]
    if not records:
        return pd.DataFrame(columns=columns)

    frame = pd.DataFrame.from_records(records)
    frame["Time Bucket"] = pd.to_datetime(frame["Timestamp"]).dt.floor(frequency)
    grouped = (
        frame.groupby("Time Bucket", as_index=False, sort=True)
        .agg(
            {
                "Buy Volume": "sum",
                "Sell Volume": "sum",
                "Gross Volume": "sum",
                "Weighted Notional": "sum",
                "Transactions": "sum",
            }
        )
    )
    grouped["Execution VWAP"] = grouped["Weighted Notional"] / grouped["Gross Volume"]
    return grouped[columns]


def canonical_transactions_csv(transactions: Iterable[Transaction]) -> bytes:
    frame = transactions_dataframe(transactions).rename(
        columns={
            "Source Row": "source_row",
            "Timestamp": "timestamp",
            "Ticker": "ticker",
            "Action": "action",
            "Quantity": "quantity",
            "Price": "price",
            "Notional": "notional",
            "Trader ID": "trader_id",
            "Signed Quantity": "signed_quantity",
        }
    )
    return frame.to_csv(index=False).encode("utf-8")


def quality_issues_csv(issues: Iterable[DataQualityIssue]) -> bytes:
    return quality_issues_dataframe(issues).to_csv(index=False).encode("utf-8")


def format_notional(value: Decimal | float) -> str:
    """Format notional without a currency symbol because currency is unknown."""

    return f"{value:,.2f}"


def format_signed_shares(value: int) -> str:
    return f"{value:+,}"


def _optional_float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)

