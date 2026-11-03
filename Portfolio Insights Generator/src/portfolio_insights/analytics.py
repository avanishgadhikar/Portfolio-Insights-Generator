"""Deterministic transaction analytics used by the dashboard and LLM boundary."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from portfolio_insights.models import ProcessingResult, TradeAction, Transaction


@dataclass(frozen=True, slots=True)
class TickerAnalytics:
    ticker: str
    transaction_count: int
    gross_share_volume: int
    gross_notional: Decimal
    buy_volume: int
    sell_volume: int
    net_traded_quantity: int
    buy_vwap: Decimal | None
    sell_vwap: Decimal | None
    named_trader_count: int


@dataclass(frozen=True, slots=True)
class TraderAnalytics:
    trader_id: str
    transaction_count: int
    gross_share_volume: int
    gross_notional: Decimal
    ticker_count: int


@dataclass(frozen=True, slots=True)
class HourlyAnalytics:
    hour: datetime
    transaction_count: int
    gross_share_volume: int
    gross_notional: Decimal
    net_traded_quantity: int


@dataclass(frozen=True, slots=True)
class PortfolioAnalytics:
    transaction_count: int
    ticker_count: int
    named_trader_count: int
    period_start: datetime | None
    period_end: datetime | None
    gross_share_volume: int
    gross_notional: Decimal
    buy_volume: int
    sell_volume: int
    buy_notional: Decimal
    sell_notional: Decimal
    net_traded_quantity: int
    ticker_activity: tuple[TickerAnalytics, ...]
    trader_activity: tuple[TraderAnalytics, ...]
    hourly_activity: tuple[HourlyAnalytics, ...]
    unknown_trader_transaction_count: int
    unknown_trader_volume: int
    unknown_trader_notional: Decimal
    duplicates_quarantined: int
    rejected_rows: int
    missing_trader_warnings: int

    @property
    def peak_hour_by_volume(self) -> HourlyAnalytics | None:
        if not self.hourly_activity:
            return None
        # hourly_activity is chronological, so max() keeps the earliest hour
        # when multiple buckets have the same volume.
        return max(self.hourly_activity, key=lambda item: item.gross_share_volume)


@dataclass(slots=True)
class _Accumulator:
    transaction_count: int = 0
    gross_share_volume: int = 0
    gross_notional: Decimal = Decimal("0")
    buy_volume: int = 0
    sell_volume: int = 0
    buy_notional: Decimal = Decimal("0")
    sell_notional: Decimal = Decimal("0")
    net_traded_quantity: int = 0

    def add(self, transaction: Transaction) -> None:
        self.transaction_count += 1
        self.gross_share_volume += transaction.quantity
        self.gross_notional += transaction.notional
        self.net_traded_quantity += transaction.signed_quantity
        if transaction.action is TradeAction.BUY:
            self.buy_volume += transaction.quantity
            self.buy_notional += transaction.notional
        else:
            self.sell_volume += transaction.quantity
            self.sell_notional += transaction.notional


def calculate_analytics(result: ProcessingResult) -> PortfolioAnalytics:
    """Calculate all supported facts from canonical transactions.

    The function performs no market-price enrichment. Net traded quantity is the
    signed flow within the uploaded period, not a confirmed current position.
    """

    overall = _Accumulator()
    ticker_accumulators: defaultdict[str, _Accumulator] = defaultdict(_Accumulator)
    trader_accumulators: defaultdict[str, _Accumulator] = defaultdict(_Accumulator)
    hour_accumulators: defaultdict[datetime, _Accumulator] = defaultdict(_Accumulator)
    ticker_named_traders: defaultdict[str, set[str]] = defaultdict(set)
    trader_tickers: defaultdict[str, set[str]] = defaultdict(set)
    unknown_trader = _Accumulator()

    for transaction in result.transactions:
        overall.add(transaction)
        ticker_accumulators[transaction.ticker].add(transaction)
        hour = transaction.timestamp.replace(minute=0, second=0, microsecond=0)
        hour_accumulators[hour].add(transaction)

        if transaction.trader_id is None:
            unknown_trader.add(transaction)
        else:
            trader_accumulators[transaction.trader_id].add(transaction)
            trader_tickers[transaction.trader_id].add(transaction.ticker)
            ticker_named_traders[transaction.ticker].add(transaction.trader_id)

    ticker_activity = tuple(
        sorted(
            (
                _build_ticker_analytics(
                    ticker,
                    accumulator,
                    len(ticker_named_traders[ticker]),
                )
                for ticker, accumulator in ticker_accumulators.items()
            ),
            key=lambda item: (-item.gross_notional, item.ticker),
        )
    )
    trader_activity = tuple(
        sorted(
            (
                TraderAnalytics(
                    trader_id=trader_id,
                    transaction_count=accumulator.transaction_count,
                    gross_share_volume=accumulator.gross_share_volume,
                    gross_notional=accumulator.gross_notional,
                    ticker_count=len(trader_tickers[trader_id]),
                )
                for trader_id, accumulator in trader_accumulators.items()
            ),
            key=lambda item: (-item.gross_notional, item.trader_id),
        )
    )
    hourly_activity = tuple(
        HourlyAnalytics(
            hour=hour,
            transaction_count=accumulator.transaction_count,
            gross_share_volume=accumulator.gross_share_volume,
            gross_notional=accumulator.gross_notional,
            net_traded_quantity=accumulator.net_traded_quantity,
        )
        for hour, accumulator in sorted(hour_accumulators.items())
    )

    timestamps = [transaction.timestamp for transaction in result.transactions]
    return PortfolioAnalytics(
        transaction_count=overall.transaction_count,
        ticker_count=len(ticker_accumulators),
        named_trader_count=len(trader_accumulators),
        period_start=min(timestamps) if timestamps else None,
        period_end=max(timestamps) if timestamps else None,
        gross_share_volume=overall.gross_share_volume,
        gross_notional=overall.gross_notional,
        buy_volume=overall.buy_volume,
        sell_volume=overall.sell_volume,
        buy_notional=overall.buy_notional,
        sell_notional=overall.sell_notional,
        net_traded_quantity=overall.net_traded_quantity,
        ticker_activity=ticker_activity,
        trader_activity=trader_activity,
        hourly_activity=hourly_activity,
        unknown_trader_transaction_count=unknown_trader.transaction_count,
        unknown_trader_volume=unknown_trader.gross_share_volume,
        unknown_trader_notional=unknown_trader.gross_notional,
        duplicates_quarantined=len(result.issues_with_code("exact_duplicate")),
        rejected_rows=result.rejected_row_count,
        missing_trader_warnings=len(result.issues_with_code("missing_trader_id")),
    )


def _build_ticker_analytics(
    ticker: str,
    accumulator: _Accumulator,
    named_trader_count: int,
) -> TickerAnalytics:
    return TickerAnalytics(
        ticker=ticker,
        transaction_count=accumulator.transaction_count,
        gross_share_volume=accumulator.gross_share_volume,
        gross_notional=accumulator.gross_notional,
        buy_volume=accumulator.buy_volume,
        sell_volume=accumulator.sell_volume,
        net_traded_quantity=accumulator.net_traded_quantity,
        buy_vwap=_vwap(accumulator.buy_notional, accumulator.buy_volume),
        sell_vwap=_vwap(accumulator.sell_notional, accumulator.sell_volume),
        named_trader_count=named_trader_count,
    )


def _vwap(notional: Decimal, quantity: int) -> Decimal | None:
    return None if quantity == 0 else notional / quantity


def latest_prices_by_ticker(
    transactions: Iterable[Transaction],
) -> dict[str, Decimal]:
    """Return each ticker's latest observed execution price.

    Source-row order resolves trades sharing the same timestamp, matching the
    repository's deterministic chronological ordering.
    """

    latest: dict[str, Transaction] = {}
    for transaction in transactions:
        current = latest.get(transaction.ticker)
        if current is None or (transaction.timestamp, transaction.source_row) > (
            current.timestamp,
            current.source_row,
        ):
            latest[transaction.ticker] = transaction
    return {ticker: latest[ticker].price for ticker in sorted(latest)}

