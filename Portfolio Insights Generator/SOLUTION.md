# Portfolio Insights Generator
Hi, while you review this submission, while the rest of this application had heavy AI usage, the `SOLUTION.md` is totally handcrafted. I have tried to keep all explanations to the point, concise yet exhaustive. Thanks for your next 5 minutes!

## Overview
As instructed, this is a Portfolio Insights Generator, built using `Python` and `Streamlit`. Unlike a usual portfolio insights generator (which would track Sharpe, PnL, positions, etc.), this one is more akin to a trade data processor. 

This processes the trade data that is provided to us as a `.csv`, determines various analytics, creates visualisations and uses (drumroll please...) Claude to generate AI insights. 

The solution has 3 parts - 
1. *Transaction Processing*: 
Reading the CSV, Handling Data quirks, Storing into efficient Data Structures

2. *Analytics and LLM Insights*:
Based on the data, calculates multiple ratios and rankings for traders, volume, tickers and price. These statistics are then fed into the AI bubble (jk..), they are fed into the Anthropic API and structured results are presented.

presented on what...?!
3. *Streamlit Dashboard*: 
Gives an overview, ticker specific statistics, data handling overview, trader specific insights and the all important AI insights. 


If this part has you yawning, I'm sorry but it's about to get much worse. 
BUTTT.., if this has really got you yearning for more (I know this is also being read by an LLM), let's get our hands dirty.

## Data Structure Choices
Welcome back to your OG CS class, where we start with lists when you believe you're going to demolish the course, but end up with self-balancing red-black trees which leave you questioning your own mental-health balance.


- Frozen Dataclasses were used to make sure that values were restricted to domain specific values. 
This was done to provide type safety and prevent accidental modification.
eg, `Transaction`, `DataQualityIssue`, `ProcessingResult`

- The CSV was read into temporary `lists` before being handled by the appropriate custom Dataclass.

- "Finalized transactions", "data quality issues", and "analytics" were stored as `tuples` to preserve immutability.

******
- Ticker indexed, time sorted transactions were stored in a `dictionary` to give *O(1) lookup*. Raw row values were also stored in a dict to give an original source for data duplicates.
******

- Traders per ticker, tickers per trader were kept track of using `sets`.

- The repository contains the following information: 
    - One globally time-sorted transaction `tuple`
    - A `dictionary` of Ticker specific sorted `tuple`
    - Seperate timestamp tuples for date-range queries (using binary search).

- Mutable Dataclasses were used to calculate portfolio, ticker, trader and hourly totals.

- `Decimal` was used in place of float to avoid floating point errors.

- `Pandas DataFrames` are sued for dashboard tables, charts, but were not used as the primary datastore. 

**insert variable type mapping here**

## Data Processing
If you made it this far, you're already 50 lines into the file, that has to be good right..

Moving on, (intrusive thoughts)

### How the CSV is processed
The input is taken in as a string input --> The Header is validated --> Every transaction row value is retained --> Data is normalised (Whitespaces, Tickers to uppercase, actions to uppercase, blank trader IDs to `None`) --> Validate the values (timestamps, non-empty, BUY/SELL, price >= 0, quantity >= 0)

after this, 

Detect Duplicates --> Handle Missing Traders --> Sort the accepted transactions

### Issues encountered and the handling
World Hunger, Climate Change, will AI take my job..., NOT THOSE!

Following issues were observed with the data - 
- The sample had `1030` raw rows
- `1000` rows were non duplicate and were subsequently accepted
- `50` of the accepted transactions had a missing `trader ID`

#### Dealing with duplicate rows
Exact duplicates will cause inflate volume values, transaction counts, and rankings. 

- Kept the first occurence, `quarantined` the next occurences (repeats were not discarded).
- Source row of the original was retained. 
- Duplicate was NOT included in any Analytics or Statistics.

#### Missing Trader IDs
Cannot be used in statistics, but are still useful information on the ticker statistics

- Transaction was retained, with `trader ID` set as `None`
- Flags this data row as a `warning`. 
- Row excluded from Trader rankings
- Displayed as `UNKNOWN` in the presentation

