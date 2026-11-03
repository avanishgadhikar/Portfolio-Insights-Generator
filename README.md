# Portfolio Insights Generator

This take-home project processes a transaction CSV into a validated, auditable
dataset, calculates deterministic analytics, and uses Anthropic to turn those
verified facts into structured natural-language commentary.

## Current scope

- Strict CSV schema and value validation
- Immutable normalized transaction models
- Raw-row and source-line traceability
- Exact-duplicate quarantine
- Missing-trader warnings without dropping valid trades
- Stable chronological ordering
- Efficient ticker and inclusive date-range retrieval
- Deterministic market, ticker, trader, and hourly analytics
- Compact metric catalog for grounded LLM input
- Anthropic Structured Outputs with evidence-ID validation
- Deterministic insight fallback when API-backed commentary is unavailable
- Interactive Streamlit dashboard with ticker, trader, quality, and AI views

## Data-cleaning decisions

1. Original field values and the one-based CSV source line are preserved.
2. Whitespace is trimmed from normalized values; ticker and action are uppercase.
3. Timestamps must match `YYYY-MM-DD HH:MM:SS`. They remain timezone-naive
   because the source does not identify a timezone.
4. Quantity must be a positive integer.
5. Price must be a positive, finite `Decimal`.
6. Exact duplicate raw rows are excluded from the canonical analytical dataset
   and retained as quarantined data-quality findings. The first row is retained.
7. Missing trader IDs become `None` and produce warnings; the trades remain valid.
   A later presentation layer may display these records as `UNKNOWN`.
8. Timestamp ties are ordered by source row.

The supplied sample has 1,030 rows. Processing produces 1,000 canonical
transactions, 30 quarantined exact duplicates, and 50 missing-trader warnings.

## Storage design

`InMemoryTransactionRepository` stores one globally time-ordered tuple and a
dictionary of ticker-specific time-ordered buckets. Ticker lookup is approximately
O(1); time boundaries within a bucket use binary search, followed by O(k) result
materialization.

The public `TransactionRepository` protocol allows a later SQLite implementation
without changing the analytics or presentation layers.

## LLM pipeline

Python calculates all financial values. The Anthropic layer receives only a
compact analytics snapshot containing metric IDs, labels, and display values; it
does not receive the raw CSV. Claude returns a schema-validated `InsightReport`,
and every insight must reference metric IDs that exist in the supplied snapshot.
Python remains responsible for displaying the referenced evidence values.

The generated commentary must not reinterpret net traded quantity as a confirmed
current position and must not claim P&L or performance because the source file
does not include opening positions or market-price history.

Copy the safe template and place your key in the ignored local `.env` file:

```bash
cp .env.example .env
```

```text
ANTHROPIC_API_KEY=your-api-key
ANTHROPIC_MODEL=claude-sonnet-5-5
```

`.env` is excluded by `.gitignore`; `.env.example` is safe to share because it
contains no credential. A key set directly in the process environment takes
precedence over the `.env` value.

Regular tests use a fake client and do not consume API credits.

## Test coverage

- `tests/test_processing.py` verifies schema enforcement, normalization, raw-row
  preservation, missing-trader warnings, duplicate quarantine, and invalid-row
  rejection.
- `tests/test_repository.py` verifies chronological ordering, ticker indexing,
  inclusive date retrieval, unknown tickers, and invalid date ranges.
- `tests/test_analytics.py` verifies portfolio totals, ticker VWAP, rankings,
  unknown-trader treatment, peak-hour logic, latest-price selection, and empty
  datasets.
- `tests/test_insights.py` verifies grounded snapshots and prompts, structured
  Anthropic responses, evidence validation, cache hashes, missing-key behavior,
  the 7,500-token response ceiling, and deterministic fallback commentary.
- `tests/test_presentation.py` verifies dashboard table ordering, UNKNOWN display
  labels, buy/sell time buckets, execution VWAP, trader-by-ticker net flow and
  latest-price marking, numeric chart values, quality-report traceability, and
  currency-neutral formatting.
- `tests/test_app.py` smoke-tests all five dashboard tabs and confirms that
  loading the application does not automatically call Anthropic.

## Dashboard

Run the local dashboard from the project root:

```bash
source .venv/bin/activate
streamlit run app.py
```

The bundled sample loads by default. The sidebar can replace it with another CSV
and filter the accepted transactions by date, ticker, action, and trader-ID
availability. Data-quality counts always describe the complete import. Claude is
called only after the **Generate AI Insights** button is pressed; identical
dataset/model/prompt combinations are reused within the current browser session.

Dashboard tabs:

- **Overview:** key statistics, ticker activity, and hourly buy/sell volume
- **Ticker Explorer:** linked execution-price and bounded-volume panels, VWAP, and chronological transactions
- **Trader Activity:** named-trader rankings, ticker-level net traded flow marked at the latest observed execution price, and separate unknown-trader activity
- **Data Quality:** auditable findings, policy documentation, and CSV downloads
- **AI Insights:** evidence-grounded Claude commentary and generation metadata

## Setup and tests

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
pytest
```

## Project structure

```text
src/portfolio_insights/models.py      Domain and quality-report models
src/portfolio_insights/processing.py  CSV validation and normalization
src/portfolio_insights/repository.py  In-memory indexed storage
src/portfolio_insights/analytics.py   Deterministic transaction analytics
src/portfolio_insights/insight_models.py  Anthropic request/response schemas
src/portfolio_insights/insights.py    Grounded prompting and Anthropic client
src/portfolio_insights/presentation.py  Dashboard DataFrame adapters
app.py                                Streamlit dashboard entry point
tests/                                Unit, integration, and dashboard smoke tests
```
