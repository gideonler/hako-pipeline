"""SQLite connection and schema helpers."""

import sqlite3
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from .models import Candle, ReferencePrice


UPSERT_CANDLE_SQL = """
INSERT INTO daily_ohlcv (
    venue,
    symbol,
    trading_date,
    open,
    high,
    low,
    close,
    volume,
    volume_unit,
    source_file,
    source_row_number,
    loaded_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (venue, symbol, trading_date)
DO UPDATE SET
    open = excluded.open,
    high = excluded.high,
    low = excluded.low,
    close = excluded.close,
    volume = excluded.volume,
    volume_unit = excluded.volume_unit,
    source_file = excluded.source_file,
    source_row_number = excluded.source_row_number,
    loaded_at = excluded.loaded_at
WHERE daily_ohlcv.open IS NOT excluded.open
   OR daily_ohlcv.high IS NOT excluded.high
   OR daily_ohlcv.low IS NOT excluded.low
   OR daily_ohlcv.close IS NOT excluded.close
   OR daily_ohlcv.volume IS NOT excluded.volume
   OR daily_ohlcv.volume_unit IS NOT excluded.volume_unit
   OR daily_ohlcv.source_file IS NOT excluded.source_file
   OR daily_ohlcv.source_row_number IS NOT excluded.source_row_number
"""

UPSERT_REFERENCE_SQL = """
INSERT INTO daily_reference_price (
    symbol,
    trading_date,
    reference_close_usd,
    source_file,
    source_row_number,
    loaded_at
)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT (symbol, trading_date)
DO UPDATE SET
    reference_close_usd = excluded.reference_close_usd,
    source_file = excluded.source_file,
    source_row_number = excluded.source_row_number,
    loaded_at = excluded.loaded_at
WHERE daily_reference_price.reference_close_usd
          IS NOT excluded.reference_close_usd
   OR daily_reference_price.source_file IS NOT excluded.source_file
   OR daily_reference_price.source_row_number IS NOT excluded.source_row_number
"""


def initialize_database(db_path: Path, schema_path: Path) -> None:
    """Create the database and apply its schema idempotently."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_sql = schema_path.read_text(encoding="utf-8")

    with sqlite3.connect(db_path) as connection:
        connection.executescript(schema_sql)


def upsert_candles(db_path: Path, candles: Sequence[Candle]) -> int:
    """Insert or update validated candles in one transaction."""
    if not candles:
        return 0

    loaded_at = datetime.now(timezone.utc).isoformat()
    values = [
        (
            candle.venue,
            candle.symbol,
            candle.trading_date.isoformat(),
            candle.open,
            candle.high,
            candle.low,
            candle.close,
            candle.volume,
            candle.volume_unit,
            candle.source_file,
            candle.source_row_number,
            loaded_at,
        )
        for candle in candles
    ]

    with sqlite3.connect(db_path) as connection:
        connection.executemany(UPSERT_CANDLE_SQL, values)
        rows_changed = connection.total_changes

    return rows_changed


def upsert_reference_prices(
    db_path: Path,
    references: Sequence[ReferencePrice],
) -> int:
    """Insert or update validated reference prices in one transaction."""
    if not references:
        return 0

    loaded_at = datetime.now(timezone.utc).isoformat()
    values = [
        (
            reference.symbol,
            reference.trading_date.isoformat(),
            reference.reference_close_usd,
            reference.source_file,
            reference.source_row_number,
            loaded_at,
        )
        for reference in references
    ]

    with sqlite3.connect(db_path) as connection:
        connection.executemany(UPSERT_REFERENCE_SQL, values)
        rows_changed = connection.total_changes

    return rows_changed
