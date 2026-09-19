"""Command-line entry point for the trusted market-data pipeline."""

import logging
from pathlib import Path

from .adapters import parse_binance_row, parse_coinbase_row, parse_kraken_row
from .database import initialize_database
from .loader import LoadResult, load_ohlcv_file, load_reference_file


logger = logging.getLogger(__name__)

PIPELINE_DIR = Path(__file__).resolve().parent
DATA_DIR = PIPELINE_DIR.parent
PROJECT_ROOT = DATA_DIR.parent
SCHEMA_PATH = PIPELINE_DIR / "ddl" / "schema.sql"
RAW_FEEDS_DIR = DATA_DIR / "raw_feeds"
NEW_SOURCE_DIR = DATA_DIR / "new_source"
OUTPUT_DIR = PROJECT_ROOT / "output"
DATABASE_PATH = OUTPUT_DIR / "prices.db"

OHLCV_SOURCES = (
    ("binance_BTCUSD.csv", "BTCUSD", parse_binance_row),
    ("binance_ETHUSD.csv", "ETHUSD", parse_binance_row),
    ("kraken_BTCUSD.csv", "BTCUSD", parse_kraken_row),
    ("kraken_ETHUSD.csv", "ETHUSD", parse_kraken_row),
    ("coinbase_BTCUSD.csv", "BTCUSD", parse_coinbase_row),
    ("coinbase_ETHUSD.csv", "ETHUSD", parse_coinbase_row),
)

REFERENCE_SOURCES = (
    ("reference_BTCUSD.csv", "BTCUSD"),
    ("reference_ETHUSD.csv", "ETHUSD"),
)


def log_rejections(result: LoadResult) -> None:
    """Log every rejected source row with its quality failures."""
    for rejection in result.rejections:
        logger.warning(
            "Rejected %s row %d: %s",
            rejection.source_file,
            rejection.source_row_number,
            ", ".join(rejection.reasons),
        )


def main() -> None:
    """Initialize the trusted database and run the pipeline."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    initialize_database(DATABASE_PATH, SCHEMA_PATH)
    logger.info("Database initialized: %s", DATABASE_PATH)

    for filename, symbol, parser in OHLCV_SOURCES:
        result = load_ohlcv_file(
            DATABASE_PATH,
            RAW_FEEDS_DIR / filename,
            symbol,
            parser,
        )
        log_rejections(result)

    for filename, symbol in REFERENCE_SOURCES:
        result = load_reference_file(
            DATABASE_PATH,
            RAW_FEEDS_DIR / filename,
            symbol,
        )
        log_rejections(result)


if __name__ == "__main__":
    main()
