from __future__ import annotations

from io import StringIO
from types import SimpleNamespace

import pytest

from portfolio_insights.analytics import calculate_analytics
from portfolio_insights.insight_models import (
    Insight,
    InsightCategory,
    InsightImportance,
    InsightReport,
)
from portfolio_insights.insights import (
    AnthropicInsightGenerator,
    InsightConfigurationError,
    InvalidInsightEvidenceError,
    build_analytics_snapshot,
    build_fallback_report,
    build_prompt,
    snapshot_hash,
    validate_insight_evidence,
)
from portfolio_insights.processing import load_transactions_csv


HEADER = "timestamp,ticker,action,quantity,price,trader_id\n"
ROWS = """2024-01-15 10:05:00,AAPL,BUY,10,100.00,T001
2024-01-15 10:20:00,AAPL,SELL,4,110.00,T002
2024-01-15 11:00:00,MSFT,BUY,5,200.00,
"""


def _snapshot():
    result = load_transactions_csv(StringIO(HEADER + ROWS))
    return build_analytics_snapshot(calculate_analytics(result))


def _report(evidence_id: str = "overview.gross_share_volume") -> InsightReport:
    return InsightReport(
        executive_summary="Activity was concentrated in the supplied period.",
        insights=[
            Insight(
                title="Activity",
                category=InsightCategory.MARKET_ACTIVITY,
                importance=InsightImportance.MEDIUM,
                explanation="The dataset contains recorded share volume.",
                evidence_metric_ids=[evidence_id],
            ),
            Insight(
                title="Ticker leadership",
                category=InsightCategory.TICKER_ACTIVITY,
                importance=InsightImportance.MEDIUM,
                explanation="One ticker led gross notional activity.",
                evidence_metric_ids=["ticker.rank_1.symbol"],
            ),
            Insight(
                title="Quality",
                category=InsightCategory.DATA_QUALITY,
                importance=InsightImportance.HIGH,
                explanation="Missing trader IDs remain visible.",
                evidence_metric_ids=["quality.missing_trader_warnings"],
            ),
        ],
        caveats=["Net quantity is not a confirmed current position."],
    )


def test_snapshot_contains_grounded_metrics_without_raw_transactions() -> None:
    snapshot = _snapshot()

    assert snapshot.metrics["overview.gross_share_volume"].raw_value == "19"
    assert snapshot.rankings["tickers_by_gross_notional"] == ["AAPL", "MSFT"]
    serialized = snapshot.model_dump_json()
    assert "raw_row" not in serialized
    assert "2024-01-15 10:05:00,AAPL" not in serialized


def test_prompt_contains_constraints_and_snapshot() -> None:
    prompt = build_prompt(_snapshot())

    assert "three to five" in prompt
    assert "analytics_snapshot" in prompt
    assert "overview.gross_share_volume" in prompt


def test_evidence_validation_rejects_unknown_metric() -> None:
    with pytest.raises(InvalidInsightEvidenceError, match="unknown metrics"):
        validate_insight_evidence(_report("invented.metric"), _snapshot())


def test_cache_hash_is_stable_and_model_specific() -> None:
    snapshot = _snapshot()

    assert snapshot_hash(snapshot, "model-a") == snapshot_hash(snapshot, "model-a")
    assert snapshot_hash(snapshot, "model-a") != snapshot_hash(snapshot, "model-b")


def test_generator_uses_structured_output_and_returns_metadata() -> None:
    report = _report()

    class FakeMessages:
        def parse(self, **kwargs):
            assert kwargs["output_format"] is InsightReport
            assert kwargs["max_tokens"] == 7_500
            return SimpleNamespace(
                parsed_output=report,
                _request_id="req_test",
                usage=SimpleNamespace(input_tokens=100, output_tokens=50),
            )

    client = SimpleNamespace(messages=FakeMessages())
    generated = AnthropicInsightGenerator(client=client, model="test-model").generate(
        _snapshot()
    )

    assert generated.report == report
    assert generated.model == "test-model"
    assert generated.request_id == "req_test"
    assert generated.input_tokens == 100
    assert generated.output_tokens == 50


def test_missing_api_key_fails_without_network_call(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("portfolio_insights.insights.load_dotenv", lambda: False)

    with pytest.raises(InsightConfigurationError, match="ANTHROPIC_API_KEY"):
        AnthropicInsightGenerator()


def test_fallback_report_is_grounded() -> None:
    snapshot = _snapshot()
    report = build_fallback_report(snapshot)

    validate_insight_evidence(report, snapshot)
    assert len(report.insights) == 3

