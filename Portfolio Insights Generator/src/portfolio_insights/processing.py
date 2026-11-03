"""CSV ingestion, validation, normalization, and data-quality reporting."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TextIO

from portfolio_insights.models import (
    DataQualityIssue,
    IssueDisposition,
    ProcessingResult,
    RawTransactionRow,
    TradeAction,
    Transaction,
)


REQUIRED_COLUMNS = (
    "timestamp",
    "ticker",
    "action",
    "quantity",
    "price",
    "trader_id",
)
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


class CSVSchemaError(ValueError):
    """Raised when the CSV header cannot represent a transaction row."""


@dataclass(frozen=True, slots=True)
class CleaningPolicy:
    """Explicit, reviewable choices applied during ingestion."""

    quarantine_exact_duplicates: bool = True


CSVSource = str | Path | TextIO


def load_transactions_csv(
    source: CSVSource,
    policy: CleaningPolicy | None = None,
) -> ProcessingResult:
    """Load and validate transactions from a file path or text stream.

    Invalid rows are rejected, exact duplicate raw rows are quarantined, and
    missing trader IDs are retained as ``None`` with a warning. Accepted
    transactions are returned in stable chronological order.
    """

    active_policy = policy or CleaningPolicy()
    with _open_source(source) as stream:
        reader = csv.DictReader(stream)
        _validate_header(reader.fieldnames)
        return _process_rows(reader, active_policy)


def _process_rows(
    rows: Iterator[dict[str, str | None]],
    policy: CleaningPolicy,
) -> ProcessingResult:
    transactions: list[Transaction] = []
    issues: list[DataQualityIssue] = []
    first_source_row_by_raw_values: dict[tuple[str, ...], int] = {}
    raw_row_count = 0

    for source_row, row in enumerate(rows, start=2):
        raw_row_count += 1
        raw_row = _to_raw_row(row)
        row_issues, parsed = _parse_row(source_row, raw_row)

        if row_issues:
            issues.extend(row_issues)
            continue

        assert parsed is not None
        duplicate_of = first_source_row_by_raw_values.get(raw_row.values())
        if policy.quarantine_exact_duplicates and duplicate_of is not None:
            issues.append(
                DataQualityIssue(
                    source_row=source_row,
                    code="exact_duplicate",
                    message=f"Exact duplicate of source row {duplicate_of}.",
                    disposition=IssueDisposition.QUARANTINED,
                    raw_row=raw_row,
                    related_source_row=duplicate_of,
                )
            )
            continue

        first_source_row_by_raw_values.setdefault(raw_row.values(), source_row)
        transactions.append(parsed)
        if parsed.trader_id is None:
            issues.append(
                DataQualityIssue(
                    source_row=source_row,
                    code="missing_trader_id",
                    message="Trader ID is missing; the transaction was retained.",
                    disposition=IssueDisposition.WARNING,
                    raw_row=raw_row,
                )
            )

    transactions.sort(key=lambda transaction: (transaction.timestamp, transaction.source_row))
    return ProcessingResult(
        raw_row_count=raw_row_count,
        transactions=tuple(transactions),
        issues=tuple(issues),
    )


def _parse_row(
    source_row: int,
    raw_row: RawTransactionRow,
) -> tuple[list[DataQualityIssue], Transaction | None]:
    issues: list[DataQualityIssue] = []
    timestamp_text = raw_row.timestamp.strip()
    ticker = raw_row.ticker.strip().upper()
    action_text = raw_row.action.strip().upper()
    quantity_text = raw_row.quantity.strip()
    price_text = raw_row.price.strip()
    trader_text = raw_row.trader_id.strip()

    timestamp = _parse_timestamp(timestamp_text)
    if timestamp is None:
        issues.append(
            _rejected(
                source_row,
                "invalid_timestamp",
                f"Timestamp must match {TIMESTAMP_FORMAT!r}.",
                raw_row,
            )
        )

    if not ticker:
        issues.append(
            _rejected(source_row, "missing_ticker", "Ticker is required.", raw_row)
        )

    try:
        action = TradeAction(action_text)
    except ValueError:
        action = None
        issues.append(
            _rejected(
                source_row,
                "invalid_action",
                "Action must be BUY or SELL.",
                raw_row,
            )
        )

    quantity = _parse_positive_integer(quantity_text)
    if quantity is None:
        issues.append(
            _rejected(
                source_row,
                "invalid_quantity",
                "Quantity must be a positive integer.",
                raw_row,
            )
        )

    price = _parse_positive_decimal(price_text)
    if price is None:
        issues.append(
            _rejected(
                source_row,
                "invalid_price",
                "Price must be a positive finite decimal.",
                raw_row,
            )
        )

    if issues:
        return issues, None

    assert timestamp is not None
    assert action is not None
    assert quantity is not None
    assert price is not None
    return [], Transaction(
        source_row=source_row,
        timestamp=timestamp,
        ticker=ticker,
        action=action,
        quantity=quantity,
        price=price,
        trader_id=trader_text or None,
        raw_row=raw_row,
    )


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.strptime(value, TIMESTAMP_FORMAT)
    except ValueError:
        return None
    return parsed if parsed.strftime(TIMESTAMP_FORMAT) == value else None


def _parse_positive_integer(value: str) -> int | None:
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 and str(parsed) == value else None


def _parse_positive_decimal(value: str) -> Decimal | None:
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() and parsed > 0 else None


def _to_raw_row(row: dict[str, str | None]) -> RawTransactionRow:
    return RawTransactionRow(
        timestamp=row.get("timestamp") or "",
        ticker=row.get("ticker") or "",
        action=row.get("action") or "",
        quantity=row.get("quantity") or "",
        price=row.get("price") or "",
        trader_id=row.get("trader_id") or "",
    )


def _rejected(
    source_row: int,
    code: str,
    message: str,
    raw_row: RawTransactionRow,
) -> DataQualityIssue:
    return DataQualityIssue(
        source_row=source_row,
        code=code,
        message=message,
        disposition=IssueDisposition.REJECTED,
        raw_row=raw_row,
    )


def _validate_header(fieldnames: list[str] | None) -> None:
    if fieldnames is None:
        raise CSVSchemaError("CSV is empty or does not contain a header row.")
    missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
    if missing:
        raise CSVSchemaError(f"CSV is missing required columns: {', '.join(missing)}")


@contextmanager
def _open_source(source: CSVSource) -> Iterator[TextIO]:
    if hasattr(source, "read"):
        yield source  # type: ignore[misc]
        return

    with Path(source).open(mode="r", encoding="utf-8-sig", newline="") as stream:
        yield stream

