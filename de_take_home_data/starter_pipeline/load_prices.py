"""
load_prices.py  --  starter market-data loader (INHERITED CODE)

Loads daily OHLCV candles from a venue CSV into a local SQLite database
(prices.db) so analysts can query them.

Currently loads Binance BTCUSD only. Run it with:

    python load_prices.py

It works... mostly. Part of your task is to understand what it does,
fix what it gets wrong, and extend it. Do NOT assume it is correct.

Fixes and extensions:

Fixes and extensions:

1. Fixed file paths so the script works from any directory
2. Reused the pipeline’s trusted database tables
3. Prevented duplicates using a primary key and idempotent upserts
4. Added checks to stop invalid OHLCV data from being saved
5. Loaded reference prices before validating venue prices
6. Moved source details and column mappings into configuration
7. Added a Gemini adapter to standardize its different format
8. Used a transaction to prevent partially loaded data
9. Added CLI options for database and data paths
10. Added logging for accepted, rejected, duplicate, and written rows

"""
import argparse
import logging
import sqlite3
import sys
from contextlib import closing
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Allow this file to be executed directly from any directory.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from src.database import initialize_database 
from src.helpers.config import SOURCES 
from src.loader import load_ohlcv_file, load_reference_file  

logger = logging.getLogger(__name__)

DB = PROJECT_ROOT / "output" / "prices.db"
SCHEMA_PATH = PROJECT_ROOT / "src" / "ddl" / "schema.sql"
RAW_FEEDS_DIR = PROJECT_ROOT / "data" / "raw_feeds"
DATA_DIR = PROJECT_ROOT / "data"

REFERENCE_SOURCES = (
    ("reference_BTCUSD.csv", "BTCUSD"),
    ("reference_ETHUSD.csv", "ETHUSD"),
)
LOADER_SOURCE_PATHS = frozenset(
    {
        Path("raw_feeds/binance_BTCUSD.csv"),
        Path("new_source/gemini_BTCUSD.csv"),
        Path("new_source/gemini_ETHUSD.csv"),
    }
)
def load(
    database_path: Path = DB,
    data_dir: Path = DATA_DIR,
):
    initialize_database(database_path, SCHEMA_PATH)

    results = []
    raw_feeds_dir = data_dir / "raw_feeds"

    with closing(sqlite3.connect(database_path)) as connection:
        with connection:
            # Load reference prices first.
            for filename, symbol in REFERENCE_SOURCES:
                source_path = raw_feeds_dir / filename

                result = load_reference_file(
                    connection,
                    source_path,
                    symbol,
                )
                results.append(result)

                if result.rejected:
                    raise ValueError(
                        f"{filename}: contains invalid reference prices"
                    )

            # reference-price lookup
            references = {
                (symbol, trading_date): reference_close
                for symbol, trading_date, reference_close
                in connection.execute(
                    "SELECT symbol, trading_date, reference_close_usd "
                    "FROM daily_reference_price"
                )
            }

            # Load every configured OHLCV source.
            for source in SOURCES:
                if source.relative_path not in LOADER_SOURCE_PATHS:
                    continue

                source_path = data_dir / source.relative_path

                result = load_ohlcv_file(
                    connection,
                    source_path,
                    source.symbol,
                    source.parser,
                    required_columns=source.required_columns,
                    references=(
                        references
                        if source.enforce_reference_check
                        else None
                    ),
                )
                results.append(result)

                for rejection in result.rejections:
                    logger.warning(
                        "Rejected %s row %d: %s",
                        rejection.source_file,
                        rejection.source_row_number,
                        ", ".join(rejection.reasons),
                    )

    return results



if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Load trusted market-price data"
    )
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()

    try:
        load(args.db, args.data_dir)
    except Exception:
        logger.exception("Load failed; transaction rolled back")
        raise SystemExit(1)
