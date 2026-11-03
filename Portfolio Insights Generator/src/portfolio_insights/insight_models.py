"""Validated request and response models for the Anthropic boundary."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalysisPeriod(StrictModel):
    start: str | None
    end: str | None
    timezone: str


class SnapshotMetric(StrictModel):
    label: str
    raw_value: str
    display_value: str
    unit: str


class AnalyticsSnapshot(StrictModel):
    analysis_period: AnalysisPeriod
    metrics: dict[str, SnapshotMetric]
    rankings: dict[str, list[str]]
    notes: list[str]


class InsightCategory(StrEnum):
    MARKET_ACTIVITY = "market_activity"
    TICKER_ACTIVITY = "ticker_activity"
    TRADER_ACTIVITY = "trader_activity"
    ORDER_FLOW = "order_flow"
    TIME_PATTERN = "time_pattern"
    DATA_QUALITY = "data_quality"


class InsightImportance(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Insight(StrictModel):
    title: str
    category: InsightCategory
    importance: InsightImportance
    explanation: str
    evidence_metric_ids: list[str] = Field(min_length=1)


class InsightReport(StrictModel):
    executive_summary: str
    insights: list[Insight] = Field(min_length=3, max_length=5)
    caveats: list[str]

