import csv
import sqlite3
import tempfile
import unittest
import shutil
import subprocess
import sys
from contextlib import closing
from pathlib import Path

from src.adapters import (
    parse_binance_row,
    parse_coinbase_row,
    parse_gemini_row,
    parse_kraken_row,
)
from src.database import initialize_database
from src.helpers.config import (
    BINANCE_COLUMNS,
    COINBASE_COLUMNS,
    GEMINI_COLUMNS,
    KRAKEN_COLUMNS,
)
from src.loader import (
    load_ohlcv_file,
    load_reference_file,
)
from src.validation import validate_candle
from src.main import run_pipeline
from de_take_home_data.starter_pipeline.load_prices import load as load_inherited


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = (
    PROJECT_ROOT / "src" / "ddl" / "schema.sql"
)
RAW_FEEDS_DIR = PROJECT_ROOT / "data" / "raw_feeds"
BINANCE_BTC_PATH = RAW_FEEDS_DIR / "binance_BTCUSD.csv"
DATA_DIR = PROJECT_ROOT / "data"
GEMINI_BTC_PATH = DATA_DIR / "new_source" / "gemini_BTCUSD.csv"


def read_binance_rows() -> list[dict[str, str]]:
    with BINANCE_BTC_PATH.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


class DatabaseTests(unittest.TestCase):
    def test_schema_can_be_applied_twice(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "prices.db"

            initialize_database(database_path, SCHEMA_PATH)
            initialize_database(database_path, SCHEMA_PATH)

            with closing(sqlite3.connect(database_path)) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }

        self.assertEqual(tables, {"daily_ohlcv", "daily_reference_price",
                                  "rejected_rows", "missing_dates"})


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
                required_columns=BINANCE_COLUMNS,
            )
            second_result = load_ohlcv_file(
                database_path,
                BINANCE_BTC_PATH,
                "BTCUSD",
                parse_binance_row,
                required_columns=BINANCE_COLUMNS,
            )

            with closing(sqlite3.connect(database_path)) as connection:
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
            ("binance_BTCUSD.csv", "BTCUSD", parse_binance_row, BINANCE_COLUMNS),
            ("binance_ETHUSD.csv", "ETHUSD", parse_binance_row, BINANCE_COLUMNS),
            ("kraken_BTCUSD.csv", "BTCUSD", parse_kraken_row, KRAKEN_COLUMNS),
            ("kraken_ETHUSD.csv", "ETHUSD", parse_kraken_row, KRAKEN_COLUMNS),
            ("coinbase_BTCUSD.csv", "BTCUSD", parse_coinbase_row, COINBASE_COLUMNS),
            ("coinbase_ETHUSD.csv", "ETHUSD", parse_coinbase_row, COINBASE_COLUMNS),
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
                    required_columns=required_columns,
                )
                for filename, symbol, parser, required_columns in ohlcv_sources
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
                    required_columns=required_columns,
                )
                for filename, symbol, parser, required_columns in ohlcv_sources
            ]
            second_reference_results = [
                load_reference_file(
                    database_path,
                    RAW_FEEDS_DIR / filename,
                    symbol,
                )
                for filename, symbol in reference_sources
            ]

            with closing(sqlite3.connect(database_path)) as connection:
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


