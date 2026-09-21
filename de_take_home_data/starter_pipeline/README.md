# Inherited loader — `load_prices.py`

This is the inherited Part 2 entry point. It has been fixed to reuse the shared
trusted schema, source adapters, validation, transactions, and idempotent
upserts. It has also been extended to load Gemini's different source format.

## Run it

From the repository root:

```bash
python3 de_take_home_data/starter_pipeline/load_prices.py
```

The paths are resolved from the script location, so the command also works when
started from another directory. Optional paths can be supplied with:

```bash
python3 de_take_home_data/starter_pipeline/load_prices.py \
  --db output/prices.db \
  --data-dir data
```

## What it loads

- BTCUSD and ETHUSD reference-price files
- Binance BTCUSD from the inherited source
- Gemini BTCUSD and ETHUSD from the new source

Reference prices are loaded first. The venue files are then parsed through the
source configuration and shared loader. Gemini symbols, epoch-millisecond
timestamps, and short column names are normalized by `src/adapters.py`.

## Behaviour

- Invalid OHLCV records are kept out of the trusted table.
- Primary keys and conditional upserts make reruns idempotent.
- All files are loaded in one transaction, so a fatal error rolls back the run.
- Logs report read, accepted, duplicate, rejected, written, and removed rows.
- Gemini receives the shared structural checks. Its configurable reference-price
  comparison is disabled pending confirmation that the candle windows are
  directly comparable.

Rejected rows from this entry point are logged. The Part 1 entry point
`python3 -m src.main` additionally persists rejected rows and missing dates in
the audit tables.

## Verify it

Run the loader twice and confirm the second run does not add trusted rows. Then
run the complete automated suite from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

The tests cover Gemini normalization, rerun safety, execution from another
directory, and transaction rollback.
