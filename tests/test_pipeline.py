import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from de_take_home_data.starter_pipeline.adapters import (
    parse_binance_row,
    parse_coinbase_row,
    parse_kraken_row,
)
from de_take_home_data.starter_pipeline.database import initialize_database
from de_take_home_data.starter_pipeline.loader import (
    load_ohlcv_file,
    load_reference_file,
)
from de_take_home_data.starter_pipeline.validation import validate_candle


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = (
    PROJECT_ROOT / "de_take_home_data" / "starter_pipeline" / "ddl" / "schema.sql"
)
RAW_FEEDS_DIR = PROJECT_ROOT / "de_take_home_data" / "raw_feeds"
BINANCE_BTC_PATH = RAW_FEEDS_DIR / "binance_BTCUSD.csv"


def read_binance_rows() -> list[dict[str, str]]:
    with BINANCE_BTC_PATH.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


class DatabaseTests(unittest.TestCase):
    def test_schema_can_be_applied_twice(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "prices.db"

            initialize_database(database_path, SCHEMA_PATH)
            initialize_database(database_path, SCHEMA_PATH)

            with sqlite3.connect(database_path) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }

        self.assertEqual(tables, {"daily_ohlcv", "daily_reference_price"})


class BinanceAdapterTests(unittest.TestCase):
    def test_valid_row_is_normalized(self) -> None:
        row = read_binance_rows()[0]

        candle = parse_binance_row(row, BINANCE_BTC_PATH.name, 2, "BTCUSD")

        self.assertEqual(candle.business_key, ("binance", "BTCUSD", candle.trading_date))
        self.assertEqual(candle.trading_date.isoformat(), "2026-01-01")
        self.assertEqual(validate_candle(candle), [])

    def test_invalid_ohlc_row_is_rejected(self) -> None:
        row = next(
            row
            for row in read_binance_rows()
            if row["timestamp"].startswith("2026-03-10")
        )

        candle = parse_binance_row(row, BINANCE_BTC_PATH.name, 72, "BTCUSD")

        self.assertEqual(
            validate_candle(candle),
            ["high_below_candle_value", "low_above_candle_value"],
        )


class BinanceLoadTests(unittest.TestCase):
    def test_rerun_keeps_same_trusted_row_count(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "prices.db"
            initialize_database(database_path, SCHEMA_PATH)

            first_result = load_ohlcv_file(
                database_path,
                BINANCE_BTC_PATH,
                "BTCUSD",
                parse_binance_row,
            )
            second_result = load_ohlcv_file(
                database_path,
                BINANCE_BTC_PATH,
                "BTCUSD",
                parse_binance_row,
            )

            with sqlite3.connect(database_path) as connection:
                trusted_count = connection.execute(
                    "SELECT COUNT(*) FROM daily_ohlcv "
                    "WHERE venue = 'binance' AND symbol = 'BTCUSD'"
                ).fetchone()[0]

        self.assertEqual(first_result.rows_read, 123)
        self.assertEqual(first_result.duplicates, 3)
        self.assertEqual(first_result.rejected, 1)
        self.assertEqual(first_result.accepted, 119)
        self.assertEqual(first_result.written, 119)
        self.assertEqual(second_result.accepted, 119)
        self.assertEqual(second_result.written, 0)
        self.assertEqual(trusted_count, 119)


class AllSourceLoadTests(unittest.TestCase):
    def test_all_part_one_sources_are_loaded_idempotently(self) -> None:
        ohlcv_sources = (
            ("binance_BTCUSD.csv", "BTCUSD", parse_binance_row),
            ("binance_ETHUSD.csv", "ETHUSD", parse_binance_row),
            ("kraken_BTCUSD.csv", "BTCUSD", parse_kraken_row),
            ("kraken_ETHUSD.csv", "ETHUSD", parse_kraken_row),
            ("coinbase_BTCUSD.csv", "BTCUSD", parse_coinbase_row),
            ("coinbase_ETHUSD.csv", "ETHUSD", parse_coinbase_row),
        )
        reference_sources = (
            ("reference_BTCUSD.csv", "BTCUSD"),
            ("reference_ETHUSD.csv", "ETHUSD"),
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "prices.db"
            initialize_database(database_path, SCHEMA_PATH)

            first_ohlcv_results = [
                load_ohlcv_file(
                    database_path,
                    RAW_FEEDS_DIR / filename,
                    symbol,
                    parser,
                )
                for filename, symbol, parser in ohlcv_sources
            ]
            first_reference_results = [
                load_reference_file(
                    database_path,
                    RAW_FEEDS_DIR / filename,
                    symbol,
                )
                for filename, symbol in reference_sources
            ]

            second_ohlcv_results = [
                load_ohlcv_file(
                    database_path,
                    RAW_FEEDS_DIR / filename,
                    symbol,
                    parser,
                )
                for filename, symbol, parser in ohlcv_sources
            ]
            second_reference_results = [
                load_reference_file(
                    database_path,
                    RAW_FEEDS_DIR / filename,
                    symbol,
                )
                for filename, symbol in reference_sources
            ]

            with sqlite3.connect(database_path) as connection:
                ohlcv_count = connection.execute(
                    "SELECT COUNT(*) FROM daily_ohlcv"
                ).fetchone()[0]
                reference_count = connection.execute(
                    "SELECT COUNT(*) FROM daily_reference_price"
                ).fetchone()[0]

        self.assertEqual(sum(result.accepted for result in first_ohlcv_results), 700)
        self.assertEqual(sum(result.duplicates for result in first_ohlcv_results), 6)
        self.assertEqual(sum(result.rejected for result in first_ohlcv_results), 6)
        self.assertEqual(
            sum(result.accepted for result in first_reference_results),
            240,
        )
        self.assertEqual(ohlcv_count, 700)
        self.assertEqual(reference_count, 240)
        self.assertEqual(sum(result.written for result in second_ohlcv_results), 0)
        self.assertEqual(sum(result.written for result in second_reference_results), 0)


if __name__ == "__main__":
    unittest.main()