class CompletePipelineTests(unittest.TestCase):
    def test_reference_gate_and_nonfinite_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "prices.db"
            source = Path(directory) / "binance_BTCUSD.csv"
            row = read_binance_rows()[0]
            initialize_database(database, SCHEMA_PATH)
            def write(record):
                with source.open("w", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=row.keys())
                    writer.writeheader()
                    writer.writerow(record)
            write(row)
            missing = load_ohlcv_file(database, source, "BTCUSD",
                                      parse_binance_row,
                                      required_columns=BINANCE_COLUMNS,
                                      references={})
            self.assertIn("missing_reference_price", missing.rejections[0].reasons)
            for value in ("nan", "inf", "-1"):
                write(dict(row, close=value))
                result = load_ohlcv_file(
                    database,
                    source,
                    "BTCUSD",
                    parse_binance_row,
                    required_columns=BINANCE_COLUMNS,
                )
                self.assertEqual(result.accepted, 0)
                self.assertEqual(result.rejected, 1)

    def snapshot(self, database):
        with closing(sqlite3.connect(database)) as connection:
            return {table: connection.execute(
                f"SELECT * FROM {table} ORDER BY 1, 2, 3").fetchall()
                for table in ("daily_ohlcv", "daily_reference_price",
                              "rejected_rows", "missing_dates")}

    def test_quality_audit_and_exact_rerun(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "prices.db"
            # Seed the old, structurally valid outlier to verify its removal.
            initialize_database(database, SCHEMA_PATH)
            load_ohlcv_file(
                database,
                BINANCE_BTC_PATH,
                "BTCUSD",
                parse_binance_row,
                required_columns=BINANCE_COLUMNS,
            )
            results = run_pipeline(database, RAW_FEEDS_DIR)
            before = self.snapshot(database)
            again = run_pipeline(database, RAW_FEEDS_DIR)
            self.assertEqual(before, self.snapshot(database))
            self.assertEqual(len(before["daily_ohlcv"]), 698)
            self.assertEqual(len(before["daily_reference_price"]), 240)
            self.assertEqual(len(before["rejected_rows"]), 8)
            self.assertEqual(len(before["missing_dates"]), 14)
            self.assertEqual(sum(r.removed for r in results), 1)
            self.assertEqual(sum(r.written + r.removed for r in again), 0)
            self.assertEqual(sum(r.rows_read for r in results), 952)
            self.assertEqual(sum(r.duplicates for r in results), 6)
            self.assertFalse(any(row[0] == "binance" and row[2] == "2026-01-30"
                                 for row in before["daily_ohlcv"]))
            self.assertTrue(all(row[0].startswith("coinbase")
                                and "2026-03-04" <= row[2] <= "2026-03-10"
                                for row in before["missing_dates"]))

    def test_late_failure_rolls_back_all_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "prices.db"
            raw = root / "raw"
            shutil.copytree(RAW_FEEDS_DIR, raw)
            run_pipeline(database, raw)
            before = self.snapshot(database)
            # A valid early correction followed by a malformed final file.
            reference = raw / "reference_BTCUSD.csv"
            reference.write_text(reference.read_text().replace("90410.44", "90411.44"))
            (raw / "coinbase_ETHUSD.csv").write_text("wrong_header\n1\n")
            with self.assertRaisesRegex(ValueError, "missing required columns"):
                run_pipeline(database, raw)
            self.assertEqual(before, self.snapshot(database))

    def test_conflicts_reject_all_occurrences_and_remove_stale_value(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "prices.db"
            source = Path(directory) / "binance_BTCUSD.csv"
            rows = read_binance_rows()
            initialize_database(database, SCHEMA_PATH)
            def write(records):
                with source.open("w", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(records)
            write([rows[0]])
            load_ohlcv_file(
                database,
                source,
                "BTCUSD",
                parse_binance_row,
                required_columns=BINANCE_COLUMNS,
            )
            changed = dict(rows[0], volume="999")
            write([rows[0], rows[0], changed])
            result = load_ohlcv_file(
                database,
                source,
                "BTCUSD",
                parse_binance_row,
                required_columns=BINANCE_COLUMNS,
            )
            self.assertEqual((result.accepted, result.duplicates, result.rejected),
                             (0, 0, 3))
            self.assertEqual(result.removed, 1)


class InheritedLoaderTests(unittest.TestCase):
    def test_gemini_adapter_normalizes_symbol_and_singapore_date(self):
        with GEMINI_BTC_PATH.open(newline="", encoding="utf-8") as source:
            row = next(csv.DictReader(source))

        candle = parse_gemini_row(row, GEMINI_BTC_PATH.name, 2, "BTCUSD")

        self.assertEqual(candle.venue, "gemini")
        self.assertEqual(candle.symbol, "BTCUSD")
        self.assertEqual(candle.trading_date.isoformat(), "2026-01-01")
        self.assertEqual(candle.volume_unit, "base")
        with self.assertRaisesRegex(ValueError, "expected symbol ETHUSD"):
            parse_gemini_row(row, GEMINI_BTC_PATH.name, 2, "ETHUSD")

    def test_inherited_loader_onboards_gemini_idempotently(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "prices.db"
            first = load_inherited(database, DATA_DIR)
            before = CompletePipelineTests().snapshot(database)
            second = load_inherited(database, DATA_DIR)

            self.assertEqual(before, CompletePipelineTests().snapshot(database))
            with closing(sqlite3.connect(database)) as connection:
                counts = dict(
                    connection.execute(
                        "SELECT venue, COUNT(*) FROM daily_ohlcv GROUP BY venue"
                    )
                )
                reference_count = connection.execute(
                    "SELECT COUNT(*) FROM daily_reference_price"
                ).fetchone()[0]

        self.assertEqual(counts, {"binance": 118, "gemini": 240})
        self.assertEqual(reference_count, 240)
        self.assertEqual(sum(item.rejected for item in first), 2)
        self.assertEqual(sum(item.duplicates for item in first), 3)
        self.assertEqual(sum(item.written + item.removed for item in second), 0)

    def test_direct_script_works_from_another_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "prices.db"
            script = (
                PROJECT_ROOT
                / "de_take_home_data"
                / "starter_pipeline"
                / "load_prices.py"
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--db",
                    str(database),
                    "--data-dir",
                    str(DATA_DIR),
                ],
                cwd=directory,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            with closing(sqlite3.connect(database)) as connection:
                gemini_count = connection.execute(
                    "SELECT COUNT(*) FROM daily_ohlcv WHERE venue = 'gemini'"
                ).fetchone()[0]
            self.assertEqual(gemini_count, 240)


if __name__ == "__main__":
    unittest.main()
