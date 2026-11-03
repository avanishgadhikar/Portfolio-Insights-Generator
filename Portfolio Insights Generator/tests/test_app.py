from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_dashboard_loads_sample_without_api_call() -> None:
    app_path = Path(__file__).parents[1] / "app.py"

    app = AppTest.from_file(str(app_path), default_timeout=20).run()

    assert not app.exception
    assert app.title[0].value == "Portfolio Insights Generator"
    assert len(app.tabs) == 5
    assert [tab.label for tab in app.tabs] == [
        "Overview",
        "Ticker Explorer",
        "Trader Activity",
        "Data Quality",
        "AI Insights",
    ]
    metric_values = [metric.value for metric in app.metric]
    assert "1,000" in metric_values
    assert "108,690" in metric_values

