#!/usr/bin/env python3
"""
load_prices.py  --  starter market-data loader (INHERITED CODE)

Loads daily OHLCV candles from a venue CSV into a local SQLite database
(prices.db) so analysts can query them.

Currently loads Binance BTCUSD only. Run it with:

    python load_prices.py

It works... mostly. Part of your task is to understand what it does,
fix what it gets wrong, and extend it. Do NOT assume it is correct.
"""
import csv
import logging
import sqlite3

DB = "prices.db"
SOURCE_FILE = "../raw_feeds/binance_BTCUSD.csv"
VENUE = "binance"
ASSET = "BTCUSD"

logger = logging.getLogger(__name__)


def load():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS prices ("
        "venue TEXT, asset TEXT, ts TEXT, open REAL, high REAL, "
        "low REAL, close REAL, volume REAL)"
    )

    with open(SOURCE_FILE) as f:
        reader = csv.DictReader(f)
        for row in reader:
            cur.execute(
                "INSERT INTO prices (venue, asset, ts, open, high, low, close, volume) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (VENUE, ASSET, row["timestamp"], row["open"], row["high"],
                 row["low"], row["close"], row["volume"]),
            )

    conn.commit()
    n = cur.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    logger.info("Loaded. prices table now has %d rows.", n)
    conn.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    load()
