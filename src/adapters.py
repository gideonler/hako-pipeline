"""Source-specific parsers that produce canonical pipeline records."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from .models import Candle, ReferencePrice

SINGAPORE_TIMEZONE = ZoneInfo("Asia/Singapore")


def parse_gemini_row(
    row: dict[str, str],
    source_file: str,
    source_row_number: int,
    expected_symbol: str,
) -> Candle:
    """Normalize a Gemini epoch-millisecond row into a canonical candle."""
    symbol = row["symbol"].replace("-", "").upper()

    if symbol != expected_symbol:
        raise ValueError(
            f"expected symbol {expected_symbol}, received {row['symbol']}"
        )

    timestamp = datetime.fromtimestamp(
        int(row["time_ms"]) / 1000,
        tz=timezone.utc,
    )

    return Candle(
        venue="gemini",
        symbol=symbol,
        trading_date=timestamp.astimezone(SINGAPORE_TIMEZONE).date(),
        open=float(row["o"]),
        high=float(row["h"]),
        low=float(row["l"]),
        close=float(row["c"]),
        volume=float(row["base_vol"]),
        volume_unit="base",
        source_file=source_file,
        source_row_number=source_row_number,
    )


def parse_binance_row(
    row: dict[str, str],
    source_file: str,
    source_row_number: int,
    symbol: str,
) -> Candle:
    """Normalize one Binance CSV row into a canonical candle."""
    timestamp = datetime.fromisoformat(row["timestamp"])

    return Candle(
        venue="binance",
        symbol=symbol,
        trading_date=timestamp.date(),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
        volume_unit="base",
        source_file=source_file,
        source_row_number=source_row_number,
    )


def parse_kraken_row(
    row: dict[str, str],
    source_file: str,
    source_row_number: int,
    symbol: str,
) -> Candle:
    """Normalize one Kraken CSV row into a canonical candle."""
    return Candle(
        venue="kraken",
        symbol=symbol,
        trading_date=date.fromisoformat(row["date"]),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
        volume_unit="base",
        source_file=source_file,
        source_row_number=source_row_number,
    )


def parse_coinbase_row(
    row: dict[str, str],
    source_file: str,
    source_row_number: int,
    symbol: str,
) -> Candle:
    """Normalize one Coinbase CSV row into a canonical candle."""
    return Candle(
        venue="coinbase",
        symbol=symbol,
        trading_date=date.fromisoformat(row["time"]),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
        volume_unit="unknown",
        source_file=source_file,
        source_row_number=source_row_number,
    )


def parse_reference_row(
    row: dict[str, str],
    source_file: str,
    source_row_number: int,
    symbol: str,
) -> ReferencePrice:
    """Normalize one external reference-price CSV row."""
    return ReferencePrice(
        symbol=symbol,
        trading_date=date.fromisoformat(row["date"]),
        reference_close_usd=float(row["reference_close_usd"]),
        source_file=source_file,
        source_row_number=source_row_number,
    )