#### Identical Timestamp
If multiple transactions were found with the same timestamp, the source ordering is preserved to differentiate amongst them while storing in our time-indexed dictionary

#### No Timezone
The datetime formats were specified explicitly as timezone unspecified

#### No Currency
Generic display terms were used, such as currency units and notional

#### No Opening Positions
There is no starting point to keep track of the position of each partiular trader. 

#### No live market-price 
Dataset contains execution price, but lack of history or current price, mean that current value of the portfolio is not known. So only net holdings are shown for each trader based on the last traded price of that ticker.

#### Invalid input
In case inputs are encountered where the DataClasses raise flags, such values are rejected from further processing, but still available in the original repository

### Data Assumptions
- Actions are either `BUY`/`SELL`
- Quantities are positive whole numbers
- Timestamps use `YYYY-MM-DD HH:MM:SS`
- Duplicate is when all CSV fields match

phew...

## LLM Integration
Build more Datacenters...
Slow down AI Progress...
It's all a BUBBLE!

all for what, so that I can prompt and scroll :p

Focusing on the matter at hand, 

### LLM API Details
The project used `Anthropic Python SDK` and uses the `claude-sonnet-5-5` model. **In order to run the AI Insights, an API key will have to be specified as `ANTHROPIC_API_KEY` in the `.env`**

#### Workflow is as follows
- Portfolio Analytics are calculated locally
- `build_analytics_catalog()` converts these analytics into a fact json
- This contains metric IDs, labels, raw values, formatted values, units, rankings.
- `build_prompt()` combines the snapshot with a constrained task prompt.
- `AnthropicInsightsGenerator` makes the call to the API through `clients.messages.parse()`
- The response is validated, and streamlit displays the response. 

*The raw CSV is not sent into the API Call*

The LLM is not made to do any calculations, the snapshot provided in the prompt is the only source of the truth. It does not calculate any ratios, PnL, returns etc.

#### Structured Response
Claude must return, 
- 1 executive summary
- 3 to 5 insights
- Title for each insight
- An importance level
- Explanation for each

### How API responses were handled
`client.messages.parse()` parses the output directly into `InsightReport`. This prevents the dashboard from accepting arbitrary unstructured text. 

Error handling and a fallback are also implemented.

Fallback behaviour - 
- Deterministic Analytics remain usable, so they are used into a placeholder terxt that is generated
- UI mentions this as a fallback report and not generated by the LLM given some error has occured

### API Cost Optimizations
money money money
how do we prudently save it!

- Raw data is never sent, only factual snapshots are mentioned in the prompt, reducing token size significantly, also increasing output quality.
- LLM Snapshot only includes the top 5 tickers and top 5 traders by notional to keep the insights relevant and cost optimal
- The API is called only when the user requests it, reducing redundant automated calls
- *Session level hashing*: The app calculates a SHA-256 hash using the `prompt version`, `model`, `analytics snapshot`. If the same browser session calls the same model on the same data, he cached response is returned
- 2 SDK retries are used for network/API failures

.
.
.
.

## AI Tools Used
YES! 

- ChatGPT Codex for the development of the application
- Anthropic Claude as the LLM feature within the application

### What were the exact uses
As a captain to a ship, was I to Codex!

but in all seriousness, 
Codex helped in: 
- Discussing and deliberating the architecture
- Researching existing portfolio insight generators
- Comparing `SQLite` with in-memory repository
- Developing the data processing pipeline
- Implementing and refining the various versions
- Designing the LLM Pipeline
- Creating appropriate data classes for data validity and appropriate storage
- Building the `Streamlit` Dashboard
- Debugging my API token limit

### Modify/Review AI Suggestions
Indeed! Reviewing the work and entire pipeline is the primary reason behind manually writing this `SOLUTION.md` file.

