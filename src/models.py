"""Canonical records shared by all source adapters."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Candle:
    """One normalized daily OHLCV candle from a venue."""

    venue: str
    symbol: str
    trading_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    volume_unit: str
    source_file: str
    source_row_number: int

    @property
    def business_key(self) -> tuple[str, str, date]:
        """Return the fields that uniquely identify a trusted candle."""
        return self.venue, self.symbol, self.trading_date


@dataclass(frozen=True)
class ReferencePrice:
    """One normalized daily external reference price."""

    symbol: str
    trading_date: date
    reference_close_usd: float
    source_file: str
    source_row_number: int

    @property
    def business_key(self) -> tuple[str, date]:
        """Return the fields that uniquely identify a reference price."""
        return self.symbol, self.trading_date
