"""Domain models shared by transaction processing and storage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class TradeAction(StrEnum):
    """Supported transaction directions."""

    BUY = "BUY"
    SELL = "SELL"


class IssueDisposition(StrEnum):
    """How a data-quality issue affects the corresponding input row."""

    WARNING = "warning"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class RawTransactionRow:
    """An immutable copy of a CSV row before normalization."""

    timestamp: str
    ticker: str
    action: str
    quantity: str
    price: str
    trader_id: str

    def values(self) -> tuple[str, str, str, str, str, str]:
        """Return values in the source CSV's canonical column order."""

        return (
            self.timestamp,
            self.ticker,
            self.action,
            self.quantity,
            self.price,
            self.trader_id,
        )

    def as_dict(self) -> dict[str, str]:
        """Return a mutable display/export representation."""

        return {
            "timestamp": self.timestamp,
            "ticker": self.ticker,
            "action": self.action,
            "quantity": self.quantity,
            "price": self.price,
            "trader_id": self.trader_id,
        }


@dataclass(frozen=True, slots=True)
class Transaction:
    """A validated, normalized transaction.

    Timestamps intentionally remain timezone-naive because the source file does
    not identify a timezone. ``source_row`` is the one-based CSV line number,
    including the header, and provides deterministic ordering for timestamp ties.
    """

    source_row: int
    timestamp: datetime
    ticker: str
    action: TradeAction
    quantity: int
    price: Decimal
    trader_id: str | None
    raw_row: RawTransactionRow

    @property
    def signed_quantity(self) -> int:
        """Return positive buy quantity or negative sell quantity."""

        return self.quantity if self.action is TradeAction.BUY else -self.quantity

    @property
    def notional(self) -> Decimal:
        """Return the unsigned traded notional for this transaction."""

        return self.price * self.quantity


@dataclass(frozen=True, slots=True)
class DataQualityIssue:
    """A traceable validation, warning, or quarantine finding."""

    source_row: int
    code: str
    message: str
    disposition: IssueDisposition
    raw_row: RawTransactionRow
    related_source_row: int | None = None


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    """The complete result of processing one CSV import."""

    raw_row_count: int
    transactions: tuple[Transaction, ...]
    issues: tuple[DataQualityIssue, ...]

    @property
    def accepted_row_count(self) -> int:
        return len(self.transactions)

    @property
    def quarantined_row_count(self) -> int:
        return len(
            {
                issue.source_row
                for issue in self.issues
                if issue.disposition is IssueDisposition.QUARANTINED
            }
        )

    @property
    def rejected_row_count(self) -> int:
        return len(
            {
                issue.source_row
                for issue in self.issues
                if issue.disposition is IssueDisposition.REJECTED
            }
        )

    @property
    def warning_count(self) -> int:
        return sum(
            issue.disposition is IssueDisposition.WARNING for issue in self.issues
        )

    def issues_with_code(self, code: str) -> tuple[DataQualityIssue, ...]:
        """Return all findings matching a stable machine-readable code."""

        return tuple(issue for issue in self.issues if issue.code == code)

