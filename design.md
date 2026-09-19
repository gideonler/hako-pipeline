# Market Data Pipeline Design Note

> Work in progress: this note describes the implementation completed so far and identifies the remaining work before submission.

## Architecture and current implementation

The solution uses a lightweight medallion architecture. The supplied CSV files are the immutable Bronze layer. Source adapters parse each source into a canonical `Candle` record, which is the logical Silver layer. Silver records pass shared type and OHLCV validation before they can be published to the Gold SQLite tables. Keeping parsing, validation, and persistence separate makes source-specific differences explicit and allows the storage implementation to be replaced later.

The current package is in `de_take_home_data/starter_pipeline/` and contains:

- `models.py`: the canonical daily `Candle` model and its business key.
- `adapters.py`: adapters for Binance, Kraken, Coinbase, and reference prices.
- `validation.py`: finite-number, positive-price, nonnegative-volume, and OHLC-bound checks.
- `database.py`: idempotent SQLite schema initialization.
- `loader.py`: Binance file ingestion, validation, deduplication, and transactional upserts.
- `ddl/schema.sql`: trusted-table constraints and an analyst query index.
- `main.py`: path resolution, logging, database initialization, and source orchestration.

The entry point creates `output/prices.db`, loads all six venue files, and loads both reference files. It can be run from the repository root with:

```bash
python3 -m de_take_home_data.starter_pipeline.main
```

## Schema and grain

The trusted `daily_ohlcv` table has one row per `venue`, `symbol`, and `trading_date`. This matches the source data's daily-candle grain while preserving venue-level price differences. The three fields form the primary key, preventing more than one trusted candle for the same business key and providing the basis for idempotent upserts.

OHLC values and volume are stored alongside `volume_unit`, because source volumes may not use comparable units. Provenance is retained through `source_file` and `source_row_number`, and `loaded_at` records when a row was published. ISO-formatted dates keep SQLite queries simple and sort correctly. Database `CHECK` constraints provide a final safeguard for positive prices, nonnegative volume, and valid candle bounds even if application validation is bypassed.

Reference prices are stored separately in `daily_reference_price`. A reference record has one close per symbol and date rather than a venue OHLCV candle, so forcing it into `daily_ohlcv` would create nullable or misleading fields. An index on `(symbol, trading_date)` supports the common analyst access pattern of retrieving a symbol's history across venues.

Timezone-aware timestamps will be converted deliberately before deriving `trading_date`. In particular, Gemini's epoch timestamps represent 16:00 UTC, which is midnight on the next calendar day in Singapore. Date-only feeds do not reveal their timezone, so that limitation will be documented rather than silently inventing timestamp precision.

## Data quality and reruns

Two layers protect the trusted tables: Python validation produces understandable rejection reasons, while SQLite constraints enforce the invariants at publication time. The completed structural checks detect non-finite numbers, prices at or below zero, negative volume, highs below another candle value, and lows above another candle value.

The loader deduplicates exact records, rejects every row involved in a conflicting business key, and uses `INSERT ... ON CONFLICT DO UPDATE` inside a transaction. A complete structural-quality run produces 700 trusted OHLCV rows and 240 reference rows. An unchanged rerun performs zero database writes. Before submission, the pipeline still needs persistent rejected-row reporting, missing-date reporting, and comparison with the supplied reference price.

## Inherited loader

The inherited `load_prices.py` currently reads only Binance BTCUSD, depends on the caller's working directory, inserts duplicates on every run, relies on SQLite's implicit string conversion, performs no validation, has no uniqueness constraint, and does not guarantee resource cleanup if an exception occurs. It also reports only the table's total row count, which does not explain what happened during the current run.

The completed change so far replaces `print` with structured logging and configures logging only when the script is executed as an entry point. The remaining Part 2 work is to replace working-directory-relative paths with `Path`-based paths, reuse the shared adapter and validation boundary, use context managers and an atomic transaction, enforce idempotency, report read/accepted/rejected counts, and add a Gemini adapter for its combined symbol, epoch-millisecond timestamp, abbreviated price columns, and base-volume field. This section will be updated to past tense as those fixes are completed.

## Production scheduling, monitoring, and alerting

For the supplied daily-file contract, I would keep the pipeline batch-oriented. An Airflow DAG would run after the expected delivery window and receive an explicit processing date, making scheduled runs and backfills behave the same way. Tasks would check file arrival, ingest each venue independently, run quality checks, and publish trusted data only after required checks pass. Retries would be safe because files would be tracked by checksum and trusted rows would be merged using their business key.

Each run would emit input, accepted, duplicate, rejected, and output counts; the latest trading date; file freshness; duration; and validation failures by rule and source. Alerts would cover missing or late files, job failure after retries, stale trusted data, unexpected row-count changes, duplicate conflicts, and rejection rates above a defined threshold. Logs would include a run ID, source file, and processing date so an alert can be traced to the affected input.

## Growth to millions of rows per day

The first constraints would be Python row-at-a-time inserts, SQLite's single-writer model, local disk, and full-table analytical scans. The initial improvements would be streaming CSV reads, batched `executemany` writes, one transaction per batch, and incremental processing of new files.

As retained volume and query concurrency grow, raw and normalized data would move to object storage as date- and venue-partitioned Parquet. Distributed processing such as Spark would be introduced when a single machine no longer meets the processing window, and trusted models would be served through a warehouse or lakehouse table format. Airflow would continue to manage retries and backfills, while dbt could own downstream SQL models and warehouse-level tests. The source adapters, canonical contract, validation rules, business keys, and provenance fields would remain applicable after replacing SQLite. Streaming infrastructure would only be introduced if the business requirement changed from daily files to near-real-time market data.
