"""Declarative source definitions for the shared OHLCV loader."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..adapters import (
    parse_binance_row,
    parse_coinbase_row,
    parse_gemini_row,
    parse_kraken_row,
)
from ..models import Candle


@dataclass(frozen=True)
class SourceConfig:
    """Describe where a source lives and how it should be normalized."""

    relative_path: Path
    symbol: str
    parser: Callable[[dict[str, str], str, int, str], Candle]
    required_columns: frozenset[str]
    enforce_reference_check: bool = True


BINANCE_COLUMNS = frozenset(
    {"timestamp", "open", "high", "low", "close", "volume"}
)
KRAKEN_COLUMNS = frozenset(
    {"date", "open", "high", "low", "close", "volume"}
)
COINBASE_COLUMNS = frozenset(
    {"time", "open", "high", "low", "close", "volume"}
)
GEMINI_COLUMNS = frozenset(
    {"symbol", "time_ms", "o", "h", "l", "c", "base_vol"}
)


SOURCES = (
    SourceConfig(
        relative_path=Path("raw_feeds/binance_BTCUSD.csv"),
        symbol="BTCUSD",
        parser=parse_binance_row,
        required_columns=BINANCE_COLUMNS,
    ),
    SourceConfig(
        relative_path=Path("raw_feeds/binance_ETHUSD.csv"),
        symbol="ETHUSD",
        parser=parse_binance_row,
        required_columns=BINANCE_COLUMNS,
    ),
    SourceConfig(
        relative_path=Path("raw_feeds/kraken_BTCUSD.csv"),
        symbol="BTCUSD",
        parser=parse_kraken_row,
        required_columns=KRAKEN_COLUMNS,
    ),
    SourceConfig(
        relative_path=Path("raw_feeds/kraken_ETHUSD.csv"),
        symbol="ETHUSD",
        parser=parse_kraken_row,
        required_columns=KRAKEN_COLUMNS,
    ),
    SourceConfig(
        relative_path=Path("raw_feeds/coinbase_BTCUSD.csv"),
        symbol="BTCUSD",
        parser=parse_coinbase_row,
        required_columns=COINBASE_COLUMNS,
    ),
    SourceConfig(
        relative_path=Path("raw_feeds/coinbase_ETHUSD.csv"),
        symbol="ETHUSD",
        parser=parse_coinbase_row,
        required_columns=COINBASE_COLUMNS,
    ),
    SourceConfig(
        relative_path=Path("new_source/gemini_BTCUSD.csv"),
        symbol="BTCUSD",
        parser=parse_gemini_row,
        required_columns=GEMINI_COLUMNS,
        enforce_reference_check=False,
    ),
    SourceConfig(
        relative_path=Path("new_source/gemini_ETHUSD.csv"),
        symbol="ETHUSD",
        parser=parse_gemini_row,
        required_columns=GEMINI_COLUMNS,
        enforce_reference_check=False,
    ),
)
