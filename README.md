# Market Data Pipeline

Local Python and SQLite pipeline for daily cryptocurrency OHLCV files.

The project uses three logical layers:

- **Bronze:** original CSV files, unchanged.
- **Silver:** normalized and validated Python records.
- **Gold:** trusted SQLite tables for analyst queries.

## Requirements

- Python 3.10 or newer
- SQLite CLI only if you want to run the example SQL commands

The pipeline runtime uses only the Python standard library.

## Run the pipeline

From the repository root:

```bash
python3 -m de_take_home_data.starter_pipeline.main
```

The command loads all six venue files and both reference files, then creates:

```text
output/prices.db
```

Check the database tables:

```bash
sqlite3 output/prices.db ".tables"
```

Expected tables:

```text
daily_ohlcv  daily_reference_price
```

## Run the tests

From the repository root:

```bash
python3 -m unittest discover -s tests -v
```

The tests currently verify that:

- Applying the schema twice succeeds and does not create duplicate tables.
- A valid Binance row is normalized into the canonical candle format.
- The known invalid Binance OHLC row is rejected by validation.
- Loading Binance BTCUSD twice leaves exactly 119 trusted rows.
- Loading every Part 1 source twice leaves 700 OHLCV rows and 240 reference rows.

## Check rerun safety

Run the pipeline twice:

```bash
python3 -m de_take_home_data.starter_pipeline.main
python3 -m de_take_home_data.starter_pipeline.main
```

Both runs should complete successfully. Confirm the trusted row count:

```bash
sqlite3 output/prices.db \
  "SELECT COUNT(*) FROM daily_ohlcv; SELECT COUNT(*) FROM daily_reference_price;"
```

Expected result:

```text
700
240
```

## Project layout

```text
de_take_home_data/
├── raw_feeds/              # Bronze input files
├── new_source/             # Gemini input files
└── starter_pipeline/
    ├── main.py             # Pipeline entry point
    ├── adapters.py         # Source normalization
    ├── validation.py       # Data-quality rules
    ├── database.py         # SQLite setup and persistence
    ├── loader.py           # File loading and deduplication
    ├── models.py           # Canonical records
    ├── load_prices.py      # Inherited loader for Part 2
    └── ddl/schema.sql      # Gold table definitions

output/prices.db            # Produced SQLite database
tests/                      # Automated tests
design.md                   # Design and production notes
```

The implementation is still in progress. Persistent rejection reporting, missing-date reporting, reference-price comparison, and Gemini support are the next milestones.
