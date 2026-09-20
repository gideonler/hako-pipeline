"""Command-line entry point for the trusted market-data pipeline."""

import argparse
import json
import logging
import sqlite3
from datetime import date
from pathlib import Path

from .database import database_session, initialize_database
from .helpers.config import SOURCES
from .loader import LoadResult, load_ohlcv_file, load_reference_file


logger = logging.getLogger(__name__)

PIPELINE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PIPELINE_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
SCHEMA_PATH = PIPELINE_DIR / "ddl" / "schema.sql"
RAW_FEEDS_DIR = DATA_DIR / "raw_feeds"
OUTPUT_DIR = PROJECT_ROOT / "output"
DATABASE_PATH = OUTPUT_DIR / "prices.db"
EXPECTED_START = date(2026, 1, 1)
EXPECTED_END = date(2026, 4, 30)

REFERENCE_SOURCES = (
    ("reference_BTCUSD.csv", "BTCUSD"),
    ("reference_ETHUSD.csv", "ETHUSD"),
)


def save_audit_results(
    connection: sqlite3.Connection,
    source_file: str,
    symbol: str,
    result: LoadResult,
) -> None:
    """Save and log rejected rows and missing input dates."""
    connection.executemany(
        "INSERT INTO rejected_rows "
        "(source_file, source_row_number, reasons, raw_record) "
        "VALUES (?, ?, ?, ?)",
        [
            (
                rejection.source_file,
                rejection.source_row_number,
                json.dumps(rejection.reasons),
                rejection.raw_record,
            )
            for rejection in result.rejections
        ],
    )
    connection.executemany(
        "INSERT INTO missing_dates "
        "(source_file, symbol, trading_date) VALUES (?, ?, ?)",
        [
            (source_file, symbol, missing_date)
            for missing_date in result.missing_dates
        ],
    )

    for rejection in result.rejections:
        logger.warning(
            "Rejected %s row %d: %s",
            rejection.source_file,
            rejection.source_row_number,
            ", ".join(rejection.reasons),
        )
    if result.missing_dates:
        logger.warning(
            "%s missing input dates: %s",
            source_file,
            ", ".join(result.missing_dates),
        )


def run_pipeline(
    database_path: Path = DATABASE_PATH,
    raw_dir: Path = RAW_FEEDS_DIR,
    max_deviation: float = 0.20,
) -> list[LoadResult]:
    """
    Publish the six raw venue files and two references in one transaction.
    """
    initialize_database(database_path, SCHEMA_PATH)
    results: list[LoadResult] = []
    expected_period = {
        "expected_start": EXPECTED_START,
        "expected_end": EXPECTED_END,
    }

    with database_session(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM rejected_rows")
        connection.execute("DELETE FROM missing_dates")

        for filename, symbol in REFERENCE_SOURCES:
            result = load_reference_file(
                connection,
                raw_dir / filename,
                symbol,
                **expected_period,
            )
            results.append(result)
            save_audit_results(connection, filename, symbol, result)
            if result.rejected or result.missing_dates:
                raise ValueError(f"{filename}: reference coverage is invalid")

        references = {
            (symbol, trading_date): close
            for symbol, trading_date, close in connection.execute(
                "SELECT symbol, trading_date, reference_close_usd "
                "FROM daily_reference_price"
            )
        }

        for source in SOURCES:
            if source.relative_path.parent != Path("raw_feeds"):
                continue

            source_path = raw_dir / source.relative_path.name
            result = load_ohlcv_file(
                connection,
                source_path,
                source.symbol,
                source.parser,
                required_columns=source.required_columns,
                references=references,
                max_deviation=max_deviation,
                **expected_period,
            )
            results.append(result)
            save_audit_results(
                connection,
                source_path.name,
                source.symbol,
                result,
            )

    logger.info(
        "Committed: accepted records=%d rejected rows=%d exact duplicates=%d",
        sum(result.accepted for result in results),
        sum(result.rejected for result in results),
        sum(result.duplicates for result in results),
    )
    return results


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    parser = argparse.ArgumentParser(description="Build trusted daily market data")
    parser.add_argument("--db", type=Path, default=DATABASE_PATH)
    parser.add_argument("--raw-dir", type=Path, default=RAW_FEEDS_DIR)
    parser.add_argument(
        "--max-deviation",
        type=float,
        default=0.20,
        help="Maximum close/reference relative deviation (default 0.20)",
    )
    args = parser.parse_args()
    try:
        run_pipeline(args.db, args.raw_dir, args.max_deviation)
    except Exception:
        logger.exception("Pipeline failed; data transaction rolled back")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
