# Inherited loader — load_prices.py

This is an existing script a previous engineer left behind. It loads daily
OHLCV candles from a venue CSV into a local SQLite database `prices.db`.

## Run it
```
cd starter_pipeline
python load_prices.py
```
It will create `prices.db` in the current folder and print how many rows the
`prices` table has.

## What it does today
- Reads `../raw_feeds/binance_BTCUSD.csv`
- Inserts every row into a `prices` table
- Prints the row count

It is intentionally simple and not necessarily correct. Treat it as inherited
production code: understand it before you change it.