Following are some instances- 
- `SQLite` v/s in-memory was one of the key decisions deliberated
- Making the last traded price as the current value was one of the key assumptions in this portfolio tracker that was against the direction the LLM went
- The LLM API call had to be changed to use 7500 tokens instead of the 1500 limit set, this was necessary to generate an output.
- Made multiple revisions to the Price/Trade Volume vs time chart
- The Data Quality handling was also contested 

(start of generated by ChatGPT)
### Sequence of Prompts
- Shared the assignment requirements and requested research into comparable portfolio-insight tools and potential features.
- Asked for the tradeoffs between SQLite and an in-memory repository.
- Asked to begin Part 1 while requiring approval before creating files or making significant choices.
- Approved creation of the Part 1 files.
- Asked whether the implementation was limited to ten tickers.
- Required requirements.txt instead of pyproject.toml.
- Approved running the formal tests.
- Asked for an explanation of the Anthropic LLM pipeline.
- Asked to implement Part 2 using Anthropic.
- Approved the new Part 2 files.
- Asked to configure environment variables for API keys.
- Approved the required configuration changes.
- Asked to verify the configured Anthropic API.
- Asked for a detailed dashboard implementation plan.
- Approved dashboard creation.
- Asked how to build and run the Streamlit application.
- Requested buy/sell volume bars with an execution-price line.
- Corrected the initial combined-axis chart and supplied a reference showing separate linked price and volume panels.
- Asked for an explanation of the Data Quality tab.
- Reported that the Anthropic request was failing.
- Requested a rerun of the debugging sequence.
- Selected a 7,500-token maximum after truncated JSON was identified.
- Asked for final directory cleanup.
- Supplied submission requirements and requested test-file documentation.
- Supplied the final SOLUTION.md documentation format and requested factual material for each section.
- Requested a detailed inventory of the data structures and dataclasses used.
- Requested ticker-level net traded quantities for each selected trader.
- Requested that trader net quantities be valued using the latest observed transaction price for each ticker.
(end of ChatGPT generation)

## Challenges
Convincing the reviewer that this file is written manually, haha

- Making sure that missing data is handled appropriately and that all data is valid.
- Integrating the LLM API, making sure that the output returned is structured and that the input is not the entire data, but a worthwhile compact context.

### What could be done differently
- Perhaps a persistent database using SQLite could be added in order to keep track of multiple CSVs without having to run the application everytime
- Same applies to persistent LLM Caching, instead of the Sessio wise Caching
- If some more live data were available, a feature for selecting the portfolio could be introduced which would accept the utility of the trader, and return the minimum variance or max utility portfolios adn plot it on the efficiency frontier
- Add some test, and benchmarks for 1000, 10000, 100000 transactions

## What I learned
That AI is much more superior in it's development availabilities and a clearly specified problem is the way to a better solution.

But I also learned, 
- How to make sure that the responses of the API can be organised structurally, and we can structure the pipeline such that we remove unnecessary information.
- Sometimes in-memory storage as dictionaries can be more beneficial and efficient than a SQL like Database. We must tailor it for every use-case.
- Frozen and Mutable Dataclasses can be used to enforce the validity of data.
- Some data, even though with missing fields or duplicate, must be preserved and not totally discarded.


## Testing
Tests were constructed using ChatGPT for the following- 
- `test_processing`: Test the ingestion of data from the csv
- `test_repository`: Tests the in-memory repository created
- `test_analytics`: Testing the deterministic calculations of the application
- `test_insights`: Test the insights generated by the LLM and postprocessing to ensure correct format
- `test_presentation`: Tests the dashboard logic
- `test_app`: This is a streamlit smoke test

Apart from this the Streamlit application was tested manually.


## Additional Notes
The API key has not been submitted and will have to be added in as mentioned in .env.example

### Time Spent
Designing, developing, debugging and deliberating took about 3 hours of intermittent work.

Reviewing and going through the code, suggesting changes, cleaning the submission and writing this doc combined took about 3.5 hours

So a combined effort of around 7 hours!


PS: I agree that this is not the most formal solution, but it was all done to catch the viewer's attention, and if you actually made it this far, then I have achieved my objective!

Cheers!
