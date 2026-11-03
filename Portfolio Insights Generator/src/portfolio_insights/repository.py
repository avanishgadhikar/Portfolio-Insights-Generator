"""In-memory storage with efficient ticker and time-range retrieval."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from portfolio_insights.models import Transaction


class TransactionRepository(Protocol):
    """Storage contract consumed by analytics and presentation layers."""

    def get_by_ticker(
        self,
        ticker: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> Sequence[Transaction]: ...

    def get_all_chronological(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> Sequence[Transaction]: ...

    def get_tickers(self) -> Sequence[str]: ...


@dataclass(frozen=True, slots=True)
class _TimeOrderedBucket:
    transactions: tuple[Transaction, ...]
    timestamps: tuple[datetime, ...]

    @classmethod
    def from_transactions(
        cls, transactions: Iterable[Transaction]
    ) -> _TimeOrderedBucket:
        ordered = tuple(
            sorted(transactions, key=lambda item: (item.timestamp, item.source_row))
        )
        return cls(
            transactions=ordered,
            timestamps=tuple(item.timestamp for item in ordered),
        )

    def between(
        self,
        start: datetime | None,
        end: datetime | None,
    ) -> tuple[Transaction, ...]:
        _validate_range(start, end)
        left = 0 if start is None else bisect_left(self.timestamps, start)
        right = len(self.transactions) if end is None else bisect_right(self.timestamps, end)
        return self.transactions[left:right]


class InMemoryTransactionRepository:
    """Immutable read repository indexed by normalized ticker.

    Data is sorted once at construction. Ticker bucket lookup is approximately
    O(1), and date boundaries are located with binary search.
    """

    def __init__(self, transactions: Iterable[Transaction]) -> None:
        all_bucket = _TimeOrderedBucket.from_transactions(transactions)
        grouped: defaultdict[str, list[Transaction]] = defaultdict(list)
        for transaction in all_bucket.transactions:
            grouped[transaction.ticker].append(transaction)

        self._all = all_bucket
        self._by_ticker = {
            ticker: _TimeOrderedBucket.from_transactions(items)
            for ticker, items in grouped.items()
        }
        self._tickers = tuple(sorted(self._by_ticker))

    def __len__(self) -> int:
        return len(self._all.transactions)

    def get_by_ticker(
        self,
        ticker: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[Transaction, ...]:
        normalized = ticker.strip().upper()
        bucket = self._by_ticker.get(normalized)
        if bucket is None:
            _validate_range(start, end)
            return ()
        return bucket.between(start, end)

    def get_all_chronological(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[Transaction, ...]:
        return self._all.between(start, end)

    def get_tickers(self) -> tuple[str, ...]:
        return self._tickers


def _validate_range(start: datetime | None, end: datetime | None) -> None:
    for boundary in (start, end):
        if boundary is not None and boundary.tzinfo is not None:
            raise ValueError("Date range boundaries must be timezone-naive.")
    if start is not None and end is not None and start > end:
        raise ValueError("Start timestamp must not be after end timestamp.")

