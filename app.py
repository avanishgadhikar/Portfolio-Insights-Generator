"""Streamlit dashboard for transaction analytics and grounded AI insights."""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, time
from decimal import Decimal
from io import StringIO
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from plotly.subplots import make_subplots


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from portfolio_insights.analytics import (
    PortfolioAnalytics,
    calculate_analytics,
    latest_prices_by_ticker,
)
from portfolio_insights.insights import (
    DEFAULT_MODEL,
    AnthropicInsightGenerator,
    GeneratedInsightReport,
    InsightConfigurationError,
    InsightGenerationError,
    InvalidInsightEvidenceError,
    build_analytics_snapshot,
    build_fallback_report,
    snapshot_hash,
)
from portfolio_insights.models import ProcessingResult, Transaction
from portfolio_insights.presentation import (
    canonical_transactions_csv,
    execution_activity_dataframe,
    format_notional,
    format_signed_shares,
    quality_issues_csv,
    quality_issues_dataframe,
    ticker_activity_dataframe,
    trader_activity_dataframe,
    trader_ticker_activity_dataframe,
    transactions_dataframe,
)
from portfolio_insights.processing import CSVSchemaError, load_transactions_csv
from portfolio_insights.repository import InMemoryTransactionRepository


st.set_page_config(
    page_title="Portfolio Insights Generator",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
load_dotenv()


INSTITUTIONAL_BLUE = "#183B56"
BUY_GREEN = "#2A9D8F"
SELL_CORAL = "#E76F51"
st.markdown(
    """
    <style>
    .block-container {padding-top: 1.6rem; padding-bottom: 2.5rem; max-width: 1500px;}
    [data-testid="stMetric"] {background: rgba(24, 59, 86, 0.055); border: 1px solid rgba(24, 59, 86, 0.12); padding: 0.85rem 1rem; border-radius: 0.7rem;}
    [data-testid="stMetricLabel"] {font-weight: 600;}
    .dashboard-kicker {color: #547083; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 0.15rem;}
    .dashboard-subtitle {color: #657786; margin-top: -0.45rem; margin-bottom: 1.3rem;}
    .status-ok {color: #16766b; font-weight: 650;}
    .status-warn {color: #a36312; font-weight: 650;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def process_csv_bytes(data: bytes) -> ProcessingResult:
    text = data.decode("utf-8-sig")
    return load_transactions_csv(StringIO(text))


def filtered_transactions(
    transactions: tuple[Transaction, ...],
    *,
    start_date: date,
    end_date: date,
    tickers: tuple[str, ...],
    action: str,
    include_unknown: bool,
) -> tuple[Transaction, ...]:
    start = datetime.combine(start_date, time.min)
    end = datetime.combine(end_date, time.max)
    ticker_set = set(tickers)
    return tuple(
        item
        for item in transactions
        if start <= item.timestamp <= end
        and item.ticker in ticker_set
        and (action == "All" or item.action.value == action.upper())
        and (include_unknown or item.trader_id is not None)
    )


def analytics_for_view(
    full_result: ProcessingResult,
    transactions: tuple[Transaction, ...],
) -> PortfolioAnalytics:
    filtered_result = ProcessingResult(
        raw_row_count=full_result.raw_row_count,
        transactions=transactions,
        issues=full_result.issues,
    )
    return calculate_analytics(filtered_result)


def plot_layout(fig, *, height: int = 380) -> None:
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=45, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", color="#29485c"),
        legend_title_text="",
    )
    fig.update_xaxes(gridcolor="rgba(84,112,131,0.13)")
    fig.update_yaxes(gridcolor="rgba(84,112,131,0.08)")


def execution_activity_figure(frame: pd.DataFrame, *, show_price: bool) -> go.Figure:
    """Build linked price and volume panels for a single security."""

    if show_price:
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.025,
            row_heights=[0.72, 0.28],
        )
        fig.add_scatter(
            x=frame["Time Bucket"],
            y=frame["Execution VWAP"],
            name="Execution VWAP",
            mode="lines+markers",
            line=dict(color=INSTITUTIONAL_BLUE, width=2.5),
            marker=dict(size=6),
            hovertemplate="%{x}<br>Execution VWAP: %{y:,.2f}<extra></extra>",
            row=1,
            col=1,
        )
        volume_row = 2
    else:
        fig = make_subplots(rows=1, cols=1)
        volume_row = 1

    fig.add_bar(
        x=frame["Time Bucket"],
        y=frame["Buy Volume"],
        name="Buy Volume",
        marker_color=BUY_GREEN,
        hovertemplate="%{x}<br>Buy volume: %{y:,}<extra></extra>",
        row=volume_row,
        col=1,
    )
    fig.add_bar(
        x=frame["Time Bucket"],
        y=frame["Sell Volume"],
        name="Sell Volume",
        marker_color=SELL_CORAL,
        hovertemplate="%{x}<br>Sell volume: %{y:,}<extra></extra>",
        row=volume_row,
        col=1,
    )
    if show_price:
        fig.update_yaxes(title_text="Execution Price", row=1, col=1)
        fig.update_yaxes(title_text="Volume", rangemode="tozero", row=2, col=1)
        fig.update_xaxes(showticklabels=False, row=1, col=1)
    else:
        fig.update_yaxes(title_text="Share Volume", row=1, col=1)
    fig.update_layout(barmode="group", hovermode="x unified")
    plot_layout(fig, height=500 if show_price else 380)
    return fig


def render_kpis(analytics: PortfolioAnalytics) -> None:
    values = (
        ("Accepted transactions", f"{analytics.transaction_count:,}"),
        ("Gross share volume", f"{analytics.gross_share_volume:,}"),
        ("Gross notional¹", format_notional(analytics.gross_notional)),
        ("Net traded quantity²", format_signed_shares(analytics.net_traded_quantity)),
        ("Distinct tickers", f"{analytics.ticker_count:,}"),
        ("Named traders", f"{analytics.named_trader_count:,}"),
    )
    for offset in range(0, len(values), 3):
        columns = st.columns(3)
        for column, (label, value) in zip(columns, values[offset : offset + 3]):
            column.metric(label, value)


def render_overview(
    analytics: PortfolioAnalytics,
    transactions: tuple[Transaction, ...],
) -> None:
    render_kpis(analytics)
    st.caption(
        "¹ Currency is unspecified in the source CSV.  ² Net traded quantity covers only the filtered uploaded period and is not a confirmed current position."
    )
    ticker_frame = ticker_activity_dataframe(analytics.ticker_activity)
    execution_frame = execution_activity_dataframe(transactions)

    if ticker_frame.empty:
        st.info("No accepted transactions match the current filters.")
        return

    left, right = st.columns((1.05, 0.95))
    with left:
        st.subheader("Activity by ticker")
        metric_label = st.selectbox(
            "Rank tickers by",
            ("Gross Notional", "Gross Volume", "Transactions"),
            label_visibility="collapsed",
            key="overview_ticker_metric",
        )
        ranked = ticker_frame.sort_values(metric_label, ascending=True)
        fig = px.bar(
            ranked,
            x=metric_label,
            y="Ticker",
            orientation="h",
            color_discrete_sequence=[INSTITUTIONAL_BLUE],
            hover_data=["Transactions", "Gross Volume", "Gross Notional", "Net Quantity"],
        )
        plot_layout(fig)
        st.plotly_chart(fig, width="stretch")

    with right:
        st.subheader("Buy and sell volume")
        volume_frame = ticker_frame.melt(
            id_vars="Ticker",
            value_vars=["Buy Volume", "Sell Volume"],
            var_name="Side",
            value_name="Share Volume",
        )
        fig = px.bar(
            volume_frame,
            x="Ticker",
            y="Share Volume",
            color="Side",
            barmode="group",
            color_discrete_map={"Buy Volume": BUY_GREEN, "Sell Volume": SELL_CORAL},
        )
        plot_layout(fig)
        st.plotly_chart(fig, width="stretch")

    st.subheader("Hourly buy and sell activity")
    if execution_frame.empty:
        st.info("No hourly activity is available for the current filters.")
    else:
        show_price = analytics.ticker_count == 1
        fig = execution_activity_figure(execution_frame, show_price=show_price)
        st.plotly_chart(fig, width="stretch")
        if not show_price:
            st.caption(
                "The price overlay appears when the filtered view contains one ticker; averaging prices across securities would be misleading."
            )
        st.caption("Source timestamp timezone is unspecified.")

    left, right = st.columns(2)
    with left:
        st.subheader("Leading tickers")
        st.dataframe(
            ticker_frame.head(5)[
                ["Ticker", "Transactions", "Gross Volume", "Gross Notional", "Net Quantity"]
            ],
            hide_index=True,
            width="stretch",
            column_config={"Gross Notional": st.column_config.NumberColumn(format="%.2f")},
        )
    with right:
        st.subheader("Leading named traders")
        trader_frame = trader_activity_dataframe(analytics.trader_activity)
        if trader_frame.empty:
            st.info("No named traders match the current filters.")
        else:
            st.dataframe(
                trader_frame.head(5),
                hide_index=True,
                width="stretch",
                column_config={"Gross Notional": st.column_config.NumberColumn(format="%.2f")},
            )


def render_ticker_explorer(
    analytics: PortfolioAnalytics,
    repository: InMemoryTransactionRepository,
) -> None:
    tickers = repository.get_tickers()
    if not tickers:
        st.info("No ticker activity matches the current filters.")
        return

    selected = st.selectbox("Select a ticker", tickers, key="ticker_explorer_selection")
    ticker_lookup = {item.ticker: item for item in analytics.ticker_activity}
    selected_analytics = ticker_lookup[selected]
    selected_transactions = repository.get_by_ticker(selected)

    values = (
        ("Transactions", f"{selected_analytics.transaction_count:,}"),
        ("Gross volume", f"{selected_analytics.gross_share_volume:,}"),
        ("Gross notional¹", format_notional(selected_analytics.gross_notional)),
        ("Net quantity²", format_signed_shares(selected_analytics.net_traded_quantity)),
        ("Buy VWAP", "—" if selected_analytics.buy_vwap is None else format_notional(selected_analytics.buy_vwap)),
        ("Sell VWAP", "—" if selected_analytics.sell_vwap is None else format_notional(selected_analytics.sell_vwap)),
    )
    for offset in range(0, len(values), 3):
        columns = st.columns(3)
        for column, (label, value) in zip(columns, values[offset : offset + 3]):
            column.metric(label, value)

    st.subheader("Hourly execution activity and price")
    execution_frame = execution_activity_dataframe(selected_transactions)
    fig = execution_activity_figure(execution_frame, show_price=True)
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Price is the quantity-weighted average execution price within each hour. Source currency and timestamp timezone are unspecified."
    )

    st.subheader("Chronological transactions")
    st.dataframe(
        transactions_dataframe(selected_transactions),
        hide_index=True,
        width="stretch",
        column_config={
            "Price": st.column_config.NumberColumn(format="%.2f"),
            "Notional": st.column_config.NumberColumn(format="%.2f"),
        },
    )


def render_trader_activity(
    analytics: PortfolioAnalytics,
    transactions: tuple[Transaction, ...],
    latest_prices: dict[str, Decimal],
) -> None:
    top, unknown = st.columns((2.2, 1))
    with top:
        st.subheader("Named-trader leaderboard")
    with unknown:
        st.metric("Unknown-trader volume", f"{analytics.unknown_trader_volume:,}")

    frame = trader_activity_dataframe(analytics.trader_activity)
    if frame.empty:
        st.info("No named traders match the current filters.")
    else:
        ranking = st.selectbox(
            "Rank traders by",
            ("Gross Notional", "Gross Volume", "Transactions", "Distinct Tickers"),
            key="trader_ranking_metric",
        )
        ranked = frame.sort_values(ranking, ascending=False)
        left, right = st.columns((1.1, 0.9))
        with left:
            fig = px.bar(
                ranked.head(15).sort_values(ranking),
                x=ranking,
                y="Trader ID",
                orientation="h",
                color_discrete_sequence=[INSTITUTIONAL_BLUE],
            )
            plot_layout(fig, height=430)
            st.plotly_chart(fig, width="stretch")
        with right:
            st.dataframe(
                ranked,
                hide_index=True,
                width="stretch",
                column_config={"Gross Notional": st.column_config.NumberColumn(format="%.2f")},
            )

        selected = st.selectbox("Inspect a named trader", tuple(ranked["Trader ID"]))
        trader_transactions = tuple(item for item in transactions if item.trader_id == selected)
        ticker_flow = trader_ticker_activity_dataframe(trader_transactions, latest_prices)

        signed_marked_value = ticker_flow["Marked Net Flow Value"].sum()
        gross_marked_value = ticker_flow["Marked Net Flow Value"].abs().sum()
        marked_left, marked_right = st.columns(2)
        marked_left.metric("Signed marked net flow value¹", format_notional(signed_marked_value))
        marked_right.metric("Gross marked net flow value¹", format_notional(gross_marked_value))

        st.subheader("Marked net traded value by ticker")
        ticker_flow_chart = ticker_flow.copy()
        ticker_flow_chart["Flow"] = ticker_flow_chart["Marked Net Flow Value"].map(
            lambda value: "Net bought" if value > 0 else "Net sold" if value < 0 else "Flat"
        )
        fig = px.bar(
            ticker_flow_chart.sort_values("Marked Net Flow Value"),
            x="Marked Net Flow Value",
            y="Ticker",
            orientation="h",
            color="Flow",
            color_discrete_map={
                "Net bought": BUY_GREEN,
                "Net sold": SELL_CORAL,
                "Flat": "#8da0ad",
            },
            hover_data=["Buy Volume", "Sell Volume", "Gross Volume", "Gross Notional"],
        )
        fig.add_vline(x=0, line_color="#8da0ad", line_width=1)
        plot_layout(fig, height=380)
        st.plotly_chart(fig, width="stretch")
        st.caption(
            "¹ Each ticker's net traded quantity is marked using its latest accepted execution price in the selected date/ticker universe. Currency is unspecified; this is filtered transaction flow, not a confirmed holding or live market value."
        )
        st.dataframe(
            ticker_flow,
            hide_index=True,
            width="stretch",
            column_config={
                "Gross Notional": st.column_config.NumberColumn(format="%.2f"),
                "Latest Observed Price": st.column_config.NumberColumn(format="%.2f"),
                "Marked Net Flow Value": st.column_config.NumberColumn(format="%.2f"),
            },
        )

        st.subheader("Chronological transactions")
        st.dataframe(
            transactions_dataframe(trader_transactions),
            hide_index=True,
            width="stretch",
            column_config={
                "Price": st.column_config.NumberColumn(format="%.2f"),
                "Notional": st.column_config.NumberColumn(format="%.2f"),
            },
        )

    with st.expander("Unknown-trader activity"):
        unknown_transactions = tuple(item for item in transactions if item.trader_id is None)
        st.write(
            f"{analytics.unknown_trader_transaction_count:,} accepted transactions, "
            f"{analytics.unknown_trader_volume:,} shares, and "
            f"{format_notional(analytics.unknown_trader_notional)} in unspecified-currency notional."
        )
        if unknown_transactions:
            st.dataframe(
                transactions_dataframe(unknown_transactions),
                hide_index=True,
                width="stretch",
            )


def render_data_quality(result: ProcessingResult) -> None:
    columns = st.columns(5)
    values = (
        ("Raw rows", result.raw_row_count),
        ("Accepted rows", result.accepted_row_count),
        ("Quarantined", result.quarantined_row_count),
        ("Rejected", result.rejected_row_count),
        ("Warnings", result.warning_count),
    )
    for column, (label, value) in zip(columns, values):
        column.metric(label, f"{value:,}")

    issue_frame = quality_issues_dataframe(result.issues)
    if issue_frame.empty:
        st.success("No data-quality findings were recorded.")
    else:
        st.subheader("Traceable findings")
        choices = ("All", *sorted(issue_frame["Disposition"].unique()))
        selected = st.selectbox("Disposition", choices, key="quality_disposition")
        shown = issue_frame if selected == "All" else issue_frame[issue_frame["Disposition"] == selected]
        st.dataframe(shown, hide_index=True, width="stretch")

    with st.expander("Cleaning policy and assumptions"):
        st.markdown(
            """
            - Original field values and CSV source rows are preserved.
            - Tickers and actions are normalized to uppercase after trimming whitespace.
            - Timestamps are parsed strictly and remain timezone-unspecified.
            - Quantities must be positive integers; prices use decimal arithmetic.
            - Exact duplicate raw rows are quarantined, not silently deleted.
            - Missing trader IDs remain null and appear as `UNKNOWN` only in presentation.
            - Timestamp ties use source-row order for deterministic retrieval.
            """
        )

    left, right = st.columns(2)
    left.download_button(
        "Download cleaned transactions",
        canonical_transactions_csv(result.transactions),
        file_name="cleaned_transactions.csv",
        mime="text/csv",
        width="stretch",
    )
    right.download_button(
        "Download quality findings",
        quality_issues_csv(result.issues),
        file_name="data_quality_findings.csv",
        mime="text/csv",
        width="stretch",
    )


def render_insight_report(report, snapshot, *, fallback: bool) -> None:
    if fallback:
        st.warning("Displaying deterministic fallback commentary; this report was not generated by Claude.")
    st.subheader("Executive summary")
    st.write(report.executive_summary)

    for insight in report.insights:
        with st.container(border=True):
            st.markdown(f"#### {insight.title}")
            st.caption(f"{insight.category.value.replace('_', ' ').title()} · {insight.importance.value.title()} importance")
            st.write(insight.explanation)
            st.markdown("**Evidence**")
            for metric_id in insight.evidence_metric_ids:
                metric = snapshot.metrics[metric_id]
                st.markdown(f"- {metric.label}: `{metric.display_value}`")

    if report.caveats:
        with st.expander("Caveats", expanded=True):
            for caveat in report.caveats:
                st.markdown(f"- {caveat}")


def render_ai_insights(analytics: PortfolioAnalytics) -> None:
    snapshot = build_analytics_snapshot(analytics)
    model = os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
    key_configured = bool(os.getenv("ANTHROPIC_API_KEY"))
    current_hash = snapshot_hash(snapshot, model)

    left, middle, right = st.columns(3)
    left.metric("Configured model", model)
    middle.metric("Grounded metrics", f"{len(snapshot.metrics):,}")
    right.metric("API status", "Configured" if key_configured else "Not configured")
    st.caption("Claude receives aggregated metrics only. It does not receive the raw transaction CSV.")

    if st.button("Generate AI Insights", type="primary", width="stretch"):
        cached_hash = st.session_state.get("insight_snapshot_hash")
        if cached_hash != current_hash:
            st.session_state.pop("insight_report", None)
            st.session_state.pop("insight_metadata", None)
            st.session_state.pop("insight_is_fallback", None)

        if "insight_report" not in st.session_state:
            if not key_configured:
                st.session_state.insight_report = build_fallback_report(snapshot)
                st.session_state.insight_is_fallback = True
                st.session_state.insight_metadata = None
            else:
                try:
                    with st.spinner("Generating grounded commentary with Anthropic…"):
                        generated = AnthropicInsightGenerator(model=model).generate(snapshot)
                    st.session_state.insight_report = generated.report
                    st.session_state.insight_is_fallback = False
                    st.session_state.insight_metadata = generated
                except (
                    InsightConfigurationError,
                    InsightGenerationError,
                    InvalidInsightEvidenceError,
                ) as exc:
                    st.error(str(exc))
                    st.session_state.insight_report = build_fallback_report(snapshot)
                    st.session_state.insight_is_fallback = True
                    st.session_state.insight_metadata = None
            st.session_state.insight_snapshot_hash = current_hash

    if st.session_state.get("insight_snapshot_hash") == current_hash:
        report = st.session_state.get("insight_report")
        if report is not None:
            render_insight_report(
                report,
                snapshot,
                fallback=bool(st.session_state.get("insight_is_fallback")),
            )
            metadata: GeneratedInsightReport | None = st.session_state.get("insight_metadata")
            if metadata is not None:
                with st.expander("Generation metadata"):
                    st.json(
                        {
                            "model": metadata.model,
                            "generated_at": metadata.generated_at.isoformat(),
                            "request_id": metadata.request_id,
                            "input_tokens": metadata.input_tokens,
                            "output_tokens": metadata.output_tokens,
                            "prompt_version": metadata.prompt_version,
                            "snapshot_hash": metadata.snapshot_hash[:16],
                        }
                    )
    else:
        st.info("Generate a report for the current filtered view. One Anthropic request will be made.")

    st.caption("AI-generated analysis is descriptive, not investment advice.")


st.markdown('<div class="dashboard-kicker">Transaction intelligence</div>', unsafe_allow_html=True)
st.title("Portfolio Insights Generator")
st.markdown(
    '<div class="dashboard-subtitle">Auditable transaction analytics with grounded Anthropic commentary.</div>',
    unsafe_allow_html=True,
)


with st.sidebar:
    st.header("Dataset")
    source_mode = st.radio("Data source", ("Bundled sample", "Upload CSV"), horizontal=True)
    if source_mode == "Upload CSV":
        uploaded = st.file_uploader("Transaction CSV", type=("csv",))
        if uploaded is None:
            st.info("Upload a CSV to begin.")
            st.stop()
        source_name = uploaded.name
        source_bytes = uploaded.getvalue()
    else:
        source_name = "sample_transactions.csv"
        source_bytes = (ROOT / source_name).read_bytes()

    try:
        full_result = process_csv_bytes(source_bytes)
    except UnicodeDecodeError:
        st.error("The CSV must use UTF-8 encoding.")
        st.stop()
    except CSVSchemaError as exc:
        st.error(str(exc))
        st.stop()
    except Exception as exc:
        st.error(f"The CSV could not be processed: {exc}")
        st.stop()

    full_analytics = calculate_analytics(full_result)
    st.caption(source_name)
    st.write(f"**{full_result.accepted_row_count:,}** accepted of **{full_result.raw_row_count:,}** rows")

    st.divider()
    st.header("View filters")
    if full_analytics.period_start is None or full_analytics.period_end is None:
        st.warning("No valid transactions are available.")
        st.stop()

    selected_dates = st.date_input(
        "Date range",
        value=(full_analytics.period_start.date(), full_analytics.period_end.date()),
        min_value=full_analytics.period_start.date(),
        max_value=full_analytics.period_end.date(),
    )
    if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
        start_date, end_date = selected_dates
    else:
        start_date = end_date = selected_dates[0] if isinstance(selected_dates, tuple) else selected_dates

    all_tickers = tuple(item.ticker for item in full_analytics.ticker_activity)
    selected_tickers = tuple(st.multiselect("Tickers", all_tickers, default=all_tickers))
    selected_action = st.radio("Action", ("All", "Buy", "Sell"), horizontal=True)
    include_unknown = st.toggle("Include unknown traders", value=True)

    st.divider()
    if os.getenv("ANTHROPIC_API_KEY"):
        st.markdown('<span class="status-ok">● Anthropic API configured</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-warn">● Anthropic API not configured</span>', unsafe_allow_html=True)


view_transactions = filtered_transactions(
    full_result.transactions,
    start_date=start_date,
    end_date=end_date,
    tickers=selected_tickers,
    action=selected_action,
    include_unknown=include_unknown,
)
valuation_transactions = filtered_transactions(
    full_result.transactions,
    start_date=start_date,
    end_date=end_date,
    tickers=selected_tickers,
    action="All",
    include_unknown=True,
)
view_analytics = analytics_for_view(full_result, view_transactions)
repository = InMemoryTransactionRepository(view_transactions)
latest_prices = latest_prices_by_ticker(valuation_transactions)


overview_tab, ticker_tab, trader_tab, quality_tab, insights_tab = st.tabs(
    ("Overview", "Ticker Explorer", "Trader Activity", "Data Quality", "AI Insights")
)
with overview_tab:
    render_overview(view_analytics, view_transactions)
with ticker_tab:
    render_ticker_explorer(view_analytics, repository)
with trader_tab:
    render_trader_activity(view_analytics, view_transactions, latest_prices)
with quality_tab:
    render_data_quality(full_result)
with insights_tab:
    render_ai_insights(view_analytics)

